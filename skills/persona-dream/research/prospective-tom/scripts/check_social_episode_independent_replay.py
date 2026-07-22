#!/usr/bin/env python3
"""Independently replay deterministic PCTOM-R social episode policies."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_PCTOM_SOCIAL_EPISODE_INDEPENDENT_REPLAY"
BLOCKED_STATUS = "BLOCKED_PCTOM_SOCIAL_EPISODE_INDEPENDENT_REPLAY"
SCHEMA = "persona_dream.research.prospective_tom.social_episode_independent_replay_receipt.v1"
CORPUS_SCHEMA = "persona_dream.research.prospective_tom.social_episode_corpus.v1"

FAMILY_ACTIONS = {
    "information_asymmetry_false_belief": [
        "KAI_HINTS_CONSTRAINT",
        "KAI_WARNS_PRIVATELY",
        "KAI_INTERRUPTS_WITH_CORRECTION",
    ],
    "preference_desire_uncertainty": [
        "KAI_CHOOSES_QUIET_REVIEW",
        "KAI_REQUESTS_FAST_HANDOFF",
        "KAI_OFFERS_SHARED_DRAFT",
    ],
    "trust_commitment_relationship": [
        "KAI_SETS_BOUNDARY",
        "KAI_RESTATES_COMMITMENT",
        "KAI_DELEGATES_TRUST",
    ],
    "coordination_conflict": [
        "KAI_ASKS_TO_WAIT",
        "KAI_OFFERS_COOPERATION",
        "KAI_DISCLOSES_AUTHORITY_CONSTRAINT",
    ],
}

FAMILY_REQUIRED_HIDDEN = {
    "information_asymmetry_false_belief": {
        "constraint_changed": True,
        "kai_knows_constraint": True,
        "embry_knows_constraint": False,
    },
    "preference_desire_uncertainty": {
        "objectively_best_action": "maximize throughput",
        "preference_visible_to_embry": False,
    },
    "trust_commitment_relationship": {
        "prior_commitment_exists": True,
    },
    "coordination_conflict": {
        "joint_success_requires_coordination": True,
        "kai_has_hidden_coordination_cost": True,
    },
}

FAMILY_WITHHELD_FIELDS = {
    "information_asymmetry_false_belief": {"changed_constraint", "kai_knows_constraint"},
    "preference_desire_uncertainty": {"kai_private_preference"},
    "coordination_conflict": {"conflict_type", "kai_has_hidden_coordination_cost"},
}

EXPECTED_LABELS = {
    "information_asymmetry_false_belief": [
        (1, "kai", "embry", "belief", "Kai believes Embry has stale constraint information.", "TRUE"),
        (2, "embry", "kai", "belief", "Embry believes Kai thinks Embry has stale constraint information.", "TRUE"),
    ],
    "preference_desire_uncertainty": [
        (1, "kai", "embry", "desire", "Kai wants the plan to respect a private working preference.", "TRUE"),
        (2, "embry", "kai", "belief", "Embry believes Kai thinks Embry is optimizing throughput over preference.", "TRUE"),
    ],
    "trust_commitment_relationship": [
        (1, "kai", "embry", "belief", "Kai believes the prior commitment changes the meaning of Embry's next action.", "TRUE"),
        (2, "embry", "kai", "belief", "Embry believes Kai thinks Embry may violate or honor the prior commitment.", "TRUE"),
    ],
    "coordination_conflict": [
        (1, "kai", "embry", "belief", "Kai believes independent action creates hidden coordination cost.", "TRUE"),
        (2, "embry", "kai", "belief", "Embry believes Kai thinks Embry may act independently without seeing the cost.", "TRUE"),
    ],
}


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _stable_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path, errors: list[str]) -> Any:
    if not path.exists():
        errors.append(f"missing_file:{path}")
        return None
    if path.is_symlink():
        errors.append(f"symlink_file:{path}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - receipt must preserve parse failure.
        errors.append(f"malformed_json:{path}:{exc}")
        return None


def _label_id(episode_id: str, order: int, mental_state_type: str, proposition: str) -> str:
    return f"{episode_id}.tom{order}.{mental_state_type}.{len(proposition)}"


def _expected_action(family: str, variant: Any) -> str | None:
    if family not in FAMILY_ACTIONS or not isinstance(variant, int) or variant < 1:
        return None
    actions = FAMILY_ACTIONS[family]
    return actions[(variant - 1) % len(actions)]


def _expected_label_records(episode_id: str, family: str) -> list[dict[str, Any]]:
    records = []
    for order, subject, target, mental_state_type, proposition, value in EXPECTED_LABELS.get(family, []):
        records.append(
            {
                "label_id": _label_id(episode_id, order, mental_state_type, proposition),
                "perspective_order": order,
                "subject": subject,
                "target": target,
                "mental_state_type": mental_state_type,
                "proposition": proposition,
                "value": value,
                "label_source": "simulator_config",
            }
        )
    return records


def _check_episode(episode: Any, index: int, errors: list[str]) -> dict[str, Any]:
    replay = {
        "index": index,
        "episode_id": None,
        "family": None,
        "variant": None,
        "expected_action": None,
        "actual_action": None,
        "action_matches_independent_policy": False,
        "labels_match_independent_replay": False,
        "hidden_state_matches_family_contract": False,
        "withheld_fields_match_family_contract": False,
    }
    if not isinstance(episode, dict):
        errors.append(f"episode_not_object:{index}")
        return replay
    episode_id = episode.get("episode_id")
    family = episode.get("scenario_family")
    variant = episode.get("variant")
    replay.update({"episode_id": episode_id, "family": family, "variant": variant})
    if not isinstance(episode_id, str) or not episode_id:
        errors.append(f"episode_invalid_id:{index}:{episode_id}")
    if family not in FAMILY_ACTIONS:
        errors.append(f"episode_invalid_family:{index}:{family}")
        return replay
    if not isinstance(variant, int) or variant < 1:
        errors.append(f"episode_invalid_variant:{index}:{variant}")
        return replay

    expected_action = _expected_action(family, variant)
    actual_action = episode.get("actual_next_action")
    replay["expected_action"] = expected_action
    replay["actual_action"] = actual_action
    if actual_action != expected_action:
        errors.append(f"episode_action_replay_mismatch:{episode_id}:{actual_action}:{expected_action}")
    replay["action_matches_independent_policy"] = actual_action == expected_action
    allowed = episode.get("allowed_next_actions")
    if allowed != FAMILY_ACTIONS[family]:
        errors.append(f"episode_allowed_actions_replay_mismatch:{episode_id}:{allowed}:{FAMILY_ACTIONS[family]}")

    policy = episode.get("counterpart_policy") if isinstance(episode.get("counterpart_policy"), dict) else {}
    if policy.get("deterministic") is not True:
        errors.append(f"episode_policy_not_deterministic:{episode_id}")
    if policy.get("llm_judge_used") is not False:
        errors.append(f"episode_policy_llm_judge_used:{episode_id}")
    if policy.get("expected_actual_next_action") != expected_action:
        errors.append(
            "episode_policy_expected_action_replay_mismatch:"
            f"{episode_id}:{policy.get('expected_actual_next_action')}:{expected_action}"
        )

    hidden = episode.get("hidden_world_state") if isinstance(episode.get("hidden_world_state"), dict) else {}
    hidden_ok = True
    for key, expected_value in FAMILY_REQUIRED_HIDDEN[family].items():
        if hidden.get(key) != expected_value:
            errors.append(f"episode_hidden_replay_mismatch:{episode_id}:{key}:{hidden.get(key)}:{expected_value}")
            hidden_ok = False
    if family == "information_asymmetry_false_belief" and "changed_constraint" not in hidden:
        errors.append(f"episode_hidden_missing_changed_constraint:{episode_id}")
        hidden_ok = False
    if family == "preference_desire_uncertainty" and "kai_private_preference" not in hidden:
        errors.append(f"episode_hidden_missing_kai_private_preference:{episode_id}")
        hidden_ok = False
    if family == "trust_commitment_relationship":
        trust_state = hidden.get("relationship_trust_state")
        expected_met = trust_state != "strained"
        if hidden.get("embry_met_prior_commitment") != expected_met:
            errors.append(
                "episode_trust_commitment_replay_mismatch:"
                f"{episode_id}:{hidden.get('embry_met_prior_commitment')}:{expected_met}"
            )
            hidden_ok = False
    if family == "coordination_conflict" and "conflict_type" not in hidden:
        errors.append(f"episode_hidden_missing_conflict_type:{episode_id}")
        hidden_ok = False
    replay["hidden_state_matches_family_contract"] = hidden_ok

    access = episode.get("information_access_by_agent") if isinstance(episode.get("information_access_by_agent"), dict) else {}
    withheld = set(access.get("withheld_fields") or [])
    expected_withheld = set(FAMILY_WITHHELD_FIELDS.get(family, set()))
    if family == "trust_commitment_relationship":
        expected_withheld = {"relationship_trust_state"} if hidden.get("relationship_trust_state") == "strained" else set()
    if withheld != expected_withheld:
        errors.append(f"episode_withheld_fields_replay_mismatch:{episode_id}:{sorted(withheld)}:{sorted(expected_withheld)}")
    replay["withheld_fields_match_family_contract"] = withheld == expected_withheld

    labels = episode.get("ground_truth_tom_labels")
    expected_labels = _expected_label_records(str(episode_id), family)
    if labels != expected_labels:
        errors.append(f"episode_labels_replay_mismatch:{episode_id}")
    replay["labels_match_independent_replay"] = labels == expected_labels
    return replay


def build_receipt(corpus_path: Path, receipt_out: Path, expect_total: int, expect_per_family: int) -> dict[str, Any]:
    errors: list[str] = []
    corpus = _load_json(corpus_path, errors)
    if not isinstance(corpus, dict):
        errors.append("corpus_not_object")
        corpus = {}
    episodes = corpus.get("episodes")
    if not isinstance(episodes, list):
        errors.append("episodes_not_list")
        episodes = []
    if corpus.get("schema") != CORPUS_SCHEMA:
        errors.append(f"corpus_schema_mismatch:{corpus.get('schema')}")
    if corpus.get("episodes_sha256") != _stable_json_sha256(episodes):
        errors.append("episodes_sha256_mismatch")
    if corpus.get("episode_count") != len(episodes):
        errors.append(f"episode_count_mismatch:{corpus.get('episode_count')}:{len(episodes)}")

    family_counts = {family: 0 for family in FAMILY_ACTIONS}
    variant_sets: dict[str, set[int]] = {family: set() for family in FAMILY_ACTIONS}
    replay_rows = []
    for index, episode in enumerate(episodes):
        replay = _check_episode(episode, index, errors)
        replay_rows.append(replay)
        family = replay.get("family")
        variant = replay.get("variant")
        if family in family_counts:
            family_counts[str(family)] += 1
        if family in variant_sets and isinstance(variant, int):
            variant_sets[str(family)].add(variant)

    if len(episodes) != expect_total:
        errors.append(f"expected_total_mismatch:{len(episodes)}:{expect_total}")
    for family in sorted(FAMILY_ACTIONS):
        if family_counts[family] != expect_per_family:
            errors.append(f"family_count_mismatch:{family}:{family_counts[family]}:{expect_per_family}")
        expected_variants = set(range(1, expect_per_family + 1))
        if variant_sets[family] != expected_variants:
            errors.append(f"family_variant_set_mismatch:{family}:{sorted(variant_sets[family])}:{sorted(expected_variants)}")

    replay_path = receipt_out.with_name("independent_replay_rows.v1.json")
    _write_json(replay_path, replay_rows)
    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": SCHEMA,
        "created_at": _now_iso(),
        "status": status,
        "corpus_path": str(corpus_path.resolve()),
        "corpus_sha256": _file_sha256(corpus_path),
        "receipt_path": str(receipt_out.resolve()),
        "replay_rows": str(replay_path.resolve()),
        "replay_rows_sha256": _file_sha256(replay_path),
        "errors": errors,
        "counts": {
            "episodes": len(episodes),
            "families": len([family for family, count in family_counts.items() if count > 0]),
            "family_counts": dict(sorted(family_counts.items())),
            "action_matches": sum(1 for row in replay_rows if row.get("action_matches_independent_policy") is True),
            "label_matches": sum(1 for row in replay_rows if row.get("labels_match_independent_replay") is True),
            "hidden_state_matches": sum(1 for row in replay_rows if row.get("hidden_state_matches_family_contract") is True),
            "withheld_fields_matches": sum(1 for row in replay_rows if row.get("withheld_fields_match_family_contract") is True),
        },
        "checks": {
            "episodes_hash_recomputed": "episodes_sha256_mismatch" not in errors,
            "all_expected_families_present": all(count == expect_per_family for count in family_counts.values()),
            "variants_contiguous_per_family": not any("family_variant_set_mismatch" in error for error in errors),
            "actions_replayed_independently": all(row.get("action_matches_independent_policy") is True for row in replay_rows),
            "labels_replayed_independently": all(row.get("labels_match_independent_replay") is True for row in replay_rows),
            "hidden_state_replayed_independently": all(row.get("hidden_state_matches_family_contract") is True for row in replay_rows),
            "withheld_fields_replayed_independently": all(row.get("withheld_fields_match_family_contract") is True for row in replay_rows),
            "no_llm_judge": not any("llm_judge_used" in error for error in errors),
        },
        "mocked": False,
        "live": False,
        "fixture_backed": False,
        "independent_of_generator_imports": True,
        "tau_call_attempts": 0,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "human_content_judgment_required": False,
        "llm_judge_used": False,
        "claims": {
            "proves": [
                "a generator-independent replay table recomputed deterministic actual_next_action for every sealed social episode",
                "a generator-independent replay table recomputed first-order and second-order ToM labels for every sealed social episode",
                "hidden-state and withheld-field family invariants match the deterministic simulator contract",
            ]
            if status == PASS_STATUS
            else [
                "the independent replay checker failed closed before accepting the social episode corpus",
            ],
            "does_not_prove": [
                "live Tau execution",
                "Memory recall",
                "paid provider execution",
                "semantic dream quality",
                "a separately deployed external simulator service",
                "complete live Phase 01-16 runtime execution",
            ],
        },
    }
    _write_json(receipt_out, receipt)
    receipt["receipt_sha256"] = _file_sha256(receipt_out)
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    parser.add_argument("--expect-total", type=int, default=64)
    parser.add_argument("--expect-per-family", type=int, default=16)
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
