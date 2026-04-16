#!/usr/bin/env python3
"""
Discord Operations - Graph Memory Persistence

Persists keyword matches to graph-memory for knowledge graph integration.
"""

import os
import json
import subprocess
from pathlib import Path
from typing import Any

from discord_ops.config import (
    MATCHES_LOG,
    MEMORY_SCOPE,
    logger,
)
from discord_ops.keyword_matcher import KeywordMatch, create_match_tags
from discord_ops.utils import with_retries

__all__ = [
    "get_memory_skill_path",
    "persist_match_to_memory",
    "search_memory",
    "check_memory_status",
    "log_match",
    "get_local_matches_count",
]


# =============================================================================
# MEMORY SKILL PATH
# =============================================================================

_MEMORY_SOCK = "/run/user/1000/embry/memory.sock"


def _memory_post(endpoint: str, body: dict, timeout: float = 30.0) -> "httpx.Response":
    """POST to embry-memory daemon via Unix socket."""
    import httpx
    transport = httpx.HTTPTransport(uds=_MEMORY_SOCK)
    with httpx.Client(transport=transport, base_url="http://localhost", timeout=timeout) as client:
        return client.post(endpoint, json=body)


def get_memory_skill_path() -> Path:
    """Check if embry-memory daemon socket exists."""
    return Path(_MEMORY_SOCK)


# =============================================================================
# PERSISTENCE FUNCTIONS
# =============================================================================

def persist_match_to_memory(match: KeywordMatch) -> dict[str, Any]:
    """Persist a keyword match to graph-memory via Unix socket.

    Args:
        match: The keyword match to persist

    Returns:
        Result dict with 'stored' status and optionally 'error' or 'tags'
    """
    all_tags = create_match_tags(match)
    problem = f"[DISCORD] #{match.channel_name}: {match.content[:100]}..."
    solution = json.dumps({
        "content": match.content,
        "url": match.message_url,
        "author": match.author,
        "timestamp": match.timestamp,
        "platform": "discord",
        "guild": match.guild_name,
        "channel": match.channel_name,
        "matched_keywords": match.matched_keywords,
    }, indent=2)

    @with_retries
    def _execute_learn() -> dict[str, Any]:
        resp = _memory_post("/learn", {
            "problem": problem,
            "solution": solution,
            "scope": MEMORY_SCOPE,
            "tags": all_tags,
        })
        resp.raise_for_status()
        return {"stored": True, "tags": all_tags}

    try:
        return _execute_learn()
    except Exception as e:
        logger.error(f"Failed to persist to memory after retries: {e}")
        return {"stored": False, "error": str(e)}


def search_memory(query: str, k: int = 10) -> list[dict[str, Any]]:
    """Search memory for stored Discord matches via Unix socket."""
    @with_retries
    def _execute_recall() -> list[dict[str, Any]]:
        resp = _memory_post("/recall", {"q": query, "scope": MEMORY_SCOPE, "k": k})
        resp.raise_for_status()
        return resp.json().get("items", [])

    try:
        return _execute_recall()
    except Exception as e:
        logger.warning(f"Memory search failed after retries: {e}")
        return []


def check_memory_status() -> dict[str, Any]:
    """Check status of the memory integration via Unix socket."""
    status = {
        "available": Path(_MEMORY_SOCK).exists(),
        "path": _MEMORY_SOCK,
        "connected": False,
        "scope": MEMORY_SCOPE,
        "error": None,
    }

    if not status["available"]:
        status["error"] = "Memory socket not found"
        return status

    try:
        import httpx
        transport = httpx.HTTPTransport(uds=_MEMORY_SOCK)
        with httpx.Client(transport=transport, base_url="http://localhost", timeout=10.0) as client:
            resp = client.get("/health")
            if resp.status_code == 200:
                status["connected"] = True
            else:
                status["error"] = f"HTTP {resp.status_code}"
    except Exception as e:
        status["error"] = str(e)

    return status


# =============================================================================
# LOCAL LOGGING
# =============================================================================

def log_match(match: KeywordMatch, persist: bool = True) -> dict[str, Any]:
    """Append match to log file and optionally persist to memory.

    Args:
        match: The keyword match to log
        persist: If True, also persist to graph-memory

    Returns:
        Result dict with 'logged' and optionally 'memory' status
    """
    result = {"logged": True}

    # Write to local log file
    with open(MATCHES_LOG, "a") as f:
        f.write(json.dumps(match.to_dict()) + "\n")

    # Persist to memory if enabled
    if persist:
        memory_result = persist_match_to_memory(match)
        result["memory"] = memory_result

    return result


def get_local_matches_count() -> int:
    """Get count of matches in local log file."""
    if MATCHES_LOG.exists():
        lines = MATCHES_LOG.read_text().strip().split("\n")
        return len([l for l in lines if l.strip()])
    return 0
