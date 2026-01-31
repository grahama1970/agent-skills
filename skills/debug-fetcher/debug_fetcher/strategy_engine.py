"""Strategy exhaustion engine for resilient URL fetching.

Tries multiple strategies in order until one succeeds or all fail.
Integrates with /memory for learned strategy prioritization.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from .memory_bridge import get_best_strategy_for_url, learn_strategy
from .memory_schema import FetchStrategy
from .pdf_bridge import (
    is_pdf_url,
    check_pdf_health,
    notify_debug_pdf,
    notify_fetch_failure_for_pdf,
)


# Path to skills
FETCHER_SKILL_PATH = Path(__file__).parent.parent.parent / "fetcher" / "run.sh"
YOUTUBE_SKILL_PATH = Path(__file__).parent.parent.parent / "ingest-youtube" / "run.sh"

# Strategy order (default)
DEFAULT_STRATEGIES = [
    "direct",
    "playwright",
    "wayback",
    "brave",
    "jina",
    "proxy",
    "ua_rotation",
]

# Domains that need special handling
YOUTUBE_DOMAINS = {"youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com"}

# Max retries per strategy
MAX_RETRIES = int(os.getenv("LEARN_FETCHER_MAX_RETRIES", "2"))


@dataclass
class FetchAttempt:
    """Result of a single fetch attempt."""

    url: str
    strategy: str
    success: bool
    status_code: int = 0
    content_verdict: str = ""
    content_length: int = 0
    timing_ms: int = 0
    error: str = ""
    file_path: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategyResult:
    """Final result after exhausting strategies."""

    url: str
    success: bool
    winning_strategy: str = ""
    attempts: List[FetchAttempt] = field(default_factory=list)
    final_attempt: Optional[FetchAttempt] = None


class StrategyEngine:
    """Engine for exhausting fetch strategies until success.

    Integrates with /memory to:
    1. Check for learned strategies before trying defaults
    2. Store successful strategies for future use
    """

    def __init__(
        self,
        strategies: Optional[List[str]] = None,
        max_retries: int = MAX_RETRIES,
        enable_memory: bool = True,
    ):
        """Initialize strategy engine.

        Args:
            strategies: List of strategies to try (default: all)
            max_retries: Max retries per strategy
            enable_memory: Whether to use /memory for learning
        """
        self.strategies = strategies or DEFAULT_STRATEGIES
        self.max_retries = max_retries
        self.enable_memory = enable_memory

    def _is_youtube_url(self, url: str) -> bool:
        """Check if URL is a YouTube video."""
        try:
            parsed = urlparse(url)
            return (parsed.hostname or "").lower().replace("www.", "") in {
                "youtube.com", "youtu.be", "m.youtube.com"
            }
        except Exception:
            return False

    def _run_youtube_skill(self, url: str, timeout: int = 120) -> FetchAttempt:
        """Fetch YouTube content via /ingest-youtube skill.

        Args:
            url: YouTube URL
            timeout: Fetch timeout

        Returns:
            FetchAttempt with transcript or error
        """
        import time
        import json

        start = time.time()

        if not YOUTUBE_SKILL_PATH.exists():
            return FetchAttempt(
                url=url,
                strategy="youtube",
                success=False,
                error="ingest-youtube skill not found",
            )

        try:
            result = subprocess.run(
                [str(YOUTUBE_SKILL_PATH), "transcript", url],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=YOUTUBE_SKILL_PATH.parent,
            )

            timing_ms = int((time.time() - start) * 1000)

            # Check for success
            if result.returncode == 0 and result.stdout.strip():
                return FetchAttempt(
                    url=url,
                    strategy="youtube",
                    success=True,
                    content_length=len(result.stdout),
                    timing_ms=timing_ms,
                    metadata={"transcript": result.stdout},
                )

            return FetchAttempt(
                url=url,
                strategy="youtube",
                success=False,
                timing_ms=timing_ms,
                error=result.stderr or "No transcript returned",
            )

        except subprocess.TimeoutExpired:
            return FetchAttempt(
                url=url,
                strategy="youtube",
                success=False,
                error="Timeout",
                timing_ms=timeout * 1000,
            )
        except Exception as e:
            return FetchAttempt(
                url=url,
                strategy="youtube",
                success=False,
                error=str(e),
            )

    def _run_fetcher(
        self,
        url: str,
        strategy: str,
        timeout: int = 60,
    ) -> FetchAttempt:
        """Run fetcher with a specific strategy.

        Args:
            url: Target URL
            strategy: Strategy name
            timeout: Fetch timeout in seconds

        Returns:
            FetchAttempt with result
        """
        import time

        start = time.time()

        # Build environment for strategy
        env = os.environ.copy()

        if strategy == "playwright":
            env["FETCHER_FORCE_PLAYWRIGHT"] = "1"
        elif strategy == "wayback":
            env["FETCHER_USE_WAYBACK"] = "1"
        elif strategy == "brave":
            env["FETCHER_USE_BRAVE_ALTERNATES"] = "1"
        elif strategy == "jina":
            env["FETCHER_USE_JINA"] = "1"
        elif strategy == "proxy":
            # Proxy env vars should already be set
            env["FETCHER_USE_PROXY"] = "1"
        elif strategy == "ua_rotation":
            env["FETCHER_ROTATE_USER_AGENT"] = "1"

        try:
            result = subprocess.run(
                [str(FETCHER_SKILL_PATH), "get", url, "--json"],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                cwd=FETCHER_SKILL_PATH.parent,
            )

            timing_ms = int((time.time() - start) * 1000)

            # Parse output
            output = result.stdout.strip()
            if output:
                import json
                try:
                    data = json.loads(output)
                    return FetchAttempt(
                        url=url,
                        strategy=strategy,
                        success=data.get("content_verdict") == "ok",
                        status_code=data.get("status", 0),
                        content_verdict=data.get("content_verdict", ""),
                        content_length=len(data.get("text", "")),
                        timing_ms=timing_ms,
                        file_path=data.get("file_path", ""),
                        metadata=data,
                    )
                except json.JSONDecodeError:
                    pass

            # Non-JSON output or parse failure
            return FetchAttempt(
                url=url,
                strategy=strategy,
                success=result.returncode == 0,
                timing_ms=timing_ms,
                error=result.stderr if result.returncode != 0 else "",
            )

        except subprocess.TimeoutExpired:
            return FetchAttempt(
                url=url,
                strategy=strategy,
                success=False,
                error="Timeout",
                timing_ms=timeout * 1000,
            )
        except Exception as e:
            return FetchAttempt(
                url=url,
                strategy=strategy,
                success=False,
                error=str(e),
            )

    def exhaust_strategies(self, url: str) -> StrategyResult:
        """Try all strategies until one succeeds.

        Args:
            url: Target URL

        Returns:
            StrategyResult with winning strategy or all_failed
        """
        result = StrategyResult(url=url, success=False)

        # 0. Special case: YouTube URLs use /ingest-youtube skill first
        if self._is_youtube_url(url):
            attempt = self._run_youtube_skill(url)
            result.attempts.append(attempt)
            if attempt.success:
                result.success = True
                result.winning_strategy = "youtube"
                result.final_attempt = attempt
                if self.enable_memory:
                    learn_strategy(url=url, strategy_used="youtube", timing_ms=attempt.timing_ms)
                return result

        # 1. Check /memory for learned strategy
        learned_strategy = None
        if self.enable_memory:
            learned = get_best_strategy_for_url(url)
            if learned:
                learned_strategy = learned.successful_strategy

        # 2. Build strategy order
        strategies_to_try = []

        # Put learned strategy first (if exists and not already first)
        if learned_strategy and learned_strategy in self.strategies:
            strategies_to_try.append(learned_strategy)

        # Add remaining strategies
        for s in self.strategies:
            if s not in strategies_to_try:
                strategies_to_try.append(s)

        # 3. Try each strategy
        for strategy in strategies_to_try:
            for attempt_num in range(self.max_retries):
                attempt = self._run_fetcher(url, strategy)
                result.attempts.append(attempt)

                if attempt.success:
                    result.success = True
                    result.winning_strategy = strategy
                    result.final_attempt = attempt

                    # Store in /memory if this worked
                    if self.enable_memory:
                        learn_strategy(
                            url=url,
                            strategy_used=strategy,
                            timing_ms=attempt.timing_ms,
                        )

                    # Check PDF health if this was a PDF URL
                    # This helps debug-pdf know about potential issues before extraction
                    if is_pdf_url(url) and attempt.file_path:
                        try:
                            from pathlib import Path
                            pdf_path = Path(attempt.file_path)
                            if pdf_path.exists():
                                pdf_bytes = pdf_path.read_bytes()
                                health = check_pdf_health(pdf_bytes)
                                if health.get("issues"):
                                    notify_debug_pdf(
                                        url=url,
                                        issues=health["issues"],
                                        fetch_strategy=strategy,
                                        additional_context=f"Page count: {health.get('page_count', 'unknown')}, Has text: {health.get('has_text', 'unknown')}",
                                    )
                        except Exception:
                            pass  # Don't fail the fetch due to health check errors

                    return result

                # If not a transient error, don't retry this strategy
                if attempt.error and "Timeout" not in attempt.error:
                    break

        # All strategies failed
        result.winning_strategy = "all_failed"
        if result.attempts:
            result.final_attempt = result.attempts[-1]

        # Notify debug-pdf if this was a PDF URL that failed
        if is_pdf_url(url):
            strategies_tried = [a.strategy for a in result.attempts]
            error = result.final_attempt.error if result.final_attempt else "Unknown error"
            notify_fetch_failure_for_pdf(url, error, strategies_tried)

        return result

    async def exhaust_strategies_async(self, url: str) -> StrategyResult:
        """Async version of exhaust_strategies.

        Useful when fetching multiple URLs concurrently.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.exhaust_strategies, url)

    def fetch_batch(
        self,
        urls: List[str],
        concurrency: int = 4,
    ) -> List[StrategyResult]:
        """Fetch multiple URLs with strategy exhaustion.

        Args:
            urls: List of URLs to fetch
            concurrency: Max concurrent fetches

        Returns:
            List of StrategyResult for each URL
        """
        async def _fetch_all():
            semaphore = asyncio.Semaphore(concurrency)

            async def _fetch_one(url: str) -> StrategyResult:
                async with semaphore:
                    return await self.exhaust_strategies_async(url)

            tasks = [_fetch_one(url) for url in urls]
            return await asyncio.gather(*tasks)

        return asyncio.run(_fetch_all())


def exhaust_strategies(url: str, enable_memory: bool = True) -> Tuple[bool, str, Dict[str, Any]]:
    """Convenience function to exhaust strategies for a URL.

    Args:
        url: Target URL
        enable_memory: Whether to use /memory

    Returns:
        Tuple of (success, winning_strategy, metadata)
    """
    engine = StrategyEngine(enable_memory=enable_memory)
    result = engine.exhaust_strategies(url)

    metadata = {}
    if result.final_attempt:
        metadata = {
            "status_code": result.final_attempt.status_code,
            "content_verdict": result.final_attempt.content_verdict,
            "content_length": result.final_attempt.content_length,
            "timing_ms": result.final_attempt.timing_ms,
            "file_path": result.final_attempt.file_path,
            "attempts": len(result.attempts),
        }

    return result.success, result.winning_strategy, metadata
