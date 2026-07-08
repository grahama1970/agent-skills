#!/usr/bin/env python3
"""Check video-provider registry refresh fixtures."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from refresh_video_provider_registry import refresh_provider_registry, write_json


PASS_STATUS = "PASS_VIDEO_PROVIDER_REGISTRY_REFRESH"
BLOCKED_STATUS = "BLOCKED_VIDEO_PROVIDER_REGISTRY_REFRESH"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_fixture(fixture_path: Path, fixtures_root: Path, output_root: Path) -> dict[str, Any]:
    fixture = read_json(fixture_path)
    fixture_name = str(fixture_path.parent.relative_to(fixtures_root))
    out_dir = output_root / "video-provider-refresh-fixture-results" / fixture_name
    receipt_path = out_dir / "provider_registry_refresh_receipt.v1.json"
    fixture_results_dir = fixture_path.parent / "brave_results"
    receipt = refresh_provider_registry(
        receipt_path,
        fixture_results_dir if fixture_results_dir.exists() else None,
        live_brave_search=False,
        count=8,
    )
    expected = fixture.get("expected") if isinstance(fixture.get("expected"), dict) else {}
    errors: list[str] = []
    if expected.get("status") and receipt["status"] != expected["status"]:
        errors.append(f"status_mismatch:{receipt['status']}:expected:{expected['status']}")
    for provider_id in expected.get("discovered_provider_ids") or []:
        if provider_id not in receipt["discovered_provider_ids"]:
            errors.append(f"missing_discovered_provider:{provider_id}")
    for provider_id in expected.get("fal_hosted_provider_ids") or []:
        if provider_id not in receipt["fal_hosted_provider_ids"]:
            errors.append(f"missing_fal_hosted_provider:{provider_id}")
    for provider_id in expected.get("fal_api_doc_provider_ids") or []:
        if provider_id not in receipt["fal_api_doc_provider_ids"]:
            errors.append(f"missing_fal_api_doc_provider:{provider_id}")
    for blocker in expected.get("blockers") or []:
        if blocker not in receipt["blockers"]:
            errors.append(f"missing_blocker:{blocker}")
    return {
        "fixture": fixture_name,
        "status": receipt["status"],
        "discovered_provider_ids": receipt["discovered_provider_ids"],
        "fal_hosted_provider_ids": receipt["fal_hosted_provider_ids"],
        "fal_api_doc_provider_ids": receipt["fal_api_doc_provider_ids"],
        "blockers": receipt["blockers"],
        "receipt_path": str(receipt_path),
        "errors": errors,
    }


def run_fixtures(fixtures_root: Path, receipt_out: Path) -> dict[str, Any]:
    results = [
        run_fixture(path, fixtures_root, receipt_out.parent)
        for path in sorted(fixtures_root.glob("*/fixture.json"))
    ]
    errors = [f"{result['fixture']}:{error}" for result in results for error in result["errors"]]
    observed_blockers = sorted({blocker for result in results for blocker in result["blockers"]})
    observed_providers = sorted({provider for result in results for provider in result["discovered_provider_ids"]})
    observed_fal_hosted = sorted({provider for result in results for provider in result["fal_hosted_provider_ids"]})
    observed_fal_api_docs = sorted({provider for result in results for provider in result["fal_api_doc_provider_ids"]})
    expected_blockers = {
        "BLOCKED_FAL_MODEL_CATALOG_NOT_FOUND",
        "BLOCKED_REQUIRED_PROVIDER_NOT_DISCOVERED:bytedance-seedance",
        "BLOCKED_FAL_API_DOCS_NOT_OBSERVED:kling",
        "BLOCKED_FAL_API_DOCS_NOT_OBSERVED:bytedance-seedance",
    }
    if len(results) != 3:
        errors.append(f"fixture_count_mismatch:{len(results)}:expected:3")
    for blocker in sorted(expected_blockers - set(observed_blockers)):
        errors.append(f"missing_expected_observed_blocker:{blocker}")
    receipt = {
        "schema": "persona_dream.video_provider_registry_refresh_checker_receipt.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": PASS_STATUS if not errors else BLOCKED_STATUS,
        "fixture_count": len(results),
        "observed_provider_ids": observed_providers,
        "observed_fal_hosted_provider_ids": observed_fal_hosted,
        "observed_fal_api_doc_provider_ids": observed_fal_api_docs,
        "observed_blockers": observed_blockers,
        "errors": errors,
        "results": results,
        "actual_provider_call_attempts": 0,
        "provider_live": False,
        "paid_call_authorized": False,
        "provider_accessible_url_created": False,
        "submitted": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "mocked": False,
        "claims": {
            "proves": [
                "provider refresh fixtures were parsed into fal-hosted provider and fal API/docs evidence",
                "missing fal catalog/docs evidence produced deterministic blockers",
                "no provider, paid, URL, submit, or live-ready state was claimed",
            ],
            "does_not_prove": [
                "current provider schema compatibility",
                "provider-accessible URLs",
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
