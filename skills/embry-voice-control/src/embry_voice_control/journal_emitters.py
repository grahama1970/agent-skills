"""Canonical producers for the three previously unproduced journal event types.

The live Embry journal only ever contained ``listener.*`` events because three
event types along the immutable turn spine had no ``append_event`` producer:

    speaker.verification.completed   -- the resemblyzer Horus speaker gate
    tau.turn_plan.completed          -- the bounded Tau tick turn plan
    chatterbox.voice_render.completed-- the rendered answer audio

Every field here is dictated by the existing consumers, which this module was
written to satisfy exactly:

  * ``event_journal.validate_event`` -- the schema contract (required string
    fields, ``mocked``/``live`` booleans, ``artifact_hashes`` dict of non-empty
    strings, ``payload`` dict, no producer-supplied ``sequence``).
  * ``chat_projection.build_turn_chat_projection`` -- reads
    ``speaker.payload.score``; ``tau.payload.turn_plan_path`` /
    ``turn_plan_sha256``; ``render.payload.audio.sha256``; and enforces the
    causation chain ``tau.turn_plan.completed <- memory.answer_resolved`` and
    ``chatterbox.voice_render.completed <- tau.turn_plan.completed``.
  * ``artifact_authority.resolve_audio_artifact`` -- resolves audio only through
    a ``chatterbox.voice_render.completed`` event whose ``payload.audio.sha256``
    matches and whose ``artifact_hashes.tau_turn_plan_sha256`` matches.
  * ``pipewire_playback.run_playback`` -- claims the render event by exact
    ``chatterbox.voice_render.completed`` type/sequence and requires
    ``artifact_hashes.tts_render_text_sha256`` and a 24 kHz mono WAV.
  * ``audio_e2e/runner.py`` -- for physical turns asserts exactly one
    ``speaker.verification.completed`` with ``profile_hash``, ``speaker_id ==
    'horus_lupercal'``, a horus ``candidate`` at/above threshold and
    ``speaker_identity_proven is not False``.

The event builder mirrors the proven derived-event producers
(``proofs/tau/.../run_journal_memory_tau_proof.py::append_derived`` for
``tau.turn_plan.completed`` and
``proofs/chat-ux/.../journalize_projection_inputs.py`` for
``chatterbox.voice_render.completed``) so these functions are drop-in
replacements that emit byte-identical events, and it follows the
``pipewire_playback._event`` receipt-hash convention.

Sequence is always assigned by the journal itself (``append_event``); producers
must never supply it.  Event ids are deterministic content hashes so re-running
a turn (crash recovery / idempotent replay) yields the same event.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any
import wave

from embry_voice_control.event_journal import append_event

EVENT_SCHEMA = "embry.voice_event.v1"


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strip(value: str) -> str:
    return str(value).removeprefix("sha256:")


def _build_event(
    *,
    event_type: str,
    id_seed: dict[str, Any],
    source_event: dict[str, Any],
    causation_id: str,
    correlation_id: str,
    producer: str,
    artifact_hashes: dict[str, str],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Assemble one canonical, journal-valid derived event (no sequence)."""
    if not isinstance(causation_id, str) or not causation_id:
        raise ValueError("causation_id_required")
    for key, value in artifact_hashes.items():
        if not isinstance(value, str) or not value:
            raise ValueError(f"artifact_hash_invalid:{key}")
    return {
        "schema": EVENT_SCHEMA,
        "event_id": f"{event_type}.{sha256_hex(canonical_json(id_seed))[:16]}",
        "session_id": source_event["session_id"],
        "turn_id": source_event["turn_id"],
        "type": event_type,
        "created_at": _utc_now(),
        "causation_id": causation_id,
        "correlation_id": correlation_id,
        "producer": producer,
        "mocked": False,
        "live": True,
        "artifact_hashes": artifact_hashes,
        "receipt_hash": "sha256:" + sha256_hex(canonical_json(payload)),
        "payload": payload,
    }


def emit_speaker_verification_completed(
    journal_db: Path,
    *,
    source_event: dict[str, Any],
    decision: dict[str, Any],
    profile_receipt: dict[str, str],
    producer: str = "embry-voice-control.speaker-gate",
) -> dict[str, Any]:
    """Emit ``speaker.verification.completed`` for one turn's Horus speaker gate.

    ``source_event`` is the turn's ``listener.final_transcript`` event (the
    causation parent).  ``decision`` is a ``speaker_gate.verify_turn_speaker``
    result.  Fails CLOSED: a rejected decision is still journaled (recording the
    rejection) with ``speaker_identity_proven`` / ``allow_personal_memory`` set
    to ``False`` so downstream personal-memory unlock cannot proceed.
    """
    audio_sha256 = _strip(source_event["payload"]["audio_sha256"])
    profile_hash = _strip(decision["profile_hash"])
    payload = {
        "schema": "embry.speaker_verification_event_payload.v1",
        "speaker_id": decision["speaker_id"],
        "profile_hash": decision["profile_hash"],
        "score": decision["score"],
        "confidence": decision["confidence"],
        "threshold": decision["threshold"],
        "observed_ambiguity_margin": decision["observed_margin"],
        "min_ambiguity_margin": decision["min_margin"],
        "best_impostor_confidence": decision.get("best_impostor_confidence"),
        "candidates": decision["candidates"],
        "accepted": decision["accepted"],
        "speaker_identity_proven": decision["speaker_identity_proven"],
        "allow_personal_memory": decision["allow_personal_memory"],
        "fresh_physical_human_speech": decision["fresh_physical_human_speech"],
        "source_identity": decision["source_identity"],
        "voice_persona": decision["voice_persona"],
        "engine": decision["engine"],
        "audio_sha256": audio_sha256,
        "rejection_reason": decision["rejection_reason"],
        "profile_receipt": {
            "path": str(profile_receipt["path"]),
            "sha256": profile_receipt["sha256"],
        },
    }
    # Stable id: independent of volatile similarity floats so replay is idempotent.
    id_seed = {
        "source_event_id": source_event["event_id"],
        "type": "speaker.verification.completed",
        "audio_sha256": audio_sha256,
        "profile_hash": profile_hash,
    }
    event = _build_event(
        event_type="speaker.verification.completed",
        id_seed=id_seed,
        source_event=source_event,
        causation_id=source_event["event_id"],
        correlation_id=source_event.get("correlation_id") or source_event["event_id"],
        producer=producer,
        artifact_hashes={
            "audio_sha256": audio_sha256,
            "speaker_profile_sha256": profile_hash,
            "profile_receipt_sha256": _strip(profile_receipt["sha256"]),
        },
        payload=payload,
    )
    return append_event(journal_db, event)


def emit_tau_turn_plan_completed(
    journal_db: Path,
    *,
    source_event: dict[str, Any],
    causation_id: str,
    turn_plan_path: str,
    turn_plan_sha256: str,
    tts_render_text_sha256: str,
    source_contract: str,
    producer: str = "embry-voice-control.journal-memory-tau",
) -> dict[str, Any]:
    """Emit ``tau.turn_plan.completed`` after the bounded Tau tick.

    ``causation_id`` MUST be the ``memory.answer_resolved`` event id: the
    chat projection walks ``tau.turn_plan.completed <- memory.answer_resolved
    <- memory.intent_resolved <- memory.speaker_resolved`` and rejects any other
    parent.  Produces the same payload and event id as the proven
    ``run_journal_memory_tau_proof.append_derived`` call.
    """
    payload = {
        "turn_plan_path": str(turn_plan_path),
        "turn_plan_sha256": turn_plan_sha256,
        "tts_render_text_sha256": tts_render_text_sha256,
        "source_contract": source_contract,
        "suite_ready": False,
    }
    id_seed = {
        "source_event_id": source_event["event_id"],
        "type": "tau.turn_plan.completed",
        "payload": payload,
    }
    event = _build_event(
        event_type="tau.turn_plan.completed",
        id_seed=id_seed,
        source_event=source_event,
        causation_id=causation_id,
        correlation_id=source_event["correlation_id"],
        producer=producer,
        artifact_hashes={
            "turn_plan_sha256": turn_plan_sha256,
            "tts_render_text_sha256": tts_render_text_sha256,
        },
        payload=payload,
    )
    return append_event(journal_db, event)


def _wav_metadata(path: Path) -> dict[str, Any]:
    with wave.open(str(path), "rb") as wav:
        frames = wav.getnframes()
        rate = wav.getframerate()
        return {
            "channels": wav.getnchannels(),
            "sample_rate_hz": rate,
            "duration_ms": round(frames * 1000 / rate) if rate else 0,
        }


def emit_chatterbox_voice_render_completed(
    journal_db: Path,
    *,
    source_event: dict[str, Any],
    tau_plan_event: dict[str, Any],
    render_receipt: dict[str, Any],
    render_receipt_sha256: str,
    render_receipt_path: str | None = None,
    producer: str = "embry-voice-control.chatterbox-render",
) -> dict[str, Any]:
    """Emit ``chatterbox.voice_render.completed`` from an accepted render receipt.

    ``tau_plan_event`` is the ``tau.turn_plan.completed`` event (the causation
    parent).  ``render_receipt`` is an ``embry.voice.causal_chatterbox_render_
    receipt.v2`` object.  Audio channels / sample rate / duration are read from
    the real rendered WAV, and the WAV is hashed to confirm it matches the
    receipt before journaling.  This event is what unblocks the already-written
    playback emitter in ``pipewire_playback.py`` (it claims exactly this type).
    """
    tau = render_receipt["tau"]
    chatterbox = render_receipt["chatterbox"]
    audio_path = Path(str(chatterbox["audio_path"]))
    if not audio_path.is_file():
        raise FileNotFoundError(f"render_audio_missing:{audio_path}")
    audio_sha256 = sha256_file(audio_path)
    if audio_sha256 != _strip(chatterbox["audio_sha256"]):
        raise ValueError("render_audio_hash_mismatch")
    turn_plan_sha256 = tau["turn_plan_sha256"]
    tts_render_text_sha256 = tau["tts_render_text_sha256"]
    metadata = _wav_metadata(audio_path)
    payload = {
        "schema": "embry.chatterbox_voice_render_event_payload.v1",
        "tau_turn_plan": {"path": str(tau["turn_plan_path"]), "sha256": turn_plan_sha256},
        "tts_render_text_sha256": tts_render_text_sha256,
        "render_receipt": {
            "path": str(render_receipt_path) if render_receipt_path else None,
            "sha256": "sha256:" + _strip(render_receipt_sha256),
            "acceptance_all_true": all(render_receipt.get("acceptance", {}).values()),
        },
        "audio": {
            "artifact_id": "audio:" + audio_sha256,
            "path": str(audio_path),
            "sha256": audio_sha256,
            "bytes": audio_path.stat().st_size,
            "content_type": "audio/wav",
            "channels": metadata["channels"],
            "sample_rate_hz": metadata["sample_rate_hz"],
            "duration_ms": metadata["duration_ms"],
        },
    }
    id_seed = {
        "tau_turn_plan_sha256": turn_plan_sha256,
        "audio_sha256": audio_sha256,
        "render_receipt_sha256": _strip(render_receipt_sha256),
    }
    event = _build_event(
        event_type="chatterbox.voice_render.completed",
        id_seed=id_seed,
        source_event=source_event,
        causation_id=tau_plan_event["event_id"],
        correlation_id=source_event["event_id"],
        producer=producer,
        artifact_hashes={
            "tau_turn_plan_sha256": turn_plan_sha256,
            "tts_render_text_sha256": tts_render_text_sha256,
            "audio_sha256": audio_sha256,
        },
        payload=payload,
    )
    return append_event(journal_db, event)
