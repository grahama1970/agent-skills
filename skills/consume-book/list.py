"""List books functionality for consume-book."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table

from consume_common.registry import ContentRegistry

console = Console()


def list_books(json_output: bool = False, registry_path: Optional[Path] = None) -> list[dict[str, object]]:
    """List all ingested books."""
    if not registry_path:
        registry_path = Path.home() / ".pi" / "consume-book" / "registry.json"

    registry = ContentRegistry(registry_path)
    books = registry.list_content("book")

    if json_output:
        return books

    if not books:
        console.print("[yellow]No books found in registry[/yellow]")
        return []

    table = Table(title="Ingested Books")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Title", style="green")
    table.add_column("Format", style="magenta")
    table.add_column("Consumed", justify="right")
    table.add_column("Last Read", justify="right")

    for book in books:
        format_hint = str(book.get("metadata", {}).get("format", "text"))
        consume_count = book.get("consume_count", 0)
        last_consumed = book.get("last_consumed", "Never")
        last_str = last_consumed.split("T")[0] if last_consumed != "Never" else "Never"

        table.add_row(
            book["content_id"][:8] + "...",
            book.get("title", "Unknown"),
            format_hint,
            str(consume_count),
            last_str,
        )

    console.print(table)
    return books


def main() -> None:
    """CLI entry point for list."""
    import argparse

    parser = argparse.ArgumentParser(description="List ingested books")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    books = list_books(json_output=args.json)
    if args.json:
        print(json.dumps({"books": books}, indent=2))


if __name__ == "__main__":
    main()
