"""QRA Utilities - Logging, progress, text processing, and resilience patterns.

This module provides:
- Rich/tqdm progress indicators with graceful fallback
- Sentence splitting utilities
- Section building from text
- Rate limiting and retry decorators
"""

from __future__ import annotations

import functools
import re
import sys
import threading
import time as _time
from typing import Any, Callable, Generator, List, Tuple, Dict, Optional

from qra.config import ABBREVIATIONS, DEFAULT_MAX_SECTION_CHARS

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
    pass

try:
    from tqdm import tqdm

    _HAS_TQDM = True
except ImportError:
    pass


def log(msg: str, style: Optional[str] = None) -> None:
    """Log message with optional rich styling.

    Args:
        msg: Message to log
        style: Rich style (e.g., 'green', 'red', 'bold', 'dim')
    """
    if _HAS_RICH and _console:
        _console.print(f"[dim][qra][/dim] {msg}", style=style)
    else:
        print(f"[qra] {msg}", file=sys.stderr)


def status_panel(title: str, content: Dict[str, Any]) -> None:
    """Display a rich status panel if available.

    Args:
        title: Panel title
        content: Key-value pairs to display
    """
    if _HAS_RICH and _console:
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="white")
        for k, v in content.items():
            table.add_row(str(k), str(v))
        _console.print(
            Panel(table, title=f"[bold]{title}[/bold]", border_style="blue")
        )
    else:
        print(f"[qra] {title}:", file=sys.stderr)
        for k, v in content.items():
            print(f"  {k}: {v}", file=sys.stderr)


def iter_with_progress(
    iterable: Any, desc: str = "Processing", total: Optional[int] = None
) -> Generator[Any, None, None]:
    """Iterate with progress bar (tqdm or rich fallback).

    Args:
        iterable: Items to iterate over
        desc: Progress description
        total: Total count (auto-detected if possible)

    Yields:
        Items from iterable
    """
    if total is None:
        try:
            total = len(iterable)
        except TypeError:
            pass

    if _HAS_TQDM and not _HAS_RICH:
        yield from tqdm(iterable, desc=f"[qra] {desc}", total=total, file=sys.stderr)
        return

    if _HAS_RICH and _console:
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=_console,
        )
        task_id = progress.add_task(desc, total=total or 0)

        with progress:
            for item in iterable:
                yield item
                progress.advance(task_id)
        return

    # Fallback: simple percentage logging
    for i, item in enumerate(iterable):
        if total and i % max(1, total // 10) == 0:
            print(f"[qra] {desc}: {i}/{total}", file=sys.stderr)
        yield item


# =============================================================================
# Resilience Patterns (fallback when common.memory_client unavailable)
# =============================================================================


def with_retries(
    max_attempts: int = 3,
    base_delay: float = 0.5,
    exceptions: Tuple[type, ...] = (Exception,),
    on_retry: Optional[Callable] = None,
) -> Callable:
    """Decorator for retry logic with exponential backoff.

    Args:
        max_attempts: Maximum retry attempts
        base_delay: Initial delay between retries (doubles each attempt)
        exceptions: Exception types to catch and retry
        on_retry: Optional callback(attempt, error) on each retry

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
                            on_retry(attempt, e)
                        _time.sleep(delay)
            if last_error:
                raise last_error
            return None

        return wrapper

    return decorator


class RateLimiter:
    """Simple thread-safe rate limiter.

    Args:
        requests_per_second: Maximum requests per second
    """

    def __init__(self, requests_per_second: float = 5.0):
        self.interval = 1.0 / max(1, requests_per_second)
        self.last_request = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """Acquire permission to make a request, blocking if necessary."""
        with self._lock:
            sleep_time = max(0.0, (self.last_request + self.interval) - _time.time())
            if sleep_time > 0:
                _time.sleep(sleep_time)
            self.last_request = _time.time()


# =============================================================================
# Text Processing
# =============================================================================


def split_sentences(text: str) -> List[str]:
    """Split text into sentences.

    Uses NLTK PunktSentenceTokenizer if available, otherwise falls back
    to regex-based splitting.

    Args:
        text: Text to split

    Returns:
        List of sentences
    """
    if not text or not text.strip():
        return []

    try:
        from nltk.tokenize import PunktSentenceTokenizer

        tok = PunktSentenceTokenizer()
        tok._params.abbrev_types.update({a.replace(".", "") for a in ABBREVIATIONS})
        sents = [t.strip() for t in tok.tokenize(text) if t.strip()]
        if sents:
            return sents
    except Exception:
        pass

    # Fallback: regex split
    sents = re.split(r"(?<=[.!?])\s+(?=[A-Z(])", text)
    return [s.strip() for s in sents if s.strip()]


def build_sections(
    text: str,
    max_section_chars: int = DEFAULT_MAX_SECTION_CHARS,
) -> List[Tuple[str, str]]:
    """Build sections from text, respecting document structure.

    Detects markdown headers and numbered sections, splits oversized
    sections at sentence boundaries.

    Args:
        text: Text to split into sections
        max_section_chars: Maximum characters per section

    Returns:
        List of (section_title, section_content) tuples
    """
    lines = text.split("\n")
    sections: List[Tuple[str, str]] = []

    current_title = ""
    current_content: List[str] = []

    # Pattern for markdown headers
    header_re = re.compile(r"^(#{1,6})\s+(.+)$")
    # Pattern for numbered sections
    numbered_re = re.compile(r"^\s*(\d+(?:\.\d+)*)\s*[.:)\-]?\s+(\S.*)$")

    for line in lines:
        # Check for headers
        m = header_re.match(line)
        if m:
            # Save previous section
            if current_content:
                content = "\n".join(current_content).strip()
                if content:
                    sections.append((current_title, content))
            current_title = m.group(2).strip()
            current_content = []
            continue

        m = numbered_re.match(line)
        if m and len(m.group(2)) > 10:  # Avoid matching simple numbers
            if current_content:
                content = "\n".join(current_content).strip()
                if content:
                    sections.append((current_title, content))
            current_title = m.group(2).strip()
            current_content = []
            continue

        current_content.append(line)

    # Don't forget last section
    if current_content:
        content = "\n".join(current_content).strip()
        if content:
            sections.append((current_title, content))

    # If no structure detected, return as single section
    if not sections:
        return [("", text)]

    # Split oversized sections
    result: List[Tuple[str, str]] = []
    for title, content in sections:
        if len(content) <= max_section_chars:
            result.append((title, content))
        else:
            # Split at sentence boundaries
            sents = split_sentences(content)
            chunk_sents: List[str] = []
            chunk_chars = 0
            part_num = 1

            for sent in sents:
                if chunk_chars + len(sent) > max_section_chars and chunk_sents:
                    chunk_title = (
                        f"{title} (part {part_num})" if title else f"Part {part_num}"
                    )
                    result.append((chunk_title, " ".join(chunk_sents)))
                    part_num += 1
                    chunk_sents = []
                    chunk_chars = 0

                chunk_sents.append(sent)
                chunk_chars += len(sent) + 1

            if chunk_sents:
                chunk_title = (
                    f"{title} (part {part_num})"
                    if title and part_num > 1
                    else title
                )
                result.append((chunk_title, " ".join(chunk_sents)))

    return result


def clean_json_string(s: str) -> str:
    """Clean JSON string from LLM response.

    Removes markdown code blocks and extra whitespace.

    Args:
        s: Raw LLM response

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
