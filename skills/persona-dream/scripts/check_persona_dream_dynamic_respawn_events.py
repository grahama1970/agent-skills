#!/usr/bin/env python3
"""Classify dynamic Persona Dream change events into respawn actions."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_DYNAMIC_RESPAWN_EVENTS"
BLOCKED_STATUS = "BLOCKED_DYNAMIC_RESPAWN_EVENTS"

CHANGE_RULES: dict[str, dict[str, str]] = {
    "IDEA_CHANGED": {
        "phase02_story_contract": "REGENERATE_REQUIRED",
        "phase06_script_contract": "REGENERATE_REQUIRED",
        "phase07_storyboard_packet": "REGENERATE_REQUIRED",
        "phase08_kling_scene_packet": "REGENERATE_REQUIRED",
    },
    "MEMORY_SET_CHANGED": {
        "phase02_story_contract": "REGENERATE_REQUIRED",
        "phase06_script_contract": "REGENERATE_REQUIRED",
        "phase07_storyboard_packet": "REGENERATE_REQUIRED",
        "phase08_kling_scene_packet": "REGENERATE_REQUIRED",
    },
    "STORY_CHANGED": {
        "phase06_script_contract": "REGENERATE_REQUIRED",
        "phase07_storyboard_packet": "REGENERATE_REQUIRED",
        "phase08_kling_scene_packet": "REGENERATE_REQUIRED",
    },
    "SCRIPT_CHANGED": {
        "phase07_storyboard_packet": "REGENERATE_REQUIRED",
        "phase08_kling_scene_packet": "REGENERATE_REQUIRED",
    },
    "REFERENCE_CHANGED": {
        "phase07_storyboard_packet": "REVALIDATE_REQUIRED",
        "phase08_kling_scene_packet": "REGENERATE_REQUIRED",
    },
    "STORYBOARD_CHANGED": {
        "phase08_kling_scene_packet": "REGENERATE_REQUIRED",
    },
    "KLING_SETTINGS_CHANGED": {
        "phase08_kling_scene_packet": "REGENERATE_REQUIRED",
    },
}

REASON_BY_CHANGE = {
    "IDEA_CHANGED": "UPSTREAM_IDEA_CHANGED",
    "MEMORY_SET_CHANGED": "UPSTREAM_MEMORY_RESIDUE_CHANGED",
    "STORY_CHANGED": "UPSTREAM_STORY_CHANGED",
    "SCRIPT_CHANGED": "UPSTREAM_SCRIPT_CHANGED",
    "REFERENCE_CHANGED": "REFERENCE_HASH_CHANGED",
    "STORYBOARD_CHANGED": "STORYBOARD_HASH_CHANGED",
    "KLING_SETTINGS_CHANGED": "KLING_DISTILLATION_SETTINGS_CHANGED",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def add_blocker(blockers: list[str], blocker: str) -> None:
    if blocker not in blockers:
        blockers.append(blocker)


def classify_event(event: dict[str, Any], blockers: list[str]) -> list[dict[str, Any]]:
    change_type = str(event.get("change_type") or "")
    if change_type not in CHANGE_RULES:
        add_blocker(blockers, "BLOCKED_UNKNOWN_CHANGE_TYPE")
        return []
    if event.get("provider_live") is True:
        add_blocker(blockers, "BLOCKED_PROVIDER_LIVE_IN_RESPAWN_EVENT")
    if event.get("paid_call_authorized") is True:
        add_blocker(blockers, "BLOCKED_PAID_CALL_AUTHORIZED_IN_RESPAWN_EVENT")
    if event.get("human_decision_required") is True:
        return [
            {
                "artifact_id": artifact_id,
                "decision": "BLOCKED_HUMAN_DECISION_REQUIRED",
                "reason_code": "BLOCKED_MANUAL_DECISION_REQUIRED",
                "change_type": change_type,
            }
            for artifact_id in CHANGE_RULES[change_type]
        ]
    reason = REASON_BY_CHANGE[change_type]
    decisions: list[dict[str, Any]] = []
    for artifact_id, decision in CHANGE_RULES[change_type].items():
        decisions.append(
            {
                "artifact_id": artifact_id,
                "decision": decision,
                "reason_code": reason,
                "change_type": change_type,
            }
        )
    return decisions


def build_plan(source: dict[str, Any], source_path: Path) -> dict[str, Any]:
    blockers: list[str] = []
    if source.get("schema") != "persona_dream.dynamic_change_events.v1":
        add_blocker(blockers, "BLOCKED_DYNAMIC_RESPAWN_EVENT_SCHEMA")
    if source.get("provider_live") is not False:
        add_blocker(blockers, "BLOCKED_PROVIDER_LIVE_IN_RESPAWN_EVENT")
    if source.get("paid_call_authorized") is not False:
        add_blocker(blockers, "BLOCKED_PAID_CALL_AUTHORIZED_IN_RESPAWN_EVENT")
    decisions: list[dict[str, Any]] = []
    for event in source.get("events") or []:
        if not isinstance(event, dict):
            add_blocker(blockers, "BLOCKED_DYNAMIC_RESPAWN_EVENT_SCHEMA")
            continue
        decisions.extend(classify_event(event, blockers))
    if not decisions:
        add_blocker(blockers, "BLOCKED_CHANGE_EVENT_MISSING")
    return {
        "schema": "persona_dream.dynamic_respawn_event_plan.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_path": str(source_path),
        "status": PASS_STATUS if not blockers else BLOCKED_STATUS,
        "provider_live": False,
        "paid_call_authorized": False,
        "actual_provider_call_attempts": 0,
        "live_image_call_started": False,
        "live_kling_call_started": False,
        "decisions": decisions,
        "observed_decisions": sorted({decision["decision"] for decision in decisions}),
        "observed_reason_codes": sorted({decision["reason_code"] for decision in decisions}),
        "blockers": blockers,
        "claims": {
            "proves": [
                "dynamic change events were mapped to deterministic respawn actions",
                "provider_live and paid_call_authorized remained false",
            ],
            "does_not_prove": [
                "artifacts were regenerated",
                "manual acceptance",
                "provider readiness",
                "live Kling generation",
            ],
        },
    }


def run_one(source_path: Path, output_root: Path) -> dict[str, Any]:
    plan = build_plan(read_json(source_path), source_path)
    plan_path = output_root / "dynamic_respawn_event_plan.v1.json"
    write_json(plan_path, plan)
    receipt = {
        "schema": "persona_dream.dynamic_respawn_events_receipt.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": plan["status"],
        "provider_live": False,
        "paid_call_authorized": False,
        "actual_provider_call_attempts": 0,
        "live_image_call_started": False,
        "live_kling_call_started": False,
        "event_plan_path": str(plan_path),
        "decision_count": len(plan["decisions"]),
        "observed_decisions": plan["observed_decisions"],
        "observed_reason_codes": plan["observed_reason_codes"],
        "observed_blockers": sorted(plan["blockers"]),
        "claims": plan["claims"],
    }
    receipt_path = output_root / "dynamic_respawn_events_receipt.v1.json"
    write_json(receipt_path, receipt)
    return receipt


def expected_for_fixture(fixture_dir: Path) -> dict[str, Any]:
    path = fixture_dir / "expected.json"
    return read_json(path) if path.exists() else {}


def run_fixtures(fixtures_root: Path, receipt_out: Path) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    output_root = receipt_out.parent / "dynamic-respawn-fixture-results"
    for source_path in sorted(fixtures_root.glob("**/dynamic_change_events.v1.json")):
        fixture_dir = source_path.parent
        receipt = run_one(source_path, output_root / fixture_dir.relative_to(fixtures_root))
        expected = expected_for_fixture(fixture_dir)
        errors: list[str] = []
        if expected.get("status") and receipt["status"] != expected["status"]:
            errors.append(f"status_mismatch:{receipt['status']}:expected:{expected['status']}")
        for decision in expected.get("decisions", []):
            if decision not in receipt["observed_decisions"]:
                errors.append(f"missing_decision:{decision}")
        for reason in expected.get("reason_codes", []):
            if reason not in receipt["observed_reason_codes"]:
                errors.append(f"missing_reason_code:{reason}")
        for blocker in expected.get("blockers", []):
            if blocker not in receipt["observed_blockers"]:
                errors.append(f"missing_blocker:{blocker}")
        results.append(
            {
                "fixture": str(fixture_dir.relative_to(fixtures_root)),
                "status": receipt["status"],
                "decision_count": receipt["decision_count"],
                "observed_decisions": receipt["observed_decisions"],
                "observed_reason_codes": receipt["observed_reason_codes"],
                "observed_blockers": receipt["observed_blockers"],
                "expected": expected,
                "errors": errors,
            }
        )
    errors = [f"{result['fixture']}:{error}" for result in results for error in result["errors"]]
    aggregate = {
        "schema": "persona_dream.dynamic_respawn_events_checker_receipt.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": PASS_STATUS if not errors else BLOCKED_STATUS,
        "provider_live": False,
        "paid_call_authorized": False,
        "actual_provider_call_attempts": 0,
        "live_image_call_started": False,
        "live_kling_call_started": False,
        "fixture_count": len(results),
        "observed_decisions": sorted({decision for result in results for decision in result["observed_decisions"]}),
        "observed_reason_codes": sorted({reason for result in results for reason in result["observed_reason_codes"]}),
        "observed_blockers": sorted({blocker for result in results for blocker in result["observed_blockers"]}),
        "errors": errors,
        "results": results,
        "claims": {
            "proves": [
                "dynamic respawn event fixtures produced deterministic decisions",
                "provider_live and paid_call_authorized remained false",
            ],
            "does_not_prove": [
                "artifact regeneration",
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
    group.add_argument("--events", type=Path)
    group.add_argument("--fixtures-root", type=Path)
    parser.add_argument("--receipt-out", required=True, type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.events:
        receipt = run_one(args.events.resolve(), args.receipt_out.resolve().parent)
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
