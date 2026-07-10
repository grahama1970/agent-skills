"""Durable SQLite WAL journal for ordered Embry listener and turn events.

Producers provide canonical event identity and provenance, but never choose the
per-session sequence. SQLite allocates the next sequence in the same transaction
that stores the event. Exact duplicate event IDs are idempotent and return the
stored event; conflicting event IDs fail closed.
"""

from __future__ import annotations

from datetime import datetime, timezone
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


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(path: Path) -> sqlite3.Connection:
    """Open and initialize the event journal."""
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute(
        """CREATE TABLE IF NOT EXISTS session_sequences (
        session_id TEXT PRIMARY KEY,
        last_sequence INTEGER NOT NULL DEFAULT 0
        )"""
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS events (
        event_offset INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT NOT NULL UNIQUE,
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
        consumer_id TEXT PRIMARY KEY,
        cursor_offset INTEGER NOT NULL DEFAULT 0,
        registered_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
        )"""
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS consumer_events (
        consumer_id TEXT NOT NULL,
        event_offset INTEGER NOT NULL,
        event_id TEXT NOT NULL,
        state TEXT NOT NULL CHECK (state IN ('claimed', 'acked')),
        claimed_at TEXT NOT NULL,
        acked_at TEXT,
        PRIMARY KEY (consumer_id, event_offset),
        FOREIGN KEY (consumer_id) REFERENCES consumers(consumer_id),
        FOREIGN KEY (event_offset) REFERENCES events(event_offset)
        )"""
    )
    connection.commit()
    return connection


def validate_event(event: dict[str, Any]) -> None:
    """Reject incomplete, noncanonical, or producer-sequenced events."""
    if event.get("schema") != EVENT_SCHEMA:
        raise ValueError("event_schema_invalid")
    if "sequence" in event:
        raise ValueError("event_sequence_producer_forbidden")
    for field in REQUIRED_TEXT_FIELDS:
        if not isinstance(event.get(field), str) or not event[field]:
            raise ValueError(f"event_missing_{field}")
    if not isinstance(event.get("mocked"), bool):
        raise ValueError("event_mocked_invalid")
    if not isinstance(event.get("live"), bool):
        raise ValueError("event_live_invalid")
    artifact_hashes = event.get("artifact_hashes")
    if not isinstance(artifact_hashes, list) or not all(
        isinstance(item, str) and item for item in artifact_hashes
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


def _event_matches_row(event: dict[str, Any], row: sqlite3.Row) -> bool:
    return (
        row["session_id"] == event["session_id"]
        and row["turn_id"] == event["turn_id"]
        and row["event_type"] == event["type"]
        and row["created_at"] == event["created_at"]
        and row["causation_id"] == event["causation_id"]
        and row["correlation_id"] == event["correlation_id"]
        and row["producer"] == event["producer"]
        and bool(row["mocked"]) is event["mocked"]
        and bool(row["live"]) is event["live"]
        and row["artifact_hashes_json"] == _json_dumps(event["artifact_hashes"])
        and row["receipt_hash"] == event["receipt_hash"]
        and row["payload_json"] == _json_dumps(event["payload"])
    )


def append_event(path: Path, event: dict[str, Any]) -> dict[str, Any]:
    """Append one event and return the canonical stored event."""
    validate_event(event)
    payload_json = _json_dumps(event["payload"])
    artifact_hashes_json = _json_dumps(event["artifact_hashes"])
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        existing = connection.execute(
            "SELECT * FROM events WHERE event_id = ?", (event["event_id"],)
        ).fetchone()
        if existing is not None:
            if _event_matches_row(event, existing):
                return _row_to_event(existing)
            raise ValueError("event_id_conflict")
        connection.execute(
            "INSERT OR IGNORE INTO session_sequences(session_id, last_sequence) VALUES (?, 0)",
            (event["session_id"],),
        )
        sequence = int(connection.execute(
            "SELECT last_sequence + 1 FROM session_sequences WHERE session_id = ?",
            (event["session_id"],),
        ).fetchone()[0])
        connection.execute(
            "UPDATE session_sequences SET last_sequence = ? WHERE session_id = ?",
            (sequence, event["session_id"]),
        )
        cursor = connection.execute(
            """INSERT INTO events (
            event_id, session_id, turn_id, sequence, event_type, created_at,
            causation_id, correlation_id, producer, mocked, live,
            artifact_hashes_json, receipt_hash, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event["event_id"], event["session_id"], event["turn_id"], sequence,
                event["type"], event["created_at"], event["causation_id"],
                event["correlation_id"], event["producer"], int(event["mocked"]),
                int(event["live"]), artifact_hashes_json, event["receipt_hash"], payload_json,
            ),
        )
        stored = connection.execute(
            "SELECT * FROM events WHERE event_offset = ?", (cursor.lastrowid,)
        ).fetchone()
        connection.commit()
        return _row_to_event(stored)


def _register_consumer(connection: sqlite3.Connection, consumer_id: str) -> None:
    if not consumer_id:
        raise ValueError("consumer_id_required")
    now = _utc_now()
    connection.execute(
        """INSERT INTO consumers(consumer_id, cursor_offset, registered_at, updated_at)
        VALUES (?, 0, ?, ?)
        ON CONFLICT(consumer_id) DO UPDATE SET updated_at = excluded.updated_at""",
        (consumer_id, now, now),
    )


def claim_events(path: Path, consumer_id: str, limit: int = 100) -> list[dict[str, Any]]:
    """Durably claim unacked events after a consumer cursor."""
    if limit < 1:
        raise ValueError("claim_limit_invalid")
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _register_consumer(connection, consumer_id)
        cursor_offset = int(connection.execute(
            "SELECT cursor_offset FROM consumers WHERE consumer_id = ?", (consumer_id,)
        ).fetchone()[0])
        rows = connection.execute(
            """SELECT e.* FROM events e
            LEFT JOIN consumer_events ce
              ON ce.consumer_id = ? AND ce.event_offset = e.event_offset
            WHERE e.event_offset > ? AND (ce.state IS NULL OR ce.state = 'claimed')
            ORDER BY e.event_offset LIMIT ?""",
            (consumer_id, cursor_offset, limit),
        ).fetchall()
        now = _utc_now()
        for row in rows:
            connection.execute(
                """INSERT INTO consumer_events(
                consumer_id, event_offset, event_id, state, claimed_at
                ) VALUES (?, ?, ?, 'claimed', ?)
                ON CONFLICT(consumer_id, event_offset) DO UPDATE SET
                state = 'claimed', claimed_at = excluded.claimed_at""",
                (consumer_id, row["event_offset"], row["event_id"], now),
            )
        connection.commit()
    return [_row_to_event(row) for row in rows]


def ack_event(path: Path, consumer_id: str, event_id: str) -> int:
    """Ack a claimed event and advance the durable contiguous cursor."""
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _register_consumer(connection, consumer_id)
        row = connection.execute("SELECT event_offset FROM events WHERE event_id = ?", (event_id,)).fetchone()
        if row is None:
            raise ValueError("event_unknown")
        event_offset = int(row["event_offset"])
        claim = connection.execute(
            """SELECT state FROM consumer_events
            WHERE consumer_id = ? AND event_offset = ?""",
            (consumer_id, event_offset),
        ).fetchone()
        if claim is None:
            raise ValueError("event_not_claimed")
        now = _utc_now()
        connection.execute(
            """UPDATE consumer_events SET state = 'acked', acked_at = ?
            WHERE consumer_id = ? AND event_offset = ?""",
            (now, consumer_id, event_offset),
        )
        while True:
            cursor_offset = int(connection.execute(
                "SELECT cursor_offset FROM consumers WHERE consumer_id = ?", (consumer_id,)
            ).fetchone()[0])
            next_row = connection.execute(
                """SELECT event_offset FROM events
                WHERE event_offset > ? ORDER BY event_offset LIMIT 1""",
                (cursor_offset,),
            ).fetchone()
            if next_row is None:
                break
            next_offset = int(next_row["event_offset"])
            acked = connection.execute(
                """SELECT 1 FROM consumer_events
                WHERE consumer_id = ? AND event_offset = ? AND state = 'acked'""",
                (consumer_id, next_offset),
            ).fetchone()
            if acked is None:
                break
            connection.execute(
                "UPDATE consumers SET cursor_offset = ?, updated_at = ? WHERE consumer_id = ?",
                (next_offset, now, consumer_id),
            )
        offset = consumer_offset(path, consumer_id, _connection=connection)
        connection.commit()
        return offset


def consumer_offset(path: Path, consumer_id: str, _connection: sqlite3.Connection | None = None) -> int:
    """Return a consumer's durable contiguous ack cursor."""
    connection = _connection or connect(path)
    try:
        row = connection.execute(
            "SELECT cursor_offset FROM consumers WHERE consumer_id = ?", (consumer_id,)
        ).fetchone()
        return 0 if row is None else int(row["cursor_offset"])
    finally:
        if _connection is None:
            connection.close()


def list_events(path: Path, session_id: str, after_sequence: int = 0) -> list[dict[str, Any]]:
    """Return ordered events for one session."""
    with connect(path) as connection:
        rows = connection.execute(
            "SELECT * FROM events WHERE session_id = ? AND sequence > ? ORDER BY sequence",
            (session_id, after_sequence),
        ).fetchall()
    return [_row_to_event(row) for row in rows]


def session_ids(path: Path) -> list[str]:
    """Return sessions ordered by first event insertion."""
    with connect(path) as connection:
        rows = connection.execute(
            "SELECT session_id, MIN(event_offset) AS first_row FROM events GROUP BY session_id ORDER BY first_row"
        ).fetchall()
    return [str(row["session_id"]) for row in rows]


__all__ = ["append_event", "claim_events", "ack_event", "consumer_offset"]
