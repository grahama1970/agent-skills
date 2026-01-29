#!/usr/bin/env python3
"""Common utilities, logging, and progress indicators for distill skill.

Provides graceful fallback between Rich, tqdm, and plain text output.
Also includes retry logic and rate limiting utilities.
"""

from __future__ import annotations

import functools
import sys
import threading
import time as _time
from typing import Any, Callable, Dict, Iterator, List, Tuple, Type, Optional, Iterable

# =============================================================================
# Rich/tqdm Progress Indicators (optional, graceful fallback)
# =============================================================================

_HAS_RICH = False
_HAS_TQDM = False
_console = None

try:
    from rich.console import Console
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TaskProgressColumn,
        TimeElapsedColumn,
    )
    from rich.panel import Panel
    from rich.table import Table
    _HAS_RICH = True
    _console = Console(stderr=True)
except ImportError:
    Progress = None
    Panel = None
    Table = None

try:
    from tqdm import tqdm
    _HAS_TQDM = True
except ImportError:
    tqdm = None


def log(msg: str, style: Optional[str] = None) -> None:
    """Log message with optional rich styling."""
    if _HAS_RICH and _console:
        _console.print(f"[dim][distill][/dim] {msg}", style=style)
    else:
        print(f"[distill] {msg}", file=sys.stderr)


def status_panel(title: str, content: Dict[str, Any]) -> None:
    """Display a rich status panel if available."""
    if _HAS_RICH and _console:
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="white")
        for k, v in content.items():
            table.add_row(str(k), str(v))
        _console.print(Panel(table, title=f"[bold]{title}[/bold]", border_style="blue"))
    else:
        print(f"[distill] {title}:", file=sys.stderr)
        for k, v in content.items():
            print(f"  {k}: {v}", file=sys.stderr)


def create_progress() -> Optional[Any]:
    """Create a progress context manager."""
    if _HAS_RICH and Progress:
        return Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=_console,
        )
    return None


def iter_with_progress(iterable: Iterable[Any], desc: str = "Processing", total: Optional[int] = None) -> Iterator[Any]:
    """Iterate with progress bar (tqdm or rich fallback).

    Args:
        iterable: The iterable to process
        desc: Description for the progress bar
        total: Total number of items (optional, will try to infer)

    Yields:
        Items from the iterable
    """
    if total is None:
        try:
            total = len(iterable)
        except TypeError:
            pass

    if _HAS_TQDM and not _HAS_RICH and tqdm:
        # Use tqdm if rich not available
        yield from tqdm(iterable, desc=f"[distill] {desc}", total=total, file=sys.stderr)
        return

    if _HAS_RICH and _console:
        # Rich progress bar
        progress = create_progress()
        if progress:
            task_id = progress.add_task(desc, total=total or 0)
            with progress:
                for item in iterable:
                    yield item
                    progress.advance(task_id)
            return

    # Fallback: plain iteration with periodic updates
    for i, item in enumerate(iterable):
        if total and i % max(1, total // 10) == 0:
            print(f"[distill] {desc}: {i}/{total}", file=sys.stderr)
        yield item


# =============================================================================
# Resilience Utilities (retry logic and rate limiting)
# =============================================================================


def with_retries(
    max_attempts: int = 3,
    base_delay: float = 0.5,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Callable[[Exception, int], None] = None,
) -> Callable:
    """Decorator for retry logic with exponential backoff.

    Args:
        max_attempts: Maximum number of attempts
        base_delay: Base delay in seconds (doubles each retry)
        exceptions: Tuple of exception types to catch
        on_retry: Optional callback called on each retry

    Returns:
        Decorated function
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_error = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_error = e
                    if attempt < max_attempts:
                        delay = base_delay * (2 ** (attempt - 1))
                        if on_retry:
                            on_retry(e, attempt)
                        _time.sleep(delay)
            if last_error:
                raise last_error
            return None
        return wrapper
    return decorator


class RateLimiter:
    """Thread-safe rate limiter using token bucket algorithm."""

    def __init__(self, requests_per_second: float = 5.0):
        """Initialize rate limiter.

        Args:
            requests_per_second: Maximum requests per second
        """
        self.interval = 1.0 / max(1, requests_per_second)
        self.last_request = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """Acquire permission to make a request, blocking if needed."""
        with self._lock:
            now = _time.time()
            sleep_time = max(0.0, (self.last_request + self.interval) - now)
            if sleep_time > 0:
                _time.sleep(sleep_time)
            self.last_request = _time.time()


# Global rate limiter instance for memory operations
memory_limiter = RateLimiter(requests_per_second=5)


# =============================================================================
# Memory Client Import Helper
# =============================================================================

_HAS_MEMORY_CLIENT = False
_MemoryClient = None
_MemoryScope = None

try:
    from common.memory_client import MemoryClient as _MC, MemoryScope as _MS
    _HAS_MEMORY_CLIENT = True
    _MemoryClient = _MC
    _MemoryScope = _MS
except ImportError:
    pass


def has_memory_client() -> bool:
    """Check if memory client is available."""
    return _HAS_MEMORY_CLIENT


def get_memory_client() -> Any:
    """Get MemoryClient class if available, None otherwise."""
    return _MemoryClient


def get_memory_scope() -> Any:
    """Get MemoryScope class if available, None otherwise."""
    return _MemoryScope


# =============================================================================
# JSON Utilities
# =============================================================================


def clean_json_string(s: str) -> str:
    """Basic JSON string cleanup - removes markdown code blocks.

    Args:
        s: Raw string that may contain markdown code blocks

    Returns:
        Cleaned JSON string
    """
    s = s.strip()
    if s.startswith("```json"):
        s = s[7:]
    if s.startswith("```"):
        s = s[3:]
    if s.endswith("```"):
        s = s[:-3]
    return s.strip()
