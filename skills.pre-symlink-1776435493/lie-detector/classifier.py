"""Layer 4: Embedding + sklearn classifier for gaming/honest/drift detection.

Purpose:
    Classify conversation turns using sentence-transformer embeddings +
    LogisticRegression. Trained on the 2026-02-28 incident seed data
    plus R14 regression findings. Shadow-LEGO Tier 0.5.

Inputs:
    - Text description of what an agent did in a turn
    - Training data JSONL (text + label pairs)

Outputs:
    - ClassifierResult with HONEST/GAMING/DRIFT prediction + confidence
    - Shadow log entry for /assistant teacher review

Failure modes:
    - Model not trained → return INCONCLUSIVE with warning
    - sentence-transformers not installed → graceful skip
    - Training data too small → warn but train anyway

Dependencies:
    - sentence-transformers >= 2.2.0
    - scikit-learn >= 1.0.0
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import find_dotenv, load_dotenv
from loguru import logger

load_dotenv(find_dotenv(usecwd=True), override=False)

STORAGE_DIR = Path(os.getenv(
    "LIE_DETECTOR_STORAGE",
    "/mnt/storage12tb/skills/lie-detector",
))
MODEL_DIR = STORAGE_DIR / "models" / "setfit-v1"
SHADOW_FILE = STORAGE_DIR / "shadow.jsonl"

LABELS = ["honest", "gaming", "drift"]
GAMING_THRESHOLD = 0.8
HONEST_THRESHOLD = 0.8

# Lazy-loaded model
_model = None


@dataclass
class ClassifierResult:
    verdict: str  # HONEST | GAMING | DRIFT | INCONCLUSIVE
    confidence: float = 0.0
    probabilities: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "confidence": round(self.confidence, 3),
            "probabilities": {k: round(v, 3) for k, v in self.probabilities.items()},
        }


def _load_model():
    """Lazy-load the embedding model + sklearn classifier."""
    global _model
    if _model is not None:
        return _model
    clf_path = MODEL_DIR / "classifier.pkl"
    config_path = MODEL_DIR / "config.json"
    if not clf_path.exists():
        logger.warning("classifier not found at {} — run 'train' first", clf_path)
        return None
    try:
        import pickle
        from sentence_transformers import SentenceTransformer
        with open(clf_path, "rb") as f:
            clf = pickle.load(f)
        config = {}
        if config_path.exists():
            config = json.loads(config_path.read_text())
        backbone = config.get("backbone", "sentence-transformers/all-MiniLM-L6-v2")
        encoder = SentenceTransformer(backbone)
        _model = {"encoder": encoder, "classifier": clf, "config": config}
        logger.info("loaded classifier from {} (backbone={})", MODEL_DIR, backbone)
        return _model
    except ImportError:
        logger.warning("sentence-transformers not installed — classifier unavailable")
        return None
    except Exception as e:
        logger.error("failed to load classifier: {}", e)
        return None


def classify(text: str) -> ClassifierResult:
    """Classify a conversation turn as honest/gaming/drift."""
    model = _load_model()
    if model is None:
        return ClassifierResult(verdict="INCONCLUSIVE", confidence=0.0)

    try:
        t0 = time.monotonic()
        encoder = model["encoder"]
        clf = model["classifier"]
        embedding = encoder.encode([text], show_progress_bar=False)
        predictions = clf.predict(embedding)
        probs = clf.predict_proba(embedding)
        latency_ms = (time.monotonic() - t0) * 1000

        pred_idx = int(predictions[0])
        pred_label = LABELS[pred_idx] if pred_idx < len(LABELS) else "unknown"

        prob_dict = {}
        for i, label in enumerate(LABELS):
            if i < probs.shape[1]:
                prob_dict[label] = float(probs[0][i])

        confidence = max(prob_dict.values()) if prob_dict else 0.5

        # Map to verdict
        if pred_label == "gaming" and confidence >= GAMING_THRESHOLD:
            verdict = "GAMING"
        elif pred_label == "honest" and confidence >= HONEST_THRESHOLD:
            verdict = "HONEST"
        elif pred_label == "drift":
            verdict = "DRIFT"
        else:
            verdict = "INCONCLUSIVE"

        result = ClassifierResult(
            verdict=verdict, confidence=confidence, probabilities=prob_dict,
        )

        # Shadow log
        _log_shadow(text, result, latency_ms)
        return result

    except Exception as e:
        logger.error("classifier inference failed: {}", e)
        return ClassifierResult(verdict="INCONCLUSIVE", confidence=0.0)


def train(training_data_path: Path, output_dir: Path | None = None) -> dict[str, Any]:
    """Train embedding + sklearn classifier on labeled examples.

    Training data format (JSONL):
        {"text": "...", "label": "gaming"}
        {"text": "...", "label": "honest"}
    """
    import pickle
    from collections import Counter

    try:
        from sentence_transformers import SentenceTransformer
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import cross_val_score
        import numpy as np
    except ImportError as e:
        raise RuntimeError(f"Dependencies not installed: {e}") from e

    out = output_dir or MODEL_DIR
    out.mkdir(parents=True, exist_ok=True)

    # Load training data
    texts, labels = [], []
    for line in training_data_path.read_text().strip().split("\n"):
        if not line.strip():
            continue
        entry = json.loads(line)
        texts.append(entry["text"])
        labels.append(entry["label"])

    label_map = {label: i for i, label in enumerate(LABELS)}
    numeric_labels = np.array([label_map.get(l, 0) for l in labels])

    logger.info("training classifier on {} examples ({} per class avg)",
                len(texts), len(texts) // max(len(set(labels)), 1))

    # Encode
    encoder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    embeddings = encoder.encode(texts, show_progress_bar=False)

    # Train with cross-validation
    clf = LogisticRegression(max_iter=1000, C=10.0, class_weight="balanced")
    cv_scores = cross_val_score(clf, embeddings, numeric_labels, cv=min(5, len(texts)), scoring="f1_weighted")
    clf.fit(embeddings, numeric_labels)

    # Save
    with open(out / "classifier.pkl", "wb") as f:
        pickle.dump(clf, f)

    config = {
        "label_to_idx": label_map,
        "idx_to_label": {str(v): k for k, v in label_map.items()},
        "backbone": "sentence-transformers/all-MiniLM-L6-v2",
        "classifier": "LogisticRegression",
        "training_examples": len(texts),
        "cv_f1_weighted": round(float(cv_scores.mean()), 3),
        "training_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }
    with open(out / "config.json", "w") as f:
        json.dump(config, f, indent=2)

    # Reset cached model
    global _model
    _model = None

    logger.info("classifier saved to {} (CV F1={:.3f})", out, cv_scores.mean())
    label_counts = dict(Counter(labels))
    return {"model_dir": str(out), "examples": len(texts), "labels": label_counts, "cv_f1": round(float(cv_scores.mean()), 3)}


def _log_shadow(text: str, result: ClassifierResult, latency_ms: float) -> None:
    """Append shadow log entry for /assistant teacher review."""
    SHADOW_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task": "lie-detection",
        "tier": 0.5,
        "input_text": text[:500],
        "prediction": result.verdict,
        "confidence": result.confidence,
        "probabilities": result.probabilities,
        "latency_ms": round(latency_ms, 1),
    }
    with open(SHADOW_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")
