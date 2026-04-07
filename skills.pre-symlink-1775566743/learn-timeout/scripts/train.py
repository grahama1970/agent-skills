"""Train duration and risk models from collected training data."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.features import TaskFeatures, features_to_dict
from lib.models import DurationModel, RiskModel
from lib.storage import save_models, store_to_memory

app = typer.Typer(add_completion=False)

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "training_data.jsonl"


def _load_training_data(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


@app.command()
def main(
    data_path: Path = typer.Option(DATA_PATH, help="Path to training_data.jsonl"),
    classifier_lab_benchmark: bool = typer.Option(
        False, "--classifier-lab-benchmark",
        help="Run classifier-lab backbone comparison after training",
    ),
    store_memory: bool = typer.Option(True, help="Store model summary in /memory"),
) -> None:
    """Train both duration and risk models."""
    if not data_path.exists():
        logger.error(f"Training data not found: {data_path}")
        logger.info("Run './run.sh collect' first to gather training data.")
        raise typer.Exit(1)

    rows = _load_training_data(data_path)
    if len(rows) < 10:
        logger.error(f"Only {len(rows)} samples — need at least 10 for training.")
        raise typer.Exit(1)

    logger.info(f"Loaded {len(rows)} training samples")

    # Build feature dicts and labels
    feature_dicts: list[dict] = []
    durations: list[float] = []
    timed_out: list[bool] = []

    for row in rows:
        feat = TaskFeatures(
            task_type=row.get("task_type", "pdf_extraction"),
            page_count=row.get("page_count", 0),
            file_size_mb=row.get("file_size_mb", 0.0),
            table_pages=row.get("table_pages", 0),
            estimated_table_count=row.get("estimated_table_count", 0),
            image_pages=row.get("image_pages", 0),
            has_tables=row.get("has_tables", False),
            has_figures=row.get("has_figures", False),
            has_formulas=row.get("has_formulas", False),
            has_requirements=row.get("has_requirements", False),
            estimated_sections=row.get("estimated_sections", 0),
            domain=row.get("domain", "general"),
            source=row.get("source", "unknown"),
            layout_columns=row.get("layout_columns", 1),
            max_tables_per_page=row.get("max_tables_per_page", 0),
            prompt_tokens=row.get("prompt_tokens", 0),
        )
        feature_dicts.append(features_to_dict(feat))
        durations.append(row["actual_duration_s"])
        timed_out.append(row.get("timed_out", False))

    # --- Train duration model ---
    logger.info("Training duration model (GradientBoostingRegressor)...")
    dur_model = DurationModel()
    dur_metrics = dur_model.train(feature_dicts, durations)

    print(f"\nDuration Model Results:")
    print(f"  Samples:  {dur_metrics['samples']}")
    print(f"  MAE:      {dur_metrics['mae']:.1f}s")
    print(f"  R²:       {dur_metrics['r2']:.3f}")
    print(f"  Features: {dur_metrics['feature_count']}")

    # Top feature importances
    imp = dur_model.feature_importance()
    print(f"\n  Top Features:")
    for name, score in list(imp.items())[:10]:
        print(f"    {name}: {score:.4f}")

    # --- Train risk model ---
    logger.info("Training risk model (LogisticRegression)...")
    risk_model = RiskModel()
    risk_metrics = risk_model.train(feature_dicts, timed_out)

    if risk_metrics:
        print(f"\nRisk Model Results:")
        print(f"  Samples:   {risk_metrics['samples']}")
        print(f"  Positives: {risk_metrics['positives']}")
        print(f"  ROC-AUC:   {risk_metrics['roc_auc']:.3f}")
    else:
        print(f"\nRisk Model: skipped (insufficient timeout events)")

    # --- Save ---
    out_dir = save_models(dur_model, risk_model if risk_model.available else None)
    print(f"\nModels saved to: {out_dir}")

    # --- Store to /memory ---
    if store_memory:
        ok = store_to_memory(dur_model, risk_model if risk_model.available else None)
        if ok:
            print("Model summary stored to /memory")
        else:
            print("Warning: could not store to /memory (service may be offline)")

    # --- Optional classifier-lab benchmark ---
    if classifier_lab_benchmark:
        _run_classifier_lab_benchmark(rows)


def _run_classifier_lab_benchmark(rows: list[dict]) -> None:
    """Generate labels and run classifier-lab for visual complexity classification."""
    skill_dir = Path(__file__).resolve().parent.parent
    pi_dir = skill_dir.parent.parent.parent  # pi-mono root
    classifier_lab = pi_dir / ".pi" / "skills" / "classifier-lab"

    if not (classifier_lab / "run.sh").exists():
        logger.warning("classifier-lab not found, skipping benchmark")
        return

    # Generate risk labels from training data
    labels_path = skill_dir / "data" / "benchmark_labels.jsonl"
    with open(labels_path, "w") as f:
        for row in rows:
            dur = row.get("actual_duration_s", 0)
            if dur < 60:
                label = "low"
            elif dur < 300:
                label = "medium"
            else:
                label = "high"
            f.write(json.dumps({"label": label, "duration_s": dur}) + "\n")

    logger.info(f"Generated {len(rows)} benchmark labels at {labels_path}")
    logger.info("Run classifier-lab benchmark manually:")
    print(f"\n  cd {classifier_lab}")
    print(f"  ./run.sh benchmark \\")
    print(f"    --labels-jsonl {labels_path} \\")
    print(f"    --backbones 'efficientnet_b0,convnextv2_nano,mobilenetv3_large_100' \\")
    print(f"    --epochs 1 --max-steps 60 \\")
    print(f"    --store-memory --require-memory-store \\")
    print(f"    --memory-scope learn_timeout")


if __name__ == "__main__":
    app()
