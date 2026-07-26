from pathlib import Path

from embry_voice_control.event_journal import list_events
from embry_voice_control.listener_turn import publish_listener_turn_journal, strip_wake_word


def test_strip_wake_word_supports_observed_kmb_initialism() -> None:
    assert strip_wake_word("K.M.B. What is the capital of France?") == "What is the capital of France?"


def test_strip_wake_word_supports_observed_embree_spelling() -> None:
    assert strip_wake_word("Hey Embree make her brave ask one more clarifying question.") == (
        "make her brave ask one more clarifying question."
    )


def test_strip_wake_word_supports_observed_emory_spelling() -> None:
    assert strip_wake_word("Hey Emory, what is the capital of France?") == (
        "what is the capital of France?"
    )


def test_publish_listener_turn_journal_writes_projection_events(tmp_path: Path) -> None:
    db = tmp_path / "voice-events.sqlite3"
    listener_receipt_path = tmp_path / "listener.json"
    listener_receipt_path.write_text('{"acceptance":{"pass":true}}', encoding="utf-8")
    audio_path = tmp_path / "answer.wav"
    audio_path.write_bytes(b"RIFF" + b"x" * 64)
    listener_receipt = {
        "underlying_receipt_path": str(tmp_path / "underlying.json"),
        "listener_events": {
            "final_transcript": "Hey Embry, what is the capital of France?",
            "wake_detected": True,
            "events_path": str(tmp_path / "events.jsonl"),
        },
    }
    response = {
        "sessionId": "s",
        "turnId": "t",
        "answerText": "The capital of France is Paris.",
        "memory": {"intent": {"action": "QUERY"}},
        "tauBoundary": {"route_taken": "static_answer"},
        "reasoningSteps": [{"id": "tau-turn-plan"}],
        "audioPath": str(audio_path),
        "audioUrl": "/chatterbox-artifacts/answer.wav",
        "receiptPath": str(tmp_path / "answer.json"),
        "voiceEnvelope": {
            "version": 1,
            "frameMs": 16,
            "durationMs": 32,
            "frames": [
                {"t": 0, "level": 0.1, "bass": 0.2, "mid": 0.3, "treble": 0.4},
                {"t": 0.016, "level": 0.5, "bass": 0.6, "mid": 0.7, "treble": 0.8},
            ],
        },
        "audioAuthority": {"path": str(audio_path), "sha256": "stale", "durationMs": 32},
    }
    playback = {
        "requested": True,
        "played": True,
        "driver": "pipewire-pw-play",
        "command": ["pw-play", "--target", "59", str(audio_path)],
        "target": "59",
        "returncode": 0,
    }

    stored = publish_listener_turn_journal(
        journal_db=db,
        receipt_created_at="2026-07-25T20:47:08+00:00",
        listener_receipt_path=listener_receipt_path,
        listener_receipt=listener_receipt,
        turn_text="what is the capital of France?",
        request_payload={"sessionId": "s", "turnId": "t"},
        response=response,
        local_playback=playback,
    )

    assert [event["type"] for event in stored] == [
        "listener.final_transcript",
        "memory.answer_resolved",
        "tau.turn_plan.completed",
        "chatterbox.voice_render.completed",
        "playback.requested",
        "playback.started",
        "playback.ended",
    ]
    events = list_events(db, "s")
    assert events[3]["payload"]["audio"]["envelope"]["frames"][1]["treble"] == 0.8
    assert events[-1]["payload"]["sink"]["target"] == "59"
