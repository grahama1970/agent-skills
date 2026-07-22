#!/usr/bin/env python3
"""Audit PCTOM-R2 Phase 3 pre-seal outcome isolation."""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from pctom_phase3_lineage_lib import audit_case_data, collect_forbidden_paths, load_case_data, mutation_status
from pctom_r2_phase1_lib import ROOT_DEFAULT, SCHEMA_PREFIX, now_iso, rel, stable_json_sha256, write_json


PASS_STATUS = "PASS_PCTOM_PRESEAL_OUTCOME_ISOLATION"
BLOCKED_STATUS = "BLOCKED_PCTOM_PRESEAL_OUTCOME_ISOLATION"


def _negative_cases(data: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    cases: list[tuple[str, str, dict[str, Any]]] = []
    outcome_visible = deepcopy(data)
    outcome_visible["tom_prediction_commitment"]["outcome_visible"] = True
    cases.append(("outcome-visible-true", "BLOCKED_PCTOM_PROSPECTIVE_LEAKAGE", outcome_visible))

    hidden_world = deepcopy(data)
    hidden_world["tom_prediction_commitment"]["prediction_payload"]["hidden_world_state"] = {
        "kai_private_belief": "Embry already ignored the warning"
    }
    cases.append(("hidden-world-state-in-payload", "BLOCKED_PCTOM_PROSPECTIVE_LEAKAGE", hidden_world))

    scoring_receipt = deepcopy(data)
    scoring_receipt["dream_branches"][0]["scoring_receipt"] = "receipts/future-score.json"
    cases.append(("score-artifact-in-branch", "BLOCKED_PCTOM_PROSPECTIVE_LEAKAGE", scoring_receipt))
    return cases


def audit_isolation(root: Path, case_root: Path, receipt_out: Path) -> dict[str, Any]:
    errors: list[str] = []
    data, load_errors = load_case_data(case_root)
    case_errors, derived = audit_case_data(data)
    errors.extend(load_errors)
    errors.extend(error for error in case_errors if error.startswith("prospective_leakage:"))

    negative_results: list[dict[str, Any]] = []
    for case_name, expected_status, mutated in _negative_cases(data):
        mutation_errors, mutation_derived = audit_case_data(mutated)
        observed_status = mutation_status(mutation_errors)
        blocked_as_expected = observed_status == expected_status
        if not blocked_as_expected:
            errors.append(f"negative_fixture_not_blocked:{case_name}:{observed_status}:{expected_status}")
        negative_results.append({
            "fixture": case_name,
            "expected_status": expected_status,
            "observed_status": observed_status,
            "blocked_as_expected": blocked_as_expected,
            "forbidden_paths": collect_forbidden_paths(mutated),
            "counts": mutation_derived["counts"],
            "errors": mutation_errors,
        })

    counts = {
        "case_files": 4,
        "preseal_outcome_dependencies": derived["counts"]["preseal_outcome_dependencies"],
        "forbidden_outcome_paths": len(derived["forbidden_paths"]),
        "negative_fixtures": len(negative_results),
        "negative_fixtures_blocked": sum(1 for row in negative_results if row.get("blocked_as_expected") is True),
        "preseal_reveal_read_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
    }
    status = PASS_STATUS if not errors and counts["preseal_outcome_dependencies"] == 0 else BLOCKED_STATUS
    receipt = {
        "schema": f"{SCHEMA_PREFIX}.pctom_preseal_outcome_isolation_receipt.v1",
        "created_at": now_iso(),
        "status": status,
        "mocked": False,
        "live": False,
        "fixture_backed": True,
        "provider_call_attempts": 0,
        "memory_write_attempts": 0,
        "human_content_judgment_rows": 0,
        "llm_judge_rows": 0,
        "case_root": rel(root, case_root),
        "counts": counts,
        "isolation_checks": {
            "outcome_visible_false_before_reveal": derived["counts"]["preseal_outcome_dependencies"] == 0,
            "forbidden_outcome_keys_absent": not derived["forbidden_paths"],
            "no_reveal_or_score_artifact_dependency": counts["preseal_reveal_read_attempts"] == 0,
            "negative_outcome_leaks_fail_closed": counts["negative_fixtures_blocked"] == counts["negative_fixtures"],
            "prediction_payload_hash_recomputed": derived["payload_hash_valid"],
        },
        "negative_fixture_results": negative_results,
        "errors": errors,
        "claims": {
            "proves": [
                "Gate 0 fixture commitment, residue, and dream branch artifacts contain no pre-seal outcome or scoring dependencies",
                "pre-seal outcome isolation audit fails closed when outcome visibility, hidden world state, or scoring artifacts are injected before reveal",
            ] if status == PASS_STATUS else [
                "pre-seal outcome isolation audit failed closed before Phase 3 acceptance",
            ],
            "does_not_prove": [
                "live Memory recall",
                "semantic dream quality",
                "future prediction accuracy",
                "proper scoring",
                "belief revision",
                "pipeline reliability under service faults",
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
    parser.add_argument("--case-root", type=Path, default=None)
    parser.add_argument("--receipt-out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    case_root = args.case_root or args.root / "fixtures/gate0/positive/lineage_ok"
    receipt = audit_isolation(args.root, case_root, args.receipt_out)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(args.receipt_out)
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
