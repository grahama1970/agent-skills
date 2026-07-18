"""Code-level sanity for the three canonical journal event emitters.

These checks run without the live system and without resemblyzer: each emitter
is exercised against a temporary SQLite journal and the resulting events are
re-validated with the journal's own ``validate_event`` contract.  The full
six-type chat projection is then built over a synthetic-but-schema-valid event
list to confirm the emitted ``speaker.verification.completed``,
``tau.turn_plan.completed`` and ``chatterbox.voice_render.completed`` events
resolve end to end alongside the memory/entities/playback events.
"""

from pathlib import Path
import hashlib
import json
import struct
import sys
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from embry_voice_control.chat_projection import build_turn_chat_projection
from embry_voice_control.event_journal import append_event, list_events, validate_event
from embry_voice_control.journal_emitters import (
    emit_chatterbox_voice_render_completed,
    emit_speaker_verification_completed,
    emit_tau_turn_plan_completed,
)


def _write_json(path: Path, value: dict) -> str:
    path.write_text(json.dumps(value, sort_keys=True))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_wav(path: Path, *, ms: int = 40) -> str:
    frames = int(24000 * ms / 1000)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(struct.pack("<" + "h" * frames, *([1000] * frames)))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _add(db: Path, event_id: str, event_type: str, payload: dict, *, cause: str) -> dict:
    return append_event(db, {
        "schema": "embry.voice_event.v1", "event_id": event_id, "session_id": "s",
        "turn_id": "t", "type": event_type, "created_at": "2026-07-18T00:00:00Z",
        "causation_id": cause, "correlation_id": "source", "producer": "test",
        "mocked": False, "live": True, "artifact_hashes": {},
        "receipt_hash": "sha256:" + event_id, "payload": payload,
    })


def _revalidate_stored(db: Path) -> None:
    """Every stored event minus its journal-assigned sequence must re-validate."""
    for stored in list_events(db, "s"):
        producer_view = {key: value for key, value in stored.items() if key != "sequence"}
        validate_event(producer_view)


def test_each_emitter_produces_journal_valid_events(tmp_path: Path) -> None:
    db = tmp_path / "events.sqlite3"
    audio = tmp_path / "answer.wav"
    audio_hash = _write_wav(audio)
    answer = "The capital of France is Paris."
    answer_hash = hashlib.sha256(answer.encode()).hexdigest()
    plan = {
        "session_id": "s", "turn_id": "t", "source_event_id": "source",
        "display_text": answer, "display_text_sha256": answer_hash,
        "tts_render_text_sha256": answer_hash,
    }
    plan_path = tmp_path / "plan.json"
    plan_hash = _write_json(plan_path, plan)

    source = _add(db, "source", "listener.final_transcript",
                  {"text": "Hey Embry, what is the capital of France?",
                   "audio_sha256": "cafebabe", "audio_path": str(audio)},
                  cause="recording")
    memory_answer = _add(db, "memory-answer", "memory.answer_resolved", {}, cause="memory-intent")

    speaker = emit_speaker_verification_completed(
        db,
        source_event=source,
        decision={
            "accepted": True, "speaker_id": "horus_lupercal", "profile_hash": "profabc",
            "score": 0.91, "confidence": 0.91, "threshold": 0.75, "observed_margin": 0.19,
            "min_margin": 0.08, "best_impostor_confidence": 0.72,
            "candidates": [{"speaker_id": "horus_lupercal", "confidence": 0.91},
                           {"speaker_id": "impostor:family", "confidence": 0.72}],
            "speaker_identity_proven": True, "allow_personal_memory": True,
            "fresh_physical_human_speech": True, "source_identity": "physical_horus_identity",
            "voice_persona": "horus_lupercal", "engine": "resemblyzer_voice_encoder",
            "rejection_reason": None,
        },
        profile_receipt={"path": str(tmp_path / "enroll.json"), "sha256": "sha256:enroll"},
    )
    assert speaker["type"] == "speaker.verification.completed"
    assert speaker["causation_id"] == "source"
    assert speaker["payload"]["speaker_identity_proven"] is True
    assert speaker["payload"]["score"] == 0.91  # chat_projection detail field

    tau_plan = emit_tau_turn_plan_completed(
        db, source_event=source, causation_id=memory_answer["event_id"],
        turn_plan_path=str(plan_path), turn_plan_sha256="sha256:" + plan_hash,
        tts_render_text_sha256=answer_hash, source_contract="physical_horus_identity",
    )
    assert tau_plan["causation_id"] == "memory-answer"
    assert tau_plan["payload"]["turn_plan_sha256"] == "sha256:" + plan_hash

    render_receipt = {
        "acceptance": {"a": True, "b": True},
        "tau": {"turn_plan_path": str(plan_path), "turn_plan_sha256": "sha256:" + plan_hash,
                "tts_render_text_sha256": answer_hash},
        "chatterbox": {"audio_path": str(audio), "audio_sha256": audio_hash},
    }
    render = emit_chatterbox_voice_render_completed(
        db, source_event=source, tau_plan_event=tau_plan, render_receipt=render_receipt,
        render_receipt_sha256="sha256:receipt", render_receipt_path=str(tmp_path / "r.json"),
    )
    assert render["causation_id"] == tau_plan["event_id"]
    assert render["payload"]["audio"]["sha256"] == audio_hash
    assert render["payload"]["audio"]["channels"] == 1
    assert render["payload"]["audio"]["sample_rate_hz"] == 24000
    assert render["artifact_hashes"]["tau_turn_plan_sha256"] == "sha256:" + plan_hash

    _revalidate_stored(db)

    # Event ids are stable content hashes (crash-recovery guards re-derivation),
    # and re-appending the exact stored event is idempotent in the journal.
    assert append_event(db, {k: v for k, v in speaker.items() if k != "sequence"})[
        "event_id"
    ] == speaker["event_id"]
    assert render["event_id"].startswith("chatterbox.voice_render.completed.")
    assert tau_plan["event_id"].startswith("tau.turn_plan.completed.")


def test_full_six_type_projection_resolves(tmp_path: Path) -> None:
    """Build the whole projection over emitter output plus memory/entities/playback."""
    db = tmp_path / "events.sqlite3"
    audio = tmp_path / "answer.wav"
    audio_hash = _write_wav(audio)
    user_text = "Hey Embry, what is the capital of France?"
    answer = "The capital of France is Paris."
    answer_hash = hashlib.sha256(answer.encode()).hexdigest()
    plan = {"session_id": "s", "turn_id": "t", "source_event_id": "source",
            "display_text": answer, "display_text_sha256": answer_hash,
            "tts_render_text_sha256": answer_hash}
    plan_path = tmp_path / "plan.json"
    plan_hash = _write_json(plan_path, plan)
    user_entities = {"entity_nodes": [{"id": "capital", "node_kind": "domain_term",
        "extracted": {"text": "capital", "span": [23, 30], "source": "spacy", "kind": "domain_term"},
        "metadata": {"grounded": True}}]}
    assistant_entities = {"entity_nodes": [{"id": "paris", "node_kind": "domain_term",
        "extracted": {"text": "Paris", "span": [25, 30], "source": "spacy", "kind": "domain_term"},
        "metadata": {"grounded": True}}]}
    user_path = tmp_path / "user.json"
    user_hash = _write_json(user_path, user_entities)
    assistant_path = tmp_path / "assistant.json"
    assistant_hash = _write_json(assistant_path, assistant_entities)

    source = _add(db, "source", "listener.final_transcript",
                  {"text": user_text, "audio_sha256": "cafebabe", "audio_path": str(audio)},
                  cause="recording")
    # Speaker gate is a sibling branch off the final transcript.
    emit_speaker_verification_completed(
        db, source_event=source, decision={
            "accepted": True, "speaker_id": "horus_lupercal", "profile_hash": "profabc",
            "score": 0.9, "confidence": 0.9, "threshold": 0.75, "observed_margin": 0.2,
            "min_margin": 0.08, "best_impostor_confidence": 0.7,
            "candidates": [{"speaker_id": "horus_lupercal", "confidence": 0.9}],
            "speaker_identity_proven": True, "allow_personal_memory": True,
            "fresh_physical_human_speech": True, "source_identity": "physical_horus_identity",
            "voice_persona": "horus_lupercal", "engine": "resemblyzer_voice_encoder",
            "rejection_reason": None,
        }, profile_receipt={"path": str(tmp_path / "enroll.json"), "sha256": "sha256:enroll"})
    _add(db, "memory-speaker", "memory.speaker_resolved", {}, cause="source")
    _add(db, "memory-intent", "memory.intent_resolved", {}, cause="memory-speaker")
    memory_answer = _add(db, "memory-answer", "memory.answer_resolved", {}, cause="memory-intent")
    tau_plan = emit_tau_turn_plan_completed(
        db, source_event=source, causation_id=memory_answer["event_id"],
        turn_plan_path=str(plan_path), turn_plan_sha256="sha256:" + plan_hash,
        tts_render_text_sha256=answer_hash, source_contract="physical_horus_identity")
    _add(db, "tau-tick", "tau.persistent_tick.completed", {}, cause=tau_plan["event_id"])
    _add(db, "entities-user", "entities.extraction.completed",
         {"target_role": "user", "result_path": str(user_path),
          "result_sha256": "sha256:" + user_hash}, cause="source")
    _add(db, "entities-assistant", "entities.extraction.completed",
         {"target_role": "assistant", "result_path": str(assistant_path),
          "result_sha256": "sha256:" + assistant_hash}, cause=tau_plan["event_id"])
    render = emit_chatterbox_voice_render_completed(
        db, source_event=source, tau_plan_event=tau_plan,
        render_receipt={"acceptance": {"a": True},
                        "tau": {"turn_plan_path": str(plan_path),
                                "turn_plan_sha256": "sha256:" + plan_hash,
                                "tts_render_text_sha256": answer_hash},
                        "chatterbox": {"audio_path": str(audio), "audio_sha256": audio_hash}},
        render_receipt_sha256="sha256:receipt")

    projection = build_turn_chat_projection(db, session_id="s", turn_id="t")
    trace_types = [step["event_type"] for step in projection["messages"][1]["reasoning_steps"]]
    assert set(trace_types) == {
        "speaker.verification.completed", "memory.speaker_resolved",
        "memory.intent_resolved", "memory.answer_resolved",
        "tau.persistent_tick.completed", "tau.turn_plan.completed",
    }
    assert projection["messages"][1]["provenance"]["render_event_id"] == render["event_id"]
    speaker_step = next(s for s in trace_types if s == "speaker.verification.completed")
    assert speaker_step  # resolved
    assert projection["hashes"]["audio_sha256"] == audio_hash
