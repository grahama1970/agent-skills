#!/usr/bin/env python3
"""Validate a provider-media local staging receipt."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json: {path}: {exc}") from exc


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _block(result: dict[str, Any], reason: str) -> dict[str, Any]:
    result["status"] = "BLOCKED"
    result["first_blocker"] = {"phase": "provider_media_local_staging", "reason": reason}
    return result


def validate_provider_media_local_staging(path: Path) -> dict[str, Any]:
    path = path.resolve()
    receipt = _read_json(path)
    if not isinstance(receipt, dict):
        raise ValueError("receipt must be a JSON object")

    result: dict[str, Any] = {
        "schema": "persona_dream.provider_media_local_staging_validation.v1",
        "status": "PASS_PROVIDER_MEDIA_LOCAL_STAGING",
        "receipt": str(path),
        "first_blocker": None,
        "mocked": "yes" if "fixtures" in path.parts else "no",
        "live": "no",
        "exercised": "local staging receipt schema, staged asset existence, sha256 comparison, explicit non-authorization policy",
        "unverified": "public URL fetch, GitHub raw availability, Kling provider fetch behavior, paid-call authorization, Kling submission",
    }

    if receipt.get("schema") != "persona_dream.provider_media_local_staging_receipt.v1":
        return _block(result, f"wrong_schema:{receipt.get('schema')}")
    if receipt.get("status") != "PASS_PROVIDER_MEDIA_LOCAL_STAGING":
        return _block(result, f"wrong_status:{receipt.get('status')}")

    staged_path_value = receipt.get("staged_asset_path")
    expected_sha256 = receipt.get("staged_sha256")
    if not isinstance(staged_path_value, str) or not staged_path_value:
        return _block(result, "missing_staged_asset_path")
    if not isinstance(expected_sha256, str) or not expected_sha256.startswith("sha256:"):
        return _block(result, "missing_staged_sha256")
    staged_path = Path(staged_path_value)
    if not staged_path.exists():
        return _block(result, f"missing_staged_asset:{staged_path}")
    observed_sha256 = _sha256_file(staged_path)
    if observed_sha256 != expected_sha256:
        return _block(result, f"staged_sha256_mismatch:expected={expected_sha256}:observed={observed_sha256}")

    does_not_authorize = set(receipt.get("does_not_authorize", []))
    for required in ("git_push", "public_upload", "provider_readiness", "direct_kling_submit", "paid_provider_call"):
        if required not in does_not_authorize:
            return _block(result, f"missing_non_authorization:{required}")

    probe_command = receipt.get("next_required_probe_command")
    if not isinstance(probe_command, str) or "validate-provider-media-url" not in probe_command:
        return _block(result, "missing_next_required_probe_command")

    result["staged_asset_path"] = str(staged_path)
    result["staged_sha256"] = expected_sha256
    result["proposed_url"] = receipt.get("proposed_url")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = validate_provider_media_local_staging(args.receipt)
    except Exception as exc:
        result = {
            "schema": "persona_dream.provider_media_local_staging_validation.v1",
            "status": "BLOCKED",
            "first_blocker": {"phase": "schema_or_parse", "reason": str(exc)},
            "live": "no",
        }

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        blocker = result.get("first_blocker")
        if blocker:
            print(f"{result['status']} {blocker['reason']}")
        else:
            print(result["status"])
    return 0 if result["status"] != "BLOCKED" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
