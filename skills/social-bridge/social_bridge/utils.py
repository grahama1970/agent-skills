"""
Social Bridge Utilities Module

Common utilities including:
- Retry logic with exponential backoff
- Rate limiting
- Sensitive data redaction
- Security tag extraction
"""

import functools
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, TypeVar

from social_bridge.config import (
    MAX_RETRIES,
    RETRY_BASE_DELAY,
    RATE_LIMIT_RPS,
    REDACT_FIELDS,
    SECURITY_KEYWORDS,
    PLATFORM_COLORS,
)

logger = logging.getLogger("social-bridge.utils")

T = TypeVar("T")


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class SocialPost:
    """Unified post from any platform."""
    platform: str  # "telegram" or "x"
    source: str    # channel/account name
    author: str
    content: str
    url: str
    timestamp: datetime
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "platform": self.platform,
            "source": self.source,
            "author": self.author,
            "content": self.content,
            "url": self.url,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    def to_discord_embed(self) -> dict:
        """Convert to Discord webhook embed format."""
        color = PLATFORM_COLORS.get(self.platform, PLATFORM_COLORS["default"])
        return {
            "title": f"{self.platform.upper()}: {self.source}",
            "description": self.content[:2000],  # Discord limit
            "url": self.url,
            "color": color,
            "author": {"name": self.author},
            "timestamp": self.timestamp.isoformat(),
            "footer": {"text": self.platform.capitalize()},
        }


# =============================================================================
# SENSITIVE DATA HANDLING
# =============================================================================

def redact_sensitive(data: Any) -> Any:
    """Redact sensitive fields from dict-like input for safe logging."""
    if not isinstance(data, dict):
        return data
    return {
        k: "***REDACTED***" if k.lower() in REDACT_FIELDS else v
        for k, v in data.items()
    }


# =============================================================================
# RETRY LOGIC
# =============================================================================

def with_retries(
    func: Callable[..., T] = None,
    max_attempts: int = MAX_RETRIES,
    base_delay: float = RETRY_BASE_DELAY,
) -> Callable[..., T]:
    """Decorator that adds retry logic with exponential backoff.

    Can be used as @with_retries or @with_retries(max_attempts=5).

    Retries on transient errors (subprocess failures, network issues).
    """
    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_error: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt < max_attempts:
                        delay = base_delay * (2 ** (attempt - 1))
                        logger.warning(
                            f"Attempt {attempt}/{max_attempts} failed for {fn.__name__}: {e}. "
                            f"Retrying in {delay:.1f}s..."
                        )
                        time.sleep(delay)
                    else:
                        logger.error(f"{fn.__name__} failed after {max_attempts} attempts: {e}")
            raise last_error  # type: ignore
        return wrapper

    # Support both @with_retries and @with_retries()
    if func is not None:
        return decorator(func)
    return decorator


# =============================================================================
# RATE LIMITING
# =============================================================================

class RateLimiter:
    """Simple token-bucket rate limiter for API calls."""

    def __init__(self, requests_per_second: int = RATE_LIMIT_RPS):
        self.interval = 1.0 / max(1, requests_per_second)
        self.last_request = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """Block until rate limit allows next request."""
        with self._lock:
            now = time.time()
            sleep_time = max(0.0, (self.last_request + self.interval) - now)
            if sleep_time > 0:
                time.sleep(sleep_time)
            self.last_request = time.time()

    def __enter__(self) -> "RateLimiter":
        self.acquire()
        return self

    def __exit__(self, *args: Any) -> None:
        pass


# Global rate limiters for different services
telegram_limiter = RateLimiter(requests_per_second=3)  # Telegram is strict
discord_limiter = RateLimiter(requests_per_second=5)   # Discord webhooks


# =============================================================================
# SECURITY TAG EXTRACTION
# =============================================================================

def extract_security_tags(content: str) -> list[str]:
    """Extract security-related tags from content.

    Uses regex patterns defined in config.SECURITY_KEYWORDS to identify
    security-related topics in the content.

    Args:
        content: Text content to analyze

    Returns:
        List of security tags found in the content
    """
    tags = set()
    for pattern, tag in SECURITY_KEYWORDS:
        if re.search(pattern, content, re.IGNORECASE):
            tags.add(tag)
    return list(tags)
