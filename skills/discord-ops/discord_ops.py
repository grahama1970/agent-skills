#!/usr/bin/env python3
"""
Discord Operations Skill - Notification Monitor Model

TOS-compliant approach: Monitor YOUR OWN Discord server for security content
forwarded by researchers, then push to paper-writer/dogpile via webhooks.
Persists matches to graph-memory for knowledge graph integration.

Architecture:
  External Sources → Your Discord Server → ClawDBot Monitor → Webhooks → Consumers
                     (you are admin)       (keyword watch)     + Memory

This skill does NOT scrape external servers (TOS violation).
Instead, it monitors channels where your bot has legitimate access.
"""

import asyncio
import functools
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

# Configure logging - don't log tokens or sensitive data
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("discord-ops")

T = TypeVar("T")

try:
    import typer
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
except ImportError:
    print("Missing requirements. Run: pip install typer rich", file=sys.stderr)
    sys.exit(1)

# Optional: httpx for webhooks
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

# Optional: discord.py for direct bot integration
try:
    import discord
    from discord.ext import commands
    DISCORD_PY_AVAILABLE = True
except ImportError:
    DISCORD_PY_AVAILABLE = False

app = typer.Typer(help="Discord notification monitor for security research")
memory_app = typer.Typer(help="Memory/knowledge graph integration")
app.add_typer(memory_app, name="memory")
console = Console()

# Paths
CLAWDBOT_DIR = Path(os.environ.get("CLAWDBOT_DIR", "/home/graham/workspace/experiments/clawdbot"))
SKILL_DIR = Path(__file__).parent
CONFIG_FILE = SKILL_DIR / "config.json"
KEYWORDS_FILE = SKILL_DIR / "keywords.json"
MATCHES_LOG = SKILL_DIR / "matches.jsonl"

# Default security keywords to watch
DEFAULT_KEYWORDS = [
    # Vulnerabilities
    r"CVE-\d{4}-\d+",
    r"0-?day",
    r"zero.?day",
    r"exploit",
    r"vuln(erability)?",
    r"RCE",
    r"LPE",
    r"privesc",
    # Programs & Funding
    r"DARPA",
    r"IARPA",
    r"BAA",
    r"grants?\.gov",
    # Platforms
    r"HTB",
    r"Hack.?The.?Box",
    r"TryHackMe",
    r"CTF",
    # Threat Intel
    r"APT\d+",
    r"malware",
    r"ransomware",
    r"C2",
    r"cobalt.?strike",
    # Techniques
    r"MITRE",
    r"ATT&CK",
    r"T\d{4}",  # MITRE technique IDs
]

# =============================================================================
# RESILIENCE UTILITIES (from code review recommendations)
# =============================================================================

# Configurable via environment
MAX_RETRIES = int(os.environ.get("DISCORD_OPS_MAX_RETRIES", "3"))
RETRY_BASE_DELAY = float(os.environ.get("DISCORD_OPS_RETRY_DELAY", "0.5"))
RATE_LIMIT_RPS = int(os.environ.get("DISCORD_OPS_RATE_LIMIT_RPS", "5"))

# Fields to redact in logs
REDACT_FIELDS = {"token", "api_key", "password", "secret", "authorization", "bot_token"}


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


# Global rate limiter for Discord webhook calls
_webhook_limiter = RateLimiter(requests_per_second=5)


# Memory integration - uses graph-memory project
MEMORY_ROOT = Path(os.environ.get("MEMORY_ROOT", Path.home() / "workspace/experiments/memory"))
MEMORY_SCOPE = "social_intel"

# Keyword to tag mapping for auto-tagging
KEYWORD_TAG_MAP = {
    r"CVE-\d{4}-\d+": "cve",
    r"APT\d+": "apt",
    r"DARPA|IARPA|BAA": "darpa",
    r"0-?day|zero.?day": "0day",
    r"exploit|RCE|LPE|privesc": "exploit",
    r"malware|ransomware": "malware",
    r"HTB|Hack.?The.?Box|TryHackMe|CTF": "ctf",
    r"MITRE|ATT&CK|T\d{4}": "mitre",
    r"cobalt.?strike|C2": "c2",
}


def extract_tags_from_keywords(matched_keywords: list[str], content: str) -> list[str]:
    """Extract semantic tags from matched keywords and content."""
    tags = set()
    for pattern, tag in KEYWORD_TAG_MAP.items():
        if re.search(pattern, content, re.IGNORECASE):
            tags.add(tag)
    return list(tags)


def persist_match_to_memory(match: "KeywordMatch") -> dict[str, Any]:
    """Persist a keyword match to graph-memory.

    Uses the memory skill's learn command to store matches as lessons.
    Includes retry logic for transient failures.
    Returns the result of the learn operation.
    """
    # Extract semantic tags
    auto_tags = extract_tags_from_keywords(match.matched_keywords, match.content)
    all_tags = list(set(auto_tags + ["discord", f"channel:{match.channel_name}", f"guild:{match.guild_name}"]))

    # Format problem as a searchable identifier
    problem = f"[DISCORD] #{match.channel_name}: {match.content[:100]}..."

    # Format solution with full content and metadata
    solution = json.dumps({
        "content": match.content,
        "url": match.message_url,
        "author": match.author,
        "timestamp": match.timestamp,
        "platform": "discord",
        "guild": match.guild_name,
        "channel": match.channel_name,
        "matched_keywords": match.matched_keywords,
    }, indent=2)

    # Call memory skill via CLI
    memory_skill = Path(__file__).parent.parent / "memory" / "run.sh"

    if not memory_skill.exists():
        logger.warning("Memory skill not found, cannot persist match")
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
    """Search memory for stored Discord matches.

    Returns matching posts from graph-memory.
    Includes retry logic for transient failures.
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


@dataclass
class KeywordMatch:
    """A message that matched watched keywords."""
    timestamp: str
    guild_id: str
    guild_name: str
    channel_id: str
    channel_name: str
    author: str
    content: str
    matched_keywords: list[str]
    message_url: str

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "guild_id": self.guild_id,
            "guild_name": self.guild_name,
            "channel_id": self.channel_id,
            "channel_name": self.channel_name,
            "author": self.author,
            "content": self.content,
            "matched_keywords": self.matched_keywords,
            "message_url": self.message_url,
        }

    def to_webhook_payload(self) -> dict:
        """Format for paper-writer/dogpile webhook."""
        return {
            "source": "discord",
            "content": self.content[:2000],
            "author": self.author,
            "channel": f"{self.guild_name}/#{self.channel_name}",
            "url": self.message_url,
            "keywords": self.matched_keywords,
            "timestamp": self.timestamp,
        }

    def to_discord_embed(self) -> dict:
        """Format for Discord webhook forwarding."""
        return {
            "title": f"Keyword Match: {', '.join(self.matched_keywords[:3])}",
            "description": self.content[:2000],
            "url": self.message_url,
            "color": 0x5865F2,  # Discord blurple
            "author": {"name": self.author},
            "footer": {"text": f"{self.guild_name} #{self.channel_name}"},
            "timestamp": self.timestamp,
        }


def load_config() -> dict[str, Any]:
    """Load configuration."""
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
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
        data = json.loads(KEYWORDS_FILE.read_text())
        return data.get("patterns", DEFAULT_KEYWORDS)
    return DEFAULT_KEYWORDS


def save_keywords(patterns: list[str]) -> None:
    """Save keyword patterns."""
    KEYWORDS_FILE.write_text(json.dumps({"patterns": patterns}, indent=2))


def get_bot_token() -> str | None:
    """Get Discord bot token from config or env."""
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


def match_keywords(text: str, patterns: list[str]) -> list[str]:
    """Find all keyword patterns that match in text."""
    matches = []
    for pattern in patterns:
        try:
            if re.search(pattern, text, re.IGNORECASE):
                matches.append(pattern)
        except re.error:
            # Invalid regex, try literal match
            if pattern.lower() in text.lower():
                matches.append(pattern)
    return matches


def log_match(match: KeywordMatch, persist: bool = True) -> dict[str, Any]:
    """Append match to log file and optionally persist to memory.

    Args:
        match: The keyword match to log
        persist: If True, also persist to graph-memory

    Returns:
        Result dict with 'logged' and optionally 'memory' status
    """
    result = {"logged": True}

    # Write to local log file
    with open(MATCHES_LOG, "a") as f:
        f.write(json.dumps(match.to_dict()) + "\n")

    # Persist to memory if enabled
    if persist:
        memory_result = persist_match_to_memory(match)
        result["memory"] = memory_result

    return result


async def forward_to_webhook(url: str, match: KeywordMatch, max_retries: int = MAX_RETRIES) -> bool:
    """Forward match to webhook endpoint with retry logic.

    Includes rate limiting and exponential backoff for transient failures.
    """
    if not HTTPX_AVAILABLE:
        console.print("[red]httpx not installed for webhook forwarding[/red]")
        return False

    # Apply rate limiting (blocking call in sync context, but keeps things simple)
    _webhook_limiter.acquire()

    # Determine payload based on webhook type
    if "discord.com/api/webhooks" in url:
        payload = {"embeds": [match.to_discord_embed()]}
    else:
        payload = match.to_webhook_payload()

    last_error: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, timeout=10.0)

                # Handle Discord rate limiting
                if response.status_code == 429:
                    retry_after = float(response.headers.get("Retry-After", 5))
                    logger.warning(f"Discord rate limited, waiting {retry_after}s")
                    await asyncio.sleep(retry_after)
                    continue

                if response.status_code in (200, 204):
                    return True

                logger.warning(f"Webhook returned {response.status_code} on attempt {attempt}")

        except Exception as e:
            last_error = e
            if attempt < max_retries:
                delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(f"Webhook attempt {attempt}/{max_retries} failed: {e}. Retrying in {delay:.1f}s...")
                await asyncio.sleep(delay)
            else:
                logger.error(f"Webhook failed after {max_retries} attempts: {e}")

    if last_error:
        console.print(f"[red]Webhook error:[/red] {last_error}")
    return False


# =============================================================================
# CLI COMMANDS
# =============================================================================

@app.command()
def setup():
    """Interactive setup for notification monitoring."""
    console.print(Panel(
        "[bold]Discord Notification Monitor Setup[/bold]\n\n"
        "This skill monitors YOUR Discord server for security content\n"
        "forwarded by researchers, then pushes to paper-writer/dogpile.",
        title="Setup Wizard",
    ))

    # Check bot token
    console.print("\n[bold]1. Bot Token[/bold]")
    token = get_bot_token()
    if token:
        console.print(f"  [green]Found bot token[/green] (ends in ...{token[-8:]})")
    else:
        console.print("  [red]No bot token found[/red]")
        console.print("  Set DISCORD_BOT_TOKEN env var or add to clawdbot .env")

    # Check discord.py
    console.print("\n[bold]2. Discord.py Library[/bold]")
    if DISCORD_PY_AVAILABLE:
        console.print(f"  [green]discord.py installed[/green] (v{discord.__version__})")
    else:
        console.print("  [yellow]discord.py not installed[/yellow]")
        console.print("  Install with: pip install discord.py")
        console.print("  (Optional - can also use clawdbot directly)")

    # Check httpx
    console.print("\n[bold]3. Webhook Support[/bold]")
    if HTTPX_AVAILABLE:
        console.print("  [green]httpx installed[/green]")
    else:
        console.print("  [red]httpx not installed[/red]")
        console.print("  Install with: pip install httpx")

    # Show config
    config = load_config()
    keywords = load_keywords()

    console.print("\n[bold]4. Configuration[/bold]")
    console.print(f"  Monitored guilds: {len(config.get('monitored_guilds', {}))}")
    console.print(f"  Webhooks configured: {len(config.get('webhooks', {}))}")
    console.print(f"  Keyword patterns: {len(keywords)}")

    # Next steps
    console.print("\n[bold]Next Steps:[/bold]")
    console.print("""
  1. Create a Discord server (or use existing one where you're admin)
  2. Add your bot to the server with message read permissions
  3. Create channels for security intel (e.g., #cve-alerts, #research-feed)
  4. Configure monitoring:

     [bold]discord-ops guild add "My Server" <guild_id>[/bold]
     [bold]discord-ops webhook add alerts "https://discord.com/api/webhooks/..."[/bold]
     [bold]discord-ops monitor start[/bold]

  5. Have researchers forward content to your channels
  6. Bot watches for keywords → forwards to paper-writer/dogpile
""")


@app.command()
def keywords(
    action: str = typer.Argument("list", help="Action: list, add, remove, reset"),
    pattern: str = typer.Argument(None, help="Keyword pattern (regex supported)"),
):
    """Manage watched keyword patterns."""
    patterns = load_keywords()

    if action == "list":
        console.print(f"[bold]Watched Keywords ({len(patterns)}):[/bold]\n")
        for i, p in enumerate(patterns, 1):
            console.print(f"  {i:2}. {p}")
        return

    if action == "add" and pattern:
        if pattern not in patterns:
            patterns.append(pattern)
            save_keywords(patterns)
            console.print(f"[green]Added:[/green] {pattern}")
        else:
            console.print(f"[yellow]Already exists:[/yellow] {pattern}")
        return

    if action == "remove" and pattern:
        if pattern in patterns:
            patterns.remove(pattern)
            save_keywords(patterns)
            console.print(f"[green]Removed:[/green] {pattern}")
        else:
            console.print(f"[yellow]Not found:[/yellow] {pattern}")
        return

    if action == "reset":
        save_keywords(DEFAULT_KEYWORDS)
        console.print(f"[green]Reset to {len(DEFAULT_KEYWORDS)} default patterns[/green]")
        return

    console.print("[red]Invalid action. Use: list, add, remove, reset[/red]")


@app.command()
def guild(
    action: str = typer.Argument(..., help="Action: add, remove, list"),
    name: str = typer.Argument(None, help="Guild name"),
    guild_id: str = typer.Argument(None, help="Guild ID"),
):
    """Manage monitored Discord guilds (servers)."""
    config = load_config()
    guilds = config.get("monitored_guilds", {})

    if action == "list":
        if not guilds:
            console.print("[yellow]No guilds configured.[/yellow]")
            console.print("Add with: discord-ops guild add \"Server Name\" <guild_id>")
            return

        table = Table(title="Monitored Guilds")
        table.add_column("Name", style="cyan")
        table.add_column("Guild ID")
        table.add_column("Channels")

        for gid, info in guilds.items():
            ch_count = len(info.get("channels", []))
            table.add_row(info.get("name", "Unknown"), gid, f"{ch_count} channels")

        console.print(table)
        return

    if action == "add" and name and guild_id:
        guilds[guild_id] = {"name": name, "channels": []}
        config["monitored_guilds"] = guilds
        save_config(config)
        console.print(f"[green]Added guild:[/green] {name} ({guild_id})")
        return

    if action == "remove" and (name or guild_id):
        # Find by name or ID
        to_remove = None
        for gid, info in guilds.items():
            if gid == guild_id or info.get("name") == name:
                to_remove = gid
                break

        if to_remove:
            del guilds[to_remove]
            config["monitored_guilds"] = guilds
            save_config(config)
            console.print(f"[green]Removed guild:[/green] {to_remove}")
        else:
            console.print(f"[yellow]Guild not found[/yellow]")
        return

    console.print("[red]Invalid usage. See: discord-ops guild --help[/red]")


@app.command()
def webhook(
    action: str = typer.Argument(..., help="Action: add, remove, list, test"),
    name: str = typer.Argument(None, help="Webhook name"),
    url: str = typer.Argument(None, help="Webhook URL"),
):
    """Manage output webhooks for forwarding matches."""
    config = load_config()
    webhooks = config.get("webhooks", {})

    if action == "list":
        if not webhooks:
            console.print("[yellow]No webhooks configured.[/yellow]")
            console.print("Add with: discord-ops webhook add <name> <url>")
            return

        table = Table(title="Configured Webhooks")
        table.add_column("Name", style="cyan")
        table.add_column("URL (truncated)")

        for n, u in webhooks.items():
            table.add_row(n, u[:50] + "...")

        console.print(table)
        return

    if action == "add" and name and url:
        webhooks[name] = url
        config["webhooks"] = webhooks
        save_config(config)
        console.print(f"[green]Added webhook:[/green] {name}")
        return

    if action == "remove" and name:
        if name in webhooks:
            del webhooks[name]
            config["webhooks"] = webhooks
            save_config(config)
            console.print(f"[green]Removed:[/green] {name}")
        else:
            console.print(f"[yellow]Not found:[/yellow] {name}")
        return

    if action == "test" and name:
        if name not in webhooks:
            console.print(f"[red]Webhook not found:[/red] {name}")
            raise typer.Exit(1)

        if not HTTPX_AVAILABLE:
            console.print("[red]httpx not installed[/red]")
            raise typer.Exit(1)

        # Create test match
        test_match = KeywordMatch(
            timestamp=datetime.now(timezone.utc).isoformat(),
            guild_id="test",
            guild_name="Test Server",
            channel_id="test",
            channel_name="test-channel",
            author="discord-ops",
            content="Test message: CVE-2024-0001 exploit detected!",
            matched_keywords=["CVE-2024-0001", "exploit"],
            message_url="https://discord.com/channels/test/test/test",
        )

        success = asyncio.run(forward_to_webhook(webhooks[name], test_match))
        if success:
            console.print(f"[green]Webhook test successful![/green]")
        else:
            console.print(f"[red]Webhook test failed[/red]")
        return

    console.print("[red]Invalid usage. See: discord-ops webhook --help[/red]")


@app.command()
def monitor(
    action: str = typer.Argument("status", help="Action: start, stop, status"),
    webhook_name: str = typer.Option(None, "--webhook", "-w", help="Webhook to forward matches"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Log matches but don't forward"),
    persist: bool = typer.Option(True, "--persist/--no-persist", help="Persist matches to memory"),
):
    """Start/stop the Discord notification monitor."""
    if action == "status":
        # Check if monitor is running (via PID file or process check)
        pid_file = SKILL_DIR / "monitor.pid"
        if pid_file.exists():
            pid = pid_file.read_text().strip()
            console.print(f"[green]Monitor running[/green] (PID: {pid})")
        else:
            console.print("[yellow]Monitor not running[/yellow]")

        # Show recent matches
        if MATCHES_LOG.exists():
            lines = MATCHES_LOG.read_text().strip().split("\n")
            console.print(f"\n[bold]Recent matches:[/bold] {len(lines)} total")
            for line in lines[-5:]:
                try:
                    match = json.loads(line)
                    console.print(f"  {match['timestamp'][:16]} - {match['matched_keywords']}")
                except json.JSONDecodeError:
                    pass
        return

    if action == "start":
        if not DISCORD_PY_AVAILABLE:
            console.print("[red]discord.py not installed[/red]")
            console.print("Install with: pip install discord.py")
            console.print("\nAlternatively, configure clawdbot to forward matches.")
            raise typer.Exit(1)

        token = get_bot_token()
        if not token:
            console.print("[red]No bot token configured[/red]")
            raise typer.Exit(1)

        config = load_config()
        webhook_url = None
        if webhook_name:
            webhook_url = config.get("webhooks", {}).get(webhook_name)
            if not webhook_url:
                console.print(f"[red]Webhook not found:[/red] {webhook_name}")
                raise typer.Exit(1)

        console.print("[bold]Starting Discord monitor...[/bold]")
        console.print(f"  Dry run: {dry_run}")
        console.print(f"  Webhook: {webhook_name or 'None (log only)'}")
        console.print(f"  Memory persist: {persist}")

        # Run the monitor
        asyncio.run(_run_monitor(token, webhook_url, dry_run, persist))
        return

    if action == "stop":
        pid_file = SKILL_DIR / "monitor.pid"
        if pid_file.exists():
            pid = pid_file.read_text().strip()
            try:
                os.kill(int(pid), 15)  # SIGTERM
                pid_file.unlink()
                console.print(f"[green]Stopped monitor[/green] (PID: {pid})")
            except ProcessLookupError:
                pid_file.unlink()
                console.print("[yellow]Monitor was not running[/yellow]")
        else:
            console.print("[yellow]Monitor not running[/yellow]")
        return

    console.print("[red]Invalid action. Use: start, stop, status[/red]")


async def _run_monitor(token: str, webhook_url: str | None, dry_run: bool, persist: bool = True):
    """Run the Discord monitor bot."""
    if not DISCORD_PY_AVAILABLE:
        return

    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True

    bot = commands.Bot(command_prefix="!", intents=intents)
    keywords = load_keywords()
    config = load_config()
    monitored_guilds = set(config.get("monitored_guilds", {}).keys())

    @bot.event
    async def on_ready():
        console.print(f"[green]Connected as {bot.user}[/green]")
        console.print(f"  Monitoring {len(monitored_guilds)} guilds")
        console.print(f"  Watching {len(keywords)} keyword patterns")
        console.print(f"  Memory persist: {persist}")

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
        console.print(f"[cyan]Match:[/cyan] {matched} in #{match.channel_name}")

        if persist and result.get("memory", {}).get("stored"):
            console.print(f"  [green]Persisted to memory[/green]")
        elif persist and result.get("memory", {}).get("error"):
            console.print(f"  [yellow]Memory error: {result['memory']['error'][:50]}[/yellow]")

        # Forward to webhook (unless dry run)
        if webhook_url and not dry_run:
            success = await forward_to_webhook(webhook_url, match)
            if success:
                console.print(f"  [green]Forwarded to webhook[/green]")
            else:
                console.print(f"  [red]Webhook forward failed[/red]")

    try:
        await bot.start(token)
    except KeyboardInterrupt:
        await bot.close()
    finally:
        pid_file = SKILL_DIR / "monitor.pid"
        if pid_file.exists():
            pid_file.unlink()


@app.command()
def matches(
    limit: int = typer.Option(20, "--limit", "-l", help="Number of matches to show"),
    keyword: str = typer.Option(None, "--keyword", "-k", help="Filter by keyword"),
    output_json: bool = typer.Option(False, "--json"),
):
    """View recent keyword matches."""
    if not MATCHES_LOG.exists():
        console.print("[yellow]No matches logged yet.[/yellow]")
        return

    lines = MATCHES_LOG.read_text().strip().split("\n")
    matches_list = []

    for line in reversed(lines):
        if len(matches_list) >= limit:
            break
        try:
            match = json.loads(line)
            if keyword and keyword.lower() not in str(match.get("matched_keywords", [])).lower():
                continue
            matches_list.append(match)
        except json.JSONDecodeError:
            continue

    if output_json:
        print(json.dumps(matches_list, indent=2))
        return

    if not matches_list:
        console.print("[yellow]No matches found.[/yellow]")
        return

    console.print(f"[bold]Recent Matches ({len(matches_list)}):[/bold]\n")

    for match in matches_list:
        ts = match.get("timestamp", "")[:16]
        kw = ", ".join(match.get("matched_keywords", [])[:3])
        ch = match.get("channel_name", "unknown")
        content = match.get("content", "")[:100]

        console.print(f"[dim]{ts}[/dim] [cyan]#{ch}[/cyan] [{kw}]")
        console.print(f"  {content}...")
        console.print()


@app.command()
def version():
    """Show version and status."""
    console.print("discord-ops v0.2.0 (Notification Monitor Model)")
    console.print(f"  discord.py: {'installed' if DISCORD_PY_AVAILABLE else 'not installed'}")
    console.print(f"  httpx: {'installed' if HTTPX_AVAILABLE else 'not installed'}")
    console.print(f"  Bot token: {'configured' if get_bot_token() else 'missing'}")


# =============================================================================
# MEMORY COMMANDS
# =============================================================================

@memory_app.command("search")
def memory_search(
    query: str = typer.Argument(..., help="Search query"),
    k: int = typer.Option(10, "--k", "-k", help="Number of results"),
    output_json: bool = typer.Option(False, "--json"),
):
    """Search stored Discord matches in memory."""
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
                channel = sol_data.get("channel", "unknown")
            except (json.JSONDecodeError, TypeError):
                content = solution[:200]
                url = ""
                channel = "unknown"

            console.print(f"[cyan]{i}. #{channel}[/cyan] (score: {score:.2f})")
            console.print(f"   {content}...")
            if url:
                console.print(f"   [dim]{url}[/dim]")
            console.print()


@memory_app.command("ingest")
def memory_ingest(
    limit: int = typer.Option(100, "--limit", "-l", help="Max matches to ingest"),
):
    """Ingest existing matches from log file into memory."""
    if not MATCHES_LOG.exists():
        console.print("[yellow]No matches log file found.[/yellow]")
        return

    lines = MATCHES_LOG.read_text().strip().split("\n")
    console.print(f"[bold]Ingesting {min(len(lines), limit)} matches to memory...[/bold]")

    stored = 0
    errors = 0

    for i, line in enumerate(lines[-limit:]):
        try:
            data = json.loads(line)
            match = KeywordMatch(
                timestamp=data.get("timestamp", ""),
                guild_id=data.get("guild_id", ""),
                guild_name=data.get("guild_name", ""),
                channel_id=data.get("channel_id", ""),
                channel_name=data.get("channel_name", ""),
                author=data.get("author", ""),
                content=data.get("content", ""),
                matched_keywords=data.get("matched_keywords", []),
                message_url=data.get("message_url", ""),
            )

            result = persist_match_to_memory(match)
            if result.get("stored"):
                stored += 1
            else:
                errors += 1

            if (i + 1) % 10 == 0:
                console.print(f"  Processed {i + 1}/{min(len(lines), limit)}...")

        except (json.JSONDecodeError, KeyError) as e:
            errors += 1
            continue

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

    # Show local matches count
    if MATCHES_LOG.exists():
        lines = MATCHES_LOG.read_text().strip().split("\n")
        console.print(f"  [cyan]Local matches:[/cyan] {len(lines)}")
    else:
        console.print("  [cyan]Local matches:[/cyan] 0")


if __name__ == "__main__":
    app()
