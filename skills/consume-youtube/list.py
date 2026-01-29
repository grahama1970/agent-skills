"""List videos functionality for consume-youtube."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table

from consume_common.registry import ContentRegistry

console = Console()


def list_videos(
    json_output: bool = False,
    channel: Optional[str] = None,
    registry_path: Optional[Path] = None
) -> list[dict[str, object]]:
    """List all ingested videos."""
    if not registry_path:
        registry_path = Path.home() / ".pi" / "consume-youtube" / "registry.json"

    registry = ContentRegistry(registry_path)
    videos = registry.list_content("youtube")

    if channel:
        videos = [v for v in videos if v.get("metadata", {}).get("channel") == channel]

    if json_output:
        return videos

    if not videos:
        console.print("[yellow]No videos found in registry[/yellow]")
        return []

    table = Table(title="Ingested YouTube Videos")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Title", style="green")
    table.add_column("Channel", style="magenta")
    table.add_column("Segments", justify="right")
    table.add_column("Consumed", justify="right")
    table.add_column("Last Viewed", justify="right")

    for video in videos:
        segments = int(video.get("metadata", {}).get("segment_count", 0))
        consume_count = video.get("consume_count", 0)
        last_consumed = video.get("last_consumed", "Never")
        last_str = last_consumed.split("T")[0] if last_consumed != "Never" else "Never"

        table.add_row(
            video["content_id"][:8] + "...",
            video.get("title", "Unknown"),
            str(video.get("metadata", {}).get("channel", "")),
            str(segments),
            str(consume_count),
            last_str,
        )

    console.print(table)
    return videos


def main() -> None:
    """CLI entry point for list."""
    import argparse

    parser = argparse.ArgumentParser(description="List ingested YouTube videos")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--channel", help="Filter by channel")

    args = parser.parse_args()

    videos = list_videos(json_output=args.json, channel=args.channel)
    if args.json:
        print(json.dumps({"videos": videos}, indent=2))


if __name__ == "__main__":
    main()
