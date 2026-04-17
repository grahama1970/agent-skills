#!/usr/bin/env python3
"""Memory storage operations for distill skill.

Provides storage of Q&A pairs to the memory system with retry logic
and rate limiting.  After storing, stamps `taxonomy_tags` directly on
the ArangoDB document so bridge-based readiness queries work.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import List, Optional

from loguru import logger

from .utils import (
    get_memory_client,
    has_memory_client,
    log,
    memory_limiter,
    with_retries,
)

# Bridge tags that should be promoted to taxonomy_tags for graph traversal
BRIDGE_TAGS = {"Precision", "Resilience", "Fragility", "Corruption", "Loyalty", "Stealth"}


# Removed: memory accessed via httpx to Unix socket (see _memory_cmd)
def _stamp_taxonomy_tags(problem: str, scope: str, bridge_tags: List[str]) -> None:
    """Stamp taxonomy_tags via /memory tag — never access ArangoDB directly.

    memory-agent learn stores tags in the `tags` array, but readiness
    and multi-hop traversal queries use `taxonomy_tags`.  This post-hook
    finds the document by hash and stamps bridge tags via /memory tag.
    """
    if not bridge_tags:
        return

    import json
    from pathlib import Path
    import httpx

    # Find the document by problem_hash + scope via /memory sample
    problem_hash = hashlib.sha256(problem.encode()).hexdigest()[:16]

    try:
        result = subprocess.run(
            [MEMORY_RUN, "sample", "--collection", "lessons", "--limit", "1",
             "--filter", f'doc.problem_hash=="{problem_hash}" AND doc.scope=="{scope}"',
             "--fields", "_key"],
            capture_output=True, text=True, timeout=30,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode != 0:
            logger.debug("memory sample failed (rc={}): {}", result.returncode, result.stderr)
            return

        data = json.loads(result.stdout)
        items = data.get("items", [])
        if not items:
            return

        doc_key = items[0].get("_key")
        if not doc_key:
            return

        # Stamp via /memory tag (merge mode)
        tag_result = subprocess.run(
            [MEMORY_RUN, "tag", "--collection", "lessons", "--key", doc_key,
             "--tags", json.dumps(bridge_tags), "--field", "taxonomy_tags"],
            capture_output=True, text=True, timeout=30,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if tag_result.returncode != 0:
            logger.debug("memory tag failed: {}", tag_result.stderr)
    except Exception as e:
        logger.debug("taxonomy_tags stamp failed: {}", e)


def store_qa(
    problem: str,
    solution: str,
    scope: str,
    tags: List[str] = None,
) -> bool:
    """Store Q&A pair via memory-agent learn with retry logic.

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
    # Use memory-agent CLI directly — common.memory_client has scope issues
    # with non-standard scopes like brandon_bailey
    @with_retries(max_attempts=3, base_delay=0.5)
    def _store_with_retry() -> bool:
        memory_limiter.acquire()
        cmd = [
            "memory-agent", "learn",
            "--problem", problem,
            "--solution", solution,
            "--scope", scope,
        ]
        if tags:
            for tag in tags:
                cmd.extend(["--tag", tag])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode != 0:
            raise RuntimeError(f"Memory learn failed (rc={result.returncode}): {result.stderr}")
        return True

    try:
        success = _store_with_retry()
        if success and tags:
            bridge_tags = [t for t in tags if t in BRIDGE_TAGS]
            _stamp_taxonomy_tags(problem, scope, bridge_tags)
        return success
    except Exception as e:
        log(f"Failed to store after retries: {e}", style="red")
        return False
