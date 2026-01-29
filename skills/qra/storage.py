"""QRA Storage - Memory storage integration.

This module handles storing QRA pairs to the memory system
using either the common MemoryClient or subprocess fallback.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from qra.config import MEMORY_REQUESTS_PER_SECOND, SKILLS_DIR
from qra.utils import log, RateLimiter, with_retries

# =============================================================================
# Memory Client Setup
# =============================================================================

# Add skills directory to path for common imports
if str(SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR))

# Import common memory client for standardized resilience patterns
HAS_MEMORY_CLIENT = False
MemoryClient = None
MemoryScope = None

try:
    from common.memory_client import MemoryClient, MemoryScope

    HAS_MEMORY_CLIENT = True
except ImportError:
    pass

# Rate limiter for memory operations
_memory_limiter = RateLimiter(requests_per_second=MEMORY_REQUESTS_PER_SECOND)

# =============================================================================
# Storage Functions
# =============================================================================


def store_qra(
    qra: Dict[str, Any],
    scope: str,
    tags: Optional[List[str]] = None,
) -> bool:
    """Store QRA pair via memory-agent learn with retry logic.

    Uses MemoryClient if available, otherwise falls back to subprocess.

    Args:
        qra: QRA dict with problem/solution or question/answer
        scope: Memory scope for storage
        tags: Additional tags for the entry

    Returns:
        True if stored successfully
    """
    problem = qra.get("problem", qra.get("question", ""))
    solution = qra.get("solution", qra.get("answer", ""))
    all_tags = ["qra", "distilled"]
    if tags:
        all_tags.extend(tags)

    # Use common MemoryClient if available for standardized resilience
    if HAS_MEMORY_CLIENT and MemoryClient is not None:
        try:
            client = MemoryClient(scope=scope)
            result = client.learn(problem=problem, solution=solution, tags=all_tags)
            if not result.success:
                log(f"Store failed: {result.error}", style="red")
            return result.success
        except Exception as e:
            log(f"Store failed: {e}", style="red")
            return False

    # Fallback: direct subprocess with inline retry logic
    return _store_via_subprocess(problem, solution, scope, all_tags)


def _store_via_subprocess(
    problem: str,
    solution: str,
    scope: str,
    tags: List[str],
) -> bool:
    """Store via memory-agent subprocess with retries.

    Args:
        problem: Question/problem text
        solution: Answer/solution text
        scope: Memory scope
        tags: Tags for the entry

    Returns:
        True if successful
    """

    @with_retries(max_attempts=3, base_delay=0.5)
    def _store_with_retry() -> bool:
        _memory_limiter.acquire()
        cmd = [
            "memory-agent",
            "learn",
            "--problem",
            problem,
            "--solution",
            solution,
            "--scope",
            scope,
        ]
        for tag in tags:
            cmd.extend(["--tag", tag])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise RuntimeError(f"Memory learn failed: {result.stderr}")
        return True

    try:
        return _store_with_retry()
    except Exception as e:
        log(f"Store failed after retries: {e}", style="red")
        return False


def batch_store_qras(
    qras: List[Dict[str, Any]],
    scope: str,
    source: str = "",
    dry_run: bool = False,
) -> int:
    """Store multiple QRA pairs with progress tracking.

    Args:
        qras: List of QRA dicts
        scope: Memory scope
        source: Source identifier for tagging
        dry_run: If True, skip actual storage

    Returns:
        Count of successfully stored items
    """
    from qra.utils import iter_with_progress

    if dry_run:
        log(f"DRY RUN - would store {len(qras)} QRAs", style="yellow")
        return 0

    log(f"Storing {len(qras)} QRAs to scope '{scope}'")
    tags = [source.split("/")[0] if "/" in source else source] if source else []

    stored = 0
    for qra in iter_with_progress(qras, desc="Storing"):
        if store_qra(qra, scope, tags=tags):
            stored += 1

    return stored


def check_memory_available() -> bool:
    """Check if memory-agent is available.

    Returns:
        True if memory-agent can be called
    """
    if HAS_MEMORY_CLIENT:
        return True

    try:
        result = subprocess.run(
            ["memory-agent", "--help"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
