#!/usr/bin/env python3
"""Run a confidence-gated epistemic planning intervention over full64 live Tau artifacts."""
from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.util
import json
import random
import statistics
import time
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[3]
RESEARCH_ROOT = ROOT / "research" / "prospective-tom"
GATE6_SCRIPT = RESEARCH_ROOT / "scripts" / "run_action_selection_trial.py"
DIST_SCRIPT = SCRIPT_DIR / "run_live_tau_distributional_planning_intervention.py"
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
PASS_STATUS = "PASS_LIVE_TAU_PCTOM_CONFIDENCE_GATED_PLANNING_INTERVENTION"
BLOCKED_STATUS = "BLOCKED_LIVE_TAU_PCTOM_CONFIDENCE_GATED_PLANNING_INTERVENTION"
POLICY_ID = "confidence_gated_epistemic_action.v1"
DEFAULT_CONFIDENCE_THRESHOLD = 0.35


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot_load_module:{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dist = _load_module(DIST_SCRIPT, "pctom_distributional_planning_intervention")


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


def _mapped_action_mass(distribution: list[dict[str, Any]]) -> dict[str, float]:
    mapped = {action: 0.0 for action in ACTION_VOCABULARY}
    for item in distribution:
        mapped[dist._counterpart_to_agent_action(str(item["value"]))] += float(item["probability"])
    return mapped


def _select_confidence_gated_action(mapped_mass: dict[str, float], threshold: float) -> tuple[str, dict[str, Any]]:
    top_action = max(ACTION_VOCABULARY, key=lambda action: (mapped_mass[action], -ACTION_VOCABULARY.index(action)))
    top_mass = mapped_mass[top_action]
    sorted_masses = sorted(mapped_mass.values(), reverse=True)
    margin = sorted_masses[0] - (sorted_masses[1] if len(sorted_masses) > 1 else 0.0)
    if top_mass < threshold:
        return "ASK_CLARIFYING_QUESTION", {
            "rule": "LOW_CONFIDENCE_EPISTEMIC_ACTION",
            "top_mapped_action": top_action,
            "top_mapped_action_probability": top_mass,
            "mapped_action_margin": margin,
            "confidence_threshold": threshold,
        }
    return top_action, {
        "rule": "CONFIDENT_TOP_MAPPED_ACTION",
        "top_mapped_action": top_action,
        "top_mapped_action_probability": top_mass,
        "mapped_action_margin": margin,
        "confidence_threshold": threshold,
    }


def _build_action_selection(
    *,
    episode: dict[str, Any],
    condition: str,
    base_receipt_sha256: str,
    commitment_bundle: dict[str, Any],
    scoring_receipt: dict[str, Any],
    outcome: dict[str, Any],
    scoring_receipt_sha256: str,
    outcome_reveal_sha256: str,
    confidence_threshold: float,
    errors: list[str],
) -> dict[str, Any]:
    distribution = dist._predicted_distribution(commitment_bundle, errors, f"{outcome.get('episode_id')}_{condition}")
    mapped_mass = _mapped_action_mass(distribution)
    selected_action, decision_rule = _select_confidence_gated_action(mapped_mass, confidence_threshold)
    actual_next_action = outcome.get("actual_next_action")
    policy = episode.get("counterpart_policy") if isinstance(episode.get("counterpart_policy"), dict) else {}
    expected_actual = policy.get("expected_actual_next_action")
    if actual_next_action != expected_actual:
        errors.append(f"outcome_policy_mismatch:{actual_next_action}:{expected_actual}")
    oracle_action = dist._counterpart_to_agent_action(str(actual_next_action))
    options = [dist._with_utility(action, oracle_action) for action in ACTION_VOCABULARY]
    option_by_action = {option["action"]: option for option in options}
    selected_utility = option_by_action[selected_action]["expected_utility"]
    oracle_utility = option_by_action[oracle_action]["expected_utility"]
    planning_regret = max(0.0, oracle_utility - selected_utility)
    if abs(planning_regret) < 1e-9:
        planning_regret = 0.0
    selected_components = option_by_action[selected_action]
    return {
        "schema": "persona_dream.research.prospective_tom.action_selection.v1",
        "episode_id": outcome.get("episode_id"),
        "prediction_id": outcome.get("prediction_id"),
        "outcome_id": outcome.get("outcome_id"),
        "selected_action": selected_action,
        "scoring_receipt_sha256": scoring_receipt_sha256,
        "outcome_reveal_sha256": outcome_reveal_sha256,
        "action_options": options,
        "oracle_policy": {
            "action": oracle_action,
            "expected_utility": oracle_utility,
            "policy_reference": "deterministic_simulator_policy.v1",
            "counterpart_policy_id": policy.get("policy_id"),
            "actual_next_action": actual_next_action,
            "llm_judge_used": False,
        },
        "planning_regret": planning_regret,
        "realized_outcome": {
            "task_reward": selected_components["expected_task_reward"],
            "social_cost": selected_components["expected_social_cost"],
            "information_gain": selected_components["expected_information_gain"],
            "observed_counterpart_action": actual_next_action,
        },
        "decision_basis": {
            "prediction_id": outcome.get("prediction_id"),
            "condition": condition,
            "scoring_status": scoring_receipt.get("status"),
            "intervention_policy": POLICY_ID,
            "confidence_threshold": confidence_threshold,
            "decision_rule": decision_rule,
            "mapped_agent_action_probability": mapped_mass,
            "predicted_next_action_distribution": distribution,
            "mapping_rule_id": "counterpart_action_to_constrained_agent_action.v1",
            "base_receipt_sha256": base_receipt_sha256,
            "human_content_judgment_required": False,
        },
        "canonical_memory_write": False,
    }


def _direction(delta: float) -> str:
    if delta < -1e-9:
        return "BENEFIT"
    if delta > 1e-9:
        return "HARM"
    return "TIE"


def _summarize(action_rows: list[dict[str, Any]], original_rows: dict[tuple[str, str], dict[str, Any]], *, bootstrap_samples: int, bootstrap_seed: int, alpha: float) -> dict[str, Any]:
    valid_rows = [row for row in action_rows if row.get("status") == "PASS_TOM_ACTION_SELECTION"]
    by_episode: dict[str, dict[str, dict[str, Any]]] = collections.defaultdict(dict)
    for row in valid_rows:
        by_episode[str(row["episode_id"])][str(row["condition"])] = row

    planning_rows: list[dict[str, Any]] = []
    deltas: list[float] = []
    changed_by_condition: collections.Counter[str] = collections.Counter()
    changed_by_family: collections.Counter[str] = collections.Counter()
    rule_counts: collections.Counter[str] = collections.Counter()

    for row in valid_rows:
        key = (str(row.get("episode_id")), str(row.get("condition")))
        original = original_rows.get(key, {})
        changed = row.get("selected_action") != original.get("selected_action")
        if changed:
            changed_by_condition[str(row.get("condition"))] += 1
            changed_by_family[str(row.get("family"))] += 1
        row["original_selected_action"] = original.get("selected_action")
        row["original_planning_regret"] = original.get("planning_regret")
        row["selected_action_changed_from_original"] = changed
        if isinstance(row.get("decision_rule"), str):
            rule_counts[str(row["decision_rule"])] += 1

    for episode_id in sorted(by_episode):
        rows = by_episode[episode_id]
        if set(rows) != set(CONDITIONS):
            continue
        baseline_condition = min(BASELINE_CONDITIONS, key=lambda condition: float(rows[condition]["planning_regret"]))
        cd_row = rows["CD"]
        baseline_row = rows[baseline_condition]
        delta = float(cd_row["planning_regret"]) - float(baseline_row["planning_regret"])
        if abs(delta) < 1e-9:
            delta = 0.0
        deltas.append(delta)
        planning_rows.append(
            {
                "episode_id": episode_id,
                "family": cd_row.get("family"),
                "baseline_condition": baseline_condition,
                "cd_planning_regret": cd_row.get("planning_regret"),
                "baseline_planning_regret": baseline_row.get("planning_regret"),
                "cd_minus_baseline_planning_regret": delta,
                "direction": _direction(delta),
                "cd_selected_action": cd_row.get("selected_action"),
                "baseline_selected_action": baseline_row.get("selected_action"),
                "cd_decision_rule": cd_row.get("decision_rule"),
                "baseline_decision_rule": baseline_row.get("decision_rule"),
                "cd_original_selected_action": cd_row.get("original_selected_action"),
                "baseline_original_selected_action": baseline_row.get("original_selected_action"),
            }
        )
    planning_regret_ci = _bootstrap_ci(deltas, samples=bootstrap_samples, seed=bootstrap_seed, alpha=alpha)
    return {
        "planning_rows": planning_rows,
        "delta_values": deltas,
        "summary": {
            "planning_rows": len(planning_rows),
            "direction_counts": dict(collections.Counter(row["direction"] for row in planning_rows)),
            "mean_cd_minus_baseline_planning_regret": _mean(deltas),
            "planning_regret_ci": planning_regret_ci,
            "planning_benefit_with_confidence": _planning_benefit_with_confidence(planning_regret_ci),
            "action_policy_change_count": sum(changed_by_condition.values()),
            "action_policy_change_count_by_condition": dict(changed_by_condition),
            "action_policy_change_count_by_family": dict(changed_by_family),
            "decision_rule_counts": dict(rule_counts),
            "nonzero_planning_delta_count": sum(1 for row in planning_rows if row["direction"] != "TIE"),
            "nonzero_planning_delta_families": sorted({str(row.get("family")) for row in planning_rows if row["direction"] != "TIE"}),
        },
    }


def run_intervention(
    *,
    base_root: Path,
    output_root: Path,
    receipt_out: Path,
    confidence_threshold: float,
    bootstrap_samples: int,
    bootstrap_seed: int,
    alpha: float,
) -> dict[str, Any]:
    started = time.monotonic()
    errors: list[str] = []
    gate6 = _load_module(GATE6_SCRIPT, "pctom_gate6_action_selection")
    base_root = base_root.resolve()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()

    base_receipt_path = base_root / "live_tau_sealed_test_replication_receipt.v1.json"
    base_receipt = dist._load_json(base_receipt_path, errors, "base_full64_receipt")
    base_receipt = base_receipt if isinstance(base_receipt, dict) else {}
    dist._validate_base(base_receipt, errors)
    base_receipt_sha256 = _file_sha256(base_receipt_path) if base_receipt_path.exists() else None

    comparison_root = base_root / "live_tau_sealed_test_condition_comparison"
    action_root = base_root / "live_tau_sealed_test_action_selection"
    case_index_path = comparison_root / "artifacts" / "live_condition_case_index.json"
    corpus_path = comparison_root / "artifacts" / "social_episode_corpus.v1.json"
    original_action_index_path = action_root / "artifacts" / "live_condition_action_decisions.json"
    case_index = dist._load_json(case_index_path, errors, "case_index")
    corpus = dist._load_json(corpus_path, errors, "corpus")
    original_action_index = dist._load_json(original_action_index_path, errors, "original_action_index")
    episodes = dist._episode_index(corpus, errors)
    if not isinstance(case_index, list):
        errors.append("case_index_not_list")
        case_index = []
    if not isinstance(original_action_index, list):
        errors.append("original_action_index_not_list")
        original_action_index = []
    original_rows = {
        (str(row.get("episode_id")), str(row.get("condition"))): row
        for row in original_action_index
        if isinstance(row, dict)
    }

    action_rows: list[dict[str, Any]] = []
    decision_counts = {condition: 0 for condition in CONDITIONS}
    regret_counts = {condition: 0 for condition in CONDITIONS}
    regrets = {condition: [] for condition in CONDITIONS}
    individual_status_counts: dict[str, int] = {}

    for row_idx, row in enumerate(case_index):
        if not isinstance(row, dict):
            errors.append(f"case_index_{row_idx}_not_object")
            continue
        condition = row.get("condition")
        episode_id = row.get("episode_id")
        if condition not in CONDITIONS:
            errors.append(f"case_index_{row_idx}_invalid_condition:{condition}")
            continue
        if episode_id not in episodes:
            errors.append(f"case_index_{row_idx}_episode_missing:{episode_id}")
            continue
        if row.get("tau_live_call_performed") is not True or row.get("tau_status") != "PASS":
            errors.append(f"case_index_{row_idx}_tau_not_pass:{row.get('tau_status')}:{row.get('tau_live_call_performed')}")
            continue
        statuses = row.get("statuses") if isinstance(row.get("statuses"), dict) else {}
        if statuses.get("gate5") != "PASS_TOM_SCORING_RECEIPT":
            errors.append(f"case_index_{row_idx}_gate5_not_pass:{statuses.get('gate5')}")
            continue

        case_root = Path(str(row.get("case_root", "")))
        receipt_root = Path(str(row.get("receipt_root", "")))
        commitment_path = case_root / "tom_prediction_commitment_bundle.json"
        outcome_path = case_root / "tom_outcome_reveal.json"
        scoring_path = receipt_root / "gate5_scoring_receipt.json"
        case_errors: list[str] = []
        commitment_bundle = dist._load_json(commitment_path, case_errors, "commitment_bundle")
        outcome = dist._load_json(outcome_path, case_errors, "outcome_reveal")
        scoring_receipt = dist._load_json(scoring_path, case_errors, "scoring_receipt")
        if not isinstance(commitment_bundle, dict) or not isinstance(outcome, dict) or not isinstance(scoring_receipt, dict):
            errors.extend(f"{episode_id}:{condition}:{error}" for error in case_errors)
            continue

        action_selection = _build_action_selection(
            episode=episodes[episode_id],
            condition=str(condition),
            base_receipt_sha256=str(base_receipt_sha256),
            commitment_bundle=commitment_bundle,
            scoring_receipt=scoring_receipt,
            outcome=outcome,
            scoring_receipt_sha256=_stable_json_sha256(scoring_receipt),
            outcome_reveal_sha256=_stable_json_sha256(outcome),
            confidence_threshold=confidence_threshold,
            errors=case_errors,
        )
        out_case_root = output_root / "artifacts" / "cases" / str(episode_id) / str(condition)
        out_receipt_root = output_root / "receipts" / "cases" / str(episode_id) / str(condition)
        action_path = out_case_root / "action_selection.json"
        gate6_receipt_path = out_receipt_root / "gate6_action_selection_receipt.json"
        _write_json(action_path, action_selection)
        gate6_errors, derived = gate6._check_action_selection(corpus_path, scoring_path, outcome_path, action_path)
        all_case_errors = case_errors + gate6_errors
        gate6_status = "PASS_TOM_ACTION_SELECTION" if not all_case_errors else "BLOCKED_TOM_ACTION_SELECTION"
        individual_status_counts[gate6_status] = individual_status_counts.get(gate6_status, 0) + 1
        gate6_receipt = {
            "schema": "persona_dream.research.prospective_tom.action_selection_receipt.v1",
            "created_at": _now_iso(),
            "status": gate6_status,
            "base_receipt_path": str(base_receipt_path),
            "base_receipt_sha256": base_receipt_sha256,
            "corpus_path": str(corpus_path),
            "scoring_receipt_path": str(scoring_path),
            "outcome_reveal_path": str(outcome_path),
            "action_selection_path": str(action_path),
            "receipt_path": str(gate6_receipt_path),
            "episode_id": episode_id,
            "condition": condition,
            "errors": all_case_errors,
            "counts": derived["counts"],
            "checks": derived["checks"],
            "metrics": derived["metrics"],
            "mocked": False,
            "live": True,
            "fixture_backed": False,
            "live_tau_originated_case_consumed": True,
            "deterministic_simulator_corpus_fixture_backed": True,
            "human_content_judgment_required": False,
            "tau_call_attempts": 0,
            "memory_write_attempts": 0,
            "provider_call_attempts": 0,
            "canonical_memory_write_attempts": 0,
            "identity_write_attempts": 0,
            "source_memory_write_attempts": 0,
        }
        _write_json(gate6_receipt_path, gate6_receipt)
        family = episodes[str(episode_id)].get("scenario_family")
        if gate6_status != "PASS_TOM_ACTION_SELECTION":
            errors.append(f"gate6_case_blocked:{episode_id}:{condition}:{all_case_errors}")
        else:
            decision_counts[str(condition)] += 1
            regret_counts[str(condition)] += 1
            regret = gate6_receipt.get("metrics", {}).get("planning_regret")
            if isinstance(regret, (int, float)) and not isinstance(regret, bool):
                regrets[str(condition)].append(float(regret))
        action_rows.append(
            {
                "episode_id": episode_id,
                "family": family,
                "condition": condition,
                "case_root": str(out_case_root),
                "receipt_root": str(out_receipt_root),
                "source_case_root": str(case_root),
                "source_receipt_root": str(receipt_root),
                "action_selection_path": str(action_path),
                "gate6_receipt_path": str(gate6_receipt_path),
                "status": gate6_status,
                "selected_action": action_selection.get("selected_action"),
                "oracle_action": action_selection.get("oracle_policy", {}).get("action"),
                "planning_regret": action_selection.get("planning_regret"),
                "intervention_policy": POLICY_ID,
                "confidence_threshold": confidence_threshold,
                "decision_rule": action_selection.get("decision_basis", {}).get("decision_rule", {}).get("rule"),
                "errors": all_case_errors,
            }
        )

    for condition in CONDITIONS:
        if decision_counts[condition] != 64:
            errors.append(f"action_decisions_per_condition_mismatch:{condition}:{decision_counts[condition]}:64")
        if regret_counts[condition] != 64:
            errors.append(f"planning_regret_scores_per_condition_mismatch:{condition}:{regret_counts[condition]}:64")

    summary_payload = _summarize(
        action_rows,
        original_rows,
        bootstrap_samples=bootstrap_samples,
        bootstrap_seed=bootstrap_seed,
        alpha=alpha,
    )
    intervention_summary = summary_payload["summary"]
    if intervention_summary["planning_rows"] != 64:
        errors.append(f"planning_rows_count_mismatch:{intervention_summary['planning_rows']}:64")
    if intervention_summary["nonzero_planning_delta_count"] <= 0:
        errors.append("intervention_nonzero_planning_delta_count_zero")
    planning_benefit_with_confidence = intervention_summary["planning_benefit_with_confidence"]
    harm_only = (
        intervention_summary["direction_counts"].get("HARM", 0) > 0
        and intervention_summary["direction_counts"].get("BENEFIT", 0) == 0
    )

    base_is_full64_live_tau = base_receipt.get("full_64_episode_replication") is True and base_receipt.get("live") is True
    live_tau_artifacts_consumed = base_is_full64_live_tau and len(action_rows) > 0
    status = PASS_STATUS if not errors else BLOCKED_STATUS
    decision_index_path = output_root / "artifacts" / "confidence_gated_action_decisions.json"
    planning_rows_path = output_root / "artifacts" / "confidence_gated_planning_rows.json"
    summary_path = output_root / "artifacts" / "confidence_gated_planning_summary.json"
    _write_json(decision_index_path, {"schema": "pctom.confidence_gated_action_decisions.v1", "rows": action_rows})
    _write_json(planning_rows_path, {"schema": "pctom.confidence_gated_planning_rows.v1", "rows": summary_payload["planning_rows"]})
    _write_json(
        summary_path,
        {
            "schema": "pctom.confidence_gated_planning_intervention_summary.v1",
            "intervention_policy": POLICY_ID,
            "confidence_threshold": confidence_threshold,
            "summary": intervention_summary,
        },
    )

    receipt = {
        "schema": "pctom.live_tau_confidence_gated_planning_intervention_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "base_root": str(base_root),
        "base_receipt": str(base_receipt_path),
        "base_receipt_sha256": base_receipt_sha256,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "decision_index": str(decision_index_path),
        "decision_index_sha256": _file_sha256(decision_index_path) if decision_index_path.exists() else None,
        "planning_rows_path": str(planning_rows_path),
        "planning_rows_sha256": _file_sha256(planning_rows_path) if planning_rows_path.exists() else None,
        "summary_path": str(summary_path),
        "summary_sha256": _file_sha256(summary_path) if summary_path.exists() else None,
        "conditions": list(CONDITIONS),
        "action_set": list(ACTION_VOCABULARY),
        "intervention_policy": POLICY_ID,
        "confidence_threshold": confidence_threshold,
        "oracle_policy_reference": "deterministic_simulator_policy.v1",
        "llm_judge_used": False,
        "errors": errors,
        "counts": {
            "base_tau_call_attempts": base_receipt.get("counts", {}).get("tau_call_attempts")
            if isinstance(base_receipt.get("counts"), dict)
            else None,
            "base_cases": base_receipt.get("counts", {}).get("cases") if isinstance(base_receipt.get("counts"), dict) else None,
            "base_episodes_consumed": base_receipt.get("counts", {}).get("episodes_consumed")
            if isinstance(base_receipt.get("counts"), dict)
            else None,
            "cases_seen": len(case_index),
            "action_cases_written": len(action_rows),
            "individual_status_counts": individual_status_counts,
            "action_decisions_per_condition": decision_counts,
            "planning_regret_scores_per_condition": regret_counts,
            "action_policy_change_count": intervention_summary["action_policy_change_count"],
            "action_policy_change_count_by_condition": intervention_summary["action_policy_change_count_by_condition"],
            "action_policy_change_count_by_family": intervention_summary["action_policy_change_count_by_family"],
            "decision_rule_counts": intervention_summary["decision_rule_counts"],
            "planning_direction_counts": intervention_summary["direction_counts"],
            "nonzero_planning_delta_count": intervention_summary["nonzero_planning_delta_count"],
        },
        "metrics": {
            "mean_planning_regret_by_condition": {condition: _mean(regrets[condition]) for condition in CONDITIONS},
            "planning_regret_delta_vs_strongest_baseline": {
                "mean_cd_minus_baseline": intervention_summary["mean_cd_minus_baseline_planning_regret"],
                "confidence_interval": intervention_summary["planning_regret_ci"],
                "direction_counts": intervention_summary["direction_counts"],
            },
            "nonzero_planning_delta_families": intervention_summary["nonzero_planning_delta_families"],
            "planning_benefit_with_confidence": planning_benefit_with_confidence,
            "belief_prediction_benefit_kept_separate_from_planning_benefit": True,
        },
        "checks": {
            "base_is_full64_live_tau": base_is_full64_live_tau,
            "base_receipt_hash_recomputed": isinstance(base_receipt_sha256, str) and base_receipt_sha256.startswith("sha256:"),
            "conditions_represented": all(decision_counts[condition] == 64 for condition in CONDITIONS),
            "reward_or_regret_scores_recomputed": all(regret_counts[condition] == 64 for condition in CONDITIONS),
            "intervention_policy_named": POLICY_ID,
            "intervention_produces_non_tied_planning_delta": intervention_summary["nonzero_planning_delta_count"] > 0,
            "planning_benefit_not_claimed_when_harm_only": not harm_only or planning_benefit_with_confidence is False,
            "belief_prediction_benefit_kept_separate_from_planning_benefit": True,
            "human_content_judgment_absent": True,
            "unsupported_writes_absent": True,
            "llm_judge_absent": True,
        },
        "mocked": False,
        "live": live_tau_artifacts_consumed,
        "fixture_backed": False,
        "live_tau_originated_artifacts_consumed": live_tau_artifacts_consumed,
        "live_tau_reexecuted": False,
        "deterministic_simulator_corpus_fixture_backed": live_tau_artifacts_consumed,
        "human_content_judgment_required": False,
        "tau_call_attempts": 0,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "processing_time_s": round(time.monotonic() - started, 6),
        "claims": {
            "proves": [
                "a deterministic confidence-gated epistemic action policy consumed full64 live Tau M/R/D/CD artifacts",
                "the intervention produced non-tied CD-vs-baseline planning deltas",
                "all intervention decisions were rescored by Gate 6 against deterministic simulator oracle policy",
                "planning benefit was not claimed when the non-tied delta was harmful",
                "no Tau, Memory, provider, canonical memory, identity, source-memory, LLM judge, or human content-judgment action was attempted",
            ]
            if status == PASS_STATUS
            else [
                "the confidence-gated planning intervention failed closed before claiming non-tied planning-intervention evidence",
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
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    parser.add_argument("--confidence-threshold", type=float, default=DEFAULT_CONFIDENCE_THRESHOLD)
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    parser.add_argument("--bootstrap-seed", type=int, default=1702)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt = run_intervention(
        base_root=args.base_root,
        output_root=args.output_root,
        receipt_out=args.receipt_out,
        confidence_threshold=args.confidence_threshold,
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
