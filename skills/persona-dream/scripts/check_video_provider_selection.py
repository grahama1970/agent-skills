#!/usr/bin/env python3
"""Check Persona Dream video provider selection fixtures."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from select_video_provider import read_json, select_provider, write_json


PASS_STATUS = "PASS_VIDEO_PROVIDER_SELECTION"
BLOCKED_STATUS = "BLOCKED_VIDEO_PROVIDER_SELECTION"


def run_fixture(fixture_path: Path, fixtures_root: Path, output_root: Path, default_registry: Path) -> dict[str, Any]:
    fixture = read_json(fixture_path)
    fixture_name = str(fixture_path.parent.relative_to(fixtures_root))
    out_dir = output_root / "video-provider-selection-fixture-results" / fixture_name
    scene_path = out_dir / "video_scene_contract.v1.json"
    registry_path = out_dir / "video_provider_registry.v1.json"
    output = out_dir / "video_provider_scorecard.v1.json"
    write_json(scene_path, fixture.get("scene_contract") or {})
    if isinstance(fixture.get("registry"), dict):
        write_json(registry_path, fixture["registry"])
    else:
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_path.write_text(default_registry.read_text(encoding="utf-8"), encoding="utf-8")
    scorecard = select_provider(read_json(scene_path), read_json(registry_path), scene_path, registry_path, output)
    expected = fixture.get("expected") if isinstance(fixture.get("expected"), dict) else {}
    errors: list[str] = []
    if expected.get("recommended_provider_id") and scorecard["recommended_provider_id"] != expected["recommended_provider_id"]:
        errors.append(f"provider_mismatch:{scorecard['recommended_provider_id']}:expected:{expected['recommended_provider_id']}")
    if expected.get("selection_status") and scorecard["selection_status"] != expected["selection_status"]:
        errors.append(f"selection_status_mismatch:{scorecard['selection_status']}:expected:{expected['selection_status']}")
    observed_provider_blockers = sorted({blocker for provider in scorecard["providers"] for blocker in provider.get("blockers", [])})
    observed_blockers = sorted(set(scorecard.get("blockers") or []) | set(observed_provider_blockers))
    for blocker in expected.get("blockers") or []:
        if blocker not in observed_blockers:
            errors.append(f"missing_blocker:{blocker}")
    return {
        "fixture": fixture_name,
        "recommended_provider_id": scorecard["recommended_provider_id"],
        "selection_status": scorecard["selection_status"],
        "observed_blockers": observed_blockers,
        "scorecard_path": str(output),
        "errors": errors,
    }


def run_fixtures(fixtures_root: Path, receipt_out: Path) -> dict[str, Any]:
    default_registry = Path(__file__).resolve().parents[1] / "provider_registry" / "video_provider_registry.v1.json"
    results = [run_fixture(path, fixtures_root, receipt_out.parent, default_registry) for path in sorted(fixtures_root.glob("*/fixture.json"))]
    errors = [f"{result['fixture']}:{error}" for result in results for error in result["errors"]]
    observed_blockers = sorted({blocker for result in results for blocker in result["observed_blockers"]})
    observed_selection_statuses = sorted({result["selection_status"] for result in results})
    observed_recommended_providers = sorted({result["recommended_provider_id"] for result in results})
    expected_blockers = {
        "BLOCKED_PROVIDER_LIVE_NOT_ENABLED",
        "BLOCKED_PAID_CALL_AUTHORIZATION_MISSING",
        "BLOCKED_MANUAL_ACCEPTANCE_MISSING",
        "BLOCKED_PROVIDER_REGISTRY_STALE",
        "BLOCKED_PROVIDER_CAPABILITY_MISSING",
        "BLOCKED_HEIGHTENED_COPYRIGHT_REVIEW_REQUIRED",
    }
    if len(results) != 8:
        errors.append(f"fixture_count_mismatch:{len(results)}:expected:8")
    for blocker in sorted(expected_blockers - set(observed_blockers)):
        errors.append(f"missing_expected_observed_blocker:{blocker}")
    receipt = {
        "schema": "persona_dream.video_provider_selection_checker_receipt.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": PASS_STATUS if not errors else BLOCKED_STATUS,
        "fixture_count": len(results),
        "observed_selection_statuses": observed_selection_statuses,
        "observed_recommended_providers": observed_recommended_providers,
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
                "provider selection fixtures were scored deterministically from scene contracts and a versioned registry",
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
