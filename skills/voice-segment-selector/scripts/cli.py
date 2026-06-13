#!/usr/bin/env python3
"""voice-segment-selector CLI."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import typer

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lib.bundle import build_bundle
from lib.export import export_dataset
from lib.gender import ClassifierMode
from lib.prepare import prepare_job
from lib.review import append_decision, serve_review

app = typer.Typer(add_completion=False, help="Select clean gender-bucketed voice segments for TTS training")


def default_job_dir() -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return Path(f"/tmp/voice-segment-selector-{stamp}")


@app.command()
def prepare(
    input: Path = typer.Option(..., "--input", help="Audio or video file"),
    job_dir: Path = typer.Option(None, "--job-dir", help="Job output directory"),
    classifier: ClassifierMode = typer.Option("both", "--classifier", help="f0, hf, or both"),
    min_clip_sec: float = typer.Option(6.0, "--min-clip-sec"),
    max_clip_sec: float = typer.Option(18.0, "--max-clip-sec"),
    no_transcribe: bool = typer.Option(False, "--no-transcribe"),
    language: str = typer.Option("en", "--language"),
    chapters_json: Path | None = typer.Option(None, "--chapters-json"),
    max_duration_sec: float = typer.Option(7200.0, "--max-duration-sec"),
) -> None:
    """Normalize, split, score, classify, and transcribe candidate clips."""
    out = job_dir or default_job_dir()
    manifest = prepare_job(
        input_path=input,
        job_dir=out,
        classifier=classifier,
        min_clip_sec=min_clip_sec,
        max_clip_sec=max_clip_sec,
        transcribe=not no_transcribe,
        language=language,
        chapters_json=chapters_json,
        max_duration_sec=max_duration_sec,
    )
    typer.echo(json.dumps(manifest, indent=2))


@app.command()
def review(
    job_dir: Path = typer.Option(..., "--job-dir"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8791, "--port"),
) -> None:
    """Start a lightweight HTTP review API."""
    serve_review(job_dir, host=host, port=port)


@app.command("decide")
def decide(
    job_dir: Path = typer.Option(..., "--job-dir"),
    clip_id: str = typer.Option(..., "--id"),
    decision: str = typer.Option(..., "--decision", help="accept, reject, or maybe"),
) -> None:
    """Record a human review decision for one clip."""
    append_decision(job_dir, clip_id, decision)
    typer.echo(json.dumps({"id": clip_id, "decision": decision}, indent=2))


@app.command()
def export(
    job_dir: Path = typer.Option(..., "--job-dir"),
    out_dir: Path = typer.Option(None, "--out-dir"),
    gender: str | None = typer.Option(None, "--gender", help="male, female, or omit for all"),
    auto_accept_top: int = typer.Option(0, "--auto-accept-top", help="Auto-export top N ranked clips"),
) -> None:
    """Export accepted clips to a TTS-ready dataset with metadata.jsonl."""
    target = out_dir or (job_dir / "voice-dataset")
    summary = export_dataset(
        job_dir=job_dir,
        out_dir=target,
        gender=gender,
        auto_accept_top=auto_accept_top,
    )
    typer.echo(json.dumps(summary, indent=2))


@app.command()
def bundle(
    job_dir: Path = typer.Option(..., "--job-dir"),
    gender: str = typer.Option(..., "--gender"),
    target_sec: float = typer.Option(30.0, "--target-sec"),
    out: Path = typer.Option(None, "--out"),
) -> None:
    """Build one WAV of target duration from ranked clips."""
    output = out or (job_dir / f"{gender}_best_{int(target_sec)}s.wav")
    payload = build_bundle(job_dir=job_dir, out_path=output, gender=gender, target_sec=target_sec)
    typer.echo(json.dumps(payload, indent=2))


if __name__ == "__main__":
    app()
