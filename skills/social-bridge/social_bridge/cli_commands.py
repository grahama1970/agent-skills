"""
Social Bridge CLI Commands Module

Contains all the CLI command implementations for the various subcommands.
This module is imported by the main social_bridge.py CLI entry point.
"""

import json
import logging
from datetime import datetime, timedelta, timezone

try:
    import typer
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
except ImportError:
    raise ImportError("Missing requirements. Run: pip install typer rich")

from social_bridge.config import CONFIG_FILE, SECURITY_KEYWORDS, ensure_directories
from social_bridge.telegram import (
    get_telegram_credentials, normalize_channel_name, fetch_channels_sync,
    get_default_channels, TELETHON_AVAILABLE,
)
from social_bridge.twitter import (
    check_surf_available, check_surf_extension_connected, normalize_account_name,
    fetch_x_account, get_default_accounts,
)
from social_bridge.discord_webhook import (
    validate_webhook_url, send_test_message, send_posts, HTTPX_AVAILABLE,
)
from social_bridge.graph_storage import (
    check_memory_available, check_memory_service, persist_posts, search_memory, get_memory_scope,
)

logger = logging.getLogger("social-bridge.cli")
console = Console()


def load_config() -> dict:
    """Load configuration."""
    ensure_directories()
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {"telegram_channels": [], "x_accounts": [], "webhooks": {}, "last_fetch": {}}


def save_config(config: dict) -> None:
    """Save configuration."""
    CONFIG_FILE.write_text(json.dumps(config, indent=2))


def _print_posts(posts: list, max_show: int = 10):
    """Print posts in a readable format."""
    for post in posts[:max_show]:
        console.print(f"\n[cyan]@{post.source}[/cyan] ({post.timestamp.strftime('%Y-%m-%d %H:%M')})")
        console.print(f"  {post.content[:200]}...")
        console.print(f"  [dim]{post.url}[/dim]")


# Telegram Commands
def telegram_add_cmd(channel: str):
    channel = normalize_channel_name(channel)
    config = load_config()
    if channel not in config["telegram_channels"]:
        config["telegram_channels"].append(channel)
        save_config(config)
        console.print(f"[green]Added Telegram channel:[/green] @{channel}")
    else:
        console.print(f"[yellow]Channel already monitored:[/yellow] @{channel}")


def telegram_remove_cmd(channel: str):
    channel = normalize_channel_name(channel)
    config = load_config()
    if channel in config["telegram_channels"]:
        config["telegram_channels"].remove(channel)
        save_config(config)
        console.print(f"[green]Removed:[/green] @{channel}")
    else:
        console.print(f"[yellow]Not found:[/yellow] @{channel}")


def telegram_list_cmd():
    config = load_config()
    channels = config.get("telegram_channels", [])
    if not channels:
        console.print("[yellow]No Telegram channels configured.[/yellow]")
        console.print("Add with: [bold]social-bridge telegram add @channel[/bold]\nSuggested:")
        for ch in get_default_channels():
            console.print(f"  @{ch['name']} - {ch['focus']}")
        return
    table = Table(title="Monitored Telegram Channels")
    table.add_column("Channel", style="cyan")
    table.add_column("URL")
    for ch in channels:
        table.add_row(f"@{ch}", f"https://t.me/{ch}")
    console.print(table)


def telegram_fetch_cmd(channel: str | None, limit: int, output_json: bool, persist: bool):
    if not TELETHON_AVAILABLE:
        console.print("[red]Telethon not installed. Run: pip install telethon[/red]")
        raise typer.Exit(1)
    api_id, api_hash = get_telegram_credentials()
    if not api_id or not api_hash:
        console.print("[red]Set TELEGRAM_API_ID and TELEGRAM_API_HASH (from my.telegram.org)[/red]")
        raise typer.Exit(1)
    config = load_config()
    channels = [channel] if channel else config.get("telegram_channels", [])
    if not channels:
        console.print("[yellow]No channels to fetch.[/yellow]")
        return
    posts = fetch_channels_sync(int(api_id), api_hash, channels, limit)
    if persist:
        stored, _ = persist_posts(posts)
        console.print(f"[green]Persisted {stored}/{len(posts)} posts[/green]")
    if output_json:
        print(json.dumps([p.to_dict() for p in posts], indent=2))
    else:
        console.print(f"[green]Fetched {len(posts)} messages from {len(channels)} channels[/green]")
        _print_posts(posts)


# X/Twitter Commands
def x_add_cmd(account: str):
    account = normalize_account_name(account)
    config = load_config()
    if account not in config["x_accounts"]:
        config["x_accounts"].append(account)
        save_config(config)
        console.print(f"[green]Added X account:[/green] @{account}")
    else:
        console.print(f"[yellow]Account already monitored:[/yellow] @{account}")


def x_remove_cmd(account: str):
    account = normalize_account_name(account)
    config = load_config()
    if account in config["x_accounts"]:
        config["x_accounts"].remove(account)
        save_config(config)
        console.print(f"[green]Removed:[/green] @{account}")
    else:
        console.print(f"[yellow]Not found:[/yellow] @{account}")


def x_list_cmd():
    config = load_config()
    accounts = config.get("x_accounts", [])
    if not accounts:
        console.print("[yellow]No X/Twitter accounts configured.[/yellow]")
        console.print("Add with: [bold]social-bridge x add username[/bold]\nSuggested:")
        for acc in get_default_accounts():
            console.print(f"  @{acc['name']} - {acc['focus']}")
        return
    table = Table(title="Monitored X/Twitter Accounts")
    table.add_column("Account", style="cyan")
    table.add_column("URL")
    for acc in accounts:
        table.add_row(f"@{acc}", f"https://x.com/{acc}")
    console.print(table)


def x_fetch_cmd(account: str | None, limit: int, output_json: bool):
    if not check_surf_available():
        console.print("[red]surf CLI not found. Install surf-cli extension.[/red]")
        raise typer.Exit(1)
    config = load_config()
    accounts = [account] if account else config.get("x_accounts", [])
    if not accounts:
        console.print("[yellow]No accounts to fetch.[/yellow]")
        return
    posts = []
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
        for acc in accounts:
            task = progress.add_task(f"Fetching @{acc}...", total=None)
            try:
                account_posts = fetch_x_account(acc, limit)
                posts.extend(account_posts)
                progress.update(task, description=f"[green]@{acc}: {len(account_posts)} tweets[/green]")
            except Exception as e:
                progress.update(task, description=f"[red]@{acc}: {e}[/red]")
    if output_json:
        print(json.dumps([p.to_dict() for p in posts], indent=2))
    else:
        console.print(f"\n[green]Fetched {len(posts)} tweets from {len(accounts)} accounts[/green]")
        _print_posts(posts)


# Webhook Commands
def webhook_add_cmd(name: str, url: str):
    if not validate_webhook_url(url):
        console.print("[red]Invalid webhook URL. Must start with https://discord.com/api/webhooks/[/red]")
        raise typer.Exit(1)
    config = load_config()
    config["webhooks"][name] = url
    save_config(config)
    console.print(f"[green]Added webhook:[/green] {name}")


def webhook_remove_cmd(name: str):
    config = load_config()
    if name in config.get("webhooks", {}):
        del config["webhooks"][name]
        save_config(config)
        console.print(f"[green]Removed:[/green] {name}")
    else:
        console.print(f"[yellow]Not found:[/yellow] {name}")


def webhook_list_cmd():
    config = load_config()
    webhooks = config.get("webhooks", {})
    if not webhooks:
        console.print("[yellow]No webhooks. Add with: social-bridge webhook add name URL[/yellow]")
        return
    table = Table(title="Discord Webhooks")
    table.add_column("Name", style="cyan")
    table.add_column("URL (truncated)")
    for name, url in webhooks.items():
        table.add_row(name, url[:50] + "...")
    console.print(table)


def webhook_test_cmd(name: str):
    if not HTTPX_AVAILABLE:
        console.print("[red]httpx not installed. Run: pip install httpx[/red]")
        raise typer.Exit(1)
    config = load_config()
    url = config.get("webhooks", {}).get(name)
    if not url:
        console.print(f"[red]Webhook not found:[/red] {name}")
        raise typer.Exit(1)
    try:
        if send_test_message(url):
            console.print("[green]Webhook test successful![/green]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")


# Aggregate Commands
def fetch_all_cmd(telegram: bool, x: bool, hours: int, limit: int, output_json: bool, persist: bool):
    fetch_tg = telegram or (not telegram and not x)
    fetch_x = x or (not telegram and not x)
    all_posts, cutoff = [], datetime.now(timezone.utc) - timedelta(hours=hours)

    if fetch_tg and TELETHON_AVAILABLE:
        console.print("[bold]Fetching Telegram...[/bold]")
        api_id, api_hash = get_telegram_credentials()
        if api_id and api_hash:
            config = load_config()
            channels = config.get("telegram_channels", [])
            if channels:
                posts = [p for p in fetch_channels_sync(int(api_id), api_hash, channels, limit) if p.timestamp >= cutoff]
                all_posts.extend(posts)
                console.print(f"  [green]Telegram: {len(posts)} posts[/green]")

    if fetch_x:
        console.print("[bold]Fetching X/Twitter...[/bold]")
        if not check_surf_available():
            console.print("[yellow]surf CLI not found; skipping X/Twitter[/yellow]")
        else:
            config = load_config()
            for acc in config.get("x_accounts", []):
                posts = [p for p in fetch_x_account(acc, limit) if p.timestamp >= cutoff]
                all_posts.extend(posts)
            console.print(f"  [green]X/Twitter: {len([p for p in all_posts if p.platform == 'x'])} posts[/green]")

    all_posts.sort(key=lambda p: p.timestamp, reverse=True)
    if persist and all_posts:
        stored, _ = persist_posts(all_posts)
        console.print(f"[green]Persisted {stored}/{len(all_posts)} posts[/green]")
    if output_json:
        print(json.dumps([p.to_dict() for p in all_posts], indent=2))
    else:
        console.print(f"\n[bold green]Total: {len(all_posts)} posts[/bold green]")


def forward_cmd(webhook: str, hours: int, filter_keywords: str | None, dry_run: bool):
    if not HTTPX_AVAILABLE:
        console.print("[red]httpx not installed.[/red]")
        raise typer.Exit(1)
    config = load_config()
    webhook_url = config.get("webhooks", {}).get(webhook)
    if not webhook_url:
        console.print(f"[red]Webhook not found:[/red] {webhook}")
        raise typer.Exit(1)

    cutoff, all_posts = datetime.now(timezone.utc) - timedelta(hours=hours), []
    console.print("[bold]Fetching content...[/bold]")
    if TELETHON_AVAILABLE:
        api_id, api_hash = get_telegram_credentials()
        if api_id and api_hash:
            channels = config.get("telegram_channels", [])
            if channels:
                all_posts.extend([p for p in fetch_channels_sync(int(api_id), api_hash, channels, 50) if p.timestamp >= cutoff])

    if filter_keywords:
        kws = [k.strip().lower() for k in filter_keywords.split(",")]
        all_posts = [p for p in all_posts if any(k in p.content.lower() for k in kws)]

    console.print(f"[green]Found {len(all_posts)} posts to forward[/green]")
    if dry_run:
        for post in all_posts[:10]:
            console.print(f"\n[cyan]{post.platform}/@{post.source}[/cyan]\n  {post.content[:100]}...")
        return
    sent, failed = send_posts(webhook_url, all_posts, lambda p, e: console.print(f"[red]Error:[/red] {e}"))
    console.print(f"[green]Forwarded {sent}/{len(all_posts)} posts to Discord[/green]")
    if failed:
        console.print(f"[yellow]Failed: {failed}[/yellow]")


def setup_cmd():
    console.print(Panel("[bold]Social Bridge Setup[/bold]\n\nConfigure social media aggregation.", title="Setup Wizard"))
    console.print("\n[bold]1. Telegram Setup[/bold]")
    if TELETHON_AVAILABLE:
        api_id, api_hash = get_telegram_credentials()
        console.print("  [green]Telethon installed[/green]")
        console.print(f"  [{'green' if api_id else 'yellow'}]API credentials: {'configured' if api_id else 'missing (get at my.telegram.org)'}[/]")
    else:
        console.print("  [red]Telethon not installed (pip install telethon)[/red]")
    console.print("\n[bold]2. X/Twitter Setup[/bold]")
    if check_surf_available():
        ext_connected = check_surf_extension_connected()
        console.print(f"  [green]surf CLI found[/green], extension: [{'green' if ext_connected else 'yellow'}]{'connected' if ext_connected else 'not connected'}[/]")
    else:
        console.print("  [red]surf CLI not found[/red]")
    console.print("\n[bold]3. Discord Webhooks[/bold]")
    console.print(f"  httpx: [{'green' if HTTPX_AVAILABLE else 'red'}]{'installed' if HTTPX_AVAILABLE else 'not installed'}[/]")
    webhooks = load_config().get("webhooks", {})
    console.print(f"  [{'green' if webhooks else 'yellow'}]{len(webhooks)} webhook(s) configured[/]" if webhooks else "  [yellow]No webhooks configured[/yellow]")
    console.print("\n[bold]Quick Start:[/bold]\n  social-bridge telegram add @vaborivs\n  social-bridge x add malwaretechblog\n  social-bridge webhook add sec URL\n  social-bridge fetch && social-bridge forward -w sec")


# Memory Commands
def memory_search_cmd(query: str, k: int, output_json: bool):
    results = search_memory(query, k=k)
    if output_json:
        print(json.dumps(results, indent=2))
        return
    if not results:
        console.print("[yellow]No results found.[/yellow]")
        return
    console.print(f"[green]Found {len(results)} results[/green]\n")
    for i, item in enumerate(results, 1):
        solution, score = item.get("solution", ""), item.get("score", 0)
        try:
            sol = json.loads(solution)
            content, url, platform = sol.get("content", solution)[:200], sol.get("url", ""), sol.get("platform", "?")
        except (json.JSONDecodeError, TypeError):
            content, url, platform = solution[:200], "", "?"
        console.print(f"[cyan]{i}. [{platform.upper()}][/cyan] (score: {score:.2f})\n   {content}...")
        if url:
            console.print(f"   [dim]{url}[/dim]")


def memory_ingest_cmd(hours: int, limit: int, telegram_only: bool, x_only: bool):
    cutoff, all_posts = datetime.now(timezone.utc) - timedelta(hours=hours), []
    fetch_tg = telegram_only or (not telegram_only and not x_only)
    fetch_x = x_only or (not telegram_only and not x_only)

    if fetch_tg and TELETHON_AVAILABLE:
        api_id, api_hash = get_telegram_credentials()
        if api_id and api_hash:
            config = load_config()
            if channels := config.get("telegram_channels", []):
                console.print("[bold]Fetching Telegram...[/bold]")
                posts = [p for p in fetch_channels_sync(int(api_id), api_hash, channels, limit) if p.timestamp >= cutoff]
                all_posts.extend(posts)
                console.print(f"  [green]Telegram: {len(posts)} posts[/green]")

    if fetch_x:
        if not check_surf_available():
            console.print("[yellow]surf CLI not found; skipping X/Twitter[/yellow]")
        else:
            config = load_config()
            if accounts := config.get("x_accounts", []):
                console.print("[bold]Fetching X/Twitter...[/bold]")
                for acc in accounts:
                    posts = [p for p in fetch_x_account(acc, limit) if p.timestamp >= cutoff]
                    all_posts.extend(posts)
                console.print(f"  [green]X/Twitter: {len([p for p in all_posts if p.platform == 'x'])} posts[/green]")

    if not all_posts:
        console.print("[yellow]No posts to ingest.[/yellow]")
        return
    console.print(f"\n[bold]Persisting {len(all_posts)} posts...[/bold]")
    stored, errors = persist_posts(all_posts)
    console.print(f"\n[green]Persisted: {stored}[/green]")
    if errors:
        console.print(f"[yellow]Errors: {errors}[/yellow]")


def memory_status_cmd():
    console.print("[bold]Memory Integration Status[/bold]\n")
    if not check_memory_available():
        console.print("  [red]Memory skill not found[/red]")
        return
    console.print("  [green]Memory skill: Found[/green]")
    connected, status = check_memory_service()
    console.print(f"  Memory service: [{'green' if connected else 'yellow'}]{status}[/]")
    console.print(f"  [cyan]Scope:[/cyan] {get_memory_scope()}")
    console.print("\n[bold]Auto-tagging Patterns:[/bold]")
    for pattern, tag in SECURITY_KEYWORDS[:5]:
        console.print(f"  {tag}: {pattern}")
    console.print(f"  ... and {len(SECURITY_KEYWORDS) - 5} more")
