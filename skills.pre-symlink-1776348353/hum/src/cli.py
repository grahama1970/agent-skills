#!/usr/bin/env python3
"""CLI for /hum skill — persona humming pipeline."""

from __future__ import annotations
import os

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .cache import HumCache
from .pipeline import HumPipeline

app = typer.Typer(help="Persona humming pipeline")
console = Console()

DEFAULT_PERSONA = "embry"


@app.command()
def add(
    url: str = typer.Argument(..., help="YouTube URL to process"),
    persona: str = typer.Option(DEFAULT_PERSONA, help="Target persona"),
    mood: Optional[str] = typer.Option(None, help="Comma-separated mood tags"),
    bridges: Optional[str] = typer.Option(None, help="Comma-separated bridge attributes"),
    title: Optional[str] = typer.Option(None, help="Track title (auto-detected if omitted)"),
    artist: Optional[str] = typer.Option(None, help="Artist name"),
    connection: Optional[str] = typer.Option(None, help="Persona connection note"),
    pitch: int = typer.Option(0, help="Pitch shift in semitones"),
    f0method: str = typer.Option("rmvpe", help="F0 extraction: rmvpe, harvest, crepe"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Full pipeline: download, stem, convert to persona voice, cache."""
    pipeline = HumPipeline(persona=persona)

    mood_list = [m.strip() for m in mood.split(",")] if mood else []
    bridge_list = [b.strip() for b in bridges.split(",")] if bridges else []

    console.print(f"[bold]Adding hum for {persona}[/bold]: {url}")
    console.print()

    result = pipeline.add(
        url=url,
        title=title,
        artist=artist,
        mood=mood_list,
        bridges=bridge_list,
        persona_connection=connection or "",
        pitch=pitch,
        f0method=f0method,
    )

    if output_json:
        print(json.dumps(result, indent=2))
    else:
        if result.get("status") == "ok":
            console.print(f"[green]Cached:[/green] {result['track_id']}")
            console.print(f"  File: {result['audio_path']}")
            console.print(f"  Duration: {result.get('duration_s', '?')}s")
        else:
            console.print(f"[red]Failed:[/red] {result.get('error', 'unknown')}")
            raise typer.Exit(1)


@app.command()
def train(
    persona: str = typer.Option(DEFAULT_PERSONA, help="Target persona"),
    epochs: int = typer.Option(200, help="Training epochs"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Train persona RVC voice model from existing TTS samples."""
    pipeline = HumPipeline(persona=persona)

    console.print(f"[bold]Training RVC model for {persona}[/bold]")
    console.print(f"  Epochs: {epochs}")
    console.print()

    result = pipeline.train_voice(epochs=epochs)

    if output_json:
        print(json.dumps(result, indent=2))
    else:
        if result.get("status") == "ok":
            console.print(f"[green]Model trained:[/green] {result['model_path']}")
        else:
            console.print(f"[red]Failed:[/red] {result.get('error', 'unknown')}")
            raise typer.Exit(1)


@app.command("list")
def list_tracks(
    persona: str = typer.Option(DEFAULT_PERSONA, help="Target persona"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List all cached hums for a persona."""
    cache = HumCache(persona=persona)
    tracks = cache.list_tracks()

    if output_json:
        print(json.dumps([t.to_dict() for t in tracks], indent=2))
        return

    if not tracks:
        console.print(f"No hums cached for {persona}")
        console.print(f"  Add one: ./run.sh add <youtube-url> --persona {persona}")
        return

    table = Table(title=f"Hum Cache: {persona}")
    table.add_column("ID", style="cyan")
    table.add_column("Title")
    table.add_column("Artist")
    table.add_column("Mood")
    table.add_column("Bridges")
    table.add_column("Duration")

    for t in tracks:
        table.add_row(
            t.id,
            t.title,
            t.artist,
            ", ".join(t.mood),
            ", ".join(t.bridge_attributes),
            f"{t.duration_s}s" if t.duration_s else "?",
        )

    console.print(table)


@app.command()
def play(
    track_id: str = typer.Argument(..., help="Track ID to play"),
    persona: str = typer.Option(DEFAULT_PERSONA, help="Target persona"),
):
    """Play a cached hum through PipeWire."""
    cache = HumCache(persona=persona)
    track = cache.get_track(track_id)

    if not track:
        console.print(f"[red]Track not found:[/red] {track_id}")
        raise typer.Exit(1)

    audio_path = cache.get_audio_path(track_id)
    if not audio_path.exists():
        console.print(f"[red]Audio file missing:[/red] {audio_path}")
        raise typer.Exit(1)

    console.print(f"Playing: {track.title} by {track.artist}")
    console.print(f"  Mood: {', '.join(track.mood)}")

    import subprocess
    subprocess.run(["pw-play", str(audio_path)], check=True,
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )


@app.command()
def info(
    track_id: str = typer.Argument(..., help="Track ID"),
    persona: str = typer.Option(DEFAULT_PERSONA, help="Target persona"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show detailed track metadata."""
    cache = HumCache(persona=persona)
    track = cache.get_track(track_id)

    if not track:
        console.print(f"[red]Track not found:[/red] {track_id}")
        raise typer.Exit(1)

    if output_json:
        print(json.dumps(track.to_dict(), indent=2))
    else:
        console.print(f"[bold]{track.title}[/bold] by {track.artist}")
        console.print(f"  ID:          {track.id}")
        console.print(f"  Source:      {track.source_url}")
        console.print(f"  Mood:        {', '.join(track.mood)}")
        console.print(f"  Bridges:     {', '.join(track.bridge_attributes)}")
        console.print(f"  Connection:  {track.persona_connection}")
        console.print(f"  Duration:    {track.duration_s}s")
        console.print(f"  Pitch:       {track.pitch_shift}")
        console.print(f"  F0 Method:   {track.f0_method}")
        console.print(f"  Created:     {track.created}")
        console.print(f"  Forbidden:   {track.forbidden}")


def main():
    app()


if __name__ == "__main__":
    main()
