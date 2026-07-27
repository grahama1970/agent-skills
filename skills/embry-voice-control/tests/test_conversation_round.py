from __future__ import annotations

import json
from pathlib import Path

from embry_voice_control import conversation_round
from embry_voice_control.event_journal import list_events


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def test_conversation_round_live_owns_receipt_and_journal(monkeypatch, tmp_path):
    session_id = "embry-conversation-round-test"
    transport_out_seen: list[Path] = []

    def fake_transport(*, runner, chatterbox_repo, transport_out_dir, sparta_api, questions, timeout):
        transport_out_seen.append(transport_out_dir)
        audio1 = transport_out_dir / "turn-001-answer.wav"
        audio2 = transport_out_dir / "turn-002-answer.wav"
        audio1.write_bytes(b"RIFFturn1")
        audio2.write_bytes(b"RIFFturn2")

        turns = []
        for index, (question, answer, answer_type) in enumerate([
            (
                "Hey Embry, tell me a short story about your cat and ask me one question about it.",
                "Miso found a tiny red toy mouse. What should she do next?",
                "session_story_generation",
            ),
            ("What did the cat find?", "a tiny red toy mouse", "session_story_context"),
        ], start=1):
            turn_id = f"{session_id}:turn-{index:03d}:embry-answer"
            response = {
                "status": "ok",
                "mocked": False,
                "live": True,
                "sessionId": session_id,
                "turnId": turn_id,
                "answerText": answer,
                "answerAuthority": "memory",
                "memory": {
                    "intent": {"action": "QUERY"},
                    "answer": {
                        "ok": True,
                        "can_answer": True,
                        "answer_type": answer_type,
                        "source_answer": answer,
                        "final_response": answer,
                        "session_context_authority": "memory",
                        "story_context_recovered": index == 2,
                        "answer_uses_story_fact": index == 2,
                    },
                },
                "tauBoundary": {"route_taken": "memory_answer"},
                "turnAuthority": {"assistantText": answer},
                "audioAuthority": {"path": str(audio1 if index == 1 else audio2), "sha256": "abc123"},
                "audioPath": str(audio1 if index == 1 else audio2),
                "voiceEnvelope": {"durationMs": 1000, "frames": [{"level": 0.1, "bass": 0.1, "mid": 0.1, "treble": 0.1}]},
                "reasoningSteps": [{}, {}, {}, {}],
            }
            response_path = transport_out_dir / f"turn-{index:03d}" / "sparta_live_turn.json"
            _write_json(response_path, response)
            turns.append({
                "turn_index": index,
                "question": question,
                "realtimestt_final_transcript": question,
                "virtual_realtimestt_route": {
                    "pass": True,
                    "realtimestt": {"receipt_path": str(transport_out_dir / f"turn-{index:03d}" / "realtimestt.json")},
                },
                "sparta_live_turn": {
                    "response_path": str(response_path),
                    "answer_authority": "memory",
                    "answer_text": answer,
                    "audio_path": str(audio1 if index == 1 else audio2),
                    "memory_answer": response["memory"]["answer"],
                },
                "answer_playback": {"returncode": 0, "target": "jabra-test"},
            })
        _write_json(transport_out_dir / "summary.json", {
            "pass": True,
            "mocked": False,
            "live": True,
            "session_id": session_id,
            "turns": turns,
        })
        return 0, '{"pass": true}', ""

    monkeypatch.setattr(conversation_round, "run_transport_adapter", fake_transport)
    receipt = conversation_round.run_conversation_round_live(
        output_root=tmp_path / "outputs",
        chatterbox_repo=tmp_path,
        runner=tmp_path / "runner.py",
        journal_db=tmp_path / "voice-events.sqlite3",
        questions=None,
    )

    assert receipt["pass"] is True
    assert receipt["mocked"] is False
    assert receipt["live"] is True
    assert receipt["transport"]["adapter"].endswith("runner.py")
    assert receipt["journal"]["published"] is True
    assert [turn["event_count"] for turn in receipt["journal"]["turns"]] == [7, 7]
    events = list_events(tmp_path / "voice-events.sqlite3", session_id)
    assert [event["type"] for event in events].count("listener.final_transcript") == 2
    assert [event["type"] for event in events].count("playback.ended") == 2
    assert transport_out_seen

