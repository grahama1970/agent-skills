"""List functionality for consume-music."""

import json
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table

from consume_common.registry import ContentRegistry
import typer

console = Console()


def list_music(registry_path: Optional[Path] = None) -> list[dict]:
    """List all music in registry."""
    if not registry_path:
        registry_path = Path.home() / ".pi" / "consume-music" / "registry.json"

    if not registry_path.exists():
        return []

    registry = ContentRegistry(registry_path)
    return registry.list_content("music")


def main(
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """CLI entry point for list."""

    entries = list_music()

    if json:
        print(json.dumps({"music": entries}, indent=2, default=str))
        return

    if not entries:
        console.print("[yellow]No music in registry. Run './run.sh sync' first.[/yellow]")
        return

    table = Table(title=f"Music Catalog ({len(entries)} tracks)")
    table.add_column("Artist", style="bold")
    table.add_column("Track")
    table.add_column("Domain", style="cyan")
    table.add_column("Bridges", style="yellow")

    for entry in entries[:50]:  # Cap display at 50
        meta = entry.get("metadata", {})
        bridges = ", ".join(meta.get("bridge_attributes", [])) or "-"
        table.add_row(
            meta.get("artist", "?")[:30],
            meta.get("track", entry.get("title", "?"))[:40],
            meta.get("domain", "")[:20],
            bridges,
        )

    if len(entries) > 50:
        table.add_row("...", f"({len(entries) - 50} more)", "", "")

    console.print(table)


if __name__ == "__main__":
    main()
