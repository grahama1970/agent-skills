"""Deterministic transport safety smoke for Battle live frontend/backend."""

from __future__ import annotations

import json
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .live_transport_server import (
    _websocket_payloads,
    build_live_transport_source,
    create_live_transport_server,
    create_live_websocket_transport_server,
)


DEFAULT_FIXTURE = Path(
    "spectator/public/battle-fixtures/battle-004-pr6-genetic-pixi/battle.normalized_ux_fixture.json"
)
FRONTEND_TEST_FILES = [
    "src/lib/battle-transport-reducer.test.ts",
    "src/lib/battle-live-sse-runtime.test.ts",
    "src/lib/battle-live-transport-contract.test.ts",
]


def prove_transport_safety_smoke(
    *,
    out_dir: Path,
    battle_root: Path,
    fixture: Path = DEFAULT_FIXTURE,
    battle_id: str = "battle-004",
) -> dict[str, Any]:
    out_dir = out_dir.resolve()
    battle_root = battle_root.resolve()
    fixture_path = fixture if fixture.is_absolute() else battle_root / fixture
    spectator_root = battle_root / "spectator"
    out_dir.mkdir(parents=True, exist_ok=True)

    source = build_live_transport_source(fixture_path=fixture_path, battle_id=battle_id)
    websocket_server = create_live_websocket_transport_server(source=source, host="127.0.0.1", port=0)
    websocket_port = int(websocket_server.socket.getsockname()[1])
    server = create_live_transport_server(
        source=source,
        host="127.0.0.1",
        port=0,
        websocket_port=websocket_port,
    )
    port = int(server.server_address[1])
    thread = threading.Thread(target=server.serve_forever, name="battle-transport-safety-smoke", daemon=True)
    websocket_thread = threading.Thread(
        target=websocket_server.serve_forever,
        name="battle-websocket-transport-safety-smoke",
        daemon=True,
    )
    websocket_thread.start()
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    websocket_url = f"ws://127.0.0.1:{websocket_port}{source.websocket_endpoint}"
    try:
        health = _http_json(f"{base_url}/healthz")
        full_sse = _http_text(f"{base_url}{source.events_endpoint}", accept="text/event-stream")
        resume_after_two = _http_text(
            f"{base_url}{source.events_endpoint}",
            accept="text/event-stream",
            headers={"Last-Event-ID": "2"},
        )
        bad_resume_statuses = {
            "future_last_event_id": _http_status(
                f"{base_url}{source.events_endpoint}",
                headers={"Last-Event-ID": str(len(source.events) + 1)},
            ),
            "non_integer_last_event_id": _http_status(
                f"{base_url}{source.events_endpoint}",
                headers={"Last-Event-ID": "not-a-seq"},
            ),
            "negative_last_event_id": _http_status(
                f"{base_url}{source.events_endpoint}",
                headers={"Last-Event-ID": "-1"},
            ),
        }
        websocket_payloads = _websocket_payloads(websocket_url)
    finally:
        server.shutdown()
        server.server_close()
        websocket_server.shutdown()
        thread.join(timeout=5)
        websocket_thread.join(timeout=5)

    frontend = _run_frontend_transport_tests(spectator_root=spectator_root)
    sse_events = _parse_sse_events(full_sse)
    resume_events = _parse_sse_events(resume_after_two)
    websocket_snapshot = websocket_payloads[0] if websocket_payloads else {}
    websocket_events = websocket_payloads[1:]
    errors = _receipt_errors(
        health=health,
        event_count=len(source.events),
        source_snapshot=source.snapshot,
        sse_events=sse_events,
        resume_events=resume_events,
        bad_resume_statuses=bad_resume_statuses,
        websocket_snapshot=websocket_snapshot,
        websocket_events=websocket_events,
        frontend=frontend,
    )
    receipt = {
        "schema": "battle.transport_safety_smoke.v1",
        "status": "PASS" if not errors else "FAIL",
        "mocked": False,
        "live": "local_http_sse_websocket_adapter_plus_frontend_transport_tests",
        "battle_id": battle_id,
        "base_url": base_url,
        "websocket_url": websocket_url,
        "backend": {
            "health": health,
            "event_count": len(source.events),
            "last_seq": source.snapshot.get("last_seq"),
            "resume_from_last_event_id": 2,
            "resumed_event_count": len(resume_events),
            "bad_resume_statuses": bad_resume_statuses,
            "safety_cases": [
                "Last-Event-ID resume excludes already acknowledged events.",
                "Future Last-Event-ID fails closed with HTTP 400.",
                "Non-integer Last-Event-ID fails closed with HTTP 400.",
                "Negative Last-Event-ID fails closed with HTTP 400.",
            ],
            "websocket": {
                "endpoint": source.websocket_endpoint,
                "event_count": len(websocket_events),
                "snapshot_first": websocket_snapshot.get("schema") == "battle.snapshot.v1",
                "matches_sse_payloads": websocket_events == sse_events,
            },
        },
        "frontend": frontend,
        "claim_boundary": {
            "proves": [
                "The existing local HTTP/SSE backend fails closed on invalid Last-Event-ID inputs.",
                "The existing local HTTP/SSE backend resumes from Last-Event-ID without replaying acknowledged events.",
                "The local WebSocket backend emits battle.snapshot.v1 first, then ordered battle.live_event.v1 payloads.",
                "The local WebSocket backend event payloads match the HTTP/SSE event payloads.",
                "The spectator transport reducer deduplicates events and enters gap_recovery on sequence gaps.",
                "The spectator SSE parser rejects malformed payloads without applying them.",
            ],
            "does_not_prove": [
                "Production infrastructure is deployed.",
                "Production WebSocket TLS, auth, fanout, compression, or reconnect behavior.",
                "Browser EventSource reconnect timing under network failure.",
                "Unbounded swarm execution.",
                "Battle or RelayForge production readiness.",
            ],
        },
        "errors": errors,
        "created_at": _now_utc(),
    }
    (out_dir / "transport-safety-smoke.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out_dir / "events.sse").write_text(full_sse.rstrip() + "\n", encoding="utf-8")
    (out_dir / "resume-after-2.sse").write_text(resume_after_two.rstrip() + "\n", encoding="utf-8")
    (out_dir / "websocket-snapshot-response.json").write_text(
        json.dumps(websocket_snapshot, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out_dir / "websocket-events.jsonl").write_text(
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in websocket_events),
        encoding="utf-8",
    )
    (out_dir / "frontend-transport-tests.stdout").write_text(frontend["stdout_tail"], encoding="utf-8")
    (out_dir / "frontend-transport-tests.stderr").write_text(frontend["stderr_tail"], encoding="utf-8")
    if errors:
        raise RuntimeError("\n".join(errors))
    return receipt


def _run_frontend_transport_tests(*, spectator_root: Path) -> dict[str, Any]:
    command = ["npm", "run", "test", "--", *FRONTEND_TEST_FILES]
    result = subprocess.run(
        command,
        cwd=spectator_root,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    summary = _parse_vitest_summary(result.stdout + "\n" + result.stderr)
    return {
        "command": " ".join(command),
        "returncode": result.returncode,
        "test_files_passed": summary.get("test_files_passed"),
        "test_files_total": summary.get("test_files_total"),
        "tests_passed": summary.get("tests_passed"),
        "tests_total": summary.get("tests_total"),
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
    }


def _parse_vitest_summary(text: str) -> dict[str, int | None]:
    files = re.search(r"Test Files\s+(\d+) passed \((\d+)\)", text)
    tests = re.search(r"Tests\s+(\d+) passed \((\d+)\)", text)
    return {
        "test_files_passed": int(files.group(1)) if files else None,
        "test_files_total": int(files.group(2)) if files else None,
        "tests_passed": int(tests.group(1)) if tests else None,
        "tests_total": int(tests.group(2)) if tests else None,
    }


def _receipt_errors(
    *,
    health: dict[str, Any],
    event_count: int,
    source_snapshot: dict[str, Any],
    sse_events: list[dict[str, Any]],
    resume_events: list[dict[str, Any]],
    bad_resume_statuses: dict[str, int],
    websocket_snapshot: dict[str, Any],
    websocket_events: list[dict[str, Any]],
    frontend: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    if health.get("status") != "PASS":
        errors.append("backend health did not return PASS")
    if not health.get("websocket_endpoint") or not health.get("websocket_port"):
        errors.append("backend health did not advertise WebSocket endpoint and port")
    if websocket_snapshot != source_snapshot:
        errors.append("WebSocket first frame did not match source snapshot")
    if websocket_events != sse_events:
        errors.append("WebSocket events did not match SSE payloads")
    if [event.get("seq") for event in websocket_events] != list(range(1, event_count + 1)):
        errors.append("WebSocket event seq values are not contiguous")
    if len(resume_events) != max(event_count - 2, 0):
        errors.append("resume-after-2 returned unexpected event count")
    if resume_events and min(int(event.get("seq", 0)) for event in resume_events) <= 2:
        errors.append("resume-after-2 replayed already acknowledged events")
    for case, status in bad_resume_statuses.items():
        if status != 400:
            errors.append(f"{case} did not fail closed with HTTP 400")
    if frontend.get("returncode") != 0:
        errors.append("frontend transport tests returned non-zero")
    if frontend.get("tests_passed") != frontend.get("tests_total") or not frontend.get("tests_total"):
        errors.append("frontend transport test summary did not show all tests passed")
    return errors


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


def _parse_sse_events(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for frame in text.strip().split("\n\n"):
        if not frame.strip():
            continue
        data_lines = [line[6:] for line in frame.splitlines() if line.startswith("data: ")]
        if data_lines:
            events.append(json.loads("\n".join(data_lines)))
    return events


def _now_utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
