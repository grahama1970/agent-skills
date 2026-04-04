"""Bayesian hyperparameter search via Optuna for create-regressor.

Sweeps model-specific hyperparameters using cross-validation MAE as objective.
Persists study to SQLite for resumability.

Usage:
    python scripts/hp_search.py data.jsonl --target score --model gbr --trials 15
    python scripts/hp_search.py data.jsonl --target score --model gbr --resume
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import typer
from loguru import logger
from sklearn.feature_extraction import DictVectorizer
from sklearn.model_selection import cross_val_score

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.data import load_data
from lib.models import MODEL_REGISTRY

app = typer.Typer(add_completion=False)

STUDY_DIR = Path(__file__).resolve().parent.parent / "state" / "hp_studies"


# ---------------------------------------------------------------------------
# Per-model search spaces
# ---------------------------------------------------------------------------

def _suggest_gbr(trial: "optuna.Trial") -> dict:
    return {
        "n_estimators": trial.suggest_int("n_estimators", 100, 500, step=50),
        "max_depth": trial.suggest_int("max_depth", 3, 10),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
        "subsample": trial.suggest_float("subsample", 0.6, 1.0),
        "min_samples_leaf": trial.suggest_int("min_samples_leaf", 1, 20),
        "random_state": 42,
    }


def _suggest_rf(trial: "optuna.Trial") -> dict:
    return {
        "n_estimators": trial.suggest_int("n_estimators", 100, 500, step=50),
        "max_depth": trial.suggest_categorical("max_depth", [None, 5, 10, 15, 20]),
        "min_samples_leaf": trial.suggest_int("min_samples_leaf", 1, 20),
        "max_features": trial.suggest_categorical("max_features", ["sqrt", "log2", None]),
        "random_state": 42,
    }


def _suggest_ridge(trial: "optuna.Trial") -> dict:
    return {
        "alpha": trial.suggest_float("alpha", 0.001, 100.0, log=True),
    }


def _suggest_lasso(trial: "optuna.Trial") -> dict:
    return {
        "alpha": trial.suggest_float("alpha", 0.001, 100.0, log=True),
        "max_iter": 10000,
    }


def _suggest_elasticnet(trial: "optuna.Trial") -> dict:
    return {
        "alpha": trial.suggest_float("alpha", 0.001, 100.0, log=True),
        "l1_ratio": trial.suggest_float("l1_ratio", 0.0, 1.0),
        "max_iter": 10000,
    }


def _suggest_xgb(trial: "optuna.Trial") -> dict:
    return {
        "n_estimators": trial.suggest_int("n_estimators", 100, 500, step=50),
        "max_depth": trial.suggest_int("max_depth", 3, 10),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
        "subsample": trial.suggest_float("subsample", 0.6, 1.0),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
        "random_state": 42,
    }


SEARCH_SPACES = {
    "gbr": _suggest_gbr,
    "rf": _suggest_rf,
    "ridge": _suggest_ridge,
    "lasso": _suggest_lasso,
    "elasticnet": _suggest_elasticnet,
    "xgb": _suggest_xgb,
}


@app.command()
def hp_search(
    input_file: Path = typer.Argument(..., help="Training data file"),
    target: str = typer.Option(..., "--target", "-t", help="Target column"),
    model: str = typer.Option("gbr", "--model", "-m", help="Model type to tune"),
    trials: int = typer.Option(15, "--trials", "-n", help="Number of Optuna trials"),
    cv_folds: int = typer.Option(5, "--cv-folds", help="CV folds for objective"),
    resume: bool = typer.Option(False, "--resume", help="Resume previous study"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
    name: Optional[str] = typer.Option(None, "--name", help="Study name (default: model type)"),
) -> None:
    """Run Bayesian hyperparameter search using Optuna."""
    try:
        import optuna
    except ImportError:
        logger.error("Optuna not installed. Run: pip install optuna")
        raise typer.Exit(1)

    if model not in SEARCH_SPACES:
        logger.error(f"No search space for model '{model}'. Available: {list(SEARCH_SPACES.keys())}")
        raise typer.Exit(1)

    if model not in MODEL_REGISTRY:
        logger.error(f"Model '{model}' not in registry (missing optional dep?)")
        raise typer.Exit(1)

    # Load data
    feature_dicts, targets = load_data(input_file, target)
    vectorizer = DictVectorizer(sparse=False)
    X = vectorizer.fit_transform(feature_dicts)
    y = np.array(targets, dtype=np.float64)

    suggest_fn = SEARCH_SPACES[model]
    model_cls = MODEL_REGISTRY[model]

    # Study storage
    study_name = name or f"regressor_{model}"
    STUDY_DIR.mkdir(parents=True, exist_ok=True)
    storage = f"sqlite:///{STUDY_DIR / study_name}.db"

    def objective(trial: optuna.Trial) -> float:
        params = suggest_fn(trial)
        estimator = model_cls(**params)
        folds = min(cv_folds, len(y))
        scores = cross_val_score(estimator, X, y, cv=folds, scoring="neg_mean_absolute_error")
        return -scores.mean()  # Optuna minimizes

    # Suppress Optuna info logs
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    if resume:
        study = optuna.load_study(study_name=study_name, storage=storage)
        remaining = max(0, trials - len(study.trials))
        logger.info(f"Resuming study '{study_name}': {len(study.trials)} existing trials, {remaining} remaining")
    else:
        study = optuna.create_study(
            study_name=study_name,
            storage=storage,
            direction="minimize",
            load_if_exists=True,
        )
        remaining = trials

    if remaining > 0:
        study.optimize(objective, n_trials=remaining)

    best = study.best_trial
    best_params = best.params
    best_mae = best.value

    # Save best params
    output_path = STUDY_DIR / f"{study_name}_best.json"
    result = {
        "model": model,
        "study_name": study_name,
        "total_trials": len(study.trials),
        "best_trial": best.number,
        "best_mae": round(best_mae, 6),
        "best_params": best_params,
        "storage": str(STUDY_DIR / f"{study_name}.db"),
    }
    output_path.write_text(json.dumps(result, indent=2))

    if output_json:
        print(json.dumps(result, indent=2))
    else:
        print(f"\nHP Search: {model} ({len(study.trials)} trials)")
        print(f"  Best MAE: {best_mae:.6f} (trial #{best.number})")
        print(f"  Best params:")
        for k, v in best_params.items():
            print(f"    {k}: {v}")
        print(f"  Saved to: {output_path}")

    logger.info(f"HP search complete: {model} best_mae={best_mae:.6f}")


if __name__ == "__main__":
    app()
