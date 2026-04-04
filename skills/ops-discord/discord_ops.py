#!/usr/bin/env python3
"""
Discord Operations Skill - CLI Entry Point

TOS-compliant notification monitor for YOUR Discord server.
Watches for security content forwarded by researchers, then pushes
to create-paper/dogpile via webhooks and persists to graph-memory.

This is a thin CLI wrapper that delegates to modular components in discord_ops/.
"""

import asyncio
import json
import sys

try:
    import typer
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
except ImportError:
    print("Missing requirements. Run: pip install typer rich", file=sys.stderr)
    sys.exit(1)

# Import from modular package
from discord_ops.config import (
    DEFAULT_KEYWORDS,
    MATCHES_LOG,
    SKILL_DIR,
)
from discord_ops.keyword_matcher import KeywordMatch
from discord_ops.utils import (
    get_bot_token,
    load_config,
    load_keywords,
    save_config,
    save_keywords,
)
from discord_ops.graph_persistence import (
    check_memory_status,
    get_local_matches_count,
    persist_match_to_memory,
    search_memory,
)
from discord_ops.webhook_monitor import (
    forward_to_webhook,
    get_feature_status,
    is_monitor_running,
    run_monitor,
    stop_monitor,
)

# CLI setup
app = typer.Typer(help="Discord notification monitor for security research")
memory_app = typer.Typer(help="Memory/knowledge graph integration")
app.add_typer(memory_app, name="memory")
console = Console()


# =============================================================================
# MAIN COMMANDS
# =============================================================================

@app.command()
def setup():
    """Interactive setup for notification monitoring."""
    features = get_feature_status()

    console.print(Panel(
        "[bold]Discord Notification Monitor Setup[/bold]\n\n"
        "This skill monitors YOUR Discord server for security content\n"
        "forwarded by researchers, then pushes to create-paper/dogpile.",
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
    if features["discord_py"]:
        import discord
        console.print(f"  [green]discord.py installed[/green] (v{discord.__version__})")
    else:
        console.print("  [yellow]discord.py not installed[/yellow]")
        console.print("  Install with: pip install discord.py")
        console.print("  (Optional - can also use clawdbot directly)")

    # Check httpx
    console.print("\n[bold]3. Webhook Support[/bold]")
    if features["httpx"]:
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

     [bold]ops-discord guild add "My Server" <guild_id>[/bold]
     [bold]ops-discord webhook add alerts "https://discord.com/api/webhooks/..."[/bold]
     [bold]ops-discord monitor start[/bold]

  5. Have researchers forward content to your channels
  6. Bot watches for keywords -> forwards to create-paper/dogpile
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
            console.print("Add with: ops-discord guild add \"Server Name\" <guild_id>")
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
            console.print("[yellow]Guild not found[/yellow]")
        return

    console.print("[red]Invalid usage. See: ops-discord guild --help[/red]")


@app.command()
def webhook(
    action: str = typer.Argument(..., help="Action: add, remove, list, test"),
    name: str = typer.Argument(None, help="Webhook name"),
    url: str = typer.Argument(None, help="Webhook URL"),
):
    """Manage output webhooks for forwarding matches."""
    config = load_config()
    webhooks = config.get("webhooks", {})
    features = get_feature_status()

    if action == "list":
        if not webhooks:
            console.print("[yellow]No webhooks configured.[/yellow]")
            console.print("Add with: ops-discord webhook add <name> <url>")
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

        if not features["httpx"]:
            console.print("[red]httpx not installed[/red]")
            raise typer.Exit(1)

        # Create test match
        test_match = KeywordMatch.create_test_match()

        success = asyncio.run(forward_to_webhook(webhooks[name], test_match))
        if success:
            console.print("[green]Webhook test successful![/green]")
        else:
            console.print("[red]Webhook test failed[/red]")
        return

    console.print("[red]Invalid usage. See: ops-discord webhook --help[/red]")


@app.command()
def monitor(
    action: str = typer.Argument("status", help="Action: start, stop, status"),
    webhook_name: str = typer.Option(None, "--webhook", "-w", help="Webhook to forward matches"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Log matches but don't forward"),
    persist: bool = typer.Option(True, "--persist/--no-persist", help="Persist matches to memory"),
):
    """Start/stop the Discord notification monitor."""
    features = get_feature_status()

    if action == "status":
        running, pid = is_monitor_running()
        if running:
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
        if not features["discord_py"]:
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
        asyncio.run(run_monitor(token, webhook_url, dry_run, persist, console))
        return

    if action == "stop":
        success, message = stop_monitor()
        if success:
            console.print(f"[green]{message}[/green]")
        else:
            console.print(f"[yellow]{message}[/yellow]")
        return

    console.print("[red]Invalid action. Use: start, stop, status[/red]")


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
    features = get_feature_status()
    from discord_ops import __version__

    console.print(f"ops-discord v{__version__} (Modular Architecture)")
    console.print(f"  discord.py: {'installed' if features['discord_py'] else 'not installed'}")
    console.print(f"  httpx: {'installed' if features['httpx'] else 'not installed'}")
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
            match = KeywordMatch.from_dict(data)
            result = persist_match_to_memory(match)

            if result.get("stored"):
                stored += 1
            else:
                errors += 1

            if (i + 1) % 10 == 0:
                console.print(f"  Processed {i + 1}/{min(len(lines), limit)}...")

        except (json.JSONDecodeError, KeyError):
            errors += 1
            continue

    console.print(f"\n[green]Persisted: {stored}[/green]")
    if errors:
        console.print(f"[yellow]Errors: {errors}[/yellow]")


@memory_app.command("status")
def memory_status():
    """Check memory integration status."""
    status = check_memory_status()

    console.print("[bold]Memory Integration Status[/bold]\n")

    # Check memory skill exists
    if status["available"]:
        console.print(f"  [green]Memory skill:[/green] {status['path']}")
    else:
        console.print(f"  [red]Memory skill not found at:[/red] {status['path']}")
        console.print("  Make sure .pi/skills/memory/run.sh exists")
        return

    # Check memory service
    if status["connected"]:
        console.print("  [green]Memory service:[/green] Connected")
    else:
        console.print(f"  [yellow]Memory service:[/yellow] {status.get('error', 'Unknown error')}")

    # Show scope
    console.print(f"  [cyan]Scope:[/cyan] {status['scope']}")

    # Show local matches count
    count = get_local_matches_count()
    console.print(f"  [cyan]Local matches:[/cyan] {count}")


if __name__ == "__main__":
    app()
