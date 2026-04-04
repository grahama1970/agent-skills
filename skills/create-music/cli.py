#!/usr/bin/env python3
"""
create-music CLI

AI-assisted music creation: voice conversion (RVC) and music generation (MusicGen).
Stem separation has moved to the create-stems skill.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

app = typer.Typer(help="AI-assisted music creation for Horus persona")
console = Console()

SCRIPT_DIR = Path(__file__).resolve().parent


@app.command("musicgen")
def musicgen_generate(
    checkpoint_dir: Path = typer.Option(..., "--checkpoint-dir", "-c", help="MusicGen checkpoint directory"),
    prompt: str = typer.Option(..., "--prompt", "-p", help="Text prompt for generation"),
    seconds: int = typer.Option(30, "--seconds", "-s", help="Duration in seconds"),
    out: Path = typer.Option(..., "--out", "-o", help="Output audio file"),
):
    """Generate music using fine-tuned MusicGen checkpoint."""
    try:
        from audiocraft.models import MusicGen
        import torchaudio
    except ImportError:
        console.print("[red]audiocraft not installed. Run: pip install audiocraft[/red]")
        raise typer.Exit(code=1)

    if not checkpoint_dir.exists():
        console.print(f"[red]Checkpoint directory not found: {checkpoint_dir}[/red]")
        raise typer.Exit(code=1)

    console.print(f"[green]Loading MusicGen from {checkpoint_dir}...[/green]")
    model = MusicGen.get_pretrained(str(checkpoint_dir))
    model.set_generation_params(duration=seconds)

    console.print(f"[green]Generating {seconds}s for prompt: '{prompt}'[/green]")
    wav = model.generate([prompt])

    # Save output
    out.parent.mkdir(parents=True, exist_ok=True)
    torchaudio.save(str(out), wav[0].cpu(), model.sample_rate)
    console.print(f"[green]Output: {out}[/green]")


@app.command("ingest-raw")
def ingest_raw(
    input_dir: Path = typer.Option(..., "--input", "-i", help="Directory with raw audio files"),
    out: Path = typer.Option(..., "--out", "-o", help="Output registry JSON"),
):
    """Ingest raw audio files into a registry."""
    if not input_dir.exists():
        console.print(f"[red]Input directory not found: {input_dir}[/red]")
        raise typer.Exit(code=1)

    registry = []
    for audio_file in input_dir.glob("**/*.wav"):
        entry = {
            "path": str(audio_file),
            "name": audio_file.stem,
            "format": audio_file.suffix,
        }
        registry.append(entry)
        console.print(f"  Ingested: {audio_file.name}")

    for audio_file in input_dir.glob("**/*.mp3"):
        entry = {
            "path": str(audio_file),
            "name": audio_file.stem,
            "format": audio_file.suffix,
        }
        registry.append(entry)
        console.print(f"  Ingested: {audio_file.name}")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(registry, indent=2))
    console.print(f"[green]Registry ({len(registry)} files): {out}[/green]")


if __name__ == "__main__":
    app()
