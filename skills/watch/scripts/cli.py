#!/usr/bin/env python3
"""Watch CLI — Typer entry point for best-practices-skills compliance."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer

SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR))

from watch import run_watch  # Import the extracted logic


app = typer.Typer(help="Watch any video: scene-change frames, transcript, scene analysis")


@app.command()
def watch(
    source: str = typer.Argument(..., help="Video URL, local file path, or movie title"),
    scene_change: bool = typer.Option(True, "--scene-change", help="Use scene-change detection"),
    no_scene_change: bool = typer.Option(False, "--no-scene-change", help="Force uniform frame sampling"),
    fps: Optional[float] = typer.Option(None, "--fps", help="Override auto-fps"),
    max_frames: int = typer.Option(100, "--max-frames", help="Max frames (default 100)"),
    resolution: int = typer.Option(256, "--resolution", help="Frame width in pixels"),
    start: Optional[str] = typer.Option(None, "--start", help="Start time (SS, MM:SS, HH:MM:SS)"),
    end: Optional[str] = typer.Option(None, "--end", help="End time (SS, MM:SS, HH:MM:SS)"),
    subtitle: Optional[Path] = typer.Option(None, "--subtitle", help="Path to SRT subtitle file"),
    emotion: Optional[str] = typer.Option(None, "--emotion", help="Emotion tag for scene filtering"),
    tag: Optional[str] = typer.Option(None, "--tag", help="SRT cue tag for scene filtering"),
    query: Optional[str] = typer.Option(None, "--query", help="Free-text search in SRT"),
    whisper: bool = typer.Option(True, "--whisper", help="Enable Whisper fallback"),
    no_whisper: bool = typer.Option(False, "--no-whisper", help="Skip Whisper fallback"),
    doc2qra: bool = typer.Option(False, "--doc2qra", help="Feed transcript to doc2qra for QRA extraction"),
    out_dir: Optional[Path] = typer.Option(None, "--out-dir", help="Working directory"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON instead of markdown"),
):
    """Watch a video: extract frames, transcript, and optional scene analysis."""
    use_scene_change = scene_change and not no_scene_change
    use_whisper = whisper and not no_whisper
    exit_code = run_watch(
        source=source,
        scene_change=use_scene_change,
        fps=fps,
        max_frames=max_frames,
        resolution=resolution,
        start=start,
        end=end,
        subtitle=str(subtitle) if subtitle else None,
        emotion=emotion,
        tag=tag,
        query=query,
        whisper=use_whisper,
        doc2qra=doc2qra,
        out_dir=str(out_dir) if out_dir else None,
        json_output=json_output,
    )
    raise typer.Exit(code=exit_code)


if __name__ == "__main__":
    app()
