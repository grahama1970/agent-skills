#!/usr/bin/env python3
"""Train a TF-IDF + LogisticRegression classifier for evidence-based grading.

Binary: Pass vs Absurd (fabricated control IDs).
Uses TF-IDF features which give 91.7% CV accuracy (Wilson LB 0.866).

Output: sklearn Pipeline saved to models/sparta_stress_evidence/
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline

# Paths
TRAINING_DATA = Path(__file__).resolve().parents[1] / "results" / "merged_evidence_training_v2.jsonl"
MODEL_DIR = Path(__file__).resolve().parents[1] / "models" / "sparta_stress_evidence"


def load_data():
    texts, labels = [], []
    with open(TRAINING_DATA) as f:
        for line in f:
            item = json.loads(line)
            texts.append(item["text"])
            label = item["label"]
            # Merge Fail into Absurd (both are "not Pass", Fail has too few samples)
            if label == "Fail":
                label = "Absurd"
            labels.append(label)
    return texts, labels


def train(texts, labels):
    y = np.array(labels)
    label_set = sorted(set(labels))
    print(f"Classes: {label_set}")
    print(f"Distribution: {Counter(labels)}")

    # Build sklearn Pipeline (serializable, works with /assistant gateway)
    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(max_features=5000, ngram_range=(1, 2))),
        ("clf", LogisticRegression(
            max_iter=1000,
            class_weight="balanced",
            C=1.0,
            random_state=42,
        )),
    ])

    # 5-fold stratified CV
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    y_pred = cross_val_predict(pipeline, texts, y, cv=skf)

    print("\n=== 5-Fold Cross-Validation Results ===")
    print(classification_report(y, y_pred, target_names=label_set))
    print("Confusion Matrix:")
    print(confusion_matrix(y, y_pred, labels=label_set))

    agreement = np.mean(y_pred == y)
    print(f"\nOverall agreement: {agreement:.4f} ({agreement*100:.1f}%)")

    # Wilson score lower bound (99% CI)
    n = len(y)
    z = 2.576
    p_hat = agreement
    denom = 1 + z**2 / n
    center = (p_hat + z**2 / (2 * n)) / denom
    spread = z * np.sqrt((p_hat * (1 - p_hat) + z**2 / (4 * n)) / n) / denom
    wilson_lb = center - spread
    print(f"Wilson LB (99% CI): {wilson_lb:.4f}")
    passes = wilson_lb >= 0.85 and n >= 200
    print(f"Passes gate (>= 0.85 AND n >= 200): {'YES' if passes else 'NO'}")

    # Train final model on all data
    pipeline.fit(texts, y)

    # Verify
    test_preds = pipeline.predict([
        "What countermeasures protect against SV-SP-1 threats?",
        "How does SV-ZZ-99 address quantum security?",
        "How to install WordPress on Ubuntu?",
    ])
    print(f"\nTest predictions:")
    print(f"  Valid SPARTA control: {test_preds[0]}")
    print(f"  Fabricated control: {test_preds[1]}")
    print(f"  Non-SPARTA question: {test_preds[2]}")

    # Confidence scores
    proba = pipeline.predict_proba([
        "What countermeasures protect against SV-SP-1 threats?",
        "How does SV-ZZ-99 address quantum security?",
    ])
    print(f"\nConfidence scores:")
    for i, q in enumerate(["Valid control", "Fabricated"]):
        max_conf = max(proba[i])
        pred_class = pipeline.classes_[np.argmax(proba[i])]
        print(f"  {q}: {pred_class} ({max_conf:.3f})")

    # Save
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODEL_DIR / "sklearn_pipeline.joblib"
    joblib.dump(pipeline, model_path)
    print(f"\nSaved pipeline to {model_path}")

    # Save metadata
    metadata = {
        "task": "sparta_stress_evidence",
        "type": "validator",
        "model_type": "sklearn_pipeline",
        "model_path": str(model_path),
        "cv_accuracy": round(float(agreement), 4),
        "wilson_lb": round(float(wilson_lb), 4),
        "n_samples": len(texts),
        "n_classes": len(label_set),
        "classes": label_set,
        "threshold": 0.6,
        "shadow_mode": True,
    }
    with open(MODEL_DIR / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    return agreement, wilson_lb


if __name__ == "__main__":
    texts, labels = load_data()
    print(f"Loaded {len(texts)} samples")
    agreement, wilson_lb = train(texts, labels)
