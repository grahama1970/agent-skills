"""Memory schema for fetch strategies.

Defines the FetchStrategy dataclass used to store and recall
successful fetching strategies in /memory.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class FetchStrategy:
    """A learned strategy for fetching URLs from a specific domain/path pattern.

    This is stored in /memory and recalled before fetching to apply
    known-good strategies proactively.
    """

    # Target identification
    domain: str
    path_pattern: str = "*"  # e.g., "/article/*", "/pdf/*", "*"

    # What worked
    successful_strategy: str = "direct"  # direct, playwright, wayback, brave, jina, proxy, ua_rotation

    # Request customization that helped
    headers: Dict[str, str] = field(default_factory=dict)
    cookies: Dict[str, str] = field(default_factory=dict)
    user_agent: Optional[str] = None

    # Performance metrics
    timing_ms: int = 0  # Average response time
    success_rate: float = 1.0  # 0.0 to 1.0
    failure_count: int = 0  # Total failures before success
    success_count: int = 1  # Total successes

    # Timestamps
    last_used: str = ""  # ISO format
    discovered_at: str = ""  # ISO format

    # Human-provided info (from /interview)
    human_provided: bool = False
    human_notes: str = ""
    credential_hint: str = ""  # e.g., "requires login" (not actual credentials)
    mirror_url: Optional[str] = None

    # Tags for filtering
    tags: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Set timestamps if not provided."""
        now = datetime.now(timezone.utc).isoformat()
        if not self.discovered_at:
            self.discovered_at = now
        if not self.last_used:
            self.last_used = now

    def to_memory_format(self) -> Dict[str, Any]:
        """Convert to format expected by /memory learn command.

        Returns dict with 'problem' and 'solution' keys for /memory storage.
        """
        return {
            "problem": f"Fetch strategy for {self.domain}{self.path_pattern}",
            "solution": json.dumps(asdict(self), default=str),
            "tags": self.tags + ["fetch_strategy", self.domain, self.successful_strategy],
            "scope": "fetcher_strategies",
        }

    @classmethod
    def from_memory_format(cls, item: Dict[str, Any]) -> Optional["FetchStrategy"]:
        """Parse a /memory recall result into a FetchStrategy.

        Args:
            item: A single item from /memory recall results

        Returns:
            FetchStrategy or None if parsing fails
        """
        try:
            solution = item.get("solution", "")
            if not solution:
                return None

            # Handle both JSON string and dict
            if isinstance(solution, str):
                data = json.loads(solution)
            else:
                data = solution

            # Extract fields with defaults
            return cls(
                domain=data.get("domain", ""),
                path_pattern=data.get("path_pattern", "*"),
                successful_strategy=data.get("successful_strategy", "direct"),
                headers=data.get("headers", {}),
                cookies=data.get("cookies", {}),
                user_agent=data.get("user_agent"),
                timing_ms=data.get("timing_ms", 0),
                success_rate=data.get("success_rate", 1.0),
                failure_count=data.get("failure_count", 0),
                success_count=data.get("success_count", 1),
                last_used=data.get("last_used", ""),
                discovered_at=data.get("discovered_at", ""),
                human_provided=data.get("human_provided", False),
                human_notes=data.get("human_notes", ""),
                credential_hint=data.get("credential_hint", ""),
                mirror_url=data.get("mirror_url"),
                tags=data.get("tags", []),
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            return None

    def update_stats(self, success: bool, timing_ms: int = 0) -> None:
        """Update statistics after a fetch attempt.

        Args:
            success: Whether the fetch succeeded
            timing_ms: Response time in milliseconds
        """
        self.last_used = datetime.now(timezone.utc).isoformat()

        if success:
            self.success_count += 1
            if timing_ms > 0:
                # Running average of timing
                total_timing = self.timing_ms * (self.success_count - 1)
                self.timing_ms = (total_timing + timing_ms) // self.success_count
        else:
            self.failure_count += 1

        # Recalculate success rate
        total = self.success_count + self.failure_count
        self.success_rate = self.success_count / total if total > 0 else 0.0

    def matches_url(self, url: str) -> bool:
        """Check if this strategy applies to a given URL.

        Args:
            url: Full URL to check

        Returns:
            True if this strategy should be tried for this URL
        """
        from urllib.parse import urlparse

        try:
            parsed = urlparse(url)
            host = (parsed.hostname or "").lower()
            path = parsed.path or "/"

            # Check domain match
            if self.domain not in host:
                return False

            # Check path pattern match
            if self.path_pattern == "*":
                return True

            # Simple wildcard matching
            pattern = self.path_pattern.replace("*", "")
            return path.startswith(pattern) or pattern in path

        except Exception:
            return False


@dataclass
class BatchAnalysis:
    """Analysis of a batch fetch run for pattern detection."""

    total_urls: int = 0
    successful: int = 0
    failed: int = 0

    # Failures grouped by reason
    by_status: Dict[int, List[str]] = field(default_factory=dict)  # status -> [urls]
    by_verdict: Dict[str, List[str]] = field(default_factory=dict)  # verdict -> [urls]
    by_domain: Dict[str, Dict[str, int]] = field(default_factory=dict)  # domain -> {status: count}

    # Patterns detected
    patterns: List[str] = field(default_factory=list)  # Human-readable pattern descriptions

    # URLs that need human help
    unrecoverable: List[str] = field(default_factory=list)


@dataclass
class RecoveryAction:
    """An action to take based on human input from /interview."""

    url: str
    action_type: str  # "credentials", "mirror", "manual_file", "skip", "retry"

    # Action-specific data
    credentials: Optional[Dict[str, str]] = None  # For "credentials" action
    mirror_url: Optional[str] = None  # For "mirror" action
    file_path: Optional[str] = None  # For "manual_file" action
    retry_after: Optional[int] = None  # For "retry" action (seconds to wait)

    notes: str = ""
