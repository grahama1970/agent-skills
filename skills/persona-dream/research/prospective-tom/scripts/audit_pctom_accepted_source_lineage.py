#!/usr/bin/env python3
"""Audit PCTOM-R2 Phase 3 accepted-source lineage evidence."""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from pctom_phase3_lineage_lib import (
    audit_case_data,
    build_lineage_evidence,
    load_case_data,
    mutation_status,
    phase3_negative_cases,
)
from pctom_r2_phase1_lib import ROOT_DEFAULT, SCHEMA_PREFIX, file_sha256, load_json, now_iso, rel, stable_json_sha256, write_json


PASS_STATUS = "PASS_PCTOM_ACCEPTED_SOURCE_LINEAGE"
BLOCKED_STATUS = "BLOCKED_PCTOM_ACCEPTED_SOURCE_LINEAGE"
EXPECTED_NEGATIVE_STATUSES = {
    "unaccepted-source": "BLOCKED_PCTOM_UNACCEPTED_SOURCE",
    "stale-source-substitution": "BLOCKED_PCTOM_STALE_SOURCE_SUBSTITUTION",
    "cross-episode-source": "BLOCKED_PCTOM_CROSS_EPISODE_SOURCE",
    "postseal-lineage-mutation": "BLOCKED_PCTOM_POSTSEAL_LINEAGE_MUTATION",
    "prospective-leakage": "BLOCKED_PCTOM_PROSPECTIVE_LEAKAGE",
}


def _canonical_evidence(root: Path, case_root: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="pctom-phase3-lineage-") as tmpdir:
        scratch = Path(tmpdir) / "pctom-accepted-source-lineage.v1.json"
        return build_lineage_evidence(root, case_root, scratch)


def audit_lineage(root: Path, evidence_path: Path, receipt_out: Path) -> dict[str, Any]:
    errors: list[str] = []
    evidence = load_json(evidence_path, errors, "accepted_source_lineage_evidence")
    if not isinstance(evidence, dict):
        evidence = {}
    case_root_value = evidence.get("source_case_root")
    case_root = root / case_root_value if isinstance(case_root_value, str) and case_root_value else root / "fixtures/gate0/positive/lineage_ok"
    case_data, load_errors = load_case_data(case_root)
    case_errors, case_derived = audit_case_data(case_data)
    errors.extend(load_errors)
    errors.extend(case_errors)

    for source_file in evidence.get("source_files") or []:
        if not isinstance(source_file, dict):
            errors.append("source_file_row_not_object")
            continue
        path_value = source_file.get("path")
        sha_value = source_file.get("sha256")
        if not isinstance(path_value, str) or not path_value:
            errors.append("source_file_missing_path")
            continue
        full_path = root / path_value
        if not full_path.exists():
            errors.append(f"source_file_missing:{path_value}")
            continue
        if sha_value != file_sha256(full_path):
            errors.append(f"source_file_sha_mismatch:{path_value}")

    expected_evidence = _canonical_evidence(root, case_root)
    comparable_fields = ("source_case_root", "source_files", "lineage_rows", "counts")
    for field in comparable_fields:
        if evidence.get(field) != expected_evidence.get(field):
            errors.append(f"accepted_source_lineage_evidence_mismatch:{field}")

    negative_results: list[dict[str, Any]] = []
    for case_name, expected_status, mutated in phase3_negative_cases(case_data):
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
            "counts": mutation_derived["counts"],
            "errors": mutation_errors,
        })

    counts = dict(case_derived["counts"])
    counts["lineage_rows"] = len(evidence.get("lineage_rows") or [])
    counts["negative_fixtures"] = len(negative_results)
    counts["negative_fixtures_blocked"] = sum(1 for row in negative_results if row.get("blocked_as_expected") is True)
    status = PASS_STATUS if not errors and counts["accepted_source_lineage_missing"] == 0 else BLOCKED_STATUS
    receipt = {
        "schema": f"{SCHEMA_PREFIX}.pctom_accepted_source_lineage_audit_receipt.v1",
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
        "case_root": rel(root, case_root),
        "counts": counts,
        "lineage_checks": {
            "query_receipt_to_accepted_source": counts["accepted_source_lineage_missing"] == 0,
            "accepted_source_id_hashes_recomputed": counts["stale_source_substitutions"] == 0,
            "normalized_residue_to_dream_branch": counts["accepted_source_lineage_missing"] == 0,
            "dream_branch_to_tom_prediction": counts["accepted_source_lineage_missing"] == 0,
            "prediction_payload_hash_recomputed": case_derived["payload_hash_valid"],
            "postseal_lineage_mutation_detected": any(
                row["fixture"] == "postseal-lineage-mutation" and row["blocked_as_expected"] for row in negative_results
            ),
            "required_negative_statuses_observed": sorted({row["observed_status"] for row in negative_results})
            == sorted(EXPECTED_NEGATIVE_STATUSES.values()),
        },
        "negative_fixture_results": negative_results,
        "errors": errors,
        "claims": {
            "proves": [
                "archived Gate 0 fixture lineage maps each ToM prediction evidence source through query receipt, accepted raw source id, normalized residue, and dream branch",
                "accepted-source lineage audit fails closed for unaccepted source ids, stale accepted-source hashes, cross-episode source use, post-seal payload mutation, and pre-seal outcome leakage",
            ] if status == PASS_STATUS else [
                "accepted-source lineage audit failed closed before Phase 3 acceptance",
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
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt = audit_lineage(args.root, args.evidence, args.receipt_out)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(args.receipt_out)
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
