#!/usr/bin/env python3
"""Train bridge-tag classifier from heuristic labels with hyperparameter sweep.

Uses /classifier-lab pattern: train → evaluate → sweep → select best.

Training data: 166 SFX files with 67-dim feature vectors and heuristic
bridge tag labels from classify_bridge_tags(). The trained model should
reproduce the heuristic mapping but generalize better to new audio.

Multi-label classification: 6 bridge tags, each independent binary.
Uses sklearn MultiOutputClassifier with cross-validation.

Hyperparameter sweep via Optuna:
  - Model type: RF, GradientBoosting, SVC
  - Feature scaling: StandardScaler, MinMaxScaler, None
  - Per-model hyperparameters (n_estimators, max_depth, C, etc.)

Output: joblib bundle with model, scaler, tags, metrics.
"""

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import typer
from loguru import logger

BRIDGE_TAGS = ["Precision", "Resilience", "Fragility", "Corruption", "Loyalty", "Stealth"]
FEATURE_DIM = 67


def load_training_data(path: Path) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Load feature vectors and multi-label targets from training JSON.

    Args:
        path: Path to sfx_training_data.json

    Returns:
        (X, Y, keys) where X is (n, 67) features, Y is (n, 6) binary labels
    """
    data = json.loads(path.read_text())

    X = []
    Y = []
    keys = []
    for item in data:
        fv = item["feature_vector"]
        if len(fv) != FEATURE_DIM:
            logger.warning(f"Skipping {item['key']}: feature dim {len(fv)} != {FEATURE_DIM}")
            continue
        X.append(fv)
        # Multi-label: binary vector for each bridge tag
        tags = set(item.get("bridge_tags", []))
        y = [1 if tag in tags else 0 for tag in BRIDGE_TAGS]
        Y.append(y)
        keys.append(item["key"])

    return np.array(X), np.array(Y), keys


def train_and_evaluate(
    X: np.ndarray,
    Y: np.ndarray,
    model_type: str = "rf",
    scaler_type: str = "standard",
    n_estimators: int = 100,
    max_depth: int = 10,
    C: float = 1.0,
    n_folds: int = 5,
) -> dict[str, Any]:
    """Train multi-label classifier with cross-validation.

    Args:
        X: Feature matrix (n, 67)
        Y: Label matrix (n, 6)
        model_type: 'rf', 'gb', or 'svc'
        scaler_type: 'standard', 'minmax', or 'none'
        n_estimators: For RF/GB
        max_depth: For RF/GB
        C: For SVC
        n_folds: Cross-validation folds

    Returns:
        Dict with metrics, trained model, scaler
    """
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.model_selection import cross_val_predict
    from sklearn.multioutput import MultiOutputClassifier
    from sklearn.preprocessing import MinMaxScaler, StandardScaler
    from sklearn.svm import SVC

    # Scale features
    scaler = None
    if scaler_type == "standard":
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
    elif scaler_type == "minmax":
        scaler = MinMaxScaler()
        X_scaled = scaler.fit_transform(X)
    else:
        X_scaled = X.copy()

    # Build base estimator
    if model_type == "rf":
        base = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        )
    elif model_type == "gb":
        base = GradientBoostingClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            random_state=42,
        )
    elif model_type == "svc":
        base = SVC(C=C, kernel="rbf", probability=True, class_weight="balanced", random_state=42)
    else:
        raise ValueError(f"Unknown model type: {model_type}")

    model = MultiOutputClassifier(base)

    # Cross-validated predictions
    # Filter out labels with too few positive samples for CV
    # (GradientBoosting crashes if a fold gets a single-class column)
    label_pos_counts = Y.sum(axis=0)
    min_viable = max(n_folds, 3)  # Need at least this many positives for CV
    viable_mask = label_pos_counts >= min_viable

    # If some labels are too rare, CV on viable subset only
    Y_viable = Y[:, viable_mask]
    actual_folds = n_folds
    if Y_viable.shape[1] > 0:
        min_pos = int(min(Y_viable.sum(axis=0)))
        min_neg = int(min((1 - Y_viable).sum(axis=0)))
        actual_folds = min(n_folds, min_pos, min_neg)
        actual_folds = max(actual_folds, 2)

    # Build predictions array with zeros for non-viable labels
    Y_pred = np.zeros_like(Y)
    if Y_viable.shape[1] > 0:
        try:
            viable_model = MultiOutputClassifier(base)
            Y_pred_viable = cross_val_predict(viable_model, X_scaled, Y_viable, cv=actual_folds)
            viable_indices = np.where(viable_mask)[0]
            for j, orig_idx in enumerate(viable_indices):
                Y_pred[:, orig_idx] = Y_pred_viable[:, j]
        except ValueError:
            # Last resort: just predict zeros for everything
            pass

    # Per-tag metrics
    from sklearn.metrics import f1_score, precision_score, recall_score

    per_tag = {}
    for i, tag in enumerate(BRIDGE_TAGS):
        y_true = Y[:, i]
        y_pred = Y_pred[:, i]
        n_pos = int(y_true.sum())
        n_pred_pos = int(y_pred.sum())

        if n_pos == 0:
            per_tag[tag] = {"f1": 0.0, "precision": 0.0, "recall": 0.0, "support": 0, "predicted": n_pred_pos}
            continue

        per_tag[tag] = {
            "f1": float(f1_score(y_true, y_pred, zero_division=0)),
            "precision": float(precision_score(y_true, y_pred, zero_division=0)),
            "recall": float(recall_score(y_true, y_pred, zero_division=0)),
            "support": n_pos,
            "predicted": n_pred_pos,
        }

    # Overall metrics (macro and weighted)
    macro_f1 = float(f1_score(Y, Y_pred, average="macro", zero_division=0))
    weighted_f1 = float(f1_score(Y, Y_pred, average="weighted", zero_division=0))
    samples_f1 = float(f1_score(Y, Y_pred, average="samples", zero_division=0))

    # Fit final model on all data
    model.fit(X_scaled, Y)

    return {
        "macro_f1": macro_f1,
        "weighted_f1": weighted_f1,
        "samples_f1": samples_f1,
        "per_tag": per_tag,
        "model": model,
        "scaler": scaler,
        "model_type": model_type,
        "scaler_type": scaler_type,
        "n_folds": actual_folds,
        "params": {
            "model_type": model_type,
            "scaler_type": scaler_type,
            "n_estimators": n_estimators,
            "max_depth": max_depth,
            "C": C,
        },
    }


def run_hyperparameter_sweep(
    X: np.ndarray,
    Y: np.ndarray,
    n_trials: int = 50,
) -> dict[str, Any]:
    """Optuna hyperparameter sweep for bridge tag classifier.

    Args:
        X: Feature matrix
        Y: Label matrix
        n_trials: Number of Optuna trials

    Returns:
        Dict with best params, best metrics, all trial results
    """
    try:
        import optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)
    except ImportError:
        logger.warning("optuna not installed, running grid search fallback")
        return _grid_search_fallback(X, Y)

    results = []

    def objective(trial):
        model_type = trial.suggest_categorical("model_type", ["rf", "gb", "svc"])

        scaler_type = trial.suggest_categorical("scaler_type", ["standard", "minmax", "none"])

        if model_type in ("rf", "gb"):
            n_estimators = trial.suggest_int("n_estimators", 50, 300, step=50)
            max_depth = trial.suggest_int("max_depth", 3, 20)
            C = 1.0
        else:
            n_estimators = 100
            max_depth = 10
            C = trial.suggest_float("C", 0.01, 100.0, log=True)

        result = train_and_evaluate(
            X, Y,
            model_type=model_type,
            scaler_type=scaler_type,
            n_estimators=n_estimators,
            max_depth=max_depth,
            C=C,
        )

        results.append({
            "params": result["params"],
            "macro_f1": result["macro_f1"],
            "weighted_f1": result["weighted_f1"],
            "samples_f1": result["samples_f1"],
        })

        return result["weighted_f1"]

    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    # Train best model
    best = study.best_params
    best_result = train_and_evaluate(
        X, Y,
        model_type=best.get("model_type", "rf"),
        scaler_type=best.get("scaler_type", "standard"),
        n_estimators=best.get("n_estimators", 100),
        max_depth=best.get("max_depth", 10),
        C=best.get("C", 1.0),
    )

    return {
        "best_params": best,
        "best_metrics": {
            "macro_f1": best_result["macro_f1"],
            "weighted_f1": best_result["weighted_f1"],
            "samples_f1": best_result["samples_f1"],
            "per_tag": best_result["per_tag"],
        },
        "best_model": best_result["model"],
        "best_scaler": best_result["scaler"],
        "all_trials": sorted(results, key=lambda r: r["weighted_f1"], reverse=True),
        "n_trials": n_trials,
    }


def _grid_search_fallback(X: np.ndarray, Y: np.ndarray) -> dict[str, Any]:
    """Grid search when Optuna isn't available."""
    configs = [
        {"model_type": "rf", "scaler_type": "standard", "n_estimators": 100, "max_depth": 10, "C": 1.0},
        {"model_type": "rf", "scaler_type": "standard", "n_estimators": 200, "max_depth": 15, "C": 1.0},
        {"model_type": "rf", "scaler_type": "minmax", "n_estimators": 150, "max_depth": 8, "C": 1.0},
        {"model_type": "gb", "scaler_type": "standard", "n_estimators": 100, "max_depth": 5, "C": 1.0},
        {"model_type": "gb", "scaler_type": "standard", "n_estimators": 200, "max_depth": 8, "C": 1.0},
        {"model_type": "svc", "scaler_type": "standard", "n_estimators": 100, "max_depth": 10, "C": 1.0},
        {"model_type": "svc", "scaler_type": "standard", "n_estimators": 100, "max_depth": 10, "C": 10.0},
        {"model_type": "svc", "scaler_type": "minmax", "n_estimators": 100, "max_depth": 10, "C": 0.1},
    ]

    best_result = None
    best_score = -1
    all_results = []

    for cfg in configs:
        result = train_and_evaluate(X, Y, **cfg)
        all_results.append({"params": result["params"], "weighted_f1": result["weighted_f1"]})
        if result["weighted_f1"] > best_score:
            best_score = result["weighted_f1"]
            best_result = result

    return {
        "best_params": best_result["params"],
        "best_metrics": {
            "macro_f1": best_result["macro_f1"],
            "weighted_f1": best_result["weighted_f1"],
            "samples_f1": best_result["samples_f1"],
            "per_tag": best_result["per_tag"],
        },
        "best_model": best_result["model"],
        "best_scaler": best_result["scaler"],
        "all_trials": sorted(all_results, key=lambda r: r["weighted_f1"], reverse=True),
        "n_trials": len(configs),
    }


def save_model(model, scaler, metrics: dict, output_path: Path) -> None:
    """Save trained model as joblib bundle."""
    import joblib

    bundle = {
        "model": model,
        "scaler": scaler,
        "tags": BRIDGE_TAGS,
        "feature_dim": FEATURE_DIM,
        "metrics": metrics,
    }
    joblib.dump(bundle, output_path)
    logger.info(f"Saved model to {output_path}")


def main(
    data: str = typer.Option(Path("data/sfx_training_data.json", help=""),
    output: str = typer.Option(Path("data/bridge_classifier.joblib", help=""),
    n_trials: int = typer.Option(50, help=""),
    no_sweep: bool = typer.Option(False, help="Skip Optuna sweep, use best defaults"),
    json_report: str = typer.Option(None, help=""),
):
    """CLI entry point for training."""

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # Load data
    logger.info(f"Loading training data from {data}")
    X, Y, keys = load_training_data(data)
    logger.info(f"Loaded {X.shape[0]} samples, {X.shape[1]} features, {Y.shape[1]} labels")
    logger.info(f"Label distribution: {dict(zip(BRIDGE_TAGS, Y.sum(axis=0).astype(int).tolist()))}")

    if no_sweep:
        # Train with sensible defaults
        logger.info("Training with default params (no sweep)")
        result = train_and_evaluate(X, Y, model_type="rf", scaler_type="standard", n_estimators=200, max_depth=12)
        metrics = {
            "macro_f1": result["macro_f1"],
            "weighted_f1": result["weighted_f1"],
            "samples_f1": result["samples_f1"],
            "per_tag": result["per_tag"],
        }
        model = result["model"]
        scaler = result["scaler"]
        params = result["params"]
    else:
        # Hyperparameter sweep
        logger.info(f"Running hyperparameter sweep ({n_trials} trials)")
        sweep = run_hyperparameter_sweep(X, Y, n_trials=n_trials)
        metrics = sweep["best_metrics"]
        model = sweep["best_model"]
        scaler = sweep["best_scaler"]
        params = sweep["best_params"]

        logger.info(f"\nTop 5 configurations:")
        for i, trial in enumerate(sweep["all_trials"][:5]):
            logger.info(f"  {i+1}. F1={trial['weighted_f1']:.3f} — {trial['params']}")

    # Report
    logger.info(f"\nBest params: {params}")
    logger.info(f"Weighted F1: {metrics['weighted_f1']:.3f}")
    logger.info(f"Macro F1: {metrics['macro_f1']:.3f}")
    logger.info(f"Samples F1: {metrics['samples_f1']:.3f}")
    logger.info(f"\nPer-tag metrics:")
    for tag in BRIDGE_TAGS:
        tm = metrics["per_tag"].get(tag, {})
        logger.info(
            f"  {tag:12s}: F1={tm.get('f1', 0):.3f}  "
            f"P={tm.get('precision', 0):.3f}  R={tm.get('recall', 0):.3f}  "
            f"support={tm.get('support', 0)}  predicted={tm.get('predicted', 0)}"
        )

    # Save model
    save_model(model, scaler, metrics, output)
    logger.info(f"\nModel saved to {output}")

    # JSON report
    if json_report:
        report = {
            "best_params": params,
            "metrics": metrics,
            "data_size": int(X.shape[0]),
            "feature_dim": int(X.shape[1]),
            "output_path": str(output),
        }
        json_report.write_text(json.dumps(report, indent=2))
        logger.info(f"Report saved to {json_report}")


if __name__ == "__main__":
    main()
