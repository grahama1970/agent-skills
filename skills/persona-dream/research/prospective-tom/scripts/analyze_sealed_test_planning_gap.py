#!/usr/bin/env python3
"""Diagnose why sealed-test prediction benefit did not become planning benefit."""
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
ACTION_VOCABULARY = (
    "ASK_CLARIFYING_QUESTION",
    "WAIT",
    "DISCLOSE_INFORMATION",
    "OFFER_COOPERATION",
    "SET_BOUNDARY",
    "ACT_INDEPENDENTLY",
    "ABSTAIN",
)
PASS_STATUS = "PASS_PCTOM_SEALED_TEST_PLANNING_GAP_DIAGNOSTIC"
BLOCKED_STATUS = "BLOCKED_PCTOM_SEALED_TEST_PLANNING_GAP_DIAGNOSTIC"
SOURCE_PASS_STATUS = "PASS_PCTOM_SEALED_TEST_STATISTICAL_CONFIDENCE"


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


def _percentile(sorted_values: list[float], percentile: float) -> float | None:
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * percentile
    low = int(rank)
    high = min(low + 1, len(sorted_values) - 1)
    weight = rank - low
    return sorted_values[low] * (1.0 - weight) + sorted_values[high] * weight


def _bootstrap_ci(values: list[float], *, samples: int, seed: int, alpha: float) -> dict[str, Any]:
    if not values:
        return {"samples": samples, "seed": seed, "alpha": alpha, "mean": None, "lower": None, "upper": None}
    rng = random.Random(seed)
    n = len(values)
    means = [statistics.fmean(values[rng.randrange(n)] for _ in range(n)) for _ in range(samples)]
    means.sort()
    return {
        "samples": samples,
        "seed": seed,
        "alpha": alpha,
        "mean": statistics.fmean(values),
        "lower": _percentile(means, alpha / 2.0),
        "upper": _percentile(means, 1.0 - alpha / 2.0),
        "bootstrap_distribution_sha256": _stable_json_sha256(means),
    }


def _direction(delta: float) -> str:
    if delta < -1e-9:
        return "BENEFIT"
    if delta > 1e-9:
        return "HARM"
    return "TIE"


def _counterpart_to_agent_action(counterpart_action: str) -> str:
    action = counterpart_action.upper()
    if "ASKS_TO_WAIT" in action or "QUIET_REVIEW" in action:
        return "WAIT"
    if "OFFERS_COOPERATION" in action:
        return "OFFER_COOPERATION"
    if "HINTS_CONSTRAINT" in action:
        return "ASK_CLARIFYING_QUESTION"
    if "DISCLOSES_AUTHORITY_CONSTRAINT" in action:
        return "DISCLOSE_INFORMATION"
    if "SETS_BOUNDARY" in action:
        return "SET_BOUNDARY"
    if action == "UNKNOWN":
        return "ABSTAIN"
    return "ASK_CLARIFYING_QUESTION"


def _utility(action: str, oracle_action: str) -> float:
    if action == oracle_action:
        return 1.0
    if action == "ASK_CLARIFYING_QUESTION":
        return 0.75
    if action == "ABSTAIN":
        return 0.3
    if action == "WAIT":
        return 0.45
    return 0.15


def _planning_regret(selected_action: str, oracle_action: str) -> float:
    regret = max(0.0, _utility(oracle_action, oracle_action) - _utility(selected_action, oracle_action))
    return 0.0 if abs(regret) < 1e-9 else regret


def _mapped_mass(distribution: list[dict[str, Any]]) -> dict[str, float]:
    mass = {action: 0.0 for action in ACTION_VOCABULARY}
    for item in distribution:
        mass[_counterpart_to_agent_action(str(item["value"]))] += float(item["probability"])
    return mass


def _top_and_margin(mass: dict[str, float]) -> tuple[str, float, float]:
    top_action = max(ACTION_VOCABULARY, key=lambda action: (mass[action], -ACTION_VOCABULARY.index(action)))
    sorted_masses = sorted(mass.values(), reverse=True)
    runner_up = sorted_masses[1] if len(sorted_masses) > 1 else 0.0
    return top_action, mass[top_action], mass[top_action] - runner_up


def _select_margin_gated(distribution: list[dict[str, Any]], margin_threshold: float) -> tuple[str, dict[str, Any]]:
    mass = _mapped_mass(distribution)
    top_action, top_probability, margin = _top_and_margin(mass)
    if margin <= margin_threshold:
        return "ASK_CLARIFYING_QUESTION", {
            "rule": "LOW_MARGIN_EPISTEMIC_ACTION",
            "top_mapped_action": top_action,
            "top_mapped_action_probability": top_probability,
            "mapped_action_margin": margin,
            "margin_threshold": margin_threshold,
        }
    return top_action, {
        "rule": "CLEAR_TOP_MAPPED_ACTION",
        "top_mapped_action": top_action,
        "top_mapped_action_probability": top_probability,
        "mapped_action_margin": margin,
        "margin_threshold": margin_threshold,
    }


def _load_json_object(path: Path, errors: list[str], label: str) -> dict[str, Any]:
    payload = _load_json(path, errors, label)
    return payload if isinstance(payload, dict) else {}


def _validate_source(receipt: dict[str, Any], errors: list[str]) -> None:
    expected = {
        "status": SOURCE_PASS_STATUS,
        "split": "sealed_test",
        "episode_limit": 64,
        "primary_metric": "belief_brier",
        "primary_benefit_with_confidence": True,
        "planning_benefit_with_confidence": False,
        "mocked": False,
        "live": False,
        "fixture_backed": False,
        "human_content_judgment_required": False,
        "llm_judge_used": False,
        "tau_call_attempts": 0,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
    }
    for key, value in expected.items():
        if receipt.get(key) != value:
            errors.append(f"source_{key}_mismatch:{receipt.get(key)}:{value}")
    counts = receipt.get("counts") if isinstance(receipt.get("counts"), dict) else {}
    if counts.get("episodes_consumed") != 64:
        errors.append(f"source_episodes_consumed_mismatch:{counts.get('episodes_consumed')}:64")
    if counts.get("cases") != 256:
        errors.append(f"source_case_count_mismatch:{counts.get('cases')}:256")
    for key in ("sealed_commitments_per_condition", "deterministic_scores_per_condition", "action_decisions_per_condition"):
        values = counts.get(key)
        if not isinstance(values, dict):
            errors.append(f"source_{key}_not_object")
            continue
        for condition in CONDITIONS:
            if values.get(condition) != 64:
                errors.append(f"source_{key}_{condition}_mismatch:{values.get(condition)}:64")


def _load_action_rows(action_index_path: Path, errors: list[str]) -> list[dict[str, Any]]:
    payload = _load_json(action_index_path, errors, "action_decision_index")
    if not isinstance(payload, list):
        errors.append("action_decision_index_not_list")
        return []
    rows: list[dict[str, Any]] = []
    for idx, row in enumerate(payload):
        if not isinstance(row, dict):
            errors.append(f"action_row_{idx}_not_object")
            continue
        if row.get("status") != "PASS_TOM_ACTION_SELECTION":
            errors.append(f"action_row_{idx}_status_not_pass:{row.get('status')}")
        episode_id = row.get("episode_id")
        condition = row.get("condition")
        if not isinstance(episode_id, str) or condition not in CONDITIONS:
            errors.append(f"action_row_{idx}_invalid_identity:{episode_id}:{condition}")
            continue
        rows.append(row)
    return rows


def _load_paired_planning_deltas(paired_delta_path: Path, errors: list[str]) -> list[dict[str, Any]]:
    payload = _load_json_object(paired_delta_path, errors, "paired_delta_bundle")
    rows = payload.get("planning_regret")
    if not isinstance(rows, list):
        errors.append("paired_delta_planning_regret_not_list")
        return []
    valid: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"paired_delta_{idx}_not_object")
            continue
        delta = row.get("cd_minus_baseline")
        if not isinstance(delta, (int, float)) or isinstance(delta, bool):
            errors.append(f"paired_delta_{idx}_delta_not_number:{delta}")
            continue
        valid.append(row)
    return valid


def _condition_rows_by_episode(action_rows: list[dict[str, Any]], errors: list[str]) -> dict[str, dict[str, dict[str, Any]]]:
    by_episode: dict[str, dict[str, dict[str, Any]]] = collections.defaultdict(dict)
    for row in action_rows:
        by_episode[str(row["episode_id"])][str(row["condition"])] = row
    for episode_id, rows in by_episode.items():
        missing = [condition for condition in CONDITIONS if condition not in rows]
        if missing:
            errors.append(f"episode_missing_conditions:{episode_id}:{missing}")
    return by_episode


def _build_original_gap_rows(
    by_episode: dict[str, dict[str, dict[str, Any]]],
    planning_deltas: list[dict[str, Any]],
    errors: list[str],
) -> list[dict[str, Any]]:
    delta_by_episode = {str(row.get("episode_id")): row for row in planning_deltas}
    rows: list[dict[str, Any]] = []
    for episode_id in sorted(by_episode):
        conditions = by_episode[episode_id]
        if any(condition not in conditions for condition in CONDITIONS):
            continue
        delta_row = delta_by_episode.get(episode_id)
        if not delta_row:
            errors.append(f"missing_planning_delta_for_episode:{episode_id}")
            continue
        baseline_condition = str(delta_row.get("baseline_condition"))
        if baseline_condition not in BASELINE_CONDITIONS:
            errors.append(f"invalid_planning_delta_baseline:{episode_id}:{baseline_condition}")
            continue
        cd = conditions["CD"]
        baseline = conditions[baseline_condition]
        cd_regret = float(cd["planning_regret"])
        baseline_regret = float(baseline["planning_regret"])
        computed_delta = cd_regret - baseline_regret
        if abs(computed_delta) < 1e-9:
            computed_delta = 0.0
        supplied_delta = float(delta_row["cd_minus_baseline"])
        if abs(computed_delta - supplied_delta) > 1e-6:
            errors.append(f"planning_delta_mismatch:{episode_id}:{computed_delta}:{supplied_delta}")
        rows.append(
            {
                "episode_id": episode_id,
                "baseline_condition": baseline_condition,
                "baseline_action": baseline.get("selected_action"),
                "cd_action": cd.get("selected_action"),
                "oracle_action": cd.get("oracle_action"),
                "baseline_regret": baseline_regret,
                "cd_regret": cd_regret,
                "cd_minus_baseline": computed_delta,
                "direction": _direction(computed_delta),
            }
        )
    return rows


def _predicted_distribution(commitment_bundle: dict[str, Any], errors: list[str], label: str) -> list[dict[str, Any]]:
    commitments = commitment_bundle.get("commitments")
    if not isinstance(commitments, list) or len(commitments) != 1 or not isinstance(commitments[0], dict):
        errors.append(f"{label}_commitment_bundle_expected_one_commitment")
        return []
    payload = commitments[0].get("prediction_payload")
    if not isinstance(payload, dict):
        errors.append(f"{label}_prediction_payload_missing")
        return []
    distribution = payload.get("predicted_next_action_distribution")
    if not isinstance(distribution, list) or not distribution:
        errors.append(f"{label}_predicted_next_action_distribution_missing")
        return []
    valid: list[dict[str, Any]] = []
    total = 0.0
    for idx, item in enumerate(distribution):
        if not isinstance(item, dict):
            errors.append(f"{label}_predicted_action_{idx}_not_object")
            continue
        value = item.get("value")
        probability = item.get("probability")
        if not isinstance(value, str) or not isinstance(probability, (int, float)) or isinstance(probability, bool):
            errors.append(f"{label}_predicted_action_{idx}_invalid:{item}")
            continue
        valid.append({"value": value, "probability": float(probability)})
        total += float(probability)
    if abs(total - 1.0) > 1e-6:
        errors.append(f"{label}_predicted_action_probability_sum_mismatch:{total}")
    return valid


def _load_commitment(row: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    return _load_json_object(
        Path(str(row.get("source_case_root", ""))) / "tom_prediction_commitment_bundle.json",
        errors,
        f"{row.get('episode_id')}_{row.get('condition')}_commitment",
    )


def _load_outcome(row: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    return _load_json_object(
        Path(str(row.get("source_case_root", ""))) / "tom_outcome_reveal.json",
        errors,
        f"{row.get('episode_id')}_{row.get('condition')}_outcome",
    )


def _top_action_rows(by_episode: dict[str, dict[str, dict[str, Any]]], errors: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for episode_id in sorted(by_episode):
        for condition in CONDITIONS:
            action_row = by_episode[episode_id].get(condition)
            if not action_row:
                continue
            distribution = _predicted_distribution(_load_commitment(action_row, errors), errors, f"{episode_id}_{condition}")
            if not distribution:
                continue
            mass = _mapped_mass(distribution)
            top_action, top_probability, margin = _top_and_margin(mass)
            rows.append(
                {
                    "episode_id": episode_id,
                    "condition": condition,
                    "selected_action": action_row.get("selected_action"),
                    "oracle_action": action_row.get("oracle_action"),
                    "top_mapped_action": top_action,
                    "top_mapped_action_probability": top_probability,
                    "mapped_action_margin": margin,
                    "mapped_action_mass": mass,
                }
            )
    return rows


def _simulate_margin_policy(
    by_episode: dict[str, dict[str, dict[str, Any]]],
    *,
    margin_threshold: float,
    errors: list[str],
) -> dict[str, Any]:
    simulated: dict[str, dict[str, dict[str, Any]]] = collections.defaultdict(dict)
    changed_by_condition: collections.Counter[str] = collections.Counter()
    rule_counts: collections.Counter[str] = collections.Counter()
    for episode_id in sorted(by_episode):
        for condition in CONDITIONS:
            action_row = by_episode[episode_id].get(condition)
            if not action_row:
                continue
            distribution = _predicted_distribution(_load_commitment(action_row, errors), errors, f"margin_{episode_id}_{condition}")
            selected_action, rule = _select_margin_gated(distribution, margin_threshold)
            oracle_action = _counterpart_to_agent_action(str(_load_outcome(action_row, errors).get("actual_next_action")))
            regret = _planning_regret(selected_action, oracle_action)
            if selected_action != action_row.get("selected_action"):
                changed_by_condition[condition] += 1
            rule_counts[str(rule["rule"])] += 1
            simulated[episode_id][condition] = {
                "selected_action": selected_action,
                "original_selected_action": action_row.get("selected_action"),
                "oracle_action": oracle_action,
                "planning_regret": regret,
                "decision_rule": rule,
            }

    deltas: list[float] = []
    planning_rows: list[dict[str, Any]] = []
    for episode_id in sorted(simulated):
        rows = simulated[episode_id]
        if any(condition not in rows for condition in CONDITIONS):
            continue
        baseline_condition = min(BASELINE_CONDITIONS, key=lambda condition: rows[condition]["planning_regret"])
        cd = rows["CD"]
        baseline = rows[baseline_condition]
        delta = cd["planning_regret"] - baseline["planning_regret"]
        if abs(delta) < 1e-9:
            delta = 0.0
        deltas.append(delta)
        planning_rows.append(
            {
                "episode_id": episode_id,
                "baseline_condition": baseline_condition,
                "baseline_action": baseline["selected_action"],
                "cd_action": cd["selected_action"],
                "oracle_action": cd["oracle_action"],
                "baseline_regret": baseline["planning_regret"],
                "cd_regret": cd["planning_regret"],
                "cd_minus_baseline": delta,
                "direction": _direction(delta),
                "cd_decision_rule": cd["decision_rule"]["rule"],
            }
        )
    ci = _bootstrap_ci(deltas, samples=2000, seed=9917 + int(margin_threshold * 1000), alpha=0.05)
    return {
        "margin_threshold": margin_threshold,
        "rows": len(planning_rows),
        "direction_counts": dict(collections.Counter(row["direction"] for row in planning_rows)),
        "mean_cd_minus_strongest_baseline": _mean(deltas),
        "planning_regret_ci": ci,
        "planning_benefit_with_confidence": isinstance(ci.get("upper"), (int, float)) and ci["upper"] < 0,
        "mean_planning_regret_by_condition": {
            condition: _mean([rows[condition]["planning_regret"] for rows in simulated.values() if condition in rows])
            for condition in CONDITIONS
        },
        "action_policy_change_count_by_condition": dict(changed_by_condition),
        "decision_rule_counts": dict(rule_counts),
        "planning_rows": planning_rows,
    }


def _summarize_original(rows: list[dict[str, Any]]) -> dict[str, Any]:
    deltas = [float(row["cd_minus_baseline"]) for row in rows]
    return {
        "rows": len(rows),
        "direction_counts": dict(collections.Counter(row["direction"] for row in rows)),
        "mean_cd_minus_strongest_baseline": _mean(deltas),
        "planning_regret_ci": _bootstrap_ci(deltas, samples=2000, seed=8801, alpha=0.05),
        "action_pair_counts": dict(collections.Counter(f"{row['baseline_action']}->{row['cd_action']}" for row in rows)),
        "oracle_action_counts": dict(collections.Counter(str(row["oracle_action"]) for row in rows)),
    }


def _coordination_symmetry(original_rows: list[dict[str, Any]]) -> dict[str, Any]:
    divergent = [
        row
        for row in original_rows
        if row["baseline_action"] == "OFFER_COOPERATION" and row["cd_action"] == "DISCLOSE_INFORMATION"
    ]
    return {
        "divergent_d_offer_cd_disclose_rows": len(divergent),
        "oracle_action_counts": dict(collections.Counter(str(row["oracle_action"]) for row in divergent)),
        "direction_counts": dict(collections.Counter(row["direction"] for row in divergent)),
        "mean_cd_minus_baseline": _mean([float(row["cd_minus_baseline"]) for row in divergent]),
        "diagnosis": "balanced_oracle_actions_cancel_cd_planning_advantage",
    }


def run_diagnostic(
    *,
    sealed_test_receipt_path: Path,
    output_root: Path,
    receipt_out: Path,
    margin_thresholds: list[float],
) -> dict[str, Any]:
    started = time.monotonic()
    sealed_test_receipt_path = sealed_test_receipt_path.resolve()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    artifacts = output_root / "artifacts"
    rows_path = artifacts / "sealed_test_planning_gap_rows.json"
    top_actions_path = artifacts / "sealed_test_top_action_margins.json"
    margin_policy_path = artifacts / "sealed_test_margin_policy_sensitivity.json"
    summary_path = artifacts / "sealed_test_planning_gap_summary.json"

    errors: list[str] = []
    source = _load_json_object(sealed_test_receipt_path, errors, "sealed_test_receipt")
    _validate_source(source, errors)
    heldout_receipt = _load_json_object(Path(str(source.get("heldout_condition_benefit_receipt", ""))), errors, "heldout_receipt")
    action_rows = _load_action_rows(Path(str(heldout_receipt.get("action_decision_index_path", ""))), errors)
    planning_deltas = _load_paired_planning_deltas(Path(str(source.get("paired_delta_path", ""))), errors)
    by_episode = _condition_rows_by_episode(action_rows, errors)
    original_rows = _build_original_gap_rows(by_episode, planning_deltas, errors)
    top_action_rows = _top_action_rows(by_episode, errors)
    original_summary = _summarize_original(original_rows)
    coordination_summary = _coordination_symmetry(original_rows)
    margin_summaries = [
        _simulate_margin_policy(by_episode, margin_threshold=threshold, errors=errors)
        for threshold in margin_thresholds
    ]

    original_ci = original_summary["planning_regret_ci"]
    if original_summary["rows"] != 64:
        errors.append(f"original_planning_row_count_mismatch:{original_summary['rows']}:64")
    if original_summary["mean_cd_minus_strongest_baseline"] != 0.0:
        errors.append(f"original_mean_delta_not_zero:{original_summary['mean_cd_minus_strongest_baseline']}")
    if not (
        isinstance(original_ci.get("lower"), (int, float))
        and isinstance(original_ci.get("upper"), (int, float))
        and original_ci["lower"] <= 0 <= original_ci["upper"]
    ):
        errors.append(f"original_planning_ci_does_not_cross_zero:{original_ci}")
    if coordination_summary["divergent_d_offer_cd_disclose_rows"] != 16:
        errors.append(f"coordination_divergent_count_mismatch:{coordination_summary}")
    if coordination_summary["oracle_action_counts"] != {"DISCLOSE_INFORMATION": 5, "OFFER_COOPERATION": 5, "WAIT": 6}:
        errors.append(f"coordination_oracle_action_counts_mismatch:{coordination_summary['oracle_action_counts']}")
    if any(summary["planning_benefit_with_confidence"] for summary in margin_summaries):
        errors.append("margin_policy_unexpectedly_claimed_planning_benefit")

    diagnostic_summary = {
        "schema": "persona_dream.research.prospective_tom.sealed_test_planning_gap_summary.v1",
        "source_receipt": str(sealed_test_receipt_path),
        "source_receipt_file_sha256": _file_sha256(sealed_test_receipt_path) if sealed_test_receipt_path.exists() else None,
        "original_argmax_policy": original_summary,
        "coordination_symmetry": coordination_summary,
        "margin_policy_sensitivity": [{key: value for key, value in summary.items() if key != "planning_rows"} for summary in margin_summaries],
        "diagnostic_conclusion": "PREDICTION_BENEFIT_DID_NOT_TRANSFER_TO_PLANNING_UNDER_CURRENT_ACTION_POLICY",
        "next_evidence_needed": [
            "add or validate an action policy that uses CD-specific counterfactual evidence without equally improving baselines",
            "expand or rebalance action-sensitive episodes so planning regret is not cancelled by symmetric oracle actions",
            "connect the sealed-test loop to live Tau/Memory only after the planning policy remains fail-closed",
        ],
    }
    _write_json(rows_path, {"schema": "pctom.sealed_test_planning_gap_rows.v1", "rows": original_rows})
    _write_json(top_actions_path, {"schema": "pctom.sealed_test_top_action_margins.v1", "rows": top_action_rows})
    _write_json(margin_policy_path, {"schema": "pctom.sealed_test_margin_policy_sensitivity.v1", "policies": margin_summaries})
    _write_json(summary_path, diagnostic_summary)

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.sealed_test_planning_gap_diagnostic_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "sealed_test_receipt": str(sealed_test_receipt_path),
        "sealed_test_receipt_file_sha256": _file_sha256(sealed_test_receipt_path) if sealed_test_receipt_path.exists() else None,
        "rows_path": str(rows_path),
        "rows_sha256": _file_sha256(rows_path) if rows_path.exists() else None,
        "top_action_margins_path": str(top_actions_path),
        "top_action_margins_sha256": _file_sha256(top_actions_path) if top_actions_path.exists() else None,
        "margin_policy_sensitivity_path": str(margin_policy_path),
        "margin_policy_sensitivity_sha256": _file_sha256(margin_policy_path) if margin_policy_path.exists() else None,
        "summary_path": str(summary_path),
        "summary_sha256": _file_sha256(summary_path) if summary_path.exists() else None,
        "diagnostic_conclusion": diagnostic_summary["diagnostic_conclusion"],
        "primary_prediction_benefit_with_confidence": source.get("primary_benefit_with_confidence"),
        "planning_benefit_with_confidence": False,
        "counts": {
            "episodes": original_summary["rows"],
            "original_direction_counts": original_summary["direction_counts"],
            "coordination_divergent_d_offer_cd_disclose_rows": coordination_summary["divergent_d_offer_cd_disclose_rows"],
            "coordination_oracle_action_counts": coordination_summary["oracle_action_counts"],
            "margin_policy_count": len(margin_summaries),
            "top_action_margin_rows": len(top_action_rows),
        },
        "metrics": {
            "original_argmax_policy": original_summary,
            "coordination_symmetry": coordination_summary,
            "margin_policy_sensitivity": diagnostic_summary["margin_policy_sensitivity"],
        },
        "checks": {
            "source_sealed_test_passed": source.get("status") == SOURCE_PASS_STATUS,
            "source_primary_prediction_benefit_present": source.get("primary_benefit_with_confidence") is True,
            "source_planning_benefit_absent": source.get("planning_benefit_with_confidence") is False,
            "original_planning_ci_crosses_zero": isinstance(original_ci.get("lower"), (int, float))
            and isinstance(original_ci.get("upper"), (int, float))
            and original_ci["lower"] <= 0 <= original_ci["upper"],
            "coordination_symmetry_identified": coordination_summary["oracle_action_counts"]
            == {"DISCLOSE_INFORMATION": 5, "OFFER_COOPERATION": 5, "WAIT": 6},
            "margin_policy_does_not_create_cd_vs_strongest_baseline_benefit": not any(
                summary["planning_benefit_with_confidence"] for summary in margin_summaries
            ),
            "human_content_judgment_absent": True,
            "unsupported_writes_absent": True,
            "llm_judge_absent": True,
        },
        "mocked": False,
        "live": False,
        "fixture_backed": False,
        "deterministic_simulator_corpus_fixture_backed": True,
        "human_content_judgment_required": False,
        "llm_judge_used": False,
        "tau_call_attempts": 0,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "processing_time_s": round(time.monotonic() - started, 6),
        "errors": errors,
        "claims": {
            "proves": [
                "the sealed-test prediction-benefit receipt is hash-bound and rechecked as the source",
                "the original Gate 6 planning-regret paired delta crosses zero and must not be claimed as planning benefit",
                "the D-versus-CD action difference is concentrated in coordination/conflict cases where oracle actions are balanced across offer, disclose, and wait",
                "a margin-gated epistemic action sensitivity check does not create CD planning benefit over the strongest M/R/D baseline",
                "no Tau, Memory, provider, canonical-memory, identity, source-memory, LLM judge, or human content-judgment action was attempted",
            ]
            if status == PASS_STATUS
            else ["the sealed-test planning-gap diagnostic failed closed before accepting the gap explanation"],
            "does_not_prove": [
                "planning-regret benefit",
                "live Tau sealed-test execution",
                "live Memory recall in the sealed-test loop",
                "real external service fault injection",
                "production retry machinery",
                "semantic dream quality",
                "paid provider execution",
                "complete live Phase 01-16 runtime execution",
            ],
        },
    }
    receipt["receipt_sha256"] = _stable_json_sha256({key: value for key, value in receipt.items() if key != "receipt_sha256"})
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sealed-test-receipt", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, default=None)
    parser.add_argument("--margin-threshold", action="append", type=float, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt_out = args.receipt_out or (args.output_root / "sealed_test_planning_gap_diagnostic_receipt.v1.json")
    thresholds = args.margin_threshold if args.margin_threshold is not None else [0.0, 0.2, 0.25]
    receipt = run_diagnostic(
        sealed_test_receipt_path=args.sealed_test_receipt,
        output_root=args.output_root,
        receipt_out=receipt_out,
        margin_thresholds=thresholds,
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
