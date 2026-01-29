#!/usr/bin/env python3
"""
Discord Operations - Utility Functions

Common utilities: retry logic, rate limiting, redaction, config I/O.
"""

import functools
import json
import threading
import time
from typing import Any, Callable, Optional, TypeVar

from discord_ops.config import (
    CLAWDBOT_DIR,
    CONFIG_FILE,
    DEFAULT_KEYWORDS,
    KEYWORDS_FILE,
    MAX_RETRIES,
    RATE_LIMIT_RPS,
    REDACT_FIELDS,
    RETRY_BASE_DELAY,
    logger,
)


T = TypeVar("T")

__all__ = [
    "redact_sensitive",
    "with_retries",
    "RateLimiter",
    "webhook_limiter",
    "load_config",
    "save_config",
    "load_keywords",
    "save_keywords",
    "get_bot_token",
]


# =============================================================================
# SECURITY UTILITIES
# =============================================================================

def redact_sensitive(data: Any) -> Any:
    """Redact sensitive fields from dict for safe logging."""
    if not isinstance(data, dict):
        return data
    return {
        k: ("***REDACTED***" if isinstance(k, str) and k.lower() in REDACT_FIELDS else v)
        for k, v in data.items()
    }


# =============================================================================
# RETRY DECORATOR
# =============================================================================

def with_retries(
    func: Callable[..., T],
    max_attempts: int = MAX_RETRIES,
    base_delay: float = RETRY_BASE_DELAY,
) -> Callable[..., T]:
    """Decorator that adds retry logic with exponential backoff.

    Retries on transient errors (subprocess failures, network issues).
    """
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        last_error: Optional[Exception] = None
        for attempt in range(1, max_attempts + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < max_attempts:
                    delay = base_delay * (2 ** (attempt - 1))
                    logger.warning(
                        f"Attempt {attempt}/{max_attempts} failed for {func.__name__}: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                else:
                    logger.error(f"{func.__name__} failed after {max_attempts} attempts: {e}")
        raise last_error  # type: ignore
    return wrapper


# =============================================================================
# RATE LIMITER
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


# Global rate limiter for Discord webhook calls
webhook_limiter = RateLimiter(requests_per_second=RATE_LIMIT_RPS)


# =============================================================================
# CONFIGURATION I/O
# =============================================================================

def load_config() -> dict[str, Any]:
    """Load configuration."""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except json.JSONDecodeError:
            logger.warning("Invalid config.json, using defaults")
    return {
        "monitored_guilds": {},  # guild_id -> {name, channels: [channel_ids]}
        "webhooks": {},          # name -> url
        "bot_token": None,       # Discord bot token (or use env)
    }


def save_config(config: dict[str, Any]) -> None:
    """Save configuration."""
    CONFIG_FILE.write_text(json.dumps(config, indent=2))


def load_keywords() -> list[str]:
    """Load keyword patterns."""
    if KEYWORDS_FILE.exists():
        try:
            data = json.loads(KEYWORDS_FILE.read_text())
            patterns = data.get("patterns")
            if isinstance(patterns, list):
                return patterns
            logger.warning("keywords.json 'patterns' invalid, using defaults")
        except json.JSONDecodeError:
            logger.warning("Invalid keywords.json, using defaults")
    return DEFAULT_KEYWORDS


def save_keywords(patterns: list[str]) -> None:
    """Save keyword patterns."""
    KEYWORDS_FILE.write_text(json.dumps({"patterns": patterns}, indent=2))


def get_bot_token() -> str | None:
    """Get Discord bot token from config or env.

    Priority:
    1. DISCORD_BOT_TOKEN environment variable
    2. bot_token in config.json
    3. DISCORD_BOT_TOKEN from clawdbot .env
    """
    import os

    # Try env first
    if token := os.environ.get("DISCORD_BOT_TOKEN"):
        return token

    # Try config
    config = load_config()
    if token := config.get("bot_token"):
        return token

    # Try clawdbot .env
    env_file = CLAWDBOT_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("DISCORD_BOT_TOKEN="):
                return line.split("=", 1)[1].strip()

    return None
