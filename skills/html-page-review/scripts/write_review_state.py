#!/usr/bin/env python3
"""Write session-level review-state.json.

RECONSTRUCTED 2026-08-12 from the surviving cpython-312 bytecode after the .py
source was lost (never tracked in git). Faithful to the disassembly. Now TRACKED.
"""
from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone

import typer

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command()
def main(
    session_dir: pathlib.Path = typer.Option(..., help="Root session directory"),
    iteration: str = typer.Option(..., help="Current iteration ID"),
    url: str = typer.Option(..., help="Page URL being reviewed"),
    out: pathlib.Path = typer.Option(..., help="Output JSON file path"),
) -> None:
    state = {
        "schema_version": "0.1.0",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "url": url,
        "session_dir": str(session_dir),
        "latest_iteration": iteration,
        "latest_iteration_dir": str(session_dir / "iterations" / iteration),
        "canonical_intent": str(session_dir / "canonical-intent.json"),
        "latest_review_prompt": str(session_dir / "iterations" / iteration / "prompt" / "review-request.md"),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    app()
