#!/usr/bin/env python3
"""
Social Bridge - Security Content Aggregator

Thin CLI entry point that delegates to modular components.

Aggregates security content from:
- Telegram public channels (via Telethon/MTProto)
- X/Twitter accounts (via surf browser automation)

Forwards to Discord webhooks for centralized monitoring.
Persists content to graph-memory for knowledge graph integration.
"""

import logging
import sys

# Configure logging - don't log tokens or sensitive data
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

try:
    import typer
    from rich.console import Console
except ImportError:
    print("Missing requirements. Run: pip install typer rich", file=sys.stderr)
    sys.exit(1)

# Import command implementations
from social_bridge.cli_commands import (
    # Config
    load_config,
    # Telegram
    telegram_add_cmd,
    telegram_remove_cmd,
    telegram_list_cmd,
    telegram_fetch_cmd,
    # X/Twitter
    x_add_cmd,
    x_remove_cmd,
    x_list_cmd,
    x_fetch_cmd,
    # Webhook
    webhook_add_cmd,
    webhook_remove_cmd,
    webhook_list_cmd,
    webhook_test_cmd,
    # Aggregate
    fetch_all_cmd,
    forward_cmd,
    setup_cmd,
    # Memory
    memory_search_cmd,
    memory_ingest_cmd,
    memory_status_cmd,
)
from social_bridge.telegram import TELETHON_AVAILABLE
from social_bridge.discord_webhook import HTTPX_AVAILABLE

# =============================================================================
# CLI SETUP
# =============================================================================

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


# =============================================================================
# TELEGRAM COMMANDS
# =============================================================================

@telegram_app.command("add")
def telegram_add(channel: str = typer.Argument(..., help="Channel username or URL")):
    """Add a Telegram channel to monitor."""
    telegram_add_cmd(channel)


@telegram_app.command("remove")
def telegram_remove(channel: str = typer.Argument(..., help="Channel to remove")):
    """Remove a Telegram channel."""
    telegram_remove_cmd(channel)


@telegram_app.command("list")
def telegram_list():
    """List monitored Telegram channels."""
    telegram_list_cmd()


@telegram_app.command("fetch")
def telegram_fetch(
    channel: str = typer.Argument(None, help="Specific channel (or all)"),
    limit: int = typer.Option(50, "--limit", "-l", help="Messages per channel"),
    output_json: bool = typer.Option(False, "--json"),
    persist: bool = typer.Option(False, "--persist", "-p", help="Persist to memory"),
):
    """Fetch messages from Telegram channels."""
    telegram_fetch_cmd(channel, limit, output_json, persist)


# =============================================================================
# X/TWITTER COMMANDS
# =============================================================================

@x_app.command("add")
def x_add(account: str = typer.Argument(..., help="X/Twitter username")):
    """Add an X/Twitter account to monitor."""
    x_add_cmd(account)


@x_app.command("remove")
def x_remove(account: str = typer.Argument(..., help="Account to remove")):
    """Remove an X/Twitter account."""
    x_remove_cmd(account)


@x_app.command("list")
def x_list():
    """List monitored X/Twitter accounts."""
    x_list_cmd()


@x_app.command("fetch")
def x_fetch(
    account: str = typer.Argument(None, help="Specific account (or all)"),
    limit: int = typer.Option(50, "--limit", "-l", help="Tweets per account"),
    output_json: bool = typer.Option(False, "--json"),
):
    """Fetch tweets using surf browser automation."""
    x_fetch_cmd(account, limit, output_json)


# =============================================================================
# WEBHOOK COMMANDS
# =============================================================================

@webhook_app.command("add")
def webhook_add(
    name: str = typer.Argument(..., help="Webhook name"),
    url: str = typer.Argument(..., help="Discord webhook URL"),
):
    """Add a Discord webhook."""
    webhook_add_cmd(name, url)


@webhook_app.command("remove")
def webhook_remove(name: str = typer.Argument(..., help="Webhook name")):
    """Remove a Discord webhook."""
    webhook_remove_cmd(name)


@webhook_app.command("list")
def webhook_list():
    """List Discord webhooks."""
    webhook_list_cmd()


@webhook_app.command("test")
def webhook_test(name: str = typer.Argument(..., help="Webhook name")):
    """Test a Discord webhook."""
    webhook_test_cmd(name)


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
    persist: bool = typer.Option(False, "--persist", "-p", help="Persist to memory"),
):
    """Fetch content from all sources."""
    fetch_all_cmd(telegram, x, hours, limit, output_json, persist)


@app.command("forward")
def forward(
    webhook: str = typer.Option(..., "--webhook", "-w", help="Webhook name"),
    hours: int = typer.Option(24, "--hours", "-h", help="Forward posts from last N hours"),
    filter_keywords: str = typer.Option(None, "--filter", "-f", help="Comma-separated keywords"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be sent"),
):
    """Forward aggregated content to Discord."""
    forward_cmd(webhook, hours, filter_keywords, dry_run)


@app.command("setup")
def setup():
    """Interactive setup wizard."""
    setup_cmd()


@app.command("version")
def version():
    """Show version."""
    console.print("social-bridge v0.2.0 (modular)")
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
    memory_search_cmd(query, k, output_json)


@memory_app.command("ingest")
def memory_ingest(
    hours: int = typer.Option(24, "--hours", "-h", help="Fetch posts from last N hours"),
    limit: int = typer.Option(100, "--limit", "-l", help="Max posts per source"),
    telegram_only: bool = typer.Option(False, "--telegram", "-t"),
    x_only: bool = typer.Option(False, "--x"),
):
    """Fetch and persist all social content to memory."""
    memory_ingest_cmd(hours, limit, telegram_only, x_only)


@memory_app.command("status")
def memory_status():
    """Check memory integration status."""
    memory_status_cmd()


if __name__ == "__main__":
    app()
