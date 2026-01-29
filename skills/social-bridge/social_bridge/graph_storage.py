"""
Social Bridge Graph Storage Module

Handles persistence to graph-memory for knowledge graph integration.
"""

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Callable, Optional

from social_bridge.config import MEMORY_SCOPE, MEMORY_ROOT
from social_bridge.utils import SocialPost, extract_security_tags, with_retries

logger = logging.getLogger("social-bridge.storage")


def get_memory_skill_path() -> Path | None:
    """Get the path to the memory skill run.sh.

    Returns:
        Path to run.sh or None if not found
    """
    # Try configured MEMORY_ROOT and common locations
    candidates = [
        Path(MEMORY_ROOT) / "run.sh",
        Path(MEMORY_ROOT) / "memory" / "run.sh",
        Path(__file__).parent.parent / "memory" / "run.sh",
    ]
    for candidate in candidates:
        if candidate and candidate.exists():
            # Warn if not executable but still return the path
            if not os.access(candidate, os.X_OK):
                logger.warning(f"Memory script not executable: {candidate}")
            return candidate

    # Memory skill not found
    return None


def check_memory_available() -> bool:
    """Check if the memory skill is available.

    Returns:
        True if memory skill exists
    """
    return get_memory_skill_path() is not None


def check_memory_service() -> tuple[bool, str]:
    """Check if the memory service is connected.

    Returns:
        Tuple of (is_connected, status_message)
    """
    memory_skill = get_memory_skill_path()
    if not memory_skill:
        return False, "Memory skill not found"

    try:
        result = subprocess.run(
            [str(memory_skill), "status"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(memory_skill.parent),
        )
        if result.returncode == 0:
            return True, "Connected"
        return False, result.stderr[:100] if result.stderr else "Unknown error"
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

    # Build command
    cmd = [
        str(memory_skill),
        "learn",
        "--problem", problem,
        "--solution", solution,
        "--scope", MEMORY_SCOPE,
    ]

    # Add tags
    for tag in all_tags:
        cmd.extend(["--tag", tag])

    @with_retries
    def _execute_learn() -> dict[str, Any]:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(memory_skill.parent),
        )
        if result.returncode != 0:
            raise RuntimeError(f"Memory learn failed: {result.stderr[:200]}")
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
    memory_skill = get_memory_skill_path()
    if not memory_skill:
        logger.debug("Memory skill not found, returning empty results")
        return []

    cmd = [
        str(memory_skill),
        "recall",
        "--q", query,
        "--scope", MEMORY_SCOPE,
        "--k", str(k),
    ]

    @with_retries
    def _execute_recall() -> list[dict[str, Any]]:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(memory_skill.parent),
        )
        if result.returncode != 0:
            raise RuntimeError(f"Memory recall failed: {result.stderr[:100]}")
        try:
            data = json.loads(result.stdout)
            return data.get("items", [])
        except json.JSONDecodeError:
            return []

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
