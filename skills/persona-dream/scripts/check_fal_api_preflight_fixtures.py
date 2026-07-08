#!/usr/bin/env python3
"""Check FAL API preflight fixtures without live provider calls."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from check_fal_api_preflight import check_fal_api_preflight, write_json


PASS_STATUS = "PASS_FAL_API_PREFLIGHT_FIXTURES"
BLOCKED_STATUS = "BLOCKED_FAL_API_PREFLIGHT_FIXTURES"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_fixture(fixture_path: Path, fixtures_root: Path, output_root: Path) -> dict[str, Any]:
    fixture = read_json(fixture_path)
    fixture_name = str(fixture_path.parent.relative_to(fixtures_root))
    out_dir = output_root / "fal-api-preflight-fixture-results" / fixture_name
    zshrc_path = out_dir / ".zshrc"
    receipt_path = out_dir / "fal_api_preflight_receipt.json"
    zshrc_path.parent.mkdir(parents=True, exist_ok=True)
    zshrc_path.write_text(str(fixture.get("zshrc_text", "")), encoding="utf-8")
    saved_env = {name: os.environ.pop(name, None) for name in ("FAL_API_KEY", "FAL_KEY")}
    try:
        receipt = check_fal_api_preflight(receipt_path, zshrc_path, live=False, timeout_s=1)
    finally:
        for name, value in saved_env.items():
            if value is not None:
                os.environ[name] = value
    expected = fixture.get("expected") if isinstance(fixture.get("expected"), dict) else {}
    errors: list[str] = []
    if expected.get("status") and receipt["status"] != expected["status"]:
        errors.append(f"status_mismatch:{receipt['status']}:expected:{expected['status']}")
    if "fal_api_key_present" in expected and receipt["fal_api_key_present"] != expected["fal_api_key_present"]:
        errors.append("fal_api_key_present_mismatch")
    for blocker in expected.get("blockers") or []:
        if blocker not in receipt["blockers"]:
            errors.append(f"missing_blocker:{blocker}")
    return {
        "fixture": fixture_name,
        "status": receipt["status"],
        "fal_api_key_present": receipt["fal_api_key_present"],
        "fal_api_key_source": receipt["fal_api_key_source"],
        "blockers": receipt["blockers"],
        "receipt_path": str(receipt_path),
        "errors": errors,
    }


def run_fixtures(fixtures_root: Path, receipt_out: Path) -> dict[str, Any]:
    results = [run_fixture(path, fixtures_root, receipt_out.parent) for path in sorted(fixtures_root.glob("*/fixture.json"))]
    errors = [f"{result['fixture']}:{error}" for result in results for error in result["errors"]]
    observed_blockers = sorted({blocker for result in results for blocker in result["blockers"]})
    if len(results) != 2:
        errors.append(f"fixture_count_mismatch:{len(results)}:expected:2")
    if "BLOCKED_FAL_API_KEY_MISSING" not in observed_blockers:
        errors.append("missing_expected_observed_blocker:BLOCKED_FAL_API_KEY_MISSING")
    receipt = {
        "schema": "persona_dream.fal_api_preflight_fixture_checker_receipt.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": PASS_STATUS if not errors else BLOCKED_STATUS,
        "fixture_count": len(results),
        "observed_blockers": observed_blockers,
        "errors": errors,
        "results": results,
        "actual_provider_call_attempts": 0,
        "generation_call_started": False,
        "queue_submit_started": False,
        "provider_live": False,
        "paid_call_authorized": False,
        "submitted": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "mocked": False,
        "claims": {
            "proves": [
                "FAL auth discovery fixtures checked environment-file parsing without live provider calls",
                "missing FAL key produced deterministic blockers",
                "no provider generation, queue submit, paid, URL, submit, or live-ready state was claimed",
            ],
            "does_not_prove": [
                "live FAL authentication",
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
    parser.add_argument("--fixtures-root", required=True, type=Path)
    parser.add_argument("--receipt-out", required=True, type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt = run_fixtures(args.fixtures_root.resolve(), args.receipt_out.resolve())
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
