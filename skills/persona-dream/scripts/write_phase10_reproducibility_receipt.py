#!/usr/bin/env python3
"""Write a deterministic Phase 10 reproducibility receipt from frozen artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PHASE10_ROOT = ROOT / "reports" / "pipeline-complete" / "phase_10_provider_contract"
DYNAMIC_FIELDS = {"generated_at", "created_at", "receipt_path", "runtime_seconds"}


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonicalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _canonicalize(item) for key, item in sorted(value.items()) if key not in DYNAMIC_FIELDS}
    if isinstance(value, list):
        return [_canonicalize(item) for item in value]
    return value


def _canonical_json_hash(path: Path) -> str:
    data = _canonicalize(_read_json(path))
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT.parents[1], text=True).strip()
    except Exception:  # noqa: BLE001 - receipt can still record None.
        return None


def write_phase10_reproducibility_receipt(phase10_root: Path, command: str) -> dict[str, Any]:
    phase10_root = phase10_root.resolve()
    manifest_path = phase10_root / "manifest.json"
    contract_receipt_path = phase10_root / "phase10_provider_contract_receipt.json"
    manifest = _read_json(manifest_path)
    contract_receipt = _read_json(contract_receipt_path)

    artifact_paths = sorted(path for path in phase10_root.glob("*.json") if path.name != "phase10_reproducibility_receipt.json")
    first_hashes = {path.name: _canonical_json_hash(path) for path in artifact_paths}
    second_hashes = {path.name: _canonical_json_hash(path) for path in artifact_paths}
    byte_hashes = {path.name: _file_hash(path) for path in artifact_paths}

    expected_from_manifest = {
        item["name"]: item["sha256"]
        for item in manifest.get("artifacts", [])
        if isinstance(item, dict) and item.get("name") and item.get("sha256")
    }
    expected_from_contract = {
        Path(name).name: digest
        for name, digest in (contract_receipt.get("artifact_hashes") or {}).items()
        if isinstance(name, str) and isinstance(digest, str)
    }

    mismatches: list[str] = []
    for name, expected in sorted(expected_from_manifest.items()):
        observed = byte_hashes.get(name)
        if observed != expected:
            mismatches.append(f"manifest_byte_hash:{name}:expected={expected}:observed={observed}")
    for name, expected in sorted(expected_from_contract.items()):
        observed = byte_hashes.get(name)
        if name == "phase10_provider_contract_receipt.json":
            continue
        if observed != expected:
            mismatches.append(f"contract_byte_hash:{name}:expected={expected}:observed={observed}")
    if first_hashes != second_hashes:
        mismatches.append("canonical_hashes_differ_between_passes")
    if contract_receipt.get("actual_provider_call_attempts") != 0:
        mismatches.append("provider_call_attempts_not_zero")
    if contract_receipt.get("submitted") is not False:
        mismatches.append("submitted_not_false")

    status = "PASS_PHASE10_REPRODUCIBLE" if not mismatches else "BLOCKED_PHASE10_NONDETERMINISTIC"
    return {
        "schema": "persona_dream.phase10_reproducibility_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "run_id": manifest.get("run_id") or "pipeline-complete",
        "phase10_root": str(phase10_root),
        "command": command,
        "implementation": {
            "git_commit": _git_commit(),
            "writer_path": str(Path(__file__).resolve()),
            "writer_sha256": _file_hash(Path(__file__).resolve()),
            "schema_version": "persona_dream.phase10_reproducibility_receipt.v1",
        },
        "input_hashes": contract_receipt.get("source_hashes", {}),
        "expected_manifest_hashes": expected_from_manifest,
        "expected_contract_hashes": expected_from_contract,
        "first_contract_canonical_hashes": first_hashes,
        "second_contract_canonical_hashes": second_hashes,
        "canonical_hashes_match": first_hashes == second_hashes,
        "observed_byte_hashes": byte_hashes,
        "excluded_dynamic_fields": sorted(DYNAMIC_FIELDS),
        "actual_provider_call_attempts": contract_receipt.get("actual_provider_call_attempts"),
        "submitted": contract_receipt.get("submitted"),
        "network_calls_observed": [],
        "mocked": contract_receipt.get("mocked", False),
        "live": False,
        "blockers": mismatches,
        "claims": {
            "proves": ["Phase 10 committed artifact set is canonically stable from frozen local inputs"] if not mismatches else [],
            "does_not_prove": [
                "live fal schema compatibility",
                "provider-accessible media publication",
                "paid authorization",
                "provider submit",
                "provider return",
            ],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase10-root", type=Path, default=DEFAULT_PHASE10_ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    command = "./run.sh write-phase10-reproducibility-receipt --phase10-root " + str(args.phase10_root)
    receipt = write_phase10_reproducibility_receipt(args.phase10_root, command)
    output = args.output or (args.phase10_root / "phase10_reproducibility_receipt.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
    return 0 if receipt["status"] == "PASS_PHASE10_REPRODUCIBLE" else 1


if __name__ == "__main__":
    raise SystemExit(main())

