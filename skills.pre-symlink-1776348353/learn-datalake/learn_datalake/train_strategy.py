"""Standalone sklearn training module for table strategy classifier.

Trains GradientBoosting + LogisticRegression on harvested strategy outcomes,
picks best by macro_f1, saves joblib + metrics.json.
"""

import json
from pathlib import Path
from typing import Dict, List

import joblib
import numpy as np
from loguru import logger
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.utils.class_weight import compute_sample_weight
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.preprocessing import LabelEncoder

# Feature columns expected in labels.jsonl
FEATURE_COLS = [
    "table_style_borderless",
    "table_style_bordered",
    "table_style_mixed",
    "domain_scientific",
    "domain_defense",
    "domain_engineering",
    "num_tables",
    "num_strategies_tried",
    "max_fragmentation",
    "has_fragmentation",
    "lattice_found",
    "stream_found",
    # Per-strategy fragmentation scores (-1 = not tried)
    "frag_lattice_default",
    "frag_lattice_strong",
    "frag_stream_default",
    "frag_stream_tight",
    "frag_stream_wide",
    "frag_stream_columns",
    "frag_agent_tuned",
    "frag_memory_learned",
]

# Categorical feature that needs encoding
CAT_FEATURE = "category"
_KNOWN_CATEGORIES = [
    "unknown", "scientific", "defense", "financial", "medical", "legal", "general",
]


def _load_labels(labels_path: Path) -> tuple:
    """Load JSONL and return (X, y, label_encoder)."""
    records: List[Dict] = []
    for line in labels_path.read_text().strip().splitlines():
        records.append(json.loads(line))

    if not records:
        raise ValueError("No records in labels file")

    cat_encoder = {cat: i for i, cat in enumerate(_KNOWN_CATEGORIES)}

    X_rows = []
    y_labels = []
    for rec in records:
        feat = rec["features"]
        row = [feat.get(col, 0) for col in FEATURE_COLS]
        # Encode category as int
        cat_val = feat.get(CAT_FEATURE, "unknown")
        row.append(cat_encoder.get(cat_val, 0))
        X_rows.append(row)
        y_labels.append(rec["label"])

    X = np.array(X_rows, dtype=np.float64)
    le = LabelEncoder()
    y = le.fit_transform(y_labels)
    return X, y, le


def train_and_evaluate(labels_path: Path, output_dir: Path) -> Dict:
    """Train sklearn classifier on strategy outcomes. Returns metrics dict."""
    X, y, le = _load_labels(labels_path)
    n_samples = len(X)

    # Filter out classes with < 2 samples (StratifiedShuffleSplit requires >= 2)
    from collections import Counter
    class_counts = Counter(y)
    rare_classes = {cls for cls, count in class_counts.items() if count < 2}
    if rare_classes:
        rare_labels = [le.classes_[c] for c in rare_classes]
        logger.info(f"Dropping {len(rare_classes)} rare classes with <2 samples: {rare_labels}")
        mask = np.array([yi not in rare_classes for yi in y])
        # Convert encoded ints back to string labels, filter, re-encode
        y_str = le.inverse_transform(y)[mask]
        X = X[mask]
        le = LabelEncoder()
        y = le.fit_transform(y_str)
        n_samples = len(X)

    logger.info(f"Training on {n_samples} samples, {len(le.classes_)} classes: {list(le.classes_)}")

    # Stratified 80/20 split
    sss = StratifiedShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    train_idx, test_idx = next(sss.split(X, y))
    X_train, X_test = X[train_idx], X[test_idx]
    y_train, y_test = y[train_idx], y[test_idx]

    # Compute sample weights for balanced training (GB doesn't support class_weight)
    sample_weights_train = compute_sample_weight("balanced", y_train)

    candidates = {
        "gradient_boosting": GradientBoostingClassifier(
            n_estimators=200, max_depth=5, random_state=42,
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=200, max_depth=8, class_weight="balanced",
            random_state=42, n_jobs=-1,
        ),
        "logistic_regression": LogisticRegression(
            max_iter=500, class_weight="balanced", random_state=42,
        ),
    }

    best_model = None
    best_name = None
    best_f1 = -1.0
    results = {}

    for name, model in candidates.items():
        if name == "gradient_boosting":
            model.fit(X_train, y_train, sample_weight=sample_weights_train)
        else:
            model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        acc = accuracy_score(y_test, y_pred)
        f1 = f1_score(y_test, y_pred, average="macro", zero_division=0)
        results[name] = {"accuracy": round(acc, 4), "macro_f1": round(f1, 4)}
        logger.info(f"  {name}: accuracy={acc:.4f}, macro_f1={f1:.4f}")

        if f1 > best_f1:
            best_f1 = f1
            best_model = model
            best_name = name

    # Save best model
    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = output_dir / "model.joblib"
    joblib.dump(best_model, model_path)

    # Save label encoder
    le_path = output_dir / "label_encoder.joblib"
    joblib.dump(le, le_path)

    metrics = {
        "best_model": best_name,
        "accuracy": results[best_name]["accuracy"],
        "macro_f1": results[best_name]["macro_f1"],
        "n_samples": int(n_samples),
        "n_classes": int(len(le.classes_)),
        "classes": [str(c) for c in le.classes_],
        "model_path": str(model_path),
        "all_results": results,
    }

    metrics_path = output_dir / "metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2))
    logger.info(f"Best model: {best_name} → {model_path}")

    return metrics
