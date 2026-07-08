"""Live wake-to-turn runner for Embry voice control.

The runner produces a real wake event from the deterministic wake contract,
feeds that event plus a voice-mode user question into the configured Embry
control endpoint, and writes a receipt. It does not claim hot-mic capture:
that remains a separate RealtimeSTT/browser proof.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

import httpx

from embry_voice_control.wake_word import WAKE_WORD
from embry_voice_control.wake_word import WAKE_WORD_CONTRACT
from embry_voice_control.wake_word import wake_word_detected


CAPITAL_FRANCE_QUESTION = "What is the capital of France?"
CAPITAL_FRANCE_EXPECTED = "Paris"


def now_iso() -> str:
    """Return an ISO UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def new_run_id() -> str:
    """Return a stable run id for receipt directories."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-wake-live-" + uuid4().hex[:8]


def write_json(path: Path, data: dict[str, Any]) -> None:
    """Write formatted JSON, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def normalize_url(base_url: str, suffix: str) -> str:
    """Join base URL and suffix without discarding path prefixes."""
    return f"{base_url.rstrip('/')}/{suffix.lstrip('/')}"


def normalize_text(text: str) -> str:
    """Normalize text for deterministic answer matching."""
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def nested_value(data: dict[str, Any], dotted_path: str) -> Any:
    """Return a nested value for dot-path checks."""
    value: Any = data
    for part in dotted_path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def has_any_field(data: dict[str, Any], field_expr: str) -> bool:
    """Return whether a field or alias is present."""
    return any(nested_value(data, part.strip()) is not None for part in field_expr.split("|"))


def compact_value(value: Any, depth: int = 0) -> Any:
    """Return a compact JSON-safe excerpt for receipts."""
    if depth > 4:
        return "<max-depth>"
    if isinstance(value, dict):
        return {key: compact_value(item, depth + 1) for key, item in list(value.items())[:40]}
    if isinstance(value, list):
        if len(value) > 8:
            return {"_type": "list", "count": len(value), "first": [compact_value(item, depth + 1) for item in value[:3]]}
        return [compact_value(item, depth + 1) for item in value]
    if isinstance(value, str) and len(value) > 500:
        return value[:500] + "...<truncated>"
    return value


def build_wake_event(run_id: str) -> dict[str, Any]:
    """Build the live runner wake event from the wake-word contract."""
    detected, reason = wake_word_detected(
        transcript=WAKE_WORD,
        confidence=0.96,
        current_state="idle",
        primary_speaker=True,
        now_ms=0,
        last_wake_ms=None,
    )
    transition = ["idle", "wake_detected", "listening"] if detected else ["idle"]
    return {
        "schema": "embry_voice_control.wake_event.v1",
        "event_id": f"{run_id}:wake",
        "created_at": now_iso(),
        "source": "embry_voice_control_live_runner",
        "wake_word": WAKE_WORD,
        "transcript": WAKE_WORD,
        "confidence": 0.96,
        "primary_speaker": True,
        "detected": detected,
        "reason": reason,
        "transition": transition,
        "ui_feedback": {
            "standby_instruction": WAKE_WORD_CONTRACT["standby_instruction"],
            "instruction_opacity": WAKE_WORD_CONTRACT["wake_ack_instruction_opacity"] if detected else 1.0,
            "subtitle": WAKE_WORD_CONTRACT["active_subtitle"] if detected else WAKE_WORD_CONTRACT["standby_subtitle"],
            "orb_state": "listening" if detected else "idle",
        },
        "hot_mic_wake_proven": False,
    }


def build_turn_payload(run_id: str, wake_event: dict[str, Any]) -> dict[str, Any]:
    """Return a voice-mode turn payload for the current Embry UX adapter."""
    return {
        "sessionId": f"embry-voice-control-live-{run_id}",
        "turnId": f"embry-voice-control-live-turn-{run_id}",
        "text": CAPITAL_FRANCE_QUESTION,
        "inputMode": "voice",
        "voiceEnabled": True,
        "chatEnabled": True,
        "replayEnabled": True,
        "wakeEvent": wake_event,
        "listenerEvidence": {
            "schema": "embry_voice_control.listener_evidence.v1",
            "source": "embry_voice_control_live_runner",
            "mode": "controlled_voice_turn_after_wake",
            "wake_event_id": wake_event["event_id"],
            "final_transcript": CAPITAL_FRANCE_QUESTION,
            "hot_mic": False,
            "browser_webrtc": False,
            "realtimestt": False,
        },
        "speakerEvidence": {
            "source": "controlled_primary_speaker_contract",
            "speaker_id": "horus_primary",
            "primary_speaker": True,
            "identity_resolution_required": True,
        },
        "requireMemoryIntentVoicePolicy": True,
        "requireInterruptPolicy": True,
    }


def response_json(response: httpx.Response) -> dict[str, Any]:
    """Return response JSON or a structured parse error."""
    try:
        data = response.json()
    except ValueError as exc:
        return {"_parse_error": str(exc), "_text_prefix": response.text[:500]}
    return data if isinstance(data, dict) else {"_json_value": data}


def post_live_turn(base_url: str, payload: dict[str, Any], timeout: float) -> tuple[int | None, dict[str, Any], str | None]:
    """POST the live turn to the configured control plane."""
    url = normalize_url(base_url, "live-turn")
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout, connect=2.0)) as client:
            response = client.post(url, json=payload)
            return response.status_code, response_json(response), None
    except httpx.HTTPError as exc:
        return None, {}, str(exc)


def evaluate_acceptance(
    *,
    wake_event: dict[str, Any],
    status_code: int | None,
    response: dict[str, Any],
    error: str | None,
) -> dict[str, Any]:
    """Evaluate the wake/control-plane run deterministically."""
    answer = str(response.get("answerText") or nested_value(response, "turnAuthority.assistantText") or "")
    normalized_answer = normalize_text(answer)
    required_fields = [
        "mocked",
        "live",
        "turnId|turnAuthority.turnId",
        "turnAuthority",
        "audioAuthority|turnAuthority.audioAuthority",
        "voicePolicy",
        "pause_strategy|pauseStrategy|voicePolicy.pause_strategy|voicePolicy.pauseStrategy",
        "interrupt_policy|interruptPolicy|voicePolicy.interrupt_policy|voicePolicy.interruptPolicy",
    ]
    missing_fields = [field for field in required_fields if not has_any_field(response, field)]
    if response.get("mocked") is True:
        missing_fields.append("mocked_false")
    if response.get("live") is False:
        missing_fields.append("live_true")
    checks = {
        "wake_event_produced": wake_event.get("detected") is True and wake_event.get("transition") == ["idle", "wake_detected", "listening"],
        "wake_event_fed_to_control_plane": nested_value(response, "turnAuthority.turnId") is not None or response.get("turnId") is not None,
        "control_plane_http_2xx": status_code is not None and 200 <= status_code < 300,
        "control_plane_status_ok": response.get("status") == "ok",
        "response_is_live": response.get("live") is True,
        "response_is_not_mocked": response.get("mocked") is False,
        "turn_authority_returned": has_any_field(response, "turnAuthority.turnId"),
        "audio_authority_returned": has_any_field(response, "audioAuthority|turnAuthority.audioAuthority"),
        "voice_policy_returned": has_any_field(response, "voicePolicy"),
        "final_answer_mentions_paris": "paris" in normalized_answer,
        "required_fields_present": not missing_fields,
        "used_ui": False,
        "hot_mic_wake_proven": False,
    }
    pass_value = all(
        value
        for key, value in checks.items()
        if key not in {"used_ui", "hot_mic_wake_proven"}
    )
    return {
        "pass": pass_value,
        "checks": checks,
        "missing_fields": sorted(set(missing_fields)),
        "error": error,
        "status_code": status_code,
        "answer_text": answer,
        "normalized_answer": normalized_answer,
        "expected_answer": CAPITAL_FRANCE_EXPECTED,
    }


def run_wake_capital_france(
    *,
    base_url: str,
    output_root: Path,
    timeout: float,
) -> dict[str, Any]:
    """Run wake -> live-turn -> Chatterbox authority proof and write receipts."""
    run_id = new_run_id()
    output_dir = output_root / "wake-capital-france" / run_id
    receipt_path = output_dir / "receipt.json"
    wake_event = build_wake_event(run_id)
    payload = build_turn_payload(run_id, wake_event)
    status_code, response, error = post_live_turn(base_url, payload, timeout)
    acceptance = evaluate_acceptance(
        wake_event=wake_event,
        status_code=status_code,
        response=response,
        error=error,
    )
    receipt = {
        "schema": "embry_voice_control.wake_capital_france_live_receipt.v1",
        "run_id": run_id,
        "created_at": now_iso(),
        "mocked": False,
        "live": True,
        "used_ui": False,
        "base_url": base_url,
        "endpoint": normalize_url(base_url, "live-turn"),
        "question": CAPITAL_FRANCE_QUESTION,
        "expected_answer": CAPITAL_FRANCE_EXPECTED,
        "wake_event": wake_event,
        "request_payload": payload,
        "response_status_code": status_code,
        "response_excerpt": compact_value(response),
        "acceptance": acceptance,
        "receipt_path": str(receipt_path),
        "claims": {
            "proves": [
                "A wake event can be produced from the Embry wake contract.",
                "The wake event and voice-mode question can be sent to the configured Embry control-plane live-turn endpoint.",
                "If acceptance.pass is true, the control plane returned live non-mocked turn/audio authority and answered Paris.",
            ],
            "does_not_prove": [
                "Hot microphone wake detection.",
                "Browser getUserMedia/WebRTC capture.",
                "RealtimeSTT listener recognition.",
                "Human-audible speaker playback.",
                "Browser Chat UX rendering.",
                "Orb visual sync.",
            ],
        },
    }
    write_json(receipt_path, receipt)
    write_json(
        output_root / "wake-capital-france" / "latest.json",
        {
            "run_id": run_id,
            "receipt_path": str(receipt_path),
            "pass": acceptance["pass"],
            "status_code": status_code,
            "answer_text": acceptance["answer_text"],
        },
    )
    return receipt
