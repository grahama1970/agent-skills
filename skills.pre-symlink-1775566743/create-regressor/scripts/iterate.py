"""Self-improvement iterative training loop for create-regressor.

Combines HP search + iterative training with holdout gate promotion.
Matches the pattern from /create-classifier and /create-gpt.

Flow:
  1. Split data into train/val/holdout
  2. (Optional) Run Optuna HP search on train+val
  3. For each iteration:
     a. Train with best HPs on train set
     b. Evaluate on validation set
     c. Evaluate on holdout set (gate)
     d. If holdout gate passes → promote to best model
     e. Early exit if target metrics met
  4. Learn results to /memory

Usage:
    python scripts/iterate.py data.jsonl --target price --name house-price --model gbr
    python scripts/iterate.py data.jsonl --target score --name quality --model auto --run-hp-search
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.data import load_data
from lib.models import MODEL_REGISTRY, Regressor, auto_select
from lib.storage import MODELS_DIR, save_model
from lib.memory_integration import learn_regressor_run, recall_prior_regressors

app = typer.Typer(add_completion=False)

# Holdout gate thresholds (matches create-classifier pattern)
DEFAULT_R2_THRESHOLD = 0.85
DEFAULT_MAE_RATIO_THRESHOLD = 0.20  # MAE / target_range < 20%


def _three_way_split(
    feature_dicts: list[dict],
    targets: list[float],
    val_ratio: float = 0.15,
    holdout_ratio: float = 0.10,
    seed: int = 42,
) -> tuple:
    """Split into train/val/holdout (default 75/15/10)."""
    import random

    indices = list(range(len(feature_dicts)))
    rng = random.Random(seed)
    rng.shuffle(indices)

    n = len(indices)
    n_holdout = max(1, int(n * holdout_ratio))
    n_val = max(1, int(n * val_ratio))

    holdout_idx = indices[:n_holdout]
    val_idx = indices[n_holdout:n_holdout + n_val]
    train_idx = indices[n_holdout + n_val:]

    def _subset(idx_list):
        return [feature_dicts[i] for i in idx_list], [targets[i] for i in idx_list]

    train_fd, train_t = _subset(train_idx)
    val_fd, val_t = _subset(val_idx)
    holdout_fd, holdout_t = _subset(holdout_idx)

    return train_fd, train_t, val_fd, val_t, holdout_fd, holdout_t


def _run_hp_search(
    input_file: Path,
    target: str,
    model: str,
    trials: int,
) -> Optional[dict]:
    """Run HP search and return best params."""
    try:
        import optuna
    except ImportError:
        logger.warning("Optuna not installed — skipping HP search")
        return None

    from scripts.hp_search import SEARCH_SPACES
    if model not in SEARCH_SPACES:
        logger.info(f"No search space for {model} — using defaults")
        return None

    import subprocess
    cmd = [
        sys.executable, str(Path(__file__).parent / "hp_search.py"),
        str(input_file),
        "--target", target,
        "--model", model,
        "--trials", str(trials),
        "--json",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode == 0:
        data = json.loads(result.stdout)
        return data.get("best_params")
    else:
        logger.warning(f"HP search failed: {result.stderr[:200]}")
        return None


@app.command()
def iterate(
    input_file: Path = typer.Argument(..., help="Training data file"),
    target: str = typer.Option(..., "--target", "-t", help="Target column"),
    name: str = typer.Option(..., "--name", "-n", help="Model name"),
    model: str = typer.Option("auto", "--model", "-m", help="Model type or 'auto'"),
    max_iterations: int = typer.Option(5, "--max-iterations", help="Max training iterations"),
    r2_threshold: float = typer.Option(DEFAULT_R2_THRESHOLD, "--r2-threshold", help="Holdout R2 gate"),
    mae_ratio_threshold: float = typer.Option(
        DEFAULT_MAE_RATIO_THRESHOLD, "--mae-ratio-threshold",
        help="Holdout MAE/range gate (lower=better)",
    ),
    run_hp_search: bool = typer.Option(False, "--run-hp-search", help="Run Optuna HP search first"),
    hp_trials: int = typer.Option(15, "--hp-trials", help="Optuna trials if HP search enabled"),
    seed: int = typer.Option(42, "--seed", help="Random seed"),
    no_memory: bool = typer.Option(False, "--no-memory", help="Skip /memory integration"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Iterative self-improvement training loop with holdout gate."""

    # 0. Recall prior runs
    if not no_memory:
        prior = recall_prior_regressors(name, model)
        if prior:
            logger.info(f"Found {len(prior.get('items', []))} prior run(s) in /memory")

    # 1. Load and split
    feature_dicts, targets = load_data(input_file, target)
    train_fd, train_t, val_fd, val_t, holdout_fd, holdout_t = _three_way_split(
        feature_dicts, targets, seed=seed,
    )
    logger.info(f"Split: {len(train_fd)} train, {len(val_fd)} val, {len(holdout_fd)} holdout")

    target_range = max(targets) - min(targets) if targets else 1.0

    # 2. Auto-select if needed
    cv_results = {}
    if model == "auto":
        best_key, cv_results = auto_select(train_fd, train_t)
        logger.info(f"Auto-selected: {best_key}")
        selected_by = "auto_cv"
    else:
        if model not in MODEL_REGISTRY:
            logger.error(f"Unknown model: {model}")
            raise typer.Exit(1)
        best_key = model
        selected_by = "explicit"

    # 3. HP search (optional)
    best_params = None
    if run_hp_search:
        logger.info(f"Running HP search ({hp_trials} trials)...")
        best_params = _run_hp_search(input_file, target, best_key, hp_trials)
        if best_params:
            logger.info(f"Best HPs: {best_params}")
            selected_by = "hp_search"

    # 4. Iterative training loop
    best_model: Optional[Regressor] = None
    best_holdout_r2 = -float("inf")
    best_iteration = 0
    iteration_results = []

    for iteration in range(1, max_iterations + 1):
        logger.info(f"\n--- Iteration {iteration}/{max_iterations} ---")

        # Build model with optional HP params
        kwargs = best_params or {}
        # Vary seed per iteration for diversity
        if "random_state" in kwargs:
            kwargs = {**kwargs, "random_state": seed + iteration}

        reg = Regressor(model_type=best_key, **kwargs)
        reg.train(train_fd, train_t)

        # Evaluate on validation
        val_metrics = reg.evaluate(val_fd, val_t)
        logger.info(
            f"  Val:     MAE={val_metrics['mae']:.4f}  R2={val_metrics['r2']:.4f}  "
            f"RMSE={val_metrics['rmse']:.4f}"
        )

        # Evaluate on holdout (the gate)
        holdout_metrics = reg.evaluate(holdout_fd, holdout_t)
        holdout_r2 = holdout_metrics["r2"]
        holdout_mae_ratio = holdout_metrics["mae"] / target_range if target_range > 0 else 1.0

        logger.info(
            f"  Holdout: MAE={holdout_metrics['mae']:.4f}  R2={holdout_r2:.4f}  "
            f"MAE/range={holdout_mae_ratio:.4f}"
        )

        iter_result = {
            "iteration": iteration,
            "model_type": best_key,
            "val": val_metrics,
            "holdout": holdout_metrics,
            "holdout_mae_ratio": round(holdout_mae_ratio, 6),
            "promoted": False,
        }

        # Holdout gate check
        gate_pass = holdout_r2 >= r2_threshold and holdout_mae_ratio <= mae_ratio_threshold

        if gate_pass and holdout_r2 > best_holdout_r2:
            best_model = reg
            best_holdout_r2 = holdout_r2
            best_iteration = iteration
            iter_result["promoted"] = True
            logger.info(f"  PROMOTED (holdout R2={holdout_r2:.4f} >= {r2_threshold})")
        elif gate_pass:
            logger.info(f"  Gate passed but not better than iteration {best_iteration}")
        else:
            reasons = []
            if holdout_r2 < r2_threshold:
                reasons.append(f"R2={holdout_r2:.4f} < {r2_threshold}")
            if holdout_mae_ratio > mae_ratio_threshold:
                reasons.append(f"MAE/range={holdout_mae_ratio:.4f} > {mae_ratio_threshold}")
            logger.info(f"  Gate FAILED: {', '.join(reasons)}")

        iteration_results.append(iter_result)

        # Early exit if we're well above threshold
        if gate_pass and holdout_r2 >= r2_threshold + 0.05:
            logger.info(f"  Early exit: holdout R2 well above threshold")
            break

    # 5. Save best model
    if best_model is None:
        logger.warning("No iteration passed holdout gate. Saving last model anyway.")
        best_model = reg
        best_iteration = max_iterations

    config = {
        "input_file": str(input_file),
        "target": target,
        "model_type": best_key,
        "selected_by": selected_by,
        "iterations_run": len(iteration_results),
        "best_iteration": best_iteration,
        "holdout_gate": {"r2_threshold": r2_threshold, "mae_ratio_threshold": mae_ratio_threshold},
        "hp_search": bool(best_params),
        "hp_trials": hp_trials if run_hp_search else 0,
        "seed": seed,
    }
    if best_params:
        config["best_params"] = best_params

    model_dir = save_model(best_model, name, config=config)

    # 6. Learn to /memory
    if not no_memory:
        holdout_metrics = best_model.evaluate(holdout_fd, holdout_t)
        learn_regressor_run(
            model_name=name,
            model_type=best_key,
            metrics=holdout_metrics,
            training_samples=best_model.training_samples,
            feature_count=len(best_model.feature_names),
            selected_by=selected_by,
            cv_results=cv_results or None,
            hp_search_trials=hp_trials if run_hp_search else None,
            iteration=best_iteration,
        )

    # 7. Output
    summary = {
        "model_name": name,
        "model_type": best_key,
        "selected_by": selected_by,
        "best_iteration": best_iteration,
        "total_iterations": len(iteration_results),
        "holdout_r2": round(best_holdout_r2, 6),
        "holdout_gate_passed": best_holdout_r2 >= r2_threshold,
        "iterations": iteration_results,
        "hp_search": bool(best_params),
        "model_path": str(model_dir),
    }

    if output_json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"\nIterative training complete: {name}")
        print(f"  Model:          {best_key} (selected by {selected_by})")
        print(f"  Best iteration: {best_iteration}/{len(iteration_results)}")
        print(f"  Holdout R2:     {best_holdout_r2:.4f} (gate: {r2_threshold})")
        gate_str = "PASSED" if best_holdout_r2 >= r2_threshold else "FAILED"
        print(f"  Holdout gate:   {gate_str}")
        if best_params:
            print(f"  HP search:      {hp_trials} trials")
        print(f"  Saved:          {model_dir}")


if __name__ == "__main__":
    app()
