"""
Simulate every normal Chutes.ai error that chutes-call must handle.

Uses httpx mock responses injected into STATE.http_client to test the full
call_with_retries → _call_backend → circuit breaker → fallback chain pipeline.

Run: python3 test_error_simulation.py <skill_dir>
Exit 0 = all pass, exit 1 = failures.

Tests are split across two files:
  - test_error_simulation.py (this file): runner + T13-T19
  - test_error_simulation_ext.py: T20-T25
"""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
import time
from unittest.mock import AsyncMock

import httpx
from unittest.mock import patch

SKILL_DIR = sys.argv[1] if len(sys.argv) > 1 else "."
sys.path.insert(0, SKILL_DIR)

PASS = 0
FAIL = 0

# Patch asyncio.sleep to be instant in all tests (avoid exponential backoff)
_real_sleep = asyncio.sleep

async def _instant_sleep(delay):
    await _real_sleep(0)

_sleep_patch = patch("asyncio.sleep", _instant_sleep)


def report(test_id: str, desc: str, ok: bool, detail: str = ""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  PASS  [{test_id}] {desc}")
    else:
        FAIL += 1
        msg = f"  FAIL  [{test_id}] {desc}"
        if detail:
            msg += f"  -- {detail}"
        print(msg)


def make_mock_response(status_code: int, body: dict | str = "",
                       headers: dict | None = None) -> httpx.Response:
    """Build a fake httpx.Response."""
    if isinstance(body, dict):
        content = json.dumps(body).encode()
    else:
        content = body.encode() if isinstance(body, str) else body
    return httpx.Response(
        status_code=status_code,
        content=content,
        headers=headers or {},
        request=httpx.Request("POST", "https://fake.api/chat/completions"),
    )


def ok_response(content: str = "Hello world", model: str = "deepseek-ai/DeepSeek-V3",
                tokens_in: int = 10, tokens_out: int = 20) -> httpx.Response:
    return make_mock_response(200, {
        "choices": [{"message": {"content": content}}],
        "model": model,
        "usage": {"prompt_tokens": tokens_in, "completion_tokens": tokens_out},
    })


def fresh_app():
    """Import server with fresh state."""
    import server as srv
    importlib.reload(srv)
    return srv


# ── T13: 429 Rate Limiting ──────────────────────────────────────────

def test_429_single():
    """T13.1: Single 429 → retries exhausted, returns ok=False."""
    from fastapi.testclient import TestClient
    srv = fresh_app()
    with TestClient(srv.app) as c:
        srv.STATE.http_client.post = AsyncMock(return_value=make_mock_response(
            429, {"error": "rate limited"}, headers={"retry-after": "0"},
        ))
        data = c.post("/chat", json={
            "messages": [{"role": "user", "content": "hi"}], "caller": "test",
        }).json()
        report("T13.1", "429 → ok=False with retries",
               data["ok"] is False and data["retries"] >= 1,
               f"ok={data['ok']} retries={data['retries']}")


def test_429_retry_after_header():
    """T13.2: Retry-After header parsed."""
    fresh_app()
    from server import parse_retry_after
    val = parse_retry_after(httpx.Headers({"retry-after": "5"}))
    report("T13.2", "Retry-After: 5 → 5.0", val == 5.0, f"got {val}")


def test_429_x_ratelimit_reset():
    """T13.3: x-ratelimit-reset header parsed."""
    fresh_app()
    from server import parse_retry_after
    val = parse_retry_after(httpx.Headers({"x-ratelimit-reset": "10"}))
    report("T13.3", "x-ratelimit-reset: 10 → 10.0", val == 10.0, f"got {val}")


def test_429_ratelimit_reset():
    """T13.4: ratelimit-reset header parsed."""
    fresh_app()
    from server import parse_retry_after
    val = parse_retry_after(httpx.Headers({"ratelimit-reset": "3"}))
    report("T13.4", "ratelimit-reset: 3 → 3.0", val == 3.0, f"got {val}")


def test_429_no_retry_header():
    """T13.5: No retry headers → returns 0."""
    fresh_app()
    from server import parse_retry_after
    val = parse_retry_after(httpx.Headers({"content-type": "application/json"}))
    report("T13.5", "No retry headers → 0", val == 0, f"got {val}")


def test_429_dynamic_shrink():
    """T13.6: 3+ 429s in window → semaphore shrinks."""
    from fastapi.testclient import TestClient
    srv = fresh_app()
    with TestClient(srv.app) as c:
        initial = srv.STATE.semaphore_size
        srv.STATE.http_client.post = AsyncMock(return_value=make_mock_response(
            429, {"error": "rate limited"}, headers={"retry-after": "0"},
        ))
        for _ in range(4):
            c.post("/chat", json={"messages": [{"role": "user", "content": "hi"}]})
        new = srv.STATE.semaphore_size
        report("T13.6", f"Dynamic shrink: {initial} → {new}",
               new < initial, f"initial={initial} new={new}")


def test_429_semaphore_restore():
    """T13.7: Semaphore restores after 429 storm clears."""
    from fastapi.testclient import TestClient
    srv = fresh_app()
    with TestClient(srv.app) as c:
        srv.STATE.semaphore_size = 3
        srv.STATE.semaphore = asyncio.Semaphore(3)
        srv.STATE.recent_429s = []
        srv.STATE.http_client.post = AsyncMock(return_value=ok_response())
        c.post("/chat", json={"messages": [{"role": "user", "content": "hi"}]})
        new = srv.STATE.semaphore_size
        report("T13.7", f"Semaphore restored: 3 → {new}", new > 3, f"new={new}")


# ── T14: 5xx Server Errors ──────────────────────────────────────────

def test_5xx(test_id: str, code: int):
    """Generic 5xx test."""
    from fastapi.testclient import TestClient
    srv = fresh_app()
    with TestClient(srv.app) as c:
        srv.STATE.http_client.post = AsyncMock(
            return_value=make_mock_response(code, f"Error {code}"))
        data = c.post("/chat", json={
            "messages": [{"role": "user", "content": "hi"}],
        }).json()
        report(test_id, f"{code} → ok=False, error mentions {code}",
               data["ok"] is False and str(code) in data.get("error", ""),
               f"error={data.get('error', '')[:60]}")


# ── T15: 4xx Client Errors ──────────────────────────────────────────

def test_4xx(test_id: str, code: int, body: dict):
    """Generic 4xx test."""
    from fastapi.testclient import TestClient
    srv = fresh_app()
    with TestClient(srv.app) as c:
        srv.STATE.http_client.post = AsyncMock(
            return_value=make_mock_response(code, body))
        data = c.post("/chat", json={
            "messages": [{"role": "user", "content": "hi"}],
        }).json()
        report(test_id, f"{code} → ok=False, error mentions {code}",
               data["ok"] is False and str(code) in data.get("error", ""),
               f"error={data.get('error', '')[:60]}")


# ── T16: Timeout Errors ─────────────────────────────────────────────

def test_timeout(test_id: str, exc_class, desc: str):
    """Generic timeout test."""
    from fastapi.testclient import TestClient
    srv = fresh_app()
    with TestClient(srv.app) as c:
        srv.STATE.http_client.post = AsyncMock(side_effect=exc_class("timed out"))
        data = c.post("/chat", json={
            "messages": [{"role": "user", "content": "hi"}],
        }).json()
        report(test_id, f"{desc} → ok=False",
               data["ok"] is False and "imeout" in data.get("error", ""),
               f"error={data.get('error', '')[:60]}")


# ── T17: Connection Errors ──────────────────────────────────────────

def test_connection_error():
    """T17.1: ConnectError → breaks retry, fails."""
    from fastapi.testclient import TestClient
    srv = fresh_app()
    with TestClient(srv.app) as c:
        srv.STATE.http_client.post = AsyncMock(
            side_effect=httpx.ConnectError("connection refused"))
        data = c.post("/chat", json={
            "messages": [{"role": "user", "content": "hi"}],
        }).json()
        report("T17.1", "ConnectError → ok=False",
               data["ok"] is False and data["retries"] >= 1,
               f"error={data.get('error', '')[:60]}")


def test_connection_error_breaks_loop():
    """T17.2: Generic exception only retries once per backend."""
    from fastapi.testclient import TestClient
    srv = fresh_app()
    with TestClient(srv.app) as c:
        call_count = 0

        async def counting_post(*a, **kw):
            nonlocal call_count
            call_count += 1
            raise ConnectionResetError("reset by peer")

        srv.STATE.http_client.post = counting_post
        c.post("/chat", json={"messages": [{"role": "user", "content": "hi"}]})
        report("T17.2", "Generic exception breaks retry (1 call/backend)",
               call_count == 1, f"call_count={call_count}")


# ── T18: Circuit Breaker Integration ────────────────────────────────

def test_circuit_trip():
    """T18.1: Consecutive 5xx trips circuit to OPEN."""
    from fastapi.testclient import TestClient
    srv = fresh_app()
    with TestClient(srv.app) as c:
        srv.STATE.http_client.post = AsyncMock(
            return_value=make_mock_response(500, "error"))
        primary = srv.resolve_backend("deepseek-ai/DeepSeek-V3")
        primary.circuit.state = srv.CircuitState.CLOSED
        primary.circuit.consecutive_failures = 0
        c.post("/chat", json={"messages": [{"role": "user", "content": "hi"}]})
        c.post("/chat", json={"messages": [{"role": "user", "content": "hi"}]})
        report("T18.1", f"Failures → circuit={primary.circuit.state.value}",
               primary.circuit.state == srv.CircuitState.OPEN,
               f"failures={primary.circuit.consecutive_failures}")


def test_circuit_open_skips():
    """T18.2: OPEN circuit → skips backend."""
    from fastapi.testclient import TestClient
    srv = fresh_app()
    with TestClient(srv.app) as c:
        for b in srv.BACKENDS:
            if b.api_key:
                b.circuit.state = srv.CircuitState.OPEN
                b.circuit.opened_at = time.time()
        data = c.post("/chat", json={
            "messages": [{"role": "user", "content": "hi"}],
        }).json()
        report("T18.2", "All circuits OPEN → ok=False",
               data["ok"] is False, f"error={data.get('error', '')[:60]}")


def test_halfopen_success():
    """T18.3: HALF_OPEN + success → CLOSED."""
    from fastapi.testclient import TestClient
    srv = fresh_app()
    with TestClient(srv.app) as c:
        primary = srv.resolve_backend("deepseek-ai/DeepSeek-V3")
        primary.circuit.state = srv.CircuitState.HALF_OPEN
        srv.STATE.http_client.post = AsyncMock(return_value=ok_response())
        data = c.post("/chat", json={
            "messages": [{"role": "user", "content": "hi"}],
        }).json()
        report("T18.3", "HALF_OPEN + success → CLOSED",
               data["ok"] is True and primary.circuit.state == srv.CircuitState.CLOSED,
               f"state={primary.circuit.state.value}")


def test_halfopen_failure():
    """T18.4: HALF_OPEN + failure → back to OPEN."""
    from fastapi.testclient import TestClient
    srv = fresh_app()
    with TestClient(srv.app) as c:
        primary = srv.resolve_backend("deepseek-ai/DeepSeek-V3")
        primary.circuit.state = srv.CircuitState.HALF_OPEN
        primary.circuit.consecutive_failures = 3
        srv.STATE.http_client.post = AsyncMock(
            return_value=make_mock_response(500, "error"))
        c.post("/chat", json={"messages": [{"role": "user", "content": "hi"}]})
        report("T18.4", "HALF_OPEN + failure → OPEN",
               primary.circuit.state == srv.CircuitState.OPEN,
               f"state={primary.circuit.state.value}")


# ── T19: Backend Resolution & Fallback ──────────────────────────────

def test_no_backend():
    """T19.1: No available backend → immediate error."""
    from fastapi.testclient import TestClient
    srv = fresh_app()
    with TestClient(srv.app) as c:
        saved = [(b, b.api_key) for b in srv.BACKENDS]
        for b in srv.BACKENDS:
            b.api_key = ""
        try:
            data = c.post("/chat", json={
                "messages": [{"role": "user", "content": "hi"}],
            }).json()
            report("T19.1", "No backend → 'No available backend'",
                   data["ok"] is False and "No available" in data.get("error", ""),
                   f"error={data.get('error', '')}")
        finally:
            for b, key in saved:
                b.api_key = key


def test_fallback_succeeds():
    """T19.2: Primary fails → fallback succeeds (tenacious)."""
    from fastapi.testclient import TestClient
    srv = fresh_app()
    with TestClient(srv.app) as c:
        available = [b for b in srv.BACKENDS if b.api_key]
        if len(available) < 2:
            report("T19.2", "Fallback (SKIP: <2 backends)", True, "skipped")
            return

        async def failing_then_ok(*a, **kw):
            url = str(a[0]) if a else kw.get("url", "")
            if available[0].api_base in url:
                return make_mock_response(503, "down")
            return ok_response()

        srv.STATE.http_client.post = failing_then_ok
        data = c.post("/chat", json={
            "messages": [{"role": "user", "content": "hi"}],
            "tenacious": True,
        }).json()
        report("T19.2", "Primary 503 → fallback succeeds",
               data["ok"] is True and data["retries"] >= 1,
               f"backend={data.get('backend', '')} retries={data['retries']}")


def test_all_backends_fail():
    """T19.3: All backends fail → error with retry count."""
    from fastapi.testclient import TestClient
    srv = fresh_app()
    with TestClient(srv.app) as c:
        srv.STATE.http_client.post = AsyncMock(
            return_value=make_mock_response(503, "down"))
        data = c.post("/chat", json={
            "messages": [{"role": "user", "content": "hi"}],
            "tenacious": True,
        }).json()
        report("T19.3", "All backends 503 → ok=False",
               data["ok"] is False and data["retries"] > 0,
               f"retries={data['retries']}")


# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    _sleep_patch.start()

    print("── T13: 429 Rate Limiting ──")
    test_429_single()
    test_429_retry_after_header()
    test_429_x_ratelimit_reset()
    test_429_ratelimit_reset()
    test_429_no_retry_header()
    test_429_dynamic_shrink()
    test_429_semaphore_restore()

    print("── T14: 5xx Server Errors ──")
    test_5xx("T14.1", 503)
    test_5xx("T14.2", 500)
    test_5xx("T14.3", 502)

    print("── T15: 4xx Client Errors ──")
    test_4xx("T15.1", 401, {"error": "invalid api key"})
    test_4xx("T15.2", 422, {"detail": "invalid model"})

    print("── T16: Timeout Errors ──")
    test_timeout("T16.1", httpx.ReadTimeout, "ReadTimeout")
    test_timeout("T16.2", httpx.ConnectTimeout, "ConnectTimeout")

    print("── T17: Connection Errors ──")
    test_connection_error()
    test_connection_error_breaks_loop()

    print("── T18: Circuit Breaker Integration ──")
    test_circuit_trip()
    test_circuit_open_skips()
    test_halfopen_success()
    test_halfopen_failure()

    print("── T19: Backend Resolution & Fallback ──")
    test_no_backend()
    test_fallback_succeeds()
    test_all_backends_fail()

    # Import and run extended tests
    from test_error_simulation_ext import run_extended
    ext_pass, ext_fail = run_extended()
    PASS += ext_pass
    FAIL += ext_fail

    _sleep_patch.stop()

    print()
    print(f"═══ Error Simulation: {PASS}/{PASS + FAIL} passed, {FAIL} failed ═══")
    sys.exit(0 if FAIL == 0 else 1)
