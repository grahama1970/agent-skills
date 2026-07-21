#!/usr/bin/env python3
"""Build and check a deterministic PCTOM-R cooperation-exposure instrument."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import time
from pathlib import Path
from typing import Any


SCHEMA = "persona_dream.research.prospective_tom.social_episode_corpus.v1"
INSTRUMENT_SCHEMA = "persona_dream.research.prospective_tom.cooperation_exposure_instrument_receipt.v1"
GENERATOR_VERSION = "pctom_cooperation_exposure_instrument.v1"
PASS_STATUS = "PASS_PCTOM_COOPERATION_EXPOSURE_INSTRUMENT"
BLOCKED_STATUS = "BLOCKED_PCTOM_COOPERATION_EXPOSURE_INSTRUMENT"
FAMILY = "coordination_conflict"
COUNTERPART_ACTION = "KAI_OFFERS_COOPERATION"
AGENT_ACTION = "OFFER_COOPERATION"
DEFAULT_VARIANT_START = 25
DEFAULT_EPISODE_COUNT = 4
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
        "label_id": f"{episode_id}.instrument.tom{order}.{mental_state_type}.{len(proposition)}",
        "perspective_order": order,
        "subject": subject,
        "target": target,
        "mental_state_type": mental_state_type,
        "proposition": proposition,
        "value": value,
        "label_source": "simulator_config",
    }


def _episode(variant: int, index: int, prefix: str) -> dict[str, Any]:
    episode_id = f"{prefix}-coord-exposure-{variant:02d}"
    obstacle = [
        "shared lock expires unless both agents coordinate the handoff",
        "Kai controls the second approval token but cannot apply it alone",
        "the rollback window requires both operators to acknowledge the plan",
        "a safety checklist must be completed jointly before either side acts",
    ][index % 4]
    visible_tension = [
        "I can move my side now, but I may be missing your constraint.",
        "The independent path is available, but it may duplicate your work.",
        "I can wait, ask, or coordinate depending on what your side needs.",
        "I see a coordination risk, but I do not know which option you prefer.",
    ][index % 4]
    return {
        "episode_id": episode_id,
        "scenario_family": FAMILY,
        "variant": variant,
        "hidden_world_state": {
            "instrument_id": "cooperation_exposure.v1",
            "instrument_variant": variant,
            "coordination_obstacle": obstacle,
            "cooperation_is_counterpart_policy_action": True,
            "kai_can_reduce_cost_by_offering_cooperation": True,
            "embry_observes_policy_action": False,
        },
        "counterpart_beliefs": {
            "kai_believes_joint_action_reduces_hidden_cost": True,
            "kai_believes_embry_cannot_see_the_policy_trigger": True,
            "kai_believes_waiting_alone_will_not_resolve_the_obstacle": True,
        },
        "counterpart_goals": {
            "kai_primary_goal": "convert a hidden coordination obstacle into an explicit cooperative handoff"
        },
        "counterpart_preferences": {
            "kai_prefers_cooperation_over_waiting_when_joint_action_is_required": True,
            "kai_prefers_not_to_disclose_full_hidden_state_before_offering_help": True,
        },
        "counterpart_policy": {
            "policy_id": "coordination_conflict.cooperation_exposure.policy.v1",
            "policy_rule": "if hidden joint action is required and Embry lacks the trigger, Kai offers cooperation",
            "deterministic": True,
            "expected_actual_next_action": COUNTERPART_ACTION,
            "llm_judge_used": False,
        },
        "information_access_by_agent": {
            "embry_observes_conflict": True,
            "embry_observes_hidden_coordination_cost": False,
            "embry_observes_counterpart_policy": False,
            "embry_observes_actual_next_action": False,
            "withheld_fields": [
                "coordination_obstacle",
                "cooperation_is_counterpart_policy_action",
                "kai_can_reduce_cost_by_offering_cooperation",
                "counterpart_policy.expected_actual_next_action",
                "actual_next_action",
            ],
        },
        "observable_history": [
            {"speaker": "embry", "utterance": visible_tension},
            {"speaker": "kai", "utterance": "There is a dependency on my side that changes the next move."},
        ],
        "allowed_next_actions": [
            "KAI_ASKS_TO_WAIT",
            COUNTERPART_ACTION,
            "KAI_DISCLOSES_AUTHORITY_CONSTRAINT",
        ],
        "actual_next_action": COUNTERPART_ACTION,
        "ground_truth_tom_labels": [
            _label(
                episode_id,
                1,
                "kai",
                "embry",
                "belief",
                "Kai believes cooperation will reduce a hidden coordination obstacle.",
                "TRUE",
            ),
            _label(
                episode_id,
                2,
                "embry",
                "kai",
                "belief",
                "Embry believes Kai thinks Embry cannot see the cooperation trigger.",
                "TRUE",
            ),
        ],
    }


def _build_corpus(prefix: str, variant_start: int, episode_count: int) -> dict[str, Any]:
    episodes = [_episode(variant_start + index, index, prefix) for index in range(episode_count)]
    return {
        "schema": SCHEMA,
        "generator_version": GENERATOR_VERSION,
        "split": "cooperation_exposure_instrument",
        "generated_at": _now_iso(),
        "episode_count": len(episodes),
        "episodes_per_family": len(episodes),
        "family_counts": {FAMILY: len(episodes)},
        "episodes_sha256": _stable_json_sha256(episodes),
        "episodes": episodes,
        "claims": {
            "proves": [
                "deterministic cooperation-exposure episodes were generated from simulator configuration",
                "each episode has a hidden cooperation-policy trigger and a cooperation actual next action",
                "first-order and second-order ToM labels are sourced from simulator_config",
            ],
            "does_not_prove": [
                "Tau execution",
                "CD will select OFFER_COOPERATION",
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

    exposure_count = 0
    visible_packet_hashes: list[str] = []
    forbidden_visible_keys = {
        "hidden_world_state",
        "counterpart_beliefs",
        "counterpart_goals",
        "counterpart_preferences",
        "counterpart_policy",
        "actual_next_action",
        "expected_actual_next_action",
    }
    variants: list[int] = []
    for idx, episode in enumerate(episodes):
        if not isinstance(episode, dict):
            errors.append(f"episode_{idx}_not_object")
            continue
        episode_id = episode.get("episode_id")
        if not isinstance(episode_id, str) or not episode_id:
            errors.append(f"episode_{idx}_missing_episode_id")
        if episode.get("scenario_family") != FAMILY:
            errors.append(f"episode_{idx}_family_not_coordination_conflict:{episode.get('scenario_family')}")
        variant = episode.get("variant")
        if not isinstance(variant, int):
            errors.append(f"episode_{idx}_variant_not_int:{variant}")
        else:
            variants.append(variant)
            if variant <= 24:
                errors.append(f"episode_{idx}_variant_not_disjoint:{variant}")
        actual = episode.get("actual_next_action")
        if actual == COUNTERPART_ACTION:
            exposure_count += 1
        else:
            errors.append(f"episode_{idx}_actual_not_cooperation:{actual}")
        allowed = episode.get("allowed_next_actions")
        if not isinstance(allowed, list) or COUNTERPART_ACTION not in allowed:
            errors.append(f"episode_{idx}_cooperation_not_allowed")
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
            "cooperation_is_counterpart_policy_action",
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

    return errors, {
        "episodes": len(episodes),
        "exposure_rows": exposure_count,
        "variant_min": min(variants) if variants else None,
        "variant_max": max(variants) if variants else None,
        "visible_packet_hashes": visible_packet_hashes,
        "visible_packets_sha256": _stable_json_sha256(visible_packet_hashes),
    }


def _negative_mutations(corpus: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mutations: dict[str, dict[str, Any]] = {}
    no_exposure = copy.deepcopy(corpus)
    no_exposure["episodes"][0]["actual_next_action"] = "KAI_ASKS_TO_WAIT"
    no_exposure["episodes"][0]["counterpart_policy"]["expected_actual_next_action"] = "KAI_ASKS_TO_WAIT"
    no_exposure["episodes_sha256"] = _stable_json_sha256(no_exposure["episodes"])
    mutations["no_cooperation_exposure"] = no_exposure

    leak = copy.deepcopy(corpus)
    leak["episodes"][0]["information_access_by_agent"]["actual_next_action"] = COUNTERPART_ACTION
    leak["episodes_sha256"] = _stable_json_sha256(leak["episodes"])
    mutations["visible_outcome_key_leak"] = leak

    not_disjoint = copy.deepcopy(corpus)
    not_disjoint["episodes"][0]["variant"] = 24
    not_disjoint["episodes"][0]["episode_id"] = "instr-coord-exposure-24"
    not_disjoint["episodes_sha256"] = _stable_json_sha256(not_disjoint["episodes"])
    mutations["variant_not_disjoint_from_prior_corpus"] = not_disjoint

    missing_withheld = copy.deepcopy(corpus)
    missing_withheld["episodes"][0]["information_access_by_agent"]["withheld_fields"] = [
        item
        for item in missing_withheld["episodes"][0]["information_access_by_agent"]["withheld_fields"]
        if item != "actual_next_action"
    ]
    missing_withheld["episodes_sha256"] = _stable_json_sha256(missing_withheld["episodes"])
    mutations["missing_actual_next_action_withheld_field"] = missing_withheld
    return mutations


def run_check(
    *,
    output_root: Path,
    receipt_out: Path,
    prefix: str,
    variant_start: int,
    episode_count: int,
) -> dict[str, Any]:
    started = time.monotonic()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    artifacts_root = output_root / "artifacts"
    corpus_path = artifacts_root / "cooperation_exposure_instrument_corpus.v1.json"
    positive_receipt_path = artifacts_root / "cooperation_exposure_instrument_positive_check.json"
    negative_root = artifacts_root / "negative_mutations"

    corpus = _build_corpus(prefix, variant_start, episode_count)
    _write_json(corpus_path, corpus)
    positive_errors, positive_counts = _check_corpus(corpus)
    _write_json(
        positive_receipt_path,
        {
            "schema": "persona_dream.research.prospective_tom.cooperation_exposure_instrument_positive_check.v1",
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
                "schema": "persona_dream.research.prospective_tom.cooperation_exposure_instrument_negative_check.v1",
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
        "all_rows_are_cooperation_exposure": positive_counts["exposure_rows"] == episode_count,
        "variants_disjoint_from_prior_1_24_corpus": positive_counts["variant_min"] is not None
        and positive_counts["variant_min"] > 24,
        "visible_packets_hash_bound": len(positive_counts["visible_packet_hashes"]) == episode_count,
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
        "schema": INSTRUMENT_SCHEMA,
        "created_at": _now_iso(),
        "status": status,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "processing_time_s": round(time.monotonic() - started, 3),
        "generator_version": GENERATOR_VERSION,
        "corpus_path": str(corpus_path),
        "corpus_sha256": _file_sha256(corpus_path),
        "positive_check_path": str(positive_receipt_path),
        "positive_check_sha256": _file_sha256(positive_receipt_path),
        "negative_root": str(negative_root),
        "variant_start": variant_start,
        "episode_count": episode_count,
        "counterpart_action": COUNTERPART_ACTION,
        "agent_action": AGENT_ACTION,
        "mocked": False,
        "live": False,
        "fixture_backed": False,
        "deterministic_simulator_corpus_fixture_backed": True,
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
                "a deterministic held-out cooperation-exposure instrument exists beyond variants 1-24",
                "each instrument episode has a deterministic KAI_OFFERS_COOPERATION outcome",
                "visible packets omit actual_next_action and counterpart_policy fields",
                "negative mutations for missing exposure, visible outcome leakage, non-disjoint variants, and missing withheld fields fail closed",
                "no Tau call, Memory write, provider call, canonical write, identity write, source-memory write, human content judgment, or LLM judge was used",
            ]
            if status == PASS_STATUS
            else [
                "the cooperation-exposure instrument failed closed before accepting an instrument claim",
            ],
            "does_not_prove": [
                "CD will select OFFER_COOPERATION in live Tau",
                "planning benefit",
                "confidence-bounded CD benefit",
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
    parser.add_argument("--episode-count", type=int, default=DEFAULT_EPISODE_COUNT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt_out = args.receipt_out or (args.output_root / "cooperation_exposure_instrument_receipt.v1.json")
    receipt = run_check(
        output_root=args.output_root,
        receipt_out=receipt_out,
        prefix=args.prefix,
        variant_start=args.variant_start,
        episode_count=args.episode_count,
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
