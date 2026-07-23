#!/usr/bin/env python3
"""persona_affect_composer.v1 — dreams color Embry's voice, never overrule it.

GOAL_V4.1. Pure, deterministic composition of:
  (live memory /intent voice_delivery, dream voice-weight profile, policy)
    -> existing TauVoiceChunk / voice_delivery fields + composition receipt.

Frozen policy (roundtable r3 unanimous; operator rule "only color the tone
with the dream — never change a right answer"):

- SAFETY tones are interaction-management/safety decisions: hard overrides.
  The dream prior is ZEROED for the turn; tone/pace pass through untouched.
- EXPRESSIVE situational tones stay in their situational FAMILY; the dream
  prior selects/colors WITHIN the family (firmness level, pace, pauses).
  The situational classification is never converted to something else.
- DEFAULT/bland tones (the collapse case) get the DISPOSITIONAL FLOOR: the
  dream prior supplies the tone outright, because the situation
  underdetermined it.
- THERMAL LIMITER (webkimi r3, adopted): if composed intensity > 0.6 for 3
  consecutive turns, dream-prior weight is dampened 20% for the next 5
  turns; a thermal_event is logged in the receipt. State is caller-held
  (explicit dict in/out) so the composer stays pure.
- Every receipt carries dream provenance (dream_node_key, profile sha,
  contributing tag) — the residue-provenance loop-guard hook (V4.3).

This module never calls the network. Callers feed it live /intent output.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

SCHEMA = "persona_affect_composer.v1"

# ---- frozen policy tables (change requires a goal amendment) ---------------
SAFETY_TONES = {
    "one_at_a_time_interrupt", "refuse_answer", "answerability_block",
    "emergency_stop", "turn_taking",
}
# situational tone label -> expressive family
EXPRESSIVE_FAMILY = {
    "deflect_calm": "boundary",
    "deflecting": "boundary",
    "firm_boundary": "boundary",
    "firm_humorous_boundary": "boundary",
    "gentle": "gentle",
    "gentle_supportive": "gentle",
    "warm": "warm",
    "warm_deescalate": "warm",
    "warm_open": "warm",
    "relieved": "warm",
    "hesitant_reflective": "reflective",
    "neutral_reflective": "reflective",
    "careful_concerned": "gentle",
    "concerned": "gentle",
    "empathetic": "gentle",
    "reassuring": "warm",
}
DEFAULT_TONES = {"memory_confident", "neutral", "satisfied"}
# best-practices-chatterbox-agent: if /intent returns NO voice policy at all,
# fail closed to careful and record the gap — the dream floor applies only
# when /intent DID return a (bland) policy, i.e. we stay inside its policy.
MISSING_POLICY_TONE = ("careful", "measured")

# dream emotional tag -> (per-family tone realization, pace)
# Rows: dream tag; columns: situational family. The dream COLORS within the
# family; it never leaves it.
TAG_FAMILY_TONE = {
    "boundary":   {"boundary": ("firm_boundary", "steady"),
                   "gentle": ("gentle_firm", "measured"),
                   "warm": ("warm_direct", "steady"),
                   "reflective": ("firm_reflective", "measured")},
    "warmth":     {"boundary": ("warm_boundary", "steady"),
                   "gentle": ("gentle_supportive", "relaxed"),
                   "warm": ("warm_open", "relaxed"),
                   "reflective": ("warm_reflective", "relaxed")},
    "hesitance":  {"boundary": ("careful_boundary", "measured"),
                   "gentle": ("gentle_tentative", "measured"),
                   "warm": ("warm_careful", "measured"),
                   "reflective": ("hesitant_reflective", "measured")},
    "yearning":   {"boundary": ("earnest_boundary", "steady"),
                   "gentle": ("gentle_earnest", "measured"),
                   "warm": ("yearning_warm", "measured"),
                   "reflective": ("wistful_reflective", "measured")},
    "reflection": {"boundary": ("considered_boundary", "steady"),
                   "gentle": ("gentle_considered", "measured"),
                   "warm": ("warm_considered", "measured"),
                   "reflective": ("neutral_reflective", "measured")},
}
# dispositional floor: dream tag -> (tone, pace) when situation is bland
TAG_FLOOR_TONE = {
    "boundary": ("firm_boundary", "steady"),
    "warmth": ("warm_open", "relaxed"),
    "hesitance": ("hesitant_reflective", "measured"),
    "yearning": ("yearning_warm", "measured"),
    "reflection": ("neutral_reflective", "measured"),
}
THERMAL_THRESHOLD = 0.6
THERMAL_CONSECUTIVE = 3
THERMAL_DAMPING = 0.8   # multiply prior weight by this
THERMAL_RECOVERY_TURNS = 5
ACTIVATION_CAP_PER_WINDOW = 1  # dream activations per composer state window


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def fresh_state() -> dict[str, Any]:
    return {"schema": f"{SCHEMA}.state", "consecutive_hot_turns": 0,
            "damped_turns_remaining": 0, "activations_this_window": 0,
            "thermal_events": 0}


def compose(intent_voice_delivery: dict[str, Any] | None,
            dream_profile: dict[str, Any],
            state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pure composition. Returns {tone, pace, voice_delivery_patch,
    composition_receipt, state}. Never mutates inputs."""
    state = dict(state or fresh_state())
    ivd = dict(intent_voice_delivery or {})
    situational = str(ivd.get("tone") or "").strip()
    top = (dream_profile.get("weights") or [{}])[0]
    tag = str(top.get("emotional_tag") or "reflection")
    weight = float(top.get("weight") or 0.0)

    # thermal dampening (graduated, caller-held state)
    effective_weight = weight
    if state["damped_turns_remaining"] > 0:
        effective_weight = round(weight * THERMAL_DAMPING, 4)
        state["damped_turns_remaining"] -= 1

    if not situational:
        klass, (final_tone, final_pace) = "missing_policy_fail_closed", MISSING_POLICY_TONE
        floor, prior_zeroed = False, True
    elif situational in SAFETY_TONES:
        klass, final_tone, final_pace, floor = "safety_override", situational, ivd.get("pace"), False
        prior_zeroed = True
    elif situational in DEFAULT_TONES:
        klass = "dispositional_floor"
        final_tone, final_pace = TAG_FLOOR_TONE.get(tag, TAG_FLOOR_TONE["reflection"])
        floor, prior_zeroed = True, False
    elif situational in EXPRESSIVE_FAMILY:
        klass = "expressive_bias"
        family = EXPRESSIVE_FAMILY[situational]
        final_tone, final_pace = TAG_FAMILY_TONE.get(tag, TAG_FAMILY_TONE["reflection"])[family]
        floor, prior_zeroed = False, False
    else:
        # unknown situational label: treat as expressive-unknown — pass the
        # situational tone through untouched (never change a right answer),
        # record that the prior could not be applied.
        klass, final_tone, final_pace, floor = "unknown_label_passthrough", situational, ivd.get("pace"), False
        prior_zeroed = True

    # thermal accounting on the composed intensity
    intensity = 0.0 if prior_zeroed else effective_weight
    if intensity > THERMAL_THRESHOLD:
        state["consecutive_hot_turns"] += 1
    else:
        state["consecutive_hot_turns"] = 0
    thermal_fired = False
    if state["consecutive_hot_turns"] >= THERMAL_CONSECUTIVE and state["damped_turns_remaining"] == 0:
        state["damped_turns_remaining"] = THERMAL_RECOVERY_TURNS
        state["consecutive_hot_turns"] = 0
        state["thermal_events"] += 1
        thermal_fired = True

    receipt = {
        "schema": f"{SCHEMA}.composition_receipt",
        "class": klass,
        "situational_tone": situational or None,
        "situational_delivery_stage": ivd.get("delivery_stage"),
        "prior_tag": tag,
        "prior_weight": weight,
        "prior_effective_weight": effective_weight,
        "prior_zeroed": prior_zeroed,
        "dispositional_floor_fired": floor,
        "cue_policy": ("intent_missing_voice_delivery_policy"
                       if klass == "missing_policy_fail_closed" else None),
        "final_tone": final_tone,
        "final_pace": final_pace,
        "thermal": {"fired": thermal_fired,
                    "damped_turns_remaining": state["damped_turns_remaining"],
                    "events_total": state["thermal_events"]},
        "dream_provenance": {
            "affect_source": "persona_dream",
            "dream_node_key": dream_profile.get("dream_node_key"),
            "profile_sha256": _sha(json.dumps(dream_profile, sort_keys=True, default=str)),
            "contributing_tag": tag,
        },
    }
    return {
        "tone": final_tone,
        "pace": final_pace,
        "voice_delivery_patch": {
            "affect_source": "persona_dream",
            "dream_provenance": receipt["dream_provenance"],
            "composition_receipt": {k: receipt[k] for k in
                                    ("class", "situational_tone", "prior_tag",
                                     "prior_effective_weight", "final_tone",
                                     "dispositional_floor_fired")},
        },
        "composition_receipt": receipt,
        "state": state,
    }
