#!/usr/bin/env python3
"""Train bridge-tag text classifier from ArangoDB lessons.

Distills keyword-based bridge tags into a lightweight ML classifier that
uses text embeddings as features. The ML model can generalize beyond
exact keyword matches to semantically similar content.

Training pipeline:
  1. Fetch lessons with bridge_attributes from ArangoDB
  2. Embed text (problem + solution) via embedding service
  3. Train multi-label classifier (embedding → 6 bridge logits)
  4. Optuna hyperparameter sweep
  5. Save model for inference in taxonomy sweep --mode classifier

Usage:
    python train_bridge_text_classifier.py --db memory --limit 3000 --n-trials 50
    python train_bridge_text_classifier.py --db memory --no-sweep  # quick train
"""

import os
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

import typer

import httpx
import numpy as np
from loguru import logger

# Removed: memory accessed via httpx to Unix socket (see _memory_cmd)
def _memory_cmd(args: list, timeout: int = 60) -> dict:
    """Call embry-memory daemon via Unix socket HTTP API."""
    str_args = [str(a) for a in args]
    subcmd = str_args[0] if str_args else ""
    rest = str_args[1:]

    # Parse CLI-style flags into a dict
    params: dict = {}
    list_keys: dict[str, list] = {}
    i = 0
    while i < len(rest):
        if rest[i].startswith("--"):
            key = rest[i][2:].replace("-", "_")
            if i + 1 < len(rest) and not rest[i + 1].startswith("--"):
                val = rest[i + 1]
                if key in ("tag", "tags", "collections"):
                    list_keys.setdefault(key, []).append(val)
                else:
                    params[key] = val
                i += 2
            else:
                params[key] = True
                i += 1
        else:
            i += 1
    for k, v in list_keys.items():
        params[k] = v

    transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
    with httpx.Client(transport=transport, base_url="http://localhost", timeout=float(timeout)) as client:
        if subcmd == "recall":
            body = {"q": params.get("q", params.get("query", "")), "k": int(params.get("k", params.get("limit", 5)))}
            for opt in ("scope", "threshold"):
                if opt in params:
                    body[opt] = float(params[opt]) if opt == "threshold" else params[opt]
            if "collections" in params:
                c = params["collections"]
                body["collections"] = c if isinstance(c, list) else [c]
            if "tags" in params:
                t = params["tags"]
                body["tags"] = t if isinstance(t, list) else [t]
            resp = client.post("/recall", json=body)
        elif subcmd == "learn":
            body = {"problem": params.get("problem", ""), "solution": params.get("solution", "")}
            if "scope" in params:
                body["scope"] = params["scope"]
            if "collection" in params:
                body["scope"] = params["collection"]
            if "tag" in params:
                body["tags"] = params["tag"] if isinstance(params["tag"], list) else [params["tag"]]
            if "tags" in params:
                body["tags"] = params["tags"] if isinstance(params["tags"], list) else [params["tags"]]
            if "json" in params:
                body.update(json.loads(params["json"]))
            resp = client.post("/learn", json=body)
        elif subcmd == "count":
            coll = params.get("collection", params.get("scope", "lessons"))
            resp = client.post("/query", json={"aql": f"RETURN LENGTH({coll})", "bind_vars": {}})
        elif subcmd == "sample":
            body = {"collection": params.get("collection", "lessons"), "limit": int(params.get("limit", 10))}
            if "fields" in params:
                body["return_fields"] = [f.strip() for f in str(params["fields"]).split(",")]
            resp = client.post("/list", json=body)
        elif subcmd == "tag":
            if "doc" in params:
                doc = json.loads(params["doc"]) if isinstance(params["doc"], str) else params["doc"]
                resp = client.post("/upsert", json={"collection": params.get("collection", "lessons"), "documents": [doc]})
            elif "key" in params:
                tags_val = params.get("tags", "[]")
                tags_list = json.loads(tags_val) if isinstance(tags_val, str) else tags_val
                field = params.get("field", "tags")
                resp = client.post("/upsert", json={"collection": params.get("collection", "lessons"), "documents": [{"_key": params["key"], field: tags_list}]})
            else:
                raise RuntimeError(f"Unsupported tag args: {rest}")
        elif subcmd == "search":
            body = {"q": params.get("q", params.get("query", "")), "k": int(params.get("limit", 10))}
            if "collection" in params:
                body["collections"] = [params["collection"]]
            if "scope" in params:
                body["scope"] = params["scope"]
            resp = client.post("/recall", json=body)
        else:
            raise RuntimeError(f"Unsupported memory subcommand via httpx: {subcmd}")
        resp.raise_for_status()
        return resp.json()

BRIDGE_TAGS = ["Precision", "Resilience", "Fragility", "Corruption", "Loyalty", "Stealth"]
EMBEDDING_URL = "http://127.0.0.1:8602"


def _set_embedding_url(url: str) -> None:
    global EMBEDDING_URL
    EMBEDDING_URL = url


def fetch_labeled_lessons(limit: int = 3000) -> list[dict]:
    """Fetch lessons with bridge_attributes via /memory sample.

    Args:
        limit: Max lessons to fetch

    Returns:
        List of dicts with lesson fields including bridge_attributes
    """
    results = _memory_cmd([
        "sample", "--collection", "lessons",
        "--limit", str(limit),
        "--filter", "bridge_attributes!=null",
    ], timeout=120)
    logger.info(f"Fetched {len(results)} labeled lessons via /memory")
    return results


def embed_texts(texts: list[str], batch_size: int = 64) -> np.ndarray:
    """Embed texts via the embedding service.

    Args:
        texts: List of text strings
        batch_size: Texts per batch request

    Returns:
        numpy array of shape (n, embedding_dim)
    """
    all_vectors = []
    client = httpx.Client(timeout=60.0)

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        try:
            resp = client.post(f"{EMBEDDING_URL}/embed/batch", json={"texts": batch})
            resp.raise_for_status()
            vectors = resp.json()["vectors"]
            all_vectors.extend(vectors)
        except Exception as e:
            logger.warning(f"Embedding batch {i}-{i+len(batch)} failed: {e}")
            # Return zero vectors for failed batch
            dim = all_vectors[0] if all_vectors else [0.0] * 384
            all_vectors.extend([[0.0] * len(dim)] * len(batch))

        if (i + batch_size) % 500 == 0:
            logger.info(f"  Embedded {min(i + batch_size, len(texts))}/{len(texts)}")

    client.close()
    return np.array(all_vectors)


def prepare_data(lessons: list[dict]) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Prepare training data from lessons.

    Concatenates problem + solution as text, converts bridge_attributes to
    multi-label binary matrix.

    Args:
        lessons: List from fetch_labeled_lessons()

    Returns:
        (X_embeddings, Y_labels, keys)
    """
    texts = []
    labels = []
    keys = []

    for lesson in lessons:
        problem = lesson.get("problem", "") or ""
        solution = lesson.get("solution", "") or ""
        text = f"{problem}\n{solution}".strip()
        if not text:
            continue

        bridge_attrs = set(lesson.get("bridge_attributes", []))
        y = [1 if tag in bridge_attrs else 0 for tag in BRIDGE_TAGS]
        texts.append(text)
        labels.append(y)
        keys.append(lesson.get("key", ""))

    logger.info(f"Prepared {len(texts)} samples from {len(lessons)} lessons")

    # Embed texts
    logger.info("Embedding texts...")
    t0 = time.time()
    X = embed_texts(texts)
    elapsed = time.time() - t0
    logger.info(f"Embedded {len(texts)} texts in {elapsed:.1f}s ({len(texts)/elapsed:.0f} texts/s)")

    Y = np.array(labels)
    return X, Y, keys


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

    Same pattern as sfx-catalog training.
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

    # Handle rare labels (same as sfx-catalog training)
    label_pos_counts = Y.sum(axis=0)
    min_viable = max(n_folds, 3)
    viable_mask = label_pos_counts >= min_viable

    Y_viable = Y[:, viable_mask]
    actual_folds = n_folds
    if Y_viable.shape[1] > 0:
        min_pos = int(min(Y_viable.sum(axis=0)))
        min_neg = int(min((1 - Y_viable).sum(axis=0)))
        actual_folds = min(n_folds, min_pos, min_neg)
        actual_folds = max(actual_folds, 2)

    Y_pred = np.zeros_like(Y)
    if Y_viable.shape[1] > 0:
        try:
            viable_model = MultiOutputClassifier(base)
            Y_pred_viable = cross_val_predict(viable_model, X_scaled, Y_viable, cv=actual_folds)
            viable_indices = np.where(viable_mask)[0]
            for j, orig_idx in enumerate(viable_indices):
                Y_pred[:, orig_idx] = Y_pred_viable[:, j]
        except ValueError as e:
            logger.warning(f"CV failed: {e}")

    # Per-tag metrics
    from sklearn.metrics import f1_score, precision_score, recall_score

    per_tag = {}
    for i, tag in enumerate(BRIDGE_TAGS):
        y_true = Y[:, i]
        y_pred = Y_pred[:, i]
        n_pos = int(y_true.sum())

        if n_pos == 0:
            per_tag[tag] = {"f1": 0.0, "precision": 0.0, "recall": 0.0, "support": 0}
            continue

        per_tag[tag] = {
            "f1": float(f1_score(y_true, y_pred, zero_division=0)),
            "precision": float(precision_score(y_true, y_pred, zero_division=0)),
            "recall": float(recall_score(y_true, y_pred, zero_division=0)),
            "support": n_pos,
        }

    macro_f1 = float(f1_score(Y, Y_pred, average="macro", zero_division=0))
    weighted_f1 = float(f1_score(Y, Y_pred, average="weighted", zero_division=0))

    # Fit final model on all data
    model.fit(X_scaled, Y)

    return {
        "macro_f1": macro_f1,
        "weighted_f1": weighted_f1,
        "per_tag": per_tag,
        "model": model,
        "scaler": scaler,
        "params": {
            "model_type": model_type,
            "scaler_type": scaler_type,
            "n_estimators": n_estimators,
            "max_depth": max_depth,
            "C": C,
        },
    }


def run_sweep(X: np.ndarray, Y: np.ndarray, n_trials: int = 50,
              model_types: list[str] | None = None) -> dict[str, Any]:
    """Optuna hyperparameter sweep."""
    if model_types is None:
        model_types = ["rf", "gb", "svc"]

    try:
        import optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)
    except ImportError:
        logger.warning("optuna not installed, using grid search")
        return _grid_search(X, Y)

    results = []

    def objective(trial):
        model_type = trial.suggest_categorical("model_type", model_types)
        scaler_type = trial.suggest_categorical("scaler_type", ["standard", "minmax", "none"])

        if model_type == "rf":
            n_estimators = trial.suggest_int("n_estimators", 50, 300, step=50)
            max_depth = trial.suggest_int("max_depth", 3, 20)
            C = 1.0
        elif model_type == "gb":
            n_estimators = trial.suggest_int("n_estimators", 50, 300, step=50)
            max_depth = trial.suggest_int("max_depth", 3, 8)  # GB is single-threaded; cap depth
            C = 1.0
        else:
            n_estimators = 100
            max_depth = 10
            C = trial.suggest_float("C", 0.01, 100.0, log=True)

        result = train_and_evaluate(X, Y, model_type=model_type, scaler_type=scaler_type,
                                     n_estimators=n_estimators, max_depth=max_depth, C=C)
        results.append({"params": result["params"], "weighted_f1": result["weighted_f1"]})
        return result["weighted_f1"]

    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=n_trials)

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
        "best_metrics": {"macro_f1": best_result["macro_f1"], "weighted_f1": best_result["weighted_f1"],
                         "per_tag": best_result["per_tag"]},
        "best_model": best_result["model"],
        "best_scaler": best_result["scaler"],
        "all_trials": sorted(results, key=lambda r: r["weighted_f1"], reverse=True),
    }


def _grid_search(X: np.ndarray, Y: np.ndarray) -> dict[str, Any]:
    """Fallback grid search."""
    configs = [
        {"model_type": "rf", "scaler_type": "standard", "n_estimators": 200, "max_depth": 12, "C": 1.0},
        {"model_type": "rf", "scaler_type": "minmax", "n_estimators": 150, "max_depth": 8, "C": 1.0},
        {"model_type": "gb", "scaler_type": "minmax", "n_estimators": 300, "max_depth": 3, "C": 1.0},
        {"model_type": "svc", "scaler_type": "standard", "n_estimators": 100, "max_depth": 10, "C": 1.0},
        {"model_type": "svc", "scaler_type": "standard", "n_estimators": 100, "max_depth": 10, "C": 10.0},
    ]
    best_result = None
    best_score = -1
    for cfg in configs:
        result = train_and_evaluate(X, Y, **cfg)
        if result["weighted_f1"] > best_score:
            best_score = result["weighted_f1"]
            best_result = result
    return {
        "best_params": best_result["params"],
        "best_metrics": {"macro_f1": best_result["macro_f1"], "weighted_f1": best_result["weighted_f1"],
                         "per_tag": best_result["per_tag"]},
        "best_model": best_result["model"],
        "best_scaler": best_result["scaler"],
        "all_trials": [],
    }


app = typer.Typer()


@app.command()
def main(
    limit: int = typer.Option(3000, help=""),
    output: Path = typer.Option(Path("data/bridge_text_classifier.joblib"), help=""),
    n_trials: int = typer.Option(50, "--n-trials", help=""),
    no_sweep: bool = typer.Option(False, "--no-sweep", help=""),
    exclude_models: Optional[list[str]] = typer.Option(None, "--exclude-models",
                                                       help="Model types to exclude from sweep (e.g. svc)"),
    json_report: Optional[Path] = typer.Option(None, "--json-report", help=""),
    embedding_url: str = typer.Option(EMBEDDING_URL, "--embedding-url", help=""),
):
    _set_embedding_url(embedding_url)

    # Fetch data via /memory sample
    lessons = fetch_labeled_lessons(limit)
    if not lessons:
        logger.error("No labeled lessons found")
        raise typer.Exit(code=1)

    # Prepare data (embed texts)
    X, Y, keys = prepare_data(lessons)
    logger.info(f"Data: {X.shape[0]} samples, {X.shape[1]} features, {Y.shape[1]} labels")
    logger.info(f"Label dist: {dict(zip(BRIDGE_TAGS, Y.sum(axis=0).astype(int).tolist()))}")

    # Train
    excluded = exclude_models or []
    if no_sweep:
        result = train_and_evaluate(X, Y, model_type="rf", scaler_type="standard",
                                     n_estimators=200, max_depth=12)
        metrics = {"macro_f1": result["macro_f1"], "weighted_f1": result["weighted_f1"],
                   "per_tag": result["per_tag"]}
        model, scaler, params = result["model"], result["scaler"], result["params"]
    else:
        model_types = [m for m in ["rf", "gb", "svc"] if m not in excluded]
        logger.info(f"Running {n_trials}-trial sweep (models: {model_types})...")
        sweep = run_sweep(X, Y, n_trials=n_trials, model_types=model_types)
        metrics = sweep["best_metrics"]
        model, scaler = sweep["best_model"], sweep["best_scaler"]
        params = sweep["best_params"]

        logger.info(f"\nTop 5:")
        for i, t in enumerate(sweep["all_trials"][:5]):
            logger.info(f"  {i+1}. F1={t['weighted_f1']:.3f} — {t['params']}")

    # Report
    logger.info(f"\nBest params: {params}")
    logger.info(f"Weighted F1: {metrics['weighted_f1']:.3f}")
    logger.info(f"Macro F1: {metrics['macro_f1']:.3f}")
    for tag in BRIDGE_TAGS:
        tm = metrics["per_tag"].get(tag, {})
        logger.info(f"  {tag:12s}: F1={tm.get('f1', 0):.3f}  P={tm.get('precision', 0):.3f}  "
                     f"R={tm.get('recall', 0):.3f}  support={tm.get('support', 0)}")

    # Save
    import joblib
    output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "scaler": scaler, "tags": BRIDGE_TAGS,
                 "embedding_dim": X.shape[1], "metrics": metrics}, output)
    logger.info(f"\nModel saved to {output}")

    if json_report:
        report = {"best_params": params, "metrics": metrics, "data_size": int(X.shape[0])}
        json_report.write_text(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    app()
