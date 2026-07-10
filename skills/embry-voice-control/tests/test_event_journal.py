"""Deterministic contract checks for the Embry event journal."""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from embry_voice_control.event_journal import (
    ack_event,
    append_event,
    claim_events,
    consumer_offset,
    list_events,
)


def event(*, event_id: str = "event-1", session_id: str = "session-a") -> dict:
    return {
        "schema": "embry.voice_event.v1",
        "event_id": event_id,
        "session_id": session_id,
        "turn_id": "turn-a",
        "type": "listener.final_transcript",
        "created_at": "2026-07-10T12:00:00Z",
        "causation_id": "cause-a",
        "correlation_id": "corr-a",
        "producer": "test-producer",
        "mocked": False,
        "live": True,
        "artifact_hashes": {"receipt": "sha256:abc"},
        "receipt_hash": "sha256:def",
        "payload": {"text": "Embry"},
    }


def test_journal_allocates_sequence_and_persists_across_connections(tmp_path: Path) -> None:
    db = tmp_path / "events.sqlite3"
    assert append_event(db, event(event_id="two"))["sequence"] == 1
    assert append_event(db, event(event_id="one"))["sequence"] == 2

    assert [row["sequence"] for row in list_events(db, "session-a")] == [1, 2]


def test_producer_sequence_is_rejected(tmp_path: Path) -> None:
    db = tmp_path / "events.sqlite3"
    bad = event()
    bad["sequence"] = 7

    with pytest.raises(ValueError, match="event_sequence_forbidden"):
        append_event(db, bad)


def test_required_canonical_fields_are_enforced(tmp_path: Path) -> None:
    db = tmp_path / "events.sqlite3"
    bad = event()
    del bad["receipt_hash"]

    with pytest.raises(ValueError, match="event_missing_receipt_hash"):
        append_event(db, bad)


def test_exact_event_replay_is_idempotent_and_returns_stored_event(tmp_path: Path) -> None:
    db = tmp_path / "events.sqlite3"
    first = append_event(db, event())
    second = append_event(db, event())
    assert first == second
    assert len(list_events(db, "session-a")) == 1


def test_event_id_conflict_fails_closed(tmp_path: Path) -> None:
    db = tmp_path / "events.sqlite3"
    append_event(db, event(event_id="same"))
    conflicting = event(event_id="same")
    conflicting["payload"] = {"text": "different"}

    with pytest.raises(ValueError, match="event_id_conflict"):
        append_event(db, conflicting)


def test_consumer_claim_ack_and_offset_are_restart_safe(tmp_path: Path) -> None:
    db = tmp_path / "events.sqlite3"
    stored = append_event(db, event(event_id="one"))

    assert consumer_offset(db, "consumer-a", "session-a") == 0
    assert [row["event_id"] for row in claim_events(db, "consumer-a")] == ["one"]
    assert [row["event_id"] for row in claim_events(db, "consumer-a")] == ["one"]
    assert ack_event(db, "consumer-a", stored["event_id"])["sequence"] == stored["sequence"]
    assert consumer_offset(db, "consumer-a", "session-a") == stored["sequence"]
    assert claim_events(db, "consumer-a") == []
