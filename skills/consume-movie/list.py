"""List movies functionality for consume-movie."""

import json
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table

console = Console()


def list_movies(json_output: bool = False, registry_path: Optional[Path] = None) -> list[dict]:
    """List all ingested movies.

    Args:
        json_output: Output as JSON
        registry_path: Override registry path

    Returns:
        List of movie dicts
    """
    from consume_common.registry import ContentRegistry

    if not registry_path:
        registry_path = Path.home() / ".pi" / "consume-movie" / "registry.json"

    registry = ContentRegistry(registry_path)
    movies = registry.list_content("movie")

    if json_output:
        return movies

    if not movies:
        console.print("[yellow]No movies found in registry[/yellow]")
        return []

    # Create table
    table = Table(title="Ingested Movies")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Title", style="green")
    table.add_column("Duration", justify="right")
    table.add_column("Consumed", justify="right")
    table.add_column("Last Viewed", justify="right")

    for movie in movies:
        duration = movie.get("metadata", {}).get("duration", 0)
        consume_count = movie.get("consume_count", 0)
        last_consumed = movie.get("last_consumed")

        duration_str = f"{duration/60:.1f}m" if duration else "Unknown"
        consumed_str = str(consume_count)
        last_str = last_consumed.split("T")[0] if last_consumed else "Never"

        table.add_row(
            movie["content_id"][:8] + "...",
            movie.get("title", "Unknown"),
            duration_str,
            consumed_str,
            last_str
        )

    console.print(table)
    return movies


def main():
    """CLI entry point for list."""
    import argparse

    parser = argparse.ArgumentParser(description="List ingested movies")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    movies = list_movies(json_output=args.json)

    if args.json:
        print(json.dumps({"movies": movies}, indent=2))


if __name__ == "__main__":
    main()