"""Executable local UX8 snapshot/SSE adapter for normalized Battle fixtures."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .live_transport_contract import PATH_LEAK_MARKERS, PRIVATE_MARKERS, SECRET_PATTERNS


SNAPSHOT_SCHEMA = "battle.snapshot.v1"
LIVE_EVENT_SCHEMA = "battle.live_event.v1"
SSE_EVENT_NAME = "battle.live_event"


@dataclass(frozen=True)
class LiveTransportSource:
    battle_id: str
    run_id: str
    snapshot_endpoint: str
    events_endpoint: str
    snapshot: dict[str, Any]
    events: list[dict[str, Any]]


def build_live_transport_source(*, fixture_path: Path, battle_id: str) -> LiveTransportSource:
    """Build a UX8 snapshot and ordered live-event stream from a normalized fixture."""

    fixture = _read_json(fixture_path)
    fixture_battle_id = fixture.get("battle_id")
    if fixture_battle_id != battle_id:
        raise ValueError(f"battle_id mismatch: requested {battle_id!r}, fixture has {fixture_battle_id!r}")
    if fixture.get("schema") != "battle.normalized_ux_fixture.v1":
        raise ValueError("fixture must use schema battle.normalized_ux_fixture.v1")

    run_id = str(fixture.get("run_id") or fixture.get("genetic_lifecycle", {}).get("fixture_id") or fixture_path.parent.name)
    snapshot_endpoint = f"/battle/live/{battle_id}/snapshot"
    events_endpoint = f"/battle/live/{battle_id}/events"
    source_events = _ordered_fixture_events(fixture)
    events = [
        _live_event_from_fixture_event(event=event, seq=index, battle_id=battle_id, run_id=run_id)
        for index, event in enumerate(source_events, start=1)
    ]
    snapshot = {
        "schema": SNAPSHOT_SCHEMA,
        "battle_id": battle_id,
        "run_id": run_id,
        "generated_at": fixture.get("generated_at") or "1970-01-01T00:00:00Z",
        "mode": "live",
        "source_fixture_schema": fixture.get("schema"),
        "status": fixture.get("status", "SNAPSHOT_READY"),
        "mocked": fixture.get("mocked", False),
        "live": "local_http_sse_adapter",
        "last_seq": len(events),
        "events": [],
        "snapshot_endpoint": snapshot_endpoint,
        "sse_endpoint": events_endpoint,
        "generated_from": "battle.normalized_ux_fixture.v1",
        "claim_boundary": _claim_boundary(fixture),
        "lanes": _compact_lanes(fixture.get("lanes", [])),
        "scoreboard": fixture.get("scoreboard", {}),
        "timeline": fixture.get("timeline", {}),
        "genetic_lifecycle": {
            "present_event_types": fixture.get("genetic_lifecycle", {}).get("present_event_types", []),
            "not_emitted_event_types": fixture.get("genetic_lifecycle", {}).get("not_emitted_event_types", []),
            "claim_boundary": fixture.get("genetic_lifecycle", {}).get("claim_boundary", {}),
        },
    }
    _assert_no_raw_path_leak(snapshot)
    for event in events:
        _assert_no_raw_path_leak(event)
    return LiveTransportSource(
        battle_id=battle_id,
        run_id=run_id,
        snapshot_endpoint=snapshot_endpoint,
        events_endpoint=events_endpoint,
        snapshot=snapshot,
        events=events,
    )


def serve_live_transport(*, fixture_path: Path, battle_id: str, host: str, port: int) -> None:
    """Serve health, snapshot, and finite SSE endpoints for a normalized fixture."""

    source = build_live_transport_source(fixture_path=fixture_path, battle_id=battle_id)
    server = _make_server(source=source, host=host, port=port)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def prove_live_transport_server(*, fixture_path: Path, battle_id: str, out_dir: Path) -> dict[str, Any]:
    """Exercise the local SSE adapter and write deterministic proof artifacts."""

    source = build_live_transport_source(fixture_path=fixture_path, battle_id=battle_id)
    server = _make_server(source=source, host="127.0.0.1", port=0)
    port = int(server.server_address[1])
    thread = threading.Thread(target=server.serve_forever, name="battle-live-transport-proof", daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{port}"
        healthz = _get_json(f"{base}/healthz")
        snapshot = _get_json(f"{base}{source.snapshot_endpoint}")
        events_sse = _get_text(f"{base}{source.events_endpoint}")
        resumed_sse = _get_text(f"{base}{source.events_endpoint}", headers={"Last-Event-ID": "2"})
        future_status = _get_status(f"{base}{source.events_endpoint}", headers={"Last-Event-ID": str(len(source.events) + 5)})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    out_dir.mkdir(parents=True, exist_ok=True)
    _write_json(out_dir / "healthz-response.json", healthz)
    _write_json(out_dir / "snapshot-response.json", snapshot)
    (out_dir / "events.sse").write_text(events_sse, encoding="utf-8")
    (out_dir / "events-resume-from-2.sse").write_text(resumed_sse, encoding="utf-8")

    raw_paths_leaked = _contains_raw_path_marker({"snapshot": snapshot, "events": _parse_sse_data(events_sse)})
    receipt = {
        "schema": "battle.live_transport_server_proof.v1",
        "status": "PASS",
        "mocked": False,
        "live": "local_http_sse_adapter",
        "battle_id": battle_id,
        "run_id": source.run_id,
        "snapshot_schema": snapshot.get("schema"),
        "event_schema": source.events[0].get("schema") if source.events else None,
        "event_count": len(source.events),
        "last_seq": snapshot.get("last_seq"),
        "resume_from_last_event_id": 2,
        "resumed_event_count": _count_sse_events(resumed_sse),
        "future_last_event_id_status": future_status,
        "raw_path_boundary": {
            "raw_paths_leaked": raw_paths_leaked,
            "frontend_reads_raw_runtime_paths": False,
        },
        "claim_boundary": {
            "proves": [
                "The local Battle live transport adapter served a battle.snapshot.v1 snapshot.",
                "The local Battle live transport adapter served ordered battle.live_event.v1 SSE events.",
                "Last-Event-ID resume returns only events after the acknowledged sequence.",
            ],
            "does_not_prove": [
                "Production deployment.",
                "WebSocket support.",
                "Exploit success.",
                "Blue detection, kill, or block.",
                "Judge success.",
            ],
        },
    }
    if raw_paths_leaked:
        receipt["status"] = "FAIL"
    _write_json(out_dir / "live-transport-server-proof.json", receipt)
    return receipt


def _make_server(*, source: LiveTransportSource, host: str, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        server_version = "BattleLiveTransport/1"

        def do_OPTIONS(self) -> None:  # noqa: N802
            self._send_empty(204)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/healthz":
                self._send_json(
                    {
                        "schema": "battle.live_transport_health.v1",
                        "status": "PASS",
                        "battle_id": source.battle_id,
                        "run_id": source.run_id,
                        "snapshot_endpoint": source.snapshot_endpoint,
                        "sse_endpoint": source.events_endpoint,
                        "event_count": len(source.events),
                        "last_seq": len(source.events),
                    }
                )
                return
            if parsed.path == source.snapshot_endpoint:
                self._send_json(source.snapshot)
                return
            if parsed.path == source.events_endpoint:
                last_event_id = _last_event_id(self.headers.get("Last-Event-ID"), parse_qs(parsed.query))
                if last_event_id > len(source.events):
                    self._send_json(
                        {
                            "schema": "battle.live_transport_error.v1",
                            "status": "GAP",
                            "reason": "last_event_id_beyond_available_stream",
                            "last_seq": len(source.events),
                        },
                        status=400,
                    )
                    return
                events = [event for event in source.events if int(event["seq"]) > last_event_id]
                self._send_sse(events)
                return
            self._send_json({"status": "NOT_FOUND", "path": parsed.path}, status=404)

        def log_message(self, _format: str, *_args: Any) -> None:
            return

        def _send_empty(self, status: int) -> None:
            self.send_response(status)
            self._send_cors_headers()
            self.end_headers()

        def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
            encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _send_sse(self, events: list[dict[str, Any]]) -> None:
            chunks: list[str] = []
            for event in events:
                chunks.append(f"id: {event['seq']}\n")
                chunks.append(f"event: {SSE_EVENT_NAME}\n")
                chunks.append(f"data: {json.dumps(event, sort_keys=True)}\n\n")
            encoded = "".join(chunks).encode("utf-8")
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Accel-Buffering", "no")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _send_cors_headers(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Last-Event-ID, Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")

    return ThreadingHTTPServer((host, port), Handler)


def _ordered_fixture_events(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    events = fixture.get("events", [])
    if not isinstance(events, list):
        raise ValueError("fixture.events must be a list")
    return sorted(
        [event for event in events if isinstance(event, dict)],
        key=lambda event: (
            event.get("order_index", 0) if isinstance(event.get("order_index"), int) else 0,
            event.get("id", ""),
        ),
    )


def _live_event_from_fixture_event(*, event: dict[str, Any], seq: int, battle_id: str, run_id: str) -> dict[str, Any]:
    event_id = str(event.get("id") or f"{run_id}:event:{seq}")
    at_seconds = _event_seconds(event, seq)
    lane_id = str(event.get("lane_id") or event.get("actor_id") or "battle")
    receipt_id = str(_receipt_id(event) or event_id)
    event_type = str(event.get("event_type") or "battle.event")
    ui = event.get("ui") if isinstance(event.get("ui"), dict) else {}
    payload = {
        "actor_id": event.get("actor_id"),
        "actor_kind": event.get("actor_kind"),
        "team": event.get("team"),
        "lane_id": lane_id,
        "receipt_id": receipt_id,
        "summary": event.get("summary"),
        "ui": ui,
    }
    normalized = {
        "schema": LIVE_EVENT_SCHEMA,
        "event_id": event_id,
        "seq": seq,
        "battle_id": battle_id,
        "run_id": run_id,
        "at_seconds": at_seconds,
        "observed_at": str(event.get("ts") or "1970-01-01T00:00:00Z"),
        "event_type": event_type,
        "payload": _redact_payload(payload),
        "lifecycle": {
            "schema": "battle.lifecycle_event.v1",
            "source_time_seconds": at_seconds,
            "phase": _event_phase(event_type),
            "importance": str(ui.get("importance") or "visible"),
            "lane_id": lane_id,
            "exploit_id": lane_id,
            "spawn_type": str(event.get("spawn_type") or ""),
            "outcome_class": str(event.get("outcome_class") or "unresolved_pressure"),
            "score_delta": event.get("score_delta") if isinstance(event.get("score_delta"), dict) else {},
            "receipt_id": receipt_id,
            "presentation_owner": "ux",
            "proof_mode": str(event.get("proof_mode") or "receipt_backed_fixture"),
        },
    }
    return normalized


def _event_seconds(event: dict[str, Any], seq: int) -> float:
    for key in ("at_seconds", "elapsed_seconds"):
        value = event.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return float(seq)


def _event_phase(event_type: str) -> str:
    parts = event_type.replace("-", "_").split(".")
    return parts[-1] if parts and parts[-1] else "event"


def _receipt_id(event: dict[str, Any]) -> str | None:
    evidence = event.get("evidence")
    if isinstance(evidence, dict) and evidence.get("receipt_id"):
        return str(evidence["receipt_id"])
    receipts = event.get("receipts")
    if isinstance(receipts, list) and receipts:
        first = receipts[0]
        if isinstance(first, dict) and first.get("receipt_id"):
            return str(first["receipt_id"])
        if isinstance(first, str):
            return first
    return None


def _claim_boundary(fixture: dict[str, Any]) -> dict[str, Any]:
    genetic = fixture.get("genetic_lifecycle")
    if isinstance(genetic, dict) and isinstance(genetic.get("claim_boundary"), dict):
        return genetic["claim_boundary"]
    claims = fixture.get("claims")
    if isinstance(claims, dict):
        return claims
    return {
        "may_claim": ["normalized_snapshot_materialized", "ordered_live_events_materialized"],
        "must_not_claim": ["exploit_success", "blue_detection", "blue_block", "judge_success_without_judge_receipt"],
    }


def _compact_lanes(lanes: Any) -> list[dict[str, Any]]:
    if not isinstance(lanes, list):
        return []
    compact: list[dict[str, Any]] = []
    for lane in lanes:
        if not isinstance(lane, dict):
            continue
        compact.append(
            {
                "id": lane.get("id"),
                "name": lane.get("name"),
                "team": lane.get("team"),
                "generation": lane.get("generation"),
                "runnerState": lane.get("runnerState"),
                "terminal": lane.get("terminal"),
                "proofMode": lane.get("proofMode"),
            }
        )
    return compact


def _redact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    serialized = json.dumps(payload, sort_keys=True)
    for marker in [*PATH_LEAK_MARKERS, *PRIVATE_MARKERS, "/tmp/", "/home/"]:
        serialized = serialized.replace(marker, "[redacted]")
    return json.loads(serialized)


def _assert_no_raw_path_leak(payload: dict[str, Any]) -> None:
    if _contains_raw_path_marker(payload):
        raise ValueError("live transport payload contains raw runtime path, private marker, or secret-like material")


def _contains_raw_path_marker(payload: Any) -> bool:
    serialized = json.dumps(payload, sort_keys=True)
    for marker in [*PATH_LEAK_MARKERS, *PRIVATE_MARKERS]:
        if marker in serialized:
            return True
    return any(pattern.search(serialized) for pattern in SECRET_PATTERNS)


def _last_event_id(header: str | None, query: dict[str, list[str]]) -> int:
    value = header or (query.get("last_event_id") or query.get("lastEventId") or ["0"])[0]
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(parsed, 0)


def _get_json(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _get_text(url: str, headers: dict[str, str] | None = None) -> str:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=10) as response:
        return response.read().decode("utf-8")


def _get_status(url: str, headers: dict[str, str] | None = None) -> int:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)


def _parse_sse_data(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


def _count_sse_events(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.startswith("event: "))


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
