"""Durable SQLite WAL journal for ordered Embry listener and turn events.

Producers provide canonical event identity and metadata, but never choose the
per-session journal sequence.  SQLite allocates the next sequence inside the
same transaction that inserts the event.  Exact duplicate event submissions are
idempotent and return the already stored canonical event; conflicting reuse of
an event id fails closed.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3
from pathlib import Path
from typing import Any


EVENT_SCHEMA = "embry.voice_event.v1"
_REQUIRED_TEXT_FIELDS = (
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
_REQUIRED_BOOL_FIELDS = ("mocked", "live")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
        )"""
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS consumer_offsets (
        consumer_name TEXT NOT NULL,
        session_id TEXT NOT NULL,
        sequence INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (consumer_name, session_id),
        FOREIGN KEY (consumer_name) REFERENCES consumers(consumer_name)
        )"""
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS consumer_event_state (
        consumer_name TEXT NOT NULL,
        event_id TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('claimed', 'acked')),
        claimed_at TEXT NOT NULL,
        acked_at TEXT,
        PRIMARY KEY (consumer_name, event_id),
        FOREIGN KEY (consumer_name) REFERENCES consumers(consumer_name),
        FOREIGN KEY (event_id) REFERENCES events(event_id)
        )"""
    )
    connection.commit()
    return connection


def validate_event(event: dict[str, Any]) -> None:
    """Reject incomplete or noncanonical producer events."""
    if event.get("schema") != EVENT_SCHEMA:
        raise ValueError("event_schema_invalid")
    if "sequence" in event:
        raise ValueError("event_sequence_forbidden")
    for field in _REQUIRED_TEXT_FIELDS:
        if not isinstance(event.get(field), str) or not event[field]:
            raise ValueError(f"event_missing_{field}")
    for field in _REQUIRED_BOOL_FIELDS:
        if not isinstance(event.get(field), bool):
            raise ValueError(f"event_missing_{field}")
    if not isinstance(event.get("artifact_hashes"), dict):
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


def _select_event(connection: sqlite3.Connection, event_id: str) -> sqlite3.Row | None:
    return connection.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()


def _is_exact_duplicate(row: sqlite3.Row, event: dict[str, Any]) -> bool:
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
        and row["artifact_hashes_json"] == _json(event["artifact_hashes"])
        and row["receipt_hash"] == event["receipt_hash"]
        and row["payload_json"] == _json(event["payload"])
    )


def append_event(path: Path, event: dict[str, Any]) -> dict[str, Any]:
    """Append one event and return the canonical stored event.

    The caller must not provide ``sequence``.  SQLite assigns the next positive
    sequence for the session while the write transaction is held.
    """
    validate_event(event)
    artifact_hashes_json = _json(event["artifact_hashes"])
    payload_json = _json(event["payload"])
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        existing = _select_event(connection, event["event_id"])
        if existing is not None:
            if _is_exact_duplicate(existing, event):
                connection.commit()
                return _row_to_event(existing)
            connection.rollback()
            raise ValueError("event_id_conflict")
        sequence = connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence FROM events WHERE session_id = ?",
            (event["session_id"],),
        ).fetchone()["next_sequence"]
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
        stored = _select_event(connection, event["event_id"])
        connection.commit()
    if stored is None:  # defensive; insert succeeded above
        raise RuntimeError("event_insert_missing")
    return _row_to_event(stored)


def list_events(path: Path, session_id: str, after_sequence: int = 0) -> list[dict[str, Any]]:
    """Return ordered events for one session."""
    with connect(path) as connection:
        rows = connection.execute(
            "SELECT * FROM events WHERE session_id = ? AND sequence > ? ORDER BY sequence",
            (session_id, after_sequence),
        ).fetchall()
    return [_row_to_event(row) for row in rows]


def _register_consumer(connection: sqlite3.Connection, consumer_name: str) -> None:
    if not consumer_name:
        raise ValueError("consumer_name_missing")
    now = _utc_now()
    connection.execute(
        """INSERT INTO consumers (consumer_name, created_at, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(consumer_name) DO UPDATE SET updated_at = excluded.updated_at""",
        (consumer_name, now, now),
    )


def claim_events(
    path: Path,
    consumer_name: str,
    *,
    session_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Durably register a consumer and claim restart-safe unacked events."""
    if limit < 1:
        raise ValueError("claim_limit_invalid")
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _register_consumer(connection, consumer_name)
        params: list[Any] = [consumer_name]
        session_clause = ""
        if session_id is not None:
            session_clause = "AND e.session_id = ?"
            params.append(session_id)
        params.append(limit)
        rows = connection.execute(
            f"""SELECT e.* FROM events e
            LEFT JOIN consumer_event_state s
              ON s.consumer_name = ? AND s.event_id = e.event_id
            WHERE COALESCE(s.status, 'claimed') = 'claimed' {session_clause}
            ORDER BY e.session_id, e.sequence
            LIMIT ?""",
            tuple(params),
        ).fetchall()
        now = _utc_now()
        for row in rows:
            connection.execute(
                """INSERT INTO consumer_event_state (consumer_name, event_id, status, claimed_at)
                VALUES (?, ?, 'claimed', ?)
                ON CONFLICT(consumer_name, event_id) DO NOTHING""",
                (consumer_name, row["event_id"], now),
            )
        connection.commit()
    return [_row_to_event(row) for row in rows]


def ack_event(path: Path, consumer_name: str, event_id: str) -> dict[str, Any]:
    """Acknowledge one event and advance the consumer cursor for its session."""
    if not event_id:
        raise ValueError("event_id_missing")
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _register_consumer(connection, consumer_name)
        row = _select_event(connection, event_id)
        if row is None:
            connection.rollback()
            raise ValueError("event_not_found")
        now = _utc_now()
        connection.execute(
            """INSERT INTO consumer_event_state (consumer_name, event_id, status, claimed_at, acked_at)
            VALUES (?, ?, 'acked', ?, ?)
            ON CONFLICT(consumer_name, event_id) DO UPDATE SET
              status = 'acked', acked_at = excluded.acked_at""",
            (consumer_name, event_id, now, now),
        )
        max_acked = connection.execute(
            """SELECT COALESCE(MAX(e.sequence), 0) AS sequence
            FROM events e
            JOIN consumer_event_state s ON s.event_id = e.event_id
            WHERE s.consumer_name = ? AND s.status = 'acked' AND e.session_id = ?""",
            (consumer_name, row["session_id"]),
        ).fetchone()["sequence"]
        connection.execute(
            """INSERT INTO consumer_offsets (consumer_name, session_id, sequence, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(consumer_name, session_id) DO UPDATE SET
              sequence = MAX(sequence, excluded.sequence), updated_at = excluded.updated_at""",
            (consumer_name, row["session_id"], max_acked, now),
        )
        connection.commit()
    return _row_to_event(row)


def consumer_offset(path: Path, consumer_name: str, session_id: str) -> int:
    """Return a durable consumer cursor for one session, registering if needed."""
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _register_consumer(connection, consumer_name)
        row = connection.execute(
            "SELECT sequence FROM consumer_offsets WHERE consumer_name = ? AND session_id = ?",
            (consumer_name, session_id),
        ).fetchone()
        connection.commit()
    return 0 if row is None else int(row["sequence"])


def session_ids(path: Path) -> list[str]:
    """Return sessions ordered by first event insertion."""
    with connect(path) as connection:
        rows = connection.execute(
            "SELECT session_id, MIN(rowid) AS first_row FROM events GROUP BY session_id ORDER BY first_row"
        ).fetchall()
    return [str(row["session_id"]) for row in rows]
