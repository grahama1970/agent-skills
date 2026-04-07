#!/usr/bin/env python3
"""
Check that all stems have the same sample rate and frame count.
"""
from __future__ import annotations

import sys
from pathlib import Path

import soundfile as sf
import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer()
console = Console()


@app.command()
def check(
    stems: Path = typer.Option(..., "--stems", "-s", help="Directory containing stem files"),
    strict: bool = typer.Option(True, "--strict/--no-strict", help="Fail on mismatch"),
):
    """Check that all stems are aligned (same SR and frame count)."""
    if not stems.exists():
        console.print(f"[red]Stems directory not found: {stems}[/red]")
        raise typer.Exit(code=1)

    stem_files = list(stems.glob("*.wav"))
    if not stem_files:
        console.print(f"[yellow]No .wav files found in {stems}[/yellow]")
        raise typer.Exit(code=1)

    table = Table(title="Stem Alignment Check")
    table.add_column("File")
    table.add_column("Sample Rate")
    table.add_column("Frames")
    table.add_column("Channels")

    infos = []
    for f in sorted(stem_files):
        info = sf.info(str(f))
        infos.append((f.name, info.samplerate, info.frames, info.channels))
        table.add_row(f.name, str(info.samplerate), str(info.frames), str(info.channels))

    console.print(table)

    # Check alignment
    if len(infos) < 2:
        console.print("[yellow]Only one stem found, nothing to compare.[/yellow]")
        return

    ref_sr = infos[0][1]
    ref_frames = infos[0][2]
    mismatches = []

    for name, sr, frames, ch in infos[1:]:
        if sr != ref_sr:
            mismatches.append(f"{name}: SR {sr} != {ref_sr}")
        if frames != ref_frames:
            mismatches.append(f"{name}: frames {frames} != {ref_frames}")

    if mismatches:
        console.print("[red]Alignment errors:[/red]")
        for m in mismatches:
            console.print(f"  [red]- {m}[/red]")
        if strict:
            raise typer.Exit(code=1)
    else:
        console.print("[green]All stems aligned![/green]")


if __name__ == "__main__":
    app()
