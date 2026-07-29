"""Executable Battle UX8 live transport adapter.

The adapter serves already-normalized Battle UX fixtures through the UX8
snapshot/SSE contract. It does not inspect Tau, provider, Docker, or Judge raw
runtime directories; the source of truth remains the normalized fixture.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen

from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect as websocket_connect
from websockets.sync.server import Server as WebSocketServer
from websockets.sync.server import ServerConnection, serve as websocket_serve

from .battle_event_adapter import _live_event_envelopes, _snapshot_envelope
from .live_transport_contract import GENETIC_EVENT_TYPES


SNAPSHOT_ENDPOINT_TEMPLATE = "/battle/live/{battle_id}/snapshot"
EVENTS_ENDPOINT_TEMPLATE = "/battle/live/{battle_id}/events"
WEBSOCKET_ENDPOINT_TEMPLATE = "/battle/live/{battle_id}/ws"
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

    @property
    def websocket_endpoint(self) -> str:
        return WEBSOCKET_ENDPOINT_TEMPLATE.format(battle_id=self.battle_id)


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


def create_live_transport_server(
    *,
    source: LiveTransportSource,
    host: str = "127.0.0.1",
    port: int = 0,
    websocket_port: int | None = None,
) -> ThreadingHTTPServer:
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
                        "websocket_endpoint": source.websocket_endpoint if websocket_port is not None else None,
                        "websocket_port": websocket_port,
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


def create_live_websocket_transport_server(
    *,
    source: LiveTransportSource,
    host: str = "127.0.0.1",
    port: int = 0,
    auth_token: str | None = None,
) -> WebSocketServer:
    """Create a WebSocket server for snapshot-first Battle live transport."""

    def handler(connection: ServerConnection) -> None:
        request = urlsplit(connection.request.path)
        request_path = request.path
        if request_path != source.websocket_endpoint:
            connection.close(code=1008, reason="unsupported battle live websocket path")
            return
        if auth_token is not None and not _websocket_authorized(
            request_path=connection.request.path,
            headers=connection.request.headers,
            token=auth_token,
        ):
            connection.close(code=1008, reason="battle live websocket authorization failed")
            return
        try:
            start_after = _parse_last_event_id(
                connection.request.headers.get("Last-Event-ID"),
                last_seq=len(source.events),
            )
        except ValueError as exc:
            connection.close(code=1008, reason=str(exc))
            return
        connection.send(json.dumps(source.snapshot, sort_keys=True))
        for event in source.events:
            if event["seq"] <= start_after:
                continue
            connection.send(json.dumps(event, sort_keys=True))
        connection.close(code=1000, reason="battle live websocket stream complete")

    return websocket_serve(handler, host, port, compression=None)


def serve_live_transport(
    *,
    fixture_path: Path,
    battle_id: str,
    host: str,
    port: int,
    websocket_port: int | None = None,
) -> None:
    """Serve UX8 live transport until interrupted."""

    source = build_live_transport_source(fixture_path=fixture_path, battle_id=battle_id)
    websocket_server: WebSocketServer | None = None
    websocket_thread: threading.Thread | None = None
    actual_websocket_port: int | None = None
    if websocket_port is not None:
        websocket_server = create_live_websocket_transport_server(source=source, host=host, port=websocket_port)
        actual_websocket_port = int(websocket_server.socket.getsockname()[1])
        websocket_thread = threading.Thread(
            target=websocket_server.serve_forever,
            name="battle-live-websocket-transport",
            daemon=True,
        )
        websocket_thread.start()
    server = create_live_transport_server(
        source=source,
        host=host,
        port=port,
        websocket_port=actual_websocket_port,
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()
        if websocket_server is not None:
            websocket_server.shutdown()
        if websocket_thread is not None:
            websocket_thread.join(timeout=5)


def prove_live_transport_server(
    *,
    fixture_path: Path,
    battle_id: str,
    out_dir: Path,
    host: str = "127.0.0.1",
) -> dict[str, Any]:
    """Start the adapter locally and prove snapshot, SSE, and resume behavior."""

    source = build_live_transport_source(fixture_path=fixture_path, battle_id=battle_id)
    websocket_server = create_live_websocket_transport_server(source=source, host=host, port=0)
    websocket_port = int(websocket_server.socket.getsockname()[1])
    server = create_live_transport_server(source=source, host=host, port=0, websocket_port=websocket_port)
    port = int(server.server_address[1])
    thread = threading.Thread(target=server.serve_forever, name="battle-live-transport-proof", daemon=True)
    websocket_thread = threading.Thread(
        target=websocket_server.serve_forever,
        name="battle-live-websocket-proof",
        daemon=True,
    )
    websocket_thread.start()
    thread.start()
    base_url = f"http://{host}:{port}"
    websocket_url = f"ws://{host}:{websocket_port}{source.websocket_endpoint}"
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
        websocket_payloads = _websocket_payloads(websocket_url)
    finally:
        server.shutdown()
        server.server_close()
        websocket_server.shutdown()
        thread.join(timeout=5)
        websocket_thread.join(timeout=5)

    stream_events = _parse_sse_events(stream_text)
    resumed_events = _parse_sse_events(resumed_text)
    websocket_snapshot = websocket_payloads[0] if websocket_payloads else {}
    websocket_events = websocket_payloads[1:]
    _assert_no_raw_path_leak(snapshot, stream_events)
    _assert_no_raw_path_leak({"resumed": resumed_events}, [])
    _assert_no_raw_path_leak(websocket_snapshot, websocket_events)
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
    if health.get("websocket_endpoint") != source.websocket_endpoint or health.get("websocket_port") != websocket_port:
        errors.append("health endpoint did not advertise the paired WebSocket endpoint")
    if websocket_snapshot != snapshot:
        errors.append("WebSocket first message did not match HTTP snapshot")
    if websocket_events != stream_events:
        errors.append("WebSocket event payloads did not match SSE event payloads")
    if errors:
        raise ValueError("\n".join(errors))

    receipt = {
        "schema": "battle.live_transport_server_proof.v1",
        "status": "PASS",
        "mocked": False,
        "live": "local_http_sse_websocket_adapter",
        "battle_id": battle_id,
        "run_id": source.run_id,
        "fixture_ref": source.fixture_path,
        "base_url": base_url,
        "websocket_url": websocket_url,
        "snapshot_endpoint": source.snapshot_endpoint,
        "sse_endpoint": source.events_endpoint,
        "websocket_endpoint": source.websocket_endpoint,
        "snapshot_schema": snapshot.get("schema"),
        "event_schema": "battle.live_event.v1",
        "event_count": len(stream_events),
        "websocket_event_count": len(websocket_events),
        "last_seq": snapshot.get("last_seq"),
        "resume_from_last_event_id": 2,
        "resumed_event_count": len(resumed_events),
        "future_last_event_id_status": bad_resume_status,
        "websocket_snapshot_first": True,
        "websocket_matches_sse_payloads": True,
        "genetic_event_types_when_live": list(GENETIC_EVENT_TYPES),
        "raw_path_boundary": {
            "raw_paths_leaked": False,
            "forbidden_markers": list(FORBIDDEN_TRANSPORT_MARKERS),
        },
        "claim_boundary": {
            "proves": [
                "The Battle live transport adapter served battle.snapshot.v1 over HTTP.",
                "The Battle live transport adapter served ordered battle.live_event.v1 records as SSE.",
                "The Battle live transport adapter served the same snapshot and ordered events over WebSocket.",
                "The Battle live transport adapter honored Last-Event-ID resume.",
                "The Battle live transport adapter failed closed on an impossible future Last-Event-ID.",
            ],
            "does_not_prove": [
                "A production deployment is running.",
                "Production WebSocket TLS, auth, fanout, compression, or reconnect behavior.",
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
    _write_json(out_dir / "websocket-snapshot-response.json", websocket_snapshot)
    (out_dir / "websocket-events.jsonl").write_text(
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in websocket_events),
        encoding="utf-8",
    )
    (out_dir / "events.sse").write_text(stream_text.rstrip() + "\n", encoding="utf-8")
    (out_dir / "resume-after-2.sse").write_text(resumed_text.rstrip() + "\n", encoding="utf-8")
    return receipt


def prove_production_websocket_transport(
    *,
    fixture_path: Path,
    battle_id: str,
    out_dir: Path,
    host: str = "127.0.0.1",
    auth_token: str = "battle-local-production-websocket-proof-token",
) -> dict[str, Any]:
    """Prove production-shaped WebSocket auth, resume, and fanout gates locally."""

    source = build_live_transport_source(fixture_path=fixture_path, battle_id=battle_id)
    websocket_server = create_live_websocket_transport_server(
        source=source,
        host=host,
        port=0,
        auth_token=auth_token,
    )
    websocket_port = int(websocket_server.socket.getsockname()[1])
    websocket_thread = threading.Thread(
        target=websocket_server.serve_forever,
        name="battle-production-websocket-proof",
        daemon=True,
    )
    websocket_thread.start()
    websocket_url = f"ws://{host}:{websocket_port}{source.websocket_endpoint}"
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        authorized_payloads = _websocket_payloads_with_headers(
            websocket_url,
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        query_authorized_payloads = _websocket_payloads_with_headers(
            f"{websocket_url}?access_token={auth_token}",
            headers=None,
        )
        resumed_payloads = _websocket_payloads_with_headers(
            websocket_url,
            headers={
                "Authorization": f"Bearer {auth_token}",
                "Last-Event-ID": "2",
            },
        )
        unauthenticated_rejection = _websocket_rejection_code(websocket_url, headers=None)
        bad_token_rejection = _websocket_rejection_code(
            websocket_url,
            headers={"Authorization": "Bearer wrong-token"},
        )
        bad_resume_rejection = _websocket_rejection_code(
            websocket_url,
            headers={
                "Authorization": f"Bearer {auth_token}",
                "Last-Event-ID": str(len(source.events) + 10),
            },
        )
        fanout_payloads = _concurrent_websocket_payloads(
            websocket_url=websocket_url,
            headers={"Authorization": f"Bearer {auth_token}"},
            client_count=2,
        )
    finally:
        websocket_server.shutdown()
        websocket_thread.join(timeout=5)

    authorized_snapshot = authorized_payloads[0] if authorized_payloads else {}
    authorized_events = authorized_payloads[1:]
    resumed_snapshot = resumed_payloads[0] if resumed_payloads else {}
    resumed_events = resumed_payloads[1:]
    query_authorized_events = query_authorized_payloads[1:]
    _assert_no_raw_path_leak(authorized_snapshot, authorized_events)
    _assert_no_raw_path_leak(resumed_snapshot, resumed_events)

    errors: list[str] = []
    if authorized_snapshot != source.snapshot:
        errors.append("authorized WebSocket first message did not match source snapshot")
    if authorized_events != source.events:
        errors.append("authorized WebSocket events did not match source events")
    if query_authorized_payloads != authorized_payloads:
        errors.append("query-token authorized WebSocket payloads did not match bearer-token payloads")
    if resumed_snapshot != source.snapshot:
        errors.append("resumed WebSocket first message did not match source snapshot")
    if resumed_events != source.events[2:]:
        errors.append("resumed WebSocket did not skip Last-Event-ID acknowledged events")
    if unauthenticated_rejection != 1008:
        errors.append("unauthenticated WebSocket connection did not fail closed with policy violation")
    if bad_token_rejection != 1008:
        errors.append("bad-token WebSocket connection did not fail closed with policy violation")
    if bad_resume_rejection != 1008:
        errors.append("bad Last-Event-ID WebSocket connection did not fail closed with policy violation")
    if len(fanout_payloads) != 2:
        errors.append("fanout proof did not collect two client streams")
    elif fanout_payloads[0] != authorized_payloads or fanout_payloads[1] != authorized_payloads:
        errors.append("fanout clients did not receive identical snapshot/event streams")

    receipt = {
        "schema": "battle.production_websocket_transport_proof.v1",
        "status": "PASS" if not errors else "FAIL",
        "mocked": False,
        "live": "local_authenticated_websocket_fanout_reconnect_adapter",
        "battle_id": battle_id,
        "run_id": source.run_id,
        "fixture_ref": source.fixture_path,
        "websocket_endpoint": source.websocket_endpoint,
        "websocket_url": websocket_url,
        "auth": {
            "mode": "bearer_header_or_access_token_query",
            "token_sha256": hashlib.sha256(auth_token.encode("utf-8")).hexdigest(),
            "unauthenticated_rejection_code": unauthenticated_rejection,
            "bad_token_rejection_code": bad_token_rejection,
        },
        "reconnect": {
            "resume_from_last_event_id": 2,
            "resumed_event_count": len(resumed_events),
            "bad_resume_rejection_code": bad_resume_rejection,
            "snapshot_first_after_resume": resumed_snapshot == source.snapshot,
        },
        "fanout": {
            "client_count": len(fanout_payloads),
            "identical_streams": len(fanout_payloads) == 2
            and all(payloads == authorized_payloads for payloads in fanout_payloads),
        },
        "event_count": len(authorized_events),
        "last_seq": source.snapshot.get("last_seq"),
        "websocket_snapshot_first": authorized_snapshot == source.snapshot,
        "websocket_matches_source_events": authorized_events == source.events,
        "query_token_matches_bearer": query_authorized_payloads == authorized_payloads,
        "errors": errors,
        "claim_boundary": {
            "proves": [
                "The local Battle WebSocket adapter can require authorization before emitting Battle data.",
                "The local Battle WebSocket adapter rejects missing and bad authorization before emitting Battle data.",
                "The local Battle WebSocket adapter supports snapshot-first reconnect with Last-Event-ID resume.",
                "The local Battle WebSocket adapter fails closed on impossible future Last-Event-ID values.",
                "Two concurrent authorized clients receive identical snapshot/event streams.",
            ],
            "does_not_prove": [
                "Production infrastructure is deployed.",
                "Production TLS, certificates, DNS, ingress, or secret management are configured.",
                "Production-scale fanout capacity or load behavior.",
                "Browser session identity, OAuth, cookie, CSRF, or tenant authorization.",
                "Unbounded swarm execution works.",
                "Battle or RelayForge is production ready.",
            ],
        },
    }
    _write_json(out_dir / "production-websocket-transport-proof.json", receipt)
    _write_json(out_dir / "authorized-snapshot-response.json", authorized_snapshot)
    (out_dir / "authorized-events.jsonl").write_text(
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in authorized_events),
        encoding="utf-8",
    )
    (out_dir / "resumed-events.jsonl").write_text(
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in resumed_events),
        encoding="utf-8",
    )
    if errors:
        raise ValueError("\n".join(errors))
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


def _websocket_payloads(url: str) -> list[dict[str, Any]]:
    return _websocket_payloads_with_headers(url, headers=None)


def _websocket_payloads_with_headers(
    url: str,
    *,
    headers: dict[str, str] | None,
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    with websocket_connect(
        url,
        additional_headers=headers,
        open_timeout=10,
        close_timeout=5,
        max_size=4 * 1024 * 1024,
    ) as connection:
        while True:
            try:
                message = connection.recv(timeout=10)
            except ConnectionClosed:
                break
            if not isinstance(message, str):
                raise ValueError("Battle WebSocket transport only accepts JSON text frames")
            payloads.append(json.loads(message))
    return payloads


def _websocket_authorized(*, request_path: str, headers: Any, token: str) -> bool:
    authorization = headers.get("Authorization")
    if authorization == f"Bearer {token}":
        return True
    query = parse_qs(urlsplit(request_path).query)
    return token in query.get("access_token", [])


def _websocket_rejection_code(url: str, *, headers: dict[str, str] | None) -> int | None:
    with websocket_connect(
        url,
        additional_headers=headers,
        open_timeout=10,
        close_timeout=5,
        max_size=4 * 1024 * 1024,
    ) as connection:
        try:
            message = connection.recv(timeout=10)
        except ConnectionClosed as exc:
            return exc.rcvd.code if exc.rcvd is not None else None
        raise ValueError(f"expected WebSocket rejection, received payload: {message!r}")


def _concurrent_websocket_payloads(
    *,
    websocket_url: str,
    headers: dict[str, str],
    client_count: int,
) -> list[list[dict[str, Any]]]:
    barrier = threading.Barrier(client_count)
    results: list[list[dict[str, Any]] | None] = [None] * client_count
    errors: list[BaseException] = []

    def worker(index: int) -> None:
        try:
            barrier.wait(timeout=10)
            results[index] = _websocket_payloads_with_headers(websocket_url, headers=headers)
        except BaseException as exc:  # noqa: BLE001 - propagate worker error after join
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=(index,), name=f"battle-ws-fanout-{index}", daemon=True)
        for index in range(client_count)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    if errors:
        raise errors[0]
    if any(result is None for result in results):
        raise TimeoutError("timed out waiting for WebSocket fanout clients")
    return [result for result in results if result is not None]


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
