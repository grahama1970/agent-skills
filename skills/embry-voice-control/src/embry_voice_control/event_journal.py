"""Durable SQLite WAL journal for ordered Embry listener and turn events.

Inputs are explicit event dictionaries carrying event, session, turn, and
sequence identifiers. Outputs are idempotently persisted rows. Invalid or
conflicting events fail closed; no latest-file discovery is performed.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


EVENT_SCHEMA = "embry.voice_event.v1"


def connect(path: Path) -> sqlite3.Connection:
    """Open and initialize the event journal."""
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute(
        """CREATE TABLE IF NOT EXISTS events (
        event_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        turn_id TEXT NOT NULL,
        sequence INTEGER NOT NULL,
        event_type TEXT NOT NULL,
        created_at TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        UNIQUE(session_id, sequence)
        )"""
    )
    connection.commit()
    return connection


def validate_event(event: dict[str, Any]) -> None:
    """Reject incomplete or noncanonical events."""
    if event.get("schema") != EVENT_SCHEMA:
        raise ValueError("event_schema_invalid")
    for field in ("event_id", "session_id", "turn_id", "type", "created_at"):
        if not isinstance(event.get(field), str) or not event[field]:
            raise ValueError(f"event_missing_{field}")
    if not isinstance(event.get("sequence"), int) or event["sequence"] < 1:
        raise ValueError("event_sequence_invalid")
    if not isinstance(event.get("payload"), dict):
        raise ValueError("event_payload_invalid")


def append_event(path: Path, event: dict[str, Any]) -> bool:
    """Append one event, returning False for an exact idempotent replay."""
    validate_event(event)
    payload_json = json.dumps(event["payload"], sort_keys=True, separators=(",", ":"))
    with connect(path) as connection:
        existing = connection.execute(
            "SELECT * FROM events WHERE event_id = ?", (event["event_id"],)
        ).fetchone()
        if existing is not None:
            exact = (
                existing["session_id"] == event["session_id"]
                and existing["turn_id"] == event["turn_id"]
                and existing["sequence"] == event["sequence"]
                and existing["event_type"] == event["type"]
                and existing["created_at"] == event["created_at"]
                and existing["payload_json"] == payload_json
            )
            if exact:
                return False
            raise ValueError("event_id_conflict")
        connection.execute(
            "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                event["event_id"], event["session_id"], event["turn_id"],
                event["sequence"], event["type"], event["created_at"], payload_json,
            ),
        )
        connection.commit()
    return True


def list_events(path: Path, session_id: str, after_sequence: int = 0) -> list[dict[str, Any]]:
    """Return ordered events for one session."""
    with connect(path) as connection:
        rows = connection.execute(
            "SELECT * FROM events WHERE session_id = ? AND sequence > ? ORDER BY sequence",
            (session_id, after_sequence),
        ).fetchall()
    return [
        {
            "schema": EVENT_SCHEMA,
            "event_id": row["event_id"],
            "session_id": row["session_id"],
            "turn_id": row["turn_id"],
            "sequence": row["sequence"],
            "type": row["event_type"],
            "created_at": row["created_at"],
            "payload": json.loads(row["payload_json"]),
        }
        for row in rows
    ]


def session_ids(path: Path) -> list[str]:
    """Return sessions ordered by first event insertion."""
    with connect(path) as connection:
        rows = connection.execute(
            "SELECT session_id, MIN(rowid) AS first_row FROM events GROUP BY session_id ORDER BY first_row"
        ).fetchall()
    return [str(row["session_id"]) for row in rows]
