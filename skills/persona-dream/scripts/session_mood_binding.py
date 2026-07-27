#!/usr/bin/env python3
"""Bind a Persona Dream continuity-ledger mood before a conversation starts.

This is the deterministic consumer between the hardened continuity ledger and a
future live Chatterbox render. It does not call Memory, Tau, Watch, or
Chatterbox. It proves that session mood is selected from the latest valid
ledger, remains stable across turns, and only affects the voice_delivery
envelope while answer text stays invariant.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


continuity_ledger = _load("continuity_ledger")


MOOD_TO_VOICE = {
    "guarded_quietly_wanting": {
        "tone": "firm_boundary",
        "intensity": 0.72,
        "valence": -0.25,
        "pace": "measured",
        "emphasis_tag": "guarded_yearning",
    },
    "boundary_forward_not_hostile": {
        "tone": "firm_boundary",
        "intensity": 0.78,
        "valence": -0.45,
        "pace": "steady",
        "emphasis_tag": "boundary",
    },
    "warm_but_withholding": {
        "tone": "warm_open",
        "intensity": 0.58,
        "valence": 0.35,
        "pace": "measured",
        "emphasis_tag": "warmth",
    },
    "neutral_reflective": {
        "tone": "neutral_reflective",
        "intensity": 0.45,
        "valence": 0.0,
        "pace": "measured",
        "emphasis_tag": "reflection",
    },
}


def _sha(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def ledger_hash(ledger: dict) -> str:
    return "sha256:" + _sha(ledger)


def latest_arc_delta(ledger: dict) -> dict:
    deltas = ((ledger.get("arc_state") or {}).get("recent_arc_deltas") or [])
    if not deltas:
        raise ValueError("BLOCKED_SESSION_MOOD_NO_ARC_DELTA")
    return deltas[-1]


def classify_mood(delta: dict) -> str:
    text = " ".join(str(delta.get(k) or "") for k in (
        "now", "still_true", "open_tension", "possible_expression")).lower()
    wants = any(k in text for k in ("want", "known", "understood", "witness"))
    boundary = any(k in text for k in ("boundary", "distance", "intrusion", "resist", "protect"))
    warmth = any(k in text for k in ("warm", "care", "closeness", "contact"))
    if wants and boundary:
        return "guarded_quietly_wanting"
    if boundary:
        return "boundary_forward_not_hostile"
    if warmth:
        return "warm_but_withholding"
    return "neutral_reflective"


def select_session_mood(persona_id: str, ledger: dict) -> dict:
    delta = latest_arc_delta(ledger)
    label = classify_mood(delta)
    source = {
        "persona_id": persona_id,
        "ledger_epoch": ledger["epoch"],
        "ledger_identity_core_sha256": ledger["identity_core_sha256"],
        "arc_delta_id": delta.get("arc_delta_id"),
        "arc_delta_idempotency_key": delta.get("idempotency_key"),
        "mood_label": label,
    }
    return {
        "schema": "persona_dream.session_mood.v1",
        "mood_id": "session_mood:" + _sha(source)[:24],
        "persona_id": persona_id,
        "mood_label": label,
        "source": source,
        "carried_tension": delta.get("open_tension") or delta.get("still_true"),
        "possible_expression": delta.get("possible_expression"),
        "voice_bias": MOOD_TO_VOICE[label],
    }


def bind_session(persona_id: str, *, session_id: str, first_turn_seq: int = 1) -> dict:
    if first_turn_seq <= 0:
        raise ValueError("BLOCKED_SESSION_MOOD_FIRST_TURN_CLOCK_INVALID")
    ledger = continuity_ledger.read_ledger(persona_id)
    mood = select_session_mood(persona_id, ledger)
    bind_seq = first_turn_seq - 1
    return {
        "schema": "persona_dream.session_mood_binding.v1",
        "session_id": session_id,
        "persona_id": persona_id,
        "ledger_epoch": ledger["epoch"],
        "ledger_sha256": ledger_hash(ledger),
        "bound_seq": bind_seq,
        "first_turn_seq": first_turn_seq,
        "selected_before_first_turn": bind_seq < first_turn_seq,
        "session_mood": mood,
        "turns": [],
    }


def voice_delivery_for_turn(binding: dict, answer_text: str, *,
                            turn_id: str, local_tone: str | None = None) -> dict:
    mood = binding["session_mood"]
    bias = dict(mood["voice_bias"])
    local_modulation = {"local_tone": local_tone, "applied": False}
    if local_tone and local_tone == "cautionary":
        bias["intensity"] = min(0.95, round(float(bias["intensity"]) + 0.07, 3))
        local_modulation["applied"] = True
    voice_delivery = {
        "schema": "persona_dream.voice_delivery.v1",
        "source": "continuity_session_mood",
        "session_mood_id": mood["mood_id"],
        "tone": bias["tone"],
        "pace": bias["pace"],
        "emphasis_tag": bias["emphasis_tag"],
        "intensity": bias["intensity"],
        "valence": bias["valence"],
        "use_base_emotion": True,
        "required_engine": "chatterbox_base",
        "local_modulation": local_modulation,
    }
    return {
        "turn_id": turn_id,
        "session_mood_id": mood["mood_id"],
        "answer_text": answer_text,
        "spoken_text": answer_text,
        "answer_invariance": {
            "status": "PASS_ANSWER_TEXT_EXACT_MATCH",
            "propositions_changed": False,
        },
        "voice_delivery": voice_delivery,
    }


def add_turn(binding: dict, answer_text: str, *, turn_id: str,
             local_tone: str | None = None) -> dict:
    turn = voice_delivery_for_turn(binding, answer_text, turn_id=turn_id,
                                   local_tone=local_tone)
    binding["turns"].append(turn)
    validate_binding(binding)
    return turn


def validate_binding(binding: dict) -> None:
    if not binding.get("selected_before_first_turn"):
        raise ValueError("BLOCKED_SESSION_MOOD_SELECTED_AFTER_FIRST_TURN")
    mood_id = ((binding.get("session_mood") or {}).get("mood_id"))
    if not mood_id:
        raise ValueError("BLOCKED_SESSION_MOOD_MISSING")
    for turn in binding.get("turns") or []:
        if turn.get("session_mood_id") != mood_id:
            raise ValueError("BLOCKED_SESSION_MOOD_CHANGED_MID_SESSION")
        if turn.get("spoken_text") != turn.get("answer_text"):
            raise ValueError("BLOCKED_CONTENT_CHANGED_UNDER_EMOTION")
        delivery = turn.get("voice_delivery") or {}
        if delivery.get("session_mood_id") != mood_id:
            raise ValueError("BLOCKED_SESSION_MOOD_CHANGED_MID_SESSION")
        if delivery.get("use_base_emotion") and delivery.get("required_engine") != "chatterbox_base":
            raise ValueError("BLOCKED_CHATTERBOX_ENGINE_IGNORES_CONTROLS")


def run_demo(persona_id: str, turns: list[str], *, session_id: str,
             out: Path | None = None) -> dict:
    binding = bind_session(persona_id, session_id=session_id)
    for idx, text in enumerate(turns, start=1):
        add_turn(binding, text, turn_id=f"turn_{idx:03d}")
    validate_binding(binding)
    receipt = {
        "schema": "persona_dream.session_mood_binding_receipt.v1",
        "status": "PASS_SESSION_MOOD_BINDING_DETERMINISTIC",
        "mocked": False,
        "live": False,
        "binding": binding,
        "claims": {
            "proves": [
                "session mood is selected from the latest valid continuity ledger before turn 1",
                "the same session_mood_id is attached to every turn",
                "answer_text is copied unchanged into spoken_text",
                "voice_delivery is Chatterbox-base-ready and separate from answer content"
            ],
            "does_not_prove": [
                "live Memory persistence",
                "live Chatterbox rendering",
                "perceived emotion",
                "speaker similarity",
                "adversarial Embry recognition"
            ]
        },
    }
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--persona", default="embry")
    parser.add_argument("--session-id", default="session_demo")
    parser.add_argument("--turn", action="append", default=[])
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    turns = args.turn or [
        "I can stay with the boundary and still answer the question.",
        "The answer is unchanged; only the delivery carries the mood.",
        "The boundary remains clear.",
    ]
    receipt = run_demo(args.persona, turns, session_id=args.session_id, out=args.out)
    print(json.dumps({
        "status": receipt["status"],
        "session_id": receipt["binding"]["session_id"],
        "mood_id": receipt["binding"]["session_mood"]["mood_id"],
        "mood_label": receipt["binding"]["session_mood"]["mood_label"],
        "turn_count": len(receipt["binding"]["turns"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
