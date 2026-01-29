#!/usr/bin/env python3
"""Memory storage operations for distill skill.

Provides storage of Q&A pairs to the memory system with retry logic
and rate limiting.
"""

from __future__ import annotations

import subprocess
from typing import List

from .utils import (
    get_memory_client,
    has_memory_client,
    log,
    memory_limiter,
    with_retries,
)


def store_qa(
    problem: str,
    solution: str,
    scope: str,
    tags: List[str] = None,
) -> bool:
    """Store Q&A pair via memory-agent learn with retry logic.

    Args:
        problem: The question/problem statement
        solution: The answer/solution
        scope: Memory scope to store in
        tags: Optional list of tags

    Returns:
        True if stored successfully, False otherwise
    """
    # Use common MemoryClient if available for standardized resilience
    if has_memory_client():
        MemoryClient = get_memory_client()
        try:
            client = MemoryClient(scope=scope)
            result = client.learn(problem=problem, solution=solution, tags=tags or [])
            if not result.success:
                log(f"Failed to store: {result.error}", style="red")
            return result.success
        except Exception as e:
            log(f"Failed to store: {e}", style="red")
            return False

    # Fallback: direct subprocess with inline retry logic
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

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise RuntimeError(f"Memory learn failed: {result.stderr}")
        return True

    try:
        return _store_with_retry()
    except Exception as e:
        log(f"Failed to store after retries: {e}", style="red")
        return False
