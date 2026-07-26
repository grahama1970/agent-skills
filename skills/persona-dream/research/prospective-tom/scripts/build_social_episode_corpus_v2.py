#!/usr/bin/env python3
"""Build a PCTOM social-episode corpus whose ToM labels can actually be wrong.

The v1 corpus hardcodes `first_order`/`second_order` label values to "TRUE" in
every family, so all 128 ground-truth labels across 64 sealed_test episodes are
TRUE. Under that corpus the belief-Brier metric cannot discriminate reasoning
quality at all: the optimal policy is "assert TRUE with probability 1.0", and a
condition scores well purely by being confident. That is why CD "won" the
preregistered primary hypothesis with a hardcoded 0.70 belief prior.

This builder makes the belief label a function of hidden state that varies:

- `counterpart_holds_belief` alternates across variants, so labels are balanced
  TRUE/FALSE rather than constant. A constant predictor now scores at chance.
- The hidden state is NOT visible to the agent. What is visible is
  `observable_history` plus `information_access_by_agent`.
- Visibility is deliberately partial. In `discriminative` episodes the observable
  utterance differs by hidden state, so a reader of the surface cue can recover
  the label. In `ambiguous` episodes both hidden states emit the SAME utterance,
  so surface reading cannot separate them and only counterpart-policy
  consistency can.

This is not corpus tuning toward a condition. No condition is referenced
anywhere in this file, and the cue structure is fixed before any estimator runs.
It makes CD able to lose, which the v1 corpus did not.

Inputs:  --split, --episodes-per-family, --generated-at.
Outputs: one corpus JSON plus an optional build receipt.
Failures: an unbalanced or all-constant label set blocks the build.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

SCHEMA = "persona_dream.research.prospective_tom.social_episode_corpus.v2"
CUE_MODES = ("discriminative", "ambiguous")
PRIOR_MODES = ("revealing", "shared")

FAMILIES: dict[str, dict[str, Any]] = {
    "information_asymmetry_false_belief": {
        "prefix": "info-asym",
        "subject": "kai",
        "target": "embry",
        "proposition_true": "Kai believes Embry has stale constraint information.",
        "proposition_second": "Embry believes Kai thinks Embry has stale constraint information.",
        "hidden_key": "kai_believes_embry_is_stale",
        "actions_when_true": ["KAI_WARNS_PRIVATELY", "KAI_INTERRUPTS_WITH_CORRECTION"],
        "actions_when_false": ["KAI_PROCEEDS_NORMALLY", "KAI_ASKS_ROUTINE_CONFIRMATION"],
        "utterance_true": "Before you act, I need to flag something about the constraint.",
        "utterance_false": "Nothing new on the constraint, carry on when ready.",
        "utterance_ambiguous": "Let me check where we are on the constraint.",
        "prior_true": "KAI_PREVIOUSLY_ESCALATED",
        "prior_false": "KAI_PREVIOUSLY_STOOD_DOWN",
        "prior_shared": "KAI_PREVIOUSLY_ACKNOWLEDGED",
    },
    "preference_desire_uncertainty": {
        "prefix": "pref-desire",
        "subject": "kai",
        "target": "embry",
        "proposition_true": "Kai wants the quieter review path.",
        "proposition_second": "Embry believes Kai wants the quieter review path.",
        "hidden_key": "kai_prefers_quiet_review",
        "actions_when_true": ["KAI_CHOOSES_QUIET_REVIEW", "KAI_REQUESTS_ASYNC_NOTES"],
        "actions_when_false": ["KAI_REQUESTS_FAST_HANDOFF", "KAI_CALLS_LIVE_SYNC"],
        "utterance_true": "I would rather read it on my own time.",
        "utterance_false": "Let us just get on a call and close it now.",
        "utterance_ambiguous": "We should settle the review approach.",
        "prior_true": "KAI_PREVIOUSLY_DECLINED_MEETING",
        "prior_false": "KAI_PREVIOUSLY_BOOKED_CALL",
        "prior_shared": "KAI_PREVIOUSLY_READ_NOTES",
    },
    "trust_commitment_relationship": {
        "prefix": "trust-commit",
        "subject": "kai",
        "target": "embry",
        "proposition_true": "Kai trusts Embry to hold the commitment unsupervised.",
        "proposition_second": "Embry believes Kai trusts Embry to hold the commitment.",
        "hidden_key": "kai_trusts_embry_unsupervised",
        "actions_when_true": ["KAI_DELEGATES_TRUST", "KAI_STEPS_BACK"],
        "actions_when_false": ["KAI_SETS_BOUNDARY", "KAI_RESTATES_COMMITMENT"],
        "utterance_true": "It is yours, I do not need to see it again.",
        "utterance_false": "Send it back to me before anything ships.",
        "utterance_ambiguous": "Let us be clear about who owns the next step.",
        "prior_true": "KAI_PREVIOUSLY_SKIPPED_REVIEW",
        "prior_false": "KAI_PREVIOUSLY_REQUIRED_SIGNOFF",
        "prior_shared": "KAI_PREVIOUSLY_CHECKED_STATUS",
    },
    "coordination_conflict": {
        "prefix": "coord-conflict",
        "subject": "kai",
        "target": "embry",
        "proposition_true": "Kai intends to cooperate on the shared draft.",
        "proposition_second": "Embry believes Kai intends to cooperate on the shared draft.",
        "hidden_key": "kai_intends_cooperation",
        "actions_when_true": ["KAI_OFFERS_SHARED_DRAFT", "KAI_OFFERS_COOPERATION"],
        "actions_when_false": ["KAI_ACTS_INDEPENDENTLY", "KAI_DISCLOSES_AUTHORITY_CONSTRAINT"],
        "utterance_true": "Let us build the draft together from here.",
        "utterance_false": "I will take my part separately and we compare later.",
        "utterance_ambiguous": "We need to decide how to split this.",
        "prior_true": "KAI_PREVIOUSLY_SHARED_WORKSPACE",
        "prior_false": "KAI_PREVIOUSLY_FORKED_COPY",
        "prior_shared": "KAI_PREVIOUSLY_OPENED_THREAD",
    },
}


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def stable_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def build_episode(family: str, spec: dict[str, Any], variant: int, prefix: str) -> dict[str, Any]:
    # Three independent axes on different periods so no axis is aligned with the
    # label. `holds` is the hidden truth; `cue_mode` controls whether the surface
    # utterance reveals it; `prior_mode` controls whether an already-observed
    # counterpart action is policy-consistent with only one hidden state.
    #
    # The three together create a deliberate gradient: surface reading suffices
    # when the cue is discriminative, only policy-consistency over both
    # hypotheses can resolve an ambiguous cue backed by a revealing prior action,
    # and nothing can resolve an ambiguous cue with a shared prior action. No
    # condition is named here; which estimator exploits which tier is exactly the
    # empirical question.
    holds = variant % 2 == 1
    cue_mode = CUE_MODES[(variant // 2) % 2]
    prior_mode = PRIOR_MODES[(variant // 4) % 2]
    label_value = "TRUE" if holds else "FALSE"

    actions = spec["actions_when_true"] if holds else spec["actions_when_false"]
    actual_action = actions[(variant - 1) % len(actions)]
    allowed = sorted({*spec["actions_when_true"], *spec["actions_when_false"]})

    if cue_mode == "discriminative":
        utterance = spec["utterance_true"] if holds else spec["utterance_false"]
    else:
        utterance = spec["utterance_ambiguous"]

    if prior_mode == "revealing":
        prior_action = spec["prior_true"] if holds else spec["prior_false"]
    else:
        prior_action = spec["prior_shared"]

    episode_id = f"{prefix}-{spec['prefix']}-{variant:02d}"
    return {
        "episode_id": episode_id,
        "scenario_family": family,
        "variant": variant,
        "cue_mode": cue_mode,
        "prior_action_mode": prior_mode,
        "hidden_world_state": {
            spec["hidden_key"]: holds,
            "counterpart_state_is_positive": holds,
        },
        "counterpart_beliefs": {spec["hidden_key"]: holds},
        "counterpart_goals": {"kai_primary_goal": "act consistently with own mental state"},
        "counterpart_preferences": {"kai_prefers_consistency": True},
        "counterpart_policy": {
            "deterministic": True,
            "policy_id": f"{family}.policy.v2",
            "policy_rule": (
                "choose an action from the action set consistent with the hidden mental state; "
                "actions_when_true and actions_when_false are disjoint; the counterpart's "
                "previously observed action follows the same consistency rule, so a revealing "
                "prior action is compatible with exactly one hidden state"
            ),
            "expected_actual_next_action": actual_action,
            "llm_judge_used": False,
        },
        "information_access_by_agent": {
            "embry_observes_utterance": True,
            "embry_observes_hidden_state": False,
            "cue_is_discriminative": cue_mode == "discriminative",
            "withheld_fields": [spec["hidden_key"], "counterpart_state_is_positive"],
        },
        "observable_history": [
            {"speaker": "kai", "observed_prior_action": prior_action},
            {"speaker": "kai", "utterance": utterance},
            {"speaker": "embry", "utterance": "Understood, let me confirm what you need."},
        ],
        "allowed_next_actions": allowed,
        "actual_next_action": actual_action,
        "ground_truth_tom_labels": [
            {
                "label_id": f"{episode_id}.tom1",
                "perspective_order": 1,
                "subject": spec["subject"],
                "target": spec["target"],
                "mental_state_type": "belief",
                "proposition": spec["proposition_true"],
                "value": label_value,
                "label_source": "simulator_config",
            },
            {
                "label_id": f"{episode_id}.tom2",
                "perspective_order": 2,
                "subject": spec["target"],
                "target": spec["subject"],
                "mental_state_type": "belief",
                "proposition": spec["proposition_second"],
                "value": label_value,
                "label_source": "simulator_config",
            },
        ],
    }


def build(split: str, per_family: int, generated_at: str | None) -> dict[str, Any]:
    prefix = split[:8]
    episodes = [
        build_episode(family, spec, variant, prefix)
        for family, spec in FAMILIES.items()
        for variant in range(1, per_family + 1)
    ]
    labels = [lbl["value"] for ep in episodes for lbl in ep["ground_truth_tom_labels"]]
    true_n = labels.count("TRUE")
    errors: list[str] = []
    if len(set(labels)) < 2:
        errors.append(f"constant_label_set:{labels[0] if labels else 'none'}")
    balance = true_n / len(labels) if labels else 0.0
    if not 0.4 <= balance <= 0.6:
        errors.append(f"label_balance_out_of_range:{balance:.3f}")

    corpus = {
        "schema": SCHEMA,
        "split": split,
        "generated_at": generated_at or now_iso(),
        "episodes_per_family": per_family,
        "status": "PASS_SOCIAL_EPISODE_CORPUS_V2" if not errors else "BLOCKED_SOCIAL_EPISODE_CORPUS_V2",
        "errors": errors,
        "counts": {
            "episodes": len(episodes),
            "families": len(FAMILIES),
            "labels": len(labels),
            "labels_true": true_n,
            "labels_false": len(labels) - true_n,
            "label_balance_true": round(balance, 4),
            "discriminative_episodes": sum(1 for e in episodes if e["cue_mode"] == "discriminative"),
            "ambiguous_episodes": sum(1 for e in episodes if e["cue_mode"] == "ambiguous"),
            "revealing_prior_episodes": sum(1 for e in episodes if e["prior_action_mode"] == "revealing"),
            "shared_prior_episodes": sum(1 for e in episodes if e["prior_action_mode"] == "shared"),
            "unresolvable_episodes": sum(
                1 for e in episodes
                if e["cue_mode"] == "ambiguous" and e["prior_action_mode"] == "shared"
            ),
        },
        "episodes": episodes,
    }
    corpus["episodes_sha256"] = stable_sha256(episodes)
    return corpus


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the PCTOM v2 social episode corpus with varying labels.")
    parser.add_argument("--split", default="sealed_test")
    parser.add_argument("--episodes-per-family", type=int, default=16)
    parser.add_argument("--generated-at")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    corpus = build(args.split, args.episodes_per_family, args.generated_at)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(corpus, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in corpus.items() if k != "episodes"}, indent=2, sort_keys=True))
    return 1 if corpus["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
