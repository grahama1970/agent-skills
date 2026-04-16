"""Notes functionality for consume-music."""

import json
import sys
from pathlib import Path
from typing import Optional

import typer

from rich.console import Console

from consume_common.notes import HorusNotesManager
from loguru import logger

console = Console()


def add_note(
    track_id: str,
    note: str,
    agent_id: Optional[str] = None,
    notes_dir: Optional[Path] = None,
) -> bool:
    """Add a note to a music track."""
    if not notes_dir:
        notes_dir = Path.home() / ".pi" / "consume-music" / "notes"

    manager = HorusNotesManager(notes_dir, agent_id=agent_id)
    position = {"type": "track", "value": track_id, "context": "music note"}
    manager.add_note(content_id=track_id, position=position, note=note)
    console.print(f"[green]Note added to track {track_id}[/green]")

    # Post-hook: Learn annotation to memory
    try:
        from memory_integration import learn_annotation
        learn_annotation(
            track_title=track_id,
            artist="",
            annotation=note,
            persona_id=agent_id,
        )
    except ImportError:
        pass
    except Exception as e:
        logger.debug("import failed: {}", e)

    return True


def list_notes(
    track_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    notes_dir: Optional[Path] = None,
) -> list[dict]:
    """List notes, optionally filtered by track."""
    if not notes_dir:
        notes_dir = Path.home() / ".pi" / "consume-music" / "notes"

    manager = HorusNotesManager(notes_dir, agent_id=agent_id)
    notes = manager.list_notes(content_id=track_id)
    return notes


app = typer.Typer(help="Notes functionality for consume-music")


@app.command()
def add(
    track: str = typer.Option(..., help="Track content ID"),
    note: str = typer.Option(..., help="Note text"),
    agent: Optional[str] = typer.Option(None, help="Agent ID"),
):
    """Add a note to a track."""
    add_note(track_id=track, note=note, agent_id=agent)


@app.command(name="list")
def list_cmd(
    track: Optional[str] = typer.Option(None, help="Filter by track ID"),
    agent: Optional[str] = typer.Option(None, help="Filter by agent ID"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """List notes."""
    notes = list_notes(track_id=track, agent_id=agent)

    if as_json:
        print(json.dumps({"notes": notes}, indent=2, default=str))
    else:
        if not notes:
            console.print("[yellow]No notes found[/yellow]")
            return
        for n in notes:
            console.print(f"  [{n.get('content_id', '?')}] {n.get('note', '')}")


if __name__ == "__main__":
    app()

