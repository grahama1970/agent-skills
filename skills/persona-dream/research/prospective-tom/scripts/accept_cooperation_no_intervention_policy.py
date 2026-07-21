#!/usr/bin/env python3
"""Accept no-intervention for the observed cooperation regression slice."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import statistics
import time
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_PCTOM_COOPERATION_NO_INTERVENTION_POLICY_ACCEPTANCE"
BLOCKED_STATUS = "BLOCKED_PCTOM_COOPERATION_NO_INTERVENTION_POLICY_ACCEPTANCE"
INPUT_PASS_STATUS = "PASS_PCTOM_COOPERATION_POLICY_DIAGNOSTIC"
INPUT_REJECT_CONCLUSION = "REJECT_SINGLE_PROBABILITY_COOPERATION_FALLBACK"
REGRESSION_LABEL = "LOW_CONFIDENCE_TOP_ACTION_CORRECT_RULE_REGRESSION"
ACCEPTED_POLICY_ID = "pre_outcome_no_intervention_on_observed_cooperation_candidate.v1"
QUARANTINED_POLICY_ID = "pre_outcome_cooperation_threshold_rule.v1"
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


def _contains_forbidden_pre_outcome_key(value: Any) -> bool:
    forbidden = ("oracle", "outcome", "actual_next_action", "observed")
    if isinstance(value, dict):
        for key, nested in value.items():
            if any(token in str(key).lower() for token in forbidden):
                return True
            if _contains_forbidden_pre_outcome_key(nested):
                return True
    elif isinstance(value, list):
        return any(_contains_forbidden_pre_outcome_key(item) for item in value)
    return False


def _validate_acceptance_inputs(
    *,
    diagnostic_receipt: dict[str, Any],
    diagnostic_doc: dict[str, Any],
    require_hashes: bool,
    diagnostic_receipt_path: Path | None = None,
) -> tuple[list[str], dict[str, Any], dict[str, Any]]:
    errors: list[str] = []
    if diagnostic_receipt.get("status") != INPUT_PASS_STATUS:
        errors.append(f"diagnostic_status_not_pass:{diagnostic_receipt.get('status')}")
    if diagnostic_receipt.get("diagnostic_conclusion") != INPUT_REJECT_CONCLUSION:
        errors.append(f"diagnostic_conclusion_not_reject:{diagnostic_receipt.get('diagnostic_conclusion')}")
    if diagnostic_doc.get("conclusion") != INPUT_REJECT_CONCLUSION:
        errors.append(f"diagnostic_artifact_conclusion_not_reject:{diagnostic_doc.get('conclusion')}")
    if diagnostic_receipt.get("policy_id") != QUARANTINED_POLICY_ID:
        errors.append(f"unexpected_policy_id:{diagnostic_receipt.get('policy_id')}")
    if diagnostic_doc.get("policy_id") != QUARANTINED_POLICY_ID:
        errors.append(f"unexpected_diagnostic_policy_id:{diagnostic_doc.get('policy_id')}")
    if diagnostic_receipt.get("mocked") is not False or diagnostic_receipt.get("live") is not True:
        errors.append(f"diagnostic_live_mocked_flags_mismatch:{diagnostic_receipt.get('live')}:{diagnostic_receipt.get('mocked')}")
    if diagnostic_receipt.get("live_tau_originated_artifacts_consumed") is not True:
        errors.append("diagnostic_live_tau_originated_artifacts_not_consumed")
    if diagnostic_receipt.get("live_tau_reexecuted_by_this_command") is not False:
        errors.append("diagnostic_reexecuted_live_tau")
    if diagnostic_receipt.get("tau_call_attempts") != 0 or diagnostic_receipt.get("tau_live_call_performed") != 0:
        errors.append("diagnostic_tau_calls_not_zero")
    if diagnostic_receipt.get("llm_judge_used") is not False or diagnostic_receipt.get("human_content_judgment_required") is not False:
        errors.append("diagnostic_judgment_flags_not_false")
    for key in ZERO_WRITE_KEYS:
        if diagnostic_receipt.get(key) != 0:
            errors.append(f"diagnostic_{key}_not_zero:{diagnostic_receipt.get(key)}")

    receipt_checks = diagnostic_receipt.get("checks")
    if not isinstance(receipt_checks, dict):
        errors.append("diagnostic_receipt_checks_not_object")
        receipt_checks = {}
    if receipt_checks.get("negative_checks_failed_closed") is not True:
        errors.append("diagnostic_negative_checks_not_failed_closed")
    if receipt_checks.get("observed_low_confidence_correct_regression") is not True:
        errors.append("diagnostic_regression_check_not_true")
    if receipt_checks.get("rule_inputs_exclude_oracle_or_outcome") is not True:
        errors.append("diagnostic_oracle_exclusion_check_not_true")
    if receipt_checks.get("unsupported_writes_absent") is not True:
        errors.append("diagnostic_unsupported_writes_check_not_true")

    label_counts = diagnostic_doc.get("label_counts")
    if not isinstance(label_counts, dict):
        errors.append("diagnostic_label_counts_not_object")
        label_counts = {}
    if label_counts.get(REGRESSION_LABEL, 0) <= 0:
        errors.append("missing_low_confidence_correct_regression_label")
    if diagnostic_doc.get("candidate_count") != diagnostic_receipt.get("candidate_count"):
        errors.append("diagnostic_candidate_count_receipt_mismatch")

    candidates = diagnostic_doc.get("candidates")
    if not isinstance(candidates, list):
        errors.append("diagnostic_candidates_not_list")
        candidates = []
    accepted_rows: list[dict[str, Any]] = []
    avoided_regret_deltas: list[float] = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            errors.append(f"candidate_{index}_not_object")
            continue
        if candidate.get("label") != REGRESSION_LABEL:
            continue
        pre = candidate.get("pre_outcome_features")
        post = candidate.get("post_outcome_evaluation_only")
        if not isinstance(pre, dict):
            errors.append(f"candidate_{index}_pre_outcome_features_not_object")
            continue
        if not isinstance(post, dict):
            errors.append(f"candidate_{index}_post_outcome_evaluation_not_object")
            continue
        if _contains_forbidden_pre_outcome_key(pre):
            errors.append(f"candidate_{index}_pre_outcome_feature_leaks_oracle_or_outcome")
        if pre.get("original_selected_action") != "OFFER_COOPERATION":
            errors.append(f"candidate_{index}_original_action_not_offer_cooperation:{pre.get('original_selected_action')}")
        if pre.get("intervened_selected_action") == pre.get("original_selected_action"):
            errors.append(f"candidate_{index}_threshold_rule_did_not_change_action")
        if pre.get("selected_from_predicted_counterpart_action") != "KAI_OFFERS_COOPERATION":
            errors.append(f"candidate_{index}_selected_counterpart_action_not_cooperation")
        original_regret = post.get("original_planning_regret")
        intervened_regret = post.get("intervened_planning_regret")
        delta = post.get("intervened_minus_original_regret")
        if not isinstance(original_regret, (int, float)) or isinstance(original_regret, bool):
            errors.append(f"candidate_{index}_original_regret_not_number")
            continue
        if not isinstance(intervened_regret, (int, float)) or isinstance(intervened_regret, bool):
            errors.append(f"candidate_{index}_intervened_regret_not_number")
            continue
        if not isinstance(delta, (int, float)) or isinstance(delta, bool):
            errors.append(f"candidate_{index}_regret_delta_not_number")
            continue
        if float(original_regret) >= float(intervened_regret):
            errors.append(f"candidate_{index}_no_intervention_does_not_preserve_lower_regret")
        if float(delta) <= 0:
            errors.append(f"candidate_{index}_regret_delta_not_positive")
        accepted_rows.append(
            {
                "episode_id": candidate.get("episode_id"),
                "variant": candidate.get("variant"),
                "accepted_policy_id": ACCEPTED_POLICY_ID,
                "accepted_action": pre.get("original_selected_action"),
                "quarantined_policy_id": QUARANTINED_POLICY_ID,
                "quarantined_action": pre.get("intervened_selected_action"),
                "pre_outcome_basis": {
                    "selected_from_predicted_counterpart_action": pre.get(
                        "selected_from_predicted_counterpart_action"
                    ),
                    "selected_counterpart_action_probability": pre.get(
                        "selected_counterpart_action_probability"
                    ),
                    "probability_margin": pre.get("probability_margin"),
                    "distribution_sum": pre.get("distribution_sum"),
                    "baseline_original_actions": pre.get("baseline_original_actions"),
                    "action_changed_by_quarantined_rule": pre.get("action_changed_by_rule"),
                },
                "post_outcome_evaluation_only": {
                    "oracle_action": post.get("oracle_action"),
                    "original_planning_regret": original_regret,
                    "quarantined_rule_planning_regret": intervened_regret,
                    "regret_delta_avoided": delta,
                    "original_direction": post.get("original_direction"),
                    "quarantined_rule_direction": post.get("intervened_direction"),
                },
            }
        )
        avoided_regret_deltas.append(float(delta))

    if not accepted_rows:
        errors.append("no_accepted_no_intervention_rows")

    acceptance = {
        "schema": "persona_dream.research.prospective_tom.cooperation_no_intervention_policy_acceptance.v1",
        "accepted_policy_id": ACCEPTED_POLICY_ID,
        "quarantined_policy_ids": [QUARANTINED_POLICY_ID],
        "input_diagnostic_conclusion": diagnostic_doc.get("conclusion"),
        "input_candidate_count": diagnostic_doc.get("candidate_count"),
        "input_label_counts": label_counts,
        "acceptance_scope": "observed_live_instrument_regression_candidates_only",
        "accepted_rows": accepted_rows,
        "summary": {
            "accepted_row_count": len(accepted_rows),
            "threshold_regression_row_count": len(accepted_rows),
            "mean_regret_delta_avoided": _mean(avoided_regret_deltas),
            "broad_planning_benefit_claimed": False,
            "replacement_policy_claimed": False,
        },
    }
    checks = {
        "diagnostic_receipt_passed": diagnostic_receipt.get("status") == INPUT_PASS_STATUS,
        "diagnostic_rejected_threshold_rule": diagnostic_receipt.get("diagnostic_conclusion")
        == INPUT_REJECT_CONCLUSION
        and diagnostic_doc.get("conclusion") == INPUT_REJECT_CONCLUSION,
        "regression_label_present": label_counts.get(REGRESSION_LABEL, 0) > 0,
        "pre_outcome_basis_excludes_oracle_or_outcome": not any(
            error.endswith("pre_outcome_feature_leaks_oracle_or_outcome") for error in errors
        ),
        "no_intervention_preserves_lower_regret": all(
            row["post_outcome_evaluation_only"]["regret_delta_avoided"] > 0 for row in accepted_rows
        )
        and bool(accepted_rows),
        "unsupported_writes_absent": all(diagnostic_receipt.get(key) == 0 for key in ZERO_WRITE_KEYS),
        "no_new_tau_calls": diagnostic_receipt.get("tau_call_attempts") == 0
        and diagnostic_receipt.get("tau_live_call_performed") == 0,
        "no_judgment_used": diagnostic_receipt.get("llm_judge_used") is False
        and diagnostic_receipt.get("human_content_judgment_required") is False,
    }

    if require_hashes:
        diagnostic_path_value = diagnostic_receipt.get("diagnostic_path")
        if not isinstance(diagnostic_path_value, str):
            errors.append("diagnostic_path_missing_from_receipt")
        else:
            diagnostic_path = Path(diagnostic_path_value)
            if not diagnostic_path.exists():
                errors.append(f"diagnostic_path_missing:{diagnostic_path}")
            elif diagnostic_receipt.get("diagnostic_sha256") != _file_sha256(diagnostic_path):
                errors.append("diagnostic_sha256_mismatch")
        if diagnostic_receipt_path is not None and diagnostic_receipt.get("receipt_sha256") != _stable_json_sha256(
            {key: value for key, value in diagnostic_receipt.items() if key != "receipt_sha256"}
        ):
            errors.append("diagnostic_receipt_sha256_mismatch")

    return errors, checks, acceptance


def _negative_checks(*, diagnostic_receipt: dict[str, Any], diagnostic_doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}

    wrong_conclusion_receipt = copy.deepcopy(diagnostic_receipt)
    wrong_conclusion_doc = copy.deepcopy(diagnostic_doc)
    wrong_conclusion_receipt["diagnostic_conclusion"] = "OBSERVED_RULE_HELPED_UNSAFE_COOPERATION"
    wrong_conclusion_doc["conclusion"] = "OBSERVED_RULE_HELPED_UNSAFE_COOPERATION"
    errors, checks, _acceptance = _validate_acceptance_inputs(
        diagnostic_receipt=wrong_conclusion_receipt,
        diagnostic_doc=wrong_conclusion_doc,
        require_hashes=False,
    )
    results["diagnostic_conclusion_not_reject"] = {
        "failed_closed": any("conclusion_not_reject" in error for error in errors),
        "errors": errors,
        "checks": checks,
    }

    missing_regression_receipt = copy.deepcopy(diagnostic_receipt)
    missing_regression_doc = copy.deepcopy(diagnostic_doc)
    if isinstance(missing_regression_doc.get("label_counts"), dict):
        missing_regression_doc["label_counts"][REGRESSION_LABEL] = 0
    if isinstance(missing_regression_doc.get("candidates"), list):
        for candidate in missing_regression_doc["candidates"]:
            if isinstance(candidate, dict) and candidate.get("label") == REGRESSION_LABEL:
                candidate["label"] = "UNSAFE_COOPERATION_RULE_HELPED"
    errors, checks, _acceptance = _validate_acceptance_inputs(
        diagnostic_receipt=missing_regression_receipt,
        diagnostic_doc=missing_regression_doc,
        require_hashes=False,
    )
    results["missing_regression_candidate"] = {
        "failed_closed": "missing_low_confidence_correct_regression_label" in errors
        and "no_accepted_no_intervention_rows" in errors,
        "errors": errors,
        "checks": checks,
    }

    leak_doc = copy.deepcopy(diagnostic_doc)
    candidates = leak_doc.get("candidates") if isinstance(leak_doc, dict) else None
    if isinstance(candidates, list) and candidates:
        for candidate in candidates:
            if isinstance(candidate, dict) and isinstance(candidate.get("pre_outcome_features"), dict):
                candidate["pre_outcome_features"]["oracle_action"] = "OFFER_COOPERATION"
                break
    errors, checks, _acceptance = _validate_acceptance_inputs(
        diagnostic_receipt=diagnostic_receipt,
        diagnostic_doc=leak_doc,
        require_hashes=False,
    )
    results["pre_outcome_oracle_leak"] = {
        "failed_closed": any("pre_outcome_feature_leaks_oracle_or_outcome" in error for error in errors),
        "errors": errors,
        "checks": checks,
    }

    non_beneficial_doc = copy.deepcopy(diagnostic_doc)
    candidates = non_beneficial_doc.get("candidates") if isinstance(non_beneficial_doc, dict) else None
    if isinstance(candidates, list):
        for candidate in candidates:
            if (
                isinstance(candidate, dict)
                and candidate.get("label") == REGRESSION_LABEL
                and isinstance(candidate.get("post_outcome_evaluation_only"), dict)
            ):
                post = candidate["post_outcome_evaluation_only"]
                post["original_planning_regret"] = 0.55
                post["intervened_planning_regret"] = 0.0
                post["intervened_minus_original_regret"] = -0.55
                break
    errors, checks, _acceptance = _validate_acceptance_inputs(
        diagnostic_receipt=diagnostic_receipt,
        diagnostic_doc=non_beneficial_doc,
        require_hashes=False,
    )
    results["no_intervention_not_lower_regret"] = {
        "failed_closed": any("no_intervention_does_not_preserve_lower_regret" in error for error in errors)
        and any("regret_delta_not_positive" in error for error in errors),
        "errors": errors,
        "checks": checks,
    }
    return results


def run_acceptance(
    *,
    policy_diagnostic_receipt: Path,
    output_root: Path,
    receipt_out: Path,
    run_negative_checks: bool = True,
) -> dict[str, Any]:
    started = time.monotonic()
    policy_diagnostic_receipt = policy_diagnostic_receipt.resolve()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    artifacts_root = output_root / "artifacts"
    acceptance_path = artifacts_root / "cooperation_no_intervention_policy_acceptance.json"
    negative_path = artifacts_root / "cooperation_no_intervention_policy_negative_checks.json"
    errors: list[str] = []

    diagnostic_receipt = _load_json(policy_diagnostic_receipt, errors, "policy_diagnostic_receipt")
    diagnostic_receipt = diagnostic_receipt if isinstance(diagnostic_receipt, dict) else {}
    diagnostic_path = Path(str(diagnostic_receipt.get("diagnostic_path", "")))
    diagnostic_doc = _load_json(diagnostic_path, errors, "policy_diagnostic") if str(diagnostic_path) else None
    diagnostic_doc = diagnostic_doc if isinstance(diagnostic_doc, dict) else {}

    acceptance_errors, checks, acceptance = _validate_acceptance_inputs(
        diagnostic_receipt=diagnostic_receipt,
        diagnostic_doc=diagnostic_doc,
        require_hashes=True,
        diagnostic_receipt_path=policy_diagnostic_receipt,
    )
    errors.extend(acceptance_errors)
    negative_results = (
        _negative_checks(diagnostic_receipt=diagnostic_receipt, diagnostic_doc=diagnostic_doc)
        if run_negative_checks
        else {}
    )
    negative_checks_failed_closed = all(result.get("failed_closed") is True for result in negative_results.values())
    if run_negative_checks and not negative_checks_failed_closed:
        errors.append("negative_checks_did_not_fail_closed")

    _write_json(acceptance_path, acceptance)
    if run_negative_checks:
        _write_json(
            negative_path,
            {
                "schema": "persona_dream.research.prospective_tom.cooperation_no_intervention_policy_negative_checks.v1",
                "results": negative_results,
            },
        )

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    final_checks = {
        **checks,
        "negative_checks_failed_closed": negative_checks_failed_closed if run_negative_checks else None,
    }
    receipt_payload = {
        "schema": "persona_dream.research.prospective_tom.cooperation_no_intervention_policy_acceptance_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "processing_time_s": round(time.monotonic() - started, 3),
        "input_policy_diagnostic_receipt": str(policy_diagnostic_receipt),
        "input_policy_diagnostic_receipt_sha256": _file_sha256(policy_diagnostic_receipt)
        if policy_diagnostic_receipt.exists()
        else None,
        "acceptance_path": str(acceptance_path),
        "acceptance_sha256": _file_sha256(acceptance_path) if acceptance_path.exists() else None,
        "negative_checks_path": str(negative_path) if run_negative_checks else None,
        "negative_checks_sha256": _file_sha256(negative_path) if run_negative_checks and negative_path.exists() else None,
        "accepted_policy_id": ACCEPTED_POLICY_ID,
        "quarantined_policy_ids": [QUARANTINED_POLICY_ID],
        "input_diagnostic_conclusion": diagnostic_receipt.get("diagnostic_conclusion"),
        "candidate_count": diagnostic_receipt.get("candidate_count"),
        "accepted_row_count": acceptance.get("summary", {}).get("accepted_row_count"),
        "threshold_regression_row_count": acceptance.get("summary", {}).get("threshold_regression_row_count"),
        "mean_regret_delta_avoided": acceptance.get("summary", {}).get("mean_regret_delta_avoided"),
        "mocked": False,
        "live": diagnostic_receipt.get("live") is True,
        "live_tau_originated_artifacts_consumed": diagnostic_receipt.get("live_tau_originated_artifacts_consumed") is True,
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
        "broad_planning_benefit_claimed": False,
        "replacement_policy_claimed": False,
        "checks": final_checks,
        "negative_results": negative_results,
        "errors": errors,
        "claims": {
            "proves": [
                "the single-probability cooperation threshold fallback is quarantined for the observed live instrument regression slice",
                "no-intervention preserves the observed lower-regret CD cooperation action for the accepted regression candidate",
                "accepted pre-outcome basis excludes oracle/outcome fields",
                "negative mutations fail closed for conclusion drift, missing regression exposure, oracle leakage, and non-beneficial no-intervention",
                "no Tau call, Memory write, provider call, canonical write, identity write, source-memory write, human content judgment, or LLM judge was used",
            ]
            if status == PASS_STATUS
            else [
                "the no-intervention acceptance failed closed before accepting a policy scope",
            ],
            "does_not_prove": [
                "broad held-out planning benefit",
                "replacement cooperation policy benefit",
                "confidence-bounded CD planning benefit",
                "that no-intervention is optimal outside this observed regression candidate",
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
    parser.add_argument("--policy-diagnostic-receipt", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, default=None)
    parser.add_argument("--skip-negative-checks", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt_out = args.receipt_out or (args.output_root / "cooperation_no_intervention_policy_acceptance_receipt.v1.json")
    receipt = run_acceptance(
        policy_diagnostic_receipt=args.policy_diagnostic_receipt,
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
