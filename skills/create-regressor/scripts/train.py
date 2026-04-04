"""Training CLI for create-regressor.

Usage:
    python scripts/train.py data.jsonl --target duration_seconds --name pdf-duration
    python scripts/train.py data.csv --target price --model ridge --name house-price
    python scripts/train.py data.jsonl --target score --model auto --name quality
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

try:
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path.home() / ".pi" / "skills"))
    from common.task_monitor import TaskClient
except ImportError:
    TaskClient = None

# Ensure lib is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.data import load_data, split_data
from lib.models import MODEL_REGISTRY, Regressor, TrainResult, auto_select
from lib.storage import save_model, store_to_memory

app = typer.Typer(add_completion=False)


@app.command()
def train(
    input_file: Path = typer.Argument(..., help="JSONL, JSON, or CSV data file"),
    target: str = typer.Option(..., "--target", "-t", help="Target column name"),
    name: str = typer.Option(..., "--name", "-n", help="Model name for saving"),
    model: str = typer.Option("auto", "--model", "-m", help="Model type or 'auto'"),
    test_split: float = typer.Option(0.2, "--test-split", help="Fraction for test set"),
    seed: int = typer.Option(42, "--seed", help="Random seed"),
    cv_folds: int = typer.Option(5, "--cv-folds", help="CV folds for auto selection"),
    no_memory: bool = typer.Option(False, "--no-memory", help="Skip /memory storage"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Train a regression model from tabular data."""
    monitor = TaskClient(f"create-regressor/{name}", total=1, description=f"Training regressor {name}") if TaskClient else None

    feature_dicts, targets = load_data(input_file, target)

    train_fd, train_t, test_fd, test_t = split_data(
        feature_dicts, targets, test_ratio=test_split, seed=seed,
    )
    logger.info(f"Split: {len(train_fd)} train, {len(test_fd)} test")

    cv_results: dict = {}

    if model == "auto":
        best_key, cv_results = auto_select(
            train_fd, train_t, cv_folds=cv_folds,
        )
        logger.info(f"Auto-selected: {best_key}")
        selected_by = "auto_cv"
    else:
        if model not in MODEL_REGISTRY:
            logger.error(f"Unknown model: {model}. Available: {list(MODEL_REGISTRY.keys())}")
            raise typer.Exit(1)
        best_key = model
        selected_by = "explicit"

    reg = Regressor(model_type=best_key)
    metrics = reg.train(train_fd, train_t)

    # Evaluate on test set
    if test_fd:
        test_metrics = reg.evaluate(test_fd, test_t)
        logger.info(
            f"Test set: MAE={test_metrics['mae']:.3f}, "
            f"R2={test_metrics['r2']:.4f}, RMSE={test_metrics['rmse']:.3f}"
        )
    else:
        test_metrics = metrics

    config = {
        "input_file": str(input_file),
        "target": target,
        "model_type": best_key,
        "selected_by": selected_by,
        "test_split": test_split,
        "seed": seed,
        "cv_folds": cv_folds,
    }

    model_dir = save_model(reg, name, config=config)

    if not no_memory:
        ok = store_to_memory(name, reg)
        if ok:
            logger.info("Model summary stored to /memory")

    result = TrainResult(
        model_name=name,
        model_type=best_key,
        selected_by=selected_by,
        mae=test_metrics.get("mae", reg.mae),
        rmse=test_metrics.get("rmse", reg.rmse),
        r2=test_metrics.get("r2", reg.r2),
        mape=test_metrics.get("mape", reg.mape),
        training_samples=reg.training_samples,
        feature_count=len(reg.feature_names),
        version=reg.version,
        cv_results=cv_results,
    )

    if monitor:
        monitor.update(item=f"R2={result.r2:.4f} MAE={result.mae:.3f}")
        monitor.finish()

    if output_json:
        print(result.to_json())
    else:
        print(f"\nModel '{name}' trained successfully")
        print(f"  Type:     {best_key} (selected by {selected_by})")
        print(f"  Samples:  {reg.training_samples} train, {len(test_fd)} test")
        print(f"  Features: {len(reg.feature_names)}")
        print(f"  MAE:      {result.mae:.3f}")
        print(f"  RMSE:     {result.rmse:.3f}")
        print(f"  R2:       {result.r2:.4f}")
        print(f"  MAPE:     {result.mape:.3f}")
        print(f"  Saved:    {model_dir}")
        if cv_results:
            print("\n  Cross-validation results:")
            for k, v in cv_results.items():
                print(f"    {k:12s}  MAE={v.get('mae', '?'):>8}  R2={v.get('r2', '?'):>7}")


if __name__ == "__main__":
    app()
