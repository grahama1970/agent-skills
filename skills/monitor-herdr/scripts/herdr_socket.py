#!/usr/bin/env python3
"""Herdr Unix-socket client and the small readers layered on it.

Inputs: the Herdr socket at ~/.config/herdr/herdr.sock.
Outputs: parsed JSON-RPC results for pane.read, agent.explain, and friends.
Failure modes: a socket error is returned as an error body, never raised, so the
monitor stays fail-closed rather than crashing mid-tick.

Split out of monitor_herdr.py to keep every module under the 800-line repo limit.
"""

from __future__ import annotations

import json
import re
import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loguru import logger

from monitor_common import redact_api_record

DEFAULT_SOCKET_PATH = Path.home() / ".config" / "herdr" / "herdr.sock"


@dataclass(frozen=True)
class HerdrResponse:
    request: dict[str, Any]
    response: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {"request": self.request, "response": self.response}
class HerdrClient:
    def __init__(self, socket_path: Path, timeout_s: float = 10.0) -> None:
        self.socket_path = socket_path
        self.timeout_s = timeout_s
        self.counter = 0
        self.trace: list[dict[str, Any]] = []

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.counter += 1
        request = {
            "id": f"monitor_herdr_{self.counter}",
            "method": method,
            "params": params or {},
        }
        started = datetime.now(UTC)
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.timeout_s)
                sock.connect(str(self.socket_path))
                sock.sendall((json.dumps(request) + "\n").encode("utf-8"))
                data = b""
                while b"\n" not in data:
                    chunk = sock.recv(262144)
                    if not chunk:
                        break
                    data += chunk
        except OSError as exc:
            logger.error("Herdr socket call failed for {}: {}", method, exc)
            response = {"error": {"code": "socket_error", "message": str(exc)}}
        else:
            line = data.split(b"\n", 1)[0]
            try:
                response = json.loads(line.decode("utf-8"))
            except json.JSONDecodeError as exc:
                logger.error("Herdr socket returned invalid JSON for {}: {}", method, exc)
                response = {"error": {"code": "invalid_json", "message": str(exc), "raw": line.decode("utf-8", "replace")[:2000]}}
            if response.get("id") != request["id"]:
                response = {
                    "error": {
                        "code": "response_id_mismatch",
                        "message": f"expected {request['id']!r}, got {response.get('id')!r}",
                    }
                }
            elif "result" not in response and "error" not in response:
                response = {"error": {"code": "invalid_response_shape", "message": "missing result/error"}}
        record = HerdrResponse(request=request, response=response).as_dict()
        record["duration_seconds"] = (datetime.now(UTC) - started).total_seconds()
        self.trace.append(redact_api_record(record))
        if "error" in response:
            raise RuntimeError(f"{method} failed: {response['error']}")
        return response["result"]
def read_pane_text(client: HerdrClient, pane_id: str) -> str:
    try:
        result = client.call("pane.read", {"pane_id": pane_id, "source": "recent_unwrapped", "lines": 140, "format": "text"})
    except RuntimeError:
        logger.error("Herdr pane.read failed for {}", pane_id)
        return ""
    text = result.get("read", {}).get("text")
    return text if isinstance(text, str) else ""
def explain_agent(client: HerdrClient, pane_id: str) -> dict[str, Any]:
    try:
        result = client.call("agent.explain", {"target": pane_id})
    except RuntimeError as exc:
        logger.error("Herdr agent.explain failed for {}: {}", pane_id, exc)
        return {"error": str(exc)}
    explain = result.get("explain")
    return explain if isinstance(explain, dict) else {}
def find_patterns(text: str, patterns: list[str]) -> list[str]:
    lowered = text.lower()
    matches: list[str] = []
    for pattern in patterns:
        if re.search(pattern, lowered, flags=re.IGNORECASE | re.MULTILINE):
            matches.append(pattern)
    return matches
