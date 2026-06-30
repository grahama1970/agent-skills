#!/usr/bin/env python3
"""Ingest SPARTA — thin skill wrapper around the real pipeline.

The real pipeline: ~/workspace/experiments/sparta/src/sparta/pipeline/
  - 48 numbered steps (00-61) + QRA modules + helpers = 27K+ LOC
  - DuckDB read-only via SpartaDataBridge, ArangoDB primary store
  - 486 tests

This skill is an INTERFACE. It dispatches to the real pipeline steps.
It does NOT reimplement any pipeline logic.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import typer
from loguru import logger

SPARTA_ROOT = Path(os.environ.get("SPARTA_ROOT", "${HOME}/workspace/experiments/sparta"))
PIPELINE_STEPS = SPARTA_ROOT / "src" / "sparta" / "pipeline" / "steps"

app = typer.Typer(help="SPARTA ingestion pipeline — thin wrapper around real pipeline.")


# ---------------------------------------------------------------------------
# Core: run a pipeline step
# ---------------------------------------------------------------------------

@app.command()
def step(
    step_number: str = typer.Argument(..., help="Step number (e.g. '03', '12', '05d')"),
    run_id: str = typer.Option("", "--run-id", help="Run ID for data directory"),
    limit: int = typer.Option(0, "--limit", help="Limit items processed"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show plan without executing"),
    extra_args: list[str] = typer.Argument(None, help="Extra args passed to the step"),
):
    """Run a specific pipeline step by number.

    Examples:
        ./run.sh step 03 --run-id myrun --limit 100
        ./run.sh step 12 --run-id myrun
        ./run.sh step 05d --run-id myrun
    """
    # Find the step file
    matches = sorted(PIPELINE_STEPS.glob(f"{step_number}*.py"))
    # Filter out helper files (prefixed with _)
    matches = [m for m in matches if not m.name.startswith("_")]

    if not matches:
        logger.error("No step found matching '{}' in {}", step_number, PIPELINE_STEPS)
        available = sorted(f.stem for f in PIPELINE_STEPS.glob("[0-9]*.py"))
        logger.info("Available steps: {}", ", ".join(available[:20]))
        raise typer.Exit(1)

    if len(matches) > 1:
        logger.warning("Multiple matches for '{}': {}", step_number, [m.name for m in matches])

    step_file = matches[0]
    module_name = f"sparta.pipeline.steps.{step_file.stem}"

    cmd = [sys.executable, "-m", module_name]
    if run_id:
        cmd.extend(["--run-id", run_id])
    if limit > 0:
        cmd.extend(["--limit", str(limit)])
    if dry_run:
        cmd.append("--dry-run")
    if extra_args:
        cmd.extend(extra_args)

    logger.info("Running: {}", " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(SPARTA_ROOT),
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )
    raise typer.Exit(result.returncode)


# ---------------------------------------------------------------------------
# List available steps
# ---------------------------------------------------------------------------

@app.command()
def steps():
    """List all available pipeline steps."""
    step_files = sorted(PIPELINE_STEPS.glob("[0-9]*.py"))
    typer.echo(f"Pipeline steps ({len(step_files)} files):\n")
    for f in step_files:
        # Read first docstring line
        doc = ""
        try:
            with open(f) as fh:
                for line in fh:
                    if line.startswith('"""') or line.startswith("'''"):
                        doc = line.strip().strip('"').strip("'")
                        break
        except Exception:
            pass
        typer.echo(f"  {f.stem:<45} {doc[:60]}")


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

@app.command()
def status():
    """Show pipeline and data health."""
    typer.echo("=== SPARTA Pipeline Status ===\n")

    # Project location
    typer.echo(f"  Project:    {SPARTA_ROOT}")
    typer.echo(f"  Pipeline:   {PIPELINE_STEPS}")
    typer.echo(f"  Steps:      {len(list(PIPELINE_STEPS.glob('[0-9]*.py')))} files")

    # Check for run directories
    runs_dir = SPARTA_ROOT / "data" / "runs"
    if runs_dir.exists():
        runs = sorted(runs_dir.iterdir())
        typer.echo(f"  Runs:       {len(runs)} ({runs[-1].name if runs else 'none'})")
    else:
        typer.echo("  Runs:       no data/runs/ directory")

    # Check DuckDB — find latest run dynamically
    if runs_dir.exists():
        dbs = sorted(runs_dir.glob("*/sparta.duckdb"), key=lambda p: p.stat().st_mtime, reverse=True)
        if dbs:
            size_mb = dbs[0].stat().st_size / (1024 * 1024)
            typer.echo(f"  DuckDB:     {dbs[0].parent.name}/{dbs[0].name} ({size_mb:.0f} MB)")
        else:
            typer.echo("  DuckDB:     not found in any run")
    else:
        typer.echo("  DuckDB:     no data/runs/ directory")

    # Check venv
    venv = SPARTA_ROOT / ".venv"
    typer.echo(f"  Venv:       {'ok' if venv.exists() else 'MISSING'}")

    typer.echo()


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

@app.command()
def test(
    verbose: bool = typer.Option(False, "-v", "--verbose"),
    pattern: str = typer.Option("", "-k", help="Test name pattern filter"),
):
    """Run pipeline tests."""
    cmd = [sys.executable, "-m", "pytest", "tests/", "-q"]
    if verbose:
        cmd.append("-v")
    if pattern:
        cmd.extend(["-k", pattern])

    logger.info("Running: {}", " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(SPARTA_ROOT),
                            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"})
    raise typer.Exit(result.returncode)


# ---------------------------------------------------------------------------
# Explorer UX (launches ux-lab with SPARTA components)
# ---------------------------------------------------------------------------

@app.command()
def explorer(
    no_browser: bool = typer.Option(False, "--no-browser", help="Don't auto-open browser"),
):
    """Launch SPARTA Explorer UX via ux-lab dev server."""
    ux_lab = Path.home() / "workspace" / "experiments" / "pi-mono" / "packages" / "ux-lab"
    if not (ux_lab / "package.json").exists():
        logger.error("ux-lab not found at {}", ux_lab)
        raise typer.Exit(1)

    logger.info("Starting SPARTA Explorer at http://localhost:3002")
    logger.info("  Frontend: Vite on :3002")
    logger.info("  API proxy: Express on :3001 → memory daemon")

    if not no_browser:
        # Open browser after a short delay to let Vite start
        subprocess.Popen(
            ["bash", "-c", "sleep 2 && xdg-open http://localhost:3002 2>/dev/null &"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    result = subprocess.run(["npm", "run", "dev"], cwd=str(ux_lab),
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )
    raise typer.Exit(result.returncode)


# ---------------------------------------------------------------------------
# Data Integrity Audit (post-ingestion gate)
# ---------------------------------------------------------------------------

MEMORY_ROOT = Path(os.environ.get(
    "MEMORY_ROOT", "${HOME}/workspace/experiments/memory"
))

@app.command()
def audit(
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Run SPARTA data integrity audit — gate before Explorer Chat.

    Checks: collections, embeddings, dimensions, mind tags, views,
    BM25, dense/semantic, graph traversal, QRA integrity, cross-framework
    chains, scoring, framework naming, entity corpus.
    """
    cmd = [
        str(MEMORY_ROOT / ".venv" / "bin" / "python"),
        "-m", "graph_memory.maintenance.sparta_audit",
    ]
    if output_json:
        cmd.append("--json")

    logger.info("Running SPARTA data integrity audit...")
    result = subprocess.run(cmd, cwd=str(MEMORY_ROOT),
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )
    if result.returncode != 0:
        logger.error("Data integrity audit FAILED — fix issues before using Explorer Chat")
    raise typer.Exit(result.returncode)


if __name__ == "__main__":
    app()
