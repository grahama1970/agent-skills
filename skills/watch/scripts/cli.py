#!/usr/bin/env python3
"""Watch CLI — Typer entry point for best-practices-skills compliance."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

logger.remove()
logger.add(sys.stderr, format="{time:HH:mm:ss} | {level:<7} | {message}", level="INFO")

SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR))

from watch import run_watch  # Import the extracted logic


app = typer.Typer(help="Watch any video: scene-change frames, transcript, scene analysis")


@app.command()
def watch(
    source: str = typer.Argument(..., help="Video URL, local file path, or movie title"),
    scene_change: bool = typer.Option(True, "--scene-change/--no-scene-change", help="Use scene-change detection"),
    fps: Optional[float] = typer.Option(None, "--fps", help="Override auto-fps"),
    max_frames: int = typer.Option(100, "--max-frames", help="Max frames (default 100)"),
    resolution: int = typer.Option(512, "--resolution", help="Frame width in pixels"),
    start: Optional[str] = typer.Option(None, "--start", help="Start time (SS, MM:SS, HH:MM:SS)"),
    end: Optional[str] = typer.Option(None, "--end", help="End time (SS, MM:SS, HH:MM:SS)"),
    subtitle: Optional[Path] = typer.Option(None, "--subtitle", help="Path to SRT subtitle file"),
    emotion: Optional[str] = typer.Option(None, "--emotion", help="Emotion tag for scene filtering"),
    tag: Optional[str] = typer.Option(None, "--tag", help="SRT cue tag for scene filtering"),
    query: Optional[str] = typer.Option(None, "--query", help="Free-text search in SRT"),
    whisper: bool = typer.Option(True, "--whisper/--no-whisper", help="Enable Whisper fallback"),
    doc2qra: bool = typer.Option(False, "--doc2qra", help="Feed transcript to doc2qra for QRA extraction"),
    persona: Optional[str] = typer.Option(None, "--persona", help="Persona name (e.g. embry) for persona_memory tagging"),
    out_dir: Optional[Path] = typer.Option(None, "--out-dir", help="Working directory"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON instead of markdown"),
):
    """Watch a video: extract frames, transcript, and optional scene analysis."""
    exit_code = run_watch(
        source=source,
        scene_change=scene_change,
        fps=fps,
        max_frames=max_frames,
        resolution=resolution,
        start=start,
        end=end,
        subtitle=str(subtitle) if subtitle else None,
        emotion=emotion,
        tag=tag,
        query=query,
        whisper=whisper,
        doc2qra=doc2qra,
        persona=persona,
        out_dir=str(out_dir) if out_dir else None,
        json_output=json_output,
    )
    raise typer.Exit(code=exit_code)


if __name__ == "__main__":
    app()
