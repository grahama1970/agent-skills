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


def event(*, event_id: str, session_id: str = "session-a") -> dict:
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
        "artifact_hashes": ["sha256:abc"],
        "receipt_hash": "sha256:def",
        "payload": {"text": "Embry"},
    }


def test_journal_allocates_ordered_sequences_and_persists(tmp_path: Path) -> None:
    db = tmp_path / "events.sqlite3"
    first = append_event(db, event(event_id="first"))
    second = append_event(db, event(event_id="second"))

    assert first["sequence"] == 1
    assert second["sequence"] == 2
    assert [row["sequence"] for row in list_events(db, "session-a")] == [1, 2]


def test_producer_sequence_is_rejected(tmp_path: Path) -> None:
    db = tmp_path / "events.sqlite3"
    supplied = event(event_id="sequenced")
    supplied["sequence"] = 99

    with pytest.raises(ValueError, match="event_sequence_producer_supplied"):
        append_event(db, supplied)


def test_exact_event_replay_is_idempotent_and_returns_stored_event(tmp_path: Path) -> None:
    db = tmp_path / "events.sqlite3"
    original = append_event(db, event(event_id="same"))
    replay = append_event(db, event(event_id="same"))

    assert replay == original
    assert len(list_events(db, "session-a")) == 1


def test_event_id_conflict_fails_closed(tmp_path: Path) -> None:
    db = tmp_path / "events.sqlite3"
    append_event(db, event(event_id="same"))
    conflicting = event(event_id="same")
    conflicting["payload"] = {"text": "different"}

    with pytest.raises(ValueError, match="event_id_conflict"):
        append_event(db, conflicting)


def test_required_canonical_fields_fail_closed(tmp_path: Path) -> None:
    db = tmp_path / "events.sqlite3"
    incomplete = event(event_id="missing")
    del incomplete["receipt_hash"]

    with pytest.raises(ValueError, match="event_missing_receipt_hash"):
        append_event(db, incomplete)


def test_consumer_claim_ack_and_offset_survive_restart(tmp_path: Path) -> None:
    db = tmp_path / "events.sqlite3"
    one = append_event(db, event(event_id="one"))
    two = append_event(db, event(event_id="two"))

    claimed = claim_events(db, "consumer-a", "session-a", limit=10)
    assert [row["event_id"] for row in claimed] == ["one", "two"]
    assert consumer_offset(db, "consumer-a", "session-a") == 0

    assert ack_event(db, "consumer-a", two["event_id"]) == 0
    assert consumer_offset(db, "consumer-a", "session-a") == 0
    assert ack_event(db, "consumer-a", one["event_id"]) == 2
    assert consumer_offset(db, "consumer-a", "session-a") == 2
    assert claim_events(db, "consumer-a", "session-a", limit=10) == []
