#!/usr/bin/env python3
"""Deterministic eval for the live-question bridge.

Runs a fake live-evidence HTTP server on a free port, points a VoiceBridge
at it against a real CockpitSession, and asserts:
  - accepted candidates appear in bootstrap state with source
    live_evidence_live and advance the revision once;
  - a re-poll does not advance the revision (fingerprint dedup);
  - a dead live-evidence service degrades honestly (health flags, state
    untouched) while manual question intake stays functional.
"""

from __future__ import annotations

import json
import socket
import threading
from http.server import (
    BaseHTTPRequestHandler,
    ThreadingHTTPServer,
)

from explain_project_core.catalog import sample_record
from explain_project_core.models import COCKPIT_EVENT_ADAPTER
from explain_project_core.server import CockpitSession
from explain_project_core.voice_bridge import VoiceBridge


def candidate_event() -> dict[str, object]:
    return {
        "schema": "live_evidence.question_candidate.v1",
        "question_id": "live-question-12345",
        "normalized_question": (
            "Why does publish wait for the report marker?"
        ),
        "speaker": "interviewer",
        "source_event_ids": [
            "live-event-12345678"
        ],
        "source_spans": [
            {
                "event_id": "live-event-12345678",
                "sequence": 11,
                "start_offset": 0,
                "end_offset": 40,
            }
        ],
        "start_sequence": 11,
        "end_sequence": 11,
        "trigger_reason": "vad_punct_650ms",
        "fingerprint": "live-fingerprint-12345",
    }


def _fake_server() -> tuple[ThreadingHTTPServer, int]:
    events = [candidate_event()]

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            if self.path == "/api/events":
                body = json.dumps({"events": events}).encode()
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(404)
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
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

    server, port = _fake_server()
    try:
        bridge = VoiceBridge(
            session,
            url=f"http://127.0.0.1:{port}",
        )

        posted = bridge.poll_once()
        assert [p["status"] for p in posted] == ["ACCEPTED"], posted

        state = session.bootstrap().state
        assert state.revision == 1, state.revision
        assert state.question is not None
        assert state.question.source == "live_evidence_live", (
            state.question.source
        )
        assert state.question.provenance == "live_fingerprint"
        assert bridge.health()["reachable"] is True

        # Re-poll: same candidate must not advance the revision.
        again = bridge.poll_once()
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
    assert dead.poll_once() == []
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
