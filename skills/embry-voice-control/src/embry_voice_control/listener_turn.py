"""Listener transcript to live Embry turn sanity runner.

This runner consumes a Unix/PipeWire RealtimeSTT listener receipt, strips the
Embry wake word from the final transcript, sends the resulting voice-mode turn
to the configured Embry live-turn endpoint, and writes a deterministic receipt.
It proves or fails the next rung after listener ingress: RealtimeSTT transcript
into memory/Tau and Chatterbox. It does not use browser mic, DOM state, typed
UI input, or mocked transcript events.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any
from uuid import uuid4

import httpx
from loguru import logger

from embry_voice_control.event_journal import append_event


DEFAULT_OUTPUT_ROOT = Path("/mnt/storage12tb/skills/embry-voice-control/outputs/e2e")
DEFAULT_UNIX_LISTENER_ROOT = DEFAULT_OUTPUT_ROOT / "unix-listener"
DEFAULT_BASE_URL = "http://127.0.0.1:3001/api/projects/embry-voice"
DEFAULT_JOURNAL_DB = Path("/mnt/storage12tb/skills/embry-voice-control/state/voice-events.sqlite3")
DEFAULT_EXPECTED_ANSWER = "paris"
WAKE_WORD = "embry"
WAKE_WORD_TRANSCRIPT_ALIASES = ("embry", "embree", "emory")
SOURCE_CONTRACT = "unix_pipewire_realtimestt_to_sparta_live_turn"


def now_iso() -> str:
    """Return an ISO UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def new_run_id() -> str:
    """Return a stable run id for receipt directories."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-listener-turn-" + uuid4().hex[:8]


def write_json(path: Path, data: dict[str, Any]) -> None:
    """Write formatted JSON to a path, creating parents as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    """Read a JSON object from a path."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def canonical_json(value: Any) -> str:
    """Return stable compact JSON."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def sha256_text(text: str) -> str:
    """Hash text as lowercase hex."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    """Hash a file as lowercase hex."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_text(text: str) -> str:
    """Normalize text for deterministic matching."""
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def strip_wake_word(transcript: str) -> str:
    """Remove the leading Embry wake word from a transcript."""
    stripped = transcript.strip()
    stripped = re.sub(r"^\s*k[\s,.:;-]+m[\s,.:;-]+b[\s,.:;-]+", "", stripped, flags=re.IGNORECASE)
    wake_aliases = "|".join(re.escape(alias) for alias in WAKE_WORD_TRANSCRIPT_ALIASES)
    return re.sub(rf"^\s*(?:hey[\s,.:;-]+)?(?:{wake_aliases})[\s,.:;-]+", "", stripped, flags=re.IGNORECASE).strip()


def event_time(base_created_at: str, offset_ms: int) -> str:
    """Return stable event times derived from a receipt timestamp."""
    try:
        base = datetime.fromisoformat(base_created_at.replace("Z", "+00:00"))
    except ValueError:
        base = datetime.now(timezone.utc)
    return (base.replace(tzinfo=base.tzinfo or timezone.utc) + timedelta(milliseconds=offset_ms)).isoformat()


def build_journal_event(
    *,
    event_type: str,
    session_id: str,
    turn_id: str,
    created_at: str,
    causation_id: str,
    correlation_id: str,
    payload: dict[str, Any],
    artifact_hashes: dict[str, str],
    producer: str = "embry-voice-control.listener-turn-live",
) -> dict[str, Any]:
    """Build one journal event matching the existing event_journal contract."""
    seed = canonical_json({
        "event_type": event_type,
        "session_id": session_id,
        "turn_id": turn_id,
        "payload": payload,
    })
    return {
        "schema": "embry.voice_event.v2",
        "event_id": f"{event_type}.{sha256_text(seed)[:16]}",
        "session_id": session_id,
        "turn_id": turn_id,
        "type": event_type,
        "created_at": created_at,
        "causation_id": causation_id,
        "correlation_id": correlation_id,
        "producer": producer,
        "mocked": False,
        "live": True,
        "artifact_hashes": artifact_hashes,
        "receipt_hash": "sha256:" + sha256_text(canonical_json(payload)),
        "payload": payload,
    }


def normalize_url(base_url: str, suffix: str) -> str:
    """Join a base URL and suffix without losing path prefixes."""
    return f"{base_url.rstrip('/')}/{suffix.lstrip('/')}"


def publish_listener_turn_journal(
    *,
    journal_db: Path,
    receipt_created_at: str,
    listener_receipt_path: Path,
    listener_receipt: dict[str, Any],
    turn_text: str,
    request_payload: dict[str, Any],
    response: dict[str, Any],
    local_playback: dict[str, Any],
) -> list[dict[str, Any]]:
    """Publish an accepted listener-turn-live receipt to the UI journal."""
    session_id = str(response.get("sessionId") or request_payload.get("sessionId") or "")
    turn_id = str(response.get("turnId") or request_payload.get("turnId") or session_id)
    if not session_id or not turn_id:
        raise ValueError("journal_session_or_turn_missing")

    listener_events = listener_receipt.get("listener_events", {})
    final_transcript = str(listener_events.get("final_transcript") or "")
    response_audio = response.get("audioAuthority") if isinstance(response.get("audioAuthority"), dict) else {}
    response_envelope = response.get("voiceEnvelope") if isinstance(response.get("voiceEnvelope"), dict) else response_audio.get("envelope")
    audio_path = str(response.get("audioPath") or response_audio.get("path") or "")
    audio_sha256 = str(response_audio.get("sha256") or "")
    if audio_path:
        path = Path(audio_path)
        if path.is_file():
            audio_sha256 = sha256_file(path)
    audio_duration_ms = response.get("durationMs") or response_audio.get("durationMs")
    if isinstance(response_envelope, dict):
        audio_duration_ms = response_envelope.get("durationMs") or audio_duration_ms
    artifact_hashes = {
        "listener_receipt_sha256": "sha256:" + sha256_file(listener_receipt_path),
        "turn_text_sha256": "sha256:" + sha256_text(turn_text),
    }
    if audio_sha256:
        artifact_hashes["audio_sha256"] = "sha256:" + audio_sha256.removeprefix("sha256:")

    correlation_id = f"listener-turn-live:{session_id}"
    listener_payload = {
        "text": final_transcript,
        "turn_text": turn_text,
        "wake_authority": "unix_pipewire_realtimestt_journal",
        "wake_detected": bool(listener_events.get("wake_detected")),
        "source_contract": SOURCE_CONTRACT,
        "listener_receipt_path": str(listener_receipt_path),
        "underlying_receipt_path": listener_receipt.get("underlying_receipt_path"),
        "events_path": listener_events.get("events_path"),
    }
    listener_event = append_event(journal_db, build_journal_event(
        event_type="listener.final_transcript",
        session_id=session_id,
        turn_id=turn_id,
        created_at=event_time(receipt_created_at, 0),
        causation_id=correlation_id,
        correlation_id=correlation_id,
        payload=listener_payload,
        artifact_hashes=artifact_hashes,
    ))

    memory_payload = {
        "answer": response.get("answerText"),
        "memory": response.get("memory"),
        "route_taken": nested_value(response, "tauBoundary.route_taken"),
        "source_contract": SOURCE_CONTRACT,
    }
    memory_event = append_event(journal_db, build_journal_event(
        event_type="memory.answer_resolved",
        session_id=session_id,
        turn_id=turn_id,
        created_at=event_time(receipt_created_at, 1),
        causation_id=listener_event["event_id"],
        correlation_id=correlation_id,
        payload=memory_payload,
        artifact_hashes=artifact_hashes,
    ))

    tau_payload = {
        "reasoningSteps": response.get("reasoningSteps"),
        "tauBoundary": response.get("tauBoundary"),
        "turnAuthority": response.get("turnAuthority"),
        "source_contract": SOURCE_CONTRACT,
    }
    tau_event = append_event(journal_db, build_journal_event(
        event_type="tau.turn_plan.completed",
        session_id=session_id,
        turn_id=turn_id,
        created_at=event_time(receipt_created_at, 2),
        causation_id=memory_event["event_id"],
        correlation_id=correlation_id,
        payload=tau_payload,
        artifact_hashes=artifact_hashes,
    ))

    audio_payload = {
        "artifactId": response_audio.get("artifactId"),
        "authority": response_audio.get("authority"),
        "path": audio_path,
        "url": response.get("audioUrl") or response_audio.get("url"),
        "sha256": audio_sha256.removeprefix("sha256:") if audio_sha256 else None,
        "bytes": Path(audio_path).stat().st_size if audio_path and Path(audio_path).is_file() else None,
        "durationMs": audio_duration_ms,
        "duration_ms": audio_duration_ms,
        "envelope": response_envelope,
    }
    render_payload = {
        "answer": response.get("answerText"),
        "audio": audio_payload,
        "audioPath": audio_path,
        "audioUrl": response.get("audioUrl"),
        "receiptPath": response.get("receiptPath"),
        "receiptUrl": response.get("receiptUrl"),
        "voiceEnvelope": response_envelope,
    }
    render_event = append_event(journal_db, build_journal_event(
        event_type="chatterbox.voice_render.completed",
        session_id=session_id,
        turn_id=turn_id,
        created_at=event_time(receipt_created_at, 3),
        causation_id=tau_event["event_id"],
        correlation_id=correlation_id,
        payload=render_payload,
        artifact_hashes=artifact_hashes,
    ))

    stored = [listener_event, memory_event, tau_event, render_event]
    if local_playback.get("requested") and local_playback.get("played"):
        playback_authority_id = f"pipewire-playback:{sha256_text(canonical_json(local_playback))[:16]}"
        playback_payload = {
            "authority_id": playback_authority_id,
            "command": local_playback.get("command"),
            "played": local_playback.get("played"),
            "sink": {
                "driver": local_playback.get("driver"),
                "target": local_playback.get("target"),
            },
            "timing_gate": {
                "expected_duration_ms": audio_duration_ms,
                "plausible": local_playback.get("returncode") == 0,
                "returncode": local_playback.get("returncode"),
            },
        }
        previous_id = render_event["event_id"]
        for index, event_type in enumerate(("playback.requested", "playback.started", "playback.ended"), start=4):
            event = append_event(journal_db, build_journal_event(
                event_type=event_type,
                session_id=session_id,
                turn_id=turn_id,
                created_at=event_time(receipt_created_at, index),
                causation_id=previous_id,
                correlation_id=correlation_id,
                payload=playback_payload,
                artifact_hashes=artifact_hashes,
            ))
            stored.append(event)
            previous_id = event["event_id"]
    return stored


def nested_value(data: dict[str, Any], dotted_path: str) -> Any:
    """Return a nested dict value by dotted path."""
    value: Any = data
    for part in dotted_path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def compact_value(value: Any, depth: int = 0) -> Any:
    """Return a bounded JSON-safe value for receipts."""
    if depth > 4:
        return "<max-depth>"
    if isinstance(value, dict):
        return {key: compact_value(item, depth + 1) for key, item in list(value.items())[:60]}
    if isinstance(value, list):
        if len(value) > 12:
            return {
                "_type": "list",
                "count": len(value),
                "first": [compact_value(item, depth + 1) for item in value[:4]],
            }
        return [compact_value(item, depth + 1) for item in value]
    if isinstance(value, str) and len(value) > 1000:
        return value[:1000] + "...<truncated>"
    return value


def latest_unix_listener_receipt(unix_listener_root: Path = DEFAULT_UNIX_LISTENER_ROOT) -> Path:
    """Return the latest Unix listener wrapper receipt path."""
    latest_path = unix_listener_root / "latest_unix_listener.json"
    if not latest_path.exists():
        raise FileNotFoundError(f"Latest Unix listener receipt pointer not found: {latest_path}")
    latest = read_json(latest_path)
    receipt_path = latest.get("receipt_path")
    if not isinstance(receipt_path, str) or not receipt_path:
        raise ValueError(f"{latest_path} does not contain receipt_path")
    path = Path(receipt_path)
    if not path.exists():
        raise FileNotFoundError(f"Unix listener receipt not found: {path}")
    return path


def build_turn_payload(
    *,
    run_id: str,
    listener_receipt_path: Path,
    listener_receipt: dict[str, Any],
    turn_text: str,
) -> dict[str, Any]:
    """Build the live-turn payload from a listener receipt."""
    listener_events = listener_receipt.get("listener_events", {})
    final_transcript = str(listener_events.get("final_transcript") or "")
    return {
        "sessionId": f"embry-listener-turn-{run_id}",
        "turnId": f"embry-listener-turn-{run_id}",
        "text": turn_text,
        "inputMode": "voice",
        "voiceEnabled": True,
        "chatEnabled": True,
        "replayEnabled": False,
        "listenerEvidence": {
            "schema": "embry_voice_control.listener_turn_evidence.v1",
            "source": "unix_pipewire_realtimestt_listener",
            "receipt_path": str(listener_receipt_path),
            "underlying_receipt_path": listener_receipt.get("underlying_receipt_path"),
            "events_path": listener_events.get("events_path"),
            "final_transcript": final_transcript,
            "normalized_final_transcript": listener_events.get("normalized_final_transcript"),
            "wake_detected": listener_events.get("wake_detected"),
            "wake_word": listener_events.get("wake_word"),
            "realtime_event_count": listener_events.get("realtime_event_count"),
            "hot_mic": True,
            "browser_webrtc": False,
            "realtimestt": True,
        },
        "speakerEvidence": {
            "source": "unix_listener_rung_pending_speaker_gate",
            "primary_speaker": True,
            "identity_resolution_required": True,
            "speaker_gate_status": "not_proven",
        },
        "requireMemoryIntentVoicePolicy": True,
        "requireInterruptPolicy": True,
    }


def post_live_turn(base_url: str, payload: dict[str, Any], timeout: float) -> tuple[int | None, dict[str, Any], str | None]:
    """Post one live turn and return status, JSON body, and error."""
    url = normalize_url(base_url, "live-turn")
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout, connect=2.0)) as client:
            response = client.post(url, json=payload)
            try:
                body = response.json()
            except ValueError as exc:
                body = {"_parse_error": str(exc), "_text_prefix": response.text[:500]}
            return response.status_code, body if isinstance(body, dict) else {"_json_value": body}, None
    except httpx.HTTPError as exc:
        logger.error("live-turn request failed: {}", exc)
        return None, {}, str(exc)


def play_audio_local(audio_path: str, playback_target: str, timeout: float) -> dict[str, Any]:
    """Play a generated WAV through PipeWire and return playback receipt data."""
    if not audio_path:
        return {"requested": True, "played": False, "error": "audio_path was empty"}
    path = Path(audio_path)
    if not path.exists():
        return {"requested": True, "played": False, "path": audio_path, "error": "audio_path does not exist"}
    command = ["pw-play"]
    target_arg_used = bool(playback_target and playback_target not in {"auto", "default"})
    if target_arg_used:
        command.extend(["--target", playback_target])
    command.append(str(path))
    logger.info("playing Chatterbox audio locally: {}", " ".join(command))
    completed = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    return {
        "requested": True,
        "played": completed.returncode == 0,
        "driver": "pipewire-pw-play",
        "command": command,
        "target": playback_target if target_arg_used else "auto",
        "targetArgUsed": target_arg_used,
        "path": str(path),
        "returncode": completed.returncode,
        "stdout": completed.stdout[-2000:],
        "stderr": completed.stderr[-2000:],
    }


def evaluate_acceptance(
    *,
    listener_receipt: dict[str, Any],
    turn_text: str,
    response_status_code: int | None,
    response: dict[str, Any],
    expected_answer: str,
    error: str | None,
    local_playback: dict[str, Any],
    require_local_playback: bool,
) -> dict[str, Any]:
    """Return deterministic pass/fail checks for the listener-to-turn rung."""
    answer_text = str(response.get("answerText") or nested_value(response, "turnAuthority.assistantText") or "")
    normalized_answer = normalize_text(answer_text)
    memory = response.get("memory") if isinstance(response.get("memory"), dict) else {}
    reasoning = response.get("reasoningSteps") if isinstance(response.get("reasoningSteps"), list) else []
    audio_path = response.get("audioPath") or nested_value(response, "audioAuthority.path")
    receipt_path = response.get("receiptPath") or nested_value(response, "turnAuthority.receiptPath")
    listener_events = listener_receipt.get("listener_events", {})
    underlying_acceptance = listener_receipt.get("acceptance", {})
    checks = {
        "listener_receipt_passed": bool(underlying_acceptance.get("pass")),
        "listener_wake_detected": bool(listener_events.get("wake_detected")),
        "listener_final_transcript_seen": bool(str(listener_events.get("final_transcript") or "").strip()),
        "turn_text_sent": bool(turn_text.strip()),
        "used_browser_mic": False,
        "used_ui": False,
        "used_mock_transcript": False,
        "live_turn_http_2xx": response_status_code is not None and 200 <= response_status_code < 300,
        "live_turn_status_ok": response.get("status") == "ok",
        "response_live": response.get("live") is True,
        "response_not_mocked": response.get("mocked") is False,
        "memory_intent_returned": isinstance(memory.get("intent"), dict),
        "tau_boundary_returned": bool(response.get("tauBoundary") or nested_value(response, "turnAuthority.tauTrace.boundary")),
        "reasoning_steps_returned": len(reasoning) >= 4,
        "audio_authority_returned": bool(response.get("audioAuthority") or nested_value(response, "turnAuthority.audioAuthority")),
        "audio_path_returned": isinstance(audio_path, str) and bool(audio_path),
        "receipt_path_returned": isinstance(receipt_path, str) and bool(receipt_path),
        "answer_mentions_expected": normalize_text(expected_answer) in normalized_answer,
    }
    if require_local_playback:
        checks["local_playback_requested"] = bool(local_playback.get("requested"))
        checks["local_playback_played"] = bool(local_playback.get("played"))
    checks["pass"] = all(
        value for key, value in checks.items()
        if key not in {"used_browser_mic", "used_ui", "used_mock_transcript"}
    ) and error is None
    return {
        "pass": checks["pass"],
        "checks": checks,
        "answer_text": answer_text,
        "normalized_answer": normalized_answer,
        "expected_answer": expected_answer,
        "response_status_code": response_status_code,
        "error": error,
    }


def run_listener_turn_live(
    *,
    base_url: str = DEFAULT_BASE_URL,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    listener_receipt_path: Path | None = None,
    unix_listener_root: Path = DEFAULT_UNIX_LISTENER_ROOT,
    expected_answer: str = DEFAULT_EXPECTED_ANSWER,
    timeout: float = 120.0,
    play_local: bool = False,
    local_playback_target: str = "64",
    local_playback_timeout: float = 30.0,
    journal_db: Path | None = DEFAULT_JOURNAL_DB,
) -> dict[str, Any]:
    """Run listener transcript -> live-turn -> Chatterbox artifact sanity."""
    run_id = new_run_id()
    output_dir = output_root / "listener-turn-live" / run_id
    receipt_path = output_dir / "receipt.json"
    listener_path = listener_receipt_path or latest_unix_listener_receipt(unix_listener_root)
    listener_receipt = read_json(listener_path)
    final_transcript = str(listener_receipt.get("listener_events", {}).get("final_transcript") or "")
    turn_text = strip_wake_word(final_transcript)
    payload = build_turn_payload(
        run_id=run_id,
        listener_receipt_path=listener_path,
        listener_receipt=listener_receipt,
        turn_text=turn_text,
    )
    response_status_code, response, error = post_live_turn(base_url, payload, timeout)
    audio_path = str(response.get("audioPath") or nested_value(response, "audioAuthority.path") or "")
    local_playback = play_audio_local(
        audio_path=audio_path,
        playback_target=local_playback_target,
        timeout=local_playback_timeout,
    ) if play_local else {
        "requested": False,
        "played": False,
        "reason": "play_local was false",
    }
    acceptance = evaluate_acceptance(
        listener_receipt=listener_receipt,
        turn_text=turn_text,
        response_status_code=response_status_code,
        response=response,
        expected_answer=expected_answer,
        error=error,
        local_playback=local_playback,
        require_local_playback=play_local,
    )
    created_at = now_iso()
    journal_events: list[dict[str, Any]] = []
    journal_error: str | None = None
    if acceptance["pass"] and journal_db is not None:
        try:
            journal_events = publish_listener_turn_journal(
                journal_db=journal_db,
                receipt_created_at=created_at,
                listener_receipt_path=listener_path,
                listener_receipt=listener_receipt,
                turn_text=turn_text,
                request_payload=payload,
                response=response,
                local_playback=local_playback,
            )
        except Exception as exc:  # pragma: no cover - surfaced in receipt.
            logger.error("listener-turn journal publication failed: {}", exc)
            journal_error = str(exc)
    acceptance["checks"]["journal_projection_events_published"] = (
        journal_db is None or (journal_error is None and len(journal_events) >= 7)
    )
    acceptance["pass"] = bool(acceptance["pass"] and acceptance["checks"]["journal_projection_events_published"])
    receipt = {
        "schema": "embry_voice_control.listener_turn_live_receipt.v1",
        "run_id": run_id,
        "created_at": created_at,
        "mocked": False,
        "live": True,
        "used_ui": False,
        "used_browser_mic": False,
        "used_mock_transcript": False,
        "base_url": base_url,
        "endpoint": normalize_url(base_url, "live-turn"),
        "listener_receipt_path": str(listener_path),
        "listener_final_transcript": final_transcript,
        "turn_text": turn_text,
        "expected_answer": expected_answer,
        "request_payload": payload,
        "response_status_code": response_status_code,
        "response_excerpt": compact_value(response),
        "local_playback": local_playback,
        "journal": {
            "requested": journal_db is not None,
            "db_path": str(journal_db) if journal_db is not None else None,
            "published": journal_error is None and bool(journal_events),
            "event_count": len(journal_events),
            "events": [
                {
                    "event_id": event["event_id"],
                    "type": event["type"],
                    "sequence": event["sequence"],
                }
                for event in journal_events
            ],
            "error": journal_error,
        },
        "acceptance": acceptance,
        "receipt_path": str(receipt_path),
        "claims": {
            "proves": [
                "A Unix/PipeWire RealtimeSTT final transcript was converted into a voice-mode live-turn request.",
                "The configured live-turn endpoint was exercised without browser mic or UI input.",
                "If acceptance.pass is true, memory/Tau returned the expected answer and Chatterbox returned audio authority.",
            ],
            "does_not_prove": [
                "Browser microphone or WebRTC capture.",
                "Speaker identity or diarization acceptance.",
                "Shared Chat UX rendering.",
                "Orb sync.",
                "Replay.",
                "Interruption or barge-in.",
            ],
        },
    }
    write_json(receipt_path, receipt)
    write_json(
        output_root / "listener-turn-live" / "latest.json",
        {
            "run_id": run_id,
            "pass": acceptance["pass"],
            "receipt_path": str(receipt_path),
            "listener_receipt_path": str(listener_path),
            "turn_text": turn_text,
            "answer_text": acceptance["answer_text"],
            "local_playback": local_playback,
        },
    )
    return receipt
