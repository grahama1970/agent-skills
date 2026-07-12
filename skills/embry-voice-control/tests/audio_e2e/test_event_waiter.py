from datetime import datetime, timezone
from pathlib import Path

from embry_voice_control.audio_e2e.event_waiter import managed_fields_match, wait_for_managed_wake
from embry_voice_control.audio_e2e.case_executor import _request_wer
from embry_voice_control.event_journal import append_event


def _event(event_type: str, event_id: str, managed: dict[str, str]) -> dict:
    return {
        "schema": "embry.voice_event.v1",
        "event_id": event_id,
        "session_id": managed["session_id"],
        "turn_id": managed["turn_id"],
        "type": event_type,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "causation_id": "root",
        "correlation_id": managed["campaign_id"],
        "producer": "test",
        "mocked": False,
        "live": True,
        "artifact_hashes": {},
        "receipt_hash": event_id,
        "payload": {"managed_turn": managed},
    }


def test_managed_fields_match_accepts_final_transcript_nested_contract() -> None:
    expected = {
        "campaign_id": "campaign-1", "case_id": "case-1", "attempt_id": "attempt-1",
        "session_id": "session-1", "turn_id": "turn-1", "source_authority_id": "source-1",
    }
    event = {"payload": {"managed_turn": expected}}
    assert managed_fields_match(event, expected)


def test_managed_fields_match_rejects_wrong_turn() -> None:
    expected = {"turn_id": "turn-1"}
    assert not managed_fields_match({"payload": {"managed_turn": {"turn_id": "turn-2"}}}, expected)


def test_managed_fields_match_reads_session_and_turn_from_event_envelope() -> None:
    expected = {
        "campaign_id": "campaign-1", "case_id": "case-1", "attempt_id": "attempt-1",
        "session_id": "session-1", "turn_id": "turn-1", "source_authority_id": "source-1",
    }
    event = {
        "session_id": "session-1",
        "turn_id": "turn-1",
        "payload": {
            "campaign_id": "campaign-1", "case_id": "case-1", "attempt_id": "attempt-1",
            "source_authority_id": "source-1",
        },
    }
    assert managed_fields_match(event, expected)


def test_wait_for_managed_wake_returns_exact_post_arm_event(tmp_path: Path) -> None:
    expected = {
        "campaign_id": "campaign-1", "case_id": "case-1", "attempt_id": "attempt-1",
        "session_id": "session-1", "turn_id": "turn-1", "source_authority_id": "source-1",
    }
    db = tmp_path / "journal.sqlite3"
    append_event(db, _event("listener.turn_armed", "arm-1", expected))
    wrong = {**expected, "turn_id": "turn-2"}
    append_event(db, _event("listener.wake_detected", "wake-wrong", wrong))
    append_event(db, _event("listener.wake_detected", "wake-right", expected))
    wake = wait_for_managed_wake(
        db, session_id="session-1", expected=expected, timeout_seconds=0.1, poll_seconds=0.01,
    )
    assert wake["event_id"] == "wake-right"


def test_request_wer_ignores_wake_prefix_but_rejects_clipped_question() -> None:
    expected = "Hey Embry, what evidence should a SPARTA Question Reasoning Answer pair include to be acceptable?"
    assert _request_wer(expected, "What evidence should a Sparta question reasoning answer pair include to be acceptable?") == 0
    assert _request_wer(expected, "Reasoning answer pair include to be acceptable.") > 0.25
