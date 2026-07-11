"""Deterministic fail-closed checks for the read-only chat projection."""

from pathlib import Path
import hashlib
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient

from embry_voice_control.event_journal import append_event
from embry_voice_control.listener_service import create_app


def write_json(path: Path, value: dict) -> str:
    path.write_text(json.dumps(value, sort_keys=True))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def add(path: Path, event_id: str, event_type: str, payload: dict, *, cause: str, artifacts: dict | None = None) -> dict:
    return append_event(path, {
        "schema": "embry.voice_event.v1", "event_id": event_id, "session_id": "s", "turn_id": "t",
        "type": event_type, "created_at": "2026-07-11T00:00:00Z", "causation_id": cause,
        "correlation_id": "source", "producer": "test", "mocked": False, "live": True,
        "artifact_hashes": artifacts or {}, "receipt_hash": "sha256:" + event_id, "payload": payload,
    })


def test_projection_and_artifact_endpoints_are_hash_bound(tmp_path: Path) -> None:
    db = tmp_path / "events.sqlite3"
    audio = tmp_path / "answer.wav"
    audio.write_bytes(b"RIFF" + b"x" * 60)
    audio_hash = hashlib.sha256(audio.read_bytes()).hexdigest()
    user_text = "Hey Embry, what is the capital of France?"
    answer = "The capital of France is Paris."
    answer_hash = hashlib.sha256(answer.encode()).hexdigest()
    plan = {"session_id": "s", "turn_id": "t", "source_event_id": "source", "display_text": answer, "display_text_sha256": answer_hash, "tts_render_text_sha256": answer_hash}
    plan_path = tmp_path / "plan.json"; plan_hash = write_json(plan_path, plan)
    user_entities = {"entity_nodes": [{"id": "capital", "node_kind": "domain_term", "extracted": {"text": "capital", "span": [23, 30], "source": "spacy", "kind": "domain_term"}, "metadata": {"grounded": True}}]}
    assistant_entities = {"entity_nodes": [{"id": "paris", "node_kind": "domain_term", "extracted": {"text": "Paris", "span": [25, 30], "source": "spacy", "kind": "domain_term"}, "metadata": {"grounded": True}}]}
    user_path = tmp_path / "user.json"; user_hash = write_json(user_path, user_entities)
    assistant_path = tmp_path / "assistant.json"; assistant_hash = write_json(assistant_path, assistant_entities)
    add(db, "source", "listener.final_transcript", {"text": user_text}, cause="recording")
    add(db, "speaker", "speaker.verification.completed", {"score": 0.9}, cause="source")
    add(db, "memory-speaker", "memory.speaker_resolved", {}, cause="source")
    add(db, "memory-intent", "memory.intent_resolved", {}, cause="memory-speaker")
    add(db, "memory-answer", "memory.answer_resolved", {}, cause="memory-intent")
    add(db, "tau-plan", "tau.turn_plan.completed", {"turn_plan_path": str(plan_path), "turn_plan_sha256": "sha256:" + plan_hash}, cause="memory-answer")
    add(db, "tau-tick", "tau.persistent_tick.completed", {}, cause="tau-plan")
    add(db, "entities-user", "entities.extraction.completed", {"target_role": "user", "result_path": str(user_path), "result_sha256": "sha256:" + user_hash}, cause="source")
    add(db, "entities-assistant", "entities.extraction.completed", {"target_role": "assistant", "result_path": str(assistant_path), "result_sha256": "sha256:" + assistant_hash}, cause="tau-plan")
    add(db, "render", "chatterbox.voice_render.completed", {"audio": {"artifact_id": "audio:" + audio_hash, "path": str(audio), "sha256": audio_hash, "bytes": len(audio.read_bytes()), "content_type": "audio/wav", "channels": 1, "sample_rate_hz": 24000, "duration_ms": 1}}, cause="tau-plan")
    client = TestClient(create_app(db))
    projection = client.get("/v1/sessions/s/turns/t/chat-projection")
    assert projection.status_code == 200
    assert [message["id"] for message in projection.json()["messages"]] == ["source", "tau-plan"]
    assert projection.json()["messages"][1]["annotations"][0]["mention"] == "Paris"
    artifact = client.get(f"/v1/sessions/s/turns/t/artifacts/{audio_hash}")
    assert artifact.status_code == 200 and artifact.content == audio.read_bytes()
    assert client.get(f"/v1/sessions/s/turns/t/artifacts/{'0' * 64}").status_code == 404
    assert client.get("/v1/sessions/s/turns/missing/chat-projection").status_code == 404
