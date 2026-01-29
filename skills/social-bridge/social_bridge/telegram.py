"""
Social Bridge Telegram Module

Handles all Telegram channel monitoring and message fetching via Telethon/MTProto.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone

from social_bridge.config import TELEGRAM_SESSION, DEFAULT_TELEGRAM_CHANNELS
from social_bridge.utils import SocialPost, telegram_limiter

logger = logging.getLogger("social-bridge.telegram")

# Optional: Telethon for Telegram
try:
    from telethon import TelegramClient
    from telethon.tl.types import Channel, Message
    TELETHON_AVAILABLE = True
except ImportError:
    TELETHON_AVAILABLE = False
    TelegramClient = None  # type: ignore


def check_telethon_available() -> bool:
    """Check if Telethon is installed."""
    return TELETHON_AVAILABLE


def get_telegram_credentials() -> tuple[str | None, str | None]:
    """Get Telegram API credentials from environment.

    Returns:
        Tuple of (api_id, api_hash) or (None, None) if not set.
    """
    api_id = os.environ.get("TELEGRAM_API_ID")
    api_hash = os.environ.get("TELEGRAM_API_HASH")
    return api_id, api_hash


def normalize_channel_name(channel: str) -> str:
    """Normalize a Telegram channel name.

    Removes URL prefixes and @ symbols.

    Args:
        channel: Channel identifier (URL, @name, or name)

    Returns:
        Clean channel username
    """
    return channel.replace("https://t.me/", "").replace("@", "").strip("/")


async def fetch_telegram_channels(
    api_id: int,
    api_hash: str,
    channels: list[str],
    limit: int = 50,
) -> list[SocialPost]:
    """Fetch messages from Telegram channels using Telethon.

    Includes rate limiting between channel fetches to respect Telegram API limits.

    Args:
        api_id: Telegram API ID
        api_hash: Telegram API hash
        channels: List of channel usernames to fetch
        limit: Maximum messages per channel

    Returns:
        List of SocialPost objects sorted by timestamp (newest first)
    """
    if not TELETHON_AVAILABLE:
        logger.error("Telethon not installed, cannot fetch Telegram channels")
        return []

    posts = []

    async with TelegramClient(str(TELEGRAM_SESSION), api_id, api_hash) as client:
        for i, channel_name in enumerate(channels):
            # Rate limit between channels (Telegram is strict about flood limits)
            if i > 0:
                telegram_limiter.acquire()

            try:
                logger.debug(f"Fetching Telegram channel: @{channel_name}")
                entity = await client.get_entity(channel_name)

                async for message in client.iter_messages(entity, limit=limit):
                    if message.text:
                        posts.append(SocialPost(
                            platform="telegram",
                            source=channel_name,
                            author=getattr(entity, 'title', channel_name),
                            content=message.text,
                            url=f"https://t.me/{channel_name}/{message.id}",
                            timestamp=message.date.replace(tzinfo=timezone.utc),
                            metadata={
                                "views": getattr(message, 'views', 0),
                                "forwards": getattr(message, 'forwards', 0),
                            }
                        ))
                logger.info(f"Fetched {limit} messages from @{channel_name}")
            except Exception as e:
                logger.warning(f"Error fetching @{channel_name}: {e}")

    return sorted(posts, key=lambda p: p.timestamp, reverse=True)


def fetch_channels_sync(
    api_id: int,
    api_hash: str,
    channels: list[str],
    limit: int = 50,
) -> list[SocialPost]:
    """Synchronous wrapper for fetch_telegram_channels.

    Args:
        api_id: Telegram API ID
        api_hash: Telegram API hash
        channels: List of channel usernames to fetch
        limit: Maximum messages per channel

    Returns:
        List of SocialPost objects sorted by timestamp (newest first)
    """
    return asyncio.run(fetch_telegram_channels(api_id, api_hash, channels, limit))


def get_default_channels() -> list[dict]:
    """Get list of default security-focused Telegram channels.

    Returns:
        List of dicts with 'name' and 'focus' keys
    """
    return DEFAULT_TELEGRAM_CHANNELS.copy()
