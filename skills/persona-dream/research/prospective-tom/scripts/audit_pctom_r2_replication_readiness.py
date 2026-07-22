#!/usr/bin/env python3
"""Final deterministic objective audit for PCTOM-R2 replication readiness."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from pctom_r2_phase1_lib import ROOT_DEFAULT, SCHEMA_PREFIX, file_sha256, load_json, now_iso, rel, stable_json_sha256, write_json


PASS_STATUS = "PASS_PCTOM_R2_REPLICATION_READINESS"
BLOCKED_STATUS = "BLOCKED_PCTOM_R2_REPLICATION_READINESS"

REQUIRED_RECEIPTS = {
    "phase0_contract": ("receipts/pctom-r2-contract-receipt.v1.json", "PASS_PCTOM_R2_CONTRACT"),
    "accepted_source_lineage": (
        "receipts/pctom-accepted-source-lineage-audit.v1.json",
        "PASS_PCTOM_ACCEPTED_SOURCE_LINEAGE",
    ),
    "preseal_outcome_isolation": (
        "receipts/pctom-preseal-outcome-isolation-audit.v1.json",
        "PASS_PCTOM_PRESEAL_OUTCOME_ISOLATION",
    ),
    "deterministic_scoring": (
        "receipts/pctom-deterministic-scoring-surface-audit.v1.json",
        "PASS_PCTOM_DETERMINISTIC_SCORING_SURFACE",
    ),
    "crash_safe_transitions": (
        "receipts/pctom-crash-safe-transition-surface-audit.v1.json",
        "PASS_PCTOM_CRASH_SAFE_TRANSITIONS",
    ),
    "compute_matched_corpus": (
        "receipts/pctom-compute-matched-corpus-audit.v1.json",
        "PASS_PCTOM_COMPUTE_MATCHED_CORPORA",
    ),
    "powered_trial_protocol": (
        "receipts/pctom-powered-trial-protocol-audit.v1.json",
        "PASS_PCTOM_POWERED_TRIAL_PROTOCOL",
    ),
    "evidence_scope": ("receipts/pctom-evidence-scope-audit.v1.json", "PASS_PCTOM_EVIDENCE_SCOPE_LEDGER"),
    "archive_integrity": ("receipts/pctom-archive-integrity-audit.v1.json", "PASS_PCTOM_ARCHIVE_INTEGRITY"),
    "receipt_discovery": ("receipts/pctom-receipt-discovery-audit.v1.json", "PASS_PCTOM_RECEIPT_DISCOVERY"),
    "audit_mutation_suite": ("receipts/pctom-audit-mutation-suite.v1.json", "PASS_PCTOM_AUDIT_MUTATION_SUITE"),
    "evidence_claim_integrity": (
        "receipts/pctom-evidence-claim-integrity-audit.v1.json",
        "PASS_PCTOM_EVIDENCE_CLAIM_INTEGRITY",
    ),
}

FORBIDDEN_COUNTERS = (
    "provider_call_attempts",
    "memory_write_attempts",
    "canonical_memory_write_attempts",
    "identity_write_attempts",
    "source_memory_write_attempts",
    "human_content_judgment_rows",
    "llm_judge_rows",
)


def _receipt_index(root: Path, errors: list[str]) -> dict[str, dict[str, Any]]:
    receipts: dict[str, dict[str, Any]] = {}
    for key, (relative, expected_status) in REQUIRED_RECEIPTS.items():
        path = root / relative
        raw = load_json(path, errors, f"required_receipt_{key}")
        if not isinstance(raw, dict):
            receipts[key] = {
                "path": relative,
                "expected_status": expected_status,
                "status": None,
                "sha256": "",
                "data": {},
            }
            continue
        receipts[key] = {
            "path": relative,
            "expected_status": expected_status,
            "status": raw.get("status"),
            "sha256": file_sha256(path),
            "data": raw,
        }
    return receipts


def _all_negative_fixtures_blocked(receipts: dict[str, dict[str, Any]], errors: list[str]) -> tuple[bool, int, int]:
    total = 0
    blocked = 0
    for key, record in receipts.items():
        results = record["data"].get("negative_fixture_results")
        if results is None:
            continue
        if not isinstance(results, list):
            errors.append(f"negative_fixture_results_not_list:{key}")
            continue
        for index, result in enumerate(results):
            total += 1
            if isinstance(result, dict) and result.get("blocked_as_expected") is True:
                blocked += 1
            else:
                errors.append(f"negative_fixture_not_blocked:{key}:{index}")
    return total == blocked, total, blocked


def _counter_sum(receipts: dict[str, dict[str, Any]], counter: str) -> int:
    total = 0
    for record in receipts.values():
        value = record["data"].get(counter, 0)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            total += value
    return total


def _evaluate_receipts(receipts: dict[str, dict[str, Any]], errors: list[str]) -> dict[str, Any]:
    required_rows: list[dict[str, Any]] = []
    status_errors = 0
    for key, record in receipts.items():
        ok = record["status"] == record["expected_status"]
        if not ok:
            status_errors += 1
            errors.append(f"required_receipt_status_mismatch:{key}:{record['status']}:{record['expected_status']}")
        required_rows.append(
            {
                "receipt_id": key,
                "path": record["path"],
                "sha256": record["sha256"],
                "expected_status": record["expected_status"],
                "observed_status": record["status"],
                "status_ok": ok,
            }
        )
    all_negative_ok, negative_total, negative_blocked = _all_negative_fixtures_blocked(receipts, errors)
    mutation_score = receipts["audit_mutation_suite"]["data"].get("mutation_score")
    discovery_counts = receipts["receipt_discovery"]["data"].get("counts", {})
    lineage_counts = receipts["accepted_source_lineage"]["data"].get("counts", {})
    preseal_counts = receipts["preseal_outcome_isolation"]["data"].get("counts", {})
    crash_counts = receipts["crash_safe_transitions"]["data"].get("counts", {})
    powered_protocol = receipts["powered_trial_protocol"]["data"]
    forbidden_counter_totals = {counter: _counter_sum(receipts, counter) for counter in FORBIDDEN_COUNTERS}
    stop_condition = {
        "all_required_positive_receipts": status_errors == 0,
        "all_required_negative_receipts": all_negative_ok,
        "mutation_score": mutation_score,
        "unrouted_receipts": discovery_counts.get("unrouted_receipts"),
        "preseal_outcome_dependencies": preseal_counts.get("preseal_outcome_dependencies"),
        "accepted_source_lineage_missing": lineage_counts.get("accepted_source_lineage_missing"),
        "restart_non_equivalent_recoveries": crash_counts.get("restart_non_equivalent_recoveries"),
        "human_content_judgment_rows": forbidden_counter_totals["human_content_judgment_rows"],
        "llm_judge_rows": forbidden_counter_totals["llm_judge_rows"],
        "forbidden_side_effects": sum(
            value
            for key, value in forbidden_counter_totals.items()
            if key
            in {
                "provider_call_attempts",
                "memory_write_attempts",
                "canonical_memory_write_attempts",
                "identity_write_attempts",
                "source_memory_write_attempts",
            }
        ),
        "live_efficacy_claimed": powered_protocol.get("live_efficacy_claimed"),
    }
    if mutation_score != 1.0:
        errors.append(f"mutation_score_not_one:{mutation_score}")
    expected_zero_fields = {
        "unrouted_receipts": discovery_counts.get("unrouted_receipts"),
        "preseal_outcome_dependencies": preseal_counts.get("preseal_outcome_dependencies"),
        "accepted_source_lineage_missing": lineage_counts.get("accepted_source_lineage_missing"),
        "restart_non_equivalent_recoveries": crash_counts.get("restart_non_equivalent_recoveries"),
        "human_content_judgment_rows": forbidden_counter_totals["human_content_judgment_rows"],
        "llm_judge_rows": forbidden_counter_totals["llm_judge_rows"],
        "forbidden_side_effects": stop_condition["forbidden_side_effects"],
    }
    for name, value in expected_zero_fields.items():
        if value != 0:
            errors.append(f"stop_condition_nonzero:{name}:{value}")
    if powered_protocol.get("live_efficacy_claimed") is not False:
        errors.append(f"live_efficacy_claimed_not_false:{powered_protocol.get('live_efficacy_claimed')}")
    return {
        "required_rows": required_rows,
        "stop_condition": stop_condition,
        "counts": {
            "required_receipts": len(REQUIRED_RECEIPTS),
            "required_receipts_passed": sum(1 for row in required_rows if row["status_ok"]),
            "negative_fixtures": negative_total,
            "negative_fixtures_blocked": negative_blocked,
            "status_errors": status_errors,
            **forbidden_counter_totals,
        },
    }


def _mutated_errors(root: Path, mutation: str) -> list[str]:
    errors: list[str] = []
    receipts = _receipt_index(root, errors)
    if mutation == "missing-required-receipt":
        receipts["powered_trial_protocol"]["status"] = None
    elif mutation == "bad-required-status":
        receipts["compute_matched_corpus"]["status"] = "BLOCKED_PCTOM_COMPUTE_MATCHED_CORPORA"
    elif mutation == "nonzero-forbidden-side-effect":
        receipts["preseal_outcome_isolation"]["data"]["provider_call_attempts"] = 1
    elif mutation == "live-efficacy-claimed":
        receipts["powered_trial_protocol"]["data"]["live_efficacy_claimed"] = True
    elif mutation == "unrouted-receipt":
        receipts["receipt_discovery"]["data"].setdefault("counts", {})["unrouted_receipts"] = 1
    _evaluate_receipts(receipts, errors)
    return errors


def audit_readiness(root: Path, receipt_out: Path) -> dict[str, Any]:
    errors: list[str] = []
    receipts = _receipt_index(root, errors)
    evaluation = _evaluate_receipts(receipts, errors)
    negative_results: list[dict[str, Any]] = []
    for mutation in (
        "missing-required-receipt",
        "bad-required-status",
        "nonzero-forbidden-side-effect",
        "live-efficacy-claimed",
        "unrouted-receipt",
    ):
        mutation_errors = _mutated_errors(root, mutation)
        observed_status = BLOCKED_STATUS if mutation_errors else PASS_STATUS
        negative_results.append(
            {
                "fixture": mutation,
                "expected_status": BLOCKED_STATUS,
                "observed_status": observed_status,
                "blocked_as_expected": observed_status == BLOCKED_STATUS,
                "errors": mutation_errors,
            }
        )
    for result in negative_results:
        if not result["blocked_as_expected"]:
            errors.append(f"readiness_negative_fixture_not_blocked:{result['fixture']}")
    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": f"{SCHEMA_PREFIX}.pctom_r2_replication_readiness_audit_receipt.v1",
        "created_at": now_iso(),
        "status": status,
        "mocked": False,
        "live": False,
        "fixture_backed": True,
        "provider_call_attempts": 0,
        "memory_write_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "human_content_judgment_rows": 0,
        "llm_judge_rows": 0,
        "required_receipts": evaluation["required_rows"],
        "stop_condition": evaluation["stop_condition"],
        "counts": {
            **evaluation["counts"],
            "negative_fixtures": evaluation["counts"]["negative_fixtures"] + len(negative_results),
            "negative_fixtures_blocked": evaluation["counts"]["negative_fixtures_blocked"]
            + sum(1 for result in negative_results if result["blocked_as_expected"]),
            "readiness_negative_fixtures": len(negative_results),
            "readiness_negative_fixtures_blocked": sum(
                1 for result in negative_results if result["blocked_as_expected"]
            ),
        },
        "negative_fixture_results": negative_results,
        "errors": errors,
        "claims": {
            "proves": [
                "the PCTOM-R2 required local receipts are present with their expected PASS statuses",
                "required negative fixtures across archived receipts fail closed",
                "the audit mutation score is 1.0 and receipt discovery reports zero unrouted receipts",
                "accepted-source lineage, pre-seal outcome isolation, crash-safe restart, no human/LLM judgment, and no forbidden side effects meet the frozen stop-condition counters",
                "the powered-trial protocol is sealed while live efficacy remains unclaimed",
            ]
            if status == PASS_STATUS
            else [
                "the PCTOM-R2 replication-readiness audit failed closed before goal acceptance",
            ],
            "does_not_prove": [
                "live Tau powered-trial execution",
                "live Memory recall in the powered trial",
                "counterfactual-dream prediction benefit",
                "planning benefit",
                "paid provider execution",
                "semantic dream quality",
                "complete production Phase 01-16 runtime execution",
            ],
        },
    }
    receipt["receipt_sha256"] = stable_json_sha256({key: value for key, value in receipt.items() if key != "receipt_sha256"})
    write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT_DEFAULT)
    parser.add_argument("--receipt-out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt = audit_readiness(args.root, args.receipt_out)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(args.receipt_out)
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
