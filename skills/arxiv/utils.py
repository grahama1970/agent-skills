#!/usr/bin/env python3
"""
Common utilities for arxiv-learn skill.

Provides logging, skill execution, resilience patterns (retry, rate limiting),
and shared data classes.
"""
from __future__ import annotations

import functools
import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from config import (
    SKILLS_DIR,
    SKILL_RUN_TIMEOUT,
    MEMORY_REQUESTS_PER_SECOND,
)

# =============================================================================
# Memory Client Import (with fallback)
# =============================================================================

try:
    from common.memory_client import MemoryClient, MemoryScope, with_retries, RateLimiter
    HAS_MEMORY_CLIENT = True
except ImportError:
    HAS_MEMORY_CLIENT = False
    MemoryClient = None
    MemoryScope = None

# =============================================================================
# .env Loading (best-effort)
# =============================================================================

try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True), override=False)
except Exception:
    pass

# =============================================================================
# Task Monitor Integration
# =============================================================================

try:
    sys.path.append(str(SKILLS_DIR / "task-monitor"))
    from monitor_adapter import Monitor
except ImportError:
    Monitor = None

# =============================================================================
# Logging
# =============================================================================

def log(msg: str, style: str | None = None, stage: int | None = None) -> None:
    """Log message with optional stage prefix.

    Args:
        msg: Message to log
        style: Rich console style (e.g., "bold", "green", "yellow")
        stage: Pipeline stage number (1-5) for prefix
    """
    prefix = f"[{stage}/5]" if stage else "[arxiv-learn]"
    try:
        from rich.console import Console
        console = Console(stderr=True)
        console.print(f"{prefix} {msg}", style=style)
    except ImportError:
        print(f"{prefix} {msg}", file=sys.stderr)

# =============================================================================
# Resilience Patterns (fallback when memory_client not available)
# =============================================================================

if not HAS_MEMORY_CLIENT:
    def with_retries(
        max_attempts: int = 3,
        base_delay: float = 0.5,
        exceptions: tuple = (Exception,),
        on_retry: Callable | None = None
    ):
        """Decorator for retrying failed operations with exponential backoff.

        Args:
            max_attempts: Maximum retry attempts
            base_delay: Initial delay in seconds
            exceptions: Exception types to catch and retry
            on_retry: Optional callback on retry

        Returns:
            Decorated function with retry logic
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                last_error = None
                for attempt in range(1, max_attempts + 1):
                    try:
                        return func(*args, **kwargs)
                    except exceptions as e:
                        last_error = e
                        if attempt < max_attempts:
                            delay = base_delay * (2 ** (attempt - 1))
                            if on_retry:
                                on_retry(attempt, e, delay)
                            time.sleep(delay)
                if last_error:
                    raise last_error
                return None
            return wrapper
        return decorator

    class RateLimiter:
        """Simple rate limiter using token bucket algorithm."""

        def __init__(self, requests_per_second: float = 5.0):
            """Initialize rate limiter.

            Args:
                requests_per_second: Maximum requests per second
            """
            self.interval = 1.0 / max(1, requests_per_second)
            self.last_request = 0.0
            self._lock = threading.Lock()

        def acquire(self) -> None:
            """Acquire permission to make a request, blocking if necessary."""
            with self._lock:
                sleep_time = max(0.0, (self.last_request + self.interval) - time.time())
                if sleep_time > 0:
                    time.sleep(sleep_time)
                self.last_request = time.time()

# Global rate limiter for memory operations
_memory_limiter = RateLimiter(requests_per_second=MEMORY_REQUESTS_PER_SECOND)

def get_memory_limiter() -> RateLimiter:
    """Get the global memory rate limiter."""
    return _memory_limiter

# =============================================================================
# Skill Execution
# =============================================================================

def run_skill(skill_name: str, args: list[str], capture: bool = True) -> dict | str:
    """Run a skill script and return output.

    Args:
        skill_name: Name of the skill directory
        args: Command-line arguments for the skill
        capture: Whether to capture and parse output

    Returns:
        Parsed JSON dict or raw string output

    Raises:
        FileNotFoundError: If skill not found
        RuntimeError: If skill execution fails
    """
    skill_dir = SKILLS_DIR / skill_name
    run_script = skill_dir / "run.sh"

    if not run_script.exists():
        raise FileNotFoundError(f"Skill not found: {skill_name}")

    cmd = ["bash", str(run_script)] + args
    result = subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        timeout=SKILL_RUN_TIMEOUT,
        env={**os.environ, "PYTHONPATH": f"{SKILLS_DIR}:{os.environ.get('PYTHONPATH', '')}"},
    )

    if result.returncode != 0:
        raise RuntimeError(f"{skill_name} failed: {result.stderr[:500]}")

    if capture:
        stdout = result.stdout.strip()
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            # Robust JSON extraction: look for first { and last }
            try:
                start = stdout.find("{")
                end = stdout.rfind("}")
                if start != -1 and end != -1 and end > start:
                    return json.loads(stdout[start:end+1])
            except Exception:
                pass
            return stdout
    return ""

# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class Paper:
    """Downloaded paper info."""
    arxiv_id: str
    title: str
    authors: list[str]
    pdf_path: str
    abstract: str = ""
    html_url: str = ""
    html_path: str = ""  # Path to downloaded HTML (from ar5iv)


@dataclass
class QAPair:
    """A distilled Q&A pair with agent recommendation."""
    id: str
    question: str
    answer: str
    reasoning: str = ""
    section_title: str = ""
    recommendation: str = "keep"  # keep, drop
    reason: str = ""  # Why agent recommends this
    grounding_score: float = 0.0
    stored: bool = False
    lesson_id: str = ""

    def to_interview_question(self) -> dict:
        """Convert to interview question format."""
        return {
            "id": self.id,
            "text": f"Q: {self.question}\nA: {self.answer}",
            "type": "yes_no_refine",
            "recommendation": self.recommendation,
            "reason": self.reason,
        }


@dataclass
class LearnSession:
    """Session state for the arxiv-learn pipeline."""
    arxiv_id: str = ""
    search_query: str = ""
    file_path: str = ""
    scope: str = "research"
    context: str = ""
    mode: str = "auto"
    dry_run: bool = False
    skip_interview: bool = False
    max_edges: int = 20
    accurate: bool = False  # Force accurate mode (PDF + VLM)
    high_reasoning: bool = False  # Use Codex for high-reasoning recommendations

    paper: Paper | None = None

    profile: dict | None = None  # HTML profile result
    extraction_format: str = ""
    qa_pairs: list[QAPair] = field(default_factory=list)
    approved_pairs: list[QAPair] = field(default_factory=list)
    dropped_pairs: list[QAPair] = field(default_factory=list)

    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None

# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Logging
    "log",
    # Resilience
    "with_retries",
    "RateLimiter",
    "get_memory_limiter",
    # Skill execution
    "run_skill",
    # Data classes
    "Paper",
    "QAPair",
    "LearnSession",
    # Memory client
    "HAS_MEMORY_CLIENT",
    "MemoryClient",
    "MemoryScope",
    # Task monitor
    "Monitor",
]
