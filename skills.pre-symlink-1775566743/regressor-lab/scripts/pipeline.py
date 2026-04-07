#!/usr/bin/env python3
"""End-to-end pipeline: collect → benchmark → tune → deploy."""

import os
import subprocess
import sys
from pathlib import Path

import typer

app = typer.Typer()

SKILL_DIR = Path(__file__).resolve().parent.parent
REGRESSOR_RUN = SKILL_DIR.parent / "create-regressor" / "run.sh"


@app.command()
def pipeline(
    data: Path = typer.Argument(None, help="Training data JSONL (skip collect if provided)"),
    target: str = typer.Option("duration_ms", "--target", help="Target column"),
    name: str = typer.Option("timeout-estimator", "--name", help="Model name"),
    models: str = typer.Option("linear,ridge,gbr,rf,xgb", "--models"),
    tune_trials: int = typer.Option(30, "--tune-trials", help="HP search trials for winner"),
    skip_collect: bool = typer.Option(False, "--skip-collect"),
    skip_tune: bool = typer.Option(False, "--skip-tune"),
):
    """Full pipeline: collect → benchmark → tune winner."""
    # Step 1: Collect data if not provided
    if data is None and not skip_collect:
        data = SKILL_DIR / "data" / "timeout_training.jsonl"
        print("Step 1/3: Collecting training data from extraction profiles...")
        subprocess.run(
            [sys.executable, str(SKILL_DIR / "scripts" / "collect.py"), "--out", str(data)],
            check=True,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
    elif data is None:
        data = SKILL_DIR / "data" / "timeout_training.jsonl"

    if not data.exists():
        print(f"ERROR: Data file not found: {data}", file=sys.stderr)
        raise typer.Exit(1)

    # Step 2: Benchmark
    print(f"\nStep 2/3: Benchmarking {models} on {data}...")
    subprocess.run(
        [
            sys.executable, str(SKILL_DIR / "scripts" / "benchmark.py"),
            str(data), "--target", target, "--name", name, "--models", models,
        ],
        check=True,
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )

    # Step 3: Tune winner
    if not skip_tune:
        print(f"\nStep 3/3: Tuning winner with {tune_trials} trials...")
        import json
        results_path = SKILL_DIR / "models" / name / "benchmark_results.json"
        if results_path.exists():
            with open(results_path) as f:
                results = json.load(f)
            winner = results.get("winner")
            if winner:
                winner_name = f"{name}__{winner}"
                subprocess.run(
                    [
                        str(REGRESSOR_RUN), "hp-search", str(data),
                        "--target", target, "--model", winner,
                        "--trials", str(tune_trials),
                    ],
                    check=False,
                    env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
                )
            else:
                print("No winner found, skipping tune")
        else:
            print("No benchmark results found, skipping tune")

    print(f"\nPipeline complete: {name}")
    print(f"Models: {SKILL_DIR / 'models' / name}")


if __name__ == "__main__":
    app()
