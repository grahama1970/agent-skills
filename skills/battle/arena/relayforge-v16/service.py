#!/usr/bin/env python3
"""Minimal fail-closed RelayForge V16 service skeleton.

All services share this process image and select their bounded role with the
``RELAYFORGE_ROLE`` environment variable.  The skeleton intentionally exposes
only health and contract-discovery behavior.  Security predicates, sinks, and
business workflows remain unavailable until the corresponding Judge contracts
are implemented.
"""

from __future__ import annotations

import hashlib
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

TARGET_ID = "battle-v16-relayforge-a"
IMPLEMENTATION_STATUS = "SKELETON_BLOCKED"


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


def response_for(
    *, role: str, method: str, path: str, body: bytes = b""
) -> tuple[int, dict[str, Any]]:
    """Return one deterministic response for the local service skeleton."""

    if path == "/healthz" and method == "GET":
        return HTTPStatus.OK, {
            "schema": "battle.v16.relayforge.service_health.v1",
            "status": "READY_FOR_SKELETON",
            "target_id": TARGET_ID,
            "role": role,
            "implementation_status": IMPLEMENTATION_STATUS,
        }

    if role == "edge-gateway" and method == "GET" and path == "/api/v1/status":
        return HTTPStatus.OK, {
            "schema": "battle.v16.relayforge.public_status.v1",
            "status": "SKELETON",
            "target_id": TARGET_ID,
            "public_entry_point": "POST /api/v1/jobs/import",
            "qualification_eligible": False,
        }

    if role == "edge-gateway" and method == "POST" and path in {
        "/api/v1/jobs/import",
        "/api/v1/legacy/convert",
    }:
        request_sha256 = hashlib.sha256(body).hexdigest()
        return HTTPStatus.SERVICE_UNAVAILABLE, {
            "schema": "battle.v16.relayforge.blocked_operation.v1",
            "status": "BLOCKED",
            "target_id": TARGET_ID,
            "operation": path,
            "request_sha256": request_sha256,
            "reason": "relayforge_business_and_security_predicates_unimplemented",
            "qualification_eligible": False,
        }

    if role == "judge-probe" and method == "POST" and path == "/judge/evaluate":
        return HTTPStatus.SERVICE_UNAVAILABLE, {
            "schema": "battle.v16.judge_outcome.v1",
            "status": "BLOCKED",
            "target_id": TARGET_ID,
            "reason": "judge_predicates_unimplemented",
            "pass_emitted": False,
        }

    return HTTPStatus.NOT_FOUND, {
        "schema": "battle.v16.relayforge.error.v1",
        "status": "NOT_FOUND",
        "target_id": TARGET_ID,
        "role": role,
        "path": path,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "RelayForgeSkeleton/0.1"

    def _handle(self) -> None:
        content_length = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(content_length) if content_length else b""
        status, payload = response_for(
            role=os.environ.get("RELAYFORGE_ROLE", "unconfigured"),
            method=self.command,
            path=self.path.split("?", 1)[0],
            body=body,
        )
        encoded = _json_bytes(payload)
        self.send_response(int(status))
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        self._handle()

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        self._handle()

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    port = int(os.environ.get("RELAYFORGE_PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
