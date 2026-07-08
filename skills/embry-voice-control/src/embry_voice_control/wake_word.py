"""Deterministic wake-word contract for Embry voice control.

Inputs are transcript-like wake candidates plus listener metadata. Outputs are
state-transition receipts that can be checked before any hot-mic, RealtimeSTT,
browser, Chatterbox, Tau, or memory integration is attempted. Failure modes are
explicit: low confidence, non-primary speaker, active cooldown, missing wake
word, or Embry currently speaking all fail closed.
"""

from __future__ import annotations

import re
from typing import Any

WAKE_WORD = "Embry"
WAKE_WORD_MIN_CONFIDENCE = 0.85
WAKE_WORD_COOLDOWN_MS = 1500
WAKE_WORD_CONTRACT = {
    "schema": "embry_voice_control.wake_word_contract.v1",
    "wake_word": WAKE_WORD,
    "normalized_wake_word": WAKE_WORD.lower(),
    "minimum_confidence": WAKE_WORD_MIN_CONFIDENCE,
    "cooldown_ms": WAKE_WORD_COOLDOWN_MS,
    "require_primary_speaker": True,
    "ignore_while_embry_speaking": True,
    "standby_instruction": 'SAY "EMBRY"',
    "standby_subtitle": "READY",
    "wake_ack_instruction_opacity": 0.2,
    "active_subtitle": "LISTENING...",
    "state_sequence": ["idle", "wake_detected", "listening"],
}


def normalize_wake_text(text: str) -> list[str]:
    """Return lowercase word tokens for wake-word matching."""
    return re.findall(r"[a-z0-9']+", text.lower())


def wake_word_detected(
    *,
    transcript: str,
    confidence: float,
    current_state: str,
    primary_speaker: bool,
    now_ms: int,
    last_wake_ms: int | None = None,
) -> tuple[bool, str]:
    """Evaluate the deterministic Embry wake-word gate."""
    if current_state == "speaking" and WAKE_WORD_CONTRACT["ignore_while_embry_speaking"]:
        return False, "ignored_while_embry_speaking"
    if not primary_speaker and WAKE_WORD_CONTRACT["require_primary_speaker"]:
        return False, "primary_speaker_required"
    if confidence < WAKE_WORD_MIN_CONFIDENCE:
        return False, "confidence_below_threshold"
    if last_wake_ms is not None and now_ms - last_wake_ms < WAKE_WORD_COOLDOWN_MS:
        return False, "cooldown_active"
    if WAKE_WORD.lower() not in normalize_wake_text(transcript):
        return False, "wake_word_absent"
    return True, "wake_word_detected"


def run_wake_word_sanity(run_id: str) -> dict[str, Any]:
    """Run deterministic wake-word contract checks and return a receipt."""
    last_wake_ms: int | None = None
    events: list[dict[str, Any]] = []
    cases = [
        {
            "id": "ambient-no-wake",
            "transcript": "continue the review queue",
            "confidence": 0.98,
            "primary_speaker": True,
            "current_state": "idle",
            "now_ms": 0,
            "expected_detected": False,
            "expected_state": "idle",
        },
        {
            "id": "low-confidence-wake",
            "transcript": "Embry",
            "confidence": 0.52,
            "primary_speaker": True,
            "current_state": "idle",
            "now_ms": 500,
            "expected_detected": False,
            "expected_state": "idle",
        },
        {
            "id": "primary-speaker-wake",
            "transcript": "Embry",
            "confidence": 0.91,
            "primary_speaker": True,
            "current_state": "idle",
            "now_ms": 2500,
            "expected_detected": True,
            "expected_state": "listening",
        },
        {
            "id": "cooldown-repeat",
            "transcript": "Embry",
            "confidence": 0.93,
            "primary_speaker": True,
            "current_state": "idle",
            "now_ms": 3100,
            "expected_detected": False,
            "expected_state": "idle",
        },
        {
            "id": "non-primary-wake",
            "transcript": "Embry",
            "confidence": 0.94,
            "primary_speaker": False,
            "current_state": "idle",
            "now_ms": 5200,
            "expected_detected": False,
            "expected_state": "idle",
        },
        {
            "id": "ignore-while-speaking",
            "transcript": "Embry",
            "confidence": 0.95,
            "primary_speaker": True,
            "current_state": "speaking",
            "now_ms": 7000,
            "expected_detected": False,
            "expected_state": "speaking",
        },
    ]
    for case in cases:
        detected, reason = wake_word_detected(
            transcript=str(case["transcript"]),
            confidence=float(case["confidence"]),
            current_state=str(case["current_state"]),
            primary_speaker=bool(case["primary_speaker"]),
            now_ms=int(case["now_ms"]),
            last_wake_ms=last_wake_ms,
        )
        if detected:
            last_wake_ms = int(case["now_ms"])
            transition = ["idle", "wake_detected", "listening"]
            state = "listening"
            ui_feedback = {
                "instruction": WAKE_WORD_CONTRACT["standby_instruction"],
                "instruction_opacity": WAKE_WORD_CONTRACT["wake_ack_instruction_opacity"],
                "subtitle": WAKE_WORD_CONTRACT["active_subtitle"],
                "orb_state": "listening",
            }
        else:
            transition = [str(case["current_state"])]
            state = str(case["current_state"])
            ui_feedback = {
                "instruction": WAKE_WORD_CONTRACT["standby_instruction"],
                "instruction_opacity": 1.0,
                "subtitle": WAKE_WORD_CONTRACT["standby_subtitle"] if state == "idle" else state.upper(),
                "orb_state": state,
            }
        passed = detected is case["expected_detected"] and state == case["expected_state"]
        events.append({
            "id": case["id"],
            "transcript": case["transcript"],
            "confidence": case["confidence"],
            "primary_speaker": case["primary_speaker"],
            "input_state": case["current_state"],
            "detected": detected,
            "reason": reason,
            "transition": transition,
            "output_state": state,
            "ui_feedback": ui_feedback,
            "expected_detected": case["expected_detected"],
            "expected_state": case["expected_state"],
            "pass": passed,
        })
    failed = [event for event in events if not event["pass"]]
    return {
        "schema": "embry_voice_control.wake_word_sanity_receipt.v1",
        "run_id": run_id,
        "mocked": False,
        "live": False,
        "exercised": "deterministic wake-word contract only; no microphone, RealtimeSTT, Chatterbox, Tau, memory, browser, or orb runtime",
        "contract": WAKE_WORD_CONTRACT,
        "events": events,
        "acceptance": {
            "wake_word_is_embry": WAKE_WORD == "Embry",
            "standby_instruction_is_say_embry": WAKE_WORD_CONTRACT["standby_instruction"] == 'SAY "EMBRY"',
            "idle_to_wake_detected_to_listening": any(
                event["transition"] == ["idle", "wake_detected", "listening"] and event["pass"]
                for event in events
            ),
            "low_confidence_rejected": any(event["id"] == "low-confidence-wake" and event["pass"] for event in events),
            "cooldown_rejected": any(event["id"] == "cooldown-repeat" and event["pass"] for event in events),
            "non_primary_rejected": any(event["id"] == "non-primary-wake" and event["pass"] for event in events),
            "speaking_self_audio_ignored": any(event["id"] == "ignore-while-speaking" and event["pass"] for event in events),
            "pass": not failed,
        },
        "claims": {
            "proves": [
                'The wake word contract uses "Embry".',
                'The standby prompt is SAY "EMBRY".',
                "A high-confidence primary-speaker Embry event transitions idle -> wake_detected -> listening.",
                "Low-confidence, cooldown, non-primary, and while-speaking wake attempts fail closed.",
            ],
            "does_not_prove": [
                "Hot microphone capture.",
                "RealtimeSTT wake-word recognition accuracy.",
                "Speaker verification from raw audio.",
                "Shared Chat UX rendering.",
                "Embry orb visual state in browser.",
                "Chatterbox playback.",
            ],
        },
    }
