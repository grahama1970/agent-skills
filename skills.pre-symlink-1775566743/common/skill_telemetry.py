"""
Skill Telemetry - Record skill outcomes to memory.

Provides a lightweight wrapper around MemoryClient.learn() for skills
to report success/failure outcomes. Enables memory-first debugging:
recall past failures before retrying.

Usage:
    from common.skill_telemetry import record_outcome, track_skill

    # Simple outcome recording
    record_outcome("extractor", "success", duration_s=12.3, details="Processed 5 PDFs")
    record_outcome("extractor", "failure", error="Connection refused", details="ArangoDB down")

    # Context manager with automatic timing
    with track_skill("learn-datalake") as tracker:
        do_work()
        tracker.details = "Ingested 42 documents"
    # Automatically records success + duration on clean exit, failure on exception
"""

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Optional

from loguru import logger

from .memory_client import MemoryClient, MemoryScope, LearnResult

__all__ = [
    "record_outcome",
    "track_skill",
]


def record_outcome(
    skill_name: str,
    outcome: str,
    *,
    duration_s: Optional[float] = None,
    error: Optional[str] = None,
    details: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> LearnResult:
    """Record a skill execution outcome to memory.

    Args:
        skill_name: Name of the skill (e.g., "extractor", "learn-datalake")
        outcome: One of "success", "failure", "partial"
        duration_s: Execution duration in seconds
        error: Error message (for failure/partial)
        details: Additional context about what happened
        tags: Extra tags beyond the auto-generated ones

    Returns:
        LearnResult from memory storage
    """
    problem_parts = [f"Skill '{skill_name}' execution: {outcome}"]
    if error:
        problem_parts.append(f"Error: {error}")

    solution_parts = []
    if details:
        solution_parts.append(details)
    if duration_s is not None:
        solution_parts.append(f"Duration: {duration_s:.1f}s")
    if outcome == "failure" and error:
        solution_parts.append(f"Investigate: {error}")

    all_tags = ["skill_telemetry", skill_name, outcome]
    if tags:
        all_tags.extend(tags)

    try:
        client = MemoryClient(scope=MemoryScope.OPERATIONAL)
        return client.learn(
            problem=" | ".join(problem_parts),
            solution=" | ".join(solution_parts) or f"{skill_name} completed with {outcome}",
            tags=all_tags,
        )
    except Exception as e:
        logger.warning(f"Failed to record telemetry for {skill_name}: {e}")
        return LearnResult(success=False, error=str(e))


@dataclass
class _SkillTracker:
    """Mutable state for the track_skill context manager."""
    skill_name: str
    details: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    _start: float = field(default_factory=time.monotonic)


@contextmanager
def track_skill(skill_name: str, tags: Optional[list[str]] = None):
    """Context manager that records skill outcome with automatic timing.

    On clean exit, records "success". On exception, records "failure" with error.

    Args:
        skill_name: Name of the skill
        tags: Extra tags

    Yields:
        _SkillTracker with mutable .details and .tags fields

    Example:
        with track_skill("extractor", tags=["batch"]) as t:
            results = process_batch()
            t.details = f"Processed {len(results)} items"
    """
    tracker = _SkillTracker(skill_name=skill_name, tags=tags or [])
    try:
        yield tracker
        duration = time.monotonic() - tracker._start
        record_outcome(
            skill_name,
            "success",
            duration_s=duration,
            details=tracker.details,
            tags=tracker.tags,
        )
    except Exception as e:
        duration = time.monotonic() - tracker._start
        record_outcome(
            skill_name,
            "failure",
            duration_s=duration,
            error=str(e),
            details=tracker.details,
            tags=tracker.tags,
        )
        raise
