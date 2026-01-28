#!/usr/bin/env python3
"""
Standard Memory Integration Module for All Skills

This module provides a consistent interface for interacting with the memory skill.
All skills should use this module instead of implementing their own memory integration.

Features:
- Retry logic with exponential backoff
- Rate limiting (token bucket)
- Structured logging with PII redaction
- Scope validation
- Both CLI and Python API support

Usage:
    from common.memory_client import MemoryClient, MemoryScope

    client = MemoryClient(scope=MemoryScope.SOCIAL_INTEL)

    # Recall with automatic retries
    results = client.recall("query about security")

    # Learn with validation
    client.learn(
        problem="OAuth token refresh failing",
        solution="Add explicit error handling in refreshToken()",
        tags=["oauth", "auth", "bug-fix"]
    )
"""

import functools
import json
import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union

# =============================================================================
# CONFIGURATION
# =============================================================================

# Retry configuration (overridable via environment)
MAX_RETRIES = int(os.environ.get("MEMORY_MAX_RETRIES", "3"))
RETRY_BASE_DELAY = float(os.environ.get("MEMORY_RETRY_DELAY", "0.5"))
RATE_LIMIT_RPS = int(os.environ.get("MEMORY_RATE_LIMIT_RPS", "10"))

# Path resolution
MEMORY_ROOT = os.environ.get(
    "MEMORY_ROOT",
    str(Path.home() / "workspace" / "experiments" / "memory")
)

# Logging configuration
logger = logging.getLogger("memory_client")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# Fields to redact in logs
REDACT_FIELDS = {"token", "api_key", "api_hash", "password", "secret", "authorization", "bearer"}

# Type variable for generic decorator
T = TypeVar("T")


# =============================================================================
# MEMORY SCOPES - Standardized across all skills
# =============================================================================

class MemoryScope(str, Enum):
    """
    Valid memory scopes across all skills.

    Using an enum ensures consistency and enables validation.
    Add new scopes here as needed - this is the single source of truth.
    """
    # Core scopes
    OPERATIONAL = "operational"           # General operations, default scope
    DOCUMENTS = "documents"               # Extracted documents (PDF, DOCX, etc.)
    CODE = "code"                         # Code patterns, snippets, solutions

    # Social/Intel scopes
    SOCIAL_INTEL = "social_intel"         # Social media content (Telegram, Discord)
    SECURITY = "security"                 # Security findings, vulnerabilities
    THREAT_INTEL = "threat_intel"         # Threat intelligence feeds

    # Research scopes
    RESEARCH = "research"                 # General research papers
    ARXIV = "arxiv"                       # ArXiv papers specifically

    # Persona scopes
    HORUS_LORE = "horus_lore"             # Horus persona knowledge
    PERSONA = "persona"                   # General persona knowledge
    TOM = "tom"                           # Theory of Mind observations

    # Project-specific (use sparingly)
    TEST = "test"                         # Testing/sanity checks
    SANITY = "sanity"                     # Sanity test scope

    @classmethod
    def validate(cls, scope: Union[str, "MemoryScope"]) -> str:
        """Validate and normalize a scope string."""
        if isinstance(scope, cls):
            return scope.value

        # Check if it's a valid enum value
        try:
            return cls(scope).value
        except ValueError:
            pass

        # Allow custom scopes with warning
        logger.warning(f"Using non-standard scope '{scope}'. Consider adding to MemoryScope enum.")
        return scope


# =============================================================================
# RESILIENCE UTILITIES
# =============================================================================

def redact_sensitive(data: Any, depth: int = 0) -> Any:
    """
    Recursively redact sensitive fields from data for safe logging.

    Args:
        data: Data structure to redact (dict, list, or scalar)
        depth: Current recursion depth (to prevent infinite loops)

    Returns:
        Redacted copy of the data
    """
    if depth > 10:
        return "[MAX_DEPTH]"

    if isinstance(data, dict):
        return {
            k: "[REDACTED]" if k.lower() in REDACT_FIELDS else redact_sensitive(v, depth + 1)
            for k, v in data.items()
        }
    elif isinstance(data, list):
        return [redact_sensitive(item, depth + 1) for item in data]
    elif isinstance(data, str) and len(data) > 100:
        # Truncate long strings
        return data[:100] + "..."
    return data


def with_retries(
    max_attempts: int = MAX_RETRIES,
    base_delay: float = RETRY_BASE_DELAY,
    exceptions: tuple = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator that adds retry logic with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts
        base_delay: Base delay in seconds (doubles each retry)
        exceptions: Tuple of exception types to catch
        on_retry: Optional callback called on each retry with (exception, attempt)

    Returns:
        Decorated function with retry logic

    Example:
        @with_retries(max_attempts=3, base_delay=0.5)
        def call_api():
            return requests.get(url)
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_error: Optional[Exception] = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_error = e
                    if attempt < max_attempts:
                        delay = base_delay * (2 ** (attempt - 1))
                        logger.warning(
                            f"Attempt {attempt}/{max_attempts} failed for {func.__name__}: "
                            f"{type(e).__name__}: {e}. Retrying in {delay:.1f}s..."
                        )
                        if on_retry:
                            on_retry(e, attempt)
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"All {max_attempts} attempts failed for {func.__name__}: "
                            f"{type(e).__name__}: {e}"
                        )

            if last_error:
                raise last_error
            raise RuntimeError(f"Unexpected state in retry logic for {func.__name__}")

        return wrapper
    return decorator


class RateLimiter:
    """
    Simple token-bucket rate limiter for API calls.

    Thread-safe implementation that limits requests per second.

    Example:
        limiter = RateLimiter(requests_per_second=5)
        for item in items:
            limiter.acquire()  # Blocks if rate exceeded
            process(item)
    """

    def __init__(self, requests_per_second: int = RATE_LIMIT_RPS):
        """
        Initialize rate limiter.

        Args:
            requests_per_second: Maximum requests allowed per second
        """
        self.interval = 1.0 / max(1, requests_per_second)
        self.last_request = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> float:
        """
        Acquire permission to make a request, blocking if necessary.

        Returns:
            Time waited in seconds (0.0 if no wait was needed)
        """
        with self._lock:
            now = time.time()
            elapsed = now - self.last_request
            sleep_time = max(0.0, self.interval - elapsed)

            if sleep_time > 0:
                time.sleep(sleep_time)

            self.last_request = time.time()
            return sleep_time


# Global rate limiter for memory operations
_memory_limiter = RateLimiter(requests_per_second=RATE_LIMIT_RPS)


# =============================================================================
# MEMORY CLIENT
# =============================================================================

@dataclass
class RecallResult:
    """Result from a memory recall operation."""
    items: List[Dict[str, Any]] = field(default_factory=list)
    query: str = ""
    scope: str = ""
    k: int = 5
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def found(self) -> bool:
        """Whether any results were found."""
        return len(self.items) > 0

    @property
    def top(self) -> Optional[Dict[str, Any]]:
        """Get the top result, if any."""
        return self.items[0] if self.items else None

    def to_context(self, max_items: int = 3) -> str:
        """
        Format results as context for injection into prompts.

        Args:
            max_items: Maximum number of items to include

        Returns:
            Formatted markdown string
        """
        if not self.items:
            return ""

        lines = ["## Memory Recall (Prior Solutions Found)\n"]
        for i, item in enumerate(self.items[:max_items], 1):
            problem = item.get("problem", item.get("title", "Unknown"))
            solution = item.get("solution", item.get("content", ""))
            lines.append(f"{i}. **Problem**: {problem}")
            lines.append(f"   **Solution**: {solution}\n")

        return "\n".join(lines)


@dataclass
class LearnResult:
    """Result from a memory learn operation."""
    success: bool = False
    lesson_id: str = ""
    scope: str = ""
    error: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)


class MemoryClient:
    """
    Standard client for interacting with the memory skill.

    Provides a consistent interface with built-in resilience patterns.
    Supports both CLI subprocess and Python API backends.

    Example:
        client = MemoryClient(scope=MemoryScope.SECURITY)

        # Search memory
        results = client.recall("buffer overflow techniques")
        if results.found:
            print(results.top["solution"])

        # Store new knowledge
        result = client.learn(
            problem="Heap spray detection",
            solution="Monitor allocation patterns...",
            tags=["heap", "detection"]
        )
    """

    def __init__(
        self,
        scope: Union[str, MemoryScope] = MemoryScope.OPERATIONAL,
        use_python_api: bool = False,
        memory_root: Optional[str] = None
    ):
        """
        Initialize memory client.

        Args:
            scope: Default scope for operations
            use_python_api: If True, use direct Python imports instead of CLI
            memory_root: Override path to memory project
        """
        self.scope = MemoryScope.validate(scope)
        self.use_python_api = use_python_api
        self.memory_root = Path(memory_root or MEMORY_ROOT)
        self._python_client: Optional[Any] = None

        # Validate memory root exists
        if not self.memory_root.exists():
            logger.warning(f"Memory root not found: {self.memory_root}")

    def _get_run_script(self) -> Path:
        """Get path to memory run.sh script."""
        # Check multiple locations
        candidates = [
            self.memory_root / "run.sh",
            Path.home() / ".pi" / "agent" / "skills" / "memory" / "run.sh",
            Path.home() / ".pi" / "skills" / "memory" / "run.sh",
        ]

        for candidate in candidates:
            if candidate.exists():
                return candidate

        raise FileNotFoundError(
            f"Memory run.sh not found in any of: {[str(c) for c in candidates]}"
        )

    def _get_python_client(self) -> Any:
        """Get or create Python API client."""
        if self._python_client is None:
            try:
                import sys
                sys.path.insert(0, str(self.memory_root / "src"))
                from graph_memory.api import MemoryClient as GMClient
                self._python_client = GMClient(scope=self.scope)
            except ImportError as e:
                raise ImportError(
                    f"Could not import graph_memory. Ensure memory project is installed: {e}"
                )
        return self._python_client

    @with_retries()
    def recall(
        self,
        query: str,
        scope: Optional[Union[str, MemoryScope]] = None,
        k: int = 5,
        threshold: float = 0.3
    ) -> RecallResult:
        """
        Search memory for relevant knowledge.

        Args:
            query: Search query
            scope: Override default scope
            k: Number of results to return
            threshold: Minimum similarity threshold

        Returns:
            RecallResult with matching items
        """
        effective_scope = MemoryScope.validate(scope) if scope else self.scope
        _memory_limiter.acquire()

        logger.debug(f"Recalling: {query[:50]}... (scope={effective_scope}, k={k})")

        if self.use_python_api:
            return self._recall_python(query, effective_scope, k, threshold)
        return self._recall_cli(query, effective_scope, k, threshold)

    def _recall_cli(
        self,
        query: str,
        scope: str,
        k: int,
        threshold: float
    ) -> RecallResult:
        """Recall via CLI subprocess."""
        try:
            run_script = self._get_run_script()
            cmd = [
                str(run_script), "recall",
                "--q", query,
                "--k", str(k),
                "--threshold", str(threshold),
            ]
            if scope:
                cmd.extend(["--scope", scope])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(self.memory_root)
            )

            if result.returncode == 0:
                try:
                    data = json.loads(result.stdout)
                    return RecallResult(
                        items=data.get("items", []),
                        query=query,
                        scope=scope,
                        k=k,
                        meta=data.get("meta", {})
                    )
                except json.JSONDecodeError:
                    # Non-JSON output, try to parse as text
                    logger.warning(f"Non-JSON recall output: {result.stdout[:100]}")
                    return RecallResult(query=query, scope=scope, k=k)
            else:
                logger.error(f"Recall failed: {result.stderr}")
                return RecallResult(query=query, scope=scope, k=k)

        except subprocess.TimeoutExpired:
            logger.error("Recall timed out after 30s")
            raise
        except FileNotFoundError as e:
            logger.error(f"Memory script not found: {e}")
            raise

    def _recall_python(
        self,
        query: str,
        scope: str,
        k: int,
        threshold: float
    ) -> RecallResult:
        """Recall via Python API."""
        client = self._get_python_client()
        result = client.recall(query, k=k, threshold=threshold)

        return RecallResult(
            items=result.get("items", []),
            query=query,
            scope=scope,
            k=k,
            meta=result.get("meta", {})
        )

    @with_retries()
    def learn(
        self,
        problem: str,
        solution: str,
        scope: Optional[Union[str, MemoryScope]] = None,
        tags: Optional[List[str]] = None
    ) -> LearnResult:
        """
        Store new knowledge in memory.

        Args:
            problem: Problem description or question
            solution: Solution or answer
            scope: Override default scope
            tags: Optional tags for categorization

        Returns:
            LearnResult with success status
        """
        effective_scope = MemoryScope.validate(scope) if scope else self.scope
        tags = tags or []
        _memory_limiter.acquire()

        logger.debug(f"Learning: {problem[:50]}... (scope={effective_scope})")

        if self.use_python_api:
            return self._learn_python(problem, solution, effective_scope, tags)
        return self._learn_cli(problem, solution, effective_scope, tags)

    def _learn_cli(
        self,
        problem: str,
        solution: str,
        scope: str,
        tags: List[str]
    ) -> LearnResult:
        """Learn via CLI subprocess."""
        try:
            run_script = self._get_run_script()
            cmd = [
                str(run_script), "learn",
                "--problem", problem,
                "--solution", solution,
                "--scope", scope,
            ]
            for tag in tags:
                cmd.extend(["--tag", tag])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(self.memory_root)
            )

            if result.returncode == 0:
                try:
                    data = json.loads(result.stdout)
                    return LearnResult(
                        success=True,
                        lesson_id=data.get("_key", data.get("id", "")),
                        scope=scope,
                        meta=data
                    )
                except json.JSONDecodeError:
                    # Assume success if exit code is 0
                    return LearnResult(success=True, scope=scope)
            else:
                return LearnResult(
                    success=False,
                    scope=scope,
                    error=result.stderr or "Unknown error"
                )

        except subprocess.TimeoutExpired:
            logger.error("Learn timed out after 30s")
            return LearnResult(success=False, scope=scope, error="Timeout")
        except FileNotFoundError as e:
            logger.error(f"Memory script not found: {e}")
            return LearnResult(success=False, scope=scope, error=str(e))

    def _learn_python(
        self,
        problem: str,
        solution: str,
        scope: str,
        tags: List[str]
    ) -> LearnResult:
        """Learn via Python API."""
        client = self._get_python_client()
        result = client.learn(problem=problem, solution=solution, tags=tags)

        return LearnResult(
            success=result.get("success", True),
            lesson_id=result.get("_key", ""),
            scope=scope,
            meta=result
        )

    def batch_learn(
        self,
        items: List[Dict[str, Any]],
        scope: Optional[Union[str, MemoryScope]] = None,
        concurrency: int = 4,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> List[LearnResult]:
        """
        Store multiple items in memory with concurrent execution.

        Args:
            items: List of dicts with 'problem', 'solution', and optional 'tags'
            scope: Override default scope for all items
            concurrency: Max concurrent operations (default: 4)
            progress_callback: Optional callback(completed, total) for progress updates

        Returns:
            List of LearnResult for each item (in same order as input)

        Example:
            results = client.batch_learn([
                {"problem": "Q1", "solution": "A1", "tags": ["tag1"]},
                {"problem": "Q2", "solution": "A2"},
            ], concurrency=4)
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        effective_scope = MemoryScope.validate(scope) if scope else self.scope
        results: List[Optional[LearnResult]] = [None] * len(items)
        completed = 0

        def learn_item(idx: int, item: Dict[str, Any]) -> tuple[int, LearnResult]:
            result = self.learn(
                problem=item.get("problem", ""),
                solution=item.get("solution", ""),
                scope=effective_scope,
                tags=item.get("tags", [])
            )
            return idx, result

        # Use ThreadPoolExecutor for concurrent execution
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = {
                executor.submit(learn_item, idx, item): idx
                for idx, item in enumerate(items)
            }

            for future in as_completed(futures):
                try:
                    idx, result = future.result()
                    results[idx] = result
                    completed += 1
                    if progress_callback:
                        progress_callback(completed, len(items))
                except Exception as e:
                    idx = futures[future]
                    results[idx] = LearnResult(
                        success=False,
                        scope=effective_scope,
                        error=str(e)
                    )
                    completed += 1
                    if progress_callback:
                        progress_callback(completed, len(items))

        # Filter out None values (shouldn't happen, but defensive)
        final_results = [r for r in results if r is not None]
        success_count = sum(1 for r in final_results if r.success)
        logger.info(f"Batch learn: {success_count}/{len(items)} succeeded (concurrency={concurrency})")

        return final_results

    def batch_recall(
        self,
        queries: List[str],
        scope: Optional[Union[str, MemoryScope]] = None,
        k: int = 5,
        concurrency: int = 4
    ) -> List[RecallResult]:
        """
        Search memory for multiple queries with concurrent execution.

        Args:
            queries: List of search queries
            scope: Override default scope
            k: Number of results per query
            concurrency: Max concurrent operations (default: 4)

        Returns:
            List of RecallResult for each query (in same order as input)

        Example:
            results = client.batch_recall([
                "authentication errors",
                "database connection issues",
            ])
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        effective_scope = MemoryScope.validate(scope) if scope else self.scope
        results: List[Optional[RecallResult]] = [None] * len(queries)

        def recall_query(idx: int, query: str) -> tuple[int, RecallResult]:
            result = self.recall(query, scope=effective_scope, k=k)
            return idx, result

        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = {
                executor.submit(recall_query, idx, query): idx
                for idx, query in enumerate(queries)
            }

            for future in as_completed(futures):
                try:
                    idx, result = future.result()
                    results[idx] = result
                except Exception as e:
                    idx = futures[future]
                    results[idx] = RecallResult(
                        query=queries[idx],
                        scope=effective_scope,
                        k=k
                    )
                    logger.error(f"Batch recall failed for query {idx}: {e}")

        return [r for r in results if r is not None]


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

# Default client instance
_default_client: Optional[MemoryClient] = None


def get_client(scope: Union[str, MemoryScope] = MemoryScope.OPERATIONAL) -> MemoryClient:
    """Get or create a default memory client."""
    global _default_client
    if _default_client is None or _default_client.scope != MemoryScope.validate(scope):
        _default_client = MemoryClient(scope=scope)
    return _default_client


def recall(
    query: str,
    scope: Union[str, MemoryScope] = MemoryScope.OPERATIONAL,
    k: int = 5
) -> RecallResult:
    """
    Convenience function for quick recall.

    Example:
        from common.memory_client import recall
        results = recall("authentication error handling")
    """
    return get_client(scope).recall(query, k=k)


def learn(
    problem: str,
    solution: str,
    scope: Union[str, MemoryScope] = MemoryScope.OPERATIONAL,
    tags: Optional[List[str]] = None
) -> LearnResult:
    """
    Convenience function for quick learn.

    Example:
        from common.memory_client import learn
        learn("How to fix X", "Do Y and Z", tags=["bug-fix"])
    """
    return get_client(scope).learn(problem, solution, tags=tags)


def batch_learn(
    items: List[Dict[str, Any]],
    scope: Union[str, MemoryScope] = MemoryScope.OPERATIONAL,
    concurrency: int = 4
) -> List[LearnResult]:
    """
    Convenience function for batch learning.

    Example:
        from common.memory_client import batch_learn
        results = batch_learn([
            {"problem": "Q1", "solution": "A1", "tags": ["tag1"]},
            {"problem": "Q2", "solution": "A2"},
        ])
    """
    return get_client(scope).batch_learn(items, concurrency=concurrency)


def batch_recall(
    queries: List[str],
    scope: Union[str, MemoryScope] = MemoryScope.OPERATIONAL,
    k: int = 5,
    concurrency: int = 4
) -> List[RecallResult]:
    """
    Convenience function for batch recall.

    Example:
        from common.memory_client import batch_recall
        results = batch_recall([
            "authentication errors",
            "database issues",
        ])
    """
    return get_client(scope).batch_recall(queries, k=k, concurrency=concurrency)


# =============================================================================
# MAIN (for testing)
# =============================================================================

if __name__ == "__main__":
    import sys

    # Simple CLI for testing
    if len(sys.argv) < 2:
        print("Usage: python memory_client.py <recall|learn> [args...]")
        print("\nExamples:")
        print("  python memory_client.py recall 'how to fix auth'")
        print("  python memory_client.py learn 'Problem X' 'Solution Y'")
        sys.exit(1)

    command = sys.argv[1]

    if command == "recall":
        query = sys.argv[2] if len(sys.argv) > 2 else "test query"
        result = recall(query)
        print(f"Found {len(result.items)} results:")
        for item in result.items[:3]:
            print(f"  - {item.get('problem', 'N/A')[:60]}...")

    elif command == "learn":
        if len(sys.argv) < 4:
            print("Usage: python memory_client.py learn 'problem' 'solution'")
            sys.exit(1)
        problem = sys.argv[2]
        solution = sys.argv[3]
        result = learn(problem, solution, scope=MemoryScope.TEST)
        print(f"Learn result: success={result.success}, id={result.lesson_id}")

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
