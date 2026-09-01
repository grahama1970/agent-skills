#!/usr/bin/env python3
"""Load a curate-client prep pack into a running Live Evidence server."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from live_evidence.config import DEFAULT_BACKEND_URL  # noqa: E402

try:
    from validate_prep_pack import validate as validate_prep_pack
except ImportError:  # pragma: no cover - direct script path fallback
    sys.path.insert(0, str(ROOT / "scripts"))
    from validate_prep_pack import validate as validate_prep_pack

DEFAULT_MEMORY_URL = "http://127.0.0.1:8601"


def _http_url_or_default(value: str | None, default: str) -> str:
    if value and value.startswith(("http://", "https://")):
        return value
    return default


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _post_json(base_url: str, path: str, body: dict[str, Any], *, timeout_s: float) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            raw = response.read().decode("utf-8")
            status = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        status = exc.code
    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        payload = {"body": raw}
    return status, payload


def _strip_classification(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip_classification(v) for k, v in value.items() if k != "classification"}
    if isinstance(value, list):
        return [_strip_classification(item) for item in value]
    return value


def _post_briefing(backend_url: str, briefing_pack: dict[str, Any], *, timeout_s: float) -> dict[str, Any]:
    status, payload = _post_json(
        backend_url,
        "/api/briefing/load",
        _strip_classification(briefing_pack),
        timeout_s=timeout_s,
    )
    return {
        "endpoint": "/api/briefing/load",
        "backend_url": backend_url,
        "status_code": status,
        "ok": status == 202,
        "response": payload,
    }


def _recall_probe(
    memory_url: str,
    *,
    canonical_question: str,
    collections: list[str],
    expected_keys: list[str],
    timeout_s: float,
) -> dict[str, Any]:
    status, payload = _post_json(
        memory_url,
        "/recall",
        {"q": canonical_question, "collections": collections, "k": 20},
        timeout_s=timeout_s,
    )
    returned_keys = [item.get("_key") for item in payload.get("items", []) if isinstance(item, dict)]
    missing = [key for key in expected_keys if key not in returned_keys]
    return {
        "canonical_question": canonical_question,
        "status_code": status,
        "found": bool(payload.get("found")),
        "confidence": payload.get("confidence"),
        "returned_keys": returned_keys,
        "expected_keys": expected_keys,
        "missing_expected_keys": missing,
        "ok": status == 200 and not missing,
    }


def verify_oracle_recall(pack: dict[str, Any], *, memory_url: str, timeout_s: float) -> dict[str, Any]:
    memory_exports = pack.get("memory_exports") or {}
    collections = [str(item) for item in memory_exports.get("collections") or []]
    probes = []
    for oracle in pack.get("question_oracles") or []:
        probes.append(
            _recall_probe(
                memory_url,
                canonical_question=str(oracle.get("canonical_question") or oracle.get("question_id") or ""),
                collections=collections,
                expected_keys=[str(key) for key in oracle.get("memory_keys") or []],
                timeout_s=timeout_s,
            )
        )
    return {
        "memory_url": memory_url,
        "collections": collections,
        "probe_count": len(probes),
        "probes": probes,
        "ok": bool(probes) and all(probe["ok"] for probe in probes),
    }


def load_prep_pack(
    pack_path: Path,
    *,
    backend_url: str,
    memory_url: str,
    timeout_s: float,
    skip_briefing: bool = False,
    skip_recall: bool = False,
) -> dict[str, Any]:
    validation = validate_prep_pack(pack_path)
    pack = _load_json(pack_path)
    receipt: dict[str, Any] = {
        "schema": "live_evidence.prep_pack_load_receipt.v1",
        "status": "PASS",
        "pack_path": str(pack_path),
        "pack_id": pack.get("pack_id"),
        "target": pack.get("target"),
        "started_at": datetime.now(UTC).isoformat(),
        "validation": validation,
        "briefing_load": None,
        "oracle_recall": None,
        "errors": [],
    }
    if validation.get("status") != "PASS":
        receipt["errors"].append("prep_pack_validation_failed")
    if not skip_briefing and not receipt["errors"]:
        try:
            receipt["briefing_load"] = _post_briefing(
                backend_url, pack.get("briefing_pack") or {}, timeout_s=timeout_s
            )
            if not receipt["briefing_load"].get("ok"):
                receipt["errors"].append("briefing_load_failed")
        except Exception as exc:  # noqa: BLE001 - receipt must preserve live server failure.
            receipt["briefing_load"] = {"ok": False, "error_type": type(exc).__name__, "error": str(exc)}
            receipt["errors"].append("briefing_load_failed")
    if not skip_recall and not receipt["errors"]:
        try:
            receipt["oracle_recall"] = verify_oracle_recall(
                pack, memory_url=memory_url, timeout_s=timeout_s
            )
            if not receipt["oracle_recall"].get("ok"):
                receipt["errors"].append("oracle_recall_failed")
        except Exception as exc:  # noqa: BLE001 - receipt must preserve memory daemon failure.
            receipt["oracle_recall"] = {"ok": False, "error_type": type(exc).__name__, "error": str(exc)}
            receipt["errors"].append("oracle_recall_failed")
    receipt["ended_at"] = datetime.now(UTC).isoformat()
    receipt["status"] = "PASS" if not receipt["errors"] else "FAIL"
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=ROOT)
    parser.add_argument("--pack", default="fixtures/prep_pack_drivewealth.json")
    parser.add_argument(
        "--backend-url",
        default=_http_url_or_default(os.getenv("LIVE_EVIDENCE_BACKEND_URL"), DEFAULT_BACKEND_URL),
    )
    parser.add_argument(
        "--memory-url",
        default=_http_url_or_default(os.getenv("MEMORY_SERVICE_URL"), DEFAULT_MEMORY_URL),
    )
    parser.add_argument("--timeout-s", type=float, default=30.0)
    parser.add_argument("--skip-briefing", action="store_true")
    parser.add_argument("--skip-recall", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    pack = Path(args.pack)
    if not pack.is_absolute():
        pack = root / pack
    receipt = load_prep_pack(
        pack,
        backend_url=args.backend_url,
        memory_url=args.memory_url,
        timeout_s=args.timeout_s,
        skip_briefing=args.skip_briefing,
        skip_recall=args.skip_recall,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    print(f"prep pack load: {receipt['status']}")
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
