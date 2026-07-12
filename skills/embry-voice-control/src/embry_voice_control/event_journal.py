"""Durable SQLite WAL journal for ordered Embry listener and turn events."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import hashlib
import sqlite3
from pathlib import Path
from typing import Any

EVENT_SCHEMA = "embry.voice_event.v2"
COMPATIBLE_EVENT_SCHEMAS = {"embry.voice_event.v1", EVENT_SCHEMA}
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


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _lease_until(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def connect(path: Path) -> sqlite3.Connection:
    """Open and initialize the event journal."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute(
        """CREATE TABLE IF NOT EXISTS events (
        event_id TEXT PRIMARY KEY,
        event_schema TEXT NOT NULL DEFAULT 'embry.voice_event.v1',
        session_id TEXT NOT NULL,
        turn_id TEXT NOT NULL,
        sequence INTEGER NOT NULL,
        event_type TEXT NOT NULL,
        created_at TEXT NOT NULL,
        causation_id TEXT,
        correlation_id TEXT,
        producer TEXT,
        mocked INTEGER,
        live INTEGER,
        artifact_hashes_json TEXT,
        receipt_hash TEXT,
        payload_json TEXT NOT NULL,
        UNIQUE(session_id, sequence)
        )"""
    )
    _migrate_events(connection)
    connection.execute(
        """CREATE TABLE IF NOT EXISTS consumers (
        consumer_name TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
        )"""
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS consumer_events (
        consumer_name TEXT NOT NULL,
        event_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        sequence INTEGER NOT NULL,
        claimed_until TEXT,
        acked_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (consumer_name, event_id),
        FOREIGN KEY (consumer_name) REFERENCES consumers(consumer_name),
        FOREIGN KEY (event_id) REFERENCES events(event_id)
        )"""
    )
    connection.execute(
        """CREATE INDEX IF NOT EXISTS idx_consumer_events_cursor
        ON consumer_events(consumer_name, session_id, acked_at, sequence)"""
    )
    connection.commit()
    return connection


def _migrate_events(connection: sqlite3.Connection) -> None:
    columns = {row[1] for row in connection.execute("PRAGMA table_info(events)").fetchall()}
    for column, decl in {
        "event_schema": "TEXT NOT NULL DEFAULT 'embry.voice_event.v1'",
        "causation_id": "TEXT",
        "correlation_id": "TEXT",
        "producer": "TEXT",
        "mocked": "INTEGER",
        "live": "INTEGER",
        "artifact_hashes_json": "TEXT",
        "receipt_hash": "TEXT",
    }.items():
        if column not in columns:
            connection.execute(f"ALTER TABLE events ADD COLUMN {column} {decl}")


def validate_event(event: dict[str, Any]) -> None:
    """Reject incomplete or noncanonical producer events."""
    if event.get("schema") not in COMPATIBLE_EVENT_SCHEMAS:
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
    artifact_hashes = event.get("artifact_hashes")
    if not isinstance(artifact_hashes, (dict, list)):
        raise ValueError("event_artifact_hashes_invalid")
    values = artifact_hashes.values() if isinstance(artifact_hashes, dict) else artifact_hashes
    if not all(isinstance(value, str) and value for value in values):
        raise ValueError("event_artifact_hashes_invalid")
    if not isinstance(event.get("payload"), dict):
        raise ValueError("event_payload_invalid")


def _row_to_event(row: sqlite3.Row) -> dict[str, Any]:
    artifact_hashes = row["artifact_hashes_json"]
    return {
        "schema": row["event_schema"],
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
        "artifact_hashes": json.loads(artifact_hashes) if artifact_hashes else {},
        "receipt_hash": row["receipt_hash"],
        "payload": json.loads(row["payload_json"]),
    }


def _producer_projection(event: dict[str, Any], stored: dict[str, Any]) -> dict[str, Any]:
    return {key: stored[key] for key in event if key != "sequence"}


def append_event(path: Path, event: dict[str, Any]) -> dict[str, Any]:
    """Append one event and return the canonical stored event."""
    validate_event(event)
    payload_json = _canonical_json(event["payload"])
    artifact_hashes_json = _canonical_json(event["artifact_hashes"])
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        existing = connection.execute("SELECT * FROM events WHERE event_id = ?", (event["event_id"],)).fetchone()
        if existing is not None:
            stored = _row_to_event(existing)
            if _producer_projection(event, stored) == event:
                connection.commit()
                return stored
            connection.rollback()
            raise ValueError("event_id_conflict")
        sequence = connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 FROM events WHERE session_id = ?",
            (event["session_id"],),
        ).fetchone()[0]
        connection.execute(
            """INSERT INTO events (
            event_id, event_schema, session_id, turn_id, sequence, event_type, created_at,
            causation_id, correlation_id, producer, mocked, live,
            artifact_hashes_json, receipt_hash, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event["event_id"], event["schema"], event["session_id"], event["turn_id"], sequence,
                event["type"], event["created_at"], event["causation_id"],
                event["correlation_id"], event["producer"], int(event["mocked"]),
                int(event["live"]), artifact_hashes_json, event["receipt_hash"], payload_json,
            ),
        )
        row = connection.execute("SELECT * FROM events WHERE event_id = ?", (event["event_id"],)).fetchone()
        connection.commit()
    return _row_to_event(row)


def list_events(path: Path, session_id: str, after_sequence: int = 0) -> list[dict[str, Any]]:
    """Return ordered events for one session."""
    with connect(path) as connection:
        rows = connection.execute(
            "SELECT * FROM events WHERE session_id = ? AND sequence > ? ORDER BY sequence",
            (session_id, after_sequence),
        ).fetchall()
    return [_row_to_event(row) for row in rows]


def session_snapshot(path: Path, session_id: str) -> dict[str, Any]:
    """Read one session from a single SQLite snapshot transaction."""
    with connect(path) as connection:
        connection.execute("BEGIN")
        rows = connection.execute(
            "SELECT * FROM events WHERE session_id = ? ORDER BY sequence",
            (session_id,),
        ).fetchall()
        events = [_row_to_event(row) for row in rows]
        connection.commit()
    canonical = _canonical_json(events).encode()
    return {
        "session_id": session_id,
        "through_sequence": events[-1]["sequence"] if events else 0,
        "event_count": len(events),
        "sha256": "sha256:" + hashlib.sha256(canonical).hexdigest(),
        "events": events,
    }


def _register_consumer(connection: sqlite3.Connection, consumer_name: str) -> None:
    if not isinstance(consumer_name, str) or not consumer_name:
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
    session_id: str | None = None,
    limit: int = 100,
    lease_seconds: int = 60,
) -> list[dict[str, Any]]:
    """Durably claim unacked events for one consumer until the lease expires."""
    if limit < 1:
        return []
    if lease_seconds < 1:
        raise ValueError("lease_seconds_invalid")
    now = _utc_now()
    until = _lease_until(lease_seconds)
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _register_consumer(connection, consumer_name)
        session_filter = "AND e.session_id = ?" if session_id is not None else ""
        params: tuple[Any, ...] = (consumer_name, now)
        if session_id is not None:
            params += (session_id,)
        params += (limit,)
        rows = connection.execute(
            f"""SELECT e.* FROM events e
            LEFT JOIN consumer_events ce ON ce.consumer_name = ? AND ce.event_id = e.event_id
            WHERE (ce.event_id IS NULL OR ce.acked_at IS NULL)
              AND (ce.claimed_until IS NULL OR ce.claimed_until <= ?)
              {session_filter}
            ORDER BY e.session_id, e.sequence
            LIMIT ?""",
            params,
        ).fetchall()
        stamp = _utc_now()
        for row in rows:
            connection.execute(
                """INSERT INTO consumer_events (
                consumer_name, event_id, session_id, sequence, claimed_until, acked_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, NULL, ?, ?)
                ON CONFLICT(consumer_name, event_id) DO UPDATE SET
                  claimed_until = excluded.claimed_until,
                  updated_at = excluded.updated_at""",
                (consumer_name, row["event_id"], row["session_id"], row["sequence"], until, stamp, stamp),
            )
        connection.commit()
    return [_row_to_event(row) for row in rows]


def claim_event(
    path: Path,
    consumer_name: str,
    event_id: str,
    *,
    expected_session_id: str,
    expected_turn_id: str,
    expected_sequence: int,
    expected_type: str,
    lease_seconds: int,
) -> dict[str, Any]:
    """Claim one exact event after atomically validating its lineage."""
    if lease_seconds < 1:
        raise ValueError("lease_seconds_invalid")
    now = _utc_now()
    until = _lease_until(lease_seconds)
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _register_consumer(connection, consumer_name)
        row = connection.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()
        if row is None:
            connection.rollback()
            raise ValueError("event_id_unknown")
        expected = {
            "session_id": expected_session_id,
            "turn_id": expected_turn_id,
            "sequence": expected_sequence,
            "event_type": expected_type,
        }
        for column, value in expected.items():
            if row[column] != value:
                connection.rollback()
                field = "type" if column == "event_type" else column.removeprefix("event_")
                raise ValueError(f"event_{field}_mismatch")
        state = connection.execute(
            "SELECT claimed_until, acked_at FROM consumer_events WHERE consumer_name = ? AND event_id = ?",
            (consumer_name, event_id),
        ).fetchone()
        if state is not None and state["acked_at"] is not None:
            connection.rollback()
            raise ValueError("event_already_acked")
        if state is not None and state["claimed_until"] is not None and state["claimed_until"] > now:
            connection.rollback()
            raise ValueError("event_claim_active")
        stamp = _utc_now()
        connection.execute(
            """INSERT INTO consumer_events (
            consumer_name, event_id, session_id, sequence, claimed_until, acked_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, NULL, ?, ?)
            ON CONFLICT(consumer_name, event_id) DO UPDATE SET
              claimed_until = excluded.claimed_until,
              updated_at = excluded.updated_at""",
            (consumer_name, event_id, row["session_id"], row["sequence"], until, stamp, stamp),
        )
        connection.commit()
    return {
        "schema": "embry.listener_event_claim_one.v1",
        "claimed": True,
        "already_acked": False,
        "event": _row_to_event(row),
        "lease_expires_at": until,
    }


def ack_event(path: Path, consumer_name: str, event_id: str) -> bool:
    """Ack an event for a consumer. Repeated acks are idempotent."""
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _register_consumer(connection, consumer_name)
        event = connection.execute("SELECT session_id, sequence FROM events WHERE event_id = ?", (event_id,)).fetchone()
        if event is None:
            connection.rollback()
            raise ValueError("event_id_unknown")
        now = _utc_now()
        connection.execute(
            """INSERT INTO consumer_events (
            consumer_name, event_id, session_id, sequence, claimed_until, acked_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, NULL, ?, ?, ?)
            ON CONFLICT(consumer_name, event_id) DO UPDATE SET
              acked_at = COALESCE(consumer_events.acked_at, excluded.acked_at),
              updated_at = excluded.updated_at""",
            (consumer_name, event_id, event["session_id"], event["sequence"], now, now, now),
        )
        connection.commit()
    return True


def consumer_offset(path: Path, consumer_name: str, session_id: str | None = None) -> int:
    """Return the durable acknowledged cursor for a consumer."""
    with connect(path) as connection:
        _register_consumer(connection, consumer_name)
        if session_id is None:
            row = connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) AS offset FROM consumer_events WHERE consumer_name = ? AND acked_at IS NOT NULL",
                (consumer_name,),
            ).fetchone()
        else:
            row = connection.execute(
                """SELECT COALESCE(MAX(sequence), 0) AS offset FROM consumer_events
                WHERE consumer_name = ? AND session_id = ? AND acked_at IS NOT NULL""",
                (consumer_name, session_id),
            ).fetchone()
    return int(row["offset"])


def session_ids(path: Path) -> list[str]:
    """Return sessions ordered by first event insertion."""
    with connect(path) as connection:
        rows = connection.execute(
            "SELECT session_id, MIN(rowid) AS first_row FROM events GROUP BY session_id ORDER BY first_row"
        ).fetchall()
    return [str(row["session_id"]) for row in rows]
