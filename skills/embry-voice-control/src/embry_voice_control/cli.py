"""Live sanity harness for Embry voice control.

Inputs are configured endpoint URLs and optional scenario text. Outputs are
machine-readable readiness receipts under the 12TB artifact directory. Failure
modes are explicit: missing services, missing fields, stale turn authority, or
mocked responses produce readiness gaps instead of passing.
"""

from __future__ import annotations

from datetime import datetime, timezone
import html
import json
from pathlib import Path
import struct
import time
from typing import Any
from urllib.parse import urlparse, urlunparse
from uuid import uuid4
import wave

import httpx
from loguru import logger
import typer
from websockets.sync.client import connect as websocket_connect

from embry_voice_control.live_wake import run_wake_capital_france
from embry_voice_control.listener_turn import DEFAULT_BASE_URL as LISTENER_TURN_BASE_URL
from embry_voice_control.listener_turn import DEFAULT_EXPECTED_ANSWER
from embry_voice_control.listener_turn import DEFAULT_OUTPUT_ROOT as LISTENER_TURN_OUTPUT_ROOT
from embry_voice_control.listener_turn import DEFAULT_UNIX_LISTENER_ROOT
from embry_voice_control.listener_turn import run_listener_turn_live
from embry_voice_control.unix_listener import DEFAULT_EXPECTED_PHRASE as UNIX_LISTENER_EXPECTED_PHRASE
from embry_voice_control.unix_listener import DEFAULT_OUTPUT_ROOT as UNIX_LISTENER_OUTPUT_ROOT
from embry_voice_control.unix_listener import DEFAULT_PROOF_SCRIPT
from embry_voice_control.unix_listener import DEFAULT_REALTIMESTT_PYTHON
from embry_voice_control.unix_listener import DEFAULT_REALTIMESTT_REPO
from embry_voice_control.unix_listener import run_unix_listener_sanity
from embry_voice_control.wake_word import WAKE_WORD
from embry_voice_control.wake_word import run_wake_word_sanity


app = typer.Typer(help="Embry voice control live sanity harness.")

DEFAULT_OUTPUT_ROOT = Path("/mnt/storage12tb/skills/embry-voice-control/outputs/e2e")
DEFAULT_BASE_URL = "http://127.0.0.1:3001/api/projects/embry-voice"
DEFAULT_CHAT_URL = "http://127.0.0.1:3002/#embry-voice"
DEFAULT_REALTIMESTT_URL = "http://127.0.0.1:8010"
DEFAULT_LISTENER_AUDIO = Path("/tmp/chatterbox-fork-agent-out/browser-webrtc-horus-loud-20260703T133629Z.wav")
DEFAULT_INTERRUPT_POLICY = {
    "interruptible": True,
    "barge_in_action": "cancel_old_turn",
    "duck_on_user_speech": True,
    "skip_stale_chunks": True,
    "new_turn_wins": True,
    "acknowledgement_tone": "interrupted",
    "acknowledgement_text": "Okay, stopping that.",
}


def http_to_ws_url(base_url: str, suffix: str) -> str:
    """Return a websocket URL from an HTTP base URL and suffix."""
    parsed = urlparse(base_url.rstrip("/"))
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunparse((scheme, parsed.netloc, suffix, "", "", ""))


def utc_now() -> str:
    """Return an ISO UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def normalize_url(base_url: str, suffix: str) -> str:
    """Join a base URL and suffix without losing local API path prefixes."""
    return f"{base_url.rstrip('/')}/{suffix.lstrip('/')}"


def write_json(path: Path, data: dict[str, Any]) -> None:
    """Write formatted JSON to a path, creating parents as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def write_html(path: Path, report: dict[str, Any]) -> None:
    """Write a small human-readable view over report.json."""
    rows = []
    for case in report["cases"]:
        rows.append(
            "<tr>"
            f"<td>{html.escape(case['id'])}</td>"
            f"<td>{html.escape(case['readiness'])}</td>"
            f"<td>{html.escape(case['assertion_status'])}</td>"
            f"<td>{html.escape(', '.join(case.get('missing_fields', [])))}</td>"
            "</tr>"
        )
    body = "\n".join(rows)
    page = f"""<!doctype html>
<html>
<head><meta charset="utf-8"><title>Embry Voice Control Sanity</title></head>
<body>
<h1>Embry Voice Control Sanity</h1>
<p>Run: {html.escape(report['run_id'])}</p>
<p>Overall: {html.escape(report['overall_readiness'])}</p>
<table border="1" cellspacing="0" cellpadding="6">
<thead><tr><th>Case</th><th>Readiness</th><th>Assertion</th><th>Missing</th></tr></thead>
<tbody>{body}</tbody>
</table>
</body>
</html>
"""
    path.write_text(page, encoding="utf-8")


def read_pcm16_wav(path: Path) -> tuple[int, int, bytes]:
    """Read a PCM16 WAV file and return sample rate, channels, and audio bytes."""
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        sample_rate = wav.getframerate()
        frames = wav.getnframes()
        if sample_width != 2:
            raise ValueError(f"{path} must be 16-bit PCM; got sample width {sample_width}")
        return sample_rate, channels, wav.readframes(frames)


def pcm16_audio_stats(sample_rate: int, channels: int, pcm: bytes, *, frame_ms: int = 20) -> dict[str, Any]:
    """Return basic audio level stats for a PCM16 mono/stereo buffer."""
    samples = struct.unpack(f"<{len(pcm) // 2}h", pcm) if pcm else ()
    if channels > 1:
        usable = len(samples) - (len(samples) % channels)
        mono = [
            sum(samples[index:index + channels]) / float(channels)
            for index in range(0, usable, channels)
        ]
    else:
        mono = [float(sample) for sample in samples]
    if not mono:
        return {
            "sample_rate": sample_rate,
            "channels": channels,
            "duration_seconds": 0.0,
            "peak_abs": 0,
            "rms": 0.0,
            "rms_dbfs": None,
            "non_silent_frame_ratio_250_rms": 0.0,
            "non_silent_frame_ratio_5_rms": 0.0,
        }
    peak = max(abs(sample) for sample in mono)
    rms = (sum(sample * sample for sample in mono) / len(mono)) ** 0.5
    frame_samples = max(1, int(sample_rate * frame_ms / 1000.0))
    frame_rms_values = []
    for offset in range(0, len(mono), frame_samples):
        frame = mono[offset:offset + frame_samples]
        if frame:
            frame_rms_values.append((sum(sample * sample for sample in frame) / len(frame)) ** 0.5)
    def ratio(threshold: float) -> float:
        if not frame_rms_values:
            return 0.0
        return sum(1 for value in frame_rms_values if value >= threshold) / float(len(frame_rms_values))
    dbfs = None
    if rms > 0:
        import math

        dbfs = 20.0 * math.log10(rms / 32768.0)
    return {
        "sample_rate": sample_rate,
        "channels": channels,
        "duration_seconds": round(len(mono) / float(sample_rate), 3),
        "peak_abs": int(round(peak)),
        "rms": round(float(rms), 3),
        "rms_dbfs": round(float(dbfs), 2) if dbfs is not None else None,
        "non_silent_frame_ratio_250_rms": round(ratio(250.0), 4),
        "non_silent_frame_ratio_5_rms": round(ratio(5.0), 4),
    }


def encode_realtimestt_packet(metadata: dict[str, Any], audio: bytes) -> bytes:
    """Encode a RealtimeSTT browser audio packet."""
    metadata_bytes = json.dumps(metadata, separators=(",", ":")).encode("utf-8")
    return struct.pack("<I", len(metadata_bytes)) + metadata_bytes + audio


def drain_ws_events(ws: Any, events: list[dict[str, Any]], *, timeout: float = 0.001) -> None:
    """Drain currently available JSON websocket events into a list."""
    while True:
        try:
            raw = ws.recv(timeout=timeout)
        except TimeoutError:
            return
        except Exception as exc:
            if exc.__class__.__name__ in {"ConnectionClosed", "ConnectionClosedOK"}:
                return
            raise
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            event = {"type": "unparsed", "raw": str(raw)[:500]}
        if isinstance(event, dict):
            events.append(event)


def listener_case_result(
    *,
    case_id: str,
    listener_url: str,
    data: dict[str, Any],
    exercised: str,
    required_fields: list[str],
    error: str | None = None,
) -> dict[str, Any]:
    """Build a standard result for a direct RealtimeSTT listener proof."""
    missing = missing_fields(data, required_fields)
    if "final_transcript" in required_fields and not str(data.get("final_transcript", "")).strip():
        missing.append("final_transcript_nonempty")
    assertion_pass = not error and not missing
    return {
        "id": case_id,
        "method": "WS",
        "url": listener_url,
        "status_code": 101 if data.get("websocket_connected") else None,
        "mocked": data.get("mocked"),
        "live": data.get("live"),
        "execution_status": "pass" if data.get("websocket_connected") else "error",
        "assertion_status": "pass" if assertion_pass else "fail",
        "readiness": "usable" if assertion_pass else "not_established",
        "required_fields": required_fields,
        "missing_fields": sorted(set(missing)),
        "error": error,
        "exercised": exercised,
        "request_excerpt": compact_value(data.get("request", {})),
        "response_excerpt": compact_value(data),
    }


def run_realtimestt_listener_case(
    *,
    listener_url: str,
    audio_path: Path,
    output_dir: Path,
    run_id: str,
    timeout: float,
) -> dict[str, Any]:
    """Stream a browser-shaped WAV packet sequence into RealtimeSTT and capture transcript events."""
    receipt_path = output_dir / "listener-webrtc-realtimestt.json"
    ws_url = http_to_ws_url(listener_url, "/ws/transcribe")
    started_at = utc_now()
    events: list[dict[str, Any]] = []
    data: dict[str, Any] = {
        "schema": "embry_voice_control.listener_webrtc_realtimestt.v1",
        "mocked": False,
        "live": True,
        "capture_source": "browser_webrtc_pcm16_wav_loopback",
        "audio_path": str(audio_path),
        "listener_url": listener_url,
        "websocket_url": ws_url,
        "websocket_connected": False,
        "listener_state": "not_started",
        "asr_engine": "RealtimeSTT",
        "vad_enabled": True,
        "diarization_enabled": False,
        "receipt_path": str(receipt_path),
        "request": {"run_id": run_id, "audio_path": str(audio_path)},
        "events": events,
        "started_at": started_at,
    }
    try:
        sample_rate, channels, pcm = read_pcm16_wav(audio_path)
        bytes_per_frame = channels * 2
        frames_total = len(pcm) // bytes_per_frame
        chunk_frames = max(1, sample_rate // 50)
        chunk_bytes = chunk_frames * bytes_per_frame
        stats = pcm16_audio_stats(sample_rate, channels, pcm)
        data["audio"] = {
            "sample_rate": sample_rate,
            "channels": channels,
            "frames": frames_total,
            "duration_seconds": frames_total / float(sample_rate),
            "bytes": len(pcm),
            "stats": stats,
            "quality_notes": [
                "WebRTC VAD may reject quiet files even when energy VAD would pass.",
                "Compare failed runs against peak_abs, rms, and non_silent_frame_ratio_250_rms.",
            ],
        }
        with websocket_connect(ws_url, open_timeout=min(5.0, timeout)) as ws:
            data["websocket_connected"] = True
            deadline = time.monotonic() + timeout
            drain_ws_events(ws, events, timeout=1.0)
            ws.send(json.dumps({"type": "start"}))
            data["listener_state"] = "streaming"
            drain_ws_events(ws, events, timeout=0.1)
            offset = 0
            while offset < len(pcm):
                chunk = pcm[offset: offset + chunk_bytes]
                offset += len(chunk)
                frames = len(chunk) // bytes_per_frame
                packet = encode_realtimestt_packet(
                    {
                        "sampleRate": sample_rate,
                        "channels": channels,
                        "format": "pcm_s16le",
                        "frames": frames,
                    },
                    chunk,
                )
                ws.send(packet)
                drain_ws_events(ws, events)
                time.sleep(frames / float(sample_rate))
                if time.monotonic() > deadline:
                    raise TimeoutError("Timed out while streaming listener audio")
            silence_chunk = bytes(chunk_bytes)
            for _ in range(70):
                packet = encode_realtimestt_packet(
                    {
                        "sampleRate": sample_rate,
                        "channels": channels,
                        "format": "pcm_s16le",
                        "frames": chunk_frames,
                    },
                    silence_chunk,
                )
                ws.send(packet)
                drain_ws_events(ws, events)
                time.sleep(chunk_frames / float(sample_rate))
            final_deadline = time.monotonic() + max(8.0, min(timeout, 45.0))
            while time.monotonic() < final_deadline:
                drain_ws_events(ws, events, timeout=0.25)
                if any(event.get("type") == "final" and event.get("text") for event in events):
                    break
            ws.send(json.dumps({"type": "stop"}))
            drain_ws_events(ws, events, timeout=0.5)
        final_texts = [
            str(event.get("text", "")).strip()
            for event in events
            if event.get("type") == "final" and str(event.get("text", "")).strip()
        ]
        realtime_texts = [
            str(event.get("text", "")).strip()
            for event in events
            if event.get("type") == "realtime" and str(event.get("text", "")).strip()
        ]
        transcript = " ".join(final_texts).strip()
        data.update({
            "listener_state": "completed" if transcript else "no_final_transcript",
            "final_transcript": transcript,
            "partial_transcripts": realtime_texts[-5:],
            "event_count": len(events),
            "events_by_type": {
                event_type: sum(1 for event in events if event.get("type") == event_type)
                for event_type in sorted({str(event.get("type")) for event in events})
            },
            "completed_at": utc_now(),
        })
    except Exception as exc:
        data.update({
            "listener_state": "error",
            "error": str(exc),
            "completed_at": utc_now(),
        })
        write_json(receipt_path, data)
        return listener_case_result(
            case_id="listener-webrtc",
            listener_url=ws_url,
            data=data,
            exercised="browser/WebRTC-shaped PCM into RealtimeSTT listener",
            required_fields=["mocked", "live", "websocket_connected", "capture_source", "final_transcript", "receipt_path"],
            error=str(exc),
        )
    write_json(receipt_path, data)
    return listener_case_result(
        case_id="listener-webrtc",
        listener_url=ws_url,
        data=data,
        exercised="browser/WebRTC-shaped PCM into RealtimeSTT listener",
        required_fields=["mocked", "live", "websocket_connected", "capture_source", "final_transcript", "receipt_path"],
    )


def response_json(response: httpx.Response) -> dict[str, Any]:
    """Return JSON response data or an explicit parse error object."""
    try:
        data = response.json()
    except ValueError as exc:
        logger.error("non-json response from {}: {}", response.url, exc)
        return {"_parse_error": str(exc), "_text_prefix": response.text[:500]}
    return data if isinstance(data, dict) else {"_json_value": data}


def nested_value(data: dict[str, Any], dotted_path: str) -> Any:
    """Return a nested value for dot-path checks."""
    value: Any = data
    for part in dotted_path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def has_required_field(data: dict[str, Any], field_expr: str) -> bool:
    """Return whether a required field or alias expression is present."""
    aliases = [part.strip() for part in field_expr.split("|")]
    return any(nested_value(data, alias) is not None for alias in aliases)


def missing_fields(data: dict[str, Any], fields: list[str]) -> list[str]:
    """Return required fields absent from a response object."""
    return [field for field in fields if not has_required_field(data, field)]


def has_any_field(*objects: dict[str, Any], field_expr: str) -> bool:
    """Return whether any object has a required field or alias expression."""
    return any(has_required_field(obj, field_expr) for obj in objects if obj)


def speech_policy_missing(
    *,
    data: dict[str, Any],
    payload: dict[str, Any] | None,
    require_memory_intent: bool,
) -> list[str]:
    """Return missing voice delivery policy fields for Embry speech receipts."""
    payload = payload or {}
    required = {
        "voice_policy_tone": "conversation_tone|tone|voice_envelope.tone|voiceEnvelope.tone",
        "voice_policy_delivery_stage": "delivery_stage|deliveryStage|voice_envelope.delivery_stage|voiceEnvelope.deliveryStage",
        "voice_policy_emotion_tags": "emotion_tags|emotionTags|voice_envelope.emotion_tags|voiceEnvelope.emotionTags",
        "voice_policy_chatterbox_tags": "chatterbox_tags|chatterboxTags|voice_envelope.chatterbox_tags|voiceEnvelope.chatterboxTags",
        "voice_policy_cue_policy": "cue_policy|cuePolicy|voice_envelope.cue_policy|voiceEnvelope.cuePolicy",
        "voice_policy_source": "intent_policy_source|intentPolicySource|voice_envelope.intent_policy_source|voiceEnvelope.intentPolicySource",
        "voice_policy_pause_strategy": "pause_strategy|pauseStrategy|voice_envelope.pause_strategy|voiceEnvelope.pauseStrategy",
        "voice_policy_interrupt_policy": "interrupt_policy|interruptPolicy|voice_envelope.interrupt_policy|voiceEnvelope.interruptPolicy",
    }
    missing = [
        label
        for label, expr in required.items()
        if not has_any_field(data, payload, field_expr=expr)
    ]
    source = (
        nested_value(data, "intent_policy_source")
        or nested_value(data, "intentPolicySource")
        or nested_value(data, "voice_envelope.intent_policy_source")
        or nested_value(data, "voiceEnvelope.intentPolicySource")
        or nested_value(payload, "intent_policy_source")
        or nested_value(payload, "intentPolicySource")
    )
    if require_memory_intent and source != "memory.intent":
        missing.append("intent_policy_source_memory_intent")
    if require_memory_intent and not has_required_field(data, "memory_intent|memoryIntent|memory.intent|memory.intentResult"):
        missing.append("memory_intent")
    return missing


def compact_value(value: Any, depth: int = 0) -> Any:
    """Return a compact JSON-safe excerpt for receipts."""
    if depth > 4:
        return "<max-depth>"
    if isinstance(value, dict):
        return {key: compact_value(item, depth + 1) for key, item in list(value.items())[:40]}
    if isinstance(value, list):
        if len(value) > 8:
            return {
                "_type": "list",
                "count": len(value),
                "first": [compact_value(item, depth + 1) for item in value[:3]],
            }
        return [compact_value(item, depth + 1) for item in value]
    if isinstance(value, str) and len(value) > 500:
        return value[:500] + "...<truncated>"
    return value


def case_result(
    *,
    case_id: str,
    url: str,
    method: str,
    status_code: int | None,
    data: dict[str, Any],
    required_fields: list[str],
    exercised: str,
    payload: dict[str, Any] | None = None,
    require_speech_policy: bool = False,
    require_memory_intent_policy: bool = False,
    error: str | None = None,
) -> dict[str, Any]:
    """Build a standard case result from one live endpoint call."""
    missing = missing_fields(data, required_fields)
    if require_speech_policy:
        missing.extend(
            speech_policy_missing(
                data=data,
                payload=payload,
                require_memory_intent=require_memory_intent_policy,
            )
        )
    mocked = data.get("mocked")
    live = data.get("live")
    assertion_pass = not error and status_code is not None and 200 <= status_code < 300 and not missing
    if mocked is True:
        assertion_pass = False
        missing.append("mocked_false")
    if live is False and "live" in required_fields:
        assertion_pass = False
        missing.append("live_true")
    readiness = "usable" if assertion_pass else "not_established"
    return {
        "id": case_id,
        "method": method,
        "url": url,
        "status_code": status_code,
        "mocked": mocked,
        "live": live,
        "execution_status": "pass" if status_code is not None else "error",
        "assertion_status": "pass" if assertion_pass else "fail",
        "readiness": readiness,
        "required_fields": required_fields,
        "missing_fields": sorted(set(missing)),
        "error": error,
        "exercised": exercised,
        "request_excerpt": compact_value(payload or {}),
        "response_excerpt": compact_value(data),
    }


def call_endpoint(
    client: httpx.Client,
    *,
    case_id: str,
    method: str,
    url: str,
    payload: dict[str, Any] | None,
    required_fields: list[str],
    exercised: str,
    require_speech_policy: bool = False,
    require_memory_intent_policy: bool = False,
) -> dict[str, Any]:
    """Call one real endpoint and convert the result to a case receipt."""
    try:
        if method == "GET":
            response = client.get(url)
        else:
            response = client.post(url, json=payload)
        data = response_json(response)
        return case_result(
            case_id=case_id,
            url=url,
            method=method,
            status_code=response.status_code,
            data=data,
            required_fields=required_fields,
            exercised=exercised,
            payload=payload,
            require_speech_policy=require_speech_policy,
            require_memory_intent_policy=require_memory_intent_policy,
        )
    except httpx.HTTPError as exc:
        logger.error("endpoint call failed for {} {}: {}", method, url, exc)
        return case_result(
            case_id=case_id,
            url=url,
            method=method,
            status_code=None,
            data={},
            required_fields=required_fields,
            exercised=exercised,
            payload=payload,
            require_speech_policy=require_speech_policy,
            require_memory_intent_policy=require_memory_intent_policy,
            error=str(exc),
        )


def adapted_live_turn_payload(run_id: str, text: str) -> dict[str, Any]:
    """Return a conservative text turn payload for current Embry UX adapters."""
    return {
        "sessionId": f"embry-voice-control-{run_id}",
        "turnId": f"embry-voice-control-turn-{run_id}",
        "text": text,
        "inputMode": "text",
        "voiceEnabled": True,
        "chatEnabled": True,
        "replayEnabled": True,
        "requireMemoryIntentVoicePolicy": True,
        "requireInterruptPolicy": True,
    }


def adapted_speak_payload(run_id: str) -> dict[str, Any]:
    """Return approved direct speech payload for current Embry UX adapters."""
    answer_text = "Embry voice control live sanity. I am checking the Tau voice front end."
    tts_render_text = "[chuckle] Embry voice control live sanity. I am checking the Tau voice front end."
    return {
        "sessionId": f"embry-voice-control-{run_id}",
        "turnId": f"embry-voice-control-speak-{run_id}",
        "text": tts_render_text,
        "tts_render_text": tts_render_text,
        "answer_text": answer_text,
        "tone": "playful_light",
        "conversation_tone": "playful_light",
        "delivery_stage": "positive",
        "emotion_tags": ["playful", "confident", "sanity_check"],
        "chatterbox_tags": ["[chuckle]"],
        "cue_policy": "direct_sanity_explicit_policy",
        "intent_policy_source": "direct_sanity_explicit_policy",
        "pause_strategy": "short_answer_no_filler",
        "interrupt_policy": DEFAULT_INTERRUPT_POLICY,
        "interruptible": True,
        "playLocal": False,
    }


def build_report(
    *,
    run_id: str,
    profile: str,
    base_url: str,
    chat_url: str,
    cases: list[dict[str, Any]],
    output_dir: Path,
) -> dict[str, Any]:
    """Build the readiness report from case receipts."""
    failed = [case for case in cases if case["assertion_status"] != "pass"]
    usable = [case for case in cases if case["assertion_status"] == "pass"]
    if failed and usable:
        readiness = "USABLE_WITH_GAPS"
    elif failed:
        readiness = "NOT_ESTABLISHED"
    else:
        readiness = "READY"
    return {
        "schema": "embry_voice_control.e2e_sanity_report.v1",
        "run_id": run_id,
        "profile": profile,
        "overall_readiness": readiness,
        "mocked": False,
        "live": True,
        "base_url": base_url,
        "chat_url": chat_url,
        "output_dir": str(output_dir),
        "created_at": utc_now(),
        "cases": cases,
        "needs_attention": [
            {
                "case": case["id"],
                "reason": case["error"] or "missing_required_fields_or_non_2xx_response",
                "missing_fields": case.get("missing_fields", []),
                "safe_default": "do_not_claim_embry_voice_control_ready",
            }
            for case in failed
        ],
        "claims": {
            "proves": [
                "Only cases with assertion_status=pass exercised real configured endpoints.",
            ],
            "does_not_prove": [
                "Human-audible playback unless play_local/browser checks are separately run.",
                "Browser WebRTC microphone quality unless listener-live profile is run.",
                "Production readiness unless release profile passes with no gaps.",
            ],
        },
    }


@app.command()
def wake_sanity(
    output_root: Path = typer.Option(DEFAULT_OUTPUT_ROOT, help="12TB output root for receipts"),
) -> None:
    """Run deterministic wake-word contract checks and write a receipt."""
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-wake-" + uuid4().hex[:8]
    output_dir = output_root / "wake-word" / run_id
    receipt = run_wake_word_sanity(run_id)
    receipt_path = output_dir / "receipt.json"
    receipt["receipt_path"] = str(receipt_path)
    write_json(receipt_path, receipt)
    latest_path = output_root / "wake-word" / "latest.json"
    write_json(
        latest_path,
        {
            "run_id": run_id,
            "receipt_path": str(receipt_path),
            "pass": receipt["acceptance"]["pass"],
            "wake_word": WAKE_WORD,
        },
    )
    typer.echo(json.dumps({
        "run_id": run_id,
        "pass": receipt["acceptance"]["pass"],
        "wake_word": WAKE_WORD,
        "receipt_path": str(receipt_path),
    }, indent=2))
    if not receipt["acceptance"]["pass"]:
        raise typer.Exit(code=1)


@app.command("wake-capital-france-live")
def wake_capital_france_live(
    base_url: str = typer.Option(DEFAULT_BASE_URL, help="Embry voice control or current adapter base URL"),
    output_root: Path = typer.Option(DEFAULT_OUTPUT_ROOT, help="12TB output root for receipts"),
    timeout: float = typer.Option(120.0, help="HTTP timeout in seconds"),
) -> None:
    """Produce a wake event and feed a voice-mode France question to /live-turn."""
    receipt = run_wake_capital_france(base_url=base_url, output_root=output_root, timeout=timeout)
    acceptance = receipt["acceptance"]
    typer.echo(json.dumps({
        "run_id": receipt["run_id"],
        "pass": acceptance["pass"],
        "status_code": acceptance["status_code"],
        "answer_text": acceptance["answer_text"],
        "receipt_path": receipt["receipt_path"],
        "not_proven": receipt["claims"]["does_not_prove"],
    }, indent=2))
    if not acceptance["pass"]:
        raise typer.Exit(code=1)


@app.command("unix-listener-sanity")
def unix_listener_sanity(
    realtimestt_repo: Path = typer.Option(DEFAULT_REALTIMESTT_REPO, help="Local RealtimeSTT checkout"),
    python_executable: Path = typer.Option(DEFAULT_REALTIMESTT_PYTHON, help="Python executable for the RealtimeSTT proof runner"),
    proof_script: Path = typer.Option(DEFAULT_PROOF_SCRIPT, help="RealtimeSTT PipeWire proof runner"),
    expected_phrase: str = typer.Option(UNIX_LISTENER_EXPECTED_PHRASE, help="Spoken phrase expected from RealtimeSTT"),
    playback_target: str = typer.Option("64", help="PipeWire playback target"),
    capture_target: str = typer.Option("67", help="PipeWire capture target"),
    output_root: Path = typer.Option(UNIX_LISTENER_OUTPUT_ROOT, help="Output root for listener proof receipts"),
    capture_seconds: float = typer.Option(6.0, help="PipeWire capture duration in seconds"),
    model: str = typer.Option("tiny.en", help="RealtimeSTT final transcription model"),
    realtime_model: str = typer.Option("tiny.en", help="RealtimeSTT realtime transcription model"),
    max_wer: float = typer.Option(0.5, help="Maximum WER for expected phrase match"),
    timeout: float = typer.Option(180.0, help="Subprocess timeout in seconds"),
    skip_speaker_gate: bool = typer.Option(True, help="Skip pyannote speaker gate for this rung"),
    source_wav: Path | None = typer.Option(None, help="Optional source WAV instead of generated espeak speech"),
) -> None:
    """Run the Unix/PipeWire -> RealtimeSTT listener rung and write receipts."""
    receipt = run_unix_listener_sanity(
        realtimestt_repo=realtimestt_repo,
        python_executable=python_executable,
        proof_script=proof_script,
        expected_phrase=expected_phrase,
        playback_target=playback_target,
        capture_target=capture_target,
        output_root=output_root,
        capture_seconds=capture_seconds,
        model=model,
        realtime_model=realtime_model,
        max_wer=max_wer,
        timeout=timeout,
        skip_speaker_gate=skip_speaker_gate,
        source_wav=source_wav,
    )
    acceptance = receipt["acceptance"]
    typer.echo(json.dumps({
        "run_id": receipt["run_id"],
        "pass": acceptance["pass"],
        "receipt_path": receipt["receipt_path"],
        "underlying_receipt_path": receipt["underlying_receipt_path"],
        "final_transcript": receipt["listener_events"].get("final_transcript"),
        "wake_detected": receipt["listener_events"].get("wake_detected"),
        "not_proven": receipt["claims"]["does_not_prove"],
    }, indent=2))
    if not acceptance["pass"]:
        raise typer.Exit(code=1)


@app.command("listener-turn-live")
def listener_turn_live(
    base_url: str = typer.Option(LISTENER_TURN_BASE_URL, help="Embry voice control or current adapter base URL"),
    output_root: Path = typer.Option(LISTENER_TURN_OUTPUT_ROOT, help="12TB output root for receipts"),
    listener_receipt_path: Path | None = typer.Option(None, help="Specific Unix listener wrapper receipt to consume"),
    unix_listener_root: Path = typer.Option(DEFAULT_UNIX_LISTENER_ROOT, help="Unix listener output root with latest_unix_listener.json"),
    expected_answer: str = typer.Option(DEFAULT_EXPECTED_ANSWER, help="Expected semantic answer substring"),
    timeout: float = typer.Option(120.0, help="HTTP timeout in seconds"),
    play_local: bool = typer.Option(False, help="Play returned Chatterbox WAV through local PipeWire"),
    local_playback_target: str = typer.Option("64", help="PipeWire playback target for --play-local"),
    local_playback_timeout: float = typer.Option(30.0, help="Local playback timeout in seconds"),
) -> None:
    """Route the latest Unix listener transcript into /live-turn and require Chatterbox audio."""
    receipt = run_listener_turn_live(
        base_url=base_url,
        output_root=output_root,
        listener_receipt_path=listener_receipt_path,
        unix_listener_root=unix_listener_root,
        expected_answer=expected_answer,
        timeout=timeout,
        play_local=play_local,
        local_playback_target=local_playback_target,
        local_playback_timeout=local_playback_timeout,
    )
    acceptance = receipt["acceptance"]
    typer.echo(json.dumps({
        "run_id": receipt["run_id"],
        "pass": acceptance["pass"],
        "receipt_path": receipt["receipt_path"],
        "listener_receipt_path": receipt["listener_receipt_path"],
        "turn_text": receipt["turn_text"],
        "answer_text": acceptance["answer_text"],
        "local_playback": receipt.get("local_playback"),
        "failed_checks": [
            key for key, value in acceptance["checks"].items()
            if value is not True and key not in {"used_browser_mic", "used_ui", "used_mock_transcript"}
        ],
        "not_proven": receipt["claims"]["does_not_prove"],
    }, indent=2))
    if not acceptance["pass"]:
        raise typer.Exit(code=1)


@app.command()
def verify(
    profile: str = typer.Option("controlled-live", help="controlled-live, listener-live, or release"),
    base_url: str = typer.Option(DEFAULT_BASE_URL, help="Embry voice control or current adapter base URL"),
    chat_url: str = typer.Option(DEFAULT_CHAT_URL, help="Shared Chat UX URL for reporting"),
    listener_url: str = typer.Option(DEFAULT_REALTIMESTT_URL, help="RealtimeSTT FastAPI base URL for listener-live profile"),
    listener_audio: Path = typer.Option(DEFAULT_LISTENER_AUDIO, help="PCM16 WAV file streamed as browser/WebRTC listener input"),
    output_root: Path = typer.Option(DEFAULT_OUTPUT_ROOT, help="12TB output root for receipts"),
    timeout: float = typer.Option(90.0, help="HTTP timeout in seconds"),
) -> None:
    """Run live non-mocked sanity checks and write report artifacts."""
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    output_dir = output_root / run_id
    text = "Horus asks Embry to prove voice control reaches Tau and Chatterbox."
    cases: list[dict[str, Any]] = []
    logger.info("running Embry voice control sanity profile={} base_url={}", profile, base_url)
    with httpx.Client(timeout=httpx.Timeout(timeout, connect=2.0)) as client:
        cases.append(
            call_endpoint(
                client,
                case_id="health",
                method="GET",
                url=normalize_url(base_url, "health"),
                payload=None,
                required_fields=["status"],
                exercised="control plane liveness",
            )
        )
        cases.append(
            call_endpoint(
                client,
                case_id="readiness",
                method="GET",
                url=normalize_url(base_url, "readiness"),
                payload=None,
                required_fields=["overall_readiness"],
                exercised="control plane readiness",
            )
        )
        cases.append(
            call_endpoint(
                client,
                case_id="direct-speak",
                method="POST",
                url=normalize_url(base_url, "direct-speak"),
                payload=adapted_speak_payload(run_id),
                required_fields=["mocked", "live", "audioAuthority.artifactId", "audioUrl|audioAuthority.url"],
                exercised="approved text to Chatterbox audio authority",
                require_speech_policy=True,
            )
        )
        cases.append(
            call_endpoint(
                client,
                case_id="text-turn",
                method="POST",
                url=normalize_url(base_url, "live-turn"),
                payload=adapted_live_turn_payload(run_id, text),
                required_fields=["mocked", "live", "turnId|turnAuthority.turnId", "turnAuthority", "audioAuthority"],
                exercised="text turn through memory/Tau/Chatterbox adapter authority",
                require_speech_policy=True,
                require_memory_intent_policy=True,
            )
        )
        if profile in {"listener-live", "release"}:
            listener_case = run_realtimestt_listener_case(
                listener_url=listener_url,
                audio_path=listener_audio,
                output_dir=output_dir,
                run_id=run_id,
                timeout=timeout,
            )
            cases.append(listener_case)
            transcript = nested_value(listener_case, "response_excerpt.final_transcript")
            if isinstance(transcript, str) and transcript.strip():
                listener_payload = adapted_live_turn_payload(run_id, transcript.strip())
                listener_payload.update({
                    "inputMode": "voice",
                    "captureSource": "browser_webrtc_pcm16_wav_loopback",
                    "speakerEvidence": {
                        "source": "RealtimeSTT",
                        "transcript": transcript.strip(),
                        "diarization_enabled": False,
                        "identity_resolution_required": True,
                    },
                    "listenerReceiptPath": nested_value(listener_case, "response_excerpt.receipt_path"),
                })
                cases.append(
                    call_endpoint(
                        client,
                        case_id="listener-to-turn",
                        method="POST",
                        url=normalize_url(base_url, "live-turn"),
                        payload=listener_payload,
                        required_fields=["mocked", "live", "turnId|turnAuthority.turnId", "turnAuthority", "audioAuthority"],
                        exercised="RealtimeSTT final transcript through memory/Tau/Chatterbox adapter authority",
                        require_speech_policy=True,
                        require_memory_intent_policy=True,
                    )
                )
            else:
                cases.append(
                    case_result(
                        case_id="listener-to-turn",
                        url=normalize_url(base_url, "live-turn"),
                        method="POST",
                        status_code=None,
                        data={
                            "mocked": False,
                            "live": True,
                            "listener_case": listener_case["id"],
                            "reason": "listener did not produce a final transcript",
                        },
                        required_fields=["final_transcript"],
                        exercised="RealtimeSTT final transcript through memory/Tau/Chatterbox adapter authority",
                        error="listener did not produce a final transcript",
                    )
                )
        if profile == "release":
            cases.append(
                call_endpoint(
                    client,
                    case_id="replay",
                    method="POST",
                    url=normalize_url(base_url, "replay"),
                    payload={"session_id": f"embry-voice-control-{run_id}"},
                    required_fields=["session_id", "turn_count", "audio_artifact_count", "receipt_path"],
                    exercised="shared Chat UX conversation replay",
                )
            )
    report = build_report(
        run_id=run_id,
        profile=profile,
        base_url=base_url,
        chat_url=chat_url,
        cases=cases,
        output_dir=output_dir,
    )
    write_json(output_dir / "report.json", report)
    write_html(output_dir / "index.html", report)
    latest_path = output_root / "latest.json"
    write_json(latest_path, {"run_id": run_id, "report_path": str(output_dir / "report.json"), "overall_readiness": report["overall_readiness"]})
    typer.echo(json.dumps({"run_id": run_id, "overall_readiness": report["overall_readiness"], "report_path": str(output_dir / "report.json")}, indent=2))
    if report["overall_readiness"] != "READY":
        raise typer.Exit(code=1)


@app.command("config-doctor")
def config_doctor(
    base_url: str = typer.Option(DEFAULT_BASE_URL),
    chat_url: str = typer.Option(DEFAULT_CHAT_URL),
) -> None:
    """Print non-interactive config state for the live harness."""
    result = {
        "schema": "embry_voice_control.config_doctor.v1",
        "base_url": base_url,
        "chat_url": chat_url,
        "output_root": str(DEFAULT_OUTPUT_ROOT),
        "needs_attention": [],
    }
    typer.echo(json.dumps(result, indent=2))


if __name__ == "__main__":
    app()
