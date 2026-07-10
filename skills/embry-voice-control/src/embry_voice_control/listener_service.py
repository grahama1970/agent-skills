"""Local FastAPI control surface for the durable Embry voice event journal."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from embry_voice_control.event_journal import (
    ack_event,
    append_event,
    claim_events,
    consumer_offset,
    list_events,
    session_ids,
)


DEFAULT_DB_PATH = Path(os.environ.get(
    "EMBRY_VOICE_JOURNAL_DB",
    "/mnt/storage12tb/skills/embry-voice-control/state/voice-events.sqlite3",
))


class VoiceEvent(BaseModel):
    """Canonical producer event accepted by the local listener service."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    schema_: str = Field(default="embry.voice_event.v1", alias="schema")
    event_id: str
    session_id: str
    turn_id: str
    type: str
    created_at: str
    causation_id: str
    correlation_id: str
    producer: str
    mocked: bool
    live: bool
    artifact_hashes: dict[str, str]
    receipt_hash: str
    payload: dict[str, Any]


class ClaimRequest(BaseModel):
    """Durable consumer claim request."""

    consumer_name: str
    session_id: str | None = None
    limit: int = Field(default=100, ge=1)
    lease_seconds: int = Field(default=60, ge=1)


class AckRequest(BaseModel):
    """Durable consumer ack request."""

    consumer_name: str
    event_id: str


def utc_now() -> str:
    """Return an ISO UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def _receipt_hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def create_app(db_path: Path = DEFAULT_DB_PATH) -> FastAPI:
    """Create the local listener event service."""
    app = FastAPI(title="Embry Voice Event Journal", version="1.0.0")
    app.state.db_path = db_path

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "schema": "embry.listener_service_health.v1", "db_path": str(db_path)}

    @app.post("/v1/listener/events")
    def ingest(event: VoiceEvent) -> dict[str, Any]:
        try:
            stored = append_event(db_path, event.model_dump(by_alias=True))
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {
            "schema": "embry.listener_event_ingest_receipt.v1",
            "accepted": True,
            "event": stored,
            "event_id": stored["event_id"],
            "session_id": stored["session_id"],
            "turn_id": stored["turn_id"],
            "sequence": stored["sequence"],
        }

    @app.post("/v1/listener/events/claim")
    def claim(request: ClaimRequest) -> dict[str, Any]:
        try:
            rows = claim_events(
                db_path,
                request.consumer_name,
                request.session_id,
                request.limit,
                request.lease_seconds,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"schema": "embry.listener_event_claim.v1", "events": rows}

    @app.post("/v1/listener/events/ack")
    def ack(request: AckRequest) -> dict[str, Any]:
        try:
            ack_event(db_path, request.consumer_name, request.event_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"schema": "embry.listener_event_ack.v1", "acked": True, "event_id": request.event_id}

    @app.get("/v1/listener/consumers/{consumer_name}/offset")
    def offset(consumer_name: str, session_id: str | None = None) -> dict[str, Any]:
        return {
            "schema": "embry.listener_consumer_offset.v1",
            "consumer_name": consumer_name,
            "session_id": session_id,
            "offset": consumer_offset(db_path, consumer_name, session_id),
        }

    @app.get("/v1/sessions")
    def sessions() -> dict[str, Any]:
        return {"schema": "embry.listener_sessions.v1", "sessions": session_ids(db_path)}

    @app.get("/v1/sessions/{session_id}/events")
    def events(session_id: str, after_sequence: int = Query(default=0, ge=0)) -> dict[str, Any]:
        rows = list_events(db_path, session_id, after_sequence)
        return {"schema": "embry.voice_event_journal.v1", "session_id": session_id, "events": rows}

    @app.get("/v1/sessions/{session_id}/journal")
    def journal(session_id: str) -> dict[str, Any]:
        rows = list_events(db_path, session_id)
        digest = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
        return {
            "schema": "embry.voice_event_journal.v1",
            "session_id": session_id,
            "event_count": len(rows),
            "turn_ids": list(dict.fromkeys(row["turn_id"] for row in rows)),
            "sha256": digest,
            "events": rows,
        }

    @app.post("/v1/turns/{turn_id}/cancel")
    def cancel(turn_id: str, session_id: str) -> dict[str, Any]:
        payload = {"reason": "requested", "cancelled_at": utc_now()}
        seed = {"session_id": session_id, "turn_id": turn_id, "type": "turn.cancelled", "payload": payload}
        event = {
            "schema": "embry.voice_event.v1",
            "event_id": "turn.cancelled." + _receipt_hash(seed)[:16],
            "session_id": session_id,
            "turn_id": turn_id,
            "type": "turn.cancelled",
            "created_at": payload["cancelled_at"],
            "causation_id": turn_id,
            "correlation_id": session_id,
            "producer": "embry.listener_service",
            "mocked": False,
            "live": True,
            "artifact_hashes": {},
            "receipt_hash": _receipt_hash(seed),
            "payload": payload,
        }
        try:
            stored = append_event(db_path, event)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"schema": "embry.turn_cancel_receipt.v1", "event": stored}

    return app


app = create_app()
