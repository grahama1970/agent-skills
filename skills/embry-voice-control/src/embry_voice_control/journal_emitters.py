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
import subprocess
from typing import Any
import wave

from embry_voice_control.event_journal import append_event

EVENT_SCHEMA = "embry.voice_event.v1"

# The sanctioned deterministic extractor (Flashtext/RapidFuzz, zero LLM cost)
# whose ``entity_nodes`` shape is exactly what ``chat_projection._annotations``
# consumes.  This is the same ``$extract-entities`` capability the chat-ux
# backfill (``journalize_projection_inputs.py``) journaled from, and the same
# family the memory stage uses for intent resolution.
ENTITY_EXTRACTOR_RUN = Path(
    "/home/graham/workspace/experiments/agent-skills/skills/extract-entities/run.sh"
)


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


def run_entity_extraction(text: str) -> dict[str, Any]:
    """Run the sanctioned deterministic ``extract-entities`` skill over ``text``.

    Returns the full ``EntityExtractionResult`` object.  No LLM is invoked
    (Aho-Corasick + RapidFuzz), so the result is a pure function of the input
    text and the extractor's grounded vocabulary -- re-running a turn yields the
    same ``entity_nodes`` and therefore the same journaled event id.
    """
    completed = subprocess.run(
        [str(ENTITY_EXTRACTOR_RUN), "extract", "--json", "--verbose", text],
        check=True,
        capture_output=True,
        text=True,
    )
    parsed = json.loads(completed.stdout)
    if not isinstance(parsed, dict):
        raise ValueError("entity_extraction_result_invalid")
    return parsed


def _validate_entity_spans(entity_nodes: list[dict[str, Any]], text: str) -> None:
    """Fail CLOSED before journaling: every span must resolve inside ``text``.

    Mirrors ``chat_projection._annotations`` exactly so this producer can never
    emit an event the projection would later reject with ``entity_span_invalid``.
    """
    if not isinstance(entity_nodes, list):
        raise ValueError("entity_nodes_invalid")
    previous_end = -1
    for node in sorted(
        (n for n in entity_nodes if isinstance(n.get("extracted", {}).get("span"), list)),
        key=lambda n: (int(n["extracted"]["span"][0]), int(n["extracted"]["span"][1])),
    ):
        extracted = node.get("extracted", {})
        span = extracted.get("span")
        if len(span) != 2:
            continue
        start, end = int(span[0]), int(span[1])
        mention = str(extracted.get("text", ""))
        if not (0 <= start < end <= len(text)) or text[start:end] != mention:
            raise ValueError("entity_span_mismatch")
        if start < previous_end:
            raise ValueError("entity_spans_overlap")
        previous_end = end


def _select_non_overlapping_nodes(
    entity_nodes: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Deterministically resolve overlapping real spans for the projection.

    The sanctioned extractor legitimately returns nested spans (an outer noun
    phrase and a grounded term inside it, e.g. ``certified evidence`` >
    ``evidence``).  ``chat_projection._annotations`` fails closed on any span
    overlap, so a chat annotation layer can carry only one mark per character.
    This keeps the outermost (longest, earliest-starting) REAL span and drops
    the nested ones -- inventing nothing, only selecting a maximal non-overlapping
    subset of what the extractor actually found.  Nodes without a valid 2-int
    span are retained untouched (the projection ignores them).  Returns
    ``(entity_nodes_out, dropped)`` preserving the input order of kept nodes.
    """
    spanned: list[tuple[int, int, dict[str, Any]]] = []
    for node in entity_nodes:
        span = node.get("extracted", {}).get("span")
        if isinstance(span, list) and len(span) == 2:
            try:
                start, end = int(span[0]), int(span[1])
            except (TypeError, ValueError):
                continue
            if 0 <= start < end:
                spanned.append((start, end, node))
    kept_ids: set[int] = set()
    last_end = -1
    for start, end, node in sorted(spanned, key=lambda item: (item[0], -(item[1] - item[0]))):
        if start >= last_end:
            kept_ids.add(id(node))
            last_end = end
    dropped = [node for _, _, node in spanned if id(node) not in kept_ids]
    dropped_ids = {id(node) for node in dropped}
    entity_nodes_out = [node for node in entity_nodes if id(node) not in dropped_ids]
    return entity_nodes_out, dropped


def emit_entities_extraction_completed(
    journal_db: Path,
    *,
    source_event: dict[str, Any],
    target_role: str,
    target_event_id: str,
    text: str,
    extraction_result: dict[str, Any],
    result_path: Path,
    correlation_id: str | None = None,
    derivation: dict[str, Any] | None = None,
    producer: str = "embry-voice-control.extract-entities",
) -> dict[str, Any]:
    """Emit one ``entities.extraction.completed`` event for a turn message.

    ``chat_projection.build_turn_chat_projection`` requires exactly one such
    event per role (``user`` over the final transcript, ``assistant`` over the
    Tau turn plan's ``display_text``) and reads ``payload.target_role``,
    ``payload.result_path`` and ``payload.result_sha256``; ``_annotations`` then
    re-reads ``entity_nodes`` from that file and re-validates every span against
    the message text.  ``causation_id`` is the event that carries the message
    text: the ``listener.final_transcript`` event for ``user`` and the
    ``tau.turn_plan.completed`` event for ``assistant``.

    ``extraction_result`` MUST come from ``run_entity_extraction`` (or the memory
    stage's already-journaled extractor output) -- never a hand-authored result.
    The result is written canonically to ``result_path`` (stable bytes -> stable
    hash -> idempotent replay) and every span is validated before append so this
    producer fails closed rather than journaling an unresolvable annotation.

    ``derivation`` records honest provenance when the event is computed post-hoc
    over already-recorded data (backfill); omit it for the inline live turn flow.
    """
    if target_role not in {"user", "assistant"}:
        raise ValueError("entity_target_role_invalid")
    if not isinstance(target_event_id, str) or not target_event_id:
        raise ValueError("entity_target_event_id_required")
    raw_nodes = extraction_result.get("entity_nodes", [])
    if not isinstance(raw_nodes, list):
        raise ValueError("entity_nodes_invalid")
    entity_nodes, dropped = _select_non_overlapping_nodes(raw_nodes)
    # Fail closed: the retained real spans must all resolve inside the message
    # text and be non-overlapping, exactly as chat_projection re-checks them.
    _validate_entity_spans(entity_nodes, text)

    # Only the entity_nodes list is replaced; the rest of the extractor result
    # is preserved verbatim.  When nothing overlaps, the document is byte-for-byte
    # identical to the raw extractor output (stable hash / idempotent replay).
    result_document = dict(extraction_result)
    result_document["entity_nodes"] = entity_nodes
    result_path = Path(result_path)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(result_document, indent=2, sort_keys=True) + "\n"
    result_path.write_text(serialized)
    result_sha256 = sha256_hex(serialized.encode())
    text_sha256 = sha256_hex(text.encode())

    payload = {
        "schema": "embry.entity_annotation_event_payload.v1",
        "target_role": target_role,
        "target_event_id": target_event_id,
        "target_text_sha256": "sha256:" + text_sha256,
        "extractor": "$extract-entities",
        "extractor_result_schema": "EntityExtractionResult",
        "result_path": str(result_path),
        "result_sha256": "sha256:" + result_sha256,
        "span_count": len(entity_nodes),
        "input_normalization": "none",
    }
    if dropped:
        payload["overlap_resolution"] = {
            "rule": "keep_outermost_earliest_start_non_overlapping",
            "raw_span_count": len(
                [n for n in raw_nodes if isinstance(n.get("extracted", {}).get("span"), list)]
            ),
            "kept_span_count": len(entity_nodes),
            "dropped": [
                {
                    "id": str(node.get("id", "")),
                    "span": node.get("extracted", {}).get("span"),
                    "text": node.get("extracted", {}).get("text"),
                    "reason": "nested_within_retained_span",
                }
                for node in dropped
            ],
        }
    if derivation is not None:
        payload["derivation"] = derivation
    id_seed = {
        "target_event_id": target_event_id,
        "target_text_sha256": text_sha256,
        "result_sha256": result_sha256,
    }
    event = _build_event(
        event_type="entities.extraction.completed",
        id_seed=id_seed,
        source_event=source_event,
        causation_id=target_event_id,
        correlation_id=correlation_id or source_event["event_id"],
        producer=producer,
        artifact_hashes={
            "entity_result_sha256": "sha256:" + result_sha256,
            "target_text_sha256": "sha256:" + text_sha256,
        },
        payload=payload,
    )
    return append_event(journal_db, event)
