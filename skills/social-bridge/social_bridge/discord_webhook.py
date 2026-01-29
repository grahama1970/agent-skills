"""
Social Bridge Discord Webhook Module

Handles Discord webhook delivery with rate limiting and retry logic.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from social_bridge.utils import SocialPost, discord_limiter, with_retries

logger = logging.getLogger("social-bridge.discord")

# Optional: httpx for Discord webhooks
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    httpx = None  # type: ignore


def check_httpx_available() -> bool:
    """Check if httpx is installed."""
    return HTTPX_AVAILABLE


def validate_webhook_url(url: str) -> bool:
    """Validate that a URL is a valid Discord webhook URL.

    Args:
        url: The URL to validate

    Returns:
        True if valid Discord webhook URL
    """
    return url.startswith("https://discord.com/api/webhooks/")


def send_to_webhook(
    webhook_url: str,
    payload: dict[str, Any],
    use_rate_limiter: bool = True,
) -> bool:
    """Send a payload to a Discord webhook.

    Handles rate limiting and retries automatically.

    Args:
        webhook_url: Discord webhook URL
        payload: Webhook payload (content, embeds, etc.)
        use_rate_limiter: Whether to use the global rate limiter

    Returns:
        True if successful

    Raises:
        RuntimeError: If sending fails after retries
    """
    if not HTTPX_AVAILABLE:
        raise RuntimeError("httpx not installed - run: pip install httpx")

    if use_rate_limiter:
        discord_limiter.acquire()

    @with_retries
    def _send() -> bool:
        response = httpx.post(webhook_url, json=payload, timeout=10.0)

        if response.status_code == 429:  # Rate limited
            retry_after = int(response.headers.get("Retry-After", 5))
            logger.warning(f"Discord rate limited, waiting {retry_after}s")
            time.sleep(retry_after)
            raise RuntimeError("Rate limited by Discord")

        if response.status_code not in (200, 204):
            raise RuntimeError(f"Discord returned {response.status_code}: {response.text[:100]}")

        return True

    return _send()


def send_post(webhook_url: str, post: SocialPost) -> bool:
    """Send a SocialPost to a Discord webhook as an embed.

    Args:
        webhook_url: Discord webhook URL
        post: The SocialPost to send

    Returns:
        True if successful
    """
    payload = {"embeds": [post.to_discord_embed()]}
    return send_to_webhook(webhook_url, payload)


def send_posts(
    webhook_url: str,
    posts: list[SocialPost],
    on_error: Optional[Callable[[SocialPost, Exception], None]] = None,
) -> tuple[int, int]:
    """Send multiple posts to a Discord webhook.

    Args:
        webhook_url: Discord webhook URL
        posts: List of SocialPost objects
        on_error: Optional callback for errors (receives post, exception)

    Returns:
        Tuple of (sent_count, failed_count)
    """
    sent = 0
    failed = 0

    for post in posts:
        try:
            if send_post(webhook_url, post):
                sent += 1
        except Exception as e:
            failed += 1
            logger.error(f"Failed to send post to Discord: {e}")
            if on_error:
                on_error(post, e)

    return sent, failed


def send_test_message(webhook_url: str) -> bool:
    """Send a test message to verify webhook configuration.

    Args:
        webhook_url: Discord webhook URL

    Returns:
        True if successful
    """
    payload = {
        "content": "Social Bridge test message",
        "embeds": [{
            "title": "Test",
            "description": "This is a test message from social-bridge.",
            "color": 0x00FF00,  # Green
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }]
    }
    return send_to_webhook(webhook_url, payload, use_rate_limiter=False)


def create_embed(
    title: str,
    description: str,
    url: Optional[str] = None,
    color: int = 0x5865F2,
    author: Optional[str] = None,
    footer: Optional[str] = None,
    timestamp: Optional[datetime] = None,
) -> dict[str, Any]:
    """Create a Discord embed object.

    Args:
        title: Embed title
        description: Embed description (max 2000 chars)
        url: Optional URL for the title
        color: Embed color (hex integer)
        author: Optional author name
        footer: Optional footer text
        timestamp: Optional timestamp

    Returns:
        Discord embed dict
    """
    embed: dict[str, Any] = {
        "title": title,
        "description": description[:2000],
        "color": color,
    }

    if url:
        embed["url"] = url
    if author:
        embed["author"] = {"name": author}
    if footer:
        embed["footer"] = {"text": footer}
    if timestamp:
        embed["timestamp"] = timestamp.isoformat()

    return embed
