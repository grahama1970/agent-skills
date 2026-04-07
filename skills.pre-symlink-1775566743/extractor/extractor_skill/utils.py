#!/usr/bin/env python3
"""
Common utilities for extractor skill.

This module provides:
- Resilience patterns (retry decorator, rate limiter)
- Error formatting and guidance
- Import fallbacks for common.memory_client
"""
import functools
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple, Type

# --------------------------------------------------------------------------
# Import common memory client for standardized resilience patterns
# --------------------------------------------------------------------------

try:
    from common.memory_client import MemoryClient, MemoryScope, with_retries as _mc_with_retries, RateLimiter as _MCRateLimiter
    HAS_MEMORY_CLIENT = True
except ImportError:
    HAS_MEMORY_CLIENT = False
    MemoryClient = None
    MemoryScope = None

# --------------------------------------------------------------------------
# Fallback Resilience Utilities
# --------------------------------------------------------------------------


def with_retries(
    max_attempts: int = 3,
    base_delay: float = 0.5,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable] = None,
    track_retries: bool = False,
) -> Callable:
    """
    Decorator for retry logic with exponential backoff.

    Args:
        max_attempts: Maximum number of attempts
        base_delay: Base delay in seconds (doubles each retry)
        exceptions: Tuple of exception types to catch
        on_retry: Optional callback(attempt, error, delay) on retry
        track_retries: If True, return (result, retry_count) tuple

    Returns:
        Decorated function. If track_retries=True, returns (result, retry_count).

    Example:
        @with_retries(max_attempts=3, on_retry=lambda a, e, d: print(f"Retry {a}: {e}"))
        def fetch_data():
            ...

        # With retry tracking
        @with_retries(track_retries=True)
        def fetch_with_count():
            ...
        result, retries = fetch_with_count()
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            retry_count = 0
            for attempt in range(1, max_attempts + 1):
                try:
                    result = func(*args, **kwargs)
                    if track_retries:
                        return result, retry_count
                    return result
                except exceptions as e:
                    last_error = e
                    retry_count = attempt
                    if attempt < max_attempts:
                        delay = base_delay * (2 ** (attempt - 1))
                        if on_retry:
                            on_retry(attempt, e, delay)
                        time.sleep(delay)
            if last_error:
                if track_retries:
                    raise RetryExhaustedError(last_error, retry_count)
                raise last_error
            if track_retries:
                return None, retry_count
            return None
        return wrapper
    return decorator


class RetryExhaustedError(Exception):
    """Raised when all retry attempts are exhausted."""

    def __init__(self, original_error: Exception, retry_count: int):
        self.original_error = original_error
        self.retry_count = retry_count
        super().__init__(f"Retries exhausted after {retry_count} attempts: {original_error}")


class RateLimiter:
    """Thread-safe rate limiter for API calls."""

    def __init__(self, requests_per_second: float = 5.0):
        """
        Initialize rate limiter.

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
_memory_limiter = RateLimiter(requests_per_second=5)


def get_memory_limiter() -> RateLimiter:
    """Get the global memory rate limiter."""
    return _memory_limiter


# --------------------------------------------------------------------------
# Error Formatting
# --------------------------------------------------------------------------


def format_error_guidance(error: str, filepath: Optional[Path] = None, mode: Optional[str] = None) -> str:
    """
    Generate actionable guidance based on error type.

    Args:
        error: Error message
        filepath: Optional file path for context
        mode: Optional extraction mode for context

    Returns:
        Human-readable guidance string
    """
    guidance = []
    error_lower = error.lower()

    # LLM/API errors
    if any(kw in error_lower for kw in ["api", "chutes", "connection", "timeout", "503", "429", "unauthorized"]):
        guidance.extend([
            "Try these solutions:",
            "  1. Check CHUTES_API_KEY environment variable is set",
            "  2. Try --fast mode (no LLM required): ./run.sh file.pdf --fast",
            "  3. Check network connectivity to llm.chutes.ai",
            "  4. If Chutes is overloaded (503), wait and retry",
        ])

    # File/corrupt errors
    elif any(kw in error_lower for kw in ["corrupt", "invalid pdf", "unable to read", "file not found", "permission"]):
        guidance.extend([
            "File may be corrupted or inaccessible:",
            "  1. Verify the file exists and is readable",
            "  2. Try opening the PDF in a viewer to verify it's not corrupt",
            "  3. Check file permissions",
            "  4. If password-protected, the PDF must be unlocked first",
        ])

    # Memory/resource errors
    elif any(kw in error_lower for kw in ["memory", "oom", "killed", "resource"]):
        guidance.extend([
            "Resource limit exceeded:",
            "  1. Try --fast mode to reduce memory usage",
            "  2. Process smaller batches",
            "  3. Increase system memory/swap",
        ])

    # Syntax errors in pipeline code (not a dependency issue)
    elif any(kw in error_lower for kw in ["syntaxerror", "indentationerror"]):
        guidance.extend([
            "Syntax error in pipeline code:",
            "  1. Check the traceback above for the file and line number",
            "  2. Fix the syntax error in the source file",
            "  3. Run: python -m py_compile <file> to verify",
        ])

    # Import/dependency errors
    elif any(kw in error_lower for kw in ["no module named", "importerror", "modulenotfounderror"]):
        guidance.extend([
            "Missing dependency:",
            "  1. Activate the virtual environment: source .venv/bin/activate",
            "  2. Install dependencies: pip install -e .",
            "  3. Check PYTHONPATH includes extractor/src",
        ])

    # Pipeline errors
    elif "pipeline" in error_lower or "stage" in error_lower:
        guidance.extend([
            "Pipeline processing failed:",
            "  1. Try --fast mode: ./run.sh file.pdf --fast",
            "  2. Try with explicit preset: ./run.sh file.pdf --preset arxiv",
            "  3. Check the pipeline logs in output directory",
        ])

    # Generic fallback
    else:
        guidance.extend([
            "Troubleshooting steps:",
            "  1. Try --fast mode (no LLM): ./run.sh file.pdf --fast",
            "  2. Try with explicit preset: ./run.sh file.pdf --preset arxiv",
            "  3. Check CHUTES_API_KEY is set if using LLM features",
            "  4. Run sanity check: ./sanity.sh",
        ])

    return "\n".join(guidance)
