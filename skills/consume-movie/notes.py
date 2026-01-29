"""Note management for consume-movie."""

import json
from pathlib import Path
from typing import Optional
from rich.console import Console

console = Console()


def add_note(
    movie_id: str,
    timestamp: float,
    note: str,
    agent_id: str = "horus_lupercal",
    context: Optional[str] = None,
    registry_path: Optional[Path] = None
) -> dict:
    """Add a note to a movie at a specific timestamp.

    Args:
        movie_id: Movie identifier
        timestamp: Time in seconds
        note: Note text
        agent_id: Agent taking the note
        context: Optional context text
        registry_path: Override registry path

    Returns:
        Created note dict
    """
    from consume_common.registry import ContentRegistry
    from consume_common.notes import HorusNotesManager
    from consume_common.memory_bridge import MemoryBridge

    if not registry_path:
        registry_path = Path.home() / ".pi" / "consume-movie" / "registry.json"

    # Verify movie exists
    registry = ContentRegistry(registry_path)
    movie = registry.get_content(movie_id)
    if not movie:
        console.print(f"[red]Movie {movie_id} not found[/red]")
        return {}

    # Get movie title for context
    movie_title = movie.get("title", "Unknown Movie")

    # Create notes manager
    notes_dir = Path.home() / ".pi" / "consume-movie" / "notes"
    notes_manager = HorusNotesManager(notes_dir)

    # Add note
    position = {
        "type": "timestamp",
        "value": timestamp,
        "context": context or f"{movie_title} at {timestamp:.1f}s"
    }

    note_entry = notes_manager.add_note(
        content_type="movie",
        content_id=movie_id,
        agent_id=agent_id,
        position=position,
        note=note,
        tags=["movie", "scene_analysis"]
    )

    # Store in memory
    memory_bridge = MemoryBridge()
    memory_bridge.store_consumption_insight(
        content_type="movie",
        content_title=movie_title,
        insight=note,
        agent_id=agent_id
    )

    console.print(f"[green]Note added: {note_entry['note_id']}[/green]")
    return note_entry


def list_notes(
    movie_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    registry_path: Optional[Path] = None
) -> list[dict]:
    """List notes for movies.

    Args:
        movie_id: Filter by movie ID
        agent_id: Filter by agent ID
        registry_path: Override registry path

    Returns:
        List of note dicts
    """
    from consume_common.notes import HorusNotesManager

    notes_dir = Path.home() / ".pi" / "consume-movie" / "notes"
    notes_manager = HorusNotesManager(notes_dir)

    notes = notes_manager.list_notes(
        content_id=movie_id,
        agent_id=agent_id
    )

    return notes


def main():
    """CLI entry point for notes."""
    import argparse

    parser = argparse.ArgumentParser(description="Manage movie notes")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Add note
    add_parser = subparsers.add_parser("add", help="Add a note")
    add_parser.add_argument("--movie", required=True, help="Movie ID")
    add_parser.add_argument("--timestamp", type=float, required=True, help="Time in seconds")
    add_parser.add_argument("--note", required=True, help="Note text")
    add_parser.add_argument("--agent", default="horus_lupercal", help="Agent ID")
    add_parser.add_argument("--context", help="Optional context")

    # List notes
    list_parser = subparsers.add_parser("list", help="List notes")
    list_parser.add_argument("--movie", help="Filter by movie ID")
    list_parser.add_argument("--agent", help="Filter by agent ID")
    list_parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if args.command == "add":
        note = add_note(
            movie_id=args.movie,
            timestamp=args.timestamp,
            note=args.note,
            agent_id=args.agent,
            context=args.context
        )
        if note:
            print(json.dumps(note, indent=2))
        else:
            exit(1)

    elif args.command == "list":
        notes = list_notes(
            movie_id=args.movie,
            agent_id=args.agent
        )
        if args.json:
            print(json.dumps({"notes": notes}, indent=2))
        else:
            if not notes:
                console.print("[yellow]No notes found[/yellow]")
                return

            for note in notes:
                console.print(f"\n[bold]{note['content_id']}[/bold] at {note['position']['value']:.1f}s")
                console.print(f"  Note: {note['note']}")
                console.print(f"  Agent: {note['agent_id']}")
                console.print(f"  Time: {note['timestamp']}")

    else:
        parser.print_help()
        exit(1)


if __name__ == "__main__":
    main()