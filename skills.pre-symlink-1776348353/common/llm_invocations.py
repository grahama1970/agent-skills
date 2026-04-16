"""Unified agent invocation logger → ArangoDB llm_invocations collection.

Every agent turn/response goes here: code-runner rounds, scillm calls,
dogpile syntheses, orchestrate dispatches, project agent decisions.

Usage:
    from llm_invocations import log_invocation

    log_invocation(
        agent="code-runner",
        session_key="orch-abc123",
        round=2,
        role="assistant",
        turn_index=5,
        input="Fix the auth timeout...",
        output="### FILE: src/auth.py\\n...",
        outcome="success",
        duration_ms=4200,
        model="gpt-5.3-codex",
        score=0.85,
        tags=["task:fix-auth", "strategy:direct_fix"],
    )

Query and prune operations use /memory recall and /ops-arango respectively.
No bespoke AQL in skill code.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import httpx
from loguru import logger

MEMORY_SOCKET = "/run/user/1000/embry/memory.sock"
COLLECTION = "llm_invocations"


def _post(endpoint: str, payload: dict, timeout: float = 10.0) -> dict:
    """POST to memory daemon via Unix socket."""
    transport = httpx.HTTPTransport(uds=MEMORY_SOCKET)
    with httpx.Client(transport=transport, timeout=timeout) as client:
        resp = client.post(f"http://localhost{endpoint}", json=payload)
        resp.raise_for_status()
        return resp.json()


def log_invocation(
    *,
    agent: str,
    session_key: str = "",
    round: int = 1,
    role: str = "assistant",
    turn_index: int = 0,
    input: str = "",
    output: str = "",
    outcome: str = "success",
    duration_ms: int = 0,
    model: str = "",
    score: Optional[float] = None,
    error: Optional[str] = None,
    tags: Optional[list[str]] = None,
    parent_session: str = "",
    metadata: Optional[dict] = None,
    scope: str = "",
) -> Optional[str]:
    """Log a single agent turn to llm_invocations.

    Returns the document _key on success, None on failure.
    Non-blocking: swallows connection errors so the caller's
    main loop is never interrupted by memory daemon issues.
    """
    doc = {
        "agent": agent,
        "session_key": session_key,
        "round": round,
        "role": role,
        "turn_index": turn_index,
        "input": input[:4000] if input else "",
        "output": output[:4000] if output else "",
        "outcome": outcome,
        "duration_ms": duration_ms,
        "model": model,
        "score": score,
        "error": error,
        "tags": tags or [],
        "parent_session": parent_session,
        "metadata": metadata or {},
        "scope": scope,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        result = _post("/store", {"collection": COLLECTION, "document": doc})
        return result.get("_key")
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, OSError) as e:
        logger.debug("llm_invocations log failed (non-fatal): {}", e)
        return None
