"""Executable Battle UX8 live transport adapter.

The adapter serves already-normalized Battle UX fixtures through the UX8
snapshot/SSE contract. It does not inspect Tau, provider, Docker, or Judge raw
runtime directories; the source of truth remains the normalized fixture.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .battle_event_adapter import _live_event_envelopes, _snapshot_envelope
from .live_transport_contract import GENETIC_EVENT_TYPES


SNAPSHOT_ENDPOINT_TEMPLATE = "/battle/live/{battle_id}/snapshot"
EVENTS_ENDPOINT_TEMPLATE = "/battle/live/{battle_id}/events"
FORBIDDEN_TRANSPORT_MARKERS = (
    "tau-dag-run/",
    "command-loop/",
    "command-artifacts/",
    "provider-workspace",
    "pr3c-provider-workspaces",
    "outputs/provider-worker-result.json",
    "inputs/tau-scillm-worker-work-order.json",
    "/tmp/",
    "/home/",
    "/mnt/",
    "/workspace",
    "C:\\",
    "D:\\",
)


@dataclass(frozen=True)
class LiveTransportSource:
    battle_id: str
    run_id: str
    fixture_path: str
    snapshot: dict[str, Any]
    events: list[dict[str, Any]]

    @property
    def snapshot_endpoint(self) -> str:
        return SNAPSHOT_ENDPOINT_TEMPLATE.format(battle_id=self.battle_id)

    @property
    def events_endpoint(self) -> str:
        return EVENTS_ENDPOINT_TEMPLATE.format(battle_id=self.battle_id)


def build_live_transport_source(*, fixture_path: Path, battle_id: str) -> LiveTransportSource:
    """Build in-memory snapshot/events from a normalized Battle UX fixture."""

    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    if fixture.get("schema") != "battle.normalized_ux_fixture.v1":
        raise ValueError("fixture must use schema battle.normalized_ux_fixture.v1")
    if fixture.get("battle_id") != battle_id:
        raise ValueError(f"fixture battle_id {fixture.get('battle_id')!r} does not match {battle_id!r}")
    if fixture.get("mocked") is not False:
        raise ValueError("live transport source fixture must have mocked=false")

    events = _live_event_envelopes(fixture)
    _validate_ordered_events(events=events, battle_id=battle_id)
    snapshot = _snapshot_envelope(fixture=fixture, last_seq=len(events))
    run_id = str(snapshot.get("run_id") or events[0].get("run_id") if events else "unknown")
    source = LiveTransportSource(
        battle_id=battle_id,
        run_id=run_id,
        fixture_path=_safe_fixture_ref(fixture_path),
        snapshot=snapshot,
        events=events,
    )
    _assert_no_raw_path_leak(source.snapshot, source.events)
    return source


def create_live_transport_server(*, source: LiveTransportSource, host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    """Create a ThreadingHTTPServer for the Battle live transport source."""

    class Handler(BaseHTTPRequestHandler):
        server_version = "BattleLiveTransport/1.0"

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            path = urlsplit(self.path).path
            if path == "/healthz":
                self._write_json(
                    {
                        "schema": "battle.live_transport_health.v1",
                        "status": "PASS",
                        "battle_id": source.battle_id,
                        "run_id": source.run_id,
                        "event_count": len(source.events),
                        "last_seq": source.snapshot.get("last_seq"),
                    }
                )
                return
            if path == source.snapshot_endpoint:
                self._write_json(source.snapshot)
                return
            if path == source.events_endpoint:
                self._write_sse()
                return
            self._write_json(
                {
                    "schema": "battle.live_transport_error.v1",
                    "status": "NOT_FOUND",
                    "battle_id": source.battle_id,
                    "path": path,
                },
                status=404,
            )

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib handler API
            return

        def _write_json(self, payload: dict[str, Any], *, status: int = 200) -> None:
            body = json.dumps(payload, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _write_sse(self) -> None:
            try:
                start_after = _parse_last_event_id(self.headers.get("Last-Event-ID"), last_seq=len(source.events))
            except ValueError as exc:
                self._write_json(
                    {
                        "schema": "battle.live_transport_error.v1",
                        "status": "BAD_LAST_EVENT_ID",
                        "battle_id": source.battle_id,
                        "reason": str(exc),
                    },
                    status=400,
                )
                return

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            for event in source.events:
                if event["seq"] <= start_after:
                    continue
                frame = _sse_frame(event)
                self.wfile.write(frame)
                self.wfile.flush()

    return ThreadingHTTPServer((host, port), Handler)


def serve_live_transport(*, fixture_path: Path, battle_id: str, host: str, port: int) -> None:
    """Serve UX8 live transport until interrupted."""

    source = build_live_transport_source(fixture_path=fixture_path, battle_id=battle_id)
    server = create_live_transport_server(source=source, host=host, port=port)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def prove_live_transport_server(
    *,
    fixture_path: Path,
    battle_id: str,
    out_dir: Path,
    host: str = "127.0.0.1",
) -> dict[str, Any]:
    """Start the adapter locally and prove snapshot, SSE, and resume behavior."""

    source = build_live_transport_source(fixture_path=fixture_path, battle_id=battle_id)
    server = create_live_transport_server(source=source, host=host, port=0)
    port = int(server.server_address[1])
    thread = threading.Thread(target=server.serve_forever, name="battle-live-transport-proof", daemon=True)
    thread.start()
    base_url = f"http://{host}:{port}"
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        health = _http_json(f"{base_url}/healthz")
        snapshot = _http_json(f"{base_url}{source.snapshot_endpoint}")
        stream_text = _http_text(f"{base_url}{source.events_endpoint}", accept="text/event-stream")
        resumed_text = _http_text(
            f"{base_url}{source.events_endpoint}",
            accept="text/event-stream",
            headers={"Last-Event-ID": "2"},
        )
        bad_resume_status = _http_status(
            f"{base_url}{source.events_endpoint}",
            headers={"Last-Event-ID": str(len(source.events) + 10)},
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    stream_events = _parse_sse_events(stream_text)
    resumed_events = _parse_sse_events(resumed_text)
    _assert_no_raw_path_leak(snapshot, stream_events)
    _assert_no_raw_path_leak({"resumed": resumed_events}, [])
    errors: list[str] = []
    if health.get("status") != "PASS":
        errors.append("health endpoint did not return PASS")
    if snapshot.get("schema") != "battle.snapshot.v1":
        errors.append("snapshot endpoint did not return battle.snapshot.v1")
    if snapshot.get("battle_id") != battle_id:
        errors.append("snapshot battle_id mismatch")
    if snapshot.get("last_seq") != len(source.events):
        errors.append("snapshot last_seq must match event count")
    if len(stream_events) != len(source.events):
        errors.append("SSE stream did not return every event")
    if [event.get("seq") for event in stream_events] != list(range(1, len(source.events) + 1)):
        errors.append("SSE stream seq values are not contiguous")
    if resumed_events and min(int(event.get("seq", 0)) for event in resumed_events) <= 2:
        errors.append("Last-Event-ID resume returned already-acknowledged events")
    if len(resumed_events) != max(len(source.events) - 2, 0):
        errors.append("Last-Event-ID resume returned unexpected event count")
    if bad_resume_status != 400:
        errors.append("future Last-Event-ID must fail closed with HTTP 400")
    if errors:
        raise ValueError("\n".join(errors))

    receipt = {
        "schema": "battle.live_transport_server_proof.v1",
        "status": "PASS",
        "mocked": False,
        "live": "local_http_sse_adapter",
        "battle_id": battle_id,
        "run_id": source.run_id,
        "fixture_ref": source.fixture_path,
        "base_url": base_url,
        "snapshot_endpoint": source.snapshot_endpoint,
        "sse_endpoint": source.events_endpoint,
        "snapshot_schema": snapshot.get("schema"),
        "event_schema": "battle.live_event.v1",
        "event_count": len(stream_events),
        "last_seq": snapshot.get("last_seq"),
        "resume_from_last_event_id": 2,
        "resumed_event_count": len(resumed_events),
        "future_last_event_id_status": bad_resume_status,
        "genetic_event_types_when_live": list(GENETIC_EVENT_TYPES),
        "raw_path_boundary": {
            "raw_paths_leaked": False,
            "forbidden_markers": list(FORBIDDEN_TRANSPORT_MARKERS),
        },
        "claim_boundary": {
            "proves": [
                "The Battle live transport adapter served battle.snapshot.v1 over HTTP.",
                "The Battle live transport adapter served ordered battle.live_event.v1 records as SSE.",
                "The Battle live transport adapter honored Last-Event-ID resume.",
                "The Battle live transport adapter failed closed on an impossible future Last-Event-ID.",
            ],
            "does_not_prove": [
                "A production deployment is running.",
                "A WebSocket endpoint exists.",
                "Live Tau/provider/Docker/Judge runtime directories were read.",
                "Any exploit succeeded.",
                "Any Blue detection, kill, or block occurred.",
                "Judge verified exploit success.",
                "Memory promotion occurred.",
            ],
        },
    }
    _write_json(out_dir / "live-transport-server-proof.json", receipt)
    _write_json(out_dir / "snapshot-response.json", snapshot)
    (out_dir / "events.sse").write_text(stream_text.rstrip() + "\n", encoding="utf-8")
    (out_dir / "resume-after-2.sse").write_text(resumed_text.rstrip() + "\n", encoding="utf-8")
    return receipt


def _validate_ordered_events(*, events: list[dict[str, Any]], battle_id: str) -> None:
    if not events:
        raise ValueError("live transport source must contain at least one event")
    for index, event in enumerate(events, start=1):
        if event.get("schema") != "battle.live_event.v1":
            raise ValueError(f"event {index} must use schema battle.live_event.v1")
        if event.get("battle_id") != battle_id:
            raise ValueError(f"event {index} battle_id mismatch")
        if event.get("seq") != index:
            raise ValueError(f"event seq gap: expected {index}, got {event.get('seq')}")
        payload = event.get("payload")
        lifecycle = event.get("lifecycle")
        if not isinstance(payload, dict) or not isinstance(lifecycle, dict):
            raise ValueError(f"event {index} payload/lifecycle must be objects")
        is_segment = event.get("event_type") == "battle.segment_declared" and payload.get("schema") == "battle.segment_update.v1"
        if not is_segment and not payload.get("receipt_id") and not lifecycle.get("receipt_id"):
            raise ValueError(f"event {index} is missing immutable receipt reference")


def _parse_last_event_id(value: str | None, *, last_seq: int) -> int:
    if not value:
        return 0
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError("Last-Event-ID must be an integer seq") from exc
    if parsed < 0:
        raise ValueError("Last-Event-ID must be non-negative")
    if parsed > last_seq:
        raise ValueError("Last-Event-ID is beyond current snapshot last_seq; refetch snapshot")
    return parsed


def _sse_frame(event: dict[str, Any]) -> bytes:
    return (
        f"id: {event['seq']}\n"
        "event: battle.live_event\n"
        f"data: {json.dumps(event, sort_keys=True)}\n\n"
    ).encode("utf-8")


def _parse_sse_events(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for frame in text.strip().split("\n\n"):
        if not frame.strip():
            continue
        data_lines = [line[6:] for line in frame.splitlines() if line.startswith("data: ")]
        if not data_lines:
            continue
        events.append(json.loads("\n".join(data_lines)))
    return events


def _assert_no_raw_path_leak(snapshot: dict[str, Any], events: list[dict[str, Any]]) -> None:
    serialized = json.dumps({"snapshot": snapshot, "events": events}, sort_keys=True)
    for marker in FORBIDDEN_TRANSPORT_MARKERS:
        if marker in serialized:
            raise ValueError(f"live transport payload exposes forbidden marker: {marker}")


def _safe_fixture_ref(path: Path) -> str:
    if not path.is_absolute():
        return path.as_posix()
    parts = path.parts
    if "skills" in parts:
        index = parts.index("skills")
        return "/".join(parts[index:])
    return path.name


def _http_json(url: str) -> dict[str, Any]:
    req = Request(url, headers={"Accept": "application/json"})
    with urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _http_text(url: str, *, accept: str, headers: dict[str, str] | None = None) -> str:
    req_headers = {"Accept": accept}
    if headers:
        req_headers.update(headers)
    req = Request(url, headers=req_headers)
    with urlopen(req, timeout=10) as response:
        return response.read().decode("utf-8")


def _http_status(url: str, *, headers: dict[str, str] | None = None) -> int:
    try:
        _http_text(url, accept="text/event-stream", headers=headers)
    except HTTPError as exc:
        return int(exc.code)
    return 200


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
