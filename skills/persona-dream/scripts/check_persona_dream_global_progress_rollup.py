#!/usr/bin/env python3
"""Derive Persona Dream local evidence progress from receipt facts.

The rollup is intentionally not an owner of pipeline truth. It summarizes local
revision evidence only and fails closed if it tries to imply provider readiness,
manual acceptance, paid-call approval, or live submission.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_GLOBAL_PROGRESS_ROLLUP"
BLOCKED_STATUS = "BLOCKED_GLOBAL_PROGRESS_ROLLUP"
EXPECTED_UNIT_COUNT = 20
FORBIDDEN_TRUE_FLAGS = {
    "provider_ready": "BLOCKED_PROVIDER_READY_CLAIM_IN_PROGRESS_ROLLUP",
    "live_submit_ready": "BLOCKED_LIVE_SUBMIT_CLAIM_IN_PROGRESS_ROLLUP",
    "manual_acceptance_claimed": "BLOCKED_MANUAL_ACCEPTANCE_CLAIM_IN_PROGRESS_ROLLUP",
    "paid_call_authorized": "BLOCKED_PAID_CALL_AUTHORIZED_IN_PROGRESS_ROLLUP",
    "submitted": "BLOCKED_SUBMITTED_CLAIM_IN_PROGRESS_ROLLUP",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def add_blocker(blockers: list[str], blocker: str) -> None:
    if blocker not in blockers:
        blockers.append(blocker)


def normalize_unit(unit: dict[str, Any], blockers: list[str]) -> dict[str, Any]:
    unit_id = str(unit.get("unit_id") or "")
    status = str(unit.get("status") or "")
    receipt_path = unit.get("receipt_path")
    receipt_sha = unit.get("receipt_sha256")
    evidence_state = str(unit.get("evidence_state") or "")
    if not unit_id:
        add_blocker(blockers, "BLOCKED_PROGRESS_UNIT_ID_MISSING")
    if status not in {"PASS", "PASS_WITH_LIVE_BLOCKERS", "BLOCKED", "PENDING", "STALE", "NOT_STARTED"}:
        add_blocker(blockers, "BLOCKED_PROGRESS_UNIT_STATUS_INVALID")
    if status in {"PASS", "PASS_WITH_LIVE_BLOCKERS"}:
        if not receipt_path:
            add_blocker(blockers, "BLOCKED_PROGRESS_UNIT_RECEIPT_MISSING")
        if not isinstance(receipt_sha, str) or not receipt_sha.startswith("sha256:"):
            add_blocker(blockers, "BLOCKED_PROGRESS_UNIT_HASH_MISSING")
    if evidence_state == "STALE":
        add_blocker(blockers, "BLOCKED_PROGRESS_UNIT_STALE")
    return {
        "unit_id": unit_id,
        "phase": unit.get("phase"),
        "label": unit.get("label"),
        "status": status,
        "evidence_state": evidence_state or "CURRENT",
        "receipt_path": receipt_path,
        "receipt_sha256": receipt_sha,
        "live_blockers": unit.get("live_blockers") or [],
    }


def build_rollup(source: dict[str, Any], source_path: Path) -> dict[str, Any]:
    blockers: list[str] = []
    if source.get("schema") != "persona_dream.global_progress_sources.v1":
        add_blocker(blockers, "BLOCKED_GLOBAL_PROGRESS_SOURCE_SCHEMA")
    for flag, blocker in FORBIDDEN_TRUE_FLAGS.items():
        if source.get(flag) is True:
            add_blocker(blockers, blocker)
    units = [normalize_unit(unit, blockers) for unit in source.get("units") or [] if isinstance(unit, dict)]
    unit_ids = [unit["unit_id"] for unit in units]
    if len(units) != EXPECTED_UNIT_COUNT:
        add_blocker(blockers, "BLOCKED_GLOBAL_PROGRESS_UNIT_COUNT")
    if len(unit_ids) != len(set(unit_ids)):
        add_blocker(blockers, "BLOCKED_PROGRESS_UNIT_ID_DUPLICATE")

    pass_count = sum(1 for unit in units if unit["status"] in {"PASS", "PASS_WITH_LIVE_BLOCKERS"})
    blocked_count = sum(1 for unit in units if unit["status"] == "BLOCKED")
    stale_count = sum(1 for unit in units if unit["evidence_state"] == "STALE" or unit["status"] == "STALE")
    progress_fraction = pass_count / EXPECTED_UNIT_COUNT if EXPECTED_UNIT_COUNT else 0.0
    return {
        "schema": "persona_dream.global_progress.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_path": str(source_path),
        "status": PASS_STATUS if not blockers else BLOCKED_STATUS,
        "provider_live": False,
        "paid_call_authorized": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "actual_provider_call_attempts": 0,
        "live_image_call_started": False,
        "live_kling_call_started": False,
        "manual_acceptance_claimed": False,
        "submitted": False,
        "label": "LOCAL_REVISION_EVIDENCE_PROGRESS",
        "unit_count": len(units),
        "expected_unit_count": EXPECTED_UNIT_COUNT,
        "pass_count": pass_count,
        "blocked_count": blocked_count,
        "stale_count": stale_count,
        "progress_fraction": progress_fraction,
        "progress_percent": round(progress_fraction * 100, 2),
        "units": units,
        "blockers": blockers,
        "claims": {
            "proves": [
                "local evidence units were counted from receipt-bound source records",
                "the rollup did not claim provider readiness, paid-call approval, manual acceptance, submission, or live generation",
            ],
            "does_not_prove": [
                "visual quality",
                "manual acceptance",
                "provider readiness",
                "provider-accessible URLs",
                "paid-call authorization",
                "live Kling generation",
            ],
        },
    }


def run_one(source_path: Path, output_root: Path) -> dict[str, Any]:
    source = read_json(source_path)
    rollup = build_rollup(source, source_path)
    progress_path = output_root / "global_progress.v1.json"
    write_json(progress_path, rollup)
    receipt = {
        "schema": "persona_dream.global_progress_rollup_receipt.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": rollup["status"],
        "provider_live": False,
        "paid_call_authorized": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "actual_provider_call_attempts": 0,
        "live_image_call_started": False,
        "live_kling_call_started": False,
        "source_path": str(source_path),
        "global_progress_path": str(progress_path),
        "unit_count": rollup["unit_count"],
        "pass_count": rollup["pass_count"],
        "blocked_count": rollup["blocked_count"],
        "stale_count": rollup["stale_count"],
        "progress_percent": rollup["progress_percent"],
        "observed_blockers": sorted(rollup["blockers"]),
        "claims": rollup["claims"],
    }
    receipt_path = output_root / "global_progress_rollup_receipt.v1.json"
    write_json(receipt_path, receipt)
    return receipt


def expected_for_fixture(fixture_dir: Path) -> dict[str, Any]:
    path = fixture_dir / "expected.json"
    return read_json(path) if path.exists() else {}


def run_fixtures(fixtures_root: Path, receipt_out: Path) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    output_root = receipt_out.parent / "global-progress-fixture-results"
    for source_path in sorted(fixtures_root.glob("**/global_progress_sources.v1.json")):
        fixture_dir = source_path.parent
        result_dir = output_root / fixture_dir.relative_to(fixtures_root)
        receipt = run_one(source_path, result_dir)
        expected = expected_for_fixture(fixture_dir)
        errors: list[str] = []
        if expected.get("status") and receipt["status"] != expected["status"]:
            errors.append(f"status_mismatch:{receipt['status']}:expected:{expected['status']}")
        for blocker in expected.get("blockers", []):
            if blocker not in receipt["observed_blockers"]:
                errors.append(f"missing_blocker:{blocker}")
        if "unit_count" in expected and receipt["unit_count"] != expected["unit_count"]:
            errors.append(f"unit_count_mismatch:{receipt['unit_count']}:expected:{expected['unit_count']}")
        results.append(
            {
                "fixture": str(fixture_dir.relative_to(fixtures_root)),
                "status": receipt["status"],
                "unit_count": receipt["unit_count"],
                "pass_count": receipt["pass_count"],
                "blocked_count": receipt["blocked_count"],
                "stale_count": receipt["stale_count"],
                "observed_blockers": receipt["observed_blockers"],
                "expected": expected,
                "errors": errors,
            }
        )
    errors = [f"{result['fixture']}:{error}" for result in results for error in result["errors"]]
    aggregate = {
        "schema": "persona_dream.global_progress_rollup_checker_receipt.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": PASS_STATUS if not errors else BLOCKED_STATUS,
        "provider_live": False,
        "paid_call_authorized": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "actual_provider_call_attempts": 0,
        "live_image_call_started": False,
        "live_kling_call_started": False,
        "fixture_count": len(results),
        "observed_blockers": sorted({blocker for result in results for blocker in result["observed_blockers"]}),
        "errors": errors,
        "results": results,
        "claims": {
            "proves": [
                "global progress rollup fixtures were classified deterministically",
                "the aggregate did not claim provider readiness or live submission",
            ],
            "does_not_prove": [
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
    group.add_argument("--source", type=Path)
    group.add_argument("--fixtures-root", type=Path)
    parser.add_argument("--receipt-out", required=True, type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.source:
        receipt = run_one(args.source.resolve(), args.receipt_out.resolve().parent)
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
