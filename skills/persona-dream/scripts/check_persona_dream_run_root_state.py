#!/usr/bin/env python3
"""Check Persona Dream run-root projection fixtures."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from write_persona_dream_run_state_from_run_root import build_from_run_root, read_json, write_json


PASS_STATUS = "PASS_PERSONA_DREAM_RUN_ROOT_STATE"
BLOCKED_STATUS = "BLOCKED_PERSONA_DREAM_RUN_ROOT_STATE"


def materialize_run_root(fixture_path: Path, target: Path) -> None:
    fixture = read_json(fixture_path)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    files = fixture.get("run_root_files")
    if not isinstance(files, dict):
        return
    for rel_path, content in files.items():
        path = target / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            path.write_text(content, encoding="utf-8")
        else:
            write_json(path, content)


def expected_for_fixture(fixture_path: Path) -> dict[str, Any]:
    fixture = read_json(fixture_path)
    expected = fixture.get("expected")
    return expected if isinstance(expected, dict) else {}


def run_one_fixture(fixture_path: Path, fixtures_root: Path, output_root: Path) -> dict[str, Any]:
    fixture_name = str(fixture_path.parent.relative_to(fixtures_root))
    run_root = output_root / "run-root-fixture-inputs" / fixture_name / "run_root"
    materialize_run_root(fixture_path, run_root)
    out_dir = output_root / "run-root-fixture-results" / fixture_name
    state_path = out_dir / "dream_run_state.v1.json"
    progress_path = out_dir / "global_progress_sources.v1.json"
    adapter_receipt = build_from_run_root(run_root, state_path, progress_path)
    state = read_json(state_path)
    expected = expected_for_fixture(fixture_path)
    errors: list[str] = []
    if expected.get("runtime_state") and state.get("runtime_state") != expected["runtime_state"]:
        errors.append(f"runtime_state_mismatch:{state.get('runtime_state')}:expected:{expected['runtime_state']}")
    blockers = set(adapter_receipt.get("blockers") or [])
    for blocker in expected.get("blockers") or []:
        if blocker not in blockers and blocker not in set(state.get("blockers") or []):
            errors.append(f"missing_blocker:{blocker}")
    return {
        "fixture": fixture_name,
        "status": adapter_receipt["status"],
        "runtime_state": state.get("runtime_state"),
        "blockers": sorted(set(adapter_receipt.get("blockers") or []) | set(state.get("blockers") or [])),
        "dream_run_state_path": str(state_path),
        "global_progress_sources_path": str(progress_path),
        "adapter_receipt_path": str(out_dir / "run_root_state_adapter_receipt.v1.json"),
        "errors": errors,
    }


def run_fixtures(fixtures_root: Path, receipt_out: Path) -> dict[str, Any]:
    output_root = receipt_out.parent
    fixture_paths = sorted(fixtures_root.glob("*/fixture.json"))
    results = [run_one_fixture(path, fixtures_root, output_root) for path in fixture_paths]
    errors = [f"{result['fixture']}:{error}" for result in results for error in result["errors"]]
    observed_blockers = sorted({blocker for result in results for blocker in result["blockers"]})
    observed_states = sorted({str(result["runtime_state"]) for result in results})
    expected_blockers = {
        "BLOCKED_RUN_ROOT_REQUIRED_ARTIFACT_MISSING",
        "BLOCKED_ACCEPTED_EVIDENCE_LOCK_MISSING",
        "BLOCKED_REVIEWER_RECEIPT_MISSING_FOR_ACCEPTED_ARTIFACT",
        "BLOCKED_PROMOTION_RECEIPT_MISSING_FOR_ACCEPTED_ARTIFACT",
        "BLOCKED_UNPLANNED_CHANGE_EVENTS",
        "BLOCKED_TAU_CONTRACT_WITHOUT_EXECUTION_RECEIPT",
        "BLOCKED_PROVIDER_READY_CLAIM",
    }
    if len(results) != 8:
        errors.append(f"fixture_count_mismatch:{len(results)}:expected:8")
    for blocker in sorted(expected_blockers - set(observed_blockers)):
        errors.append(f"missing_expected_observed_blocker:{blocker}")
    receipt = {
        "schema": "persona_dream.run_root_state_checker_receipt.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": PASS_STATUS if not errors else BLOCKED_STATUS,
        "fixture_count": len(results),
        "observed_states": observed_states,
        "observed_blockers": observed_blockers,
        "errors": errors,
        "results": results,
        "actual_provider_call_attempts": 0,
        "provider_live": False,
        "paid_call_authorized": False,
        "provider_accessible_url_created": False,
        "submitted": False,
        "manual_acceptance_claimed": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "mocked": False,
        "claims": {
            "proves": [
                "run-root fixtures were materialized as filesystem run roots",
                "the run-root adapter emitted dream_run_state.v1 and global_progress_sources.v1 artifacts",
                "missing or unsafe run-root evidence produced deterministic blockers",
            ],
            "does_not_prove": [
                "manual acceptance",
                "provider readiness",
                "provider-accessible URLs",
                "paid-call authorization",
                "live Tau execution",
                "live Kling generation",
            ],
        },
    }
    write_json(receipt_out, receipt)
    return receipt


def run_one_run_root(run_root: Path, receipt_out: Path) -> dict[str, Any]:
    out_dir = receipt_out.parent / "run-root-state"
    adapter_receipt = build_from_run_root(run_root, out_dir / "dream_run_state.v1.json", out_dir / "global_progress_sources.v1.json")
    receipt = {
        "schema": "persona_dream.run_root_state_checker_receipt.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": PASS_STATUS if not adapter_receipt.get("blockers") else BLOCKED_STATUS,
        "fixture_count": 0,
        "observed_states": [adapter_receipt["runtime_state"]],
        "observed_blockers": adapter_receipt.get("blockers") or [],
        "errors": [],
        "results": [adapter_receipt],
        "actual_provider_call_attempts": 0,
        "provider_live": False,
        "paid_call_authorized": False,
        "provider_accessible_url_created": False,
        "submitted": False,
        "manual_acceptance_claimed": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "mocked": False,
    }
    write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--fixtures-root", type=Path)
    group.add_argument("--run-root", type=Path)
    parser.add_argument("--receipt-out", required=True, type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.fixtures_root:
        receipt = run_fixtures(args.fixtures_root.resolve(), args.receipt_out.resolve())
    else:
        receipt = run_one_run_root(args.run_root.resolve(), args.receipt_out.resolve())
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
