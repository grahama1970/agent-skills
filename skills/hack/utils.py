"""
Utility functions for the hack skill.

This module contains common utilities including:
- Memory client integration with retry logic
- Skill runner for sibling skill invocation
- Taxonomy and treesitter integration helpers
"""
from __future__ import annotations

import functools
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

from rich.console import Console
from typing import Callable, Optional, Any

from hack.config import (
    MEMORY_SKILL,
    SKILL_RUN_TIMEOUT,
    MEMORY_TIMEOUT,
    SKILLS_DIR,
    TAXONOMY_SKILL,
    TREESITTER_SKILL,
    TASK_MONITOR_SKILL,
)

console = Console()

# Add skills directory to path for common imports
if str(SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR))

# Import common memory client for standardized resilience patterns
try:
    from common.memory_client import MemoryClient, with_retries, RateLimiter

    HAS_MEMORY_CLIENT = True
except ImportError:
    HAS_MEMORY_CLIENT = False

    # Fallback: define minimal resilience utilities inline
    def with_retries(
        max_attempts: int = 3,
        base_delay: float = 0.5,
        exceptions: tuple[type[BaseException], ...] = (Exception,),
        on_retry: Optional[Callable[[int, BaseException, float], None]] = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Retry decorator with exponential backoff."""

        def decorator(func):
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
                            if on_retry is not None:
                                try:
                                    on_retry(attempt, e, delay)
                                except Exception:
                                    pass
                            time.sleep(delay)
                if last_error:
                    raise last_error

            return wrapper

        return decorator

    class RateLimiter:
        """Simple rate limiter for memory operations."""

        def __init__(self, requests_per_second: int = 5):
            self.interval = 1.0 / max(1, requests_per_second)
            self.last_request = 0.0
            self._lock = threading.Lock()

        def acquire(self):
            with self._lock:
                sleep_time = max(
                    0.0, (self.last_request + self.interval) - time.time()
                )
                if sleep_time > 0:
                    time.sleep(sleep_time)
                self.last_request = time.time()


# Rate limiter for memory operations
_memory_limiter = RateLimiter(requests_per_second=5)


def run_skill(skill_path: Path, *args) -> subprocess.CompletedProcess | None:
    """
    Run a sibling skill and return result.

    Args:
        skill_path: Path to the skill directory
        *args: Arguments to pass to the skill's run.sh

    Returns:
        CompletedProcess if successful, None if skill not found or error
    """
    run_script = skill_path / "run.sh"
    if not run_script.exists():
        console.print(f"[yellow]Skill not found: {skill_path.name}[/yellow]")
        return None

    try:
        return subprocess.run(
            [str(run_script), *args],
            capture_output=True,
            text=True,
            timeout=SKILL_RUN_TIMEOUT,
        )
    except Exception as e:
        console.print(f"[red]Error running {skill_path.name}: {e}[/red]")
        return None


def classify_findings(text: str) -> dict | None:
    """
    Use taxonomy skill to classify security findings.

    Args:
        text: Security finding text to classify

    Returns:
        Classification dict with bridge_tags, collection_tags, etc.
    """
    result = run_skill(
        TAXONOMY_SKILL, "--text", text, "--collection", "sparta", "--json"
    )
    if result and result.returncode == 0:
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            pass
    return None


def extract_symbols(file_path: str) -> str | None:
    """
    Use treesitter skill to extract code symbols before auditing.

    Args:
        file_path: Path to the file to extract symbols from

    Returns:
        Symbol extraction output or None
    """
    result = run_skill(TREESITTER_SKILL, "symbols", file_path)
    if result and result.returncode == 0:
        return result.stdout
    return None


def register_task_monitor(name: str, total: int, state_file: str) -> bool:
    """
    Register a task with the task-monitor for progress tracking.

    Args:
        name: Task name
        total: Total number of steps
        state_file: Path to state file

    Returns:
        True if registration successful
    """
    result = run_skill(
        TASK_MONITOR_SKILL,
        "register",
        "--name",
        name,
        "--total",
        str(total),
        "--state",
        state_file,
    )
    return result is not None and result.returncode == 0


def memory_recall(query: str, scope: str = "hack_skill", k: int = 3) -> dict | None:
    """
    Query memory skill for relevant prior knowledge with retry logic.

    Args:
        query: Search query
        scope: Memory scope (default: hack_skill)
        k: Number of results to return

    Returns:
        Recall results dict or None if memory unavailable
    """
    # Use common MemoryClient if available for standardized resilience
    if HAS_MEMORY_CLIENT:
        try:
            client = MemoryClient(scope=scope)
            result = client.recall(query, k=k)
            if result.found:
                return {
                    "found": True,
                    "items": result.items,
                    "answer": result.items[0].get("solution", "")
                    if result.items
                    else "",
                }
            return {"found": False}
        except Exception:
            return None

    # Fallback: direct subprocess with inline retry logic
    @with_retries(max_attempts=3, base_delay=0.5)
    def _recall_with_retry():
        _memory_limiter.acquire()
        memory_script = MEMORY_SKILL / "run.sh"
        if not memory_script.exists():
            memory_script = (
                Path.home()
                / "workspace/experiments/pi-mono/.agent/skills/memory/run.sh"
            )
        if not memory_script.exists():
            raise FileNotFoundError("Memory skill not found")

        result = subprocess.run(
            [
                str(memory_script),
                "recall",
                "--q",
                query,
                "--scope",
                scope,
                "--k",
                str(k),
            ],
            capture_output=True,
            text=True,
            timeout=MEMORY_TIMEOUT,
        )
        if result.returncode == 0 and result.stdout:
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return {"raw": result.stdout}
        return {"found": False}

    try:
        return _recall_with_retry()
    except Exception:
        return None


def memory_store(
    content: str, scope: str = "hack_skill", context: str = "security"
) -> bool:
    """
    Store knowledge in memory skill with retry logic.

    Args:
        content: Content to store
        scope: Memory scope (default: hack_skill)
        context: Context for the stored knowledge

    Returns:
        True if storage successful
    """
    # Use common MemoryClient if available for standardized resilience
    if HAS_MEMORY_CLIENT:
        try:
            client = MemoryClient(scope=scope)
            result = client.learn(
                problem=context, solution=content, tags=["security", "hack_skill"]
            )
            return result.success
        except Exception:
            return False

    # Fallback: direct subprocess with inline retry logic
    @with_retries(max_attempts=3, base_delay=0.5)
    def _store_with_retry():
        _memory_limiter.acquire()
        memory_script = MEMORY_SKILL / "run.sh"
        if not memory_script.exists():
            memory_script = (
                Path.home()
                / "workspace/experiments/pi-mono/.agent/skills/memory/run.sh"
            )
        if not memory_script.exists():
            raise FileNotFoundError("Memory skill not found")

        result = subprocess.run(
            [
                str(memory_script),
                "store",
                "--content",
                content,
                "--scope",
                scope,
                "--context",
                context,
            ],
            capture_output=True,
            text=True,
            timeout=MEMORY_TIMEOUT,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Memory store failed: {result.stderr}")
        return True

    try:
        return _store_with_retry()
    except Exception:
        return False


def show_memory_context(query: str, scope: str = "hack_skill"):
    """
    Display relevant memory context before an operation.

    Args:
        query: Query to search for relevant context
        scope: Memory scope to search
    """
    recall = memory_recall(query, scope=scope)
    if recall and recall.get("found"):
        console.print("\n[bold blue]Memory Recall (Prior Knowledge):[/bold blue]")
        if "answer" in recall:
            console.print(f"  {recall['answer'][:500]}...")
        if "sources" in recall:
            for src in recall.get("sources", [])[:3]:
                console.print(f"  [dim]- {src.get('title', 'Unknown')}[/dim]")
        console.print()

# Explicit module exports for clarity
__all__ = [
    "run_skill",
    "classify_findings",
    "extract_symbols",
    "register_task_monitor",
    "memory_recall",
    "memory_store",
    "show_memory_context",
]
