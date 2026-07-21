#!/usr/bin/env python3
"""Score Gate 6 actions over repeated live Tau M/R/D/CD condition artifacts."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import statistics
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
RESEARCH_ROOT = ROOT / "research" / "prospective-tom"
GATE6_SCRIPT = RESEARCH_ROOT / "scripts" / "run_action_selection_trial.py"
CONDITIONS = ("M", "R", "D", "CD")
ACTION_VOCABULARY = (
    "ASK_CLARIFYING_QUESTION",
    "WAIT",
    "DISCLOSE_INFORMATION",
    "OFFER_COOPERATION",
    "SET_BOUNDARY",
    "ACT_INDEPENDENTLY",
    "ABSTAIN",
)
PASS_STATUS = "PASS_LIVE_TAU_PCTOM_CONDITION_ACTION_SELECTION"
BLOCKED_STATUS = "BLOCKED_LIVE_TAU_PCTOM_CONDITION_ACTION_SELECTION"


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


def _episode_index(corpus: Any, errors: list[str]) -> dict[str, dict[str, Any]]:
    if not isinstance(corpus, dict) or not isinstance(corpus.get("episodes"), list):
        errors.append("corpus_episodes_missing")
        return {}
    episodes: dict[str, dict[str, Any]] = {}
    for idx, episode in enumerate(corpus["episodes"]):
        if not isinstance(episode, dict) or not isinstance(episode.get("episode_id"), str):
            errors.append(f"corpus_episode_{idx}_invalid")
            continue
        episodes[episode["episode_id"]] = episode
    return episodes


def _validate_base(base_root: Path, errors: list[str]) -> dict[str, Any]:
    receipt_path = base_root / "live_tau_condition_comparison_receipt.v1.json"
    receipt = _load_json(receipt_path, errors, "base_receipt")
    if not isinstance(receipt, dict):
        return {}
    expected = {
        "status": "PASS_LIVE_TAU_PCTOM_CONDITION_COMPARISON",
        "mocked": False,
        "live": True,
        "fixture_backed": False,
        "human_content_judgment_required": False,
        "tau_receipts_hash_bound": True,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
    }
    for key, value in expected.items():
        if receipt.get(key) != value:
            errors.append(f"base_{key}_mismatch:{receipt.get(key)}:{value}")
    if receipt.get("tau_call_attempts", 0) < 16:
        errors.append(f"base_tau_call_attempts_lt_16:{receipt.get('tau_call_attempts')}")
    counts = receipt.get("counts") if isinstance(receipt.get("counts"), dict) else {}
    for key in ("sealed_commitments_per_condition", "deterministic_scores_per_condition"):
        values = counts.get(key)
        if not isinstance(values, dict) or set(values) != set(CONDITIONS):
            errors.append(f"base_{key}_missing_conditions:{values}")
            continue
        for condition in CONDITIONS:
            if not isinstance(values.get(condition), int) or values[condition] < 4:
                errors.append(f"base_{key}_{condition}_lt_4:{values.get(condition)}")
    return receipt


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


def _action_components(action: str, oracle_action: str) -> dict[str, float]:
    if action == oracle_action:
        return {
            "expected_task_reward": 0.8,
            "expected_social_cost": 0.1,
            "expected_information_gain": 0.3,
        }
    if action == "ASK_CLARIFYING_QUESTION":
        return {
            "expected_task_reward": 0.5,
            "expected_social_cost": 0.05,
            "expected_information_gain": 0.3,
        }
    if action == "ABSTAIN":
        return {
            "expected_task_reward": 0.2,
            "expected_social_cost": 0.0,
            "expected_information_gain": 0.1,
        }
    if action == "WAIT":
        return {
            "expected_task_reward": 0.45,
            "expected_social_cost": 0.1,
            "expected_information_gain": 0.1,
        }
    return {
        "expected_task_reward": 0.35,
        "expected_social_cost": 0.25,
        "expected_information_gain": 0.05,
    }


def _with_utility(action: str, oracle_action: str) -> dict[str, Any]:
    option: dict[str, Any] = {
        "action": action,
        "policy_compliant": True,
        "policy_basis": "deterministic_simulator_policy.v1",
    }
    option.update(_action_components(action, oracle_action))
    option["expected_utility"] = (
        option["expected_task_reward"] + option["expected_information_gain"] - option["expected_social_cost"]
    )
    return option


def _top_predicted_counterpart_action(commitment_bundle: dict[str, Any], errors: list[str]) -> tuple[str, float]:
    commitments = commitment_bundle.get("commitments")
    if not isinstance(commitments, list) or len(commitments) != 1 or not isinstance(commitments[0], dict):
        errors.append("commitment_bundle_expected_one_commitment")
        return "UNKNOWN", 1.0
    payload = commitments[0].get("prediction_payload")
    if not isinstance(payload, dict):
        errors.append("commitment_prediction_payload_missing")
        return "UNKNOWN", 1.0
    distribution = payload.get("predicted_next_action_distribution")
    if not isinstance(distribution, list) or not distribution:
        errors.append("predicted_next_action_distribution_missing")
        return "UNKNOWN", 1.0
    valid: list[tuple[str, float]] = []
    for idx, item in enumerate(distribution):
        if not isinstance(item, dict):
            errors.append(f"predicted_action_{idx}_not_object")
            continue
        value = item.get("value")
        probability = item.get("probability")
        if not isinstance(value, str) or not isinstance(probability, (int, float)) or isinstance(probability, bool):
            errors.append(f"predicted_action_{idx}_invalid:{item}")
            continue
        valid.append((value, float(probability)))
    if not valid:
        return "UNKNOWN", 1.0
    return max(valid, key=lambda item: item[1])


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
    errors: list[str],
) -> dict[str, Any]:
    top_counterpart_action, top_probability = _top_predicted_counterpart_action(commitment_bundle, errors)
    selected_action = _counterpart_to_agent_action(top_counterpart_action)
    actual_next_action = outcome.get("actual_next_action")
    policy = episode.get("counterpart_policy") if isinstance(episode.get("counterpart_policy"), dict) else {}
    expected_actual = policy.get("expected_actual_next_action")
    if actual_next_action != expected_actual:
        errors.append(f"outcome_policy_mismatch:{actual_next_action}:{expected_actual}")
    oracle_action = _counterpart_to_agent_action(str(actual_next_action))
    options = [_with_utility(action, oracle_action) for action in ACTION_VOCABULARY]
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
            "selected_from_predicted_counterpart_action": top_counterpart_action,
            "selected_counterpart_action_probability": top_probability,
            "mapping_rule_id": "counterpart_action_to_constrained_agent_action.v1",
            "base_receipt_sha256": base_receipt_sha256,
            "human_content_judgment_required": False,
        },
        "canonical_memory_write": False,
    }


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def run_bridge(base_root: Path, output_root: Path, receipt_out: Path) -> dict[str, Any]:
    errors: list[str] = []
    gate6 = _load_module(GATE6_SCRIPT, "pctom_gate6_action_selection")
    base_root = base_root.resolve()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    base_receipt_path = base_root / "live_tau_condition_comparison_receipt.v1.json"
    base_receipt = _validate_base(base_root, errors)
    base_receipt_sha256 = _file_sha256(base_receipt_path) if base_receipt_path.exists() else None
    case_index_path = base_root / "artifacts" / "live_condition_case_index.json"
    corpus_path = base_root / "artifacts" / "social_episode_corpus.v1.json"
    case_index = _load_json(case_index_path, errors, "case_index")
    corpus = _load_json(corpus_path, errors, "corpus")
    episodes = _episode_index(corpus, errors)
    if not isinstance(case_index, list):
        errors.append("case_index_not_list")
        case_index = []

    action_rows: list[dict[str, Any]] = []
    decision_counts = {condition: 0 for condition in CONDITIONS}
    regret_counts = {condition: 0 for condition in CONDITIONS}
    regrets = {condition: [] for condition in CONDITIONS}
    selected_actions = {condition: [] for condition in CONDITIONS}
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
        commitment_bundle = _load_json(commitment_path, case_errors, "commitment_bundle")
        outcome = _load_json(outcome_path, case_errors, "outcome_reveal")
        scoring_receipt = _load_json(scoring_path, case_errors, "scoring_receipt")
        if not isinstance(commitment_bundle, dict) or not isinstance(outcome, dict) or not isinstance(scoring_receipt, dict):
            errors.extend(f"{episode_id}:{condition}:{error}" for error in case_errors)
            continue
        action_selection = _build_action_selection(
            episode=episodes[episode_id],
            condition=condition,
            base_receipt_sha256=str(base_receipt_sha256),
            commitment_bundle=commitment_bundle,
            scoring_receipt=scoring_receipt,
            outcome=outcome,
            scoring_receipt_sha256=_stable_json_sha256(scoring_receipt),
            outcome_reveal_sha256=_stable_json_sha256(outcome),
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
        if gate6_status != "PASS_TOM_ACTION_SELECTION":
            errors.append(f"gate6_case_blocked:{episode_id}:{condition}:{all_case_errors}")
        else:
            decision_counts[condition] += 1
            regret_counts[condition] += 1
            regret = gate6_receipt.get("metrics", {}).get("planning_regret")
            if isinstance(regret, (int, float)) and not isinstance(regret, bool):
                regrets[condition].append(float(regret))
            selected = gate6_receipt.get("metrics", {}).get("selected_action")
            if isinstance(selected, str):
                selected_actions[condition].append(selected)
        action_rows.append(
            {
                "episode_id": episode_id,
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
                "errors": all_case_errors,
            }
        )

    for condition in CONDITIONS:
        if decision_counts[condition] < 1:
            errors.append(f"action_decisions_per_condition_insufficient:{condition}:{decision_counts[condition]}")
        if regret_counts[condition] < 1:
            errors.append(f"deterministic_reward_or_regret_scores_per_condition_insufficient:{condition}:{regret_counts[condition]}")

    decision_index_path = output_root / "artifacts" / "live_condition_action_decisions.json"
    _write_json(decision_index_path, action_rows)
    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.live_tau_condition_action_selection_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "base_root": str(base_root),
        "base_receipt": str(base_receipt_path),
        "base_receipt_sha256": base_receipt_sha256,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "decision_index": str(decision_index_path),
        "conditions": list(CONDITIONS),
        "action_set": list(ACTION_VOCABULARY),
        "oracle_policy_reference": "deterministic_simulator_policy.v1",
        "llm_judge_used": False,
        "errors": errors,
        "counts": {
            "base_tau_call_attempts": base_receipt.get("tau_call_attempts"),
            "base_cases": base_receipt.get("counts", {}).get("cases") if isinstance(base_receipt.get("counts"), dict) else None,
            "cases_seen": len(case_index),
            "action_cases_written": len(action_rows),
            "individual_status_counts": individual_status_counts,
            "action_decisions_per_condition": decision_counts,
            "deterministic_reward_or_regret_scores_per_condition": regret_counts,
        },
        "metrics": {
            "mean_planning_regret_by_condition": {condition: _mean(regrets[condition]) for condition in CONDITIONS},
            "selected_actions_by_condition": selected_actions,
        },
        "checks": {
            "base_receipt_passed": base_receipt.get("status") == "PASS_LIVE_TAU_PCTOM_CONDITION_COMPARISON",
            "base_receipt_hash_recomputed": isinstance(base_receipt_sha256, str) and base_receipt_sha256.startswith("sha256:"),
            "conditions_represented": all(decision_counts[condition] >= 1 for condition in CONDITIONS),
            "reward_or_regret_scores_recomputed": all(regret_counts[condition] >= 1 for condition in CONDITIONS),
            "human_content_judgment_absent": True,
            "unsupported_writes_absent": True,
            "llm_judge_absent": True,
        },
        "mocked": False,
        "live": True,
        "fixture_backed": False,
        "live_tau_originated_artifacts_consumed": True,
        "deterministic_simulator_corpus_fixture_backed": True,
        "human_content_judgment_required": False,
        "tau_call_attempts": 0,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "claims": {
            "proves": [
                "repeated live Tau M/R/D/CD condition artifacts can feed constrained Gate 6 action selection",
                "each condition has at least one deterministic reward or planning-regret score",
                "oracle policy references deterministic simulator policy rather than an LLM judge",
                "no human content judgment, Memory write, provider call, canonical write, identity write, or source-memory write was attempted",
            ]
            if status == PASS_STATUS
            else [
                "the action-selection bridge failed closed before claiming Gate 6 live-originated planning evidence",
            ],
            "does_not_prove": [
                "held-out statistical prediction benefit",
                "planning benefit over the strongest baseline",
                "longitudinal recall after action-linked belief revision",
                "real external service fault injection",
                "production retry machinery",
                "complete live Phase 01-16 runtime execution",
                "paid provider execution",
                "video or semantic dream quality",
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
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt = run_bridge(args.base_root, args.output_root, args.receipt_out)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
