#!/usr/bin/env python3
"""
Social Bridge - Security Content Aggregator

Aggregates security content from:
- Telegram public channels (via Telethon/MTProto)
- X/Twitter accounts (via surf browser automation)

Forwards to Discord webhooks for centralized monitoring.
"""

import asyncio
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

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

app = typer.Typer(help="Social Bridge - Security content aggregator")
telegram_app = typer.Typer(help="Telegram channel management")
x_app = typer.Typer(help="X/Twitter account management")
webhook_app = typer.Typer(help="Discord webhook management")

app.add_typer(telegram_app, name="telegram")
app.add_typer(x_app, name="x")
app.add_typer(webhook_app, name="webhook")

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

    if output_json:
        print(json.dumps([p.to_dict() for p in posts], indent=2))
    else:
        console.print(f"[green]Fetched {len(posts)} messages from {len(channels)} channels[/green]")
        for post in posts[:10]:
            console.print(f"\n[cyan]@{post.source}[/cyan] ({post.timestamp.strftime('%Y-%m-%d %H:%M')})")
            console.print(f"  {post.content[:200]}...")
            console.print(f"  [dim]{post.url}[/dim]")


async def _fetch_telegram_channels(api_id: int, api_hash: str, channels: list[str], limit: int) -> list[SocialPost]:
    """Fetch messages from Telegram channels using Telethon."""
    posts = []

    async with TelegramClient(str(TELEGRAM_SESSION), api_id, api_hash) as client:
        for channel_name in channels:
            try:
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
            except Exception as e:
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
):
    """Fetch content from all sources."""
    fetch_telegram = telegram or (not telegram and not x)
    fetch_x = x or (not telegram and not x)

    all_posts = []
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

    # Send to Discord
    sent = 0
    for post in all_posts:
        try:
            payload = {
                "embeds": [post.to_discord_embed()]
            }
            response = httpx.post(webhook_url, json=payload)
            if response.status_code in (200, 204):
                sent += 1
            else:
                console.print(f"[red]Failed to send:[/red] {response.status_code}")

            # Rate limit: max 30/minute
            import time
            time.sleep(2)

        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")

    console.print(f"[green]Forwarded {sent}/{len(all_posts)} posts to Discord[/green]")


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


if __name__ == "__main__":
    app()
