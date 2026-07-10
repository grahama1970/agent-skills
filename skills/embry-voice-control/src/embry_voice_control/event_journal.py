"""Durable SQLite WAL journal for ordered Embry listener and turn events.

The journal owns canonical per-session sequencing. Producers submit complete
canonical event metadata except ``sequence``; SQLite allocates the next sequence
inside the same transaction as insertion. Event IDs are idempotent only for an
exact replay and fail closed on conflicts.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


EVENT_SCHEMA = "embry.voice_event.v1"
REQUIRED_TEXT_FIELDS = (
    "event_id",
    "session_id",
    "turn_id",
    "type",
    "created_at",
    "causation_id",
    "correlation_id",
    "producer",
    "receipt_hash",
)


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def connect(path: Path) -> sqlite3.Connection:
    """Open and initialize the event journal."""
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute(
        """CREATE TABLE IF NOT EXISTS events (
        event_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        turn_id TEXT NOT NULL,
        sequence INTEGER NOT NULL,
        event_type TEXT NOT NULL,
        created_at TEXT NOT NULL,
        causation_id TEXT NOT NULL,
        correlation_id TEXT NOT NULL,
        producer TEXT NOT NULL,
        mocked INTEGER NOT NULL CHECK (mocked IN (0, 1)),
        live INTEGER NOT NULL CHECK (live IN (0, 1)),
        artifact_hashes_json TEXT NOT NULL,
        receipt_hash TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        UNIQUE(session_id, sequence)
        )"""
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS consumers (
        consumer_name TEXT PRIMARY KEY,
        registered_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        )"""
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS consumer_offsets (
        consumer_name TEXT NOT NULL,
        session_id TEXT NOT NULL,
        sequence INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
        PRIMARY KEY (consumer_name, session_id),
        FOREIGN KEY (consumer_name) REFERENCES consumers(consumer_name)
        )"""
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS consumer_claims (
        consumer_name TEXT NOT NULL,
        event_id TEXT NOT NULL,
        claimed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
        acked_at TEXT,
        PRIMARY KEY (consumer_name, event_id),
        FOREIGN KEY (consumer_name) REFERENCES consumers(consumer_name),
        FOREIGN KEY (event_id) REFERENCES events(event_id)
        )"""
    )
    connection.commit()
    return connection


def validate_event(event: dict[str, Any]) -> None:
    """Reject incomplete, noncanonical, or producer-sequenced events."""
    if event.get("schema") != EVENT_SCHEMA:
        raise ValueError("event_schema_invalid")
    if "sequence" in event:
        raise ValueError("event_sequence_producer_supplied")
    for field in REQUIRED_TEXT_FIELDS:
        if not isinstance(event.get(field), str) or not event[field]:
            raise ValueError(f"event_missing_{field}")
    if not isinstance(event.get("mocked"), bool):
        raise ValueError("event_mocked_invalid")
    if not isinstance(event.get("live"), bool):
        raise ValueError("event_live_invalid")
    if not isinstance(event.get("artifact_hashes"), list) or not all(
        isinstance(item, str) and item for item in event["artifact_hashes"]
    ):
        raise ValueError("event_artifact_hashes_invalid")
    if not isinstance(event.get("payload"), dict):
        raise ValueError("event_payload_invalid")


def _row_to_event(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "schema": EVENT_SCHEMA,
        "event_id": row["event_id"],
        "session_id": row["session_id"],
        "turn_id": row["turn_id"],
        "sequence": row["sequence"],
        "type": row["event_type"],
        "created_at": row["created_at"],
        "causation_id": row["causation_id"],
        "correlation_id": row["correlation_id"],
        "producer": row["producer"],
        "mocked": bool(row["mocked"]),
        "live": bool(row["live"]),
        "artifact_hashes": json.loads(row["artifact_hashes_json"]),
        "receipt_hash": row["receipt_hash"],
        "payload": json.loads(row["payload_json"]),
    }


def _stored_event(connection: sqlite3.Connection, event_id: str) -> dict[str, Any] | None:
    row = connection.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()
    return None if row is None else _row_to_event(row)


def _without_sequence(event: dict[str, Any]) -> dict[str, Any]:
    copy = dict(event)
    copy.pop("sequence", None)
    return copy


def append_event(path: Path, event: dict[str, Any]) -> dict[str, Any]:
    """Append one event and return the canonical stored event.

    Exact duplicate event IDs return the existing stored event. Conflicting
    reuse of an event ID raises ``ValueError('event_id_conflict')``.
    """
    validate_event(event)
    payload_json = _json(event["payload"])
    artifact_hashes_json = _json(event["artifact_hashes"])
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        existing = _stored_event(connection, event["event_id"])
        if existing is not None:
            if _without_sequence(existing) == event:
                connection.commit()
                return existing
            connection.rollback()
            raise ValueError("event_id_conflict")
        row = connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 AS sequence FROM events WHERE session_id = ?",
            (event["session_id"],),
        ).fetchone()
        sequence = int(row["sequence"])
        connection.execute(
            """INSERT INTO events (
            event_id, session_id, turn_id, sequence, event_type, created_at,
            causation_id, correlation_id, producer, mocked, live,
            artifact_hashes_json, receipt_hash, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event["event_id"],
                event["session_id"],
                event["turn_id"],
                sequence,
                event["type"],
                event["created_at"],
                event["causation_id"],
                event["correlation_id"],
                event["producer"],
                int(event["mocked"]),
                int(event["live"]),
                artifact_hashes_json,
                event["receipt_hash"],
                payload_json,
            ),
        )
        stored = _stored_event(connection, event["event_id"])
        connection.commit()
    assert stored is not None
    return stored


def list_events(path: Path, session_id: str, after_sequence: int = 0) -> list[dict[str, Any]]:
    """Return ordered events for one session."""
    with connect(path) as connection:
        rows = connection.execute(
            "SELECT * FROM events WHERE session_id = ? AND sequence > ? ORDER BY sequence",
            (session_id, after_sequence),
        ).fetchall()
    return [_row_to_event(row) for row in rows]


def _register_consumer(connection: sqlite3.Connection, consumer_name: str, session_id: str) -> None:
    if not consumer_name:
        raise ValueError("consumer_name_missing")
    if not session_id:
        raise ValueError("session_id_missing")
    connection.execute(
        "INSERT OR IGNORE INTO consumers (consumer_name) VALUES (?)", (consumer_name,)
    )
    connection.execute(
        """INSERT OR IGNORE INTO consumer_offsets (consumer_name, session_id, sequence)
        VALUES (?, ?, 0)""",
        (consumer_name, session_id),
    )


def claim_events(path: Path, consumer_name: str, session_id: str, limit: int = 100) -> list[dict[str, Any]]:
    """Durably register a consumer claim and return restart-safe unacked events."""
    if limit < 1:
        raise ValueError("limit_invalid")
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _register_consumer(connection, consumer_name, session_id)
        offset = consumer_offset(path, consumer_name, session_id, connection=connection)
        rows = connection.execute(
            """SELECT e.* FROM events e
            LEFT JOIN consumer_claims c
              ON c.consumer_name = ? AND c.event_id = e.event_id
            WHERE e.session_id = ? AND e.sequence > ? AND c.acked_at IS NULL
            ORDER BY e.sequence LIMIT ?""",
            (consumer_name, session_id, offset, limit),
        ).fetchall()
        for row in rows:
            connection.execute(
                "INSERT OR IGNORE INTO consumer_claims (consumer_name, event_id) VALUES (?, ?)",
                (consumer_name, row["event_id"]),
            )
        events = [_row_to_event(row) for row in rows]
        connection.commit()
    return events


def ack_event(path: Path, consumer_name: str, event_id: str) -> int:
    """Ack one claimed event and advance the durable contiguous cursor."""
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()
        if row is None:
            connection.rollback()
            raise ValueError("event_id_unknown")
        _register_consumer(connection, consumer_name, row["session_id"])
        claim = connection.execute(
            "SELECT * FROM consumer_claims WHERE consumer_name = ? AND event_id = ?",
            (consumer_name, event_id),
        ).fetchone()
        if claim is None:
            connection.rollback()
            raise ValueError("event_not_claimed")
        connection.execute(
            """UPDATE consumer_claims
            SET acked_at = COALESCE(acked_at, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            WHERE consumer_name = ? AND event_id = ?""",
            (consumer_name, event_id),
        )
        offset = int(connection.execute(
            "SELECT sequence FROM consumer_offsets WHERE consumer_name = ? AND session_id = ?",
            (consumer_name, row["session_id"]),
        ).fetchone()["sequence"])
        while True:
            next_row = connection.execute(
                "SELECT event_id FROM events WHERE session_id = ? AND sequence = ?",
                (row["session_id"], offset + 1),
            ).fetchone()
            if next_row is None:
                break
            acked = connection.execute(
                """SELECT 1 FROM consumer_claims
                WHERE consumer_name = ? AND event_id = ? AND acked_at IS NOT NULL""",
                (consumer_name, next_row["event_id"]),
            ).fetchone()
            if acked is None:
                break
            offset += 1
        connection.execute(
            """UPDATE consumer_offsets
            SET sequence = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE consumer_name = ? AND session_id = ?""",
            (offset, consumer_name, row["session_id"]),
        )
        connection.commit()
    return offset


def consumer_offset(
    path: Path,
    consumer_name: str,
    session_id: str,
    *,
    connection: sqlite3.Connection | None = None,
) -> int:
    """Return a consumer's durable acknowledged sequence for a session."""
    own_connection = connection is None
    if connection is None:
        connection = connect(path)
    try:
        _register_consumer(connection, consumer_name, session_id)
        row = connection.execute(
            "SELECT sequence FROM consumer_offsets WHERE consumer_name = ? AND session_id = ?",
            (consumer_name, session_id),
        ).fetchone()
        if own_connection:
            connection.commit()
        return 0 if row is None else int(row["sequence"])
    finally:
        if own_connection:
            connection.close()


def session_ids(path: Path) -> list[str]:
    """Return sessions ordered by first event insertion."""
    with connect(path) as connection:
        rows = connection.execute(
            "SELECT session_id, MIN(rowid) AS first_row FROM events GROUP BY session_id ORDER BY first_row"
        ).fetchall()
    return [str(row["session_id"]) for row in rows]
