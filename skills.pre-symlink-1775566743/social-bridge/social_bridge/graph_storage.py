"""
Social Bridge Graph Storage Module

Handles persistence to graph-memory for knowledge graph integration.
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Callable, Optional

from loguru import logger

from social_bridge.config import MEMORY_SCOPE, MEMORY_ROOT
from social_bridge.utils import SocialPost, extract_security_tags, with_retries


_MEMORY_SOCK = "/run/user/1000/embry/memory.sock"


def _memory_post(endpoint: str, body: dict, timeout: float = 30.0):
    """POST to embry-memory daemon via Unix socket."""
    import httpx
    transport = httpx.HTTPTransport(uds=_MEMORY_SOCK)
    with httpx.Client(transport=transport, base_url="http://localhost", timeout=timeout) as client:
        return client.post(endpoint, json=body)


def get_memory_skill_path() -> Path | None:
    """Check if embry-memory daemon socket exists."""
    sock = Path(_MEMORY_SOCK)
    return sock if sock.exists() else None


def check_memory_available() -> bool:
    """Check if the memory daemon socket is available."""
    return Path(_MEMORY_SOCK).exists()


def check_memory_service() -> tuple[bool, str]:
    """Check if the memory service is connected via Unix socket."""
    try:
        import httpx
        transport = httpx.HTTPTransport(uds=_MEMORY_SOCK)
        with httpx.Client(transport=transport, base_url="http://localhost", timeout=10.0) as client:
            resp = client.get("/health")
            if resp.status_code == 200:
                return True, "Connected"
            return False, f"HTTP {resp.status_code}"
    except Exception as e:
        return False, str(e)


def persist_to_memory(
    post: SocialPost,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Persist a social post to graph-memory.

    Uses the memory skill's learn command to store posts as lessons.

    Args:
        post: The SocialPost to persist
        tags: Optional additional tags

    Returns:
        Dict with 'stored' (bool), 'tags' (list), and optionally 'error' (str)
    """
    memory_skill = get_memory_skill_path()
    if not memory_skill:
        logger.warning("Memory skill not found, cannot persist post")
        return {"error": "memory skill not found", "stored": False}

    # Auto-extract security tags from content
    auto_tags = extract_security_tags(post.content)
    all_tags = list(set((tags or []) + auto_tags + [post.platform, f"source:{post.source}"]))

    # Format problem as a searchable identifier
    problem = f"[{post.platform.upper()}] @{post.source}: {post.content[:100]}..."

    # Format solution with full content and metadata
    solution = json.dumps({
        "content": post.content,
        "url": post.url,
        "author": post.author,
        "timestamp": post.timestamp.isoformat(),
        "platform": post.platform,
        "source": post.source,
        "metadata": post.metadata,
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


def persist_posts(
    posts: list[SocialPost],
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> tuple[int, int]:
    """Persist multiple posts to memory.

    Args:
        posts: List of SocialPost objects
        on_progress: Optional callback(current, total) for progress updates

    Returns:
        Tuple of (stored_count, error_count)
    """
    stored = 0
    errors = 0

    for i, post in enumerate(posts):
        result = persist_to_memory(post)
        if result.get("stored"):
            stored += 1
        else:
            errors += 1

        if on_progress:
            on_progress(i + 1, len(posts))

    return stored, errors


def search_memory(query: str, k: int = 10) -> list[dict[str, Any]]:
    """Search memory for stored social intel.

    Args:
        query: Search query
        k: Number of results to return

    Returns:
        List of matching items from graph-memory
    """
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


def get_memory_scope() -> str:
    """Get the memory scope used for social intel storage.

    Returns:
        The memory scope string
    """
    return MEMORY_SCOPE
