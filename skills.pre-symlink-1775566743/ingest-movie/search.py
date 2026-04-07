"""
Movie Ingest Skill - Search Module
NZBGeek search functionality via ops-nzbgeek skill composition.
"""
import json
import os
import subprocess
from pathlib import Path
from rich.console import Console
from rich.table import Table

from utils import release_has_subtitle_hint

console = Console()

# Category mapping: ingest-movie numeric -> ops-nzbgeek named
CATEGORY_MAP = {
    "2000": "movies",
    "5000": "tv",
    "3000": "music",
    "4000": "apps",
    "7000": "books",
}


def search_nzb(term: str, cat: str = "2000", limit: int = 10) -> list[dict]:
    """
    Search NZBGeek for movie releases by delegating to ops-nzbgeek skill.

    This function composes with the ops-nzbgeek skill for all Usenet search operations,
    following the verb-prefix composability pattern.

    Args:
        term: Movie title to search
        cat: Category (2000=Movies, 5000=TV, 3000=Music)
        limit: Max results to return

    Returns:
        List of result items in ingest-movie format
    """
    # Map numeric category to named category
    category_name = CATEGORY_MAP.get(cat, "movies")

    # Compose with ops-nzbgeek skill
    ops_nzbgeek_path = Path.home() / ".pi" / "skills" / "ops-nzbgeek" / "run.sh"

    if not ops_nzbgeek_path.exists():
        console.print("[red]ops-nzbgeek skill not found. Install it first.[/red]")
        return []

    try:
        console.print(f"[cyan]Searching NZBGeek for '{term}' (via ops-nzbgeek)...[/cyan]")

        # Change to ops-nzbgeek directory for proper uv environment resolution
        result = subprocess.run(
            [
                "bash",
                str(ops_nzbgeek_path),
                "search",
                term,
                "--category", category_name,
                "--limit", str(limit),
                "--json"
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
            cwd=ops_nzbgeek_path.parent,  # Run from ops-nzbgeek directory
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )

        # Parse JSON response from ops-nzbgeek
        items = json.loads(result.stdout)

        return items[:limit]

    except subprocess.CalledProcessError as e:
        console.print(f"[red]ops-nzbgeek search failed: {e.stderr}[/red]")
        return []
    except subprocess.TimeoutExpired:
        console.print("[red]ops-nzbgeek search timed out (30s)[/red]")
        return []
    except json.JSONDecodeError as e:
        console.print(f"[red]Failed to parse ops-nzbgeek response: {e}[/red]")
        return []
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
