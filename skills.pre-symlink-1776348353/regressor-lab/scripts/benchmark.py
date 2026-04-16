#!/usr/bin/env python3
"""Benchmark multiple regression architectures against the same dataset."""

import os
import json
import subprocess
import sys
import time
from pathlib import Path

import typer

app = typer.Typer()

SKILL_DIR = Path(__file__).resolve().parent.parent
REGRESSOR_RUN = SKILL_DIR.parent / "create-regressor" / "run.sh"
DEFAULT_MODELS = ["linear", "ridge", "lasso", "gbr", "rf", "xgb"]


@app.command()
def benchmark(
    data: Path = typer.Argument(..., help="Training data JSONL"),
    target: str = typer.Option(..., "--target", help="Target column name"),
    name: str = typer.Option("benchmark", "--name", help="Benchmark name"),
    models: str = typer.Option(
        ",".join(DEFAULT_MODELS),
        "--models",
        help="Comma-separated model types to compare",
    ),
    test_split: float = typer.Option(0.2, "--test-split", help="Holdout fraction"),
):
    """Train and compare multiple regression architectures."""
    model_list = [m.strip() for m in models.split(",")]
    results_dir = SKILL_DIR / "models" / name
    results_dir.mkdir(parents=True, exist_ok=True)

    # Resolve data to absolute path so create-regressor can find it
    data = data.resolve()
    if not data.exists():
        print(f"ERROR: Data file not found: {data}", file=sys.stderr)
        raise typer.Exit(1)

    # Describe dataset
    split_cmd = [str(REGRESSOR_RUN), "describe", str(data)]
    print(f"Describing dataset: {data}")
    subprocess.run(split_cmd, check=False,
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )

    results = []
    for model_type in model_list:
        model_name = f"{name}__{model_type}"
        print(f"\n{'='*60}")
        print(f"Training: {model_type}")
        print(f"{'='*60}")

        t0 = time.time()
        train_cmd = [
            str(REGRESSOR_RUN), "train", str(data),
            "--target", target,
            "--name", model_name,
            "--model", model_type,
        ]

        proc = subprocess.run(train_cmd, capture_output=True, text=True, timeout=600,
        env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
        train_seconds = time.time() - t0

        # Parse metrics from output
        metrics = _parse_metrics(proc.stdout,
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        metrics["model"] = model_type
        metrics["train_seconds"] = round(train_seconds, 2)
        metrics["name"] = model_name

        if proc.returncode != 0:
            metrics["error"] = proc.stderr[-500:] if proc.stderr else "unknown"
            print(f"  FAILED: {metrics.get('error', '')[:100]}")
        else:
            print(f"  MAE={metrics.get('mae', '?')} RMSE={metrics.get('rmse', '?')} R²={metrics.get('r2', '?')}")

        results.append(metrics)

    # Sort by MAE (lower is better)
    valid = [r for r in results if "error" not in r and r.get("mae") is not None]
    valid.sort(key=lambda r: r["mae"])

    winner = valid[0] if valid else None

    report = {
        "name": name,
        "data": str(data),
        "target": target,
        "results": results,
        "winner": winner["model"] if winner else None,
        "winner_metrics": winner if winner else None,
    }

    report_path = results_dir / "benchmark_results.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    # Print leaderboard
    print(f"\n{'='*60}")
    print(f"LEADERBOARD: {name}")
    print(f"{'='*60}")
    print(f"{'Rank':<5} {'Model':<15} {'MAE':<12} {'RMSE':<12} {'R²':<8} {'Time':<8}")
    print("-" * 60)
    for i, r in enumerate(valid, 1):
        print(f"{i:<5} {r['model']:<15} {r.get('mae', '?'):<12} {r.get('rmse', '?'):<12} {r.get('r2', '?'):<8} {r.get('train_seconds', '?'):<8}")

    if winner:
        print(f"\nWinner: {winner['model']} (MAE={winner['mae']})")
    print(f"Report: {report_path}")


def _parse_metrics(stdout: str) -> dict:
    """Parse MAE, RMSE, R², MAPE from create-regressor output."""
    metrics = {}
    for line in stdout.splitlines():
        line_lower = line.lower().strip()
        for key in ("mae", "rmse", "r2", "r²", "mape"):
            if key in line_lower:
                parts = line.split(":")
                if len(parts) >= 2:
                    try:
                        val = float(parts[-1].strip().rstrip("%"))
                        norm_key = "r2" if key == "r²" else key
                        metrics[norm_key] = val
                    except ValueError:
                        pass
        # Also try key=value format
        for key in ("mae=", "rmse=", "r2=", "mape="):
            if key in line_lower:
                try:
                    idx = line_lower.index(key)
                    rest = line[idx + len(key):].split()[0].rstrip(",")
                    metrics[key.rstrip("=")] = float(rest)
                except (ValueError, IndexError):
                    pass
    return metrics


if __name__ == "__main__":
    app()
