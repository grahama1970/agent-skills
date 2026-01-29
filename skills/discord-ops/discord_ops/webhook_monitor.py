#!/usr/bin/env python3
"""
Discord Operations - Webhook Monitor Module

Webhook forwarding and Discord bot monitoring functionality.
"""

import asyncio
import os
from datetime import datetime, timezone
from typing import Any, Optional

from discord_ops.config import (
    MAX_RETRIES,
    RETRY_BASE_DELAY,
    SKILL_DIR,
    logger,
)
from discord_ops.graph_persistence import log_match
from discord_ops.keyword_matcher import KeywordMatch, match_keywords
from discord_ops.utils import load_config, load_keywords, webhook_limiter

__all__ = [
    "forward_to_webhook",
    "run_monitor",
    "is_monitor_running",
    "stop_monitor",
    "get_feature_status",
]


# =============================================================================
# OPTIONAL IMPORTS
# =============================================================================

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

try:
    import discord
    from discord.ext import commands
    DISCORD_PY_AVAILABLE = True
except ImportError:
    DISCORD_PY_AVAILABLE = False


# =============================================================================
# WEBHOOK FORWARDING
# =============================================================================

async def forward_to_webhook(
    url: str,
    match: KeywordMatch,
    max_retries: int = MAX_RETRIES
) -> bool:
    """Forward match to webhook endpoint with retry logic.

    Includes rate limiting and exponential backoff for transient failures.

    Args:
        url: Webhook URL to forward to
        match: The keyword match to forward
        max_retries: Maximum retry attempts

    Returns:
        True if successful, False otherwise
    """
    if not HTTPX_AVAILABLE:
        logger.error("httpx not installed for webhook forwarding")
        return False

    # Apply rate limiting
    webhook_limiter.acquire()

    # Determine payload based on webhook type
    if "discord.com/api/webhooks" in url:
        payload = {"embeds": [match.to_discord_embed()]}
    else:
        payload = match.to_webhook_payload()

    last_error: Optional[Exception] = None
    # Reuse AsyncClient across retries for connection pooling
    async with httpx.AsyncClient() as client:
        for attempt in range(1, max_retries + 1):
            try:
                response = await client.post(url, json=payload, timeout=10.0)

                # Handle Discord rate limiting
                if response.status_code == 429:
                    # Prefer header, fallback to JSON body
                    retry_after = response.headers.get("Retry-After")
                    if retry_after is not None:
                        delay = float(retry_after)
                    else:
                        try:
                            body = response.json()
                            delay = float(body.get("retry_after", 5))
                        except Exception:
                            delay = 5.0
                    logger.warning(f"Discord rate limited, waiting {delay}s")
                    await asyncio.sleep(delay)
                    continue

                if response.status_code in (200, 204):
                    return True

                logger.warning(f"Webhook returned {response.status_code} on attempt {attempt}")

            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        f"Webhook attempt {attempt}/{max_retries} failed: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"Webhook failed after {max_retries} attempts: {e}")

    if last_error:
        logger.error(f"Webhook error: {last_error}")
    return False


# =============================================================================
# DISCORD BOT MONITOR
# =============================================================================

async def run_monitor(
    token: str,
    webhook_url: str | None,
    dry_run: bool,
    persist: bool = True,
    console: Any | None = None,
) -> None:
    """Run the Discord monitor bot.

    Args:
        token: Discord bot token
        webhook_url: Optional webhook URL to forward matches to
        dry_run: If True, log matches but don't forward
        persist: If True, persist matches to memory
        console: Optional rich console for output
    """
    if not DISCORD_PY_AVAILABLE:
        logger.error("discord.py not installed")
        return

    # Import locally to avoid import errors when discord.py isn't installed
    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True

    bot = commands.Bot(command_prefix="!", intents=intents)
    keywords = load_keywords()
    config = load_config()
    monitored_guilds = set(config.get("monitored_guilds", {}).keys())

    def log_output(message: str) -> None:
        """Output to console or logger."""
        if console:
            console.print(message)
        else:
            # Strip rich markup for logger
            import re
            clean = re.sub(r'\[/?[^\]]+\]', '', message)
            logger.info(clean)

    @bot.event
    async def on_ready():
        log_output(f"[green]Connected as {bot.user}[/green]")
        log_output(f"  Monitoring {len(monitored_guilds)} guilds")
        log_output(f"  Watching {len(keywords)} keyword patterns")
        log_output(f"  Memory persist: {persist}")

        # Save PID
        pid_file = SKILL_DIR / "monitor.pid"
        pid_file.write_text(str(os.getpid()))

    @bot.event
    async def on_message(message: discord.Message):
        # Ignore bot messages
        if message.author.bot:
            return

        # Only monitor configured guilds (or all if none configured)
        if monitored_guilds and str(message.guild.id) not in monitored_guilds:
            return

        # Check for keyword matches
        content = message.content or ""
        matched = match_keywords(content, keywords)

        if not matched:
            return

        # Create match record
        match = KeywordMatch(
            timestamp=datetime.now(timezone.utc).isoformat(),
            guild_id=str(message.guild.id) if message.guild else "",
            guild_name=message.guild.name if message.guild else "DM",
            channel_id=str(message.channel.id),
            channel_name=getattr(message.channel, 'name', 'unknown'),
            author=str(message.author),
            content=content[:2000],
            matched_keywords=matched,
            message_url=message.jump_url,
        )

        # Log the match (and optionally persist to memory)
        result = log_match(match, persist=persist)
        log_output(f"[cyan]Match:[/cyan] {matched} in #{match.channel_name}")

        if persist and result.get("memory", {}).get("stored"):
            log_output("  [green]Persisted to memory[/green]")
        elif persist and result.get("memory", {}).get("error"):
            error_msg = result['memory']['error'][:50]
            log_output(f"  [yellow]Memory error: {error_msg}[/yellow]")

        # Forward to webhook (unless dry run)
        if webhook_url and not dry_run:
            success = await forward_to_webhook(webhook_url, match)
            if success:
                log_output("  [green]Forwarded to webhook[/green]")
            else:
                log_output("  [red]Webhook forward failed[/red]")

    try:
        await bot.start(token)
    except KeyboardInterrupt:
        await bot.close()
    finally:
        pid_file = SKILL_DIR / "monitor.pid"
        if pid_file.exists():
            pid_file.unlink()


def is_monitor_running() -> tuple[bool, str | None]:
    """Check if monitor is currently running.

    Returns:
        Tuple of (is_running, pid_or_none)
    """
    pid_file = SKILL_DIR / "monitor.pid"
    if pid_file.exists():
        pid = pid_file.read_text().strip()
        # Verify process is actually running
        try:
            os.kill(int(pid), 0)
            return True, pid
        except (ProcessLookupError, ValueError):
            # PID file exists but process is dead
            pid_file.unlink()
            return False, None
    return False, None


def stop_monitor() -> tuple[bool, str]:
    """Stop the running monitor.

    Returns:
        Tuple of (success, message)
    """
    pid_file = SKILL_DIR / "monitor.pid"
    if pid_file.exists():
        pid = pid_file.read_text().strip()
        try:
            os.kill(int(pid), 15)  # SIGTERM
            pid_file.unlink()
            return True, f"Stopped monitor (PID: {pid})"
        except ProcessLookupError:
            pid_file.unlink()
            return False, "Monitor was not running"
        except ValueError:
            pid_file.unlink()
            return False, "Invalid PID in file"
    return False, "Monitor not running"


# =============================================================================
# FEATURE FLAGS
# =============================================================================

def get_feature_status() -> dict[str, bool]:
    """Get status of optional features."""
    return {
        "discord_py": DISCORD_PY_AVAILABLE,
        "httpx": HTTPX_AVAILABLE,
    }
