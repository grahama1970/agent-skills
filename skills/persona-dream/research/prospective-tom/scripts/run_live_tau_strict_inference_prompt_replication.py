#!/usr/bin/env python3
"""Run live Tau PCTOM-R condition comparison with a strict inference prompt."""
from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.util
import json
import multiprocessing as mp
import random
import statistics
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
RESEARCH_ROOT = ROOT / "research" / "prospective-tom"
LIVE_CONDITION_SCRIPT = RESEARCH_ROOT / "scripts" / "run_live_tau_condition_comparison.py"
ACTION_SELECTION_SCRIPT = RESEARCH_ROOT / "scripts" / "run_live_tau_condition_action_selection.py"
BALANCED_SCRIPT = RESEARCH_ROOT / "scripts" / "run_live_tau_balanced_planning_replication.py"
CONDITIONS = ("M", "R", "D", "CD")
PASS_STATUS = "PASS_LIVE_TAU_PCTOM_STRICT_INFERENCE_PROMPT_REPLICATION"
BLOCKED_STATUS = "BLOCKED_LIVE_TAU_PCTOM_STRICT_INFERENCE_PROMPT_REPLICATION"
POLICY_ID = "strict_inference_prompt_no_template_probabilities.v1"
DEFAULT_SPLIT = "sealed_test"

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


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot_load_module:{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _bootstrap_ci(values: list[float], *, samples: int, seed: int, alpha: float) -> dict[str, Any] | None:
    if not values:
        return None
    rng = random.Random(seed)
    means: list[float] = []
    for _ in range(samples):
        draw = [values[rng.randrange(len(values))] for _ in values]
        means.append(statistics.fmean(draw))
    means.sort()
    lower_idx = max(0, min(len(means) - 1, int((alpha / 2.0) * len(means))))
    upper_idx = max(0, min(len(means) - 1, int((1.0 - alpha / 2.0) * len(means)) - 1))
    return {
        "alpha": alpha,
        "samples": samples,
        "seed": seed,
        "mean": statistics.fmean(values),
        "lower": means[lower_idx],
        "upper": means[upper_idx],
        "bootstrap_distribution_sha256": _stable_json_sha256(means),
    }


def _strict_prompt(live_condition: Any, episode: dict[str, Any], condition: str) -> str:
    episode_id = episode["episode_id"]
    ids = live_condition._ids(episode_id, condition)
    visible = live_condition._visible_packet(episode)
    visible_refs = live_condition._visible_refs(episode)
    targets = live_condition._prediction_targets(episode)
    actions = list(episode.get("allowed_next_actions") or ["UNKNOWN"])
    synthetic_ref = {"scope": "synthetic_counterfactual", "source_id": f"{episode_id}:{condition}:do-policy-alternative"}
    held_fixed = [
        "counterpart_goals",
        "counterpart_preferences",
        "information_access_by_agent",
        "observable_history",
    ]
    truth_distribution = [
        {"value": "TRUE", "probability": "INFER_PROBABILITY"},
        {"value": "FALSE", "probability": "INFER_PROBABILITY"},
        {"value": "UNKNOWN", "probability": "INFER_PROBABILITY"},
    ]
    factual_action_distribution = [
        {"value": action, "probability": "INFER_PROBABILITY"} for action in actions
    ]
    counterfactual_action_distribution = [
        {"value": action, "probability": "INFER_PROBABILITY"} for action in actions
    ] + [{"value": "UNKNOWN", "probability": "INFER_PROBABILITY"}]

    def _belief_record(
        *,
        hypothesis_id: str,
        target: dict[str, Any],
        evidence_refs: list[dict[str, str]],
        counterfactual: bool,
        counterfactual_context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return {
            "hypothesis_id": hypothesis_id,
            "episode_id": episode_id,
            "perspective_order": target["perspective_order"],
            "subject": target["subject"],
            "target": target["target"],
            "mental_state_type": target["mental_state_type"],
            "proposition": target["proposition"],
            "distribution": truth_distribution,
            "evidence_refs": evidence_refs,
            "prediction_horizon": "next_action",
            "counterfactual": counterfactual,
            "counterfactual_context": counterfactual_context,
            "abstain": False,
            "support_status": "supported",
        }

    contract = {
        "task": "Infer one pre-reveal PCTOM-R condition prediction for deterministic scoring.",
        "policy_id": POLICY_ID,
        "condition": condition,
        "condition_instruction": live_condition.CONDITION_INSTRUCTIONS[condition],
        "episode_visible_to_agent": visible,
        "prediction_targets_without_truth_values": targets,
        "allowed_next_actions": actions,
        "required_ids": ids,
        "counterfactual_intervention": {
            "intervention_id": ids["intervention"],
            "episode_id": episode_id,
            "intervened_variable": "counterpart_policy.expected_actual_next_action",
            "intervened_value": "UNKNOWN",
            "synthetic_counterfactual_ref": synthetic_ref,
            "held_fixed": held_fixed,
        },
        "evidence_ref_rules": {
            "visible_refs_allowed_in_branch_source_evidence_refs": visible_refs,
            "visible_refs_allowed_in_prediction_payload_evidence_refs": visible_refs,
            "synthetic_counterfactual_ref_allowed_only_in_counterfactual_distribution_evidence_refs": synthetic_ref,
        },
        "output_skeleton_replace_all_infer_probability_placeholders": {
            "tom_belief_distribution_bundle": {
                "schema": "persona_dream.research.prospective_tom.tom_belief_distribution_bundle.v1",
                "episode_id": episode_id,
                "condition": condition,
                "sealed": True,
                "outcome_visible": False,
                "canonical_memory_write": False,
                "distributions": [
                    _belief_record(
                        hypothesis_id=ids["tom1_factual"],
                        target=targets[0],
                        evidence_refs=visible_refs,
                        counterfactual=False,
                        counterfactual_context=None,
                    ),
                    _belief_record(
                        hypothesis_id=ids["tom2_factual"],
                        target=targets[1],
                        evidence_refs=visible_refs,
                        counterfactual=False,
                        counterfactual_context=None,
                    ),
                    _belief_record(
                        hypothesis_id=ids["tom1_counterfactual"],
                        target=targets[0],
                        evidence_refs=[synthetic_ref],
                        counterfactual=True,
                        counterfactual_context={"intervention_id": ids["intervention"], "synthetic": True},
                    ),
                ],
            },
            "counterfactual_branch_bundle": {
                "schema": "persona_dream.research.prospective_tom.counterfactual_branch_bundle.v1",
                "episode_id": episode_id,
                "condition": condition,
                "outcome_visible": False,
                "canonical_memory_write": False,
                "branches": [
                    {
                        "branch_id": ids["factual_branch"],
                        "episode_id": episode_id,
                        "branch_type": "factual",
                        "synthetic": False,
                        "intervention": None,
                        "source_evidence_refs": visible_refs,
                        "held_fixed": held_fixed,
                        "predicted_bdi_distribution_refs": [ids["tom1_factual"], ids["tom2_factual"]],
                        "predicted_action_distribution": factual_action_distribution,
                        "expected_observation": "The visible social episode continues without revealing hidden evaluator-only truth.",
                        "uncertainty": "INFER_UNCERTAINTY_NUMBER",
                    },
                    {
                        "branch_id": ids["counterfactual_branch"],
                        "episode_id": episode_id,
                        "branch_type": "counterfactual",
                        "synthetic": True,
                        "intervention": {
                            "intervention_id": ids["intervention"],
                            "episode_id": episode_id,
                            "synthetic": True,
                            "intervened_variable": "counterpart_policy.expected_actual_next_action",
                            "intervened_value": "UNKNOWN",
                            "held_fixed": held_fixed,
                            "expected_observation": "The counterpart policy is replaced by an unspecified alternative.",
                        },
                        "source_evidence_refs": visible_refs,
                        "held_fixed": held_fixed,
                        "predicted_bdi_distribution_refs": [ids["tom1_counterfactual"]],
                        "predicted_action_distribution": counterfactual_action_distribution,
                        "expected_observation": "This branch is synthetic and excluded from literal history.",
                        "uncertainty": "INFER_UNCERTAINTY_NUMBER",
                    },
                ],
            },
            "prediction_payload": {
                "schema": "persona_dream.research.prospective_tom.tom_prediction_payload.v1",
                "episode_id": episode_id,
                "condition": condition,
                "outcome_visible": False,
                "belief_distribution_refs": [ids["tom1_factual"], ids["tom2_factual"], ids["tom1_counterfactual"]],
                "branch_refs": [ids["factual_branch"], ids["counterfactual_branch"]],
                "evidence_refs": visible_refs,
                "prediction_horizon": "next_action",
                "predicted_next_action_distribution": factual_action_distribution,
                "abstain": False,
                "condition_method": live_condition.CONDITION_INSTRUCTIONS[condition],
            },
        },
    }
    return (
        "You are producing machine-validated JSON for Persona Dream PCTOM-R.\n"
        "Return one JSON object and no prose.\n"
        "Infer probabilities from the visible episode and condition instruction; do not copy a schema example.\n"
        "Do not use a uniform distribution or a 0.34/0.33/0.33 tie-break pattern unless the visible evidence truly warrants it.\n"
        "Every probability distribution must sum to 1.0 and use numeric probabilities.\n"
        "Do not include hidden_world_state, actual_next_action, ground_truth_tom_labels, outcome, score, or reveal fields.\n"
        "The object must contain exactly these top-level payload objects: tom_belief_distribution_bundle, "
        "counterfactual_branch_bundle, prediction_payload.\n"
        "For each ToM record, include the exact fields required by the persona_dream.research.prospective_tom.tom_belief_distribution_bundle.v1 schema.\n"
        "For the factual branch, set branch_type=factual, synthetic=false, intervention=null, and predicted_action_distribution to your inferred distribution over allowed_next_actions.\n"
        "For the counterfactual branch, set branch_type=counterfactual, synthetic=true, include the supplied intervention, and keep it excluded from literal history.\n"
        "For prediction_payload.predicted_next_action_distribution, use the factual branch distribution.\n\n"
        + json.dumps(contract, indent=2, sort_keys=True)
    )


def _distribution_signature(distribution: list[dict[str, Any]]) -> tuple[float, ...]:
    return tuple(round(float(item.get("probability", 0.0)), 6) for item in distribution if isinstance(item, dict))


def _analyze_cases(case_index: list[dict[str, Any]], errors: list[str]) -> dict[str, Any]:
    template_counter: collections.Counter[str] = collections.Counter()
    top_counter: collections.Counter[str] = collections.Counter()
    action_rows: list[dict[str, Any]] = []
    blocked_case_count = 0
    for row in case_index:
        if not isinstance(row, dict):
            continue
        statuses = row.get("statuses") if isinstance(row.get("statuses"), dict) else {}
        if statuses.get("gate4") != "PASS_TOM_PREDICTION_COMMITMENTS" or statuses.get("gate5") != "PASS_TOM_SCORING_RECEIPT":
            blocked_case_count += 1
            continue
        case_root = Path(str(row.get("case_root", "")))
        bundle = _load_json(case_root / "tom_prediction_commitment_bundle.json", errors, "commitment_bundle")
        outcome = _load_json(case_root / "tom_outcome_reveal.json", errors, "outcome_reveal")
        if not isinstance(bundle, dict) or not isinstance(outcome, dict):
            continue
        commitments = bundle.get("commitments")
        if not isinstance(commitments, list) or not commitments or not isinstance(commitments[0], dict):
            errors.append(f"case_commitment_missing:{case_root}")
            continue
        payload = commitments[0].get("prediction_payload")
        if not isinstance(payload, dict):
            errors.append(f"case_prediction_payload_missing:{case_root}")
            continue
        distribution = payload.get("predicted_next_action_distribution")
        if not isinstance(distribution, list) or not distribution:
            errors.append(f"case_action_distribution_missing:{case_root}")
            continue
        signature = _distribution_signature(distribution)
        is_default_three = signature == (0.34, 0.33, 0.33)
        is_default_two = signature == (0.55, 0.45)
        template = "DEFAULT_3_ACTION_TEMPLATE" if is_default_three else "DEFAULT_2_ACTION_TEMPLATE" if is_default_two else "NON_TEMPLATE"
        template_counter[template] += 1
        top = max(distribution, key=lambda item: float(item.get("probability") or 0.0))
        actual = outcome.get("actual_next_action")
        actual_probability = next((float(item["probability"]) for item in distribution if item.get("value") == actual), 0.0)
        top_counter[str(top.get("value"))] += 1
        action_rows.append(
            {
                "episode_id": row.get("episode_id"),
                "condition": row.get("condition"),
                "template_signature": template,
                "top_predicted_action": top.get("value"),
                "top_probability": float(top.get("probability") or 0.0),
                "actual_next_action": actual,
                "actual_probability": actual_probability,
                "top_correct": top.get("value") == actual,
                "distribution": distribution,
            }
        )
    return {
        "template_counts": dict(template_counter),
        "top_predicted_action_counts": dict(top_counter),
        "action_distribution_rows": action_rows,
        "non_template_distribution_count": template_counter["NON_TEMPLATE"],
        "template_distribution_count": template_counter["DEFAULT_3_ACTION_TEMPLATE"] + template_counter["DEFAULT_2_ACTION_TEMPLATE"],
        "blocked_case_count": blocked_case_count,
    }


def _summarize_planning(action_index: list[dict[str, Any]], balanced: Any, errors: list[str], bootstrap_samples: int, bootstrap_seed: int, alpha: float) -> dict[str, Any]:
    planning_rows = balanced._planning_rows(action_index, errors)
    deltas = [float(row["cd_minus_baseline"]) for row in planning_rows]
    return {
        "planning_rows": planning_rows,
        "episodes": len(planning_rows),
        "families": sorted({row["scenario_family"] for row in planning_rows}),
        "episodes_per_family": dict(collections.Counter(row["scenario_family"] for row in planning_rows)),
        "direction_counts": dict(collections.Counter(row["direction"] for row in planning_rows)),
        "action_switch_count": sum(1 for row in planning_rows if row["action_switched"]),
        "nonzero_delta_count": sum(1 for row in planning_rows if row["cd_minus_baseline"] != 0),
        "oracle_match_transitions": dict(collections.Counter(row["oracle_match_transition"] for row in planning_rows)),
        "mean_cd_minus_baseline": statistics.fmean(deltas) if deltas else None,
        "planning_regret_ci": _bootstrap_ci(deltas, samples=bootstrap_samples, seed=bootstrap_seed, alpha=alpha),
        "planning_benefit_with_confidence": bool(deltas and (_bootstrap_ci(deltas, samples=bootstrap_samples, seed=bootstrap_seed, alpha=alpha) or {}).get("upper", 1.0) < 0),
        "row_pattern_sha256": _stable_json_sha256(
            [
                {
                    "episode_id": row["episode_id"],
                    "baseline_action": row["baseline_action"],
                    "cd_action": row["cd_action"],
                    "delta": row["cd_minus_baseline"],
                    "direction": row["direction"],
                }
                for row in planning_rows
            ]
        ),
    }


def run_strict_replication(
    *,
    output_root: Path,
    receipt_out: Path,
    family_episode_limit: int,
    episodes_per_family: int,
    variant_min: int | None,
    variant_max: int | None,
    model: str | None,
    timeout_s: float,
    outer_timeout_s: float | None,
    bootstrap_samples: int,
    bootstrap_seed: int,
    alpha: float,
) -> dict[str, Any]:
    started = time.monotonic()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    live_condition = _load_module(LIVE_CONDITION_SCRIPT, "pctom_live_tau_condition_comparison")
    action_selection = _load_module(ACTION_SELECTION_SCRIPT, "pctom_live_tau_condition_action_selection")
    balanced = _load_module(BALANCED_SCRIPT, "pctom_balanced_planning")
    errors: list[str] = []

    condition_root = output_root / "live_tau_strict_inference_condition_comparison"
    condition_receipt_path = condition_root / "live_tau_condition_comparison_receipt.v1.json"
    action_root = output_root / "live_tau_strict_inference_action_selection"
    action_receipt_path = action_root / "live_tau_condition_action_selection_receipt.v1.json"
    rows_path = output_root / "artifacts" / "strict_inference_action_distribution_rows.json"
    planning_rows_path = output_root / "artifacts" / "strict_inference_planning_rows.json"
    summary_path = output_root / "artifacts" / "strict_inference_prompt_summary.json"

    original_prompt = live_condition._prompt
    original_selector = live_condition._select_episodes

    def _selector(corpus: dict[str, Any], _limit: int) -> list[dict[str, Any]]:
        return balanced._select_balanced_episodes(
            corpus,
            family_episode_limit,
            variant_min=variant_min,
            variant_max=variant_max,
        )

    def _prompt(episode: dict[str, Any], condition: str) -> str:
        return _strict_prompt(live_condition, episode, condition)

    condition_receipt: dict[str, Any] = {}
    action_receipt: dict[str, Any] = {}

    def _run_condition_once() -> dict[str, Any]:
        try:
            live_condition._prompt = _prompt
            live_condition._select_episodes = _selector
            return live_condition.run_live_comparison(
                output_root=condition_root,
                receipt_out=condition_receipt_path,
                split=DEFAULT_SPLIT,
                episodes_per_family=episodes_per_family,
                episode_limit=family_episode_limit * len(balanced.FAMILIES),
                model=model,
                timeout_s=timeout_s,
            )
        finally:
            live_condition._prompt = original_prompt
            live_condition._select_episodes = original_selector

    if outer_timeout_s is None:
        try:
            condition_receipt = _run_condition_once()
        except Exception as exc:
            errors.append(f"condition_exception:{type(exc).__name__}:{exc}")
    else:
        ctx = mp.get_context("fork")
        queue: Any = ctx.Queue()

        def _child() -> None:
            try:
                queue.put({"ok": True, "receipt": _run_condition_once()})
            except Exception as exc:  # pragma: no cover - child process transport
                queue.put({"ok": False, "error": f"{type(exc).__name__}:{exc}"})

        process = ctx.Process(target=_child)
        process.start()
        process.join(outer_timeout_s)
        if process.is_alive():
            process.terminate()
            process.join(5)
            errors.append(f"strict_inference_outer_timeout_s:{outer_timeout_s}")
        elif not queue.empty():
            result = queue.get()
            if result.get("ok") is True and isinstance(result.get("receipt"), dict):
                condition_receipt = result["receipt"]
            else:
                errors.append(f"condition_child_error:{result.get('error')}")
        else:
            errors.append(f"condition_child_no_result:exitcode:{process.exitcode}")

    if condition_receipt.get("status") != live_condition.PASS_STATUS:
        errors.append(f"condition_status:{condition_receipt.get('status')}")
        errors.extend(f"condition_error:{error}" for error in condition_receipt.get("errors", []))

    if condition_receipt.get("status") == live_condition.PASS_STATUS:
        action_receipt = action_selection.run_bridge(condition_root, action_root, action_receipt_path)
        if action_receipt.get("status") != action_selection.PASS_STATUS:
            errors.append(f"action_selection_status:{action_receipt.get('status')}")
            errors.extend(f"action_selection_error:{error}" for error in action_receipt.get("errors", []))
    else:
        errors.append("action_selection_skipped_without_passed_condition_receipt")

    case_index_value = condition_receipt.get("case_index_path")
    if isinstance(case_index_value, str) and case_index_value:
        case_index = _load_json(Path(case_index_value), errors, "condition_case_index")
        if not isinstance(case_index, list):
            errors.append("condition_case_index_not_list")
            case_index = []
    else:
        errors.append("missing_condition_case_index_path")
        case_index = []
    action_index_value = action_receipt.get("decision_index")
    if isinstance(action_index_value, str) and action_index_value:
        action_index = _load_json(Path(action_index_value), errors, "action_decision_index")
        if not isinstance(action_index, list):
            errors.append("action_decision_index_not_list")
            action_index = []
    else:
        errors.append("missing_action_decision_index_path")
        action_index = []

    distribution_summary = _analyze_cases(case_index, errors)
    planning_summary = _summarize_planning(action_index, balanced, errors, bootstrap_samples, bootstrap_seed, alpha)
    expected_episodes = family_episode_limit * len(balanced.FAMILIES)
    expected_cases = expected_episodes * len(CONDITIONS)
    counts = condition_receipt.get("counts") if isinstance(condition_receipt.get("counts"), dict) else {}
    if condition_receipt.get("tau_call_attempts") != expected_cases:
        errors.append(f"tau_call_attempts_mismatch:{condition_receipt.get('tau_call_attempts')}:{expected_cases}")
    if condition_receipt.get("tau_live_call_performed") != expected_cases:
        errors.append(f"tau_live_call_performed_mismatch:{condition_receipt.get('tau_live_call_performed')}:{expected_cases}")
    if counts.get("cases") != expected_cases:
        errors.append(f"case_count_mismatch:{counts.get('cases')}:{expected_cases}")
    if distribution_summary["non_template_distribution_count"] <= 0:
        errors.append("strict_prompt_no_non_template_action_distributions")
    if set(planning_summary["families"]) != set(balanced.FAMILIES):
        errors.append(f"planning_families_mismatch:{planning_summary['families']}")
    for family in balanced.FAMILIES:
        if planning_summary["episodes_per_family"].get(family) != family_episode_limit:
            errors.append(f"planning_family_count_mismatch:{family}:{planning_summary['episodes_per_family'].get(family)}:{family_episode_limit}")

    _write_json(rows_path, {
        "schema": "persona_dream.research.prospective_tom.strict_inference_action_distribution_rows.v1",
        "rows": distribution_summary["action_distribution_rows"],
    })
    _write_json(planning_rows_path, {
        "schema": "persona_dream.research.prospective_tom.strict_inference_planning_rows.v1",
        "rows": planning_summary["planning_rows"],
    })
    summary = {
        "schema": "persona_dream.research.prospective_tom.strict_inference_prompt_summary.v1",
        "policy_id": POLICY_ID,
        "split": DEFAULT_SPLIT,
        "family_episode_limit": family_episode_limit,
        "episodes_per_family": episodes_per_family,
        "variant_min": variant_min,
        "variant_max": variant_max,
        "distribution_summary": {
            key: value
            for key, value in distribution_summary.items()
            if key != "action_distribution_rows"
        },
        "planning_summary": {key: value for key, value in planning_summary.items() if key != "planning_rows"},
        "condition_receipt_sha256": _file_sha256(condition_receipt_path) if condition_receipt_path.exists() else None,
        "action_receipt_sha256": _file_sha256(action_receipt_path) if action_receipt_path.exists() else None,
    }
    _write_json(summary_path, summary)

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    does_not_prove = [
        "confidence-bounded planning benefit",
        "live Memory recall in the sealed-test loop",
        "permanently deployed external production retry service",
        "complete live Phase 01-16 runtime execution",
        "paid provider execution",
        "video, audio, or semantic dream quality",
    ]
    receipt = {
        "schema": "persona_dream.research.prospective_tom.live_tau_strict_inference_prompt_replication_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "processing_time_s": round(time.monotonic() - started, 3),
        "policy_id": POLICY_ID,
        "split": DEFAULT_SPLIT,
        "family_episode_limit": family_episode_limit,
        "episodes_per_family": episodes_per_family,
        "variant_min": variant_min,
        "variant_max": variant_max,
        "timeout_s": timeout_s,
        "outer_timeout_s": outer_timeout_s,
        "conditions": list(CONDITIONS),
        "condition_receipt": str(condition_receipt_path),
        "condition_receipt_sha256": _file_sha256(condition_receipt_path) if condition_receipt_path.exists() else None,
        "action_receipt": str(action_receipt_path),
        "action_receipt_sha256": _file_sha256(action_receipt_path) if action_receipt_path.exists() else None,
        "summary_path": str(summary_path),
        "summary_sha256": _file_sha256(summary_path) if summary_path.exists() else None,
        "action_distribution_rows_path": str(rows_path),
        "action_distribution_rows_sha256": _file_sha256(rows_path) if rows_path.exists() else None,
        "planning_rows_path": str(planning_rows_path),
        "planning_rows_sha256": _file_sha256(planning_rows_path) if planning_rows_path.exists() else None,
        "mocked": False,
        "live": condition_receipt.get("tau_live_call_performed") == expected_cases,
        "fixture_backed": False,
        "deterministic_simulator_corpus_fixture_backed": True,
        "live_tau_reexecuted": True,
        "live_tau_originated_artifacts_consumed": condition_receipt.get("tau_live_call_performed") == expected_cases
        and action_receipt.get("live_tau_originated_artifacts_consumed") is True,
        "human_content_judgment_required": False,
        "llm_judge_used": False,
        "tau_call_attempts": condition_receipt.get("tau_call_attempts"),
        "tau_live_call_performed": condition_receipt.get("tau_live_call_performed"),
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "counts": {
            "expected_episodes": expected_episodes,
            "expected_cases": expected_cases,
            "cases": len(case_index),
            "action_decisions": len(action_index),
            "non_template_distribution_count": distribution_summary["non_template_distribution_count"],
            "template_distribution_count": distribution_summary["template_distribution_count"],
            "blocked_case_count": distribution_summary["blocked_case_count"],
            "template_counts": distribution_summary["template_counts"],
            "planning_rows": planning_summary["episodes"],
            "episodes_per_family": planning_summary["episodes_per_family"],
            "action_switch_count": planning_summary["action_switch_count"],
            "nonzero_delta_count": planning_summary["nonzero_delta_count"],
            "oracle_match_transitions": planning_summary["oracle_match_transitions"],
        },
        "checks": {
            "condition_receipt_passed": condition_receipt.get("status") == live_condition.PASS_STATUS,
            "action_selection_receipt_passed": action_receipt.get("status") == action_selection.PASS_STATUS,
            "strict_prompt_produced_non_template_distribution": distribution_summary["non_template_distribution_count"] > 0,
            "all_four_families_selected": set(planning_summary["families"]) == set(balanced.FAMILIES),
            "balanced_family_counts": all(
                planning_summary["episodes_per_family"].get(family) == family_episode_limit for family in balanced.FAMILIES
            ),
            "human_content_judgment_absent": True,
            "llm_judge_absent": True,
            "unsupported_writes_absent": True,
        },
        "metrics": summary,
        "planning_benefit_with_confidence": planning_summary["planning_benefit_with_confidence"],
        "errors": errors,
        "claims": {
            "proves": [
                "the strict-inference prompt was executed through live Tau M/R/D/CD condition calls over a balanced four-family sealed-test slice",
                "live Tau condition outputs were sealed before deterministic outcome reveal and scored by Gate 5",
                "Gate 6 action selections and CD-vs-strongest-baseline planning rows were recomputed from the strict prompt outputs",
                "the strict prompt produced at least one non-template action distribution instead of copying the default 0.34/0.33/0.33 pattern",
                "no human content judgment, LLM judge, Memory write, provider call, canonical write, identity write, or source-memory write was attempted",
            ]
            if status == PASS_STATUS
            else [
                "the strict-inference prompt replication failed closed before accepting a strict live planning claim",
            ],
            "does_not_prove": does_not_prove,
        },
    }
    receipt["receipt_sha256"] = _stable_json_sha256({key: value for key, value in receipt.items() if key != "receipt_sha256"})
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, default=None)
    parser.add_argument("--family-episode-limit", type=int, default=2)
    parser.add_argument("--episodes-per-family", type=int, default=24)
    parser.add_argument("--variant-min", type=int, default=None)
    parser.add_argument("--variant-max", type=int, default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout-s", type=float, default=240.0)
    parser.add_argument("--outer-timeout-s", type=float, default=None)
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260727)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt_out = args.receipt_out or (args.output_root / "live_tau_strict_inference_prompt_replication_receipt.v1.json")
    receipt = run_strict_replication(
        output_root=args.output_root,
        receipt_out=receipt_out,
        family_episode_limit=args.family_episode_limit,
        episodes_per_family=args.episodes_per_family,
        variant_min=args.variant_min,
        variant_max=args.variant_max,
        model=args.model,
        timeout_s=args.timeout_s,
        outer_timeout_s=args.outer_timeout_s,
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
