#!/usr/bin/env python3
"""Bootstrap a strategy classifier from shadow.jsonl training data.

Reads the shadow log (3,000+ extraction records) and trains a lightweight
gradient-boosted classifier to predict optimal table extraction strategy
(lattice vs stream vs network vs hybrid) from PDF features.

Usage:
    python train_strategy_classifier.py --shadow-log ../../shadow.jsonl
    python train_strategy_classifier.py --shadow-log ../../shadow.jsonl --output model.joblib
    python train_strategy_classifier.py --stats  # Just print data stats
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import typer

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
SHADOW_LOG = SKILL_DIR / "shadow.jsonl"
MODEL_PATH = SKILL_DIR / "strategy_classifier.joblib"


def load_shadow_data(path: Path = SHADOW_LOG) -> list[dict]:
    """Load and deduplicate shadow log entries."""
    if not path.exists():
        print(f"Shadow log not found: {path}")
        return []

    entries = []
    seen = set()
    for line in path.read_text().strip().split("\n"):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            # Deduplicate by (filepath, pages, strategy_actual)
            key = (entry.get("filepath", ""), entry.get("pages", ""),
                   entry.get("strategy_actual", ""))
            if key not in seen:
                seen.add(key)
                entries.append(entry)
        except json.JSONDecodeError:
            continue
    return entries


def compute_stats(entries: list[dict]) -> dict:
    """Compute training data statistics."""
    strategies = Counter(e.get("strategy_actual", "unknown") for e in entries)
    accuracies = [e.get("accuracy", 0) for e in entries]
    agreements = sum(1 for e in entries if e.get("agree", False))
    files = len({e.get("filepath", "") for e in entries})

    return {
        "total_entries": len(entries),
        "unique_files": files,
        "strategy_distribution": dict(strategies),
        "agreement_rate": round(agreements / len(entries) * 100, 1) if entries else 0,
        "avg_accuracy": round(sum(accuracies) / len(accuracies), 1) if accuracies else 0,
        "high_accuracy_pct": round(
            sum(1 for a in accuracies if a >= 80) / len(accuracies) * 100, 1
        ) if accuracies else 0,
    }


def prepare_training_data(entries: list[dict]):
    """Convert shadow log entries to feature vectors and labels.

    Features extracted from the shadow log:
    - num_tables: int (proxy for PDF complexity)
    - accuracy: float (quality achieved)
    - elapsed_seconds: float (extraction time)
    - confidence: float (routing confidence)
    - agree: bool (predicted matched actual)

    Label: strategy_actual (the strategy that produced the best result)

    Returns (X, y, feature_names) as numpy arrays.
    """
    try:
        import numpy as np
    except ImportError:
        print("numpy required: pip install numpy")
        sys.exit(1)

    feature_names = [
        "num_tables", "accuracy", "elapsed_seconds", "confidence",
    ]

    X = []
    y = []
    for e in entries:
        # Only use entries where we know the actual winning strategy
        strategy = e.get("strategy_actual", "")
        if not strategy or strategy == "auto":
            continue
        # Only use high-confidence labels (accuracy >= 50 means strategy worked)
        if e.get("accuracy", 0) < 50:
            continue

        features = [
            e.get("num_tables", 0),
            e.get("accuracy", 0),
            e.get("elapsed_seconds", 0),
            e.get("confidence", 0),
        ]
        X.append(features)
        y.append(strategy)

    return np.array(X), np.array(y), feature_names


def train_classifier(X, y, feature_names: list[str]):
    """Train a gradient-boosted classifier on the shadow data.

    Uses scikit-learn's HistGradientBoostingClassifier — fast, handles
    small datasets well, no hyperparameter tuning needed.
    """
    try:
        from sklearn.ensemble import HistGradientBoostingClassifier
        from sklearn.model_selection import cross_val_score
        from sklearn.preprocessing import LabelEncoder
        import joblib
    except ImportError:
        print("scikit-learn required: pip install scikit-learn")
        sys.exit(1)

    le = LabelEncoder()
    y_encoded = le.fit_transform(y)

    clf = HistGradientBoostingClassifier(
        max_iter=100,
        max_depth=4,
        min_samples_leaf=5,
        random_state=42,
    )

    # Cross-validation score
    if len(set(y_encoded)) >= 2 and len(y_encoded) >= 10:
        scores = cross_val_score(clf, X, y_encoded, cv=min(5, len(set(y_encoded))),
                                 scoring="accuracy")
        print(f"Cross-val accuracy: {scores.mean():.3f} (+/- {scores.std():.3f})")
    else:
        print(f"Not enough class diversity for cross-validation (classes: {set(y)})")

    # Train on full data
    clf.fit(X, y_encoded)

    # Save model + label encoder + feature names
    model_bundle = {
        "classifier": clf,
        "label_encoder": le,
        "feature_names": feature_names,
        "classes": list(le.classes_),
        "training_samples": len(y),
    }
    joblib.dump(model_bundle, MODEL_PATH)
    print(f"Model saved to {MODEL_PATH}")
    print(f"Classes: {list(le.classes_)}")
    print(f"Training samples: {len(y)}")

    return model_bundle


def predict_strategy(model_path: Path = MODEL_PATH, **features) -> tuple[str, float]:
    """Predict optimal strategy for a PDF.

    Args:
        num_tables: Expected number of tables (0 if unknown)
        accuracy: Previous accuracy on similar PDFs (0 if unknown)
        elapsed_seconds: Previous extraction time (0 if unknown)
        confidence: Current routing confidence (0 if unknown)

    Returns:
        (strategy_name, confidence) tuple
    """
    import joblib
    import numpy as np

    bundle = joblib.load(model_path)
    clf = bundle["classifier"]
    le = bundle["label_encoder"]
    feature_names = bundle["feature_names"]

    X = np.array([[features.get(f, 0) for f in feature_names]])
    proba = clf.predict_proba(X)[0]
    predicted_idx = proba.argmax()
    confidence = float(proba[predicted_idx])
    strategy = le.inverse_transform([predicted_idx])[0]

    return strategy, confidence


def main(
    shadow_log: Path = typer.Option(SHADOW_LOG, "--shadow-log", help="Shadow JSONL log path"),
    output: Path = typer.Option(MODEL_PATH, "--output", help="Output model path"),
    stats: bool = typer.Option(False, "--stats", help="Print stats only"),
) -> None:
    """Train strategy classifier from shadow logs."""
    global MODEL_PATH
    MODEL_PATH = output

    entries = load_shadow_data(shadow_log)
    if not entries:
        print("No training data found.")
        sys.exit(1)

    stats = compute_stats(entries)
    print(f"Training data statistics:")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    if stats:
        return

    X, y, feature_names = prepare_training_data(entries)
    if len(X) < 10:
        print(f"Insufficient training data: {len(X)} samples (need >= 10)")
        sys.exit(1)

    print(f"\nTraining on {len(X)} samples...")
    train_classifier(X, y, feature_names)


if __name__ == "__main__":
    typer.run(main)
