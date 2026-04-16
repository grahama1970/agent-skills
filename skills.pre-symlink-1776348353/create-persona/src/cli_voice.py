"""
Voice/TTS training CLI commands for personas.
"""
import json
import os
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from loguru import logger as log

from .cli_app import app, console

from .persona import (
    get_persona,
    list_personas,
)
from .voice import (
    train_persona_voice,
    get_voice_status,
    synthesize_speech,
    discover_voice_sources,
    VoiceTrainingConfig,
)

# =============================================================================
# Voice Command Group
# =============================================================================

voice_app = typer.Typer(help="Voice/TTS training for personas")
app.add_typer(voice_app, name="voice")


@voice_app.command("train")
def voice_train(
    name: str = typer.Argument(..., help="Persona name"),
    scope: Optional[str] = typer.Option("personas", "--scope", "-s", help="Memory scope"),
    url: Optional[list[str]] = typer.Option(None, "--url", "-u", help="YouTube URL (repeatable)"),
    discover: bool = typer.Option(False, "--discover", "-d", help="Auto-discover URLs from memory"),
    model_size: str = typer.Option("0.6B", "--model-size", "-m", help="Model size: 0.6B or 1.7B"),
    epochs: int = typer.Option(5, "--epochs", "-e", help="Training epochs"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without training"),
    background: bool = typer.Option(False, "--background", "-b", help="Run in background"),
):
    """
    Train a Qwen3-TTS voice model for a persona.

    Collects audio from YouTube (interviews, lectures, talks), builds a TTS
    dataset, and trains a Qwen3-TTS model that can synthesize speech in the
    persona's voice.

    Examples:
        # Train with specific URLs
        ./run.sh voice train "Robert Sapolsky" --url "https://youtube.com/watch?v=abc123"

        # Auto-discover URLs from persona's learning history
        ./run.sh voice train "Robert Sapolsky" --discover

        # Train 1.7B model for higher quality
        ./run.sh voice train "Robert Sapolsky" --discover --model-size 1.7B
    """
    # Collect URLs
    urls = list(url) if url else []

    if discover:
        console.print("[dim]Discovering voice sources from memory...[/dim]")
        discovered = discover_voice_sources(name, scope)
        if discovered:
            console.print(f"  Found {len(discovered)} YouTube URLs")
            urls.extend(discovered)
        else:
            console.print("  [yellow]No YouTube URLs found in memory[/yellow]")

    if not urls:
        console.print("[red]No URLs provided. Use --url or --discover[/red]")
        raise typer.Exit(1)

    console.print(f"\n[bold]Voice Training: {name}[/bold]")
    console.print(f"  Model size: {model_size}")
    console.print(f"  Epochs: {epochs}")
    console.print(f"  URLs: {len(urls)}")
    for i, u in enumerate(urls[:5], 1):
        console.print(f"    {i}. {u[:60]}...")
    if len(urls) > 5:
        console.print(f"    ... and {len(urls) - 5} more")
    console.print()

    if dry_run:
        console.print("[dim][dry-run] Would train voice model[/dim]")
        return

    if background:
        raise NotImplementedError("Background training mode not yet implemented — run without --background")

    # Run training with progress
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Starting...", total=100)

        def update_progress(pct: float, msg: str):
            progress.update(task, completed=pct, description=msg)

        result = train_persona_voice(
            persona_name=name,
            youtube_urls=urls,
            scope=scope,
            model_size=model_size,
            epochs=epochs,
            progress_callback=update_progress,
        )

    # Show result
    console.print()
    if result.status == "ready":
        console.print(f"[green]Voice training complete![/green]")
        console.print(f"  Model path: {result.model_path}")
        console.print(f"  Audio collected: {result.audio_collected_minutes:.1f} minutes")

        # Update persona with voice model path
        persona = get_persona(name, scope)
        if persona:
            persona.voice_model_path = result.model_path
            persona.voice_source_urls = urls
            persona.voice_status = "ready"
            persona.voice_trained_at = result.completed_at
            persona.update_timestamp()
            create_persona(persona, store=True)
            console.print(f"  [green]Updated persona with voice model path[/green]")
    else:
        console.print(f"[red]Voice training failed: {result.status}[/red]")
        if result.error_message:
            console.print(f"  Error: {result.error_message}")
        raise typer.Exit(1)


@voice_app.command("status")
def voice_status(
    name: str = typer.Argument(..., help="Persona name"),
    scope: Optional[str] = typer.Option("personas", "--scope", "-s", help="Memory scope"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Check voice training status for a persona.

    Examples:
        ./run.sh voice status "Robert Sapolsky"
    """
    status = get_voice_status(name, scope)

    if as_json:
        console.print(json.dumps(status.to_dict(), indent=2))
        return

    console.print(f"\n[bold]Voice Status: {name}[/bold]")
    console.print()

    # Status with color
    status_colors = {
        "ready": "green",
        "training": "yellow",
        "collecting": "yellow",
        "building_dataset": "yellow",
        "pending": "dim",
        "failed": "red",
        "unknown": "dim",
    }
    color = status_colors.get(status.status, "white")
    console.print(f"  Status: [{color}]{status.status}[/{color}]")

    if status.audio_collected_minutes > 0:
        console.print(f"  Audio collected: {status.audio_collected_minutes:.1f} minutes")

    if status.current_epoch > 0:
        console.print(f"  Training: epoch {status.current_epoch}/{status.total_epochs}")

    if status.progress_pct > 0:
        bar = "█" * int(status.progress_pct / 10) + "░" * (10 - int(status.progress_pct / 10))
        console.print(f"  Progress: [{bar}] {status.progress_pct:.0f}%")

    if status.model_path:
        console.print(f"  Model: {status.model_path}")

    if status.error_message:
        console.print(f"  [red]Error: {status.error_message}[/red]")

    if status.started_at:
        console.print(f"\n  Started: {status.started_at[:19]}")
    if status.completed_at:
        console.print(f"  Completed: {status.completed_at[:19]}")


@voice_app.command("synthesize")
def voice_synthesize(
    name: str = typer.Argument(..., help="Persona name"),
    text: str = typer.Option(..., "--text", "-t", help="Text to synthesize"),
    output: Path = typer.Option(None, "--output", "-o", help="Output WAV file"),
    scope: Optional[str] = typer.Option("personas", "--scope", "-s", help="Memory scope"),
):
    """
    Synthesize speech using a persona's trained voice.

    Examples:
        ./run.sh voice synthesize "Robert Sapolsky" --text "Hello, I'm Robert Sapolsky" --output hello.wav
    """
    from pathlib import Path as P

    # Get persona and check for voice model
    persona = get_persona(name, scope)
    if not persona:
        # Try other scopes
        for s in ["personas", "behavioral", "clients"]:
            persona = get_persona(name, s)
            if persona:
                break

    if not persona:
        console.print(f"[red]Persona '{name}' not found[/red]")
        raise typer.Exit(1)

    if not persona.voice_model_path:
        console.print(f"[red]Persona '{name}' has no trained voice model[/red]")
        console.print("[dim]Train one with: ./run.sh voice train \"{}\" --discover[/dim]".format(name))
        raise typer.Exit(1)

    model_path = P(persona.voice_model_path)
    if not model_path.exists():
        console.print(f"[red]Voice model not found: {model_path}[/red]")
        raise typer.Exit(1)

    # Default output path
    if not output:
        slug = name.lower().replace(" ", "_").replace("'", "")
        output = P(f"{slug}_speech.wav")

    console.print(f"\n[bold]Synthesizing speech...[/bold]")
    console.print(f"  Persona: {name}")
    console.print(f"  Text: {text[:60]}...")
    console.print(f"  Output: {output}")
    console.print()

    success, error = synthesize_speech(model_path, text, output)

    if success:
        console.print(f"[green]Generated: {output}[/green]")
    else:
        console.print(f"[red]Synthesis failed: {error}[/red]")
        raise typer.Exit(1)


@voice_app.command("list")
def voice_list(
    scope: Optional[str] = typer.Option("personas", "--scope", "-s", help="Memory scope"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    List personas with trained voice models.

    Examples:
        ./run.sh voice list
        ./run.sh voice list --json
    """
    personas = list_personas(scope=scope)

    # Filter to those with voice models
    voiced = [p for p in personas if p.voice_model_path or p.voice_status]

    if as_json:
        data = [
            {
                "name": p.name,
                "voice_status": p.voice_status or "none",
                "voice_model_path": p.voice_model_path or "",
                "voice_trained_at": p.voice_trained_at or "",
            }
            for p in voiced
        ]
        console.print(json.dumps(data, indent=2))
        return

    if not voiced:
        console.print("[dim]No personas with voice models found[/dim]")
        console.print("[dim]Train one with: ./run.sh voice train \"Name\" --discover[/dim]")
        return

    table = Table(title="Personas with Voice Models")
    table.add_column("Name", style="bold")
    table.add_column("Status")
    table.add_column("Trained At")

    for p in voiced:
        status_colors = {"ready": "green", "training": "yellow", "failed": "red"}
        status = p.voice_status or "none"
        color = status_colors.get(status, "dim")
        trained_at = p.voice_trained_at[:10] if p.voice_trained_at else "-"

        table.add_row(
            p.name,
            f"[{color}]{status}[/{color}]",
            trained_at,
        )

    console.print(table)

