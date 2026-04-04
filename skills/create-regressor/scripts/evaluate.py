"""Evaluation CLI for create-regressor.

Usage:
    python scripts/evaluate.py pdf-duration --test test_data.jsonl
    python scripts/evaluate.py pdf-duration --cv 5
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.storage import load_model

app = typer.Typer(add_completion=False)


@app.command()
def evaluate(
    name: str = typer.Argument(..., help="Model name to evaluate"),
    test_file: Optional[Path] = typer.Option(None, "--test", "-t", help="Test data JSONL/CSV"),
    target: Optional[str] = typer.Option(None, "--target", help="Target column (reads from config if omitted)"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Evaluate a trained model on held-out data."""
    reg = load_model(name)

    if not test_file:
        logger.error("Provide --test file for evaluation")
        raise typer.Exit(1)

    # Try to read target from saved config
    if not target:
        config_path = reg_dir(name) / "config.json"
        if config_path.exists():
            cfg = json.loads(config_path.read_text())
            target = cfg.get("target")
        if not target:
            logger.error("Provide --target column name (not found in saved config)")
            raise typer.Exit(1)

    from lib.data import load_data

    feature_dicts, targets = load_data(test_file, target)
    metrics = reg.evaluate(feature_dicts, targets)

    if output_json:
        print(json.dumps(metrics, indent=2))
    else:
        print(f"\nEvaluation: {name} on {test_file}")
        print(f"  Samples: {metrics['samples']}")
        print(f"  MAE:     {metrics['mae']:.3f}")
        print(f"  RMSE:    {metrics['rmse']:.3f}")
        print(f"  R2:      {metrics['r2']:.4f}")
        print(f"  MAPE:    {metrics['mape']:.3f}")


def reg_dir(name: str) -> Path:
    from lib.storage import MODELS_DIR
    return MODELS_DIR / name


if __name__ == "__main__":
    app()
