#!/usr/bin/env python3
"""Train and save the Shadow S00 classifier.

Uses gradient boosting (winner from classifier-lab benchmark) to predict
whether a PDF needs stream mode for table extraction.

Shadow-LEGO pattern: This classifier is a SEED PRODUCER.
It informs S05 strategy selection, never gates it.

Usage:
    python train_shadow_s00.py --data data/shadow_s00.jsonl
    python train_shadow_s00.py --data data/shadow_s00.jsonl --model-dir models/shadow-s00
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import StratifiedKFold, cross_val_score


def load_data(jsonl_path: Path) -> tuple[np.ndarray, np.ndarray, list[str], list[str]]:
    """Load training data from JSONL.

    Returns (X, y, feature_names, class_names).
    """
    rows = []
    labels = []
    feature_names = None

    with open(jsonl_path) as f:
        for line in f:
            d = json.loads(line)
            features = d["features"]
            if feature_names is None:
                feature_names = sorted(features.keys())
            row = [float(features.get(k, 0)) for k in feature_names]
            rows.append(row)
            labels.append(d["label"])

    X = np.array(rows)
    class_names = sorted(set(labels))
    label_to_idx = {c: i for i, c in enumerate(class_names)}
    y = np.array([label_to_idx[l] for l in labels])

    return X, y, feature_names, class_names


def train(
    data_path: Path,
    model_dir: Path,
    n_estimators: int = 200,
    max_depth: int = 5,
    seed: int = 42,
) -> dict:
    """Train gradient boosting classifier and save model + metadata."""
    print(f"Loading data from: {data_path}")
    X, y, feature_names, class_names = load_data(data_path)
    print(f"  Samples: {len(X)}, Features: {len(feature_names)}, Classes: {class_names}")
    print(f"  Class distribution: {dict(zip(class_names, [int((y==i).sum()) for i in range(len(class_names))]))}")

    # Train with cross-validation
    clf = GradientBoostingClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        random_state=seed,
        min_samples_leaf=5,
    )

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
    cv_scores = cross_val_score(clf, X, y, cv=cv, scoring="f1_macro")
    print(f"\n  CV macro_F1: {cv_scores.mean():.3f} ± {cv_scores.std():.3f}")
    print(f"  Per-fold: {[f'{s:.3f}' for s in cv_scores]}")

    # Train on full data
    clf.fit(X, y)

    # Feature importance
    importances = sorted(
        zip(feature_names, clf.feature_importances_),
        key=lambda x: -x[1],
    )
    print(f"\n  Top features:")
    for name, imp in importances[:10]:
        print(f"    {name}: {imp:.4f}")

    # Full-data classification report
    y_pred = clf.predict(X)
    print(f"\n  Full-data classification report:")
    print(classification_report(y, y_pred, target_names=class_names))

    # Save model
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / "shadow_s00_model.joblib"
    joblib.dump(clf, model_path)

    # Save metadata for inference
    metadata = {
        "feature_names": feature_names,
        "class_names": class_names,
        "n_samples": int(len(X)),
        "n_features": len(feature_names),
        "cv_macro_f1_mean": float(cv_scores.mean()),
        "cv_macro_f1_std": float(cv_scores.std()),
        "feature_importances": {n: float(i) for n, i in importances},
        "model_file": "shadow_s00_model.joblib",
        "model_type": "GradientBoostingClassifier",
        "hyperparams": {
            "n_estimators": n_estimators,
            "max_depth": max_depth,
            "min_samples_leaf": 5,
        },
    }
    metadata_path = model_dir / "metadata.json"
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"\n  Model saved to: {model_path}")
    print(f"  Metadata saved to: {metadata_path}")
    return metadata


import typer

app = typer.Typer()


@app.command()
def main(
    data: Path = typer.Option(..., help=""),
    model_dir: Path = typer.Option(
        Path(__file__).parent.parent / "models" / "shadow-s00",
        "--model-dir",
        help="",
    ),
    n_estimators: int = typer.Option(200, "--n-estimators", help=""),
    max_depth: int = typer.Option(5, "--max-depth", help=""),
):
    train(data, model_dir, n_estimators, max_depth)


if __name__ == "__main__":
    app()
