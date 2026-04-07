"""
Extended error simulation tests for chutes-call (T20-T25).

Imported by test_error_simulation.py — not run standalone.
Tests: tenacious mode, response edge cases, transient recovery,
usage tracking, error message quality, batch error handling.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
from unittest.mock import AsyncMock

import httpx

SKILL_DIR = sys.argv[1] if len(sys.argv) > 1 else "."
if SKILL_DIR not in sys.path:
    sys.path.insert(0, SKILL_DIR)

PASS = 0
FAIL = 0


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
    if isinstance(body, dict):
        content = json.dumps(body).encode()
    else:
        content = body.encode() if isinstance(body, str) else body
    return httpx.Response(
        status_code=status_code, content=content,
        headers=headers or {},
        request=httpx.Request("POST", "https://fake.api/chat/completions"),
    )


def ok_response(tokens_in: int = 10, tokens_out: int = 20) -> httpx.Response:
    return make_mock_response(200, {
        "choices": [{"message": {"content": "Hello"}}],
        "model": "test", "usage": {"prompt_tokens": tokens_in, "completion_tokens": tokens_out},
    })


def fresh_app():
    import server as srv
    importlib.reload(srv)
    return srv


# ── T20: Tenacious Mode ─────────────────────────────────────────────

def test_tenacious_more_retries():
    """T20.1: Tenacious → more attempts than normal."""
    from fastapi.testclient import TestClient
    srv = fresh_app()
    with TestClient(srv.app) as c:
        call_count = 0

        async def counting_fail(*a, **kw):
            nonlocal call_count
            call_count += 1
            return make_mock_response(503, "down")

        # Non-tenacious
        srv.STATE.http_client.post = counting_fail
        call_count = 0
        c.post("/chat", json={"messages": [{"role": "user", "content": "hi"}], "tenacious": False})
        normal = call_count

        # Reset circuits for tenacious run
        for b in srv.BACKENDS:
            b.circuit.state = srv.CircuitState.CLOSED
            b.circuit.consecutive_failures = 0
        call_count = 0
        srv.STATE.http_client.post = counting_fail
        c.post("/chat", json={"messages": [{"role": "user", "content": "hi"}], "tenacious": True})
        tenacious = call_count

        report("T20.1", f"Tenacious retries more: normal={normal} tenacious={tenacious}",
               tenacious > normal, f"normal={normal} tenacious={tenacious}")


# ── T21: Response Edge Cases ─────────────────────────────────────────

def test_200_empty_choices():
    """T21.1: 200 with empty choices → ok=False (IndexError on choices[0])."""
    from fastapi.testclient import TestClient
    srv = fresh_app()
    with TestClient(srv.app) as c:
        srv.STATE.http_client.post = AsyncMock(return_value=make_mock_response(200, {
            "choices": [], "model": "test",
            "usage": {"prompt_tokens": 5, "completion_tokens": 0},
        }))
        data = c.post("/chat", json={"messages": [{"role": "user", "content": "hi"}]}).json()
        # Server does choices[0] which raises IndexError on empty list → ok=False
        report("T21.1", "200 empty choices → ok=False (IndexError)",
               data["ok"] is False, f"ok={data['ok']}")


def test_200_missing_usage():
    """T21.2: 200 with no usage → ok=True, tokens=0."""
    from fastapi.testclient import TestClient
    srv = fresh_app()
    with TestClient(srv.app) as c:
        srv.STATE.http_client.post = AsyncMock(return_value=make_mock_response(200, {
            "choices": [{"message": {"content": "hello"}}], "model": "test",
        }))
        data = c.post("/chat", json={"messages": [{"role": "user", "content": "hi"}]}).json()
        report("T21.2", "200 no usage → tokens_in=0",
               data["ok"] is True and data["tokens_in"] == 0,
               f"tokens_in={data['tokens_in']}")


# ── T22: Transient Failures Recover ──────────────────────────────────

def _test_transient_recover(test_id: str, desc: str, first_response):
    """Generic: first call fails, second succeeds → ok=True, retries=1."""
    from fastapi.testclient import TestClient
    srv = fresh_app()
    with TestClient(srv.app) as c:
        call_count = 0

        async def fail_then_ok(*a, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                if callable(first_response):
                    return first_response()
                raise first_response
            return ok_response()

        srv.STATE.http_client.post = fail_then_ok
        data = c.post("/chat", json={"messages": [{"role": "user", "content": "hi"}]}).json()
        report(test_id, desc,
               data["ok"] is True and data["retries"] == 1,
               f"ok={data['ok']} retries={data['retries']}")


def test_429_then_success():
    _test_transient_recover("T22.1", "429 then 200 → recovers",
                            lambda: make_mock_response(429, "slow", {"retry-after": "0"}))


def test_503_then_success():
    _test_transient_recover("T22.2", "503 then 200 → recovers",
                            lambda: make_mock_response(503, "down"))


def test_timeout_then_success():
    _test_transient_recover("T22.3", "Timeout then 200 → recovers",
                            httpx.ReadTimeout("timed out"))


# ── T23: Usage & Error Tracking ──────────────────────────────────────

def test_error_tracking():
    """T23.1: Errors increment total_errors."""
    from fastapi.testclient import TestClient
    srv = fresh_app()
    with TestClient(srv.app) as c:
        srv.STATE.total_errors = 0
        srv.STATE.http_client.post = AsyncMock(return_value=make_mock_response(503, "down"))
        c.post("/chat", json={"messages": [{"role": "user", "content": "hi"}]})
        report("T23.1", "Error increments total_errors",
               srv.STATE.total_errors >= 1, f"total_errors={srv.STATE.total_errors}")


def test_error_caller_stats():
    """T23.2: Caller stats track errors."""
    from fastapi.testclient import TestClient
    srv = fresh_app()
    with TestClient(srv.app) as c:
        srv.STATE.caller_stats = {}
        srv.STATE.http_client.post = AsyncMock(return_value=make_mock_response(503, "down"))
        c.post("/chat", json={"messages": [{"role": "user", "content": "hi"}], "caller": "cx"})
        stats = srv.STATE.caller_stats.get("cx", {})
        report("T23.2", "Caller stats show error",
               stats.get("errors", 0) >= 1, f"stats={stats}")


def test_success_tracking():
    """T23.3: Success increments requests and tokens."""
    from fastapi.testclient import TestClient
    srv = fresh_app()
    with TestClient(srv.app) as c:
        srv.STATE.total_requests = 0
        srv.STATE.total_tokens_in = 0
        srv.STATE.http_client.post = AsyncMock(return_value=ok_response(50, 100))
        c.post("/chat", json={"messages": [{"role": "user", "content": "hi"}]})
        report("T23.3", "Success increments tokens",
               srv.STATE.total_requests >= 1 and srv.STATE.total_tokens_in >= 50,
               f"reqs={srv.STATE.total_requests} in={srv.STATE.total_tokens_in}")


def test_retry_count_accurate():
    """T23.4: Retry count matches attempts."""
    from fastapi.testclient import TestClient
    srv = fresh_app()
    with TestClient(srv.app) as c:
        srv.STATE.http_client.post = AsyncMock(return_value=make_mock_response(503, "down"))
        data = c.post("/chat", json={
            "messages": [{"role": "user", "content": "hi"}], "tenacious": False,
        }).json()
        report("T23.4", "Retry count = 2 (non-tenacious)",
               data["retries"] == 2, f"retries={data['retries']}")


# ── T24: Error Message Quality ───────────────────────────────────────

def test_429_identifies_backend():
    """T24.1: 429 error identifies backend name."""
    from fastapi.testclient import TestClient
    srv = fresh_app()
    with TestClient(srv.app) as c:
        srv.STATE.http_client.post = AsyncMock(return_value=make_mock_response(
            429, "limited", {"retry-after": "0"}))
        data = c.post("/chat", json={"messages": [{"role": "user", "content": "hi"}]}).json()
        err = data.get("error", "")
        has_backend = any(b.key in err for b in srv.BACKENDS if b.api_key)
        report("T24.1", "429 error identifies backend",
               has_backend, f"error={err[:80]}")


def test_5xx_includes_code():
    """T24.2: 5xx error includes status code."""
    from fastapi.testclient import TestClient
    srv = fresh_app()
    with TestClient(srv.app) as c:
        srv.STATE.http_client.post = AsyncMock(return_value=make_mock_response(502, "Bad Gateway"))
        data = c.post("/chat", json={"messages": [{"role": "user", "content": "hi"}]}).json()
        report("T24.2", "5xx error includes status code",
               "502" in data.get("error", ""), f"error={data.get('error', '')[:60]}")


def test_elapsed_always_present():
    """T24.3: elapsed_s >= 0 on errors (may be 0.0 with patched sleep)."""
    from fastapi.testclient import TestClient
    srv = fresh_app()
    with TestClient(srv.app) as c:
        srv.STATE.http_client.post = AsyncMock(return_value=make_mock_response(503, "down"))
        data = c.post("/chat", json={"messages": [{"role": "user", "content": "hi"}]}).json()
        report("T24.3", "elapsed_s >= 0 on error",
               "elapsed_s" in data and data["elapsed_s"] >= 0,
               f"elapsed_s={data['elapsed_s']}")


def test_circuit_state_in_response():
    """T24.4: Response includes circuit_state field."""
    from fastapi.testclient import TestClient
    srv = fresh_app()
    with TestClient(srv.app) as c:
        srv.STATE.http_client.post = AsyncMock(return_value=ok_response())
        data = c.post("/chat", json={"messages": [{"role": "user", "content": "hi"}]}).json()
        report("T24.4", "Response has circuit_state",
               "circuit_state" in data and data["circuit_state"] in ("CLOSED", "OPEN", "HALF_OPEN"),
               f"circuit_state={data.get('circuit_state')}")


# ── T25: Batch Error Handling ────────────────────────────────────────

def test_batch_mixed_errors():
    """T25.1: Batch with mixed 200s and 503s."""
    from fastapi.testclient import TestClient
    srv = fresh_app()
    with TestClient(srv.app) as c:
        # Use per-request mock: items 0,1 succeed, items 2,3 always fail.
        # Server calls: http_client.post(url, json=payload, headers=..., timeout=...)
        async def mixed_by_content(*a, **kw):
            payload = kw.get("json", {})
            msgs = payload.get("messages", [])
            content = msgs[0].get("content", "") if msgs else ""
            if "msg 2" in content or "msg 3" in content:
                return make_mock_response(503, "down")
            return ok_response()

        srv.STATE.http_client.post = mixed_by_content
        resp = c.post("/batch", json={
            "requests": [{"messages": [{"role": "user", "content": f"msg {i}"}]} for i in range(4)],
            "stream": False,
        })
        results = resp.json()
        oks = sum(1 for r in results if r["ok"])
        fails = sum(1 for r in results if not r["ok"])
        report("T25.1", f"Batch mixed: {oks} ok, {fails} errors/4",
               oks > 0 and fails > 0, f"oks={oks} fails={fails}")


def test_batch_all_fail():
    """T25.2: Batch where all items fail."""
    from fastapi.testclient import TestClient
    srv = fresh_app()
    with TestClient(srv.app) as c:
        srv.STATE.http_client.post = AsyncMock(return_value=make_mock_response(503, "down"))
        resp = c.post("/batch", json={
            "requests": [{"messages": [{"role": "user", "content": f"msg {i}"}]} for i in range(3)],
            "stream": False,
        })
        results = resp.json()
        all_failed = all(not r["ok"] for r in results)
        report("T25.2", "Batch all fail → all ok=False",
               all_failed and len(results) == 3,
               f"results={len(results)} all_failed={all_failed}")


def test_batch_all_succeed():
    """T25.3: Batch where all items succeed."""
    from fastapi.testclient import TestClient
    srv = fresh_app()
    with TestClient(srv.app) as c:
        srv.STATE.http_client.post = AsyncMock(return_value=ok_response())
        resp = c.post("/batch", json={
            "requests": [{"messages": [{"role": "user", "content": f"msg {i}"}]} for i in range(3)],
            "stream": False,
        })
        results = resp.json()
        all_ok = all(r["ok"] for r in results)
        report("T25.3", "Batch all succeed → all ok=True",
               all_ok and len(results) == 3,
               f"results={len(results)} all_ok={all_ok}")


# ── T26: ops-chutes Diagnostic Integration ──────────────────────────
# When chutes-call becomes unreliable, agents invoke /ops-chutes to diagnose.
# These tests verify the gateway exposes enough data for ops-chutes diagnosis.

def test_health_shows_circuit_open():
    """T26.1: /health shows circuit OPEN after persistent errors."""
    from fastapi.testclient import TestClient
    srv = fresh_app()
    with TestClient(srv.app) as c:
        srv.STATE.http_client.post = AsyncMock(return_value=make_mock_response(503, "down"))
        # Send enough requests to trip circuit breaker
        for _ in range(4):
            c.post("/chat", json={"messages": [{"role": "user", "content": "hi"}]})
        health = c.get("/health").json()
        chutes_circuit = health["backends"].get("chutes", {}).get("circuit_state", "")
        report("T26.1", "/health shows circuit OPEN after errors",
               chutes_circuit == "OPEN", f"circuit_state={chutes_circuit}")


def test_queue_error_rate_nonzero():
    """T26.2: /queue shows error_rate > 0 after failures (ops-chutes reads this)."""
    from fastapi.testclient import TestClient
    srv = fresh_app()
    with TestClient(srv.app) as c:
        srv.STATE.http_client.post = AsyncMock(return_value=make_mock_response(503, "down"))
        c.post("/chat", json={"messages": [{"role": "user", "content": "hi"}]})
        queue = c.get("/queue").json()
        report("T26.2", "/queue error_rate > 0 after failure",
               queue["total_errors"] >= 1 and queue["error_rate"] > 0,
               f"errors={queue['total_errors']} rate={queue['error_rate']}")


def test_usage_tracks_errors():
    """T26.3: /usage errors field increments (agent checks before calling ops-chutes)."""
    from fastapi.testclient import TestClient
    srv = fresh_app()
    with TestClient(srv.app) as c:
        srv.STATE.http_client.post = AsyncMock(return_value=make_mock_response(429, "limited"))
        c.post("/chat", json={"messages": [{"role": "user", "content": "hi"}]})
        usage = c.get("/usage").json()
        report("T26.3", "/usage errors > 0 after 429",
               usage["errors"] >= 1, f"errors={usage['errors']}")


def test_health_semaphore_shrink_visible():
    """T26.4: /health shows reduced semaphore after 429 storm (ops-chutes slot check)."""
    from fastapi.testclient import TestClient
    srv = fresh_app()
    with TestClient(srv.app) as c:
        srv.STATE.http_client.post = AsyncMock(return_value=make_mock_response(
            429, "limited", {"retry-after": "0"}))
        for _ in range(4):
            c.post("/chat", json={"messages": [{"role": "user", "content": "hi"}]})
        health = c.get("/health").json()
        report("T26.4", "/health semaphore shrunk after 429 storm",
               health["semaphore_size"] < 5,
               f"semaphore_size={health['semaphore_size']}")


def test_usage_reset_clears_errors():
    """T26.5: DELETE /usage resets error counters (agent clears after ops-chutes fix)."""
    from fastapi.testclient import TestClient
    srv = fresh_app()
    with TestClient(srv.app) as c:
        srv.STATE.http_client.post = AsyncMock(return_value=make_mock_response(503, "down"))
        c.post("/chat", json={"messages": [{"role": "user", "content": "hi"}]})
        c.delete("/usage")
        usage = c.get("/usage").json()
        report("T26.5", "DELETE /usage resets error counters",
               usage["errors"] == 0 and usage["requests"] == 0,
               f"errors={usage['errors']} requests={usage['requests']}")


def test_queue_caller_stats_for_diagnosis():
    """T26.6: /queue caller stats let ops-chutes identify which callers are failing."""
    from fastapi.testclient import TestClient
    srv = fresh_app()
    with TestClient(srv.app) as c:
        srv.STATE.http_client.post = AsyncMock(return_value=make_mock_response(503, "down"))
        c.post("/chat", json={"messages": [{"role": "user", "content": "hi"}], "caller": "learn-datalake"})
        c.post("/chat", json={"messages": [{"role": "user", "content": "hi"}], "caller": "scillm"})
        queue = c.get("/queue").json()
        callers = queue.get("callers", {})
        has_both = "learn-datalake" in callers and "scillm" in callers
        report("T26.6", "/queue tracks per-caller stats for diagnosis",
               has_both, f"callers={list(callers.keys())}")


# ═══════════════════════════════════════════════════════════════════════

def run_extended() -> tuple[int, int]:
    """Run all extended tests, return (pass_count, fail_count)."""
    global PASS, FAIL
    PASS = 0
    FAIL = 0

    print("── T20: Tenacious Mode ──")
    test_tenacious_more_retries()

    print("── T21: Response Edge Cases ──")
    test_200_empty_choices()
    test_200_missing_usage()

    print("── T22: Transient Failures Recover ──")
    test_429_then_success()
    test_503_then_success()
    test_timeout_then_success()

    print("── T23: Usage & Error Tracking ──")
    test_error_tracking()
    test_error_caller_stats()
    test_success_tracking()
    test_retry_count_accurate()

    print("── T24: Error Message Quality ──")
    test_429_identifies_backend()
    test_5xx_includes_code()
    test_elapsed_always_present()
    test_circuit_state_in_response()

    print("── T25: Batch Error Handling ──")
    test_batch_mixed_errors()
    test_batch_all_fail()
    test_batch_all_succeed()

    print("── T26: ops-chutes Diagnostic Integration ──")
    test_health_shows_circuit_open()
    test_queue_error_rate_nonzero()
    test_usage_tracks_errors()
    test_health_semaphore_shrink_visible()
    test_usage_reset_clears_errors()
    test_queue_caller_stats_for_diagnosis()

    return PASS, FAIL
