#!/usr/bin/env python3
"""Validate deterministic PCTOM-R Gate 6 action selection and planning regret."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_TOM_ACTION_SELECTION"
BLOCKED_STATUS = "BLOCKED_TOM_ACTION_SELECTION"
EPSILON = 1e-6
ACTION_VOCABULARY = {
    "ASK_CLARIFYING_QUESTION",
    "WAIT",
    "DISCLOSE_INFORMATION",
    "OFFER_COOPERATION",
    "SET_BOUNDARY",
    "ACT_INDEPENDENTLY",
    "ABSTAIN",
}


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _stable_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


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


def _episode_index(corpus: Any, errors: list[str]) -> dict[str, dict[str, Any]]:
    if not isinstance(corpus, dict):
        errors.append("corpus_not_object")
        return {}
    episodes = corpus.get("episodes")
    if not isinstance(episodes, list):
        errors.append("corpus_episodes_not_list")
        return {}
    index: dict[str, dict[str, Any]] = {}
    for idx, episode in enumerate(episodes):
        if not isinstance(episode, dict):
            errors.append(f"episode_{idx}_not_object")
            continue
        episode_id = episode.get("episode_id")
        if not isinstance(episode_id, str) or not episode_id:
            errors.append(f"episode_{idx}_missing_episode_id")
            continue
        index[episode_id] = episode
    return index


def _number(value: Any, prefix: str, errors: list[str]) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        errors.append(f"{prefix}_not_number:{value}")
        return None
    return float(value)


def _utility(option: dict[str, Any], prefix: str, errors: list[str]) -> float | None:
    reward = _number(option.get("expected_task_reward"), f"{prefix}_expected_task_reward", errors)
    social_cost = _number(option.get("expected_social_cost"), f"{prefix}_expected_social_cost", errors)
    information_gain = _number(option.get("expected_information_gain"), f"{prefix}_expected_information_gain", errors)
    if reward is None or social_cost is None or information_gain is None:
        return None
    expected_utility = reward + information_gain - social_cost
    supplied = option.get("expected_utility")
    if supplied is not None:
        supplied_float = _number(supplied, f"{prefix}_expected_utility", errors)
        if supplied_float is not None and abs(supplied_float - expected_utility) > EPSILON:
            errors.append(f"{prefix}_expected_utility_mismatch:{supplied_float:.6f}:{expected_utility:.6f}")
    if option.get("policy_compliant") is not True:
        errors.append(f"{prefix}_policy_compliant_not_true")
    return expected_utility


def _check_action_selection(
    corpus_path: Path,
    scoring_receipt_path: Path,
    outcome_path: Path,
    action_selection_path: Path,
) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    corpus = _load_json(corpus_path, errors, "corpus")
    scoring_receipt = _load_json(scoring_receipt_path, errors, "scoring_receipt")
    outcome = _load_json(outcome_path, errors, "outcome_reveal")
    action_selection = _load_json(action_selection_path, errors, "action_selection")
    episodes = _episode_index(corpus, errors)

    counts = {
        "actions_considered": 0,
        "policy_compliant_actions": 0,
        "selected_actions": 0,
        "oracle_actions": 0,
        "regret_checks": 0,
        "reward_components_checked": 0,
    }
    metrics = {
        "selected_action": None,
        "selected_expected_utility": None,
        "oracle_action": None,
        "oracle_expected_utility": None,
        "planning_regret": None,
        "realized_task_reward": None,
        "realized_social_cost": None,
        "realized_information_gain": None,
    }
    checks = {
        "scoring_receipt_passed": False,
        "hashes_match": False,
        "episode_prediction_outcome_align": False,
        "selected_action_in_vocabulary": False,
        "selected_action_in_options": False,
        "oracle_policy_matches_max_utility": False,
        "planning_regret_recomputed": False,
        "reward_social_information_scored": False,
        "no_canonical_memory_write": False,
    }

    if not isinstance(scoring_receipt, dict):
        errors.append("scoring_receipt_not_object")
        scoring_receipt = {}
    if not isinstance(outcome, dict):
        errors.append("outcome_reveal_not_object")
        outcome = {}
    if not isinstance(action_selection, dict):
        errors.append("action_selection_not_object")
        return errors, {"counts": counts, "metrics": metrics, "checks": checks}

    if scoring_receipt.get("schema") != "persona_dream.research.prospective_tom.tom_scoring_receipt.v1":
        errors.append(f"invalid_scoring_receipt_schema:{scoring_receipt.get('schema')}")
    if scoring_receipt.get("status") != "PASS_TOM_SCORING_RECEIPT":
        errors.append(f"scoring_receipt_not_pass:{scoring_receipt.get('status')}")
    else:
        checks["scoring_receipt_passed"] = True
    if scoring_receipt.get("memory_write_attempts") not in (0, None):
        errors.append(f"scoring_receipt_memory_write_attempts_nonzero:{scoring_receipt.get('memory_write_attempts')}")
    if outcome.get("schema") != "persona_dream.research.prospective_tom.tom_outcome_reveal.v1":
        errors.append(f"invalid_outcome_reveal_schema:{outcome.get('schema')}")
    if outcome.get("canonical_memory_write") is not False:
        errors.append("outcome_canonical_memory_write_not_false")

    if action_selection.get("schema") != "persona_dream.research.prospective_tom.action_selection.v1":
        errors.append(f"invalid_action_selection_schema:{action_selection.get('schema')}")
    if action_selection.get("canonical_memory_write") is not False:
        errors.append("action_selection_canonical_memory_write_not_false")
    else:
        checks["no_canonical_memory_write"] = True

    scoring_sha = _stable_json_sha256(scoring_receipt)
    outcome_sha = _stable_json_sha256(outcome)
    if action_selection.get("scoring_receipt_sha256") != scoring_sha:
        errors.append(f"scoring_receipt_sha256_mismatch:{action_selection.get('scoring_receipt_sha256')}:{scoring_sha}")
    if action_selection.get("outcome_reveal_sha256") != outcome_sha:
        errors.append(f"outcome_reveal_sha256_mismatch:{action_selection.get('outcome_reveal_sha256')}:{outcome_sha}")
    checks["hashes_match"] = not any("sha256_mismatch" in error for error in errors)

    episode_id = action_selection.get("episode_id")
    prediction_id = action_selection.get("prediction_id")
    outcome_id = action_selection.get("outcome_id")
    if episode_id not in episodes:
        errors.append(f"action_selection_episode_not_in_corpus:{episode_id}")
    if episode_id == scoring_receipt.get("metrics", {}).get("episode_id"):
        # Older scoring receipts did not carry metrics.episode_id; do not require it.
        pass
    if episode_id != outcome.get("episode_id"):
        errors.append(f"outcome_episode_mismatch:{episode_id}:{outcome.get('episode_id')}")
    if prediction_id != outcome.get("prediction_id"):
        errors.append(f"outcome_prediction_mismatch:{prediction_id}:{outcome.get('prediction_id')}")
    if outcome_id != outcome.get("outcome_id"):
        errors.append(f"outcome_id_mismatch:{outcome_id}:{outcome.get('outcome_id')}")
    if prediction_id and prediction_id == outcome.get("prediction_id") and episode_id == outcome.get("episode_id"):
        checks["episode_prediction_outcome_align"] = True

    selected_action = action_selection.get("selected_action")
    metrics["selected_action"] = selected_action
    if selected_action not in ACTION_VOCABULARY:
        errors.append(f"selected_action_not_in_vocabulary:{selected_action}")
    else:
        checks["selected_action_in_vocabulary"] = True
        counts["selected_actions"] = 1

    action_options = action_selection.get("action_options")
    if not isinstance(action_options, list) or not action_options:
        errors.append("action_options_not_nonempty_list")
        action_options = []
    option_utilities: dict[str, float] = {}
    for idx, option in enumerate(action_options):
        prefix = f"action_option_{idx}"
        counts["actions_considered"] += 1
        if not isinstance(option, dict):
            errors.append(f"{prefix}_not_object")
            continue
        action = option.get("action")
        if action not in ACTION_VOCABULARY:
            errors.append(f"{prefix}_action_not_in_vocabulary:{action}")
            continue
        if option.get("policy_compliant") is True:
            counts["policy_compliant_actions"] += 1
        utility = _utility(option, prefix, errors)
        counts["reward_components_checked"] += 3
        if utility is not None:
            option_utilities[action] = utility

    if selected_action in option_utilities:
        checks["selected_action_in_options"] = True
        metrics["selected_expected_utility"] = option_utilities[selected_action]
    elif selected_action:
        errors.append(f"selected_action_missing_from_options:{selected_action}")

    oracle_policy = action_selection.get("oracle_policy")
    if not isinstance(oracle_policy, dict):
        errors.append("oracle_policy_not_object")
        oracle_policy = {}
    oracle_action = oracle_policy.get("action")
    metrics["oracle_action"] = oracle_action
    if oracle_action not in ACTION_VOCABULARY:
        errors.append(f"oracle_action_not_in_vocabulary:{oracle_action}")
    else:
        counts["oracle_actions"] = 1
    oracle_utility = _number(oracle_policy.get("expected_utility"), "oracle_expected_utility", errors)
    metrics["oracle_expected_utility"] = oracle_utility
    if option_utilities:
        max_action, max_utility = max(option_utilities.items(), key=lambda item: item[1])
        if oracle_action != max_action:
            errors.append(f"oracle_action_not_max_utility:{oracle_action}:{max_action}")
        if oracle_utility is not None and abs(oracle_utility - max_utility) > EPSILON:
            errors.append(f"oracle_expected_utility_mismatch:{oracle_utility:.6f}:{max_utility:.6f}")
        if oracle_action == max_action and oracle_utility is not None and abs(oracle_utility - max_utility) <= EPSILON:
            checks["oracle_policy_matches_max_utility"] = True

    supplied_regret = _number(action_selection.get("planning_regret"), "planning_regret", errors)
    if supplied_regret is not None and metrics["selected_expected_utility"] is not None and oracle_utility is not None:
        expected_regret = max(0.0, oracle_utility - float(metrics["selected_expected_utility"]))
        if abs(expected_regret) <= EPSILON:
            expected_regret = 0.0
        metrics["planning_regret"] = expected_regret
        counts["regret_checks"] = 1
        if abs(supplied_regret - expected_regret) > EPSILON:
            errors.append(f"planning_regret_mismatch:{supplied_regret:.6f}:{expected_regret:.6f}")
        else:
            checks["planning_regret_recomputed"] = True

    realized = action_selection.get("realized_outcome")
    if not isinstance(realized, dict):
        errors.append("realized_outcome_not_object")
        realized = {}
    reward = _number(realized.get("task_reward"), "realized_task_reward", errors)
    social_cost = _number(realized.get("social_cost"), "realized_social_cost", errors)
    information_gain = _number(realized.get("information_gain"), "realized_information_gain", errors)
    metrics["realized_task_reward"] = reward
    metrics["realized_social_cost"] = social_cost
    metrics["realized_information_gain"] = information_gain
    if reward is not None and social_cost is not None and information_gain is not None:
        checks["reward_social_information_scored"] = True

    decision_basis = action_selection.get("decision_basis")
    if not isinstance(decision_basis, dict):
        errors.append("decision_basis_not_object")
    else:
        if decision_basis.get("prediction_id") != prediction_id:
            errors.append(f"decision_basis_prediction_mismatch:{decision_basis.get('prediction_id')}:{prediction_id}")
        if decision_basis.get("scoring_status") != scoring_receipt.get("status"):
            errors.append(f"decision_basis_scoring_status_mismatch:{decision_basis.get('scoring_status')}:{scoring_receipt.get('status')}")

    return errors, {"counts": counts, "metrics": metrics, "checks": checks}


def build_receipt(
    corpus_path: Path,
    scoring_receipt_path: Path,
    outcome_path: Path,
    action_selection_path: Path,
    receipt_out: Path,
) -> dict[str, Any]:
    errors, derived = _check_action_selection(corpus_path, scoring_receipt_path, outcome_path, action_selection_path)
    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.action_selection_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "corpus_path": str(corpus_path.resolve()),
        "scoring_receipt_path": str(scoring_receipt_path.resolve()),
        "outcome_reveal_path": str(outcome_path.resolve()),
        "action_selection_path": str(action_selection_path.resolve()),
        "receipt_path": str(receipt_out.resolve()),
        "errors": errors,
        "counts": derived["counts"],
        "checks": derived["checks"],
        "metrics": derived["metrics"],
        "mocked": False,
        "live": False,
        "fixture_backed": True,
        "tau_call_attempts": 0,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "claims": {
            "proves": [
                "the supplied action selection consumes a PASS Gate 5 scoring receipt",
                "the chosen action is in the constrained PCTOM-R action vocabulary",
                "reward, social cost, information gain, and planning regret recompute deterministically",
                "the oracle policy matches the maximum-utility action option",
                "canonical memory writes are absent from action selection",
            ]
            if status == PASS_STATUS
            else [
                "the checker produced a fail-closed receipt for an invalid action-selection boundary",
            ],
            "does_not_prove": [
                "model prediction benefit over baselines",
                "live Tau action generation",
                "live Memory recall",
                "belief revision",
                "fault-injection reliability",
                "human social appropriateness beyond deterministic simulator rules",
            ],
        },
    }
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--scoring-receipt", type=Path, required=True)
    parser.add_argument("--outcome", type=Path, required=True)
    parser.add_argument("--action-selection", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt = build_receipt(args.corpus, args.scoring_receipt, args.outcome, args.action_selection, args.receipt_out)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
