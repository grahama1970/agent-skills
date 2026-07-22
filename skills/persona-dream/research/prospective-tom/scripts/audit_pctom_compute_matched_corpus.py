#!/usr/bin/env python3
"""Audit PCTOM-R2 Phase 6 compute-matched deterministic corpora."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pctom_phase6_corpus_lib import REQUIRED_CONDITIONS, audit_corpus_data, default_phase6_paths, mutation_status, negative_cases
from pctom_r2_phase1_lib import ROOT_DEFAULT, SCHEMA_PREFIX, file_sha256, load_json, now_iso, rel, stable_json_sha256, write_json


PASS_STATUS = "PASS_PCTOM_COMPUTE_MATCHED_CORPORA"
BLOCKED_STATUS = "BLOCKED_PCTOM_COMPUTE_MATCHED_CORPORA"


def audit_corpus(root: Path, corpus_path: Path, receipt_out: Path) -> dict:
    errors: list[str] = []
    corpus = load_json(corpus_path, errors, "compute_matched_corpus")
    if not isinstance(corpus, dict):
        corpus = {}
    corpus_errors, counts = audit_corpus_data(root, corpus)
    errors.extend(corpus_errors)

    negative_results = []
    for fixture_name, expected_status, mutated in negative_cases(corpus):
        mutation_errors, mutation_counts = audit_corpus_data(root, mutated)
        observed_status = mutation_status(mutation_errors)
        blocked_as_expected = observed_status == expected_status
        if not blocked_as_expected:
            errors.append(f"negative_fixture_not_blocked:{fixture_name}:{observed_status}:{expected_status}")
        negative_results.append({
            "fixture": fixture_name,
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
        "schema": f"{SCHEMA_PREFIX}.pctom_compute_matched_corpus_audit_receipt.v1",
        "created_at": now_iso(),
        "status": status,
        "mocked": False,
        "live": False,
        "fixture_backed": True,
        "provider_call_attempts": 0,
        "memory_write_attempts": 0,
        "human_content_judgment_rows": 0,
        "llm_judge_rows": 0,
        "corpus_path": rel(root, corpus_path),
        "corpus_sha256": file_sha256(corpus_path) if corpus_path.exists() else "",
        "source_corpus_path": rel(root, default_phase6_paths(root)["source_corpus"]),
        "required_conditions": list(REQUIRED_CONDITIONS),
        "counts": counts,
        "corpus_checks": {
            "all_required_conditions_present": counts["condition_missing"] == 0,
            "same_episode_ids_per_condition": counts["condition_missing"] == 0,
            "same_compute_budget_per_condition": counts["compute_budget_mismatches"] == 0,
            "hidden_outcome_fields_absent_from_inputs": counts["outcome_leakage_rows"] == 0,
            "functional_tom_rows_present": counts["functional_tom_missing_rows"] == 0,
            "source_corpus_hash_bound": counts["source_hash_mismatches"] == 0,
            "independent_replay_hashes_match": counts["replay_mismatches"] == 0,
            "human_or_llm_judgment_absent": counts["human_or_llm_judgment_rows"] == 0,
            "negative_mutations_fail_closed": counts["negative_fixtures_blocked"] == counts["negative_fixtures"],
        },
        "negative_fixture_results": negative_results,
        "errors": errors,
        "claims": {
            "proves": [
                "deterministic Memory, free-CD, structured-CD, and functional-ToM corpus rows cover the same source episode ids",
                "all four deterministic corpus conditions carry the same declared compute budget",
                "corpus input packets exclude hidden outcome fields and preserve source-corpus replay hashes",
                "functional-ToM rows include explicit BDI-state and policy-rule artifacts",
                "budget mismatch, missing condition, outcome leakage, missing functional-ToM, source-hash mismatch, and judgment-use mutations fail closed",
            ] if status == PASS_STATUS else [
                "compute-matched corpus audit failed closed before Phase 6 acceptance",
            ],
            "does_not_prove": [
                "live Memory recall",
                "Tau execution",
                "prediction benefit",
                "semantic dream quality",
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
    parser.add_argument("--corpus", type=Path, default=None)
    parser.add_argument("--receipt-out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    corpus_path = args.corpus or default_phase6_paths(args.root)["corpus"]
    receipt = audit_corpus(args.root, corpus_path, args.receipt_out)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(args.receipt_out)
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
