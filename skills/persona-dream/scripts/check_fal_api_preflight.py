#!/usr/bin/env python3
"""Check FAL auth and non-generation API/docs access without submitting jobs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_FAL_API_PREFLIGHT"
BLOCKED_STATUS = "BLOCKED_FAL_API_PREFLIGHT"
SCHEMA = "persona_dream.fal_api_preflight_receipt.v1"

DOC_URLS = {
    "kling": [
        "https://fal.ai/docs/model-api-reference/video-generation-api/kling-video-v3-standard",
        "https://fal.ai/models/fal-ai/kling-video/v3/pro/image-to-video/api",
    ],
    "bytedance-seedance": [
        "https://fal.ai/models/bytedance/seedance-2.0/text-to-video",
        "https://fal.ai/models/bytedance/seedance-2.0/image-to-video",
    ],
}


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def add_blocker(blockers: list[str], blocker: str) -> None:
    if blocker not in blockers:
        blockers.append(blocker)


def parse_zshrc_key(path: Path) -> str | None:
    if not path.exists():
        return None
    pattern = re.compile(r"^\s*(?:export\s+)?(?:FAL_API_KEY|FAL_KEY)\s*=\s*['\"]?([^'\"\n#]+)")
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = pattern.match(line)
        if match:
            value = match.group(1).strip()
            return value or None
    return None


def discover_key(zshrc_path: Path) -> tuple[str | None, str]:
    for name in ("FAL_API_KEY", "FAL_KEY"):
        value = os.environ.get(name)
        if value:
            return value, f"env:{name}"
    value = parse_zshrc_key(zshrc_path)
    if value:
        return value, f"zshrc:{zshrc_path}"
    return None, "missing"


def key_fingerprint(key: str | None) -> str | None:
    if not key:
        return None
    return "sha256:" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def get_json(url: str, headers: dict[str, str], timeout_s: int) -> tuple[int | None, dict[str, Any] | None, str | None]:
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            body = response.read(1024 * 1024).decode("utf-8", "replace")
            return response.status, json.loads(body), None
    except urllib.error.HTTPError as exc:
        return exc.code, None, str(exc)
    except Exception as exc:  # noqa: BLE001 - receipt needs failure text
        return None, None, str(exc)


def get_status(url: str, timeout_s: int) -> tuple[int | None, str | None]:
    request = urllib.request.Request(url, headers={"User-Agent": "persona-dream-fal-preflight/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            response.read(1)
            return response.status, None
    except urllib.error.HTTPError as exc:
        return exc.code, str(exc)
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


def check_fal_api_preflight(
    receipt_out: Path,
    zshrc_path: Path,
    live: bool,
    timeout_s: int,
) -> dict[str, Any]:
    blockers: list[str] = []
    key, key_source = discover_key(zshrc_path)
    if not key:
        add_blocker(blockers, "BLOCKED_FAL_API_KEY_MISSING")

    model_probe: dict[str, Any] = {
        "enabled": live,
        "url": "https://api.fal.ai/v1/models?limit=10",
        "http_status": None,
        "model_count": 0,
        "error": None,
    }
    if live and key:
        status, payload, error = get_json(
            model_probe["url"],
            {"Authorization": f"Key {key}", "User-Agent": "persona-dream-fal-preflight/1.0"},
            timeout_s,
        )
        models = payload.get("models") if isinstance(payload, dict) else []
        model_probe.update(
            {
                "http_status": status,
                "model_count": len(models) if isinstance(models, list) else 0,
                "error": error,
            }
        )
        if status != 200 or model_probe["model_count"] <= 0:
            add_blocker(blockers, "BLOCKED_FAL_MODEL_LIST_API_FAILED")
    elif not live:
        model_probe["error"] = "LIVE_PROBE_DISABLED"

    doc_probes: list[dict[str, Any]] = []
    for provider_id, urls in DOC_URLS.items():
        for url in urls:
            status, error = get_status(url, timeout_s) if live else (None, "LIVE_PROBE_DISABLED")
            doc_probes.append({"provider_id": provider_id, "url": url, "http_status": status, "error": error})
            if live and status not in {200, 301, 302}:
                add_blocker(blockers, f"BLOCKED_FAL_DOC_URL_UNREACHABLE:{provider_id}")

    receipt = {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": PASS_STATUS if not blockers else BLOCKED_STATUS,
        "mode": "LIVE_NON_GENERATION_PROBE" if live else "AUTH_DISCOVERY_ONLY",
        "fal_api_key_present": bool(key),
        "fal_api_key_source": key_source,
        "fal_api_key_fingerprint": key_fingerprint(key),
        "model_list_probe": model_probe,
        "doc_probes": doc_probes,
        "blockers": blockers,
        "actual_provider_call_attempts": 0,
        "generation_call_started": False,
        "queue_submit_started": False,
        "provider_live": False,
        "paid_call_authorized": False,
        "provider_accessible_url_created": False,
        "submitted": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "mocked": False,
        "claims": {
            "proves": [
                "FAL API key discovery was checked without printing the secret",
                "non-generation FAL model-list and docs probes were attempted when live mode was enabled",
                "no provider generation, queue submit, paid, URL, submit, or live-ready state was claimed",
            ],
            "does_not_prove": [
                "generation endpoint schema compatibility",
                "provider-accessible media URLs",
                "paid-call authorization",
                "manual acceptance",
                "live provider readiness",
                "live video generation",
            ],
        },
    }
    write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt-out", required=True, type=Path)
    parser.add_argument("--zshrc-path", type=Path, default=Path.home() / ".zshrc")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--timeout-s", type=int, default=15)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt = check_fal_api_preflight(args.receipt_out.resolve(), args.zshrc_path.expanduser().resolve(), args.live, args.timeout_s)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
