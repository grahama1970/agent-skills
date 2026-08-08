"""http_scillm - helpers.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


@dataclass(frozen=True)
class ScillmResponse:
    status: int = 200
    lines: list[str] = field(default_factory=list)
    body: str = ""
    content_type: str = "text/event-stream"


@dataclass(frozen=True)
class CapturedRequest:
    path: str
    headers: dict[str, str]
    raw_body: str
    body: dict[str, Any] | None


class FakeScillmHTTPServer:
    def __init__(self, responses: list[ScillmResponse]) -> None:
        if not responses:
            raise ValueError("at least one fake scillm response is required")
        self._responses = responses
        self.requests: list[CapturedRequest] = []
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._server.fake = self  # type: ignore[attr-defined]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    def response_for_next_request(self) -> ScillmResponse:
        index = max(0, len(self.requests) - 1)
        if index < len(self._responses):
            return self._responses[index]
        return self._responses[-1]

    def __enter__(self) -> FakeScillmHTTPServer:
        self._thread.start()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_POST(self) -> None:
        fake: FakeScillmHTTPServer = self.server.fake  # type: ignore[attr-defined]
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode(errors="replace")
        try:
            body: dict[str, Any] | None = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            body = None
        fake.requests.append(
            CapturedRequest(
                path=self.path,
                headers={key.lower(): value for key, value in self.headers.items()},
                raw_body=raw,
                body=body,
            )
        )
        response = fake.response_for_next_request()
        payload = _response_bytes(response)
        self.send_response(response.status)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
        self.wfile.flush()


def event(data: dict[str, Any]) -> str:
    return "data: " + json.dumps(data)


def done() -> str:
    return "data: [DONE]"


def content_delta(text: str, *, finish_reason: str | None = None) -> str:
    choice: dict[str, Any] = {"delta": {"role": "assistant", "content": text}}
    if finish_reason is not None:
        choice["finish_reason"] = finish_reason
    return event({"choices": [choice]})


def empty_delta(*, finish_reason: str | None = None) -> str:
    choice: dict[str, Any] = {"delta": {}}
    if finish_reason is not None:
        choice["finish_reason"] = finish_reason
    return event({"choices": [choice]})


def tool_delta(
    *,
    index: int = 0,
    call_id: str | None = None,
    name: str | None = None,
    arguments: str | None = None,
    finish_reason: str | None = None,
) -> str:
    function: dict[str, str] = {}
    if name is not None:
        function["name"] = name
    if arguments is not None:
        function["arguments"] = arguments
    tool_call: dict[str, Any] = {
        "index": index,
        "type": "function",
        "function": function,
    }
    if call_id is not None:
        tool_call["id"] = call_id
    choice: dict[str, Any] = {"delta": {"tool_calls": [tool_call]}}
    if finish_reason is not None:
        choice["finish_reason"] = finish_reason
    return event({"choices": [choice]})


def assistant_stop(text: str = "done") -> ScillmResponse:
    return ScillmResponse(lines=[content_delta(text, finish_reason="stop"), done()])


def _response_bytes(response: ScillmResponse) -> bytes:
    if response.status >= 400:
        return (response.body or '{"error":"bad request"}').encode()
    text = "\n".join(response.lines)
    if text:
        text += "\n"
    return text.encode()
