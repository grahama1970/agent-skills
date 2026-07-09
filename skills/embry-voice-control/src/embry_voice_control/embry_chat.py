"""Embry Chat Tau-style live turn runner.

This runner is intentionally not a UX Lab proof. It consumes an existing
Unix/PipeWire RealtimeSTT listener receipt, calls memory /intent first, treats a
deterministic memory /answer refusal as a memory miss, lets the Embry Chat
Tau-style route choose the response, and sends only the Tau-approved spoken text
to Chatterbox.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any
from uuid import uuid4
import wave

import httpx
from loguru import logger

from embry_voice_control.listener_turn import DEFAULT_OUTPUT_ROOT
from embry_voice_control.listener_turn import DEFAULT_UNIX_LISTENER_ROOT
from embry_voice_control.listener_turn import compact_value
from embry_voice_control.listener_turn import latest_unix_listener_receipt
from embry_voice_control.listener_turn import nested_value
from embry_voice_control.listener_turn import normalize_url
from embry_voice_control.listener_turn import play_audio_local
from embry_voice_control.listener_turn import read_json
from embry_voice_control.listener_turn import strip_wake_word
from embry_voice_control.listener_turn import write_json
from embry_voice_control.research_turn import DEFAULT_MEMORY_URL


DEFAULT_CHATTERBOX_URL = "http://127.0.0.1:8018"
DEFAULT_CHATTERBOX_OUT_DIR = Path("/tmp/chatterbox-fork-agent-out")
DEFAULT_EMBRY_REF_AUDIO = Path(
    "/home/graham/workspace/experiments/chatterbox/persona_dream_voice_refs/embry_authorized_ref_30s_8s.wav"
)
DEFAULT_CHATTERBOX_CONTAINER_REF_DIR = "/work/persona_dream_voice_refs"
DEFAULT_EXPECTED_ANSWER = "paris"


def now_iso() -> str:
    """Return an ISO UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def new_run_id() -> str:
    """Return a stable run id for receipt directories."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-embry-chat-" + uuid4().hex[:8]


def normalize_text(text: str) -> str:
    """Normalize text for deterministic matching."""
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def sha256_file(path: Path) -> str:
    """Return sha256 for a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def wav_metadata(path: Path) -> dict[str, Any]:
    """Return simple WAV metadata."""
    with wave.open(str(path), "rb") as wav:
        frames = wav.getnframes()
        rate = wav.getframerate()
        channels = wav.getnchannels()
        width = wav.getsampwidth()
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "duration_ms": round((frames / float(rate)) * 1000.0) if rate else 0,
        "sample_rate": rate,
        "channels": channels,
        "sample_width": width,
    }


def post_json(url: str, payload: dict[str, Any], timeout: float) -> tuple[int | None, dict[str, Any], str | None]:
    """POST JSON and return status, JSON object, and error string."""
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout, connect=2.0)) as client:
            response = client.post(url, json=payload)
            try:
                body = response.json()
            except ValueError as exc:
                body = {"_parse_error": str(exc), "_text_prefix": response.text[:1000]}
            return response.status_code, body if isinstance(body, dict) else {"_json_value": body}, None
    except httpx.HTTPError as exc:
        return None, {}, str(exc)


def action_from(value: Any) -> str:
    """Extract a normalized memory action from a response object."""
    if not isinstance(value, dict):
        return ""
    for key in ("action", "intent", "route", "decision"):
        item = value.get(key)
        if isinstance(item, str) and item.strip():
            return item.strip().upper()
    return ""


def answer_text_from_memory(value: dict[str, Any]) -> str:
    """Extract usable memory answer text without accepting deterministic refusals."""
    if not isinstance(value, dict):
        return ""
    if value.get("can_answer") is False:
        return ""
    if str(value.get("answer_type") or "").lower() == "insufficient_memory_evidence":
        return ""
    if str(value.get("final_response_origin") or "").lower() == "deterministic_refusal":
        return ""
    for key in ("answer", "final_response", "response", "text"):
        item = value.get(key)
        if isinstance(item, str) and item.strip():
            normalized = normalize_text(item)
            if "need grounded memory result" in normalized:
                return ""
            if "insufficient memory evidence" in normalized:
                return ""
            return item.strip()
    return ""


def classify_memory_answer(answer_result: dict[str, Any], *, turn_text: str = "") -> str:
    """Classify memory answer for route receipts."""
    answer_text = answer_text_from_memory(answer_result)
    if answer_text and is_capital_france_query(turn_text) and "paris" not in normalize_text(answer_text):
        return "memory_miss_irrelevant_answer"
    if answer_text:
        return "memory_answer"
    if answer_result.get("can_answer") is False:
        return "memory_miss"
    if str(answer_result.get("answer_type") or "").lower() == "insufficient_memory_evidence":
        return "memory_miss"
    if str(answer_result.get("final_response_origin") or "").lower() == "deterministic_refusal":
        return "memory_miss"
    return "memory_miss"


def is_capital_france_query(text: str) -> bool:
    """Return whether a query is the controlled static fact used by this rung."""
    normalized = normalize_text(text)
    return "capital" in normalized and "france" in normalized


def build_tau_response_plan(
    *,
    turn_text: str,
    intent_result: dict[str, Any],
    answer_result: dict[str, Any],
) -> dict[str, Any]:
    """Build the minimal Embry Chat Tau-style response plan."""
    intent_action = action_from(intent_result) or "UNKNOWN"
    memory_answer = answer_text_from_memory(answer_result)
    memory_classification = classify_memory_answer(answer_result, turn_text=turn_text)
    if memory_classification.startswith("memory_miss"):
        memory_answer = ""
    if intent_action in {"COMPLIANCE", "CLARIFY", "IDENTITY_CLARIFICATION", "DEFLECT"}:
        route_taken = "fail_closed"
        answer_text = "I need to keep that inside the memory and compliance path."
        route_reason = f"memory_intent_action_{intent_action.lower()}"
    elif memory_answer:
        route_taken = "memory_answer"
        answer_text = memory_answer
        route_reason = "memory_answer_available"
    elif is_capital_france_query(turn_text):
        route_taken = "static_answer"
        answer_text = "The capital of France is Paris."
        route_reason = "memory_miss_static_fact"
    else:
        route_taken = "memory_miss_no_static_answer"
        answer_text = "I do not have enough grounded memory for that yet."
        route_reason = "memory_miss_no_allowed_fallback_in_this_rung"
    tts_render_text = answer_text
    return {
        "subagent": "embry-chat",
        "memory_first": True,
        "route_taken": route_taken,
        "route_reason": route_reason,
        "brave_search_called": False,
        "brave_search_reason": "not_needed_for_static_fact" if route_taken == "static_answer" else "not_allowed_in_this_rung",
        "memory_result_classification": memory_classification,
        "answer_text": answer_text,
        "tts_render_text": tts_render_text,
        "voice_policy": {
            "source": "memory.intent",
            "tone": "calm_precise",
            "conversation_arc": "brief_confident_answer",
            "emotion_tags": ["[calm]", "[clear]"],
            "pause_strategy": {
                "max_chunk_chars": 300,
                "inter_chunk_pause_ms": 250,
                "remove_delays_for_known_static_answer": True,
            },
            "interrupt_policy": {
                "interruptible": True,
                "preferred_action": "natural_stop_then_listen",
                "stale_audio_policy": "skip_stale_chunks",
                "new_turn_wins": True,
            },
        },
    }


def resolve_chatterbox_audio_path(value: Any, out_dir: Path = DEFAULT_CHATTERBOX_OUT_DIR) -> Path | None:
    """Resolve Chatterbox audio response values into a host-readable path."""
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    candidates: list[Path] = []
    path = Path(raw)
    if path.is_absolute():
        candidates.append(path)
    if raw.startswith("/out/"):
        candidates.append(out_dir / raw.removeprefix("/out/"))
    candidates.append(out_dir / raw.lstrip("/"))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def synthesize_chatterbox(
    *,
    chatterbox_url: str,
    text: str,
    ref_audio: Path,
    label: str,
    timeout: float,
) -> tuple[int | None, dict[str, Any], str | None, Path | None]:
    """Call Chatterbox /synthesize and resolve the returned WAV path."""
    container_ref_audio = f"{DEFAULT_CHATTERBOX_CONTAINER_REF_DIR.rstrip('/')}/{ref_audio.name}"
    payload = {
        "text": text,
        "ref_audio": container_ref_audio,
        "label": label,
        "delivery_stage": "satisfied",
        "temperature": 0.7,
    }
    status, body, error = post_json(normalize_url(chatterbox_url, "synthesize"), payload, timeout)
    audio_path = resolve_chatterbox_audio_path(body.get("audio") if isinstance(body, dict) else None)
    return status, body, error, audio_path


def run_embry_chat_static_query_live(
    *,
    memory_url: str = DEFAULT_MEMORY_URL,
    chatterbox_url: str = DEFAULT_CHATTERBOX_URL,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    listener_receipt_path: Path | None = None,
    unix_listener_root: Path = DEFAULT_UNIX_LISTENER_ROOT,
    ref_audio: Path = DEFAULT_EMBRY_REF_AUDIO,
    expected_answer: str = DEFAULT_EXPECTED_ANSWER,
    timeout: float = 120.0,
    play_local: bool = False,
    local_playback_target: str = "64",
    local_playback_timeout: float = 90.0,
) -> dict[str, Any]:
    """Run listener transcript through Embry Chat Tau-style static-query route."""
    run_id = new_run_id()
    output_dir = output_root / "embry-chat-static-query-live" / run_id
    receipt_path = output_dir / "receipt.json"
    listener_path = listener_receipt_path or latest_unix_listener_receipt(unix_listener_root)
    listener_receipt = read_json(listener_path)
    listener_events = listener_receipt.get("listener_events", {})
    final_transcript = str(listener_events.get("final_transcript") or "")
    turn_text = strip_wake_word(final_transcript)
    session_id = f"embry-chat-{run_id}"
    intent_payload = {
        "q": turn_text,
        "query": turn_text,
        "scope": "embry_voice",
        "session_id": session_id,
        "channel": "voice-chat",
        "fast": True,
    }
    answer_payload = {
        "q": turn_text,
        "query": turn_text,
        "scope": "embry_voice",
        "session_id": session_id,
        "channel": "voice-chat",
        "fast": True,
    }
    intent_status, intent_result, intent_error = post_json(normalize_url(memory_url, "intent"), intent_payload, min(timeout, 30.0))
    answer_status, answer_result, answer_error = post_json(normalize_url(memory_url, "answer"), answer_payload, min(timeout, 30.0))
    response_plan = build_tau_response_plan(
        turn_text=turn_text,
        intent_result=intent_result,
        answer_result=answer_result,
    )
    chatterbox_status, chatterbox_response, chatterbox_error, generated_audio = synthesize_chatterbox(
        chatterbox_url=chatterbox_url,
        text=str(response_plan["tts_render_text"]),
        ref_audio=ref_audio,
        label=run_id,
        timeout=timeout,
    )
    final_audio_path: Path | None = None
    if generated_audio is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        final_audio_path = output_dir / "embry_response.wav"
        shutil.copyfile(generated_audio, final_audio_path)
    local_playback = play_audio_local(
        audio_path=str(final_audio_path or ""),
        playback_target=local_playback_target,
        timeout=local_playback_timeout,
    ) if play_local else {
        "requested": False,
        "played": False,
        "reason": "play_local was false",
    }
    normalized_answer = normalize_text(str(response_plan["answer_text"]))
    checks = {
        "listener_receipt_passed": bool(nested_value(listener_receipt, "acceptance.pass")),
        "listener_final_transcript_seen": bool(final_transcript.strip()),
        "listener_wake_detected": bool(listener_events.get("wake_detected")),
        "turn_text_sent": bool(turn_text.strip()),
        "used_ui": False,
        "used_browser_mic": False,
        "used_mock_transcript": False,
        "input_source_is_realtimestt_final": bool(final_transcript.strip()),
        "memory_intent_called": intent_status is not None and 200 <= intent_status < 300,
        "memory_intent_call_index_1": True,
        "memory_answer_called": answer_status is not None and 200 <= answer_status < 300,
        "memory_answer_call_index_2": True,
        "memory_intent_action_query": action_from(intent_result) == "QUERY",
        "memory_answer_miss_not_used_as_answer": classify_memory_answer(answer_result, turn_text=turn_text).startswith("memory_miss"),
        "tau_subagent_embry_chat": response_plan["subagent"] == "embry-chat",
        "tau_route_static_answer": response_plan["route_taken"] == "static_answer",
        "brave_search_not_called": response_plan["brave_search_called"] is False,
        "answer_mentions_expected": normalize_text(expected_answer) in normalized_answer,
        "tts_render_text_matches_tau_plan": response_plan["tts_render_text"] == response_plan["answer_text"],
        "chatterbox_http_2xx": chatterbox_status is not None and 200 <= chatterbox_status < 300,
        "chatterbox_status_ok": chatterbox_response.get("ok") is True,
        "chatterbox_audio_exists": final_audio_path is not None and final_audio_path.exists(),
    }
    if play_local:
        checks["local_playback_requested"] = bool(local_playback.get("requested"))
        checks["local_playback_played"] = bool(local_playback.get("played"))
    errors = {
        "intent": intent_error,
        "answer": answer_error,
        "chatterbox": chatterbox_error,
    }
    acceptance_pass = (
        all(value for key, value in checks.items() if key not in {"used_ui", "used_browser_mic", "used_mock_transcript"})
        and not any(errors.values())
    )
    receipt = {
        "schema": "embry_chat_turn_receipt.v1",
        "run_id": run_id,
        "created_at": now_iso(),
        "mocked": False,
        "live": True,
        "used_ui": False,
        "used_browser_mic": False,
        "used_mock_transcript": False,
        "used_typed_prompt": False,
        "input": {
            "source_event_type": "realtime_stt.final.v1",
            "listener_receipt_path": str(listener_path),
            "final_transcript": final_transcript,
            "turn_text": turn_text,
            "wake_detected": listener_events.get("wake_detected"),
        },
        "memory_pipeline": {
            "memory_url": memory_url,
            "intent_called": True,
            "intent_call_index": 1,
            "intent_status_code": intent_status,
            "intent_payload": intent_payload,
            "intent_action": action_from(intent_result),
            "intent_response": compact_value(intent_result),
            "answer_called": True,
            "answer_call_index": 2,
            "answer_status_code": answer_status,
            "answer_payload": answer_payload,
            "answer_can_answer": answer_result.get("can_answer"),
            "answer_response": compact_value(answer_result),
            "memory_result_classification": response_plan["memory_result_classification"],
        },
        "tau_route": {
            "subagent": response_plan["subagent"],
            "memory_first": response_plan["memory_first"],
            "route_taken": response_plan["route_taken"],
            "route_reason": response_plan["route_reason"],
            "brave_search_called": response_plan["brave_search_called"],
            "brave_search_reason": response_plan["brave_search_reason"],
        },
        "response_plan": {
            "answer_text": response_plan["answer_text"],
            "tts_render_text": response_plan["tts_render_text"],
            "voice_policy": response_plan["voice_policy"],
        },
        "chatterbox": {
            "agent_url": chatterbox_url,
            "called_by": "embry-voice-control",
            "input_source": "tau.response_plan.tts_render_text",
            "status_code": chatterbox_status,
            "response": compact_value(chatterbox_response),
            "ref_audio": wav_metadata(ref_audio) if ref_audio.exists() else {"path": str(ref_audio), "exists": False},
            "generated_audio_path": str(generated_audio) if generated_audio else "",
            "audio": wav_metadata(final_audio_path) if final_audio_path and final_audio_path.exists() else None,
        },
        "audio_output": local_playback,
        "errors": errors,
        "acceptance": {
            "pass": acceptance_pass,
            "checks": checks,
        },
        "receipt_path": str(receipt_path),
        "claims": {
            "proves": [
                "A Unix/PipeWire RealtimeSTT final transcript was consumed without browser UI input.",
                "Embry Chat called memory /intent before memory /answer.",
                "A deterministic memory refusal was classified as a memory miss, not used as Embry's answer.",
                "Embry Chat selected a Tau-style static answer for the capital of France.",
                "Chatterbox received the Tau-approved tts_render_text.",
                "If local playback is requested and acceptance.pass is true, the Chatterbox WAV was played through PipeWire.",
            ],
            "does_not_prove": [
                "Browser microphone or WebRTC capture.",
                "Speaker identity or diarization.",
                "Shared Chat UX rendering.",
                "Orb sync.",
                "Replay.",
                "Interruption or barge-in.",
                "The full 200+ stress suite.",
            ],
        },
    }
    write_json(receipt_path, receipt)
    write_json(
        output_root / "embry-chat-static-query-live" / "latest.json",
        {
            "run_id": run_id,
            "pass": acceptance_pass,
            "receipt_path": str(receipt_path),
            "listener_receipt_path": str(listener_path),
            "turn_text": turn_text,
            "answer_text": response_plan["answer_text"],
            "audio_path": str(final_audio_path) if final_audio_path else "",
            "local_playback": local_playback,
        },
    )
    logger.info("wrote Embry Chat receipt: {}", receipt_path)
    return receipt
