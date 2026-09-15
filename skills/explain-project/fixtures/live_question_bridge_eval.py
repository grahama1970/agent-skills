#!/usr/bin/env python3
"""Deterministic eval for the live-question bridge (real SSE surface).

Serves the REAL /api/events shape: an SSE stream of
``live_evidence.app_snapshot.v1`` frames carrying transcript events with
speaker/kind/turn_id/sequence — the shape verified against the live-evidence
service source (2026-09-15). Asserts against a real CockpitSession:

  - a closed interviewer turn (final event + later other-turn event)
    appears in bootstrap state with source live_evidence_live and advances
    the revision once;
  - re-delivering the same snapshot does not advance the revision
    (fingerprint dedup);
  - an OPEN turn (final but not yet followed) is never posted;
  - a dead live-evidence service degrades honestly (health flags, state
    untouched) while manual question intake stays functional.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from http.server import (
    BaseHTTPRequestHandler,
    ThreadingHTTPServer,
)

from explain_project_core.catalog import sample_record
from explain_project_core.models import COCKPIT_EVENT_ADAPTER
from explain_project_core.server import CockpitSession
from explain_project_core.voice_bridge import VoiceBridge


def _event(
    event_id: str,
    kind: str,
    text: str,
    sequence: int,
    turn_id: str,
    speaker: str = "interviewer",
) -> dict[str, object]:
    return {
        "schema": "live_evidence.transcript_event.v1",
        "event_id": event_id,
        "created_at": "2026-09-15T18:00:00+00:00",
        "speaker": speaker,
        "kind": kind,
        "text": text,
        "sequence": sequence,
        "turn_id": turn_id,
    }


def _snapshot(transcript: list[dict[str, object]]) -> str:
    return json.dumps(
        {
            "schema": "live_evidence.app_snapshot.v1",
            "session": {
                "session_id": "evalsess12345678",
                "status": "listening",
            },
            "current_thread": "eval",
            "transcript": transcript,
            "cards": [],
            "pending_requirements": [],
            "lanes": [],
            "model_calls": [],
            "trace_events": [],
            "updated_at": "2026-09-15T18:00:00+00:00",
        }
    )


# Turn A = the question (closed: final event + a later candidate event).
TURN_A_FINAL = _event(
    "live-event-aaaa0001",
    "final",
    "Why does publish wait for the report marker?",
    11,
    "turn-aaaaaaaa",
)
TURN_A_STABILIZED = _event(
    "live-event-aaaa0002",
    "stabilized",
    "Why does publish wait for the report marker?",
    12,
    "turn-aaaaaaaa",
)
LATER_OTHER = _event(
    "live-event-bbbb0001",
    "final",
    "Because release is fenced on the marker.",
    13,
    "turn-bbbbbbbb",
    speaker="candidate",
)
# Turn C = open (final but nothing follows it).
TURN_C_FINAL = _event(
    "live-event-cccc0001",
    "final",
    "What breaks first at scale?",
    21,
    "turn-cccccccc",
)

FRAMES = [
    _snapshot([TURN_A_FINAL, LATER_OTHER]),
    _snapshot(
        [
            TURN_A_FINAL,
            TURN_A_STABILIZED,
            LATER_OTHER,
            TURN_C_FINAL,
        ]
    ),
]


def _fake_sse_server() -> tuple[ThreadingHTTPServer, int]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            if self.path != "/api/events":
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header(
                "content-type", "text/event-stream"
            )
            self.send_header("cache-control", "no-cache")
            self.end_headers()
            # Frame 1 arrives immediately; frame 2 after a beat so the
            # stream consumer sees progressive snapshots like the real
            # service, then the stream stays open.
            self.wfile.write(
                f"event: snapshot\ndata: {FRAMES[0]}\n\n".encode()
            )
            self.wfile.flush()
            time.sleep(0.4)
            self.wfile.write(
                f"event: snapshot\ndata: {FRAMES[1]}\n\n".encode()
            )
            self.wfile.flush()
            time.sleep(30)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(
        target=server.serve_forever, daemon=True
    )
    thread.start()
    return server, port


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main() -> None:
    session = CockpitSession(
        [sample_record()],
        "http://127.0.0.1:8601",
    )

    server, port = _fake_sse_server()
    try:
        bridge = VoiceBridge(
            session,
            url=f"http://127.0.0.1:{port}",
        )

        posted = bridge.stream_once(
            max_frames=2, deadline_seconds=6.0
        )
        assert [p["status"] for p in posted] == ["ACCEPTED"], (
            posted
        )

        state = session.bootstrap().state
        assert state.revision == 1, state.revision
        assert state.question is not None
        assert state.question.source == "live_evidence_live", (
            state.question.source
        )
        assert state.question.provenance == "live_fingerprint"
        question_text = state.question.text
        assert "publish wait" in question_text, question_text
        assert bridge.health()["reachable"] is True

        # Same snapshots again: dedup must not advance the revision.
        again = bridge.stream_once(
            max_frames=2, deadline_seconds=6.0
        )
        assert again == [], again
        assert session.bootstrap().state.revision == 1
    finally:
        server.shutdown()
        server.server_close()

    # Dead live-evidence service: honest degradation.
    dead = VoiceBridge(
        session,
        url=f"http://127.0.0.1:{_free_port()}",
    )
    before = session.bootstrap().state.revision
    assert (
        dead.stream_once(max_frames=1, deadline_seconds=3.0) == []
    )
    health = dead.health()
    assert health["reachable"] is False
    assert health["consecutive_failures"] >= 1
    assert session.bootstrap().state.revision == before

    # Manual input stays functional during degradation.
    manual = COCKPIT_EVENT_ADAPTER.validate_python(
        {
            "schema": "explain_project.cockpit_event.v1",
            "event_id": "evt-manual-during-outage",
            "type": "question.manual",
            "expected_revision": before,
            "payload": {
                "text": (
                    "worker crashes before success "
                    "incomplete release"
                )
            },
        }
    )
    state = session.dispatch(
        manual.model_dump(by_alias=True, mode="json")
    )
    assert state.revision == before + 1
    assert state.question is not None
    assert state.question.source == "manual"

    print("EXPLAIN_PROJECT_LIVE_QUESTION_BRIDGE_OK")


if __name__ == "__main__":
    main()
