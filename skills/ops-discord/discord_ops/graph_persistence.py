#!/usr/bin/env python3
"""
Discord Operations - Graph Memory Persistence

Persists keyword matches to graph-memory for knowledge graph integration.
"""

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

def get_memory_skill_path() -> Path:
    """Get path to the memory skill run.sh.

    Goes up from discord_ops package -> ops-discord skill -> skills dir -> memory skill
    """
    return Path(__file__).parent.parent.parent / "memory" / "run.sh"


# =============================================================================
# PERSISTENCE FUNCTIONS
# =============================================================================

def persist_match_to_memory(match: KeywordMatch) -> dict[str, Any]:
    """Persist a keyword match to graph-memory.

    Uses the memory skill's learn command to store matches as lessons.
    Includes retry logic for transient failures.

    Args:
        match: The keyword match to persist

    Returns:
        Result dict with 'stored' status and optionally 'error' or 'tags'
    """
    memory_skill = get_memory_skill_path()

    if not memory_skill.exists():
        logger.warning("Memory skill not found, cannot persist match")
        return {"error": "memory skill not found", "stored": False}

    # Extract semantic tags
    all_tags = create_match_tags(match)

    # Format problem as a searchable identifier
    problem = f"[DISCORD] #{match.channel_name}: {match.content[:100]}..."

    # Format solution with full content and metadata
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


def search_memory(query: str, k: int = 10) -> list[dict[str, Any]]:
    """Search memory for stored Discord matches.

    Args:
        query: Search query string
        k: Number of results to return

    Returns:
        List of matching items from graph-memory
    """
    memory_skill = get_memory_skill_path()

    if not memory_skill.exists():
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


def check_memory_status() -> dict[str, Any]:
    """Check status of the memory integration.

    Returns:
        Status dict with 'available', 'connected', and 'error' fields
    """
    memory_skill = get_memory_skill_path()

    status = {
        "available": memory_skill.exists(),
        "path": str(memory_skill),
        "connected": False,
        "scope": MEMORY_SCOPE,
        "error": None,
    }

    if not status["available"]:
        status["error"] = "Memory skill not found"
        return status

    try:
        result = subprocess.run(
            [str(memory_skill), "status"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(memory_skill.parent),
        )
        if result.returncode == 0:
            status["connected"] = True
        else:
            status["error"] = result.stderr[:100]
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
