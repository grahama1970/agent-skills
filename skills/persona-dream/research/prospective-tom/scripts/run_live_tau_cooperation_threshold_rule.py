#!/usr/bin/env python3
"""Evaluate a pre-outcome cooperation-threshold rule on held-out live Tau rows."""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import random
import statistics
import time
from pathlib import Path
from typing import Any


CONDITIONS = ("M", "R", "D", "CD")
BASELINE_CONDITIONS = ("M", "R", "D")
PASS_STATUS = "PASS_LIVE_TAU_PCTOM_COOPERATION_THRESHOLD_RULE"
BLOCKED_STATUS = "BLOCKED_LIVE_TAU_PCTOM_COOPERATION_THRESHOLD_RULE"
DERIVATION_PASS_STATUS = "PASS_LIVE_TAU_PCTOM_BALANCED_THRESHOLD_INTERVENTION"
BASE_PASS_STATUS = "PASS_LIVE_TAU_PCTOM_SEALED_TEST_REPLICATION"
POLICY_ID = "pre_outcome_cooperation_threshold_rule.v1"
DEFAULT_THRESHOLD = 0.5
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


def _bootstrap_ci(values: list[float], *, samples: int, seed: int, alpha: float) -> dict[str, Any]:
    if not values:
        return {"mean": None, "lower": None, "upper": None, "samples": samples, "alpha": alpha}
    rng = random.Random(seed)
    means: list[float] = []
    for _ in range(samples):
        draw = [values[rng.randrange(len(values))] for _ in values]
        means.append(statistics.fmean(draw))
    means.sort()
    lower_idx = max(0, min(len(means) - 1, int((alpha / 2.0) * len(means))))
    upper_idx = max(0, min(len(means) - 1, int((1.0 - alpha / 2.0) * len(means)) - 1))
    return {
        "mean": statistics.fmean(values),
        "lower": means[lower_idx],
        "upper": means[upper_idx],
        "samples": samples,
        "alpha": alpha,
    }


def _planning_benefit_with_confidence(ci: dict[str, Any]) -> bool:
    upper = ci.get("upper")
    return isinstance(upper, (int, float)) and not isinstance(upper, bool) and upper < 0


def _direction(delta: float) -> str:
    if delta < -1e-9:
        return "BENEFIT"
    if delta > 1e-9:
        return "HARM"
    return "TIE"


def _episode_variant(episode_id: str) -> int | None:
    suffix = episode_id.rsplit("-", 1)[-1]
    try:
        return int(suffix)
    except ValueError:
        return None


def _validate_derivation(receipt: dict[str, Any], errors: list[str]) -> None:
    if receipt.get("status") != DERIVATION_PASS_STATUS:
        errors.append(f"derivation_status_not_pass:{receipt.get('status')}")
    if receipt.get("threshold_intervention_conclusion") != "RAISE_COOPERATION_THRESHOLD_KEEP_CLARIFYING_THRESHOLD_UNPROVEN":
        errors.append(f"derivation_conclusion_unexpected:{receipt.get('threshold_intervention_conclusion')}")
    for key in ZERO_WRITE_KEYS:
        if receipt.get(key) != 0:
            errors.append(f"derivation_{key}_not_zero:{receipt.get(key)}")
    if receipt.get("mocked") is not False or receipt.get("live") is not True:
        errors.append(f"derivation_live_mocked_flags_mismatch:{receipt.get('live')}:{receipt.get('mocked')}")
    if receipt.get("llm_judge_used") is not False or receipt.get("human_content_judgment_required") is not False:
        errors.append("derivation_judgment_flags_not_false")


def _validate_base(receipt: dict[str, Any], errors: list[str]) -> None:
    expected = {
        "status": BASE_PASS_STATUS,
        "split": "sealed_test",
        "episode_limit": 64,
        "full_64_episode_replication": True,
        "mocked": False,
        "live": True,
        "fixture_backed": False,
        "human_content_judgment_required": False,
        "llm_judge_used": False,
    }
    for key, value in expected.items():
        if receipt.get(key) != value:
            errors.append(f"base_{key}_mismatch:{receipt.get(key)}:{value}")
    counts = receipt.get("counts") if isinstance(receipt.get("counts"), dict) else {}
    if counts.get("episodes_consumed") != 64:
        errors.append(f"base_episodes_consumed_mismatch:{counts.get('episodes_consumed')}:64")
    if counts.get("cases") != 256:
        errors.append(f"base_cases_mismatch:{counts.get('cases')}:256")
    for key in ("action_decisions_per_condition", "planning_regret_scores_per_condition"):
        values = counts.get(key)
        if not isinstance(values, dict):
            errors.append(f"base_{key}_not_object")
            continue
        for condition in CONDITIONS:
            if values.get(condition) != 64:
                errors.append(f"base_{key}_{condition}_mismatch:{values.get(condition)}:64")
    for key in ZERO_WRITE_KEYS:
        if receipt.get(key) != 0:
            errors.append(f"base_{key}_not_zero:{receipt.get(key)}")


def _selected_probability_from_commitment(case_root: Path, selected_from: str | None, errors: list[str], label: str) -> tuple[float | None, list[dict[str, Any]]]:
    bundle = _load_json(case_root / "tom_prediction_commitment_bundle.json", errors, f"{label}_commitment_bundle")
    if not isinstance(bundle, dict):
        return None, []
    commitments = bundle.get("commitments")
    if not isinstance(commitments, list) or len(commitments) != 1 or not isinstance(commitments[0], dict):
        errors.append(f"{label}_expected_one_commitment")
        return None, []
    payload = commitments[0].get("prediction_payload")
    if not isinstance(payload, dict):
        errors.append(f"{label}_prediction_payload_missing")
        return None, []
    distribution = payload.get("predicted_next_action_distribution")
    if not isinstance(distribution, list):
        errors.append(f"{label}_predicted_distribution_not_list")
        return None, []
    normalized: list[dict[str, Any]] = []
    total = 0.0
    selected_probability: float | None = None
    for idx, item in enumerate(distribution):
        if not isinstance(item, dict):
            errors.append(f"{label}_distribution_{idx}_not_object")
            continue
        value = item.get("value")
        probability = item.get("probability")
        if not isinstance(value, str) or not isinstance(probability, (int, float)) or isinstance(probability, bool):
            errors.append(f"{label}_distribution_{idx}_invalid:{item}")
            continue
        probability = float(probability)
        total += probability
        normalized.append({"value": value, "probability": probability})
        if selected_from is not None and value == selected_from:
            selected_probability = probability
    if abs(total - 1.0) > 1e-6:
        errors.append(f"{label}_distribution_sum_mismatch:{total}")
    return selected_probability, normalized


def _utility_surface(action_selection: dict[str, Any], errors: list[str], label: str) -> dict[str, float]:
    options = action_selection.get("action_options")
    if not isinstance(options, list):
        errors.append(f"{label}_action_options_not_list")
        return {}
    surface: dict[str, float] = {}
    for idx, option in enumerate(options):
        if not isinstance(option, dict):
            errors.append(f"{label}_option_{idx}_not_object")
            continue
        action = option.get("action")
        utility = option.get("expected_utility")
        if not isinstance(action, str) or not isinstance(utility, (int, float)) or isinstance(utility, bool):
            errors.append(f"{label}_option_{idx}_invalid:{option}")
            continue
        surface[action] = float(utility)
    return surface


def _apply_rule(
    *,
    original_action: str,
    selected_from: str | None,
    selected_probability: float | None,
    threshold: float,
) -> tuple[str, dict[str, Any]]:
    rule_inputs = {
        "original_selected_action": original_action,
        "selected_from_predicted_counterpart_action": selected_from,
        "selected_counterpart_action_probability": selected_probability,
        "cooperation_probability_threshold": threshold,
        "uses_outcome_or_oracle": False,
    }
    if (
        original_action == "OFFER_COOPERATION"
        and selected_from == "KAI_OFFERS_COOPERATION"
        and selected_probability is not None
        and selected_probability < threshold
    ):
        return "WAIT", {
            **rule_inputs,
            "rule": "LOW_CONFIDENCE_COOPERATION_FALLBACK_TO_WAIT",
            "action_changed": True,
        }
    return original_action, {
        **rule_inputs,
        "rule": "KEEP_ORIGINAL_ACTION",
        "action_changed": False,
    }


def _build_rows(
    *,
    base_root: Path,
    case_index: list[Any],
    action_index: list[Any],
    threshold: float,
    errors: list[str],
) -> list[dict[str, Any]]:
    case_by_key = {
        (str(row.get("episode_id")), str(row.get("condition"))): row
        for row in case_index
        if isinstance(row, dict)
    }
    action_by_key = {
        (str(row.get("episode_id")), str(row.get("condition"))): row
        for row in action_index
        if isinstance(row, dict)
    }
    episode_ids = sorted({episode_id for episode_id, _condition in action_by_key})
    rows: list[dict[str, Any]] = []
    for episode_id in episode_ids:
        condition_rows: dict[str, dict[str, Any]] = {}
        missing = [condition for condition in CONDITIONS if (episode_id, condition) not in action_by_key]
        if missing:
            errors.append(f"episode_missing_action_conditions:{episode_id}:{missing}")
            continue
        for condition in CONDITIONS:
            action_index_row = action_by_key[(episode_id, condition)]
            source_case = case_by_key.get((episode_id, condition))
            if not isinstance(source_case, dict):
                errors.append(f"missing_source_case:{episode_id}:{condition}")
                continue
            if action_index_row.get("status") != "PASS_TOM_ACTION_SELECTION":
                errors.append(f"action_status_not_pass:{episode_id}:{condition}:{action_index_row.get('status')}")
            if source_case.get("tau_live_call_performed") is not True or source_case.get("tau_status") != "PASS":
                errors.append(f"source_tau_not_pass:{episode_id}:{condition}")
            action_selection_path = Path(str(action_index_row.get("action_selection_path", "")))
            if not action_selection_path.is_absolute():
                action_selection_path = base_root / action_selection_path
            action_selection = _load_json(action_selection_path, errors, f"action_selection_{episode_id}_{condition}")
            if not isinstance(action_selection, dict):
                continue
            decision_basis = action_selection.get("decision_basis") if isinstance(action_selection.get("decision_basis"), dict) else {}
            selected_from = decision_basis.get("selected_from_predicted_counterpart_action")
            if selected_from is not None and not isinstance(selected_from, str):
                errors.append(f"selected_from_not_string:{episode_id}:{condition}:{selected_from}")
                selected_from = None
            source_case_root = Path(str(source_case.get("case_root", "")))
            selected_probability, distribution = _selected_probability_from_commitment(
                source_case_root,
                selected_from,
                errors,
                f"{episode_id}_{condition}",
            )
            if selected_probability is None:
                basis_probability = decision_basis.get("selected_counterpart_action_probability")
                if isinstance(basis_probability, (int, float)) and not isinstance(basis_probability, bool):
                    selected_probability = float(basis_probability)
            original_action = str(action_index_row.get("selected_action"))
            intervened_action, rule = _apply_rule(
                original_action=original_action,
                selected_from=selected_from,
                selected_probability=selected_probability,
                threshold=threshold,
            )
            surface = _utility_surface(action_selection, errors, f"{episode_id}_{condition}")
            oracle_action = action_index_row.get("oracle_action")
            original_regret = action_index_row.get("planning_regret")
            if not isinstance(original_regret, (int, float)) or isinstance(original_regret, bool):
                errors.append(f"original_regret_not_number:{episode_id}:{condition}:{original_regret}")
                original_regret = None
            oracle_utility = surface.get(str(oracle_action))
            selected_utility = surface.get(intervened_action)
            if oracle_utility is None or selected_utility is None:
                errors.append(f"utility_missing:{episode_id}:{condition}:{oracle_action}:{intervened_action}")
                intervened_regret = None
            else:
                intervened_regret = max(0.0, oracle_utility - selected_utility)
                if abs(intervened_regret) < 1e-9:
                    intervened_regret = 0.0
            condition_rows[condition] = {
                "episode_id": episode_id,
                "variant": _episode_variant(episode_id),
                "condition": condition,
                "original_selected_action": original_action,
                "intervened_selected_action": intervened_action,
                "oracle_action": oracle_action,
                "original_planning_regret": original_regret,
                "intervened_planning_regret": intervened_regret,
                "action_changed_by_rule": rule["action_changed"],
                "pre_outcome_rule_inputs": rule,
                "predicted_next_action_distribution": distribution,
                "source_case_root": str(source_case_root),
                "action_selection_path": str(action_selection_path),
            }
        if set(condition_rows) != set(CONDITIONS):
            errors.append(f"episode_condition_rows_incomplete:{episode_id}:{sorted(condition_rows)}")
            continue
        baseline_original = min(BASELINE_CONDITIONS, key=lambda c: float(condition_rows[c]["original_planning_regret"]))
        baseline_intervened = min(BASELINE_CONDITIONS, key=lambda c: float(condition_rows[c]["intervened_planning_regret"]))
        cd = condition_rows["CD"]
        original_delta = float(cd["original_planning_regret"]) - float(condition_rows[baseline_original]["original_planning_regret"])
        intervened_delta = float(cd["intervened_planning_regret"]) - float(condition_rows[baseline_intervened]["intervened_planning_regret"])
        if abs(original_delta) < 1e-9:
            original_delta = 0.0
        if abs(intervened_delta) < 1e-9:
            intervened_delta = 0.0
        rows.append(
            {
                "episode_id": episode_id,
                "variant": _episode_variant(episode_id),
                "baseline_condition_original": baseline_original,
                "baseline_condition_intervened": baseline_intervened,
                "cd_original_action": cd["original_selected_action"],
                "cd_intervened_action": cd["intervened_selected_action"],
                "cd_action_changed_by_rule": cd["action_changed_by_rule"],
                "cd_pre_outcome_rule_inputs": cd["pre_outcome_rule_inputs"],
                "cd_original_planning_regret": cd["original_planning_regret"],
                "cd_intervened_planning_regret": cd["intervened_planning_regret"],
                "baseline_original_planning_regret": condition_rows[baseline_original]["original_planning_regret"],
                "baseline_intervened_planning_regret": condition_rows[baseline_intervened]["intervened_planning_regret"],
                "original_cd_minus_baseline_planning_regret": original_delta,
                "intervened_cd_minus_baseline_planning_regret": intervened_delta,
                "original_direction": _direction(original_delta),
                "intervened_direction": _direction(intervened_delta),
                "condition_rows": condition_rows,
            }
        )
    return rows


def _summarize(rows: list[dict[str, Any]], *, bootstrap_samples: int, bootstrap_seed: int, alpha: float) -> dict[str, Any]:
    original_deltas = [float(row["original_cd_minus_baseline_planning_regret"]) for row in rows]
    intervened_deltas = [float(row["intervened_cd_minus_baseline_planning_regret"]) for row in rows]
    improvement_deltas = [original - intervened for original, intervened in zip(original_deltas, intervened_deltas)]
    cd_offer_candidates = [
        row
        for row in rows
        if row["cd_original_action"] == "OFFER_COOPERATION"
        and row["cd_pre_outcome_rule_inputs"].get("selected_from_predicted_counterpart_action") == "KAI_OFFERS_COOPERATION"
    ]
    changed_rows = [row for row in rows if row["cd_action_changed_by_rule"]]
    variants = [_episode_variant(str(row["episode_id"])) for row in rows]
    return {
        "rows": len(rows),
        "variant_min": min(variant for variant in variants if variant is not None) if variants else None,
        "variant_max": max(variant for variant in variants if variant is not None) if variants else None,
        "cd_offer_cooperation_candidates": len(cd_offer_candidates),
        "cd_low_confidence_cooperation_interventions": len(changed_rows),
        "cd_action_change_count": len(changed_rows),
        "original_direction_counts": dict(collections.Counter(row["original_direction"] for row in rows)),
        "intervened_direction_counts": dict(collections.Counter(row["intervened_direction"] for row in rows)),
        "original_mean_cd_minus_baseline_planning_regret": _mean(original_deltas),
        "intervened_mean_cd_minus_baseline_planning_regret": _mean(intervened_deltas),
        "mean_improvement_vs_original": _mean(improvement_deltas),
        "intervened_planning_regret_ci": _bootstrap_ci(
            intervened_deltas,
            samples=bootstrap_samples,
            seed=bootstrap_seed,
            alpha=alpha,
        ),
        "improvement_ci": _bootstrap_ci(
            improvement_deltas,
            samples=bootstrap_samples,
            seed=bootstrap_seed + 1,
            alpha=alpha,
        ),
        "changed_rows": changed_rows,
    }


def run_rule(
    *,
    derivation_receipt_path: Path,
    heldout_root: Path,
    output_root: Path,
    receipt_out: Path,
    cooperation_threshold: float,
    bootstrap_samples: int,
    bootstrap_seed: int,
    alpha: float,
) -> dict[str, Any]:
    started = time.monotonic()
    derivation_receipt_path = derivation_receipt_path.resolve()
    heldout_root = heldout_root.resolve()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    errors: list[str] = []

    derivation_receipt = _load_json(derivation_receipt_path, errors, "derivation_receipt")
    derivation_receipt = derivation_receipt if isinstance(derivation_receipt, dict) else {}
    _validate_derivation(derivation_receipt, errors)
    base_receipt_path = heldout_root / "live_tau_sealed_test_replication_receipt.v1.json"
    case_index_path = heldout_root / "live_tau_sealed_test_condition_comparison" / "artifacts" / "live_condition_case_index.json"
    action_index_path = heldout_root / "live_tau_sealed_test_action_selection" / "artifacts" / "live_condition_action_decisions.json"
    base_receipt = _load_json(base_receipt_path, errors, "heldout_base_receipt")
    case_index = _load_json(case_index_path, errors, "heldout_case_index")
    action_index = _load_json(action_index_path, errors, "heldout_action_index")
    base_receipt = base_receipt if isinstance(base_receipt, dict) else {}
    _validate_base(base_receipt, errors)
    if not isinstance(case_index, list):
        errors.append("heldout_case_index_not_list")
        case_index = []
    if not isinstance(action_index, list):
        errors.append("heldout_action_index_not_list")
        action_index = []

    rows = _build_rows(
        base_root=heldout_root,
        case_index=case_index,
        action_index=action_index,
        threshold=cooperation_threshold,
        errors=errors,
    )
    summary = _summarize(
        rows,
        bootstrap_samples=bootstrap_samples,
        bootstrap_seed=bootstrap_seed,
        alpha=alpha,
    )
    disjoint_from_derivation = summary["variant_max"] is not None and summary["variant_max"] <= 16
    no_oracle_rule_inputs = all(
        row["cd_pre_outcome_rule_inputs"].get("uses_outcome_or_oracle") is False for row in rows
    )
    no_regression = summary["mean_improvement_vs_original"] == 0.0 and summary["cd_action_change_count"] == 0
    conclusion = (
        "HELDOUT_NO_COOPERATION_EXPOSURE_NO_REGRESSION"
        if no_regression and summary["cd_offer_cooperation_candidates"] == 0
        else "HELDOUT_COOPERATION_THRESHOLD_RULE_CHANGED_ACTIONS"
        if summary["cd_action_change_count"] > 0
        else "HELDOUT_COOPERATION_THRESHOLD_RULE_INCONCLUSIVE"
    )

    artifacts_root = output_root / "artifacts"
    rows_path = artifacts_root / "cooperation_threshold_rule_rows.json"
    summary_path = artifacts_root / "cooperation_threshold_rule_summary.json"
    _write_json(
        rows_path,
        {
            "schema": "persona_dream.research.prospective_tom.cooperation_threshold_rule_rows.v1",
            "policy_id": POLICY_ID,
            "rows": rows,
        },
    )
    _write_json(
        summary_path,
        {
            "schema": "persona_dream.research.prospective_tom.cooperation_threshold_rule_summary.v1",
            "policy_id": POLICY_ID,
            **summary,
            "conclusion": conclusion,
        },
    )

    checks = {
        "derivation_receipt_passed": derivation_receipt.get("status") == DERIVATION_PASS_STATUS,
        "heldout_base_receipt_passed": base_receipt.get("status") == BASE_PASS_STATUS,
        "heldout_is_full64_live_tau": base_receipt.get("full_64_episode_replication") is True
        and base_receipt.get("live") is True
        and base_receipt.get("mocked") is False,
        "heldout_derivation_variant_disjoint": disjoint_from_derivation,
        "no_oracle_or_outcome_inputs_in_rule": no_oracle_rule_inputs,
        "zero_unsupported_writes": all(derivation_receipt.get(key) == 0 for key in ZERO_WRITE_KEYS)
        and all(base_receipt.get(key) == 0 for key in ZERO_WRITE_KEYS),
        "heldout_rows_complete": len(rows) == 64,
        "rule_no_regression_on_unexposed_heldout": no_regression,
    }
    for key, value in checks.items():
        if value is not True:
            errors.append(f"check_failed:{key}:{value}")

    planning_ci = summary["intervened_planning_regret_ci"]
    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.live_tau_cooperation_threshold_rule_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "processing_time_s": round(time.monotonic() - started, 3),
        "policy_id": POLICY_ID,
        "cooperation_probability_threshold": cooperation_threshold,
        "derivation_receipt": str(derivation_receipt_path),
        "derivation_receipt_sha256": _file_sha256(derivation_receipt_path) if derivation_receipt_path.exists() else None,
        "heldout_root": str(heldout_root),
        "heldout_base_receipt": str(base_receipt_path),
        "heldout_base_receipt_sha256": _file_sha256(base_receipt_path) if base_receipt_path.exists() else None,
        "rows_path": str(rows_path),
        "rows_sha256": _file_sha256(rows_path) if rows_path.exists() else None,
        "summary_path": str(summary_path),
        "summary_sha256": _file_sha256(summary_path) if summary_path.exists() else None,
        "mocked": False,
        "live": base_receipt.get("live") is True and derivation_receipt.get("live") is True,
        "fixture_backed": False,
        "live_tau_originated_artifacts_consumed": True,
        "live_tau_reexecuted_by_rule": False,
        "human_content_judgment_required": False,
        "llm_judge_used": False,
        "tau_call_attempts": 0,
        "tau_live_call_performed": 0,
        "tau_call_attempts_in_consumed_heldout": base_receipt.get("counts", {}).get("tau_call_attempts")
        if isinstance(base_receipt.get("counts"), dict)
        else None,
        "tau_live_call_performed_in_consumed_heldout": base_receipt.get("counts", {}).get("tau_live_call_performed")
        if isinstance(base_receipt.get("counts"), dict)
        else None,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "checks": checks,
        "counts": {
            "heldout_rows": summary["rows"],
            "cd_offer_cooperation_candidates": summary["cd_offer_cooperation_candidates"],
            "cd_low_confidence_cooperation_interventions": summary["cd_low_confidence_cooperation_interventions"],
            "cd_action_change_count": summary["cd_action_change_count"],
        },
        "metrics": {
            "original_mean_cd_minus_baseline_planning_regret": summary["original_mean_cd_minus_baseline_planning_regret"],
            "intervened_mean_cd_minus_baseline_planning_regret": summary["intervened_mean_cd_minus_baseline_planning_regret"],
            "mean_improvement_vs_original": summary["mean_improvement_vs_original"],
            "intervened_planning_regret_ci": planning_ci,
            "improvement_ci": summary["improvement_ci"],
            "original_direction_counts": summary["original_direction_counts"],
            "intervened_direction_counts": summary["intervened_direction_counts"],
            "heldout_variant_min": summary["variant_min"],
            "heldout_variant_max": summary["variant_max"],
        },
        "planning_benefit_with_confidence": _planning_benefit_with_confidence(planning_ci),
        "rule_conclusion": conclusion,
        "errors": errors,
        "claims": {
            "proves": [
                "the cooperation-threshold rule uses only pre-outcome action-selection and sealed prediction-distribution fields",
                "the rule can be replayed over the accepted full64 live Tau held-out root without Tau reexecution",
                "the full64 held-out variants contain no CD low-confidence OFFER_COOPERATION exposure and therefore show no-regression only",
                "unsupported Memory/provider/canonical/identity/source-memory writes remain absent",
            ]
            if status == PASS_STATUS
            else [
                "the cooperation-threshold rule failed closed before accepting held-out replay evidence",
            ],
            "does_not_prove": [
                "held-out planning benefit under cooperation-exposure cases",
                "confidence-bounded CD planning benefit",
                "semantic dream quality",
                "paid provider execution",
                "complete live Phase 01-16 runtime execution",
                "that the cooperation threshold is optimal",
            ],
        },
    }
    receipt["receipt_sha256"] = _stable_json_sha256({key: value for key, value in receipt.items() if key != "receipt_sha256"})
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--derivation-receipt", type=Path, required=True)
    parser.add_argument("--heldout-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, default=None)
    parser.add_argument("--cooperation-threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--bootstrap-samples", type=int, default=10000)
    parser.add_argument("--bootstrap-seed", type=int, default=93217)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt_out = args.receipt_out or (args.output_root / "live_tau_cooperation_threshold_rule_receipt.v1.json")
    receipt = run_rule(
        derivation_receipt_path=args.derivation_receipt,
        heldout_root=args.heldout_root,
        output_root=args.output_root,
        receipt_out=receipt_out,
        cooperation_threshold=args.cooperation_threshold,
        bootstrap_samples=args.bootstrap_samples,
        bootstrap_seed=args.bootstrap_seed,
        alpha=args.alpha,
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
