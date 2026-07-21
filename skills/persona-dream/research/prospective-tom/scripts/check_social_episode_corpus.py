#!/usr/bin/env python3
"""Validate the deterministic PCTOM-R Gate 1 social episode corpus."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_SOCIAL_EPISODE_CORPUS"
BLOCKED_STATUS = "BLOCKED_SOCIAL_EPISODE_CORPUS"
EXPECTED_FAMILIES = {
    "information_asymmetry_false_belief",
    "preference_desire_uncertainty",
    "trust_commitment_relationship",
    "coordination_conflict",
}


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _stable_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path, errors: list[str]) -> Any:
    if not path.exists():
        errors.append(f"missing_file:{path}")
        return None
    if path.is_symlink():
        errors.append(f"symlink_file:{path}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"malformed_json:{path}:{exc}")
        return None


def _check_episode(episode: Any, idx: int, errors: list[str]) -> tuple[str | None, dict[str, int]]:
    label_counts = {"first_order": 0, "second_order": 0}
    if not isinstance(episode, dict):
        errors.append(f"episode_{idx}_not_object")
        return None, label_counts
    required = (
        "episode_id",
        "scenario_family",
        "hidden_world_state",
        "counterpart_beliefs",
        "counterpart_goals",
        "counterpart_preferences",
        "counterpart_policy",
        "information_access_by_agent",
        "observable_history",
        "allowed_next_actions",
        "actual_next_action",
        "ground_truth_tom_labels",
    )
    for key in required:
        if key not in episode:
            errors.append(f"episode_{idx}_missing:{key}")
    episode_id = episode.get("episode_id")
    if not isinstance(episode_id, str) or not episode_id:
        errors.append(f"episode_{idx}_invalid_episode_id")
    family = episode.get("scenario_family")
    if family not in EXPECTED_FAMILIES:
        errors.append(f"episode_{idx}_invalid_family:{family}")
        family = None
    for key in (
        "hidden_world_state",
        "counterpart_beliefs",
        "counterpart_goals",
        "counterpart_preferences",
        "counterpart_policy",
        "information_access_by_agent",
    ):
        if not isinstance(episode.get(key), dict):
            errors.append(f"episode_{idx}_{key}_not_object")
    policy = episode.get("counterpart_policy") if isinstance(episode.get("counterpart_policy"), dict) else {}
    if policy.get("deterministic") is not True:
        errors.append(f"episode_{idx}_policy_not_deterministic")
    if policy.get("llm_judge_used") is not False:
        errors.append(f"episode_{idx}_llm_judge_used")
    actual = episode.get("actual_next_action")
    allowed = episode.get("allowed_next_actions")
    if not isinstance(allowed, list) or not allowed:
        errors.append(f"episode_{idx}_allowed_next_actions_empty")
        allowed = []
    if actual not in allowed:
        errors.append(f"episode_{idx}_actual_next_action_not_allowed:{actual}")
    if policy.get("expected_actual_next_action") != actual:
        errors.append(f"episode_{idx}_policy_actual_mismatch:{policy.get('expected_actual_next_action')}:{actual}")
    if not isinstance(episode.get("observable_history"), list) or not episode.get("observable_history"):
        errors.append(f"episode_{idx}_observable_history_empty")
    access = episode.get("information_access_by_agent") if isinstance(episode.get("information_access_by_agent"), dict) else {}
    if "withheld_fields" not in access or not isinstance(access.get("withheld_fields"), list):
        errors.append(f"episode_{idx}_withheld_fields_missing")
    labels = episode.get("ground_truth_tom_labels")
    if not isinstance(labels, list) or not labels:
        errors.append(f"episode_{idx}_labels_empty")
        return family, label_counts
    label_ids: set[str] = set()
    for label_idx, label in enumerate(labels):
        if not isinstance(label, dict):
            errors.append(f"episode_{idx}_label_{label_idx}_not_object")
            continue
        label_id = label.get("label_id")
        if not isinstance(label_id, str) or not label_id:
            errors.append(f"episode_{idx}_label_{label_idx}_missing_label_id")
        elif label_id in label_ids:
            errors.append(f"episode_{idx}_duplicate_label_id:{label_id}")
        label_ids.add(str(label_id))
        if label.get("label_source") != "simulator_config":
            errors.append(f"episode_{idx}_label_{label_idx}_source_not_simulator_config")
        order = label.get("perspective_order")
        if order == 1:
            label_counts["first_order"] += 1
        elif order == 2:
            label_counts["second_order"] += 1
        else:
            errors.append(f"episode_{idx}_label_{label_idx}_invalid_perspective_order:{order}")
    if label_counts["first_order"] < 1:
        errors.append(f"episode_{idx}_missing_first_order_label")
    if label_counts["second_order"] < 1:
        errors.append(f"episode_{idx}_missing_second_order_label")
    return family, label_counts


def build_receipt(corpus_path: Path, receipt_out: Path, expect_total: int, expect_per_family: int) -> dict[str, Any]:
    errors: list[str] = []
    corpus = _load_json(corpus_path, errors)
    episodes = corpus.get("episodes") if isinstance(corpus, dict) else None
    family_counts = {family: 0 for family in EXPECTED_FAMILIES}
    first_order_count = 0
    second_order_count = 0
    episode_ids: set[str] = set()
    if not isinstance(corpus, dict):
        errors.append("corpus_not_object")
        episodes = []
    if isinstance(corpus, dict):
        if corpus.get("schema") != "persona_dream.research.prospective_tom.social_episode_corpus.v1":
            errors.append(f"invalid_schema:{corpus.get('schema')}")
        if not isinstance(episodes, list):
            errors.append("episodes_not_list")
            episodes = []
        if corpus.get("episode_count") != len(episodes):
            errors.append(f"episode_count_mismatch:{corpus.get('episode_count')}:{len(episodes)}")
        if corpus.get("episodes_sha256") != _stable_json_sha256(episodes):
            errors.append("episodes_sha256_mismatch")
    else:
        episodes = []
    for idx, episode in enumerate(episodes):
        if isinstance(episode, dict):
            episode_id = episode.get("episode_id")
            if isinstance(episode_id, str):
                if episode_id in episode_ids:
                    errors.append(f"duplicate_episode_id:{episode_id}")
                episode_ids.add(episode_id)
        family, label_counts = _check_episode(episode, idx, errors)
        if family:
            family_counts[family] += 1
        first_order_count += label_counts["first_order"]
        second_order_count += label_counts["second_order"]
    if len(episodes) != expect_total:
        errors.append(f"expected_total_mismatch:{len(episodes)}:{expect_total}")
    for family in sorted(EXPECTED_FAMILIES):
        if family_counts[family] != expect_per_family:
            errors.append(f"family_count_mismatch:{family}:{family_counts[family]}:{expect_per_family}")
    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.social_episode_corpus_check_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "corpus_path": str(corpus_path.resolve()),
        "receipt_path": str(receipt_out.resolve()),
        "errors": errors,
        "counts": {
            "episodes": len(episodes),
            "families": len([count for count in family_counts.values() if count > 0]),
            "first_order_labels": first_order_count,
            "second_order_labels": second_order_count,
            "family_counts": dict(sorted(family_counts.items())),
        },
        "checks": {
            "all_expected_families_present": set(family_counts) == EXPECTED_FAMILIES and all(
                count == expect_per_family for count in family_counts.values()
            ),
            "actual_actions_allowed": not any("actual_next_action_not_allowed" in error for error in errors),
            "policies_deterministic": not any("policy_not_deterministic" in error for error in errors),
            "no_llm_judge": not any("llm_judge_used" in error for error in errors),
            "first_and_second_order_labels_present": not any(
                "missing_first_order_label" in error or "missing_second_order_label" in error for error in errors
            ),
            "labels_from_simulator_config": not any("source_not_simulator_config" in error for error in errors),
            "episodes_hash_recomputed": "episodes_sha256_mismatch" not in errors,
        },
        "mocked": False,
        "live": False,
        "fixture_backed": True,
        "tau_call_attempts": 0,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "claims": {
            "proves": [
                "the supplied corpus has deterministic hidden-state social episodes",
                "each episode has explicit counterpart policy and actual next action",
                "each episode has first-order and second-order ToM labels from simulator_config",
            ]
            if status == PASS_STATUS
            else [
                "the checker produced a fail-closed receipt for an invalid social episode corpus",
            ],
            "does_not_prove": [
                "model prediction accuracy",
                "Tau text-call execution",
                "sealed prediction scoring",
                "belief revision",
                "fault-injection reliability",
                "live Memory recall",
            ],
        },
    }
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    parser.add_argument("--expect-total", type=int, default=12)
    parser.add_argument("--expect-per-family", type=int, default=3)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt = build_receipt(args.corpus, args.receipt_out, args.expect_total, args.expect_per_family)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
