#!/usr/bin/env python3
"""
Social Bridge - Security Content Aggregator

Aggregates security content from:
- Telegram public channels (via Telethon/MTProto)
- X/Twitter accounts (via surf browser automation)

Forwards to Discord webhooks for centralized monitoring.
Persists content to graph-memory for knowledge graph integration.
"""

import asyncio
import functools
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

# Configure logging - don't log tokens or sensitive data
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("social-bridge")

T = TypeVar("T")

try:
    import typer
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
except ImportError:
    print("Missing requirements. Run: pip install typer rich", file=sys.stderr)
    sys.exit(1)

# Optional: Telethon for Telegram
try:
    from telethon import TelegramClient
    from telethon.tl.functions.messages import GetHistoryRequest
    from telethon.tl.types import Channel, Message
    TELETHON_AVAILABLE = True
except ImportError:
    TELETHON_AVAILABLE = False

# Optional: httpx for Discord webhooks
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

# =============================================================================
# RESILIENCE UTILITIES (from code review recommendations)
# =============================================================================

# Configurable via environment
MAX_RETRIES = int(os.environ.get("SOCIAL_BRIDGE_MAX_RETRIES", "3"))
RETRY_BASE_DELAY = float(os.environ.get("SOCIAL_BRIDGE_RETRY_DELAY", "0.5"))
RATE_LIMIT_RPS = int(os.environ.get("SOCIAL_BRIDGE_RATE_LIMIT_RPS", "3"))

# Fields to redact in logs
REDACT_FIELDS = {"token", "api_key", "api_hash", "password", "secret", "authorization"}


def redact_sensitive(data: dict[str, Any]) -> dict[str, Any]:
    """Redact sensitive fields from dict for safe logging."""
    if not isinstance(data, dict):
        return data
    return {
        k: "***REDACTED***" if k.lower() in REDACT_FIELDS else v
        for k, v in data.items()
    }


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
_telegram_limiter = RateLimiter(requests_per_second=3)  # Telegram is strict
_discord_limiter = RateLimiter(requests_per_second=5)   # Discord webhooks


# Memory integration - uses graph-memory project
MEMORY_ROOT = Path(os.environ.get("MEMORY_ROOT", Path.home() / "workspace/experiments/memory"))
MEMORY_SCOPE = "social_intel"

# Security keyword patterns for auto-tagging
SECURITY_KEYWORDS = [
    (r"CVE-\d{4}-\d+", "cve"),
    (r"APT\d+", "apt"),
    (r"DARPA|IARPA|BAA", "darpa"),
    (r"0-?day|zero.?day", "0day"),
    (r"exploit|RCE|LPE|privesc", "exploit"),
    (r"malware|ransomware|trojan|backdoor", "malware"),
    (r"HTB|Hack.?The.?Box|TryHackMe|CTF", "ctf"),
    (r"MITRE|ATT&CK|T\d{4}", "mitre"),
    (r"cobalt.?strike|C2|beacon", "c2"),
    (r"IOC|indicator", "ioc"),
]


def extract_security_tags(content: str) -> list[str]:
    """Extract security-related tags from content."""
    tags = set()
    content_lower = content.lower()
    for pattern, tag in SECURITY_KEYWORDS:
        if re.search(pattern, content, re.IGNORECASE):
            tags.add(tag)
    return list(tags)


def persist_to_memory(post: "SocialPost", tags: Optional[list[str]] = None) -> dict[str, Any]:
    """Persist a social post to graph-memory.

    Uses the memory skill's learn command to store posts as lessons.
    Returns the result of the learn operation.
    """
    # Auto-extract security tags from content
    auto_tags = extract_security_tags(post.content)
    all_tags = list(set((tags or []) + auto_tags + [post.platform, f"source:{post.source}"]))

    # Format problem as a searchable identifier
    problem = f"[{post.platform.upper()}] @{post.source}: {post.content[:100]}..."

    # Format solution with full content and metadata
    solution = json.dumps({
        "content": post.content,
        "url": post.url,
        "author": post.author,
        "timestamp": post.timestamp.isoformat(),
        "platform": post.platform,
        "source": post.source,
        "metadata": post.metadata,
    }, indent=2)

    # Call memory skill via CLI
    memory_skill = Path(__file__).parent.parent / "memory" / "run.sh"
    if not memory_skill.exists():
        # Try .pi/skills path
        memory_skill = Path(__file__).parent.parent / "memory" / "run.sh"

    if not memory_skill.exists():
        logger.warning("Memory skill not found, cannot persist post")
        return {"error": "memory skill not found", "stored": False}

    # Build command
    cmd = [
        str(memory_skill),
        "learn",
        "--problem", problem,
        "--solution", solution,
        "--scope", MEMORY_SCOPE,
    ]

    # Add tags
    for tag in all_tags:
        cmd.extend(["--tag", tag])

    @with_retries
    def _execute_learn() -> dict[str, Any]:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(memory_skill.parent),
        )
        if result.returncode != 0:
            raise RuntimeError(f"Memory learn failed: {result.stderr[:200]}")
        return {"stored": True, "tags": all_tags}

    try:
        return _execute_learn()
    except Exception as e:
        logger.error(f"Failed to persist to memory after retries: {e}")
        return {"stored": False, "error": str(e)}


def search_memory(query: str, k: int = 10) -> list[dict[str, Any]]:
    """Search memory for stored social intel.

    Returns matching posts from graph-memory.
    """
    memory_skill = Path(__file__).parent.parent / "memory" / "run.sh"

    if not memory_skill.exists():
        logger.debug("Memory skill not found, returning empty results")
        return []

    cmd = [
        str(memory_skill),
        "recall",
        "--q", query,
        "--scope", MEMORY_SCOPE,
        "--k", str(k),
    ]

    @with_retries
    def _execute_recall() -> list[dict[str, Any]]:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(memory_skill.parent),
        )
        if result.returncode != 0:
            raise RuntimeError(f"Memory recall failed: {result.stderr[:100]}")
        try:
            data = json.loads(result.stdout)
            return data.get("items", [])
        except json.JSONDecodeError:
            return []

    try:
        return _execute_recall()
    except Exception as e:
        logger.warning(f"Memory search failed after retries: {e}")
        return []


app = typer.Typer(help="Social Bridge - Security content aggregator")
telegram_app = typer.Typer(help="Telegram channel management")
x_app = typer.Typer(help="X/Twitter account management")
webhook_app = typer.Typer(help="Discord webhook management")
memory_app = typer.Typer(help="Memory/knowledge graph integration")

app.add_typer(telegram_app, name="telegram")
app.add_typer(x_app, name="x")
app.add_typer(webhook_app, name="webhook")
app.add_typer(memory_app, name="memory")

console = Console()

# Paths
DATA_DIR = Path(os.environ.get("SOCIAL_BRIDGE_DIR", Path.home() / ".social-bridge"))
CONFIG_FILE = DATA_DIR / "config.json"
CACHE_DIR = DATA_DIR / "cache"
TELEGRAM_SESSION = DATA_DIR / "telegram"

# Pre-configured security sources
DEFAULT_TELEGRAM_CHANNELS = [
    {"name": "vaborivs", "focus": "vulnerability research"},
    {"name": "exploitin", "focus": "exploit announcements"},
    {"name": "TheHackersNews", "focus": "security news"},
    {"name": "cikitech", "focus": "malware/threats"},
    {"name": "CISAgov", "focus": "CISA alerts"},
]

DEFAULT_X_ACCOUNTS = [
    {"name": "malwaretechblog", "focus": "malware analysis"},
    {"name": "SwiftOnSecurity", "focus": "security insights"},
    {"name": "0xdea", "focus": "vulnerability research"},
    {"name": "thegrugq", "focus": "opsec, threat intel"},
    {"name": "GossiTheDog", "focus": "threat intel"},
]


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
        color = 0x1DA1F2 if self.platform == "x" else 0x0088CC  # Twitter blue / Telegram blue
        return {
            "title": f"{self.platform.upper()}: {self.source}",
            "description": self.content[:2000],  # Discord limit
            "url": self.url,
            "color": color,
            "author": {"name": self.author},
            "timestamp": self.timestamp.isoformat(),
            "footer": {"text": self.platform.capitalize()},
        }


def load_config() -> dict[str, Any]:
    """Load configuration."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / "telegram").mkdir(exist_ok=True)
    (CACHE_DIR / "x").mkdir(exist_ok=True)

    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())

    return {
        "telegram_channels": [],
        "x_accounts": [],
        "webhooks": {},
        "last_fetch": {},
    }


def save_config(config: dict[str, Any]) -> None:
    """Save configuration."""
    CONFIG_FILE.write_text(json.dumps(config, indent=2))


# =============================================================================
# TELEGRAM COMMANDS
# =============================================================================

@telegram_app.command("add")
def telegram_add(channel: str = typer.Argument(..., help="Channel username or URL")):
    """Add a Telegram channel to monitor."""
    # Normalize channel name
    channel = channel.replace("https://t.me/", "").replace("@", "").strip("/")

    config = load_config()
    if channel not in config["telegram_channels"]:
        config["telegram_channels"].append(channel)
        save_config(config)
        console.print(f"[green]Added Telegram channel:[/green] @{channel}")
    else:
        console.print(f"[yellow]Channel already monitored:[/yellow] @{channel}")


@telegram_app.command("remove")
def telegram_remove(channel: str = typer.Argument(..., help="Channel to remove")):
    """Remove a Telegram channel."""
    channel = channel.replace("https://t.me/", "").replace("@", "").strip("/")

    config = load_config()
    if channel in config["telegram_channels"]:
        config["telegram_channels"].remove(channel)
        save_config(config)
        console.print(f"[green]Removed:[/green] @{channel}")
    else:
        console.print(f"[yellow]Not found:[/yellow] @{channel}")


@telegram_app.command("list")
def telegram_list():
    """List monitored Telegram channels."""
    config = load_config()
    channels = config.get("telegram_channels", [])

    if not channels:
        console.print("[yellow]No Telegram channels configured.[/yellow]")
        console.print("Add with: [bold]social-bridge telegram add @channel[/bold]")
        console.print("\nSuggested security channels:")
        for ch in DEFAULT_TELEGRAM_CHANNELS:
            console.print(f"  @{ch['name']} - {ch['focus']}")
        return

    table = Table(title="Monitored Telegram Channels")
    table.add_column("Channel", style="cyan")
    table.add_column("URL")

    for ch in channels:
        table.add_row(f"@{ch}", f"https://t.me/{ch}")

    console.print(table)


@telegram_app.command("fetch")
def telegram_fetch(
    channel: str = typer.Argument(None, help="Specific channel (or all)"),
    limit: int = typer.Option(50, "--limit", "-l", help="Messages per channel"),
    output_json: bool = typer.Option(False, "--json"),
    persist: bool = typer.Option(False, "--persist", "-p", help="Persist to memory/knowledge graph"),
):
    """Fetch messages from Telegram channels."""
    if not TELETHON_AVAILABLE:
        console.print("[red]Telethon not installed.[/red]")
        console.print("Install with: [bold]pip install telethon[/bold]")
        raise typer.Exit(1)

    api_id = os.environ.get("TELEGRAM_API_ID")
    api_hash = os.environ.get("TELEGRAM_API_HASH")

    if not api_id or not api_hash:
        console.print("[red]Telegram API credentials not set.[/red]")
        console.print("Get credentials at: https://my.telegram.org/apps")
        console.print("Then set: TELEGRAM_API_ID and TELEGRAM_API_HASH")
        raise typer.Exit(1)

    config = load_config()
    channels = [channel] if channel else config.get("telegram_channels", [])

    if not channels:
        console.print("[yellow]No channels to fetch.[/yellow]")
        return

    # Run async fetch
    posts = asyncio.run(_fetch_telegram_channels(int(api_id), api_hash, channels, limit))

    # Persist to memory if requested
    if persist:
        stored_count = 0
        with console.status("[bold green]Persisting to memory...") as status:
            for post in posts:
                result = persist_to_memory(post)
                if result.get("stored"):
                    stored_count += 1
        console.print(f"[green]Persisted {stored_count}/{len(posts)} posts to memory[/green]")

    if output_json:
        print(json.dumps([p.to_dict() for p in posts], indent=2))
    else:
        console.print(f"[green]Fetched {len(posts)} messages from {len(channels)} channels[/green]")
        for post in posts[:10]:
            console.print(f"\n[cyan]@{post.source}[/cyan] ({post.timestamp.strftime('%Y-%m-%d %H:%M')})")
            console.print(f"  {post.content[:200]}...")
            console.print(f"  [dim]{post.url}[/dim]")


async def _fetch_telegram_channels(api_id: int, api_hash: str, channels: list[str], limit: int) -> list[SocialPost]:
    """Fetch messages from Telegram channels using Telethon.

    Includes rate limiting between channel fetches to respect Telegram API limits.
    """
    posts = []

    async with TelegramClient(str(TELEGRAM_SESSION), api_id, api_hash) as client:
        for i, channel_name in enumerate(channels):
            # Rate limit between channels (Telegram is strict about flood limits)
            if i > 0:
                _telegram_limiter.acquire()

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
                console.print(f"[red]Error fetching @{channel_name}:[/red] {e}")

    return sorted(posts, key=lambda p: p.timestamp, reverse=True)


# =============================================================================
# X/TWITTER COMMANDS
# =============================================================================

@x_app.command("add")
def x_add(account: str = typer.Argument(..., help="X/Twitter username")):
    """Add an X/Twitter account to monitor."""
    account = account.replace("@", "").strip()

    config = load_config()
    if account not in config["x_accounts"]:
        config["x_accounts"].append(account)
        save_config(config)
        console.print(f"[green]Added X account:[/green] @{account}")
    else:
        console.print(f"[yellow]Account already monitored:[/yellow] @{account}")


@x_app.command("remove")
def x_remove(account: str = typer.Argument(..., help="Account to remove")):
    """Remove an X/Twitter account."""
    account = account.replace("@", "").strip()

    config = load_config()
    if account in config["x_accounts"]:
        config["x_accounts"].remove(account)
        save_config(config)
        console.print(f"[green]Removed:[/green] @{account}")
    else:
        console.print(f"[yellow]Not found:[/yellow] @{account}")


@x_app.command("list")
def x_list():
    """List monitored X/Twitter accounts."""
    config = load_config()
    accounts = config.get("x_accounts", [])

    if not accounts:
        console.print("[yellow]No X/Twitter accounts configured.[/yellow]")
        console.print("Add with: [bold]social-bridge x add username[/bold]")
        console.print("\nSuggested security accounts:")
        for acc in DEFAULT_X_ACCOUNTS:
            console.print(f"  @{acc['name']} - {acc['focus']}")
        return

    table = Table(title="Monitored X/Twitter Accounts")
    table.add_column("Account", style="cyan")
    table.add_column("URL")

    for acc in accounts:
        table.add_row(f"@{acc}", f"https://x.com/{acc}")

    console.print(table)


@x_app.command("fetch")
def x_fetch(
    account: str = typer.Argument(None, help="Specific account (or all)"),
    limit: int = typer.Option(50, "--limit", "-l", help="Tweets per account"),
    output_json: bool = typer.Option(False, "--json"),
):
    """Fetch tweets using surf browser automation."""
    # Check if surf is available
    surf_check = subprocess.run(["which", "surf"], capture_output=True)
    if surf_check.returncode != 0:
        console.print("[red]surf CLI not found.[/red]")
        console.print("Install surf-cli extension or use CDP fallback.")
        raise typer.Exit(1)

    config = load_config()
    accounts = [account] if account else config.get("x_accounts", [])

    if not accounts:
        console.print("[yellow]No accounts to fetch.[/yellow]")
        return

    posts = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        for acc in accounts:
            task = progress.add_task(f"Fetching @{acc}...", total=None)

            try:
                account_posts = _fetch_x_account(acc, limit)
                posts.extend(account_posts)
                progress.update(task, description=f"[green]@{acc}: {len(account_posts)} tweets[/green]")
            except Exception as e:
                progress.update(task, description=f"[red]@{acc}: {e}[/red]")

    if output_json:
        print(json.dumps([p.to_dict() for p in posts], indent=2))
    else:
        console.print(f"\n[green]Fetched {len(posts)} tweets from {len(accounts)} accounts[/green]")
        for post in posts[:10]:
            console.print(f"\n[cyan]@{post.source}[/cyan] ({post.timestamp.strftime('%Y-%m-%d %H:%M')})")
            console.print(f"  {post.content[:200]}...")
            console.print(f"  [dim]{post.url}[/dim]")


def _fetch_x_account(account: str, limit: int) -> list[SocialPost]:
    """Fetch tweets from X account using surf browser automation.

    Inspired by likes-sync approach - uses surf to navigate and inject
    JavaScript to extract tweet data from the DOM.
    """
    posts = []

    # Create a temporary JavaScript scraper
    scraper_js = """
    (function() {
        const tweets = [];
        const articles = document.querySelectorAll('article[data-testid="tweet"]');

        articles.forEach((article, index) => {
            if (index >= MAX_LIMIT) return;

            try {
                // Get author
                const authorEl = article.querySelector('[data-testid="User-Name"] a');
                const author = authorEl ? authorEl.textContent : 'unknown';

                // Get tweet text
                const textEl = article.querySelector('[data-testid="tweetText"]');
                const content = textEl ? textEl.textContent : '';

                // Get timestamp
                const timeEl = article.querySelector('time');
                const timestamp = timeEl ? timeEl.getAttribute('datetime') : new Date().toISOString();

                // Get tweet link
                const linkEl = article.querySelector('a[href*="/status/"]');
                const url = linkEl ? 'https://x.com' + linkEl.getAttribute('href') : '';

                // Get engagement metrics
                const metrics = {};
                const replyEl = article.querySelector('[data-testid="reply"]');
                const retweetEl = article.querySelector('[data-testid="retweet"]');
                const likeEl = article.querySelector('[data-testid="like"]');

                if (replyEl) metrics.replies = replyEl.textContent || '0';
                if (retweetEl) metrics.retweets = retweetEl.textContent || '0';
                if (likeEl) metrics.likes = likeEl.textContent || '0';

                if (content) {
                    tweets.push({
                        author: author,
                        content: content,
                        timestamp: timestamp,
                        url: url,
                        metrics: metrics
                    });
                }
            } catch (e) {
                console.error('Error parsing tweet:', e);
            }
        });

        return JSON.stringify(tweets);
    })();
    """.replace("MAX_LIMIT", str(limit))

    # Navigate to account page
    url = f"https://x.com/{account}"

    try:
        # Use surf to navigate
        subprocess.run(["surf", "go", url], capture_output=True, timeout=30)

        # Wait for page to load
        subprocess.run(["surf", "wait", "3"], capture_output=True, timeout=10)

        # Scroll to load more tweets
        for _ in range(min(limit // 10, 5)):
            subprocess.run(["surf", "scroll", "down"], capture_output=True, timeout=5)
            subprocess.run(["surf", "wait", "1"], capture_output=True, timeout=5)

        # Execute scraper JavaScript
        # Note: surf doesn't have direct JS execution, so we use CDP
        # For now, return empty and log the limitation
        console.print(f"[yellow]Note: Full X scraping requires CDP mode or likes-sync approach[/yellow]")

        # Alternative: Use surf read to get page content and parse
        result = subprocess.run(["surf", "text"], capture_output=True, text=True, timeout=30)

        if result.returncode == 0 and result.stdout:
            # Parse text content (basic extraction)
            # This is a simplified version - full implementation would use JS injection
            lines = result.stdout.split('\n')
            current_content = []

            for line in lines:
                line = line.strip()
                if line and len(line) > 20:  # Skip short lines
                    current_content.append(line)

            # Create a single aggregated post for now
            if current_content:
                posts.append(SocialPost(
                    platform="x",
                    source=account,
                    author=f"@{account}",
                    content="\n".join(current_content[:5]),  # First 5 substantial lines
                    url=url,
                    timestamp=datetime.now(timezone.utc),
                    metadata={"extraction": "basic_text"}
                ))

    except subprocess.TimeoutExpired:
        console.print(f"[red]Timeout fetching @{account}[/red]")
    except Exception as e:
        console.print(f"[red]Error fetching @{account}:[/red] {e}")

    return posts


# =============================================================================
# WEBHOOK COMMANDS
# =============================================================================

@webhook_app.command("add")
def webhook_add(
    name: str = typer.Argument(..., help="Webhook name"),
    url: str = typer.Argument(..., help="Discord webhook URL"),
):
    """Add a Discord webhook."""
    if not url.startswith("https://discord.com/api/webhooks/"):
        console.print("[red]Invalid webhook URL.[/red]")
        console.print("URL should start with: https://discord.com/api/webhooks/")
        raise typer.Exit(1)

    config = load_config()
    config["webhooks"][name] = url
    save_config(config)
    console.print(f"[green]Added webhook:[/green] {name}")


@webhook_app.command("remove")
def webhook_remove(name: str = typer.Argument(..., help="Webhook name")):
    """Remove a Discord webhook."""
    config = load_config()
    if name in config.get("webhooks", {}):
        del config["webhooks"][name]
        save_config(config)
        console.print(f"[green]Removed:[/green] {name}")
    else:
        console.print(f"[yellow]Not found:[/yellow] {name}")


@webhook_app.command("list")
def webhook_list():
    """List Discord webhooks."""
    config = load_config()
    webhooks = config.get("webhooks", {})

    if not webhooks:
        console.print("[yellow]No webhooks configured.[/yellow]")
        console.print("Add with: [bold]social-bridge webhook add name URL[/bold]")
        return

    table = Table(title="Discord Webhooks")
    table.add_column("Name", style="cyan")
    table.add_column("URL (truncated)")

    for name, url in webhooks.items():
        table.add_row(name, url[:50] + "...")

    console.print(table)


@webhook_app.command("test")
def webhook_test(name: str = typer.Argument(..., help="Webhook name")):
    """Test a Discord webhook."""
    if not HTTPX_AVAILABLE:
        console.print("[red]httpx not installed.[/red]")
        console.print("Install with: [bold]pip install httpx[/bold]")
        raise typer.Exit(1)

    config = load_config()
    url = config.get("webhooks", {}).get(name)

    if not url:
        console.print(f"[red]Webhook not found:[/red] {name}")
        raise typer.Exit(1)

    payload = {
        "content": "Social Bridge test message",
        "embeds": [{
            "title": "Test",
            "description": "This is a test message from social-bridge.",
            "color": 0x00FF00,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }]
    }

    try:
        response = httpx.post(url, json=payload)
        if response.status_code in (200, 204):
            console.print(f"[green]Webhook test successful![/green]")
        else:
            console.print(f"[red]Webhook failed:[/red] {response.status_code} - {response.text}")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")


# =============================================================================
# AGGREGATE COMMANDS
# =============================================================================

@app.command("fetch")
def fetch_all(
    telegram: bool = typer.Option(False, "--telegram", "-t", help="Fetch Telegram only"),
    x: bool = typer.Option(False, "--x", help="Fetch X/Twitter only"),
    hours: int = typer.Option(24, "--hours", "-h", help="Fetch posts from last N hours"),
    limit: int = typer.Option(50, "--limit", "-l", help="Posts per source"),
    output_json: bool = typer.Option(False, "--json"),
    persist: bool = typer.Option(False, "--persist", "-p", help="Persist to memory/knowledge graph"),
):
    """Fetch content from all sources."""
    fetch_telegram = telegram or (not telegram and not x)
    fetch_x = x or (not telegram and not x)

    all_posts: list[SocialPost] = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    if fetch_telegram:
        console.print("[bold]Fetching Telegram...[/bold]")
        # Invoke telegram fetch
        if TELETHON_AVAILABLE:
            api_id = os.environ.get("TELEGRAM_API_ID")
            api_hash = os.environ.get("TELEGRAM_API_HASH")
            if api_id and api_hash:
                config = load_config()
                channels = config.get("telegram_channels", [])
                if channels:
                    posts = asyncio.run(_fetch_telegram_channels(int(api_id), api_hash, channels, limit))
                    posts = [p for p in posts if p.timestamp >= cutoff]
                    all_posts.extend(posts)
                    console.print(f"  [green]Telegram: {len(posts)} posts[/green]")

    if fetch_x:
        console.print("[bold]Fetching X/Twitter...[/bold]")
        config = load_config()
        accounts = config.get("x_accounts", [])
        for acc in accounts:
            posts = _fetch_x_account(acc, limit)
            posts = [p for p in posts if p.timestamp >= cutoff]
            all_posts.extend(posts)
        console.print(f"  [green]X/Twitter: {len([p for p in all_posts if p.platform == 'x'])} posts[/green]")

    # Sort by timestamp
    all_posts.sort(key=lambda p: p.timestamp, reverse=True)

    # Persist to memory if requested
    if persist and all_posts:
        stored_count = 0
        with console.status("[bold green]Persisting to memory...") as status:
            for i, post in enumerate(all_posts):
                result = persist_to_memory(post)
                if result.get("stored"):
                    stored_count += 1
                status.update(f"[bold green]Persisting... {i+1}/{len(all_posts)}")
        console.print(f"[green]Persisted {stored_count}/{len(all_posts)} posts to memory[/green]")

    if output_json:
        print(json.dumps([p.to_dict() for p in all_posts], indent=2))
    else:
        console.print(f"\n[bold green]Total: {len(all_posts)} posts[/bold green]")


@app.command("forward")
def forward(
    webhook: str = typer.Option(..., "--webhook", "-w", help="Webhook name"),
    hours: int = typer.Option(24, "--hours", "-h", help="Forward posts from last N hours"),
    filter_keywords: str = typer.Option(None, "--filter", "-f", help="Comma-separated keywords"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be sent"),
):
    """Forward aggregated content to Discord."""
    if not HTTPX_AVAILABLE:
        console.print("[red]httpx not installed.[/red]")
        raise typer.Exit(1)

    config = load_config()
    webhook_url = config.get("webhooks", {}).get(webhook)

    if not webhook_url:
        console.print(f"[red]Webhook not found:[/red] {webhook}")
        console.print("Available webhooks:")
        for name in config.get("webhooks", {}).keys():
            console.print(f"  - {name}")
        raise typer.Exit(1)

    # Fetch all content
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    all_posts = []

    # Fetch from cache or live
    # For now, just do a live fetch
    console.print("[bold]Fetching content...[/bold]")

    if TELETHON_AVAILABLE:
        api_id = os.environ.get("TELEGRAM_API_ID")
        api_hash = os.environ.get("TELEGRAM_API_HASH")
        if api_id and api_hash:
            channels = config.get("telegram_channels", [])
            if channels:
                posts = asyncio.run(_fetch_telegram_channels(int(api_id), api_hash, channels, 50))
                all_posts.extend([p for p in posts if p.timestamp >= cutoff])

    # Apply keyword filter
    if filter_keywords:
        keywords = [k.strip().lower() for k in filter_keywords.split(",")]
        all_posts = [p for p in all_posts if any(k in p.content.lower() for k in keywords)]

    console.print(f"[green]Found {len(all_posts)} posts to forward[/green]")

    if dry_run:
        for post in all_posts[:10]:
            console.print(f"\n[cyan]{post.platform}/@{post.source}[/cyan]")
            console.print(f"  {post.content[:100]}...")
        return

    # Send to Discord with rate limiting and retries
    sent = 0
    failed = 0

    @with_retries
    def _send_to_webhook(payload: dict) -> bool:
        """Send payload to Discord webhook with retry on transient failures."""
        response = httpx.post(webhook_url, json=payload, timeout=10.0)
        if response.status_code == 429:  # Rate limited
            retry_after = int(response.headers.get("Retry-After", 5))
            logger.warning(f"Discord rate limited, waiting {retry_after}s")
            time.sleep(retry_after)
            raise RuntimeError("Rate limited by Discord")
        if response.status_code not in (200, 204):
            raise RuntimeError(f"Discord returned {response.status_code}")
        return True

    for post in all_posts:
        # Use rate limiter for Discord webhooks
        _discord_limiter.acquire()

        try:
            payload = {"embeds": [post.to_discord_embed()]}
            if _send_to_webhook(payload):
                sent += 1
        except Exception as e:
            failed += 1
            logger.error(f"Failed to send to Discord: {e}")
            console.print(f"[red]Error:[/red] {e}")

    console.print(f"[green]Forwarded {sent}/{len(all_posts)} posts to Discord[/green]")
    if failed > 0:
        console.print(f"[yellow]Failed: {failed}[/yellow]")


@app.command("setup")
def setup():
    """Interactive setup wizard."""
    console.print(Panel(
        "[bold]Social Bridge Setup[/bold]\n\n"
        "This wizard helps you configure social media aggregation.",
        title="Setup Wizard",
    ))

    # Check Telegram
    console.print("\n[bold]1. Telegram Setup[/bold]")
    if TELETHON_AVAILABLE:
        console.print("  [green]Telethon installed[/green]")
        api_id = os.environ.get("TELEGRAM_API_ID")
        api_hash = os.environ.get("TELEGRAM_API_HASH")
        if api_id and api_hash:
            console.print("  [green]API credentials configured[/green]")
        else:
            console.print("  [yellow]Missing API credentials[/yellow]")
            console.print("  Get them at: https://my.telegram.org/apps")
            console.print("  Set: TELEGRAM_API_ID and TELEGRAM_API_HASH")
    else:
        console.print("  [red]Telethon not installed[/red]")
        console.print("  Install with: pip install telethon")

    # Check surf
    console.print("\n[bold]2. X/Twitter Setup (via surf)[/bold]")
    surf_check = subprocess.run(["which", "surf"], capture_output=True)
    if surf_check.returncode == 0:
        console.print("  [green]surf CLI found[/green]")
        # Check if connected
        tab_check = subprocess.run(["surf", "tab.list"], capture_output=True, timeout=5)
        if tab_check.returncode == 0:
            console.print("  [green]surf extension connected[/green]")
        else:
            console.print("  [yellow]surf extension not connected - using CDP fallback[/yellow]")
    else:
        console.print("  [red]surf CLI not found[/red]")
        console.print("  See /surf skill for setup instructions")

    # Check httpx
    console.print("\n[bold]3. Discord Webhooks[/bold]")
    if HTTPX_AVAILABLE:
        console.print("  [green]httpx installed[/green]")
    else:
        console.print("  [red]httpx not installed[/red]")
        console.print("  Install with: pip install httpx")

    config = load_config()
    webhooks = config.get("webhooks", {})
    if webhooks:
        console.print(f"  [green]{len(webhooks)} webhook(s) configured[/green]")
    else:
        console.print("  [yellow]No webhooks configured[/yellow]")
        console.print("  Add with: social-bridge webhook add name URL")

    # Summary
    console.print("\n[bold]Quick Start Commands:[/bold]")
    console.print("""
  # Add sources
  social-bridge telegram add "@vaborivs"
  social-bridge x add "malwaretechblog"

  # Add Discord webhook
  social-bridge webhook add security "https://discord.com/api/webhooks/..."

  # Fetch and forward
  social-bridge fetch --all
  social-bridge forward --webhook security --hours 24
""")


@app.command("version")
def version():
    """Show version."""
    console.print("social-bridge v0.1.0")
    console.print(f"  Telethon: {'installed' if TELETHON_AVAILABLE else 'not installed'}")
    console.print(f"  httpx: {'installed' if HTTPX_AVAILABLE else 'not installed'}")


# =============================================================================
# MEMORY COMMANDS
# =============================================================================

@memory_app.command("search")
def memory_search(
    query: str = typer.Argument(..., help="Search query"),
    k: int = typer.Option(10, "--k", "-k", help="Number of results"),
    output_json: bool = typer.Option(False, "--json"),
):
    """Search stored social intel in memory."""
    results = search_memory(query, k=k)

    if output_json:
        print(json.dumps(results, indent=2))
    else:
        if not results:
            console.print("[yellow]No results found.[/yellow]")
            return

        console.print(f"[green]Found {len(results)} results[/green]\n")
        for i, item in enumerate(results, 1):
            problem = item.get("problem", "")
            solution = item.get("solution", "")
            score = item.get("score", 0)

            # Try to parse solution as JSON
            try:
                sol_data = json.loads(solution)
                content = sol_data.get("content", solution)[:200]
                url = sol_data.get("url", "")
                platform = sol_data.get("platform", "unknown")
            except (json.JSONDecodeError, TypeError):
                content = solution[:200]
                url = ""
                platform = "unknown"

            console.print(f"[cyan]{i}. [{platform.upper()}][/cyan] (score: {score:.2f})")
            console.print(f"   {content}...")
            if url:
                console.print(f"   [dim]{url}[/dim]")
            console.print()


@memory_app.command("ingest")
def memory_ingest(
    hours: int = typer.Option(24, "--hours", "-h", help="Fetch posts from last N hours"),
    limit: int = typer.Option(100, "--limit", "-l", help="Max posts per source"),
    telegram_only: bool = typer.Option(False, "--telegram", "-t"),
    x_only: bool = typer.Option(False, "--x"),
):
    """Fetch and persist all social content to memory."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    all_posts: list[SocialPost] = []

    fetch_telegram = telegram_only or (not telegram_only and not x_only)
    fetch_x = x_only or (not telegram_only and not x_only)

    # Fetch Telegram
    if fetch_telegram and TELETHON_AVAILABLE:
        api_id = os.environ.get("TELEGRAM_API_ID")
        api_hash = os.environ.get("TELEGRAM_API_HASH")
        if api_id and api_hash:
            config = load_config()
            channels = config.get("telegram_channels", [])
            if channels:
                console.print("[bold]Fetching Telegram...[/bold]")
                posts = asyncio.run(_fetch_telegram_channels(int(api_id), api_hash, channels, limit))
                posts = [p for p in posts if p.timestamp >= cutoff]
                all_posts.extend(posts)
                console.print(f"  [green]Telegram: {len(posts)} posts[/green]")

    # Fetch X/Twitter
    if fetch_x:
        config = load_config()
        accounts = config.get("x_accounts", [])
        if accounts:
            console.print("[bold]Fetching X/Twitter...[/bold]")
            for acc in accounts:
                posts = _fetch_x_account(acc, limit)
                posts = [p for p in posts if p.timestamp >= cutoff]
                all_posts.extend(posts)
            console.print(f"  [green]X/Twitter: {len([p for p in all_posts if p.platform == 'x'])} posts[/green]")

    # Persist to memory
    if not all_posts:
        console.print("[yellow]No posts to ingest.[/yellow]")
        return

    console.print(f"\n[bold]Persisting {len(all_posts)} posts to memory...[/bold]")
    stored = 0
    errors = 0

    with console.status("[bold green]Persisting...") as status:
        for i, post in enumerate(all_posts):
            result = persist_to_memory(post)
            if result.get("stored"):
                stored += 1
            else:
                errors += 1
            status.update(f"[bold green]Persisting... {i+1}/{len(all_posts)}")

    console.print(f"\n[green]Persisted: {stored}[/green]")
    if errors:
        console.print(f"[yellow]Errors: {errors}[/yellow]")


@memory_app.command("status")
def memory_status():
    """Check memory integration status."""
    memory_skill = Path(__file__).parent.parent / "memory" / "run.sh"

    console.print("[bold]Memory Integration Status[/bold]\n")

    # Check memory skill exists
    if memory_skill.exists():
        console.print(f"  [green]Memory skill:[/green] {memory_skill}")
    else:
        console.print(f"  [red]Memory skill not found at:[/red] {memory_skill}")
        console.print("  Make sure .pi/skills/memory/run.sh exists")
        return

    # Check memory service
    try:
        result = subprocess.run(
            [str(memory_skill), "status"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(memory_skill.parent),
        )
        if result.returncode == 0:
            console.print("  [green]Memory service:[/green] Connected")
        else:
            console.print(f"  [yellow]Memory service:[/yellow] {result.stderr[:100]}")
    except Exception as e:
        console.print(f"  [red]Memory service:[/red] {e}")

    # Show scope
    console.print(f"  [cyan]Scope:[/cyan] {MEMORY_SCOPE}")

    # Show keyword patterns
    console.print(f"\n[bold]Auto-tagging Patterns:[/bold]")
    for pattern, tag in SECURITY_KEYWORDS[:5]:
        console.print(f"  {tag}: {pattern}")
    console.print(f"  ... and {len(SECURITY_KEYWORDS) - 5} more")


if __name__ == "__main__":
    app()
