"""
Movie Ingest Skill - Search Module
NZBGeek search functionality.
"""
from rich.console import Console
from rich.table import Table

from config import NZB_API_KEY, NZB_BASE_URL, validate_env
from utils import get_requests_session, release_has_subtitle_hint

console = Console()


def search_nzb(term: str, cat: str = "2000", limit: int = 10) -> list[dict]:
    """
    Search NZBGeek for movie releases.

    Args:
        term: Movie title to search
        cat: Category (2000=Movies, 5000=TV)
        limit: Max results to return

    Returns:
        List of result items
    """
    validate_env(console)

    if not NZB_API_KEY:
        console.print("[red]NZB_GEEK_API_KEY not set. Cannot search.[/red]")
        return []

    params = {
        "t": "search",
        "q": term,
        "cat": cat,
        "apikey": NZB_API_KEY,
        "o": "json"
    }

    url = f"{NZB_BASE_URL.rstrip('/')}/api"
    try:
        console.print(f"[cyan]Searching NZBGeek for '{term}'...[/cyan]")
        session = get_requests_session()
        resp = session.get(url, params=params, timeout=15)
        resp.raise_for_status()

        data = resp.json()
        items = []

        # Handle XML-to-JSON quirks (single item vs list)
        if "channel" in data and "item" in data["channel"]:
            items = data["channel"]["item"]
            if isinstance(items, dict):
                items = [items]
        elif "item" in data:
            items = data["item"]

        return items[:limit]

    except Exception as e:
        console.print(f"[red]Search failed: {e}[/red]")
        return []


def display_search_results(items: list[dict], term: str) -> None:
    """Display search results in a formatted table."""
    if not items:
        console.print("[yellow]No results found.[/yellow]")
        return

    table = Table(title=f"Results for '{term}'")
    table.add_column("Title", style="green")
    table.add_column("Subs?", style="yellow", justify="center")
    table.add_column("Size", style="cyan")
    table.add_column("PubDate", style="dim")
    table.add_column("Link", style="blue")

    for item in items:
        size = item.get("size", "0")
        try:
            size_mb = int(size) / (1024 * 1024)
            size_str = f"{size_mb:.1f} MB"
        except (ValueError, TypeError):
            size_str = str(size)
        subs_flag = "✅" if release_has_subtitle_hint(item) else ""
        table.add_row(
            item.get("title", "Unknown")[:60],
            subs_flag,
            size_str,
            item.get("pubDate", "")[:16],
            item.get("link", "")[:40] + "..."
        )
    console.print(table)
