#!/usr/bin/env python3
"""Audit why accepted live Tau planning evidence remains non-general."""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import time
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_LIVE_TAU_PCTOM_PLANNING_NON_GENERALIZATION_AUDIT"
BLOCKED_STATUS = "BLOCKED_LIVE_TAU_PCTOM_PLANNING_NON_GENERALIZATION_AUDIT"
CONCLUSION = "PLANNING_SIGNAL_SPARSE_FAMILY_CONCENTRATED_NOT_GENERALIZED"


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _stable_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path, errors: list[str], label: str) -> Any:
    if not path.exists():
        errors.append(f"missing_{label}:{path}")
        return None
    if path.is_symlink():
        errors.append(f"symlink_{label}:{path}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"malformed_{label}:{path}:{exc}")
        return None


def _ci_upper(receipt: dict[str, Any], metric: str) -> Any:
    metrics = receipt.get("metrics") if isinstance(receipt.get("metrics"), dict) else {}
    intervals = metrics.get("paired_delta_confidence_intervals") if isinstance(metrics, dict) else {}
    ci = intervals.get(metric) if isinstance(intervals, dict) else {}
    return ci.get("upper") if isinstance(ci, dict) else None


def _require(receipt: dict[str, Any], key: str, expected: Any, errors: list[str], label: str) -> None:
    actual = receipt.get(key)
    if actual != expected:
        errors.append(f"{label}_{key}_mismatch:{actual}:{expected}")


def _require_zero_writes(receipt: dict[str, Any], errors: list[str], label: str) -> None:
    for key in (
        "memory_write_attempts",
        "provider_call_attempts",
        "canonical_memory_write_attempts",
        "identity_write_attempts",
        "source_memory_write_attempts",
    ):
        if receipt.get(key) != 0:
            errors.append(f"{label}_{key}_not_zero:{receipt.get(key)}")


def _load_repeated_rows(repeated_receipt: dict[str, Any], errors: list[str]) -> list[dict[str, Any]]:
    rows_path_value = repeated_receipt.get("planning_rows_path")
    if not isinstance(rows_path_value, str):
        errors.append("expanded_repeated_missing_planning_rows_path")
        return []
    rows_payload = _load_json(Path(rows_path_value), errors, "expanded_repeated_planning_rows")
    rows = rows_payload.get("rows") if isinstance(rows_payload, dict) else None
    if not isinstance(rows, list):
        errors.append("expanded_repeated_planning_rows_not_list")
        return []
    valid_rows: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"expanded_repeated_row_{idx}_not_object")
            continue
        if not isinstance(row.get("seed_index"), int):
            errors.append(f"expanded_repeated_row_{idx}_missing_seed_index")
            continue
        if not isinstance(row.get("episode_id"), str):
            errors.append(f"expanded_repeated_row_{idx}_missing_episode_id")
            continue
        valid_rows.append(row)
    return valid_rows


def _seed_pattern_hashes(rows: list[dict[str, Any]]) -> dict[int, str]:
    by_seed: dict[int, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in rows:
        by_seed[int(row["seed_index"])].append(row)
    hashes: dict[int, str] = {}
    for seed, seed_rows in by_seed.items():
        normalized: list[dict[str, Any]] = []
        for row in sorted(seed_rows, key=lambda item: str(item.get("episode_id"))):
            normalized.append(
                {
                    key: value
                    for key, value in sorted(row.items())
                    if key not in {"seed_index", "seed_episode_key"}
                }
            )
        hashes[seed] = _stable_json_sha256(normalized)
    return hashes


def _validate_statistical(stat_receipt: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    _require(stat_receipt, "status", "PASS_LIVE_TAU_PCTOM_FULL64_STATISTICAL_CONFIDENCE", errors, "statistical")
    _require(stat_receipt, "mocked", False, errors, "statistical")
    _require(stat_receipt, "live", True, errors, "statistical")
    _require(stat_receipt, "fixture_backed", False, errors, "statistical")
    _require(stat_receipt, "primary_metric", "belief_brier", errors, "statistical")
    _require(stat_receipt, "primary_benefit_with_confidence", True, errors, "statistical")
    _require(stat_receipt, "planning_benefit_with_confidence", False, errors, "statistical")
    _require(stat_receipt, "tau_call_attempts", 0, errors, "statistical")
    _require(stat_receipt, "tau_live_call_performed", 0, errors, "statistical")
    _require_zero_writes(stat_receipt, errors, "statistical")
    belief_upper = _ci_upper(stat_receipt, "belief_brier")
    planning_upper = _ci_upper(stat_receipt, "planning_regret")
    if not isinstance(belief_upper, (int, float)) or belief_upper >= 0:
        errors.append(f"statistical_belief_ci_upper_not_below_zero:{belief_upper}")
    if not isinstance(planning_upper, (int, float)) or planning_upper < 0:
        errors.append(f"statistical_planning_ci_upper_below_zero_unexpected:{planning_upper}")
    counts = stat_receipt.get("counts") if isinstance(stat_receipt.get("counts"), dict) else {}
    if counts.get("paired_delta_counts", {}).get("planning_regret") != 64:
        errors.append(f"statistical_planning_delta_count_mismatch:{counts.get('paired_delta_counts')}")
    return {"belief_ci_upper": belief_upper, "planning_ci_upper": planning_upper}


def _validate_diagnostic(diagnostic_receipt: dict[str, Any], errors: list[str]) -> None:
    _require(diagnostic_receipt, "status", "PASS_LIVE_TAU_PCTOM_FULL64_PLANNING_DIAGNOSTIC", errors, "diagnostic")
    _require(diagnostic_receipt, "diagnostic_conclusion", "SPARSE_FAMILY_CONCENTRATED_SIGNAL", errors, "diagnostic")
    _require(diagnostic_receipt, "planning_benefit_with_confidence", False, errors, "diagnostic")
    _require(diagnostic_receipt, "planning_ci_crosses_zero", True, errors, "diagnostic")
    _require(diagnostic_receipt, "mocked", False, errors, "diagnostic")
    _require(diagnostic_receipt, "live", True, errors, "diagnostic")
    _require_zero_writes(diagnostic_receipt, errors, "diagnostic")
    counts = diagnostic_receipt.get("counts") if isinstance(diagnostic_receipt.get("counts"), dict) else {}
    expected_counts = {
        "episodes": 64,
        "tie_count": 60,
        "benefit_count": 3,
        "harm_count": 1,
        "nonzero_count": 4,
        "nonzero_families": ["trust-commit"],
    }
    for key, expected in expected_counts.items():
        if counts.get(key) != expected:
            errors.append(f"diagnostic_{key}_mismatch:{counts.get(key)}:{expected}")


def _validate_sensitivity(sensitivity_receipt: dict[str, Any], errors: list[str]) -> None:
    _require(sensitivity_receipt, "status", "PASS_LIVE_TAU_PCTOM_FULL64_ACTION_POLICY_SENSITIVITY", errors, "sensitivity")
    _require(sensitivity_receipt, "sensitivity_conclusion", "REALIZED_ACTION_SWITCH_EXPLAINS_SPARSE_PLANNING_SIGNAL", errors, "sensitivity")
    _require(sensitivity_receipt, "planning_benefit_with_confidence", False, errors, "sensitivity")
    _require(sensitivity_receipt, "mocked", False, errors, "sensitivity")
    _require(sensitivity_receipt, "live", True, errors, "sensitivity")
    _require_zero_writes(sensitivity_receipt, errors, "sensitivity")
    counts = sensitivity_receipt.get("counts") if isinstance(sensitivity_receipt.get("counts"), dict) else {}
    expected_counts = {
        "episodes": 64,
        "action_switch_count": 4,
        "nonzero_delta_count": 4,
        "nonzero_action_switch_count": 4,
        "oracle_match_gain_count": 3,
        "oracle_match_loss_count": 1,
        "net_oracle_match_gain": 2,
        "nonzero_families": ["trust-commit"],
    }
    for key, expected in expected_counts.items():
        if counts.get(key) != expected:
            errors.append(f"sensitivity_{key}_mismatch:{counts.get(key)}:{expected}")


def _validate_repeated(repeated_receipt: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    _require(repeated_receipt, "status", "PASS_LIVE_TAU_PCTOM_TRUST_COMMIT_REPEATED_SEED_SUMMARY", errors, "expanded_repeated")
    _require(repeated_receipt, "mocked", False, errors, "expanded_repeated")
    _require(repeated_receipt, "live", True, errors, "expanded_repeated")
    _require(repeated_receipt, "live_tau_reexecuted", False, errors, "expanded_repeated")
    _require(repeated_receipt, "live_tau_receipts_consumed", True, errors, "expanded_repeated")
    _require(repeated_receipt, "planning_benefit_with_confidence", False, errors, "expanded_repeated")
    _require_zero_writes(repeated_receipt, errors, "expanded_repeated")
    counts = repeated_receipt.get("counts") if isinstance(repeated_receipt.get("counts"), dict) else {}
    expected_counts = {
        "seed_receipts": 2,
        "passed_seed_receipts": 2,
        "total_tau_call_attempts": 64,
        "total_cases": 64,
        "total_planning_rows": 16,
        "action_switch_count": 2,
        "nonzero_delta_count": 2,
        "nonzero_action_switch_count": 2,
    }
    for key, expected in expected_counts.items():
        if counts.get(key) != expected:
            errors.append(f"expanded_repeated_{key}_mismatch:{counts.get(key)}:{expected}")
    if counts.get("oracle_match_transitions") != {"GAIN": 2, "UNCHANGED": 14}:
        errors.append(f"expanded_repeated_oracle_transitions_mismatch:{counts.get('oracle_match_transitions')}")
    planning = repeated_receipt.get("metrics", {}).get("planning") if isinstance(repeated_receipt.get("metrics"), dict) else {}
    ci = planning.get("planning_regret_ci") if isinstance(planning, dict) else {}
    ci_upper = ci.get("upper") if isinstance(ci, dict) else None
    if ci_upper != 0.0:
        errors.append(f"expanded_repeated_planning_ci_upper_not_zero:{ci_upper}")
    rows = _load_repeated_rows(repeated_receipt, errors)
    seed_hashes = _seed_pattern_hashes(rows)
    nonidentical_seed_patterns = len(set(seed_hashes.values())) > 1
    if nonidentical_seed_patterns:
        errors.append("expanded_repeated_seed_behavior_unexpectedly_nonidentical")
    return {
        "planning_ci_upper": ci_upper,
        "seed_pattern_hashes": seed_hashes,
        "nonidentical_seed_patterns": nonidentical_seed_patterns,
    }


def run_audit(
    *,
    full64_statistical_confidence_receipt: Path,
    full64_planning_diagnostic_receipt: Path,
    full64_action_policy_sensitivity_receipt: Path,
    expanded_repeated_seed_receipt: Path,
    output_root: Path,
    receipt_out: Path,
) -> dict[str, Any]:
    started = time.monotonic()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    input_paths = {
        "full64_statistical_confidence": full64_statistical_confidence_receipt.resolve(),
        "full64_planning_diagnostic": full64_planning_diagnostic_receipt.resolve(),
        "full64_action_policy_sensitivity": full64_action_policy_sensitivity_receipt.resolve(),
        "expanded_repeated_seed_summary": expanded_repeated_seed_receipt.resolve(),
    }
    errors: list[str] = []
    loaded: dict[str, dict[str, Any]] = {}
    for label, path in input_paths.items():
        value = _load_json(path, errors, label)
        loaded[label] = value if isinstance(value, dict) else {}

    stat_summary = _validate_statistical(loaded["full64_statistical_confidence"], errors)
    _validate_diagnostic(loaded["full64_planning_diagnostic"], errors)
    _validate_sensitivity(loaded["full64_action_policy_sensitivity"], errors)
    repeated_summary = _validate_repeated(loaded["expanded_repeated_seed_summary"], errors)

    input_hashes = {label: _file_sha256(path) for label, path in input_paths.items() if path.exists()}
    audit_summary = {
        "schema": "persona_dream.research.prospective_tom.planning_non_generalization_audit_summary.v1",
        "input_receipts": {label: str(path) for label, path in input_paths.items()},
        "input_receipt_sha256": input_hashes,
        "conclusion": CONCLUSION,
        "belief_prediction_benefit_supported": loaded["full64_statistical_confidence"].get("primary_benefit_with_confidence") is True,
        "planning_benefit_supported": False,
        "planning_non_generalization_reasons": [
            "full64 planning-regret confidence interval crosses zero",
            "full64 planning deltas are 60 ties, 3 benefits, and 1 harm",
            "all full64 nonzero planning deltas are trust-commit action switches",
            "expanded repeated trust/commitment evidence has CI upper 0.0",
            "expanded repeated trust/commitment seeds reproduced the same action-row pattern",
        ],
        "full64": {
            "belief_brier_ci_upper": stat_summary.get("belief_ci_upper"),
            "planning_regret_ci_upper": stat_summary.get("planning_ci_upper"),
            "planning_counts": loaded["full64_planning_diagnostic"].get("counts"),
            "action_policy_counts": loaded["full64_action_policy_sensitivity"].get("counts"),
        },
        "expanded_repeated": {
            "counts": loaded["expanded_repeated_seed_summary"].get("counts"),
            "planning_ci_upper": repeated_summary.get("planning_ci_upper"),
            "seed_pattern_hashes": repeated_summary.get("seed_pattern_hashes"),
            "nonidentical_seed_patterns": repeated_summary.get("nonidentical_seed_patterns"),
        },
        "next_planning_evidence_needed": (
            "Introduce a broader or different planning intervention that changes action policy on more than the current "
            "trust-commit subset, or run non-identical repeated live Tau behavior over a larger/balanced planning corpus."
        ),
    }
    summary_path = output_root / "artifacts" / "planning_non_generalization_audit_summary.json"
    _write_json(summary_path, audit_summary)

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.planning_non_generalization_audit_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "processing_time_s": round(time.monotonic() - started, 3),
        "input_receipts": {label: str(path) for label, path in input_paths.items()},
        "input_receipt_sha256": input_hashes,
        "summary_path": str(summary_path),
        "summary_sha256": _file_sha256(summary_path),
        "conclusion": CONCLUSION,
        "planning_benefit_with_confidence": False,
        "mocked": False,
        "live": True,
        "fixture_backed": False,
        "live_tau_reexecuted": False,
        "live_tau_receipts_consumed": True,
        "human_content_judgment_required": False,
        "llm_judge_used": False,
        "tau_call_attempts": 0,
        "tau_live_call_performed": 0,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "counts": {
            "input_receipts": len(input_paths),
            "full64_planning_episodes": loaded["full64_planning_diagnostic"].get("counts", {}).get("episodes"),
            "full64_tie_count": loaded["full64_planning_diagnostic"].get("counts", {}).get("tie_count"),
            "full64_nonzero_delta_count": loaded["full64_planning_diagnostic"].get("counts", {}).get("nonzero_count"),
            "full64_action_switch_count": loaded["full64_action_policy_sensitivity"].get("counts", {}).get("action_switch_count"),
            "expanded_repeated_live_tau_calls_consumed": loaded["expanded_repeated_seed_summary"].get("counts", {}).get("total_tau_call_attempts"),
            "expanded_repeated_planning_rows": loaded["expanded_repeated_seed_summary"].get("counts", {}).get("total_planning_rows"),
        },
        "checks": {
            "input_receipts_hash_bound": len(input_hashes) == len(input_paths),
            "full64_belief_brier_benefit_supported": loaded["full64_statistical_confidence"].get("primary_benefit_with_confidence") is True,
            "full64_planning_benefit_not_confidence_bound": loaded["full64_statistical_confidence"].get("planning_benefit_with_confidence") is False,
            "full64_planning_signal_sparse": loaded["full64_planning_diagnostic"].get("counts", {}).get("nonzero_count") == 4,
            "full64_nonzero_deltas_family_concentrated": loaded["full64_planning_diagnostic"].get("counts", {}).get("nonzero_families") == ["trust-commit"],
            "action_policy_sensitivity_explains_nonzero_deltas": loaded["full64_action_policy_sensitivity"].get("sensitivity_conclusion")
            == "REALIZED_ACTION_SWITCH_EXPLAINS_SPARSE_PLANNING_SIGNAL",
            "expanded_repeated_planning_not_confidence_bound": loaded["expanded_repeated_seed_summary"].get("planning_benefit_with_confidence") is False,
            "expanded_repeated_seed_behavior_duplicated": repeated_summary.get("nonidentical_seed_patterns") is False,
            "llm_judge_absent": True,
            "human_content_judgment_absent": True,
            "unsupported_writes_absent": True,
        },
        "metrics": audit_summary,
        "errors": errors,
        "claims": {
            "proves": [
                "accepted live Tau planning receipts were hash-bound into one audit",
                "belief-Brier prediction benefit and planning-regret non-benefit are separated instead of conflated",
                "full64 planning-regret benefit is not confidence-bound because the CI crosses zero",
                "the realized planning signal is sparse and concentrated in trust-commit action switches",
                "expanded repeated trust/commitment live Tau evidence duplicated the action-row pattern and still has CI upper 0.0",
                "no Tau, Memory, provider, canonical memory, identity, source-memory, LLM judge, or human content-judgment action was attempted by this audit",
            ]
            if status == PASS_STATUS
            else [
                "the planning non-generalization audit failed closed before accepting the sparse/non-general planning conclusion",
            ],
            "does_not_prove": [
                "confidence-bounded planning-regret benefit",
                "non-identical repeated live Tau planning behavior",
                "planning benefit under a larger or differently balanced corpus",
                "new live Tau execution inside this aggregate command",
                "production retry machinery",
                "live Memory recall in the sealed-test loop",
                "complete live Phase 01-16 runtime execution",
                "paid provider execution",
                "video, audio, or semantic dream quality",
            ],
        },
    }
    receipt["receipt_sha256"] = _stable_json_sha256({key: value for key, value in receipt.items() if key != "receipt_sha256"})
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full64-statistical-confidence-receipt", type=Path, required=True)
    parser.add_argument("--full64-planning-diagnostic-receipt", type=Path, required=True)
    parser.add_argument("--full64-action-policy-sensitivity-receipt", type=Path, required=True)
    parser.add_argument("--expanded-repeated-seed-receipt", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt_out = args.receipt_out or (args.output_root / "planning_non_generalization_audit_receipt.v1.json")
    receipt = run_audit(
        full64_statistical_confidence_receipt=args.full64_statistical_confidence_receipt,
        full64_planning_diagnostic_receipt=args.full64_planning_diagnostic_receipt,
        full64_action_policy_sensitivity_receipt=args.full64_action_policy_sensitivity_receipt,
        expanded_repeated_seed_receipt=args.expanded_repeated_seed_receipt,
        output_root=args.output_root,
        receipt_out=receipt_out,
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
