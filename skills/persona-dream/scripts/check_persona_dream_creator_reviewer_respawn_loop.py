#!/usr/bin/env python3
"""Check creator/reviewer loop decisions against respawn and stale-write gates."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_CREATOR_REVIEWER_RESPAWN_LOOP"
BLOCKED_STATUS = "BLOCKED_CREATOR_REVIEWER_RESPAWN_LOOP"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def add_blocker(blockers: list[str], blocker: str) -> None:
    if blocker not in blockers:
        blockers.append(blocker)


def evaluate_fixture(fixture: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    if fixture.get("schema") != "persona_dream.creator_reviewer_respawn_loop_fixture.v1":
        add_blocker(blockers, "BLOCKED_CREATOR_REVIEWER_LOOP_SCHEMA")
    policy = fixture.get("policy") or {}
    if policy.get("provider_live") is not False:
        add_blocker(blockers, "BLOCKED_PROVIDER_LIVE_IN_CREATOR_REVIEWER_LOOP")
    if policy.get("paid_call_authorized") is not False:
        add_blocker(blockers, "BLOCKED_PAID_CALL_AUTHORIZED_IN_CREATOR_REVIEWER_LOOP")

    work_item = fixture.get("work_item") or {}
    respawn = fixture.get("respawn_decision") or {}
    stale_fence = fixture.get("stale_write_fence") or {}
    creator = fixture.get("creator_receipt") or {}
    validator = fixture.get("validator_receipt") or {}
    reviewer = fixture.get("reviewer_receipt") or {}

    if work_item.get("revision_id") != fixture.get("active_revision_id"):
        add_blocker(blockers, "BLOCKED_ACTIVE_REVISION_MISMATCH")
    decision = respawn.get("decision")
    if decision in {"REGENERATE_REQUIRED", "REVALIDATE_REQUIRED", "REVIEW_REQUIRED", "BLOCKED_HUMAN_DECISION_REQUIRED"}:
        if creator.get("input_revision_id") != fixture.get("active_revision_id"):
            add_blocker(blockers, "BLOCKED_CREATOR_USED_STALE_RESPAWN_INPUT")
        if decision == "BLOCKED_HUMAN_DECISION_REQUIRED":
            add_blocker(blockers, "BLOCKED_HUMAN_DECISION_REQUIRED")
    if decision == "REUSE_ALLOWED" and creator.get("provider_called") is True:
        add_blocker(blockers, "BLOCKED_REUSE_SCOPE_REGENERATED")
    if decision == "CURRENT" and creator.get("provider_called") is True and not work_item.get("force_regenerate"):
        add_blocker(blockers, "BLOCKED_CURRENT_SCOPE_REGENERATED")
    if creator.get("revision_id") != fixture.get("active_revision_id"):
        add_blocker(blockers, "BLOCKED_STALE_CREATOR_OUTPUT")
    if reviewer.get("revision_id") != fixture.get("active_revision_id"):
        add_blocker(blockers, "BLOCKED_STALE_REVIEWER_RECEIPT")
    if validator.get("status") != "PASS_PROMPT_CONTRACT":
        add_blocker(blockers, "BLOCKED_REVIEWER_PASS_WITHOUT_VALIDATOR_RECEIPT")
    if reviewer.get("accepted") is True and validator.get("artifact_sha256") != reviewer.get("reviewed_sha256"):
        add_blocker(blockers, "BLOCKED_REVIEWER_VALIDATED_SHA_MISMATCH")
    if stale_fence.get("status") != "PASS_STALE_WRITE_FENCE":
        add_blocker(blockers, "BLOCKED_STALE_WRITE_FENCE_NOT_PASS")
    if stale_fence.get("promotion_allowed") is not True:
        add_blocker(blockers, "BLOCKED_PROMOTION_NOT_ALLOWED_BY_STALE_WRITE_FENCE")
    if reviewer.get("accepted") is not True:
        add_blocker(blockers, "BLOCKED_REVIEWER_ACCEPTANCE_MISSING")

    result = "PROMOTION_ALLOWED" if not blockers else "PROMOTION_BLOCKED"
    if any(blocker in blockers for blocker in {"BLOCKED_STALE_CREATOR_OUTPUT", "BLOCKED_STALE_REVIEWER_RECEIPT"}):
        result = "OUTPUT_QUARANTINED"
    elif "BLOCKED_HUMAN_DECISION_REQUIRED" in blockers:
        result = "BLOCKED_HUMAN_DECISION_REQUIRED"
    elif "BLOCKED_REUSE_SCOPE_REGENERATED" in blockers:
        result = "REUSE_ALLOWED_NO_PROVIDER_CALL"
    return {
        "result": result,
        "blockers": blockers,
        "fixture_creator_provider_called": bool(creator.get("provider_called")),
        "promotion_allowed": result == "PROMOTION_ALLOWED",
    }


def run_one(fixture_path: Path, output_root: Path) -> dict[str, Any]:
    evaluation = evaluate_fixture(read_json(fixture_path))
    receipt = {
        "schema": "persona_dream.creator_reviewer_respawn_loop_receipt.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": PASS_STATUS if evaluation["promotion_allowed"] else BLOCKED_STATUS,
        "provider_live": False,
        "paid_call_authorized": False,
        "actual_provider_call_attempts": 0,
        "live_image_call_started": False,
        "live_kling_call_started": False,
        "fixture_path": str(fixture_path),
        **evaluation,
        "claims": {
            "proves": [
                "creator/reviewer promotion was checked against active revision, respawn decision, validator receipt, and stale-write fence state",
                "provider_live and paid_call_authorized remained false",
            ],
            "does_not_prove": [
                "image quality",
                "new image generation",
                "manual acceptance",
                "provider readiness",
                "live Kling generation",
            ],
        },
    }
    receipt_path = output_root / "creator_reviewer_respawn_loop_receipt.v1.json"
    write_json(receipt_path, receipt)
    return receipt


def expected_for_fixture(fixture_dir: Path) -> dict[str, Any]:
    path = fixture_dir / "expected.json"
    return read_json(path) if path.exists() else {}


def run_fixtures(fixtures_root: Path, receipt_out: Path) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    output_root = receipt_out.parent / "creator-reviewer-loop-fixture-results"
    for fixture_path in sorted(fixtures_root.glob("**/fixture.json")):
        fixture_dir = fixture_path.parent
        receipt = run_one(fixture_path, output_root / fixture_dir.relative_to(fixtures_root))
        expected = expected_for_fixture(fixture_dir)
        errors: list[str] = []
        if expected.get("result") and receipt["result"] != expected["result"]:
            errors.append(f"result_mismatch:{receipt['result']}:expected:{expected['result']}")
        for blocker in expected.get("blockers", []):
            if blocker not in receipt["blockers"]:
                errors.append(f"missing_blocker:{blocker}")
        results.append(
            {
                "fixture": str(fixture_dir.relative_to(fixtures_root)),
                "status": receipt["status"],
                "result": receipt["result"],
                "blockers": receipt["blockers"],
                "fixture_creator_provider_called": receipt["fixture_creator_provider_called"],
                "expected": expected,
                "errors": errors,
            }
        )
    errors = [f"{result['fixture']}:{error}" for result in results for error in result["errors"]]
    aggregate = {
        "schema": "persona_dream.creator_reviewer_respawn_loop_checker_receipt.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": PASS_STATUS if not errors else BLOCKED_STATUS,
        "provider_live": False,
        "paid_call_authorized": False,
        "actual_provider_call_attempts": 0,
        "live_image_call_started": False,
        "live_kling_call_started": False,
        "fixture_count": len(results),
        "observed_results": sorted({result["result"] for result in results}),
        "observed_blockers": sorted({blocker for result in results for blocker in result["blockers"]}),
        "fixture_creator_provider_called_true_count": sum(1 for result in results if result["fixture_creator_provider_called"]),
        "promotion_allowed_count": sum(1 for result in results if result["result"] == "PROMOTION_ALLOWED"),
        "promotion_blocked_count": sum(1 for result in results if result["result"] != "PROMOTION_ALLOWED"),
        "errors": errors,
        "results": results,
        "claims": {
            "proves": [
                "creator/reviewer respawn-loop fixtures were classified deterministically",
                "stale or out-of-scope creator/reviewer outputs did not promote",
            ],
            "does_not_prove": [
                "live image generation",
                "visual quality",
                "manual acceptance",
                "provider readiness",
                "live Kling generation",
            ],
        },
    }
    write_json(receipt_out, aggregate)
    return aggregate


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--fixture", type=Path)
    group.add_argument("--fixtures-root", type=Path)
    parser.add_argument("--receipt-out", required=True, type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.fixture:
        receipt = run_one(args.fixture.resolve(), args.receipt_out.resolve().parent)
        write_json(args.receipt_out, receipt)
    else:
        receipt = run_fixtures(args.fixtures_root.resolve(), args.receipt_out.resolve())
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
