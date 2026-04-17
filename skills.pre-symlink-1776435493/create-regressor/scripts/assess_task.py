"""Preflight task assessment with optional /dogpile research.

Analyzes the dataset and recommends model type, HP search trials,
and whether /dogpile research should be triggered.

Usage:
    python scripts/assess_task.py data.jsonl --target duration_seconds
    python scripts/assess_task.py data.jsonl --target price --dogpile-when-uncertain
"""

from __future__ import annotations
import os

import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.data import describe_data, load_data
from lib.memory_integration import recall_prior_regressors

DOGPILE_SKILL = Path(__file__).resolve().parent.parent.parent / "dogpile"

app = typer.Typer(add_completion=False)


def compute_confidence(
    n_samples: int,
    n_features: int,
    n_numeric: int,
    n_categorical: int,
    target_stats: dict,
) -> float:
    """Compute dataset confidence score (0.0-1.0).

    Penalizes:
    - Small datasets (<500 samples)
    - Very high dimensionality (features >> samples)
    - Low target variance (near-constant target)
    - Heavy categorical features (need more data for one-hot)
    """
    score = 1.0

    # Sample size penalty
    if n_samples < 100:
        score -= 0.4
    elif n_samples < 500:
        score -= 0.2
    elif n_samples < 1000:
        score -= 0.1

    # Dimensionality penalty (features/samples ratio)
    if n_features > 0 and n_samples > 0:
        ratio = n_features / n_samples
        if ratio > 0.5:
            score -= 0.3
        elif ratio > 0.2:
            score -= 0.15

    # Target variance penalty
    target_range = target_stats.get("max", 0) - target_stats.get("min", 0)
    target_mean = target_stats.get("mean", 0)
    if target_mean != 0 and target_range / abs(target_mean) < 0.01:
        score -= 0.2  # Near-constant target

    # Categorical feature penalty (need more data for one-hot)
    if n_categorical > 10:
        score -= 0.15
    elif n_categorical > 5:
        score -= 0.05

    return max(0.0, min(1.0, score))


def recommend_model(confidence: float, n_samples: int, n_features: int) -> str:
    """Recommend model type based on dataset characteristics."""
    if n_samples < 100:
        return "ridge"  # Regularization helps with small data
    if n_samples < 500 and n_features > 20:
        return "lasso"  # Feature selection with limited data
    if confidence > 0.8:
        return "auto"  # Enough data to CV properly
    return "gbr"  # Good default for medium datasets


def run_dogpile(task_description: str, model_hint: str) -> Optional[str]:
    """Call /dogpile for research on best regression approach."""
    if not DOGPILE_SKILL.exists():
        logger.warning(f"/dogpile skill not found at {DOGPILE_SKILL}")
        return None

    query = (
        f"best regression model for {task_description}, "
        f"compare {model_hint} vs gradient boosting vs random forest vs XGBoost, "
        f"feature engineering strategies for tabular regression"
    )

    logger.info(f"Calling /dogpile: {query[:80]}...")

    try:
        result = subprocess.run(
            [str(DOGPILE_SKILL / "run.sh"), "search", query, "--no-interactive"],
            capture_output=True, text=True, timeout=300,
            cwd=str(DOGPILE_SKILL),
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode == 0 and result.stdout.strip():
            logger.info("Dogpile research completed")
            return result.stdout.strip()
        else:
            logger.warning(f"Dogpile returned rc={result.returncode}")
            return None

    except subprocess.TimeoutExpired:
        logger.warning("Dogpile timed out (5 min)")
        return None
    except Exception as exc:
        logger.warning(f"Dogpile error: {exc}")
        return None


@app.command()
def assess(
    input_file: Path = typer.Argument(..., help="Data file to assess"),
    target: str = typer.Option(..., "--target", "-t", help="Target column name"),
    dogpile_when_uncertain: bool = typer.Option(
        False, "--dogpile-when-uncertain",
        help="Call /dogpile for research when confidence < threshold",
    ),
    dogpile_threshold: float = typer.Option(
        0.70, "--dogpile-threshold",
        help="Confidence threshold below which /dogpile fires",
    ),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Assess a regression task and recommend approach."""
    # 1. Describe dataset
    info = describe_data(input_file)
    n_samples = info["rows"]
    columns = info["columns"]

    n_numeric = sum(1 for c in columns if c.get("type") == "numeric")
    n_categorical = sum(1 for c in columns if c.get("type") == "categorical")
    n_features = len(columns) - 1  # Exclude target

    # Find target stats
    target_stats = {}
    for c in columns:
        if c["name"] == target:
            target_stats = {k: c[k] for k in ("min", "max", "mean") if k in c}
            break

    if not target_stats:
        logger.warning(f"Target '{target}' not found in schema — loading data to compute stats")
        fd, targets = load_data(input_file, target)
        if targets:
            target_stats = {"min": min(targets), "max": max(targets), "mean": sum(targets) / len(targets)}

    # 2. Compute confidence
    confidence = compute_confidence(n_samples, n_features, n_numeric, n_categorical, target_stats)

    # 3. Recommend model
    recommended_model = recommend_model(confidence, n_samples, n_features)

    # 4. Recall prior runs from /memory
    prior_runs = recall_prior_regressors(input_file.stem)

    # 5. Dogpile research (if uncertain)
    dogpile_result = None
    if dogpile_when_uncertain and confidence < dogpile_threshold:
        task_desc = f"{target} prediction from {n_features} features ({n_numeric} numeric, {n_categorical} categorical), {n_samples} samples"
        dogpile_result = run_dogpile(task_desc, recommended_model)

    # 6. Recommend HP search trials
    if n_samples < 200:
        hp_trials = 10
    elif n_samples < 1000:
        hp_trials = 15
    else:
        hp_trials = 25

    report = {
        "input_file": str(input_file),
        "target": target,
        "samples": n_samples,
        "features": n_features,
        "numeric_features": n_numeric,
        "categorical_features": n_categorical,
        "target_stats": target_stats,
        "confidence": round(confidence, 3),
        "recommended_model": recommended_model,
        "recommended_hp_trials": hp_trials,
        "prior_runs_found": bool(prior_runs),
        "dogpile_fired": bool(dogpile_result),
    }

    if prior_runs:
        report["prior_runs"] = [
            {"problem": it.get("problem", ""), "solution": it.get("solution", "")}
            for it in prior_runs.get("items", [])[:3]
        ]

    if dogpile_result:
        report["dogpile_summary"] = dogpile_result[:2000]

    if output_json:
        print(json.dumps(report, indent=2))
    else:
        print(f"\nAssessment: {input_file}")
        print(f"  Target:      {target}")
        print(f"  Samples:     {n_samples}")
        print(f"  Features:    {n_features} ({n_numeric} numeric, {n_categorical} categorical)")
        if target_stats:
            print(f"  Target range: [{target_stats.get('min', '?'):.4g}, {target_stats.get('max', '?'):.4g}]  mean={target_stats.get('mean', '?'):.4g}")
        print(f"  Confidence:  {confidence:.3f}")
        print(f"  Recommended: model={recommended_model}, hp_trials={hp_trials}")
        if prior_runs:
            print(f"  Prior runs:  {len(prior_runs.get('items', []))} found in /memory")
        if dogpile_result:
            print(f"  Dogpile:     Research completed ({len(dogpile_result)} chars)")
        elif dogpile_when_uncertain and confidence >= dogpile_threshold:
            print(f"  Dogpile:     Not fired (confidence {confidence:.3f} >= {dogpile_threshold})")


if __name__ == "__main__":
    app()
