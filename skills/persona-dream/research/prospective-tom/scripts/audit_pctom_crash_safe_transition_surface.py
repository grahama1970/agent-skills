#!/usr/bin/env python3
"""Audit PCTOM-R2 Phase 5 crash-safe transition evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pctom_phase5_transition_lib import (
    REQUIRED_FAULT_BOUNDARIES,
    audit_rows,
    mutation_status,
    negative_cases,
)
from pctom_r2_phase1_lib import ROOT_DEFAULT, SCHEMA_PREFIX, file_sha256, load_json, now_iso, rel, stable_json_sha256, write_json


PASS_STATUS = "PASS_PCTOM_CRASH_SAFE_TRANSITIONS"
BLOCKED_STATUS = "BLOCKED_PCTOM_CRASH_SAFE_TRANSITIONS"


def _audit_sources(root: Path, surface: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for index, source in enumerate(surface.get("source_files") or []):
        if not isinstance(source, dict):
            errors.append(f"source_{index}_not_object")
            continue
        path_value = source.get("path")
        if not isinstance(path_value, str) or not path_value:
            errors.append(f"source_{index}_missing_path")
            continue
        full = root / path_value
        if not full.exists():
            errors.append(f"source_missing:{path_value}")
            continue
        if source.get("sha256") != file_sha256(full):
            errors.append(f"source_sha_mismatch:{path_value}")
    return errors


def audit_surface_data(root: Path, surface: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    if surface.get("schema") != f"{SCHEMA_PREFIX}.pctom_crash_safe_transition_surface.v1":
        errors.append(f"invalid_surface_schema:{surface.get('schema')}")
    for key in ("mocked", "live", "fixture_backed"):
        expected = False if key in {"mocked", "live"} else True
        if surface.get(key) is not expected:
            errors.append(f"surface_{key}_unexpected:{surface.get(key)}:{expected}")
    for counter in ("provider_call_attempts", "memory_write_attempts", "human_content_judgment_rows", "llm_judge_rows"):
        if surface.get(counter, 0) != 0:
            errors.append(f"surface_counter_nonzero:{counter}:{surface.get(counter)}")
    errors.extend(_audit_sources(root, surface))
    rows = surface.get("transition_rows")
    if not isinstance(rows, list):
        errors.append("transition_rows_not_list")
        rows = []
    row_errors, counts = audit_rows(rows)
    errors.extend(row_errors)
    counts["source_errors"] = sum(1 for error in errors if error.startswith("source_"))
    counts["negative_fixtures"] = 0
    counts["negative_fixtures_blocked"] = 0
    return errors, counts


def audit_surface(root: Path, evidence_path: Path, receipt_out: Path) -> dict[str, Any]:
    errors: list[str] = []
    surface = load_json(evidence_path, errors, "crash_safe_transition_surface")
    if not isinstance(surface, dict):
        surface = {}
    surface_errors, counts = audit_surface_data(root, surface)
    errors.extend(surface_errors)

    rows = surface.get("transition_rows") if isinstance(surface.get("transition_rows"), list) else []
    negative_results: list[dict[str, Any]] = []
    for case_name, expected_status, mutated_rows in negative_cases(rows):
        mutated = dict(surface)
        mutated["transition_rows"] = mutated_rows
        mutation_errors, mutation_counts = audit_surface_data(root, mutated)
        observed_status = mutation_status(mutation_errors)
        blocked_as_expected = observed_status == expected_status
        if not blocked_as_expected:
            errors.append(f"negative_fixture_not_blocked:{case_name}:{observed_status}:{expected_status}")
        negative_results.append({
            "fixture": case_name,
            "expected_status": expected_status,
            "observed_status": observed_status,
            "blocked_as_expected": blocked_as_expected,
            "counts": mutation_counts,
            "errors": mutation_errors,
        })
    counts["negative_fixtures"] = len(negative_results)
    counts["negative_fixtures_blocked"] = sum(1 for row in negative_results if row.get("blocked_as_expected") is True)
    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": f"{SCHEMA_PREFIX}.pctom_crash_safe_transition_audit_receipt.v1",
        "created_at": now_iso(),
        "status": status,
        "mocked": False,
        "live": False,
        "fixture_backed": True,
        "provider_call_attempts": 0,
        "memory_write_attempts": 0,
        "human_content_judgment_rows": 0,
        "llm_judge_rows": 0,
        "evidence_path": rel(root, evidence_path),
        "evidence_sha256": file_sha256(evidence_path) if evidence_path.exists() else "",
        "required_fault_boundaries": sorted(REQUIRED_FAULT_BOUNDARIES),
        "counts": counts,
        "transition_checks": {
            "allowed_terminal_outcomes_only": counts["continued_unknown_state"] == 0,
            "recovered_end_states_equivalent": counts["restart_non_equivalent_recoveries"] == 0,
            "blocked_before_side_effect": counts["side_effect_before_block"] == 0,
            "quarantined_without_active_partial_state": counts["active_partial_quarantines"] == 0,
            "no_duplicate_active_predictions_or_revisions": counts["duplicate_active_state"] == 0,
            "no_unauthorized_memory_identity_or_source_writes": counts["unauthorized_writes"] == 0,
            "required_fault_boundaries_present": counts["missing_required_fault_boundaries"] == 0,
            "source_hashes_match": counts["source_errors"] == 0,
            "negative_mutations_fail_closed": counts["negative_fixtures_blocked"] == counts["negative_fixtures"],
        },
        "negative_fixture_results": negative_results,
        "errors": errors,
        "claims": {
            "proves": [
                "deterministic crash-transition rows use only recovered, blocked-before-side-effect, or quarantined-with-no-active-partial terminal outcomes",
                "recovered crash/retry transitions preserve accepted end-state equivalence, while blocked and quarantined transitions leave no accepted side effects",
                "exact retry, retry-after-uncertain-completion, interrupted persistence, malformed structured output, memory timeout, and stale artifact boundaries are represented",
                "continued unknown state, non-equivalent recovery, side effect before block, active partial quarantine, duplicate active state, and unauthorized write mutations fail closed",
            ] if status == PASS_STATUS else [
                "crash-safe transition audit failed closed before Phase 5 acceptance",
            ],
            "does_not_prove": [
                "live service fault injection",
                "deployed production retry machinery",
                "statistical prediction benefit",
                "paid provider execution",
                "production Phase 01-16 runtime execution",
            ],
        },
    }
    receipt["receipt_sha256"] = stable_json_sha256({key: value for key, value in receipt.items() if key != "receipt_sha256"})
    write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT_DEFAULT)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt = audit_surface(args.root, args.evidence, args.receipt_out)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(args.receipt_out)
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
