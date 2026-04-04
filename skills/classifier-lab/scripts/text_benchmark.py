#!/usr/bin/env python3
"""
Text and tabular benchmark engine for classifier-lab.

Mirrors benchmark.py's structure and output contract but supports:
- Text classification via HuggingFace transformers
- Tabular classification via scikit-learn

Output contract is identical to vision benchmark:
  {status, selected_backbone, selected_metrics, source, results[], taxonomy, memory_store}

Text modality adds latency fields to selected_metrics:
  {latency_p50_ms, latency_p95_ms}
"""

from __future__ import annotations

import json
import os
import random
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from loguru import logger

# Lazy imports — these are optional deps, only loaded when needed.
# This allows benchmark.py to import this module without requiring
# transformers/sklearn at import time.

DEFAULT_TEXT_CANDIDATES = [
    "prajjwal1/bert-tiny",
    "sentence-transformers/all-MiniLM-L6-v2",
    "distilbert-base-uncased",
]

DEFAULT_TABULAR_CANDIDATES = [
    "gradient_boosting",
    "random_forest",
    "logistic_regression",
]

@dataclass(frozen=True)
class TextSample:
    text: str
    label: str

@dataclass(frozen=True)
class TabularSample:
    features: Dict[str, float]
    label: str

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _samples_from_text_jsonl(labels_jsonl: Path) -> List[TextSample]:
    """Load JSONL with {text, label} or {text, labels} (multilabel uses first)."""
    rows = [line.strip() for line in labels_jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
    samples: List[TextSample] = []
    for line in rows:
        row = json.loads(line)
        text = str(row.get("text", "")).strip()
        if not text:
            continue
        label = str(row.get("label", "")).strip()
        if not label:
            # Try multilabel, take first
            labels_list = row.get("labels", [])
            if isinstance(labels_list, list) and labels_list:
                label = str(labels_list[0]).strip()
        if not label:
            continue
        samples.append(TextSample(text=text, label=label))
    return samples

def _samples_from_tabular_jsonl(labels_jsonl: Path) -> List[TabularSample]:
    """Load JSONL with {features: {key: value}, label}."""
    rows = [line.strip() for line in labels_jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
    samples: List[TabularSample] = []
    for line in rows:
        row = json.loads(line)
        features = row.get("features", {})
        if not isinstance(features, dict) or not features:
            continue
        label = str(row.get("label", "")).strip()
        if not label:
            continue
        # Coerce all feature values to float
        try:
            float_features = {k: float(v) for k, v in features.items()}
        except (ValueError, TypeError):
            continue
        samples.append(TabularSample(features=float_features, label=label))
    return samples

def _stratified_split_text(
    samples: Sequence[TextSample], val_ratio: float, seed: int
) -> Tuple[List[TextSample], List[TextSample]]:
    rng = random.Random(seed)
    by_label: Dict[str, List[TextSample]] = {}
    for sample in samples:
        by_label.setdefault(sample.label, []).append(sample)
    train: List[TextSample] = []
    val: List[TextSample] = []
    for label, items in sorted(by_label.items()):
        bucket = list(items)
        rng.shuffle(bucket)
        if len(bucket) <= 1:
            train.extend(bucket)
            continue
        n_val = max(1, int(round(len(bucket) * val_ratio)))
        n_val = min(n_val, len(bucket) - 1)
        val.extend(bucket[:n_val])
        train.extend(bucket[n_val:])
    rng.shuffle(train)
    rng.shuffle(val)
    if not val and len(train) > 1:
        val.append(train.pop())
    return train, val

def _stratified_split_tabular(
    samples: Sequence[TabularSample], val_ratio: float, seed: int
) -> Tuple[List[TabularSample], List[TabularSample]]:
    rng = random.Random(seed)
    by_label: Dict[str, List[TabularSample]] = {}
    for sample in samples:
        by_label.setdefault(sample.label, []).append(sample)
    train: List[TabularSample] = []
    val: List[TabularSample] = []
    for label, items in sorted(by_label.items()):
        bucket = list(items)
        rng.shuffle(bucket)
        if len(bucket) <= 1:
            train.extend(bucket)
            continue
        n_val = max(1, int(round(len(bucket) * val_ratio)))
        n_val = min(n_val, len(bucket) - 1)
        val.extend(bucket[:n_val])
        train.extend(bucket[n_val:])
    rng.shuffle(train)
    rng.shuffle(val)
    if not val and len(train) > 1:
        val.append(train.pop())
    return train, val

# ---------------------------------------------------------------------------
# Text benchmark (transformers)
# ---------------------------------------------------------------------------

def _macro_f1(preds: Sequence[int], labels: Sequence[int], num_classes: int) -> float:
    if not labels:
        return 0.0
    f1_values: List[float] = []
    for class_idx in range(num_classes):
        tp = sum(1 for p, l in zip(preds, labels) if p == class_idx and l == class_idx)
        fp = sum(1 for p, l in zip(preds, labels) if p == class_idx and l != class_idx)
        fn = sum(1 for p, l in zip(preds, labels) if p != class_idx and l == class_idx)
        denom = (2 * tp) + fp + fn
        f1_values.append(0.0 if denom == 0 else (2 * tp) / denom)
    return float(sum(f1_values) / max(1, len(f1_values)))

def _wilson_score_lower(accuracy: float, n: int, z: float = 2.576) -> float:
    """Wilson score confidence interval lower bound.

    Default z=2.576 gives 99% CI (safety-critical promotion decisions).
    Use z=1.96 for 95% CI.
    """
    if n == 0:
        return 0.0
    p = accuracy
    denom = 1 + z ** 2 / n
    center = (p + z ** 2 / (2 * n)) / denom
    spread = z * (p * (1 - p) / n + z ** 2 / (4 * n ** 2)) ** 0.5 / denom
    return float(center - spread)

class _TextDataset:
    """Tokenizer-based dataset for text classification benchmarking."""

    def __init__(
        self,
        samples: Sequence[TextSample],
        tokenizer: Any,
        label_to_idx: Dict[str, int],
        max_length: int = 256,
    ) -> None:
        self.samples = list(samples)
        self.tokenizer = tokenizer
        self.label_to_idx = label_to_idx
        self.max_length = max_length

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> Dict[str, Any]:
        import torch

        sample = self.samples[idx]
        encoding = self.tokenizer(
            sample.text,
            truncation=True,
            max_length=self.max_length,
            padding="max_length",
            return_tensors="pt",
        )
        label_tensor = torch.tensor(
            self.label_to_idx.get(sample.label, 0),
            dtype=torch.long,
        )
        return {
            "input_ids": encoding["input_ids"].squeeze(0),
            "attention_mask": encoding["attention_mask"].squeeze(0),
            "labels": label_tensor,
        }

def benchmark_latency(
    model: Any,
    tokenizer: Any,
    device: str,
    sample_texts: List[str],
    n_warmup: int = 10,
    n_iterations: int = 100,
) -> Dict[str, float]:
    """Benchmark model inference latency."""
    import numpy as np
    import torch

    model.eval()
    inputs_list = []
    for text in sample_texts[:5]:
        inputs = tokenizer(
            text, truncation=True, max_length=256, return_tensors="pt",
        ).to(device)
        inputs_list.append(inputs)

    if not inputs_list:
        return {"latency_mean_ms": 0.0, "latency_p50_ms": 0.0, "latency_p95_ms": 0.0}

    with torch.no_grad():
        for _ in range(n_warmup):
            for inputs in inputs_list:
                model(**inputs)

    if device == "cuda":
        torch.cuda.synchronize()

    latencies: List[float] = []
    with torch.no_grad():
        for i in range(n_iterations):
            inputs = inputs_list[i % len(inputs_list)]
            start = time.perf_counter()
            model(**inputs)
            if device == "cuda":
                torch.cuda.synchronize()
            latencies.append((time.perf_counter() - start) * 1000)

    return {
        "latency_mean_ms": float(np.mean(latencies)),
        "latency_p50_ms": float(np.percentile(latencies, 50)),
        "latency_p95_ms": float(np.percentile(latencies, 95)),
    }

def _detect_imbalance(
    train_samples: Sequence[TextSample],
    label_to_idx: Dict[str, int],
) -> Dict[str, Any]:
    """Detect class imbalance and return distribution info.

    Returns dict with label_counts, imbalance_ratio, and is_imbalanced flag.
    Warns at >20:1 ratio (same threshold as multilabel_benchmark.py).
    """
    label_counts = Counter(s.label for s in train_samples)
    idx_to_label = {v: k for k, v in label_to_idx.items()}
    num_classes = len(label_to_idx)

    counts_ordered = [label_counts.get(idx_to_label.get(i, ""), 0) for i in range(num_classes)]
    max_count = max(counts_ordered) if counts_ordered else 1
    min_count = max(min(counts_ordered), 1) if counts_ordered else 1
    imbalance_ratio = max_count / min_count

    logger.info("Class distribution ({} classes, {} samples):", num_classes, len(train_samples))
    for label in sorted(label_counts, key=label_counts.get, reverse=True):
        pct = 100.0 * label_counts[label] / len(train_samples)
        logger.info("  {:>20s}: {:>6d} ({:5.1f}%)", label, label_counts[label], pct)

    if imbalance_ratio > 20:
        logger.warning(
            "⚠ CLASS IMBALANCE DETECTED: {:.0f}:1 ratio (max={}, min={}). "
            "Applying class-weighted loss.",
            imbalance_ratio, max_count, min_count,
        )

    return {
        "label_counts": dict(label_counts),
        "counts_ordered": counts_ordered,
        "imbalance_ratio": imbalance_ratio,
        "is_imbalanced": imbalance_ratio > 5,
    }

def _benchmark_text_backbone(
    *,
    backbone: str,
    train_samples: Sequence[TextSample],
    val_samples: Sequence[TextSample],
    label_to_idx: Dict[str, int],
    device: str,
    batch_size: int,
    epochs: int,
    max_steps: int,
    max_length: int,
    seed: int,
    lr: float,
    weight_decay: float,
    label_smoothing: float,
    dropout: float,
) -> Dict[str, Any]:
    """Train and evaluate a single text backbone."""
    import torch
    from torch.utils.data import DataLoader
    from transformers import (
        AutoConfig,
        AutoModelForSequenceClassification,
        AutoTokenizer,
        get_linear_schedule_with_warmup,
    )

    torch.manual_seed(seed)
    num_classes = len(label_to_idx)

    # --- Class imbalance detection (ported from multilabel_benchmark.py) ---
    imbalance_info = _detect_imbalance(train_samples, label_to_idx)

    # Compute class weights for CrossEntropyLoss when imbalanced
    class_weight = None
    if imbalance_info["is_imbalanced"]:
        n_total = len(train_samples)
        counts = torch.tensor(imbalance_info["counts_ordered"], dtype=torch.float32)
        # Inverse frequency, clamped to [1, 50] — same range as multilabel pos_weight
        class_weight = torch.clamp(n_total / (num_classes * counts.clamp(min=1)), min=1.0, max=50.0).to(device)
        logger.info("Class weights: {}", {
            k: f"{class_weight[v].item():.2f}" for k, v in label_to_idx.items()
        })

    tokenizer = AutoTokenizer.from_pretrained(backbone)
    train_dataset = _TextDataset(train_samples, tokenizer, label_to_idx, max_length=max_length)
    val_dataset = _TextDataset(val_samples, tokenizer, label_to_idx, max_length=max_length)

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)

    config = AutoConfig.from_pretrained(backbone, num_labels=num_classes)
    setattr(config, "hidden_dropout_prob", max(0.0, min(dropout, 0.9)))
    setattr(config, "attention_probs_dropout_prob", max(0.0, min(dropout, 0.9)))
    setattr(config, "classifier_dropout", max(0.0, min(dropout, 0.9)))
    model = AutoModelForSequenceClassification.from_pretrained(
        backbone, config=config,
    ).to(device)

    criterion = torch.nn.CrossEntropyLoss(
        weight=class_weight,
        label_smoothing=max(label_smoothing, 0.0),
    )
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=max(lr, 1e-8),
        weight_decay=max(weight_decay, 0.0),
    )
    total_steps = len(train_loader) * max(1, epochs)
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=int(total_steps * 0.1),
        num_training_steps=total_steps,
    )

    # --- Early stopping state (ported from multilabel_benchmark.py) ---
    best_val_loss = float("inf")
    val_patience = 0
    max_val_patience = 2
    early_stopped = False
    steps_per_epoch = len(train_loader)
    val_interval = min(steps_per_epoch, 2000)

    step = 0
    model.train()
    for _epoch in range(max(1, epochs)):
        for batch in train_loader:
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels = batch["labels"].to(device)

            optimizer.zero_grad()
            outputs = model(input_ids=input_ids, attention_mask=attention_mask)
            loss = criterion(outputs.logits, labels)
            loss.backward()
            optimizer.step()
            scheduler.step()
            step += 1

            # Periodic validation for early stopping (after 10% warmup)
            if step % val_interval == 0 and step > int(total_steps * 0.1):
                model.eval()
                val_loss_accum = 0.0
                val_count = 0
                with torch.no_grad():
                    for vb in val_loader:
                        vi = vb["input_ids"].to(device)
                        va = vb["attention_mask"].to(device)
                        vl = vb["labels"].to(device)
                        vo = model(input_ids=vi, attention_mask=va)
                        val_loss_accum += criterion(vo.logits, vl).item() * len(vl)
                        val_count += len(vl)
                cur_val_loss = val_loss_accum / max(val_count, 1)
                if cur_val_loss < best_val_loss:
                    best_val_loss = cur_val_loss
                    val_patience = 0
                else:
                    val_patience += 1
                    if val_patience >= max_val_patience:
                        logger.info("Early stopping at step {} (val_loss={:.4f}, best={:.4f})", step, cur_val_loss, best_val_loss)
                        early_stopped = True
                model.train()

            if step >= max_steps or early_stopped:
                break
        if step >= max_steps or early_stopped:
            break

    # Evaluate
    model.eval()
    all_preds: List[int] = []
    all_labels: List[int] = []
    with torch.no_grad():
        for batch in val_loader:
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels = batch["labels"].to(device)
            outputs = model(input_ids=input_ids, attention_mask=attention_mask)
            predicted = torch.argmax(outputs.logits, dim=1)
            all_preds.extend(predicted.cpu().tolist())
            all_labels.extend(labels.cpu().tolist())

    if not all_labels:
        accuracy = 0.0
        f1 = 0.0
    else:
        correct = sum(1 for p, l in zip(all_preds, all_labels) if p == l)
        accuracy = float(correct / len(all_labels))
        f1 = _macro_f1(all_preds, all_labels, num_classes)

    # Latency benchmark
    sample_texts = [s.text for s in val_samples[:10]]
    latency = benchmark_latency(model, tokenizer, device, sample_texts)

    n_total = len(train_samples) + len(val_samples)
    return {
        "backbone": backbone,
        "status": "ok",
        "accuracy": accuracy,
        "macro_f1": f1,
        "wilson_score_lower": _wilson_score_lower(accuracy, n_total),
        "latency_p50_ms": latency["latency_p50_ms"],
        "latency_p95_ms": latency["latency_p95_ms"],
        "train_samples": len(train_samples),
        "val_samples": len(val_samples),
        "num_classes": num_classes,
        "steps": step,
        "_hf_model": model,
        "_hf_tokenizer": tokenizer,
        "_label_map": {v: k for k, v in label_to_idx.items()},
    }

# ---------------------------------------------------------------------------
# Tabular benchmark (sklearn)
# ---------------------------------------------------------------------------

def _benchmark_tabular_backbone(
    *,
    backbone: str,
    train_samples: Sequence[TabularSample],
    val_samples: Sequence[TabularSample],
    label_to_idx: Dict[str, int],
    seed: int,
) -> Dict[str, Any]:
    """Fit and evaluate a single sklearn tabular model."""
    import numpy as np
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression

    num_classes = len(label_to_idx)

    # Build feature matrix — use sorted union of all feature keys
    all_keys = sorted({k for s in list(train_samples) + list(val_samples) for k in s.features})
    if not all_keys:
        return {
            "backbone": backbone, "status": "failed", "error": "no_features",
            "accuracy": 0.0, "macro_f1": 0.0,
        }

    def to_array(samples: Sequence[TabularSample]) -> Tuple[Any, Any]:
        X = np.array([[s.features.get(k, 0.0) for k in all_keys] for s in samples])
        y = np.array([label_to_idx.get(s.label, 0) for s in samples])
        return X, y

    X_train, y_train = to_array(train_samples)
    X_val, y_val = to_array(val_samples)

    model_map = {
        "gradient_boosting": lambda: GradientBoostingClassifier(
            n_estimators=100, max_depth=5, random_state=seed,
        ),
        "random_forest": lambda: RandomForestClassifier(
            n_estimators=100, max_depth=10, random_state=seed,
            class_weight="balanced",
        ),
        "logistic_regression": lambda: LogisticRegression(
            max_iter=500, random_state=seed,
            class_weight="balanced",
        ),
    }

    factory = model_map.get(backbone)
    if factory is None:
        return {
            "backbone": backbone, "status": "failed",
            "error": f"unknown tabular backbone: {backbone}",
            "accuracy": 0.0, "macro_f1": 0.0,
        }

    clf = factory()
    clf.fit(X_train, y_train)
    preds = clf.predict(X_val).tolist()
    labels = y_val.tolist()

    correct = sum(1 for p, l in zip(preds, labels) if p == l)
    accuracy = float(correct / len(labels)) if labels else 0.0
    f1 = _macro_f1(preds, labels, num_classes)
    n_total = len(train_samples) + len(val_samples)

    return {
        "backbone": backbone,
        "status": "ok",
        "accuracy": accuracy,
        "macro_f1": f1,
        "wilson_score_lower": _wilson_score_lower(accuracy, n_total),
        "train_samples": len(train_samples),
        "val_samples": len(val_samples),
        "num_classes": num_classes,
        "feature_count": len(all_keys),
        "_model": clf,
        "_feature_order": all_keys,
        "_label_to_idx": label_to_idx,
    }

# ---------------------------------------------------------------------------
# Orchestrators
# ---------------------------------------------------------------------------

def run_text_benchmark(
    *,
    labels_jsonl: Path,
    backbones: Sequence[str],
    device: str = "cpu",
    batch_size: int = 16,
    epochs: int = 1,
    max_steps: int = 250,
    max_length: int = 256,
    val_ratio: float = 0.15,
    seed: int = 42,
    lr: float = 2e-5,
    weight_decay: float = 0.01,
    label_smoothing: float = 0.0,
    dropout: float = 0.1,
    train_jsonl: Optional[Path] = None,
    val_jsonl: Optional[Path] = None,
    output_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Benchmark text classification backbones.

    If train_jsonl and val_jsonl are provided, use them directly.
    Otherwise, split labels_jsonl into train/val.

    Returns the same output contract as vision run_benchmark().
    """
    if train_jsonl is not None and val_jsonl is not None:
        train_samples = _samples_from_text_jsonl(train_jsonl)
        val_samples = _samples_from_text_jsonl(val_jsonl)
        source = {"mode": "jsonl", "train_jsonl": str(train_jsonl), "val_jsonl": str(val_jsonl)}
    else:
        all_samples = _samples_from_text_jsonl(labels_jsonl)
        train_samples, val_samples = _stratified_split_text(all_samples, val_ratio=val_ratio, seed=seed)
        source = {"mode": "jsonl", "labels_jsonl": str(labels_jsonl)}

    if not train_samples or not val_samples:
        return {
            "status": "failed",
            "reason": "insufficient_data",
            "selected_backbone": None,
            "source": source,
            "results": [],
        }

    labels = sorted({s.label for s in train_samples + val_samples})
    label_to_idx = {label: idx for idx, label in enumerate(labels)}

    # Pre-training class distribution report
    _detect_imbalance(train_samples, label_to_idx)

    results: List[Dict[str, Any]] = []

    for backbone in backbones:
        try:
            result = _benchmark_text_backbone(
                backbone=backbone,
                train_samples=train_samples,
                val_samples=val_samples,
                label_to_idx=label_to_idx,
                device=device,
                batch_size=batch_size,
                epochs=epochs,
                max_steps=max_steps,
                max_length=max_length,
                seed=seed,
                lr=lr,
                weight_decay=weight_decay,
                label_smoothing=label_smoothing,
                dropout=dropout,
            )
            logger.info(
                "benchmark backbone={} macro_f1={:.4f} accuracy={:.4f} latency_p50={:.2f}ms",
                backbone, result["macro_f1"], result["accuracy"], result.get("latency_p50_ms", 0.0),
            )
        except Exception as exc:
            result = {
                "backbone": backbone, "status": "failed", "error": str(exc),
                "accuracy": 0.0, "macro_f1": 0.0,
            }
            logger.warning("benchmark failed backbone={} error={}", backbone, exc)
        results.append(result)

    viable = [r for r in results if r.get("status") == "ok"]
    if not viable:
        return {
            "status": "failed",
            "reason": "no_viable_backbone",
            "selected_backbone": None,
            "source": source,
            "results": results,
        }

    winner = sorted(
        viable,
        key=lambda row: (float(row.get("macro_f1", 0.0)), float(row.get("accuracy", 0.0))),
        reverse=True,
    )[0]

    selected_metrics: Dict[str, Any] = {
        "macro_f1": float(winner.get("macro_f1", 0.0)),
        "accuracy": float(winner.get("accuracy", 0.0)),
        "wilson_score_lower": float(winner.get("wilson_score_lower", 0.0)),
    }
    if "latency_p50_ms" in winner:
        selected_metrics["latency_p50_ms"] = float(winner["latency_p50_ms"])
    if "latency_p95_ms" in winner:
        selected_metrics["latency_p95_ms"] = float(winner["latency_p95_ms"])

    # Save HuggingFace transformer model when output_dir specified
    if output_dir is not None and winner.get("_hf_model") is not None:
        import json as _json
        output_dir.mkdir(parents=True, exist_ok=True)
        winner["_hf_model"].save_pretrained(output_dir)
        winner["_hf_tokenizer"].save_pretrained(output_dir)
        (output_dir / "label_map.json").write_text(_json.dumps(winner.get("_label_map", {}), indent=2))
        (output_dir / "metrics.json").write_text(_json.dumps({
            k: selected_metrics.get(k, winner.get(k, 0)) for k in
            ["macro_f1", "accuracy", "wilson_score_lower", "latency_p50_ms", "num_classes", "train_samples"]
        } | {"backbone": winner["backbone"]}, indent=2))
        logger.info("Saved HuggingFace model to {}", output_dir)
    for r in results:
        for k in ("_hf_model", "_hf_tokenizer", "_label_map"):
            r.pop(k, None)

    return {
        "status": "ok",
        "selected_backbone": winner["backbone"],
        "selected_metrics": selected_metrics,
        "source": source,
        "results": results,
    }

def run_tabular_benchmark(
    *,
    labels_jsonl: Path,
    backbones: Sequence[str],
    val_ratio: float = 0.15,
    seed: int = 42,
    train_jsonl: Optional[Path] = None,
    val_jsonl: Optional[Path] = None,
    output_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Benchmark tabular classification backbones (sklearn).

    Returns the same output contract as vision run_benchmark().
    """
    if train_jsonl is not None and val_jsonl is not None:
        train_samples = _samples_from_tabular_jsonl(train_jsonl)
        val_samples = _samples_from_tabular_jsonl(val_jsonl)
        source = {"mode": "jsonl", "train_jsonl": str(train_jsonl), "val_jsonl": str(val_jsonl)}
    else:
        all_samples = _samples_from_tabular_jsonl(labels_jsonl)
        train_samples, val_samples = _stratified_split_tabular(all_samples, val_ratio=val_ratio, seed=seed)
        source = {"mode": "jsonl", "labels_jsonl": str(labels_jsonl)}

    if not train_samples or not val_samples:
        return {
            "status": "failed",
            "reason": "insufficient_data",
            "selected_backbone": None,
            "source": source,
            "results": [],
        }

    labels = sorted({s.label for s in list(train_samples) + list(val_samples)})
    label_to_idx = {label: idx for idx, label in enumerate(labels)}
    results: List[Dict[str, Any]] = []

    for backbone in backbones:
        try:
            result = _benchmark_tabular_backbone(
                backbone=backbone,
                train_samples=train_samples,
                val_samples=val_samples,
                label_to_idx=label_to_idx,
                seed=seed,
            )
            logger.info(
                "benchmark backbone={} macro_f1={:.4f} accuracy={:.4f}",
                backbone, result["macro_f1"], result["accuracy"],
            )
        except Exception as exc:
            result = {
                "backbone": backbone, "status": "failed", "error": str(exc),
                "accuracy": 0.0, "macro_f1": 0.0,
            }
            logger.warning("benchmark failed backbone={} error={}", backbone, exc)
        results.append(result)

    viable = [r for r in results if r.get("status") == "ok"]
    if not viable:
        return {
            "status": "failed",
            "reason": "no_viable_backbone",
            "selected_backbone": None,
            "source": source,
            "results": results,
        }

    winner = sorted(
        viable,
        key=lambda row: (float(row.get("macro_f1", 0.0)), float(row.get("accuracy", 0.0))),
        reverse=True,
    )[0]

    # Save winning model as joblib if output_dir is specified
    model_path = None
    if output_dir is not None and winner.get("_model") is not None:
        import joblib
        import sklearn

        output_dir.mkdir(parents=True, exist_ok=True)

        # Save fitted sklearn model
        model_file = output_dir / "model.joblib"
        joblib.dump(winner["_model"], model_file)

        # Save label encoder (idx→label reverse mapping)
        idx_to_label = {v: k for k, v in winner["_label_to_idx"].items()}
        label_encoder_file = output_dir / "label_encoder.joblib"
        joblib.dump(idx_to_label, label_encoder_file)

        # Save metrics + feature order for deployment
        import json as _json

        metrics_file = output_dir / "metrics.json"
        metrics_file.write_text(_json.dumps({
            "accuracy": float(winner.get("accuracy", 0.0)),
            "macro_f1": float(winner.get("macro_f1", 0.0)),
            "wilson_score_lower": float(winner.get("wilson_score_lower", 0.0)),
            "n_samples": winner.get("train_samples", 0) + winner.get("val_samples", 0),
            "n_classes": winner.get("num_classes", 0),
            "best_model": winner["backbone"],
            "sklearn_version": sklearn.__version__,
            "n_features": winner.get("feature_count", 0),
            "feature_order": winner.get("_feature_order", []),
        }, indent=2))

        model_path = str(model_file)
        logger.info(
            "saved winning tabular model to {} (backbone={}, f1={:.4f})",
            model_file, winner["backbone"], float(winner.get("macro_f1", 0.0)),
        )

    # Strip internal keys before returning
    for r in results:
        r.pop("_model", None)
        r.pop("_feature_order", None)
        r.pop("_label_to_idx", None)

    return {
        "status": "ok",
        "selected_backbone": winner["backbone"],
        "selected_metrics": {
            "macro_f1": float(winner.get("macro_f1", 0.0)),
            "accuracy": float(winner.get("accuracy", 0.0)),
            "wilson_score_lower": float(winner.get("wilson_score_lower", 0.0)),
        },
        **({"model_path": model_path} if model_path else {}),
        "source": source,
        "results": results,
    }
