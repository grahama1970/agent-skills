#!/usr/bin/env python3
"""
Memory skill integration for extractor.

Provides functions to sync extraction results to the memory system
for future recall and knowledge retrieval.
"""
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from extractor_skill.config import MEMORY_SKILL_PATH
from extractor_skill.utils import (
    HAS_MEMORY_CLIENT,
    MemoryClient,
    get_memory_limiter,
    with_retries,
)


def learn_to_memory(
    filepath: Path,
    result: Dict[str, Any],
    scope: str = "documents"
) -> bool:
    """
    Auto-learn extraction summary to memory for future recall.

    Uses retry logic for resilience against transient failures.

    Args:
        filepath: Path to the extracted document
        result: Extraction result dictionary
        scope: Memory scope for storage

    Returns:
        True if learning succeeded, False otherwise
    """
    if not result.get("success"):
        return False

    counts = result.get("counts", {})
    sections = counts.get("sections", 0)
    tables = counts.get("tables", 0)
    figures = counts.get("figures", 0)
    preset = result.get("preset", "auto")

    # Build problem and solution
    problem = f"What is in {filepath.name}?"
    solution_parts = [f"{sections} sections"]
    if tables > 0:
        solution_parts.append(f"{tables} tables")
    if figures > 0:
        solution_parts.append(f"{figures} figures")
    solution_parts.append(f"Preset: {preset}")

    solution = ", ".join(solution_parts)
    tags = ["extractor", "document", preset]

    # Use common MemoryClient if available for standardized resilience
    if HAS_MEMORY_CLIENT and MemoryClient is not None:
        try:
            client = MemoryClient(scope=scope)
            mem_result = client.learn(problem=problem, solution=solution, tags=tags)
            return mem_result.success
        except Exception:
            return False

    # Fallback: direct subprocess with inline retry logic
    if not MEMORY_SKILL_PATH.exists():
        return False

    @with_retries(max_attempts=3, base_delay=0.5)
    def _learn_with_retry() -> bool:
        get_memory_limiter().acquire()
        cmd = [
            str(MEMORY_SKILL_PATH),
            "learn",
            "--problem", problem,
            "--solution", solution,
        ]
        if scope:
            cmd.extend(["--scope", scope])
        for tag in tags:
            cmd.extend(["--tag", tag])

        proc_result = subprocess.run(cmd, capture_output=True, timeout=30)
        if proc_result.returncode != 0:
            raise RuntimeError(f"Memory learn failed: {proc_result.stderr}")
        return True

    try:
        return _learn_with_retry()
    except Exception:
        return False
