#!/usr/bin/env python3
"""Memory storage operations for distill skill.

Provides storage of Q&A pairs to the memory system with retry logic
and rate limiting.  After storing, stamps `taxonomy_tags` directly on
the ArangoDB document so bridge-based readiness queries work.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any, Dict, List

import httpx

from .utils import (
    log,
    memory_limiter,
    with_retries,
)

# Bridge tags that should be promoted to taxonomy_tags for graph traversal
BRIDGE_TAGS = {"Precision", "Resilience", "Fragility", "Corruption", "Loyalty", "Stealth"}
MEMORY_SOCKET = os.environ.get("MEMORY_SOCKET", "/run/user/1000/embry/memory.sock")
MEMORY_TCP_BASE = os.environ.get("MEMORY_API_BASE", "http://127.0.0.1:8601")


def _memory_client() -> httpx.Client:
    """Create a memory daemon client, preferring the Unix socket."""
    if os.path.exists(MEMORY_SOCKET):
        transport = httpx.HTTPTransport(uds=MEMORY_SOCKET)
        return httpx.Client(transport=transport, base_url="http://localhost", timeout=httpx.Timeout(30.0, connect=2.0))
    return httpx.Client(base_url=MEMORY_TCP_BASE, timeout=httpx.Timeout(30.0, connect=2.0))


def _lesson_document(problem: str, solution: str, scope: str, tags: List[str] | None) -> Dict[str, Any]:
    """Build the daemon-owned lesson payload."""
    document: Dict[str, Any] = {
        "_key": "doc2qra-" + hashlib.sha256(f"{scope}\0{problem}".encode("utf-8")).hexdigest()[:32],
        "problem": problem,
        "solution": solution,
        "scope": scope,
    }
    if tags:
        document["tags"] = tags
        bridge_tags = [tag for tag in tags if tag in BRIDGE_TAGS]
        if bridge_tags:
            document["taxonomy_tags"] = bridge_tags
    return document


def _stamp_taxonomy_tags(problem: str, scope: str, bridge_tags: List[str]) -> None:
    """Deprecated compatibility hook.

    Bridge tags are now included in the daemon `/store` payload as
    `taxonomy_tags`, avoiding `memory-agent` subprocess calls.
    """
    return None


def store_qa(
    problem: str,
    solution: str,
    scope: str,
    tags: List[str] = None,
) -> bool:
    """Store Q&A pair via the memory daemon with retry logic.

    After successful storage, stamps bridge tags onto the document's
    `taxonomy_tags` field for graph traversal and readiness queries.

    Args:
        problem: The question/problem statement
        solution: The answer/solution
        scope: Memory scope to store in
        tags: Optional list of tags

    Returns:
        True if stored successfully, False otherwise
    """
    @with_retries(max_attempts=3, base_delay=0.5)
    def _store_with_retry() -> bool:
        memory_limiter.acquire()
        payload = {
            "collection": "lessons",
            "documents": [_lesson_document(problem, solution, scope, tags)],
        }
        with _memory_client() as client:
            response = client.post("/upsert", json=payload)
            response.raise_for_status()
        return True

    try:
        return _store_with_retry()
    except Exception as e:
        log(f"Failed to store after retries: {e}", style="red")
        return False
