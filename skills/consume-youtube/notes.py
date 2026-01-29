"""Note management for consume-youtube."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from rich.console import Console

from consume_common.notes import HorusNotesManager
from consume_common.registry import ContentRegistry
from consume_common.memory_bridge import MemoryBridge

console = Console()


def add_note(
    video_id: str,
    timestamp: float,
    note: str,
    agent_id: str = "horus_lupercal",
    context: Optional[str] = None,
    registry_path: Optional[Path] = None
) -> dict[str, object]:
    """Add a note to a video at a timestamp."""
    if not registry_path:
        registry_path = Path.home() / ".pi" / "consume-youtube" / "registry.json"

    registry = ContentRegistry(registry_path)
    video = None
    for entry in registry.list_content("youtube"):
        if entry.get("metadata", {}).get("video_id") == video_id:
            video = entry
            break

    if not video:
        console.print(f"[red]Video {video_id} not found[/red]")
        return {}

    video_title = video.get("title", video_id)

    notes_dir = Path.home() / ".pi" / "consume-youtube" / "notes"
    notes_manager = HorusNotesManager(notes_dir)

    position = {
        "type": "timestamp",
        "value": timestamp,
        "context": context or f"{video_title} at {timestamp:.1f}s"
    }

    note_entry = notes_manager.add_note(
        content_type="youtube",
        content_id=video_id,
        agent_id=agent_id,
        position=position,
        note=note,
        tags=["youtube", "segment"],
    )

    memory_bridge = MemoryBridge()
    memory_bridge.store_consumption_insight(
        content_type="youtube",
        content_title=video_title,
        insight=note,
        agent_id=agent_id,
    )

    console.print(f"[green]Note added: {note_entry['note_id']}[/green]")
    return note_entry


def list_notes(
    video_id: Optional[str] = None,
    agent_id: Optional[str] = None
) -> list[dict[str, object]]:
    """List notes for videos."""
    notes_dir = Path.home() / ".pi" / "consume-youtube" / "notes"
    notes_manager = HorusNotesManager(notes_dir)
    return notes_manager.list_notes(content_id=video_id, agent_id=agent_id)


def main() -> None:
    """CLI entry point for notes."""
    import argparse

    parser = argparse.ArgumentParser(description="Manage YouTube notes")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    add_parser = subparsers.add_parser("add", help="Add a note")
    add_parser.add_argument("--video", required=True, help="Video ID")
    add_parser.add_argument("--timestamp", type=float, required=True, help="Timestamp in seconds")
    add_parser.add_argument("--note", required=True, help="Note text")
    add_parser.add_argument("--agent", default="horus_lupercal", help="Agent ID")
    add_parser.add_argument("--context", help="Optional context")

    list_parser = subparsers.add_parser("list", help="List notes")
    list_parser.add_argument("--video", help="Filter by video ID")
    list_parser.add_argument("--agent", help="Filter by agent ID")
    list_parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if args.command == "add":
        note_entry = add_note(
            video_id=args.video,
            timestamp=args.timestamp,
            note=args.note,
            agent_id=args.agent,
            context=args.context,
        )
        if note_entry:
            print(json.dumps(note_entry, indent=2))
        else:
            raise SystemExit(1)
    elif args.command == "list":
        notes = list_notes(video_id=args.video, agent_id=args.agent)
        if args.json:
            print(json.dumps({"notes": notes}, indent=2))
        else:
            if not notes:
                console.print("[yellow]No notes found[/yellow]")
                return
            for note in notes:
                console.print(f"\n[bold]{note['content_id']}[/bold] at {note['position']['value']}")
                console.print(f"  Note: {note['note']}")
                console.print(f"  Agent: {note['agent_id']}")
                console.print(f"  Time: {note['timestamp']}")
    else:
        parser.print_help()
        raise SystemExit(1)


if __name__ == "__main__":
    main()
