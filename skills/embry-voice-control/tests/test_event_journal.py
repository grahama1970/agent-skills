"""Deterministic contract checks for the Embry event journal."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

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
        "producer": "test",
        "mocked": False,
        "live": True,
        "artifact_hashes": {},
        "receipt_hash": "sha256:test",
        "payload": {"text": "Embry"},
    }


def test_journal_allocates_ordered_sequences_and_persists(tmp_path: Path) -> None:
    db = tmp_path / "events.sqlite3"
    second = append_event(db, event(event_id="event-2"))
    first = append_event(db, event(event_id="event-1"))

    assert second["sequence"] == 1
    assert first["sequence"] == 2
    assert [row["sequence"] for row in list_events(db, "session-a")] == [1, 2]


def test_producer_sequence_is_rejected(tmp_path: Path) -> None:
    db = tmp_path / "events.sqlite3"
    supplied = event()
    supplied["sequence"] = 7

    with pytest.raises(ValueError, match="event_sequence_producer_supplied"):
        append_event(db, supplied)


def test_exact_event_replay_is_idempotent_and_returns_stored_event(tmp_path: Path) -> None:
    db = tmp_path / "events.sqlite3"
    stored = append_event(db, event())
    replay = append_event(db, event())

    assert replay == stored
    assert len(list_events(db, "session-a")) == 1


def test_event_id_conflict_fails_closed(tmp_path: Path) -> None:
    db = tmp_path / "events.sqlite3"
    append_event(db, event(event_id="same"))

    conflicting = event(event_id="same")
    conflicting["payload"] = {"text": "different"}
    with pytest.raises(ValueError, match="event_id_conflict"):
        append_event(db, conflicting)


def test_consumer_claim_ack_and_restart_safe_offset(tmp_path: Path) -> None:
    db = tmp_path / "events.sqlite3"
    one = append_event(db, event(event_id="one"))
    two = append_event(db, event(event_id="two"))

    claimed = claim_events(db, "consumer-a", limit=1, lease_seconds=30)
    assert [row["event_id"] for row in claimed] == ["one"]
    assert claim_events(db, "consumer-a", limit=10, lease_seconds=30) == [two]

    assert ack_event(db, "consumer-a", one["event_id"]) is True
    assert ack_event(db, "consumer-a", one["event_id"]) is True
    assert consumer_offset(db, "consumer-a", "session-a") == 1

    assert ack_event(db, "consumer-a", two["event_id"]) is True
    assert consumer_offset(db, "consumer-a", "session-a") == 2
    assert claim_events(db, "consumer-a", limit=10, lease_seconds=30) == []


def test_claim_lease_is_exclusive_until_expiry(tmp_path: Path) -> None:
    db = tmp_path / "events.sqlite3"
    append_event(db, event(event_id="one"))

    assert len(claim_events(db, "consumer-a", limit=1, lease_seconds=30)) == 1
    assert claim_events(db, "consumer-a", limit=1, lease_seconds=30) == []
    assert len(claim_events(db, "consumer-b", limit=1, lease_seconds=30)) == 1
