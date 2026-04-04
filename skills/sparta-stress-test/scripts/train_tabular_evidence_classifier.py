#!/usr/bin/env python3
"""Train tabular evidence classifier using grader signal features.

Uses features from evidence grader (entity extraction + QRA recall — fast ArangoDB
lookups) instead of TF-IDF on raw text. This captures the actual discriminative
signals: fabricated control IDs, QRA coverage, BM25 relevance scores.

Benchmarks 3 sklearn models via 5-fold stratified CV, computes Wilson score,
and checks against the promotion gate.

Compatible with /classifier-lab tabular format:
  {"features": {"has_valid_control": 1.0, ...}, "label": "Pass"}
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import StratifiedKFold, cross_val_predict

TRAINING_DATA = Path(__file__).resolve().parents[1] / "results" / "tabular_evidence_training.jsonl"
MODEL_DIR = Path(__file__).resolve().parents[1] / "models" / "sparta_stress_evidence"


def load_data():
    """Load tabular JSONL with {features: {...}, label: ...}."""
    feature_dicts, labels = [], []
    with open(TRAINING_DATA) as f:
        for line in f:
            item = json.loads(line)
            feature_dicts.append(item["features"])
            labels.append(item["label"])

    # Get sorted feature keys for consistent ordering
    all_keys = sorted(feature_dicts[0].keys())
    X = np.array([[fd.get(k, 0.0) for k in all_keys] for fd in feature_dicts])
    y = np.array(labels)
    return X, y, all_keys


def wilson_lower_bound(p_hat: float, n: int, z: float = 2.576) -> float:
    """Wilson score confidence interval lower bound (99% CI by default)."""
    denom = 1 + z**2 / n
    center = (p_hat + z**2 / (2 * n)) / denom
    spread = z * np.sqrt((p_hat * (1 - p_hat) + z**2 / (4 * n)) / n) / denom
    return center - spread


def benchmark_model(name: str, clf, X: np.ndarray, y: np.ndarray) -> dict:
    """5-fold stratified CV on a single model. Returns metrics."""
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    y_pred = cross_val_predict(clf, X, y, cv=skf)

    agreement = float(np.mean(y_pred == y))
    wilson_lb = wilson_lower_bound(agreement, len(y))
    passes = wilson_lb >= 0.85 and len(y) >= 200

    label_set = sorted(set(y))
    report = classification_report(y, y_pred, target_names=label_set, output_dict=True)
    cm = confusion_matrix(y, y_pred, labels=label_set)

    return {
        "name": name,
        "accuracy": agreement,
        "wilson_lb": wilson_lb,
        "passes_gate": passes,
        "macro_f1": report["macro avg"]["f1-score"],
        "per_class": {cls: report[cls] for cls in label_set},
        "confusion_matrix": cm.tolist(),
        "n_samples": len(y),
    }


def main():
    X, y, feature_keys = load_data()
    label_set = sorted(set(y))
    print(f"Loaded {len(y)} samples, {len(feature_keys)} features")
    print(f"Classes: {label_set}")
    print(f"Distribution: {Counter(y.tolist())}")
    print(f"Features: {feature_keys}\n")

    models = {
        "gradient_boosting": GradientBoostingClassifier(
            n_estimators=100, max_depth=5, random_state=42,
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=200, max_depth=10, random_state=42, class_weight="balanced",
        ),
        "logistic_regression": LogisticRegression(
            max_iter=1000, class_weight="balanced", C=1.0, random_state=42,
        ),
    }

    results = []
    for name, clf in models.items():
        print(f"\n=== {name} ===")
        result = benchmark_model(name, clf, X, y)
        results.append(result)

        print(f"  Accuracy: {result['accuracy']:.4f} ({result['accuracy']*100:.1f}%)")
        print(f"  Macro F1: {result['macro_f1']:.4f}")
        print(f"  Wilson LB (99% CI): {result['wilson_lb']:.4f}")
        print(f"  Passes gate (>= 0.85 AND n >= 200): {'YES' if result['passes_gate'] else 'NO'}")
        print(f"  Confusion matrix:")
        for i, cls in enumerate(label_set):
            print(f"    {cls}: {result['confusion_matrix'][i]}")

    # Find best model
    best = max(results, key=lambda r: r["wilson_lb"])
    print(f"\n{'='*60}")
    print(f"BEST MODEL: {best['name']}")
    print(f"  Accuracy: {best['accuracy']:.4f} ({best['accuracy']*100:.1f}%)")
    print(f"  Macro F1: {best['macro_f1']:.4f}")
    print(f"  Wilson LB: {best['wilson_lb']:.4f}")
    print(f"  PASSES GATE: {'YES' if best['passes_gate'] else 'NO'}")
    print(f"{'='*60}")

    # Train final model on all data
    best_clf_class = models[best["name"]].__class__
    best_params = models[best["name"]].get_params()
    final_clf = best_clf_class(**best_params)
    final_clf.fit(X, y)

    # Feature importance
    if hasattr(final_clf, "feature_importances_"):
        importances = list(zip(feature_keys, final_clf.feature_importances_))
        importances.sort(key=lambda x: x[1], reverse=True)
        print(f"\nFeature importance ({best['name']}):")
        for feat, imp in importances:
            print(f"  {feat:30s}: {imp:.4f}")

    # Save
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODEL_DIR / "sklearn_pipeline.joblib"
    joblib.dump({
        "model": final_clf,
        "feature_keys": feature_keys,
        "label_classes": label_set,
    }, model_path)
    print(f"\nSaved model to {model_path}")

    # Save metadata
    metadata = {
        "task": "sparta_stress_evidence",
        "type": "validator",
        "model_type": "tabular_sklearn",
        "model_path": str(model_path),
        "backbone": best["name"],
        "cv_accuracy": round(float(best["accuracy"]), 4),
        "wilson_lb": round(float(best["wilson_lb"]), 4),
        "macro_f1": round(float(best["macro_f1"]), 4),
        "n_samples": int(best["n_samples"]),
        "n_classes": len(label_set),
        "classes": label_set,
        "feature_keys": feature_keys,
        "threshold": 0.6,
        "shadow_mode": bool(not best["passes_gate"]),
        "augmented_with_db": True,
        "all_results": [
            {k: (bool(v) if isinstance(v, (np.bool_,)) else float(v) if isinstance(v, (np.floating,)) else v)
             for k, v in r.items() if k != "confusion_matrix"}
            for r in results
        ],
    }
    with open(MODEL_DIR / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"Saved metadata to {MODEL_DIR / 'metadata.json'}")

    return best


if __name__ == "__main__":
    best = main()
    sys.exit(0 if best["passes_gate"] else 1)
