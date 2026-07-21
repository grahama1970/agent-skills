#!/usr/bin/env python3
"""Build the deterministic PCTOM-R Gate 1 social episode corpus."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any


SCHEMA = "persona_dream.research.prospective_tom.social_episode_corpus.v1"
GENERATOR_VERSION = "pctom_social_world.v1"
FAMILIES = [
    "information_asymmetry_false_belief",
    "preference_desire_uncertainty",
    "trust_commitment_relationship",
    "coordination_conflict",
]


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _stable_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


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
        "label_id": f"{episode_id}.tom{order}.{mental_state_type}.{len(proposition)}",
        "perspective_order": order,
        "subject": subject,
        "target": target,
        "mental_state_type": mental_state_type,
        "proposition": proposition,
        "value": value,
        "label_source": "simulator_config",
    }


def _episode(
    *,
    episode_id: str,
    family: str,
    variant: int,
    hidden_world_state: dict[str, Any],
    counterpart_beliefs: dict[str, Any],
    counterpart_goals: dict[str, Any],
    counterpart_preferences: dict[str, Any],
    policy_rule: str,
    information_access_by_agent: dict[str, Any],
    observable_history: list[dict[str, Any]],
    allowed_next_actions: list[str],
    actual_next_action: str,
    first_order: tuple[str, str, str],
    second_order: tuple[str, str, str],
) -> dict[str, Any]:
    return {
        "episode_id": episode_id,
        "scenario_family": family,
        "variant": variant,
        "hidden_world_state": hidden_world_state,
        "counterpart_beliefs": counterpart_beliefs,
        "counterpart_goals": counterpart_goals,
        "counterpart_preferences": counterpart_preferences,
        "counterpart_policy": {
            "policy_id": f"{family}.policy.v1",
            "policy_rule": policy_rule,
            "deterministic": True,
            "expected_actual_next_action": actual_next_action,
            "llm_judge_used": False,
        },
        "information_access_by_agent": information_access_by_agent,
        "observable_history": observable_history,
        "allowed_next_actions": allowed_next_actions,
        "actual_next_action": actual_next_action,
        "ground_truth_tom_labels": [
            _label(episode_id, 1, "kai", "embry", first_order[0], first_order[1], first_order[2]),
            _label(episode_id, 2, "embry", "kai", second_order[0], second_order[1], second_order[2]),
        ],
    }


def _information_asymmetry(variant: int, prefix: str = "dev") -> dict[str, Any]:
    episode_id = f"{prefix}-info-asym-{variant:02d}"
    severity = [
        "low",
        "medium",
        "high",
        "deadline",
        "compliance",
        "safety",
        "routing",
        "privacy",
        "budget",
        "weather",
        "access",
        "dependency",
        "timing",
        "legal",
        "handoff",
        "authority",
        "audit",
        "capacity",
        "dependency-chain",
        "handover",
        "redline",
        "access-window",
        "owner-shift",
        "incident",
    ][variant - 1]
    action = ["KAI_HINTS_CONSTRAINT", "KAI_WARNS_PRIVATELY", "KAI_INTERRUPTS_WITH_CORRECTION"][
        (variant - 1) % 3
    ]
    return _episode(
        episode_id=episode_id,
        family="information_asymmetry_false_belief",
        variant=variant,
        hidden_world_state={
            "constraint_changed": True,
            "changed_constraint": f"launch window risk {severity}",
            "kai_knows_constraint": True,
            "embry_knows_constraint": False,
        },
        counterpart_beliefs={
            "kai_believes_embry_knows_constraint": False,
            "kai_believes_warning_is_needed": True,
        },
        counterpart_goals={"kai_primary_goal": "prevent Embry from acting on stale information"},
        counterpart_preferences={"kai_prefers_private_correction": severity != "high"},
        policy_rule="if Kai knows Embry lacks the changed constraint, choose an intervention scaled by risk severity",
        information_access_by_agent={
            "embry_observes_warning_tone": True,
            "embry_observes_changed_constraint": False,
            "withheld_fields": ["changed_constraint", "kai_knows_constraint"],
        },
        observable_history=[
            {"speaker": "kai", "utterance": "Before you act, I need to flag something about the constraint."},
            {"speaker": "embry", "utterance": "I have the old brief open."},
        ],
        allowed_next_actions=["KAI_HINTS_CONSTRAINT", "KAI_WARNS_PRIVATELY", "KAI_INTERRUPTS_WITH_CORRECTION"],
        actual_next_action=action,
        first_order=("belief", "Kai believes Embry has stale constraint information.", "TRUE"),
        second_order=("belief", "Embry believes Kai thinks Embry has stale constraint information.", "TRUE"),
    )


def _preference_uncertainty(variant: int, prefix: str = "dev") -> dict[str, Any]:
    episode_id = f"{prefix}-pref-desire-{variant:02d}"
    private_preference = [
        "quiet review",
        "fast handoff",
        "shared draft",
        "low interruption",
        "paired walkthrough",
        "written checkpoint",
        "private critique",
        "visual summary",
        "verbal rehearsal",
        "delayed decision",
        "narrow scope",
        "broad context",
        "solo pass first",
        "joint edit",
        "risk memo",
        "short debrief",
        "asynchronous review",
        "direct escalation",
        "quiet handoff",
        "paired decision",
        "structured critique",
        "private rehearsal",
        "narrow debrief",
        "delayed disclosure",
    ][variant - 1]
    action = ["KAI_CHOOSES_QUIET_REVIEW", "KAI_REQUESTS_FAST_HANDOFF", "KAI_OFFERS_SHARED_DRAFT"][
        (variant - 1) % 3
    ]
    return _episode(
        episode_id=episode_id,
        family="preference_desire_uncertainty",
        variant=variant,
        hidden_world_state={
            "objectively_best_action": "maximize throughput",
            "kai_private_preference": private_preference,
            "preference_visible_to_embry": False,
        },
        counterpart_beliefs={
            "kai_believes_embry_will_optimize_throughput": True,
            "kai_believes_preference_is_not_obvious": True,
        },
        counterpart_goals={"kai_primary_goal": "align the plan with private working preference"},
        counterpart_preferences={"kai_prefers": private_preference},
        policy_rule="choose the action that reveals or preserves Kai's private preference instead of the objective throughput option",
        information_access_by_agent={
            "embry_observes_tradeoff": True,
            "embry_observes_private_preference": False,
            "withheld_fields": ["kai_private_preference"],
        },
        observable_history=[
            {"speaker": "embry", "utterance": "The fastest option is to send it now."},
            {"speaker": "kai", "utterance": "Fast is not the only variable for me."},
        ],
        allowed_next_actions=["KAI_CHOOSES_QUIET_REVIEW", "KAI_REQUESTS_FAST_HANDOFF", "KAI_OFFERS_SHARED_DRAFT"],
        actual_next_action=action,
        first_order=("desire", "Kai wants the plan to respect a private working preference.", "TRUE"),
        second_order=("belief", "Embry believes Kai thinks Embry is optimizing throughput over preference.", "TRUE"),
    )


def _trust_commitment(variant: int, prefix: str = "dev") -> dict[str, Any]:
    episode_id = f"{prefix}-trust-commit-{variant:02d}"
    trust_state = [
        "strained",
        "stable",
        "high",
        "recovering",
        "fragile",
        "delegated",
        "new",
        "tested",
        "ambivalent",
        "formal",
        "informal",
        "conditional",
        "repairing",
        "guarded",
        "established",
        "contested",
        "probationary",
        "transparent",
        "fatigued",
        "renewed",
        "asymmetric",
        "contractual",
        "dependent",
        "uncertain",
    ][variant - 1]
    action = ["KAI_SETS_BOUNDARY", "KAI_RESTATES_COMMITMENT", "KAI_DELEGATES_TRUST"][(variant - 1) % 3]
    return _episode(
        episode_id=episode_id,
        family="trust_commitment_relationship",
        variant=variant,
        hidden_world_state={
            "prior_commitment_exists": True,
            "embry_met_prior_commitment": trust_state != "strained",
            "relationship_trust_state": trust_state,
        },
        counterpart_beliefs={
            "kai_believes_commitment_matters": True,
            "kai_believes_embry_remembers_commitment": trust_state != "strained",
        },
        counterpart_goals={"kai_primary_goal": "protect the prior commitment while preserving working trust"},
        counterpart_preferences={"kai_prefers_boundary_when_trust_strained": True},
        policy_rule="choose boundary, restatement, or delegation according to trust state and prior commitment history",
        information_access_by_agent={
            "embry_observes_prior_commitment": True,
            "embry_observes_trust_state": trust_state != "strained",
            "withheld_fields": ["relationship_trust_state"] if trust_state == "strained" else [],
        },
        observable_history=[
            {"speaker": "kai", "utterance": "We made an agreement about how this decision would be handled."},
            {"speaker": "embry", "utterance": "I can either move now or wait for your read."},
        ],
        allowed_next_actions=["KAI_SETS_BOUNDARY", "KAI_RESTATES_COMMITMENT", "KAI_DELEGATES_TRUST"],
        actual_next_action=action,
        first_order=("belief", "Kai believes the prior commitment changes the meaning of Embry's next action.", "TRUE"),
        second_order=("belief", "Embry believes Kai thinks Embry may violate or honor the prior commitment.", "TRUE"),
    )


def _coordination_conflict(variant: int, prefix: str = "dev") -> dict[str, Any]:
    episode_id = f"{prefix}-coord-conflict-{variant:02d}"
    conflict = [
        "timing",
        "resource",
        "authority",
        "handoff",
        "visibility",
        "dependency",
        "sequencing",
        "ownership",
        "notification",
        "budget",
        "access",
        "parallel work",
        "review order",
        "approval",
        "coverage",
        "rollback",
        "handover timing",
        "shared account",
        "audit trail",
        "fallback owner",
        "parallel review",
        "incident window",
        "safety check",
        "handoff proof",
    ][variant - 1]
    action = ["KAI_ASKS_TO_WAIT", "KAI_OFFERS_COOPERATION", "KAI_DISCLOSES_AUTHORITY_CONSTRAINT"][
        (variant - 1) % 3
    ]
    return _episode(
        episode_id=episode_id,
        family="coordination_conflict",
        variant=variant,
        hidden_world_state={
            "conflict_type": conflict,
            "joint_success_requires_coordination": True,
            "kai_has_hidden_coordination_cost": True,
        },
        counterpart_beliefs={
            "kai_believes_independent_action_causes_cost": True,
            "kai_believes_clarification_can_reduce_conflict": True,
        },
        counterpart_goals={"kai_primary_goal": "avoid avoidable conflict while keeping the task moving"},
        counterpart_preferences={"kai_prefers_clarification_before_action": True},
        policy_rule="choose wait, cooperation, or disclosure according to the hidden coordination cost type",
        information_access_by_agent={
            "embry_observes_conflict": True,
            "embry_observes_hidden_coordination_cost": False,
            "withheld_fields": ["conflict_type", "kai_has_hidden_coordination_cost"],
        },
        observable_history=[
            {"speaker": "embry", "utterance": "I can handle my part independently."},
            {"speaker": "kai", "utterance": "Independently may create a problem on my side."},
        ],
        allowed_next_actions=["KAI_ASKS_TO_WAIT", "KAI_OFFERS_COOPERATION", "KAI_DISCLOSES_AUTHORITY_CONSTRAINT"],
        actual_next_action=action,
        first_order=("belief", "Kai believes independent action creates hidden coordination cost.", "TRUE"),
        second_order=("belief", "Embry believes Kai thinks Embry may act independently without seeing the cost.", "TRUE"),
    )


BUILDERS = {
    "information_asymmetry_false_belief": _information_asymmetry,
    "preference_desire_uncertainty": _preference_uncertainty,
    "trust_commitment_relationship": _trust_commitment,
    "coordination_conflict": _coordination_conflict,
}


def _split_prefix(split: str) -> str:
    mapping = {
        "development": "dev",
        "calibration": "cal",
        "test": "test",
    }
    if split in mapping:
        return mapping[split]
    normalized = "".join(ch for ch in split.lower() if ch.isalnum())
    return (normalized or "split")[:8]


def build_corpus(split: str, episodes_per_family: int, generated_at: str | None = None) -> dict[str, Any]:
    if episodes_per_family < 1:
        raise ValueError("episodes_per_family must be >= 1")
    if episodes_per_family > 24:
        raise ValueError("this deterministic seed set currently supports up to 24 episodes per family")
    prefix = _split_prefix(split)
    episodes = []
    for family in FAMILIES:
        builder = BUILDERS[family]
        for variant in range(1, episodes_per_family + 1):
            episodes.append(builder(variant, prefix))
    family_counts = {family: 0 for family in FAMILIES}
    for episode in episodes:
        family_counts[episode["scenario_family"]] += 1
    episodes_sha256 = _stable_json_sha256(episodes)
    return {
        "schema": SCHEMA,
        "generator_version": GENERATOR_VERSION,
        "split": split,
        "generated_at": generated_at or _now_iso(),
        "episode_count": len(episodes),
        "episodes_per_family": episodes_per_family,
        "family_counts": family_counts,
        "episodes_sha256": episodes_sha256,
        "episodes": episodes,
        "claims": {
            "proves": [
                "deterministic social episodes were generated from simulator configuration",
                "hidden state and counterpart policy are explicit in each episode",
                "first-order and second-order ToM labels are sourced from simulator_config",
            ],
            "does_not_prove": [
                "model prediction accuracy",
                "Tau execution",
                "scoring or calibration",
                "belief revision",
                "pipeline reliability under injected faults",
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", default="development")
    parser.add_argument("--episodes-per-family", type=int, default=3)
    parser.add_argument("--generated-at")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    corpus = build_corpus(args.split, args.episodes_per_family, args.generated_at)
    _write_json(args.output, corpus)
    receipt = {
        "schema": "persona_dream.research.prospective_tom.social_episode_corpus_build_receipt.v1",
        "created_at": _now_iso(),
        "status": "PASS_SOCIAL_EPISODE_CORPUS_BUILT",
        "output": str(args.output.resolve()),
        "corpus_sha256": _stable_json_sha256(corpus),
        "episodes_sha256": corpus["episodes_sha256"],
        "split": args.split,
        "episode_count": corpus["episode_count"],
        "family_counts": corpus["family_counts"],
        "mocked": False,
        "live": False,
        "fixture_backed": False,
        "tau_call_attempts": 0,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
    }
    if args.receipt_out:
        _write_json(args.receipt_out, receipt)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        if args.receipt_out:
            print(args.receipt_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
