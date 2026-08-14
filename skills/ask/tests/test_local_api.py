"""The local API must not become a second implementation of anything (#1406).

The failures guarded here: a retried submit buying accepted work twice, a
reconnect replaying events as new effects, a different-UID peer reading another
user's runs, and a caller escaping the artifact root by symlink or `..`.
"""

from __future__ import annotations

import io
import json
import os
import socket
import sys
import threading
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "src"))

from ask.local_api import (  # noqa: E402
    MAX_REQUEST_BYTES,
    PROTOCOL,
    ApiError,
    LocalApi,
    resolve_artifact_path,
    serve_socket,
    serve_stdio,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "run_projection"


@pytest.fixture
def api() -> LocalApi:
    return LocalApi(artifact_root_override=FIXTURES)


def _call(api: LocalApi, method: str, **params) -> dict:
    return api.dispatch({"protocol": PROTOCOL, "request_id": "r1", "method": method, "params": params})


def test_ping_answers_with_the_protocol(api: LocalApi) -> None:
    response = _call(api, "ping")
    assert response["ok"] is True
    assert response["result"]["protocol"] == PROTOCOL


def test_an_unknown_method_is_a_typed_error(api: LocalApi) -> None:
    response = _call(api, "does.not.exist")
    assert response["ok"] is False
    assert response["error"]["code"] == "unknown_method"


def test_a_malformed_envelope_never_raises(api: LocalApi) -> None:
    assert api.dispatch("not an object")["error"]["code"] == "malformed_request"
    assert api.dispatch({"method": "ping", "params": []})["error"]["code"] == "malformed_request"


def test_run_show_returns_the_same_projection_as_the_cli(api: LocalApi) -> None:
    """Required proof 3: one canonical projection, not a second status model."""
    from ask.run_projection import project_run

    response = _call(api, "run.show", run="roundtable_partial")
    assert response["ok"] is True
    assert response["result"] == project_run(FIXTURES / "roundtable_partial")


def test_controls_delegate_to_run_control(api: LocalApi) -> None:
    """Required proof 4: no signals, no direct provider or session writes."""
    steer = _call(api, "run.steer", run="one_handler", node="handler-webgpt", message="hi")
    assert steer["result"]["schema"] == "ask.run_control.v1"
    assert steer["result"]["delivered"] is False

    cancel = _call(api, "run.cancel", run="one_handler")
    assert cancel["result"]["schema"] == "ask.run_control.v1"


def test_a_repeated_idempotency_key_returns_the_original_run(api: LocalApi) -> None:
    """Required proof 5: accepted work is often paid work."""
    api.idempotency.remember("key-1", {"request": "x"}, "run-abc")
    duplicate = api.idempotency.check("key-1", {"request": "x"})
    assert duplicate == {
        "run_id": "run-abc",
        "duplicate": True,
        "note": "returned the original run; nothing was resubmitted",
    }


def test_a_conflicting_payload_on_the_same_key_is_rejected(api: LocalApi) -> None:
    api.idempotency.remember("key-1", {"request": "x"}, "run-abc")
    with pytest.raises(ApiError) as excinfo:
        api.idempotency.check("key-1", {"request": "DIFFERENT"})
    assert excinfo.value.code == "idempotency_conflict"


def test_submit_refuses_rather_than_becoming_a_second_scheduler(api: LocalApi) -> None:
    response = _call(api, "run.submit", request="do a thing")
    assert response["ok"] is False
    assert response["error"]["code"] == "unsupported"


def test_a_cursor_beyond_known_events_reports_a_gap(api: LocalApi) -> None:
    """Required proof 6: a reconnect must not replay events as new effects."""
    response = _call(api, "run.events", run="one_handler", cursor=999)
    assert response["result"]["gap"] is True
    assert response["result"]["events"] == []


def test_a_cursor_resumes_without_replaying(api: LocalApi) -> None:
    first = _call(api, "run.events", run="one_handler")["result"]
    assert first["events"]
    second = _call(api, "run.events", run="one_handler", cursor=first["cursor"])["result"]
    assert second["events"] == []
    assert second["gap"] is False


def test_a_path_outside_the_artifact_root_is_refused() -> None:
    """Required proof 8: `..` and a symlink out are the same escape."""
    with pytest.raises(ApiError) as excinfo:
        resolve_artifact_path("/etc/passwd", FIXTURES)
    assert excinfo.value.code == "path_not_permitted"


def test_a_traversal_segment_is_refused() -> None:
    with pytest.raises(ApiError):
        resolve_artifact_path(str(FIXTURES / ".." / ".." / "etc"), FIXTURES)


def test_a_symlink_escaping_the_root_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "escape").symlink_to(outside)
    with pytest.raises(ApiError):
        resolve_artifact_path(str(root / "escape"), root)


def test_a_path_inside_the_root_is_allowed() -> None:
    assert resolve_artifact_path(str(FIXTURES / "one_handler"), FIXTURES).name == "one_handler"


def test_an_unknown_run_is_not_found(api: LocalApi) -> None:
    assert _call(api, "run.show", run="nope")["error"]["code"] == "not_found"


def test_stdio_transport_answers_line_by_line(api: LocalApi) -> None:
    source = io.StringIO(json.dumps({"method": "ping", "request_id": "a"}) + "\n")
    sink = io.StringIO()
    serve_stdio(api, stdin=source, stdout=sink)
    response = json.loads(sink.getvalue().strip())
    assert response["ok"] is True
    assert response["request_id"] == "a"


def test_stdio_rejects_an_oversized_request(api: LocalApi) -> None:
    source = io.StringIO("x" * (MAX_REQUEST_BYTES + 10) + "\n")
    sink = io.StringIO()
    serve_stdio(api, stdin=source, stdout=sink)
    assert json.loads(sink.getvalue().strip())["error"]["code"] == "request_too_large"


def test_stdio_and_dispatch_agree(api: LocalApi) -> None:
    """Required proof 2: one implementation behind both transports."""
    direct = _call(api, "run.show", run="one_handler")
    source = io.StringIO(json.dumps({"method": "run.show", "request_id": "r1", "params": {"run": "one_handler"}}) + "\n")
    sink = io.StringIO()
    serve_stdio(api, stdin=source, stdout=sink)
    assert json.loads(sink.getvalue().strip()) == direct


def test_the_socket_is_owner_only(tmp_path: Path, api: LocalApi) -> None:
    """Required proof 8: a local socket is not a trust boundary by default."""
    sock = tmp_path / "ask.sock"
    thread = threading.Thread(target=serve_socket, args=(sock, api), kwargs={"max_connections": 1}, daemon=True)
    thread.start()
    for _ in range(200):
        if sock.exists():
            break
        threading.Event().wait(0.02)
    assert sock.exists(), "socket never appeared"
    assert oct(sock.stat().st_mode)[-3:] == "600"

    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(str(sock))
    client.sendall(json.dumps({"method": "ping", "request_id": "s1"}).encode("utf-8"))
    payload = json.loads(client.recv(65536).decode("utf-8").strip())
    client.close()
    thread.join(timeout=5)
    assert payload["ok"] is True


def test_no_response_carries_a_secret(api: LocalApi) -> None:
    """Required proof 10."""
    blob = json.dumps(_call(api, "capabilities.get")).lower()
    for marker in ("sk-", "bearer ", "cookie", "authorization"):
        assert marker not in blob


def test_artifacts_manifest_stays_inside_the_root(api: LocalApi) -> None:
    response = _call(api, "artifacts.manifest", run="one_handler")
    assert response["ok"] is True
    for entry in response["result"]["artifacts"]:
        assert not entry["path"].startswith("/")
        assert ".." not in entry["path"]


def test_health_is_not_a_claim_about_subsystems(api: LocalApi) -> None:
    """A green API health check must not imply Tau or a seat is reachable."""
    result = _call(api, "health.get")["result"]
    assert result["serving"] is True
    assert "capabilities.get" in result["note"]
    assert "healthy" not in result


def test_targets_resolve_returns_one_capability(api: LocalApi) -> None:
    entry = _call(api, "targets.resolve", selector="browser.webgpt")["result"]
    assert entry["capability_id"] == "browser.webgpt"


def test_targets_resolve_rejects_an_unknown_selector(api: LocalApi) -> None:
    assert _call(api, "targets.resolve", selector="nope")["error"]["code"] == "not_found"


def test_plan_preview_has_no_side_effects(api: LocalApi, tmp_path: Path) -> None:
    """Preview exists to see the frozen shape before anything is spent."""
    before = sorted(p.name for p in FIXTURES.iterdir())
    result = _call(
        api,
        "plan.preview",
        nodes=[{
            "node_id": "handler-webgpt",
            "target_kind": "browser_seat",
            "target_selector": "webgpt",
            "adapter": "tau_opaque_compat",
            "tools": ["read"],
            "effects": ["provider_call"],
        }],
    )["result"]
    assert result["logical_hash"].startswith("sha256:")
    assert result["side_effects"] == []
    assert sorted(p.name for p in FIXTURES.iterdir()) == before


def test_plan_preview_is_stable_for_the_same_input(api: LocalApi) -> None:
    """Required proof 2: the same input yields the same logical hash."""
    node = {
        "node_id": "n",
        "target_kind": "model",
        "target_selector": "gpt-5.5-high",
        "adapter": "tau_native_agent",
        "tools": ["read"],
    }
    first = _call(api, "plan.preview", nodes=[node])["result"]["logical_hash"]
    second = _call(api, "plan.preview", nodes=[dict(node)])["result"]["logical_hash"]
    assert first == second


def test_plan_preview_rejects_a_bad_node(api: LocalApi) -> None:
    response = _call(api, "plan.preview", nodes=[{"node_id": "n", "target_kind": "browser_seat",
                                                  "adapter": "tau_native_agent"}])
    assert response["error"]["code"] == "malformed_request"
    assert "node rejected" in response["error"]["message"]


def test_run_access_survives_a_server_restart(tmp_path: Path) -> None:
    """Required proof 7: state lives in artifacts, not in the server.

    Two independently constructed servers must answer identically about the
    same run, because neither caches anything -- every read derives from disk.
    """
    first = LocalApi(artifact_root_override=FIXTURES)
    before = _call(first, "run.show", run="one_handler")
    del first  # the "restart"

    second = LocalApi(artifact_root_override=FIXTURES)
    after = _call(second, "run.show", run="one_handler")
    assert after == before
    assert after["result"]["lifecycle"] == "PASS"


def test_a_restarted_server_forgets_idempotency_keys_honestly(tmp_path: Path) -> None:
    """The limit of the in-memory store, asserted rather than assumed.

    Recovery after a restart is by run identity, not by hoping the key
    survived; a test that pretended otherwise would hide the real behaviour.
    """
    first = LocalApi(artifact_root_override=FIXTURES)
    first.idempotency.remember("k", {"a": 1}, "run-1")
    assert first.idempotency.check("k", {"a": 1})["run_id"] == "run-1"

    second = LocalApi(artifact_root_override=FIXTURES)
    assert second.idempotency.check("k", {"a": 1}) is None
