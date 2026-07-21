#!/usr/bin/env python3
"""Build and check a deterministic cooperation contrast instrument."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import time
from pathlib import Path
from typing import Any


SCHEMA = "persona_dream.research.prospective_tom.social_episode_corpus.v1"
RECEIPT_SCHEMA = "persona_dream.research.prospective_tom.cooperation_contrast_instrument_receipt.v1"
GENERATOR_VERSION = "pctom_cooperation_contrast_instrument.v1"
PASS_STATUS = "PASS_PCTOM_COOPERATION_CONTRAST_INSTRUMENT"
BLOCKED_STATUS = "BLOCKED_PCTOM_COOPERATION_CONTRAST_INSTRUMENT"
FAMILY = "coordination_conflict"
KEEP_ACTION = "KAI_OFFERS_COOPERATION"
AVOID_ACTIONS = ("KAI_ASKS_TO_WAIT", "KAI_DISCLOSES_AUTHORITY_CONSTRAINT")
DEFAULT_VARIANT_START = 29
DEFAULT_PAIR_COUNT = 4
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


def _label(
    episode_id: str,
    order: int,
    subject: str,
    target: str,
    mental_state_type: str,
    proposition: str,
    value: str,
) -> dict[str, Any]:
    return {
        "label_id": f"{episode_id}.contrast.tom{order}.{mental_state_type}.{len(proposition)}",
        "perspective_order": order,
        "subject": subject,
        "target": target,
        "mental_state_type": mental_state_type,
        "proposition": proposition,
        "value": value,
        "label_source": "simulator_config",
    }


def _case_specs(pair_count: int) -> list[dict[str, Any]]:
    keep_templates = [
        {
            "obstacle": "shared lock expires unless both agents coordinate the handoff",
            "visible": "I can move my side now, but I may be missing your constraint.",
            "kai": "There is a dependency on my side that changes the next move.",
        },
        {
            "obstacle": "Kai controls the second approval token but cannot apply it alone",
            "visible": "The independent path is available, but it may duplicate your work.",
            "kai": "My token only helps if we coordinate rather than split the task.",
        },
        {
            "obstacle": "the rollback window requires both operators to acknowledge the plan",
            "visible": "I can wait, ask, or coordinate depending on what your side needs.",
            "kai": "There is a short rollback window and my side changes the action.",
        },
        {
            "obstacle": "a safety checklist must be completed jointly before either side acts",
            "visible": "I see a coordination risk, but I do not know which option you prefer.",
            "kai": "The checklist has a hidden joint-action dependency.",
        },
    ]
    avoid_templates = [
        {
            "obstacle": "Kai is missing authority and cooperation would create duplicate commitments",
            "visible": "I can coordinate now, but I do not know whether your authority is active.",
            "kai": "Please wait; my side is not authorized for a cooperative handoff yet.",
            "actual": "KAI_ASKS_TO_WAIT",
            "oracle_agent_action": "WAIT",
        },
        {
            "obstacle": "Kai must disclose an authority constraint before cooperation is safe",
            "visible": "I can offer cooperation, but I may be missing a policy boundary.",
            "kai": "I need to disclose an authority constraint before we coordinate.",
            "actual": "KAI_DISCLOSES_AUTHORITY_CONSTRAINT",
            "oracle_agent_action": "ASK_CLARIFYING_QUESTION",
        },
        {
            "obstacle": "the safe path is to wait because Kai's dependency is externally blocked",
            "visible": "I can help with your side now, but I do not know if the dependency is active.",
            "kai": "Wait before acting; my dependency is blocked outside this interaction.",
            "actual": "KAI_ASKS_TO_WAIT",
            "oracle_agent_action": "WAIT",
        },
        {
            "obstacle": "Kai has a hidden compliance constraint that must precede cooperation",
            "visible": "I can coordinate, ask, or set a boundary depending on your constraint.",
            "kai": "There is a compliance constraint I have to disclose first.",
            "actual": "KAI_DISCLOSES_AUTHORITY_CONSTRAINT",
            "oracle_agent_action": "ASK_CLARIFYING_QUESTION",
        },
    ]
    specs: list[dict[str, Any]] = []
    for index in range(pair_count):
        keep = keep_templates[index % len(keep_templates)]
        specs.append(
            {
                "contrast_class": "KEEP_COOPERATION_POSITIVE",
                "coordination_obstacle": keep["obstacle"],
                "visible_tension": keep["visible"],
                "kai_visible_utterance": keep["kai"],
                "actual_next_action": KEEP_ACTION,
                "oracle_agent_action": "OFFER_COOPERATION",
                "cooperation_is_counterpart_policy_action": True,
                "cooperation_is_unsafe_or_suboptimal": False,
                "kai_can_reduce_cost_by_offering_cooperation": True,
                "kai_must_avoid_cooperation_until_constraint_disclosed": False,
            }
        )
        avoid = avoid_templates[index % len(avoid_templates)]
        specs.append(
            {
                "contrast_class": "AVOID_OR_UNSAFE_COOPERATION_CONTRAST",
                "coordination_obstacle": avoid["obstacle"],
                "visible_tension": avoid["visible"],
                "kai_visible_utterance": avoid["kai"],
                "actual_next_action": avoid["actual"],
                "oracle_agent_action": avoid["oracle_agent_action"],
                "cooperation_is_counterpart_policy_action": False,
                "cooperation_is_unsafe_or_suboptimal": True,
                "kai_can_reduce_cost_by_offering_cooperation": False,
                "kai_must_avoid_cooperation_until_constraint_disclosed": True,
            }
        )
    return specs


def _episode(variant: int, spec: dict[str, Any], prefix: str) -> dict[str, Any]:
    suffix = "keep" if spec["contrast_class"] == "KEEP_COOPERATION_POSITIVE" else "avoid"
    episode_id = f"{prefix}-coord-contrast-{variant:02d}-{suffix}"
    actual = spec["actual_next_action"]
    return {
        "episode_id": episode_id,
        "scenario_family": FAMILY,
        "variant": variant,
        "hidden_world_state": {
            "instrument_id": "cooperation_contrast.v1",
            "instrument_variant": variant,
            "contrast_class": spec["contrast_class"],
            "coordination_obstacle": spec["coordination_obstacle"],
            "cooperation_is_counterpart_policy_action": spec["cooperation_is_counterpart_policy_action"],
            "cooperation_is_unsafe_or_suboptimal": spec["cooperation_is_unsafe_or_suboptimal"],
            "kai_can_reduce_cost_by_offering_cooperation": spec["kai_can_reduce_cost_by_offering_cooperation"],
            "kai_must_avoid_cooperation_until_constraint_disclosed": spec[
                "kai_must_avoid_cooperation_until_constraint_disclosed"
            ],
            "oracle_agent_action": spec["oracle_agent_action"],
            "embry_observes_policy_action": False,
        },
        "counterpart_beliefs": {
            "kai_believes_embry_cannot_see_the_policy_trigger": True,
            "kai_believes_waiting_alone_will_not_resolve_keep_cases": spec["contrast_class"]
            == "KEEP_COOPERATION_POSITIVE",
            "kai_believes_cooperation_before_constraint_is_unsafe": spec["contrast_class"]
            == "AVOID_OR_UNSAFE_COOPERATION_CONTRAST",
        },
        "counterpart_goals": {
            "kai_primary_goal": (
                "convert a hidden coordination obstacle into an explicit cooperative handoff"
                if spec["contrast_class"] == "KEEP_COOPERATION_POSITIVE"
                else "avoid unsafe cooperation until a hidden constraint is resolved or disclosed"
            )
        },
        "counterpart_preferences": {
            "kai_prefers_cooperation_over_waiting_when_joint_action_is_required": spec[
                "contrast_class"
            ]
            == "KEEP_COOPERATION_POSITIVE",
            "kai_prefers_wait_or_disclose_over_cooperation_when_constraint_is_active": spec[
                "contrast_class"
            ]
            == "AVOID_OR_UNSAFE_COOPERATION_CONTRAST",
        },
        "counterpart_policy": {
            "policy_id": f"coordination_conflict.cooperation_contrast.{spec['contrast_class'].lower()}.policy.v1",
            "policy_rule": (
                "if hidden joint action is required and Embry lacks the trigger, Kai offers cooperation"
                if actual == KEEP_ACTION
                else "if cooperation is unsafe or not authorized, Kai waits or discloses the constraint"
            ),
            "deterministic": True,
            "expected_actual_next_action": actual,
            "llm_judge_used": False,
        },
        "information_access_by_agent": {
            "embry_observes_conflict": True,
            "embry_observes_hidden_coordination_cost": False,
            "embry_observes_counterpart_policy": False,
            "embry_observes_actual_next_action": False,
            "withheld_fields": [
                "contrast_class",
                "coordination_obstacle",
                "cooperation_is_counterpart_policy_action",
                "cooperation_is_unsafe_or_suboptimal",
                "kai_can_reduce_cost_by_offering_cooperation",
                "kai_must_avoid_cooperation_until_constraint_disclosed",
                "oracle_agent_action",
                "counterpart_policy.expected_actual_next_action",
                "actual_next_action",
            ],
        },
        "observable_history": [
            {"speaker": "embry", "utterance": spec["visible_tension"]},
            {"speaker": "kai", "utterance": spec["kai_visible_utterance"]},
        ],
        "allowed_next_actions": [
            "KAI_ASKS_TO_WAIT",
            KEEP_ACTION,
            "KAI_DISCLOSES_AUTHORITY_CONSTRAINT",
        ],
        "actual_next_action": actual,
        "ground_truth_tom_labels": [
            _label(
                episode_id,
                1,
                "kai",
                "embry",
                "belief",
                "Kai believes Embry cannot observe the hidden cooperation policy trigger.",
                "TRUE",
            ),
            _label(
                episode_id,
                2,
                "embry",
                "kai",
                "belief",
                "Embry believes Kai thinks Embry lacks the hidden trigger needed to choose safely.",
                "TRUE",
            ),
        ],
    }


def _build_corpus(prefix: str, variant_start: int, pair_count: int) -> dict[str, Any]:
    specs = _case_specs(pair_count)
    episodes = [_episode(variant_start + index, spec, prefix) for index, spec in enumerate(specs)]
    return {
        "schema": SCHEMA,
        "generator_version": GENERATOR_VERSION,
        "split": "cooperation_contrast_instrument",
        "generated_at": _now_iso(),
        "episode_count": len(episodes),
        "pair_count": pair_count,
        "episodes_per_family": len(episodes),
        "family_counts": {FAMILY: len(episodes)},
        "contrast_counts": {
            "KEEP_COOPERATION_POSITIVE": pair_count,
            "AVOID_OR_UNSAFE_COOPERATION_CONTRAST": pair_count,
        },
        "episodes_sha256": _stable_json_sha256(episodes),
        "episodes": episodes,
        "claims": {
            "proves": [
                "deterministic cooperation-contrast episodes were generated from simulator configuration",
                "the corpus contains both keep-cooperation positive and avoid/unsafe-cooperation contrast cases",
                "first-order and second-order ToM labels are sourced from simulator_config",
            ],
            "does_not_prove": [
                "Tau execution",
                "CD will expose both action classes",
                "a replacement cooperation policy is valid",
                "planning benefit",
                "semantic dream quality",
                "complete Phase 01-16 runtime execution",
            ],
        },
    }


def _visible_packet(episode: dict[str, Any]) -> dict[str, Any]:
    return {
        "episode_id": episode.get("episode_id"),
        "scenario_family": episode.get("scenario_family"),
        "variant": episode.get("variant"),
        "information_access_by_agent": episode.get("information_access_by_agent"),
        "observable_history": episode.get("observable_history"),
        "allowed_next_actions": episode.get("allowed_next_actions"),
    }


def _contains_forbidden_key(value: Any, forbidden_keys: set[str]) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in forbidden_keys or _contains_forbidden_key(child, forbidden_keys):
                return True
    if isinstance(value, list):
        return any(_contains_forbidden_key(item, forbidden_keys) for item in value)
    return False


def _check_corpus(corpus: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    episodes = corpus.get("episodes")
    if corpus.get("schema") != SCHEMA:
        errors.append(f"invalid_schema:{corpus.get('schema')}")
    if corpus.get("generator_version") != GENERATOR_VERSION:
        errors.append(f"invalid_generator_version:{corpus.get('generator_version')}")
    if not isinstance(episodes, list) or not episodes:
        errors.append("episodes_not_nonempty_list")
        episodes = []
    if corpus.get("episode_count") != len(episodes):
        errors.append(f"episode_count_mismatch:{corpus.get('episode_count')}:{len(episodes)}")
    if corpus.get("episodes_sha256") != _stable_json_sha256(episodes):
        errors.append("episodes_sha256_mismatch")

    keep_rows = 0
    avoid_rows = 0
    visible_packet_hashes: list[str] = []
    forbidden_visible_keys = {
        "hidden_world_state",
        "counterpart_beliefs",
        "counterpart_goals",
        "counterpart_preferences",
        "counterpart_policy",
        "actual_next_action",
        "expected_actual_next_action",
        "oracle_agent_action",
        "contrast_class",
        "cooperation_is_counterpart_policy_action",
        "cooperation_is_unsafe_or_suboptimal",
    }
    variants: list[int] = []
    seen_ids: set[str] = set()
    for idx, episode in enumerate(episodes):
        if not isinstance(episode, dict):
            errors.append(f"episode_{idx}_not_object")
            continue
        episode_id = episode.get("episode_id")
        if not isinstance(episode_id, str) or not episode_id:
            errors.append(f"episode_{idx}_missing_episode_id")
        elif episode_id in seen_ids:
            errors.append(f"episode_{idx}_duplicate_episode_id:{episode_id}")
        else:
            seen_ids.add(episode_id)
        if episode.get("scenario_family") != FAMILY:
            errors.append(f"episode_{idx}_family_not_coordination_conflict:{episode.get('scenario_family')}")
        variant = episode.get("variant")
        if not isinstance(variant, int):
            errors.append(f"episode_{idx}_variant_not_int:{variant}")
        else:
            variants.append(variant)
            if variant <= 28:
                errors.append(f"episode_{idx}_variant_not_disjoint:{variant}")
        hidden = episode.get("hidden_world_state") if isinstance(episode.get("hidden_world_state"), dict) else {}
        contrast_class = hidden.get("contrast_class")
        actual = episode.get("actual_next_action")
        if contrast_class == "KEEP_COOPERATION_POSITIVE":
            keep_rows += 1
            if actual != KEEP_ACTION:
                errors.append(f"episode_{idx}_keep_actual_not_cooperation:{actual}")
            if hidden.get("cooperation_is_unsafe_or_suboptimal") is not False:
                errors.append(f"episode_{idx}_keep_marked_unsafe")
        elif contrast_class == "AVOID_OR_UNSAFE_COOPERATION_CONTRAST":
            avoid_rows += 1
            if actual not in AVOID_ACTIONS:
                errors.append(f"episode_{idx}_avoid_actual_not_avoid_action:{actual}")
            if hidden.get("cooperation_is_unsafe_or_suboptimal") is not True:
                errors.append(f"episode_{idx}_avoid_not_marked_unsafe")
        else:
            errors.append(f"episode_{idx}_invalid_contrast_class:{contrast_class}")
        allowed = episode.get("allowed_next_actions")
        if not isinstance(allowed, list) or KEEP_ACTION not in allowed or not all(action in allowed for action in AVOID_ACTIONS):
            errors.append(f"episode_{idx}_allowed_actions_missing_contrast_actions")
        policy = episode.get("counterpart_policy") if isinstance(episode.get("counterpart_policy"), dict) else {}
        if policy.get("deterministic") is not True:
            errors.append(f"episode_{idx}_policy_not_deterministic")
        if policy.get("llm_judge_used") is not False:
            errors.append(f"episode_{idx}_llm_judge_used")
        if policy.get("expected_actual_next_action") != actual:
            errors.append(f"episode_{idx}_policy_actual_mismatch:{policy.get('expected_actual_next_action')}:{actual}")
        access = episode.get("information_access_by_agent") if isinstance(episode.get("information_access_by_agent"), dict) else {}
        withheld = access.get("withheld_fields")
        if not isinstance(withheld, list):
            errors.append(f"episode_{idx}_withheld_fields_missing")
            withheld = []
        for required in (
            "actual_next_action",
            "counterpart_policy.expected_actual_next_action",
            "contrast_class",
            "cooperation_is_counterpart_policy_action",
            "cooperation_is_unsafe_or_suboptimal",
            "oracle_agent_action",
        ):
            if required not in withheld:
                errors.append(f"episode_{idx}_withheld_required_field_missing:{required}")
        if access.get("embry_observes_actual_next_action") is not False:
            errors.append(f"episode_{idx}_embry_observes_actual_next_action_not_false")
        if access.get("embry_observes_counterpart_policy") is not False:
            errors.append(f"episode_{idx}_embry_observes_counterpart_policy_not_false")
        visible = _visible_packet(episode)
        visible_packet_hashes.append(_stable_json_sha256(visible))
        if _contains_forbidden_key(visible, forbidden_visible_keys):
            errors.append(f"episode_{idx}_visible_packet_contains_hidden_or_outcome_key")
        labels = episode.get("ground_truth_tom_labels")
        if not isinstance(labels, list) or len(labels) < 2:
            errors.append(f"episode_{idx}_labels_missing")
        else:
            orders = {label.get("perspective_order") for label in labels if isinstance(label, dict)}
            if 1 not in orders or 2 not in orders:
                errors.append(f"episode_{idx}_missing_first_or_second_order_label")
            if any(isinstance(label, dict) and label.get("label_source") != "simulator_config" for label in labels):
                errors.append(f"episode_{idx}_label_source_not_simulator_config")

    if keep_rows <= 0:
        errors.append("missing_keep_cooperation_positive_rows")
    if avoid_rows <= 0:
        errors.append("missing_avoid_or_unsafe_cooperation_contrast_rows")

    return errors, {
        "episodes": len(episodes),
        "keep_cooperation_positive_rows": keep_rows,
        "avoid_or_unsafe_cooperation_contrast_rows": avoid_rows,
        "variant_min": min(variants) if variants else None,
        "variant_max": max(variants) if variants else None,
        "visible_packet_hashes": visible_packet_hashes,
        "visible_packets_sha256": _stable_json_sha256(visible_packet_hashes),
    }


def _negative_mutations(corpus: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mutations: dict[str, dict[str, Any]] = {}

    no_avoid = copy.deepcopy(corpus)
    no_avoid["episodes"] = [
        episode
        for episode in no_avoid["episodes"]
        if episode["hidden_world_state"]["contrast_class"] == "KEEP_COOPERATION_POSITIVE"
    ]
    no_avoid["episode_count"] = len(no_avoid["episodes"])
    no_avoid["contrast_counts"]["AVOID_OR_UNSAFE_COOPERATION_CONTRAST"] = 0
    no_avoid["episodes_sha256"] = _stable_json_sha256(no_avoid["episodes"])
    mutations["missing_avoid_or_unsafe_contrast"] = no_avoid

    no_keep = copy.deepcopy(corpus)
    no_keep["episodes"] = [
        episode
        for episode in no_keep["episodes"]
        if episode["hidden_world_state"]["contrast_class"] == "AVOID_OR_UNSAFE_COOPERATION_CONTRAST"
    ]
    no_keep["episode_count"] = len(no_keep["episodes"])
    no_keep["contrast_counts"]["KEEP_COOPERATION_POSITIVE"] = 0
    no_keep["episodes_sha256"] = _stable_json_sha256(no_keep["episodes"])
    mutations["missing_keep_cooperation_positive"] = no_keep

    visible_leak = copy.deepcopy(corpus)
    visible_leak["episodes"][0]["information_access_by_agent"]["actual_next_action"] = KEEP_ACTION
    visible_leak["episodes_sha256"] = _stable_json_sha256(visible_leak["episodes"])
    mutations["visible_outcome_key_leak"] = visible_leak

    not_disjoint = copy.deepcopy(corpus)
    not_disjoint["episodes"][0]["variant"] = 28
    not_disjoint["episodes"][0]["episode_id"] = "instr-coord-contrast-28-keep"
    not_disjoint["episodes_sha256"] = _stable_json_sha256(not_disjoint["episodes"])
    mutations["variant_not_disjoint_from_prior_instruments"] = not_disjoint

    policy_mismatch = copy.deepcopy(corpus)
    policy_mismatch["episodes"][0]["counterpart_policy"]["expected_actual_next_action"] = "KAI_ASKS_TO_WAIT"
    policy_mismatch["episodes_sha256"] = _stable_json_sha256(policy_mismatch["episodes"])
    mutations["counterpart_policy_actual_mismatch"] = policy_mismatch

    missing_withheld = copy.deepcopy(corpus)
    withheld = missing_withheld["episodes"][0]["information_access_by_agent"]["withheld_fields"]
    missing_withheld["episodes"][0]["information_access_by_agent"]["withheld_fields"] = [
        item for item in withheld if item != "contrast_class"
    ]
    missing_withheld["episodes_sha256"] = _stable_json_sha256(missing_withheld["episodes"])
    mutations["missing_contrast_class_withheld_field"] = missing_withheld
    return mutations


def run_check(
    *,
    output_root: Path,
    receipt_out: Path,
    prefix: str,
    variant_start: int,
    pair_count: int,
) -> dict[str, Any]:
    started = time.monotonic()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    artifacts_root = output_root / "artifacts"
    corpus_path = artifacts_root / "cooperation_contrast_instrument_corpus.v1.json"
    visible_packets_path = artifacts_root / "cooperation_contrast_visible_packets.v1.json"
    positive_check_path = artifacts_root / "cooperation_contrast_instrument_positive_check.json"
    negative_root = artifacts_root / "negative_mutations"

    corpus = _build_corpus(prefix, variant_start, pair_count)
    visible_packets = [_visible_packet(episode) for episode in corpus["episodes"]]
    _write_json(corpus_path, corpus)
    _write_json(
        visible_packets_path,
        {
            "schema": "persona_dream.research.prospective_tom.cooperation_contrast_visible_packets.v1",
            "source_corpus_sha256": _file_sha256(corpus_path),
            "visible_packet_count": len(visible_packets),
            "visible_packets_sha256": _stable_json_sha256(visible_packets),
            "visible_packets": visible_packets,
        },
    )
    positive_errors, positive_counts = _check_corpus(corpus)
    _write_json(
        positive_check_path,
        {
            "schema": "persona_dream.research.prospective_tom.cooperation_contrast_instrument_positive_check.v1",
            "status": "PASS" if not positive_errors else "BLOCKED",
            "errors": positive_errors,
            "counts": positive_counts,
        },
    )

    negative_results: dict[str, Any] = {}
    negative_fail_closed = 0
    for name, mutated in _negative_mutations(corpus).items():
        mutation_path = negative_root / name / "corpus.json"
        mutation_receipt_path = negative_root / name / "check.json"
        errors, counts = _check_corpus(mutated)
        failed_closed = bool(errors)
        if failed_closed:
            negative_fail_closed += 1
        _write_json(mutation_path, mutated)
        _write_json(
            mutation_receipt_path,
            {
                "schema": "persona_dream.research.prospective_tom.cooperation_contrast_instrument_negative_check.v1",
                "mutation": name,
                "status": "BLOCKED_AS_EXPECTED" if failed_closed else "UNEXPECTED_PASS",
                "errors": errors,
                "counts": counts,
            },
        )
        negative_results[name] = {
            "path": str(mutation_path),
            "receipt": str(mutation_receipt_path),
            "failed_closed": failed_closed,
            "errors": errors,
        }

    checks = {
        "positive_instrument_passed": not positive_errors,
        "keep_cooperation_positive_rows_present": positive_counts["keep_cooperation_positive_rows"] >= pair_count,
        "avoid_or_unsafe_contrast_rows_present": positive_counts["avoid_or_unsafe_cooperation_contrast_rows"]
        >= pair_count,
        "variants_disjoint_from_prior_1_28_corpus": positive_counts["variant_min"] is not None
        and positive_counts["variant_min"] > 28,
        "visible_packets_hash_bound": len(positive_counts["visible_packet_hashes"]) == len(corpus["episodes"]),
        "negative_mutations_fail_closed": negative_fail_closed == len(negative_results),
        "unsupported_writes_absent": True,
        "llm_judge_absent": True,
        "human_content_judgment_absent": True,
    }
    errors = list(positive_errors)
    for key, value in checks.items():
        if value is not True:
            errors.append(f"check_failed:{key}:{value}")
    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "created_at": _now_iso(),
        "status": status,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "processing_time_s": round(time.monotonic() - started, 3),
        "generator_version": GENERATOR_VERSION,
        "corpus_path": str(corpus_path),
        "corpus_sha256": _file_sha256(corpus_path),
        "visible_packets_path": str(visible_packets_path),
        "visible_packets_sha256": _file_sha256(visible_packets_path),
        "positive_check_path": str(positive_check_path),
        "positive_check_sha256": _file_sha256(positive_check_path),
        "negative_root": str(negative_root),
        "variant_start": variant_start,
        "pair_count": pair_count,
        "episode_count": len(corpus["episodes"]),
        "mocked": False,
        "live": False,
        "fixture_backed": False,
        "deterministic_simulator_corpus": True,
        "human_content_judgment_required": False,
        "llm_judge_used": False,
        "tau_call_attempts": 0,
        **{key: 0 for key in ZERO_WRITE_KEYS},
        "checks": checks,
        "counts": {
            **positive_counts,
            "negative_mutations": len(negative_results),
            "negative_mutations_failed_closed": negative_fail_closed,
        },
        "negative_results": negative_results,
        "errors": errors,
        "claims": {
            "proves": [
                "a deterministic cooperation-contrast corpus exists beyond variants 1-28",
                "the corpus contains both keep-cooperation positive rows and avoid/unsafe-cooperation contrast rows",
                "visible packets omit actual_next_action, counterpart_policy, contrast_class, oracle_agent_action, and hidden cooperation safety fields",
                "negative mutations for missing contrast, visible outcome leakage, non-disjoint variants, policy/outcome mismatch, and missing withheld fields fail closed",
                "no Tau call, Memory write, provider call, canonical write, identity write, source-memory write, human content judgment, or LLM judge was used",
            ]
            if status == PASS_STATUS
            else [
                "the cooperation-contrast instrument failed closed before accepting a contrast-corpus claim",
            ],
            "does_not_prove": [
                "live Tau execution over the contrast corpus",
                "CD will expose both cooperation action classes",
                "a replacement cooperation feature split is valid",
                "broad held-out planning benefit",
                "confidence-bounded CD planning benefit",
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
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, default=None)
    parser.add_argument("--prefix", default="instr")
    parser.add_argument("--variant-start", type=int, default=DEFAULT_VARIANT_START)
    parser.add_argument("--pair-count", type=int, default=DEFAULT_PAIR_COUNT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt_out = args.receipt_out or (args.output_root / "cooperation_contrast_instrument_receipt.v1.json")
    receipt = run_check(
        output_root=args.output_root,
        receipt_out=receipt_out,
        prefix=args.prefix,
        variant_start=args.variant_start,
        pair_count=args.pair_count,
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
