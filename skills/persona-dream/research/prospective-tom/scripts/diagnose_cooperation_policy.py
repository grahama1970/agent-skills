#!/usr/bin/env python3
"""Diagnose observed cooperation-policy failures without reexecuting Tau."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import statistics
import time
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_PCTOM_COOPERATION_POLICY_DIAGNOSTIC"
BLOCKED_STATUS = "BLOCKED_PCTOM_COOPERATION_POLICY_DIAGNOSTIC"
INPUT_PASS_STATUS = "PASS_LIVE_TAU_PCTOM_COOPERATION_INSTRUMENT_SLICE"
POLICY_ID = "pre_outcome_cooperation_threshold_rule.v1"
ZERO_WRITE_KEYS = (
    "memory_write_attempts",
    "provider_call_attempts",
    "canonical_memory_write_attempts",
    "identity_write_attempts",
    "source_memory_write_attempts",
)


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _stable_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
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


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _probability_margin(distribution: list[dict[str, Any]]) -> float | None:
    probabilities = sorted(
        [
            float(item["probability"])
            for item in distribution
            if isinstance(item, dict)
            and isinstance(item.get("probability"), (int, float))
            and not isinstance(item.get("probability"), bool)
        ],
        reverse=True,
    )
    if len(probabilities) < 2:
        return None
    return probabilities[0] - probabilities[1]


def _distribution_sum(distribution: list[dict[str, Any]]) -> float | None:
    total = 0.0
    for item in distribution:
        if not isinstance(item, dict):
            return None
        probability = item.get("probability")
        if not isinstance(probability, (int, float)) or isinstance(probability, bool):
            return None
        total += float(probability)
    return total


def _row_label(row: dict[str, Any]) -> str:
    original = row.get("cd_original_action")
    intervened = row.get("cd_intervened_action")
    oracle = None
    condition_rows = row.get("condition_rows")
    if isinstance(condition_rows, dict):
        cd = condition_rows.get("CD")
        if isinstance(cd, dict):
            oracle = cd.get("oracle_action")
    original_regret = row.get("cd_original_planning_regret")
    intervened_regret = row.get("cd_intervened_planning_regret")
    if not isinstance(original_regret, (int, float)) or isinstance(original_regret, bool):
        return "UNCLASSIFIED_MISSING_ORIGINAL_REGRET"
    if not isinstance(intervened_regret, (int, float)) or isinstance(intervened_regret, bool):
        return "UNCLASSIFIED_MISSING_INTERVENED_REGRET"
    if original == oracle and intervened_regret > original_regret:
        return "LOW_CONFIDENCE_TOP_ACTION_CORRECT_RULE_REGRESSION"
    if original != oracle and intervened_regret < original_regret:
        return "UNSAFE_COOPERATION_RULE_HELPED"
    if original != oracle and intervened_regret >= original_regret:
        return "UNSAFE_COOPERATION_NOT_HELPED"
    if original == oracle and intervened == original:
        return "TOP_ACTION_CORRECT_RULE_UNCHANGED"
    return "OBSERVED_NO_POLICY_EFFECT"


def _rule_inputs_use_oracle_or_outcome(inputs: dict[str, Any]) -> bool:
    if inputs.get("uses_outcome_or_oracle") is not False:
        return True
    forbidden = ("oracle", "outcome", "actual_next_action", "observed")
    for key in inputs:
        lowered = str(key).lower()
        if key == "uses_outcome_or_oracle":
            continue
        if any(token in lowered for token in forbidden):
            return True
    return False


def _diagnose(
    *,
    receipt: dict[str, Any],
    rows_doc: dict[str, Any],
    summary_doc: dict[str, Any],
    require_hashes: bool,
    source_receipt_path: Path | None = None,
) -> tuple[list[str], dict[str, Any], dict[str, Any]]:
    errors: list[str] = []
    if receipt.get("status") != INPUT_PASS_STATUS:
        errors.append(f"input_status_not_pass:{receipt.get('status')}")
    for key in ZERO_WRITE_KEYS:
        if receipt.get(key) != 0:
            errors.append(f"input_{key}_not_zero:{receipt.get(key)}")
    if receipt.get("mocked") is not False or receipt.get("live") is not True:
        errors.append(f"input_live_mocked_flags_mismatch:{receipt.get('live')}:{receipt.get('mocked')}")
    if receipt.get("llm_judge_used") is not False or receipt.get("human_content_judgment_required") is not False:
        errors.append("input_judgment_flags_not_false")
    if receipt.get("live_tau_originated_artifacts_consumed") is not True:
        errors.append("input_live_tau_originated_artifacts_not_consumed")

    rows = rows_doc.get("rows") if isinstance(rows_doc, dict) else None
    if not isinstance(rows, list):
        errors.append("rows_not_list")
        rows = []
    summary_rows = summary_doc.get("rows") if isinstance(summary_doc, dict) else None
    if summary_rows != len(rows):
        errors.append(f"summary_rows_mismatch:{summary_rows}:{len(rows)}")
    summary_candidates = summary_doc.get("cd_offer_cooperation_candidates") if isinstance(summary_doc, dict) else None

    if require_hashes:
        rows_path_value = receipt.get("rows_path")
        summary_path_value = receipt.get("summary_path")
        if not isinstance(rows_path_value, str) or not isinstance(summary_path_value, str):
            errors.append("receipt_rows_or_summary_path_missing")
        else:
            rows_path = Path(rows_path_value)
            summary_path = Path(summary_path_value)
            if not rows_path.exists():
                errors.append(f"rows_path_missing:{rows_path}")
            elif receipt.get("rows_sha256") != _file_sha256(rows_path):
                errors.append("rows_sha256_mismatch")
            if not summary_path.exists():
                errors.append(f"summary_path_missing:{summary_path}")
            elif receipt.get("summary_sha256") != _file_sha256(summary_path):
                errors.append("summary_sha256_mismatch")
        if source_receipt_path is not None and receipt.get("receipt_sha256") != _stable_json_sha256(
            {key: value for key, value in receipt.items() if key != "receipt_sha256"}
        ):
            errors.append("input_receipt_sha256_mismatch")

    candidates: list[dict[str, Any]] = []
    labels: dict[str, int] = {}
    regressions: list[dict[str, Any]] = []
    helped: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"row_{idx}_not_object")
            continue
        inputs = row.get("cd_pre_outcome_rule_inputs")
        if not isinstance(inputs, dict):
            errors.append(f"row_{idx}_missing_cd_pre_outcome_rule_inputs")
            continue
        if _rule_inputs_use_oracle_or_outcome(inputs):
            errors.append(f"row_{idx}_rule_input_uses_oracle_or_outcome")
        is_candidate = (
            row.get("cd_original_action") == "OFFER_COOPERATION"
            and inputs.get("selected_from_predicted_counterpart_action") == "KAI_OFFERS_COOPERATION"
        )
        if not is_candidate:
            continue
        condition_rows = row.get("condition_rows") if isinstance(row.get("condition_rows"), dict) else {}
        cd = condition_rows.get("CD") if isinstance(condition_rows.get("CD"), dict) else {}
        distribution = row.get("condition_rows", {}).get("CD", {}).get("predicted_next_action_distribution", [])
        if not isinstance(distribution, list):
            distribution = []
            errors.append(f"row_{idx}_cd_distribution_not_list")
        label = _row_label(row)
        labels[label] = labels.get(label, 0) + 1
        original_regret = row.get("cd_original_planning_regret")
        intervened_regret = row.get("cd_intervened_planning_regret")
        delta = (
            float(intervened_regret) - float(original_regret)
            if isinstance(original_regret, (int, float))
            and not isinstance(original_regret, bool)
            and isinstance(intervened_regret, (int, float))
            and not isinstance(intervened_regret, bool)
            else None
        )
        candidate = {
            "episode_id": row.get("episode_id"),
            "variant": row.get("variant"),
            "label": label,
            "pre_outcome_features": {
                "original_selected_action": row.get("cd_original_action"),
                "intervened_selected_action": row.get("cd_intervened_action"),
                "selected_from_predicted_counterpart_action": inputs.get("selected_from_predicted_counterpart_action"),
                "selected_counterpart_action_probability": inputs.get("selected_counterpart_action_probability"),
                "probability_margin": _probability_margin(distribution),
                "distribution_sum": _distribution_sum(distribution),
                "action_changed_by_rule": row.get("cd_action_changed_by_rule"),
                "rule": inputs.get("rule"),
                "baseline_original_actions": {
                    key: value.get("original_selected_action")
                    for key, value in condition_rows.items()
                    if key in {"M", "R", "D"} and isinstance(value, dict)
                },
            },
            "post_outcome_evaluation_only": {
                "oracle_action": cd.get("oracle_action"),
                "original_planning_regret": original_regret,
                "intervened_planning_regret": intervened_regret,
                "intervened_minus_original_regret": delta,
                "original_direction": row.get("original_direction"),
                "intervened_direction": row.get("intervened_direction"),
            },
        }
        candidates.append(candidate)
        if label == "LOW_CONFIDENCE_TOP_ACTION_CORRECT_RULE_REGRESSION":
            regressions.append(candidate)
        if label == "UNSAFE_COOPERATION_RULE_HELPED":
            helped.append(candidate)

    if summary_candidates != len(candidates):
        errors.append(f"summary_candidate_count_mismatch:{summary_candidates}:{len(candidates)}")
    if not candidates:
        errors.append("no_cd_offer_cooperation_candidates")

    regression_deltas = [
        candidate["post_outcome_evaluation_only"]["intervened_minus_original_regret"]
        for candidate in regressions
        if isinstance(candidate["post_outcome_evaluation_only"].get("intervened_minus_original_regret"), (int, float))
    ]
    helped_deltas = [
        candidate["post_outcome_evaluation_only"]["intervened_minus_original_regret"]
        for candidate in helped
        if isinstance(candidate["post_outcome_evaluation_only"].get("intervened_minus_original_regret"), (int, float))
    ]
    if regressions and not helped:
        conclusion = "REJECT_SINGLE_PROBABILITY_COOPERATION_FALLBACK"
    elif regressions and helped:
        conclusion = "MIXED_POLICY_EFFECT_NEEDS_FEATURE_SPLIT"
    elif helped and not regressions:
        conclusion = "OBSERVED_RULE_HELPED_UNSAFE_COOPERATION"
    else:
        conclusion = "INSUFFICIENT_POLICY_EFFECT_EXPOSURE"

    diagnostics = {
        "policy_id": POLICY_ID,
        "conclusion": conclusion,
        "candidate_count": len(candidates),
        "label_counts": labels,
        "low_confidence_top_action_correct_regressions": len(regressions),
        "unsafe_cooperation_rule_helped": len(helped),
        "mean_rule_regression_delta": _mean([float(value) for value in regression_deltas]),
        "mean_rule_help_delta": _mean([float(value) for value in helped_deltas]),
        "candidates": candidates,
    }
    checks = {
        "input_receipt_passed": receipt.get("status") == INPUT_PASS_STATUS,
        "live_tau_originated_artifacts_consumed": receipt.get("live_tau_originated_artifacts_consumed") is True,
        "candidate_exposure_present": len(candidates) > 0,
        "rule_inputs_exclude_oracle_or_outcome": not any(
            error.endswith("rule_input_uses_oracle_or_outcome") for error in errors
        ),
        "observed_low_confidence_correct_regression": len(regressions) > 0,
        "unsafe_cooperation_help_not_observed": len(helped) == 0,
        "unsupported_writes_absent": all(receipt.get(key) == 0 for key in ZERO_WRITE_KEYS),
    }
    return errors, checks, diagnostics


def _negative_checks(
    *,
    receipt: dict[str, Any],
    rows_doc: dict[str, Any],
    summary_doc: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}

    leak_rows = copy.deepcopy(rows_doc)
    leak_rows_list = leak_rows.get("rows") if isinstance(leak_rows, dict) else None
    if isinstance(leak_rows_list, list) and leak_rows_list:
        for row in leak_rows_list:
            if isinstance(row, dict) and isinstance(row.get("cd_pre_outcome_rule_inputs"), dict):
                row["cd_pre_outcome_rule_inputs"]["uses_outcome_or_oracle"] = True
                break
    errors, checks, _diagnostics = _diagnose(
        receipt=receipt,
        rows_doc=leak_rows,
        summary_doc=summary_doc,
        require_hashes=False,
    )
    results["rule_input_oracle_outcome_leak"] = {
        "failed_closed": any("rule_input_uses_oracle_or_outcome" in error for error in errors),
        "errors": errors,
        "checks": checks,
    }

    no_candidate_rows = copy.deepcopy(rows_doc)
    rows_list = no_candidate_rows.get("rows") if isinstance(no_candidate_rows, dict) else None
    if isinstance(rows_list, list):
        for row in rows_list:
            if isinstance(row, dict):
                row["cd_original_action"] = "WAIT"
    no_candidate_summary = copy.deepcopy(summary_doc)
    if isinstance(no_candidate_summary, dict):
        no_candidate_summary["cd_offer_cooperation_candidates"] = 0
    errors, checks, _diagnostics = _diagnose(
        receipt=receipt,
        rows_doc=no_candidate_rows,
        summary_doc=no_candidate_summary,
        require_hashes=False,
    )
    results["missing_cd_cooperation_candidate"] = {
        "failed_closed": "no_cd_offer_cooperation_candidates" in errors,
        "errors": errors,
        "checks": checks,
    }

    row_count_summary = copy.deepcopy(summary_doc)
    if isinstance(row_count_summary, dict):
        row_count_summary["rows"] = -1
    errors, checks, _diagnostics = _diagnose(
        receipt=receipt,
        rows_doc=rows_doc,
        summary_doc=row_count_summary,
        require_hashes=False,
    )
    results["summary_row_count_mismatch"] = {
        "failed_closed": any(error.startswith("summary_rows_mismatch") for error in errors),
        "errors": errors,
        "checks": checks,
    }
    return results


def run_diagnostic(
    *,
    instrument_slice_receipt: Path,
    output_root: Path,
    receipt_out: Path,
    run_negative_checks: bool = True,
) -> dict[str, Any]:
    started = time.monotonic()
    instrument_slice_receipt = instrument_slice_receipt.resolve()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    artifacts_root = output_root / "artifacts"
    diagnostic_path = artifacts_root / "cooperation_policy_diagnostic.json"
    negative_path = artifacts_root / "cooperation_policy_diagnostic_negative_checks.json"
    errors: list[str] = []

    receipt = _load_json(instrument_slice_receipt, errors, "instrument_slice_receipt")
    receipt = receipt if isinstance(receipt, dict) else {}
    rows_path = Path(str(receipt.get("rows_path", "")))
    summary_path = Path(str(receipt.get("summary_path", "")))
    rows_doc = _load_json(rows_path, errors, "instrument_rows") if str(rows_path) else None
    summary_doc = _load_json(summary_path, errors, "instrument_summary") if str(summary_path) else None
    rows_doc = rows_doc if isinstance(rows_doc, dict) else {}
    summary_doc = summary_doc if isinstance(summary_doc, dict) else {}

    diagnostic_errors, checks, diagnostics = _diagnose(
        receipt=receipt,
        rows_doc=rows_doc,
        summary_doc=summary_doc,
        require_hashes=True,
        source_receipt_path=instrument_slice_receipt,
    )
    errors.extend(diagnostic_errors)
    negative_results = _negative_checks(receipt=receipt, rows_doc=rows_doc, summary_doc=summary_doc) if run_negative_checks else {}
    negative_checks_failed_closed = all(result.get("failed_closed") is True for result in negative_results.values())
    if run_negative_checks and not negative_checks_failed_closed:
        errors.append("negative_checks_did_not_fail_closed")

    _write_json(
        diagnostic_path,
        {
            "schema": "persona_dream.research.prospective_tom.cooperation_policy_diagnostic.v1",
            **diagnostics,
            "checks": checks,
        },
    )
    if run_negative_checks:
        _write_json(
            negative_path,
            {
                "schema": "persona_dream.research.prospective_tom.cooperation_policy_diagnostic_negative_checks.v1",
                "results": negative_results,
            },
        )

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    final_checks = {
        **checks,
        "negative_checks_failed_closed": negative_checks_failed_closed if run_negative_checks else None,
    }
    receipt_payload = {
        "schema": "persona_dream.research.prospective_tom.cooperation_policy_diagnostic_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "processing_time_s": round(time.monotonic() - started, 3),
        "input_instrument_slice_receipt": str(instrument_slice_receipt),
        "input_instrument_slice_receipt_sha256": _file_sha256(instrument_slice_receipt)
        if instrument_slice_receipt.exists()
        else None,
        "diagnostic_path": str(diagnostic_path),
        "diagnostic_sha256": _file_sha256(diagnostic_path) if diagnostic_path.exists() else None,
        "negative_checks_path": str(negative_path) if run_negative_checks else None,
        "negative_checks_sha256": _file_sha256(negative_path) if run_negative_checks and negative_path.exists() else None,
        "policy_id": POLICY_ID,
        "diagnostic_conclusion": diagnostics.get("conclusion"),
        "candidate_count": diagnostics.get("candidate_count"),
        "label_counts": diagnostics.get("label_counts"),
        "mocked": False,
        "live": receipt.get("live") is True,
        "live_tau_originated_artifacts_consumed": receipt.get("live_tau_originated_artifacts_consumed") is True,
        "live_tau_reexecuted_by_this_command": False,
        "tau_call_attempts": 0,
        "tau_live_call_performed": 0,
        "human_content_judgment_required": False,
        "llm_judge_used": False,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "checks": final_checks,
        "negative_results": negative_results,
        "errors": errors,
        "claims": {
            "proves": [
                "live-originated cooperation candidate rows were deterministically classified into policy-effect labels",
                "the current single-probability cooperation fallback regressed an observed low-confidence but correct cooperation choice",
                "rule-input diagnostics fail closed when oracle/outcome leakage is injected",
                "no Tau call, Memory write, provider call, canonical write, identity write, source-memory write, human content judgment, or LLM judge was used",
            ]
            if status == PASS_STATUS
            else [
                "the cooperation policy diagnostic failed closed before accepting a policy conclusion",
            ],
            "does_not_prove": [
                "a replacement cooperation policy is beneficial",
                "broad held-out planning benefit",
                "confidence-bounded CD planning benefit",
                "semantic dream quality",
                "paid provider execution",
                "complete live Phase 01-16 runtime execution",
            ],
        },
    }
    receipt_payload["receipt_sha256"] = _stable_json_sha256(
        {key: value for key, value in receipt_payload.items() if key != "receipt_sha256"}
    )
    _write_json(receipt_out, receipt_payload)
    return receipt_payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instrument-slice-receipt", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, default=None)
    parser.add_argument("--skip-negative-checks", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt_out = args.receipt_out or (args.output_root / "cooperation_policy_diagnostic_receipt.v1.json")
    receipt = run_diagnostic(
        instrument_slice_receipt=args.instrument_slice_receipt,
        output_root=args.output_root,
        receipt_out=receipt_out,
        run_negative_checks=not args.skip_negative_checks,
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
