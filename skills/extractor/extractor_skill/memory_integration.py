#!/usr/bin/env python3
"""
Memory skill integration for extractor.

Provides functions to sync extraction results to the memory system
for future recall and knowledge retrieval.

Uses MemoryClient from common.memory_client - /memory is always available.
"""
from pathlib import Path
from typing import Any, Dict

from common.memory_client import MemoryClient


def learn_to_memory(
    filepath: Path,
    result: Dict[str, Any],
    scope: str = "documents"
) -> bool:
    """
    Auto-learn extraction summary to memory for future recall.

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

    client = MemoryClient(scope=scope)
    mem_result = client.learn(problem=problem, solution=solution, tags=tags)
    return mem_result.success


def learn_failure_to_memory(
    filepath: Path,
    error: str,
    retry_count: int = 0,
    scope: str = "documents"
) -> bool:
    """
    Learn from extraction failures for pattern recognition.

    Records error patterns to memory so future extractions can:
    - Recognize similar failure modes
    - Suggest workarounds or alternative approaches
    - Track documents that need special handling

    Args:
        filepath: Path to the document that failed
        error: Error message or context
        retry_count: Number of retries attempted before failure
        scope: Memory scope for storage

    Returns:
        True if learning succeeded, False otherwise
    """
    # Truncate error to avoid overly long lessons
    error_summary = error[:200] if len(error) > 200 else error

    # Build problem/solution for failure pattern
    problem = f"Extraction failed for {filepath.name}"
    solution_parts = [f"Error: {error_summary}"]
    if retry_count > 0:
        solution_parts.append(f"Retries: {retry_count}")
    solution_parts.append("Consider: --fast mode, different preset, or manual inspection")

    solution = ". ".join(solution_parts)
    tags = ["extractor", "failure", "error-pattern", filepath.suffix.lstrip(".")]

    client = MemoryClient(scope=scope)
    mem_result = client.learn(problem=problem, solution=solution, tags=tags)
    return mem_result.success
