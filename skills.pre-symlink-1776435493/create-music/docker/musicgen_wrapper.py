#!/usr/bin/env python3
"""
MusicGen wrapper for Docker container.
Generates music from text prompts using fine-tuned or pretrained models.
"""
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

app = typer.Typer(help="MusicGen music generation")
console = Console()


@app.command()
def generate(
    prompt: str = typer.Option(..., "--prompt", "-p", help="Text prompt for generation"),
    out: Path = typer.Option(..., "--out", "-o", help="Output audio file path"),
    checkpoint_dir: Optional[Path] = typer.Option(None, "--checkpoint-dir", "-c", help="Path to fine-tuned checkpoint"),
    model: str = typer.Option("small", "--model", "-m", help="Pretrained model: small, medium, large, melody"),
    seconds: int = typer.Option(30, "--seconds", "-s", help="Duration in seconds"),
):
    """Generate music with MusicGen."""
    try:
        from audiocraft.models import MusicGen
        import torchaudio
    except ImportError as e:
        console.print(f"[red]Error importing audiocraft: {e}[/red]")
        raise typer.Exit(code=1)

    # Load model
    if checkpoint_dir:
        console.print(f"[blue]Loading fine-tuned model from {checkpoint_dir}...[/blue]")
        musicgen = MusicGen.get_pretrained(str(checkpoint_dir))
    else:
        console.print(f"[blue]Loading pretrained model: {model}...[/blue]")
        musicgen = MusicGen.get_pretrained(model)

    musicgen.set_generation_params(duration=seconds)

    # Generate
    console.print(f"[green]Generating {seconds}s for prompt: '{prompt}'...[/green]")
    wav = musicgen.generate([prompt])

    # Save output
    out.parent.mkdir(parents=True, exist_ok=True)
    torchaudio.save(str(out), wav[0].cpu(), musicgen.sample_rate)
    console.print(f"[green]Output saved: {out}[/green]")


if __name__ == "__main__":
    app()
