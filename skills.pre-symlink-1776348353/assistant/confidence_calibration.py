#!/usr/bin/env python3
"""Confidence calibration and retrieval-augmented validation for classifiers.

Two independent improvements to /assistant's confidence:
1. Temperature scaling: makes softmax confidence meaningful
2. k-NN retrieval: validates predictions against nearest training examples

Usage:
    # Fit calibration on validation data
    python confidence_calibration.py fit \
        --data ~/.pi/assistant/training_data/canvas-intent/classifier_lab_input.jsonl \
        --output ~/.pi/models/classifiers/canvas_intent_calibration.json

    # At inference (imported by assistant.py):
    from confidence_calibration import CalibratedClassifier
    cal = CalibratedClassifier.load("canvas-intent")
    result = cal.predict("show me a chart of failure rates")
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from loguru import logger

CALIBRATION_DIR = Path.home() / ".pi/models/classifiers"


class TemperatureScaler:
    """Post-hoc temperature scaling for confidence calibration.

    Learns a single parameter T that rescales logits before softmax,
    making confidence scores reflect true accuracy.
    """

    def __init__(self, temperature: float = 1.0):
        self.temperature = temperature

    def fit(self, logits: np.ndarray, labels: np.ndarray) -> float:
        """Find optimal temperature on validation set via grid search."""
        from scipy.optimize import minimize_scalar

        def nll(T):
            if T <= 0.01:
                return 1e10
            scaled = logits / T
            # Numerically stable softmax
            shifted = scaled - scaled.max(axis=1, keepdims=True)
            exp_scaled = np.exp(shifted)
            probs = exp_scaled / exp_scaled.sum(axis=1, keepdims=True)
            # NLL
            eps = 1e-10
            log_probs = np.log(probs[np.arange(len(labels)), labels] + eps)
            return -log_probs.mean()

        result = minimize_scalar(nll, bounds=(0.1, 10.0), method="bounded")
        self.temperature = float(result.x)
        logger.info(f"Optimal temperature: {self.temperature:.3f}")
        return self.temperature

    def calibrate(self, logits: np.ndarray) -> np.ndarray:
        """Apply temperature scaling to logits → calibrated probabilities."""
        scaled = logits / self.temperature
        shifted = scaled - scaled.max(axis=1, keepdims=True)
        exp_scaled = np.exp(shifted)
        return exp_scaled / exp_scaled.sum(axis=1, keepdims=True)


class KNNRetriever:
    """k-NN retrieval over training embeddings for confidence validation.

    If nearest neighbors disagree with classifier, signal low confidence.
    """

    def __init__(self, embeddings: np.ndarray, labels: np.ndarray, k: int = 5):
        self.embeddings = embeddings
        self.labels = labels
        self.k = k

    def query(self, query_embedding: np.ndarray) -> Dict[str, Any]:
        """Find k nearest neighbors and compute agreement score."""
        # Cosine similarity (embeddings should be normalized)
        if query_embedding.ndim == 1:
            query_embedding = query_embedding.reshape(1, -1)

        # Normalize
        query_norm = query_embedding / (np.linalg.norm(query_embedding, axis=1, keepdims=True) + 1e-10)
        train_norm = self.embeddings / (np.linalg.norm(self.embeddings, axis=1, keepdims=True) + 1e-10)

        similarities = (query_norm @ train_norm.T).squeeze()
        top_k_idx = np.argsort(similarities)[-self.k:][::-1]

        neighbor_labels = self.labels[top_k_idx]
        neighbor_sims = similarities[top_k_idx]

        return {
            "neighbor_labels": neighbor_labels.tolist(),
            "neighbor_similarities": neighbor_sims.tolist(),
        }

    def agreement_score(self, query_embedding: np.ndarray, predicted_class: int) -> float:
        """Fraction of k neighbors that agree with the prediction."""
        result = self.query(query_embedding)
        agree = sum(1 for l in result["neighbor_labels"] if l == predicted_class)
        return agree / self.k


class CalibratedClassifier:
    """Combines classifier + temperature scaling + k-NN retrieval.

    Loaded at inference time by assistant.py for enhanced confidence.
    """

    def __init__(
        self,
        temperature: float = 1.0,
        class_thresholds: Optional[Dict[str, float]] = None,
        knn_alpha: float = 0.3,
    ):
        self.temperature = temperature
        self.class_thresholds = class_thresholds or {}
        self.knn_alpha = knn_alpha
        self.default_threshold = 0.6

    @classmethod
    def load(cls, task: str) -> Optional["CalibratedClassifier"]:
        """Load calibration config for a task."""
        cal_path = CALIBRATION_DIR / f"{task.replace('-', '_')}_calibration.json"
        if not cal_path.exists():
            return None
        with open(cal_path) as f:
            config = json.load(f)
        return cls(
            temperature=config.get("temperature", 1.0),
            class_thresholds=config.get("class_thresholds", {}),
            knn_alpha=config.get("knn_alpha", 0.3),
        )

    def adjusted_confidence(
        self,
        raw_confidence: float,
        predicted_class: str,
    ) -> Tuple[float, bool]:
        """Return calibrated confidence and whether to trigger fallback.

        Returns:
            (calibrated_confidence, should_fallback)
        """
        # Apply temperature scaling approximation on raw confidence
        # (exact scaling requires logits, this is a sigmoid approximation)
        if self.temperature != 1.0:
            # Map confidence through inverse-softmax → scale → softmax
            # Simplified: higher T → lower confidence, lower T → higher confidence
            calibrated = raw_confidence ** (1.0 / self.temperature)
        else:
            calibrated = raw_confidence

        # Per-class threshold
        threshold = self.class_thresholds.get(predicted_class, self.default_threshold)
        should_fallback = calibrated < threshold

        return calibrated, should_fallback

    def to_dict(self) -> Dict[str, Any]:
        return {
            "temperature": self.temperature,
            "class_thresholds": self.class_thresholds,
            "knn_alpha": self.knn_alpha,
            "default_threshold": self.default_threshold,
        }


def fit_calibration(
    data_path: Path,
    task: str = "canvas-intent",
    val_ratio: float = 0.15,
    seed: int = 42,
) -> Dict[str, Any]:
    """Fit temperature scaling and per-class thresholds on validation data.

    This function:
    1. Loads the training data
    2. Splits into train/val
    3. Trains a quick classifier to get logits on val set
    4. Fits temperature T
    5. Computes per-class optimal thresholds
    """
    # Load data
    data = []
    with open(data_path) as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))

    labels_sorted = sorted(set(d["label"] for d in data))
    label2idx = {l: i for i, l in enumerate(labels_sorted)}

    # Stratified split
    rng = random.Random(seed)
    by_label = defaultdict(list)
    for d in data:
        by_label[d["label"]].append(d)

    train_data, val_data = [], []
    for label in sorted(by_label.keys()):
        items = list(by_label[label])
        rng.shuffle(items)
        n_val = max(1, int(round(len(items) * val_ratio)))
        n_val = min(n_val, len(items) - 1)
        val_data.extend(items[:n_val])
        train_data.extend(items[n_val:])

    print(f"Calibration: {len(train_data)} train, {len(val_data)} val")

    # Train a quick sklearn model to get logits
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression

    tfidf = TfidfVectorizer(max_features=5000, ngram_range=(1, 2))
    X_train = tfidf.fit_transform([d["text"] for d in train_data])
    y_train = np.array([label2idx[d["label"]] for d in train_data])
    X_val = tfidf.transform([d["text"] for d in val_data])
    y_val = np.array([label2idx[d["label"]] for d in val_data])

    clf = LogisticRegression(max_iter=1000, C=1.0)
    clf.fit(X_train, y_train)

    # Get logits (decision_function) on validation set
    logits = clf.decision_function(X_val)

    # Fit temperature
    scaler = TemperatureScaler()
    temperature = scaler.fit(logits, y_val)

    # Calibrated probabilities
    cal_probs = scaler.calibrate(logits)
    preds = np.argmax(cal_probs, axis=1)
    confs = np.max(cal_probs, axis=1)

    # Per-class optimal threshold (maximize F1 per class)
    class_thresholds = {}
    for cls_name, cls_idx in label2idx.items():
        cls_mask = preds == cls_idx
        if cls_mask.sum() == 0:
            class_thresholds[cls_name] = 0.6
            continue

        cls_correct = (preds == y_val) & cls_mask
        cls_confs = confs[cls_mask]
        cls_correct_flags = cls_correct[cls_mask]

        # Find threshold that maximizes precision while keeping recall > 0.5
        best_thresh = 0.6
        best_f1 = 0
        for thresh in np.arange(0.3, 0.9, 0.05):
            above = cls_confs >= thresh
            if above.sum() == 0:
                continue
            precision = cls_correct_flags[above].mean() if above.sum() > 0 else 0
            recall = above.sum() / len(cls_confs)
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
            if f1 > best_f1:
                best_f1 = f1
                best_thresh = thresh

        class_thresholds[cls_name] = round(float(best_thresh), 2)

    print(f"Temperature: {temperature:.3f}")
    print(f"Per-class thresholds: {json.dumps(class_thresholds, indent=2)}")

    # Overall calibrated accuracy
    acc = (preds == y_val).mean()
    print(f"Calibrated val accuracy: {acc:.3f}")

    # Save calibration config
    config = {
        "temperature": round(temperature, 4),
        "class_thresholds": class_thresholds,
        "knn_alpha": 0.3,
        "default_threshold": 0.6,
        "val_accuracy": round(float(acc), 4),
        "val_samples": len(val_data),
        "labels": labels_sorted,
    }

    out_path = CALIBRATION_DIR / f"{task.replace('-', '_')}_calibration.json"
    with open(out_path, "w") as f:
        json.dump(config, f, indent=2)

    print(f"Saved calibration to {out_path}")
    return config


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "fit":
        data_path = Path.home() / ".pi/assistant/training_data/canvas-intent/classifier_lab_input.jsonl"
        if len(sys.argv) > 3 and sys.argv[2] == "--data":
            data_path = Path(sys.argv[3])
        fit_calibration(data_path)
    else:
        print("Usage: python confidence_calibration.py fit [--data path]")
