"""Deterministic contract checks for the Embry event journal."""

from pathlib import Path
import sqlite3

import pytest

from embry_voice_control.event_journal import append_event, list_events


def event(sequence: int, *, event_id: str | None = None, session_id: str = "session-a") -> dict:
    return {
        "schema": "embry.voice_event.v1",
        "event_id": event_id or f"event-{sequence}",
        "session_id": session_id,
        "turn_id": "turn-a",
        "sequence": sequence,
        "type": "listener.final_transcript",
        "created_at": "2026-07-10T12:00:00Z",
        "payload": {"text": "Embry"},
    }


def test_journal_is_ordered_and_persists_across_connections(tmp_path: Path) -> None:
    db = tmp_path / "events.sqlite3"
    assert append_event(db, event(2)) is True
    assert append_event(db, event(1)) is True

    assert [row["sequence"] for row in list_events(db, "session-a")] == [1, 2]


def test_exact_event_replay_is_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "events.sqlite3"
    assert append_event(db, event(1)) is True
    assert append_event(db, event(1)) is False
    assert len(list_events(db, "session-a")) == 1


def test_event_id_conflict_fails_closed(tmp_path: Path) -> None:
    db = tmp_path / "events.sqlite3"
    append_event(db, event(1, event_id="same"))

    with pytest.raises(ValueError, match="event_id_conflict"):
        append_event(db, event(2, event_id="same"))


def test_session_sequence_collision_fails_closed(tmp_path: Path) -> None:
    db = tmp_path / "events.sqlite3"
    append_event(db, event(1, event_id="one"))

    with pytest.raises(sqlite3.IntegrityError):
        append_event(db, event(1, event_id="two"))
