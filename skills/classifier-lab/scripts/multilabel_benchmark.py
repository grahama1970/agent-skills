#!/usr/bin/env python3
"""
Multi-label text benchmark engine for classifier-lab.

Separated from text_benchmark.py to stay under 800-line limit.
Uses BCEWithLogitsLoss + sigmoid for true multi-label classification
where each sample can have multiple labels simultaneously.

Output contract matches text_benchmark.py with added multilabel fields.
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from loguru import logger

from text_benchmark import _wilson_score_lower, benchmark_latency


@dataclass(frozen=True)
class MultiLabelTextSample:
    text: str
    labels: Tuple[str, ...]


def detect_multilabel(labels_jsonl: Path) -> bool:
    """Check if JSONL uses multi-label format (has 'labels' list field)."""
    for line in labels_jsonl.read_text(encoding="utf-8").splitlines()[:10]:
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if "labels" in row and isinstance(row["labels"], list):
            return True
        if "label" in row:
            return False
    return False


def samples_from_jsonl(
    labels_jsonl: Path,
) -> Tuple[List[MultiLabelTextSample], List[str]]:
    """Load JSONL with {text, labels: [...]} for multi-label classification.

    Returns (samples, all_labels) where all_labels is sorted unique labels.
    """
    rows = [
        line.strip()
        for line in labels_jsonl.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    samples: List[MultiLabelTextSample] = []
    all_labels_set: set = set()
    for line in rows:
        row = json.loads(line)
        text = str(row.get("text", "")).strip()
        if not text:
            continue
        labels_list = row.get("labels", [])
        if not isinstance(labels_list, list) or not labels_list:
            continue
        labels_clean = tuple(
            str(lbl).strip() for lbl in labels_list if str(lbl).strip()
        )
        if not labels_clean:
            continue
        all_labels_set.update(labels_clean)
        samples.append(MultiLabelTextSample(text=text, labels=labels_clean))
    return samples, sorted(all_labels_set)


def stratified_split(
    samples: Sequence[MultiLabelTextSample], val_ratio: float, seed: int
) -> Tuple[List[MultiLabelTextSample], List[MultiLabelTextSample]]:
    """Split multi-label samples, stratifying by rarest label per sample."""
    rng = random.Random(seed)
    # Assign each sample to a bucket by its rarest label
    label_counts: Dict[str, int] = {}
    for s in samples:
        for lbl in s.labels:
            label_counts[lbl] = label_counts.get(lbl, 0) + 1

    by_rarest: Dict[str, List[MultiLabelTextSample]] = {}
    for s in samples:
        rarest = min(s.labels, key=lambda lbl: label_counts.get(lbl, 0))
        by_rarest.setdefault(rarest, []).append(s)

    train: List[MultiLabelTextSample] = []
    val: List[MultiLabelTextSample] = []
    for label, items in sorted(by_rarest.items()):
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


class _MultiLabelTextDataset:
    """Pre-tokenized dataset for multi-label text classification.

    Tokenizes the entire dataset once in __init__ to avoid repeated
    tokenization in __getitem__ (which was the primary training bottleneck
    when on-the-fly tokenization dominated GPU idle time).
    """

    def __init__(
        self,
        samples: Sequence[MultiLabelTextSample],
        tokenizer: Any,
        label_to_idx: Dict[str, int],
        max_length: int = 256,
    ) -> None:
        import torch

        self.num_labels = len(label_to_idx)
        n = len(samples)
        logger.info("Pre-tokenizing {} samples (max_length={})...", n, max_length)
        t0 = time.time()

        # Batch-tokenize all texts at once (much faster than per-sample)
        all_texts = [s.text for s in samples]
        encodings = tokenizer(
            all_texts,
            truncation=True,
            max_length=max_length,
            padding="max_length",
            return_tensors="pt",
        )
        self.input_ids = encodings["input_ids"]  # (n, max_length)
        self.attention_mask = encodings["attention_mask"]  # (n, max_length)

        # Pre-compute label vectors
        self.label_vectors = torch.zeros(n, self.num_labels, dtype=torch.float)
        for i, sample in enumerate(samples):
            for lbl in sample.labels:
                if lbl in label_to_idx:
                    self.label_vectors[i, label_to_idx[lbl]] = 1.0

        elapsed = time.time() - t0
        logger.info("Pre-tokenization done in {:.1f}s ({:.0f} samples/sec)", elapsed, n / max(elapsed, 0.001))

    def __len__(self) -> int:
        return self.input_ids.size(0)

    def __getitem__(self, idx: int) -> Dict[str, Any]:
        return {
            "input_ids": self.input_ids[idx],
            "attention_mask": self.attention_mask[idx],
            "labels": self.label_vectors[idx],
        }


def _multilabel_macro_f1(
    all_preds: List[List[int]],
    all_labels: List[List[int]],
    num_classes: int,
) -> Tuple[float, Dict[str, float]]:
    """Compute per-label and macro F1 for multi-label classification."""
    per_class: Dict[str, float] = {}
    f1_values: List[float] = []
    for c in range(num_classes):
        tp = sum(
            1
            for preds, labels in zip(all_preds, all_labels)
            if c in preds and c in labels
        )
        fp = sum(
            1
            for preds, labels in zip(all_preds, all_labels)
            if c in preds and c not in labels
        )
        fn = sum(
            1
            for preds, labels in zip(all_preds, all_labels)
            if c not in preds and c in labels
        )
        denom = (2 * tp) + fp + fn
        f1 = 0.0 if denom == 0 else (2 * tp) / denom
        f1_values.append(f1)
        per_class[str(c)] = f1
    macro = float(sum(f1_values) / max(1, len(f1_values)))
    return macro, per_class


def benchmark_backbone(
    *,
    backbone: str,
    train_samples: Sequence[MultiLabelTextSample],
    val_samples: Sequence[MultiLabelTextSample],
    label_to_idx: Dict[str, int],
    device: str,
    batch_size: int,
    epochs: int,
    max_steps: int,
    max_length: int,
    seed: int,
) -> Dict[str, Any]:
    """Train and evaluate a text backbone for multi-label classification."""
    import torch
    from torch.utils.data import DataLoader
    from transformers import (
        AutoModelForSequenceClassification,
        AutoTokenizer,
        get_linear_schedule_with_warmup,
    )

    torch.manual_seed(seed)
    num_classes = len(label_to_idx)
    idx_to_label = {v: k for k, v in label_to_idx.items()}

    tokenizer = AutoTokenizer.from_pretrained(backbone)
    train_dataset = _MultiLabelTextDataset(
        train_samples, tokenizer, label_to_idx, max_length=max_length
    )
    val_dataset = _MultiLabelTextDataset(
        val_samples, tokenizer, label_to_idx, max_length=max_length
    )

    train_loader = DataLoader(
        train_dataset, batch_size=batch_size, shuffle=True
    )
    val_loader = DataLoader(
        val_dataset, batch_size=batch_size, shuffle=False
    )

    model = AutoModelForSequenceClassification.from_pretrained(
        backbone,
        num_labels=num_classes,
        problem_type="multi_label_classification",
    ).to(device)

    # Compute pos_weight for class-weighted BCE (handles imbalanced rare classes)
    n_train = len(train_samples)
    label_pos_counts = torch.zeros(num_classes)
    for s in train_samples:
        for lbl in s.labels:
            if lbl in label_to_idx:
                label_pos_counts[label_to_idx[lbl]] += 1
    # pos_weight = n_neg / n_pos, clamped to [1, 50] to boost rare classes
    pos_weight = torch.clamp(
        (n_train - label_pos_counts) / label_pos_counts.clamp(min=1),
        min=1.0,
        max=50.0,
    ).to(device)
    logger.info("pos_weight per class: {}", {idx_to_label[i]: f"{pos_weight[i]:.1f}" for i in range(num_classes)})

    # Use focal loss if FOCAL_GAMMA env var is set (default: standard BCE)
    import os
    focal_gamma = float(os.environ.get("FOCAL_GAMMA", "0"))
    if focal_gamma > 0:
        logger.info("Using focal loss with gamma={}", focal_gamma)
        class FocalBCEWithLogitsLoss(torch.nn.Module):
            def __init__(self, gamma: float, pos_weight: torch.Tensor):
                super().__init__()
                self.gamma = gamma
                self.pos_weight = pos_weight

            def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
                # Standard BCE components
                p = torch.sigmoid(logits)
                # Focal modulating factor: (1-p_t)^gamma
                p_t = targets * p + (1 - targets) * (1 - p)
                focal_weight = (1 - p_t) ** self.gamma
                # Weighted BCE
                bce = torch.nn.functional.binary_cross_entropy_with_logits(
                    logits, targets, reduction="none"
                )
                # Apply pos_weight manually for positive class
                weight = targets * self.pos_weight.unsqueeze(0) + (1 - targets)
                loss = focal_weight * weight * bce
                return loss.mean()

        criterion = FocalBCEWithLogitsLoss(gamma=focal_gamma, pos_weight=pos_weight)
    else:
        criterion = torch.nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=2e-5, weight_decay=0.01
    )
    total_steps = len(train_loader) * max(1, epochs)
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=int(total_steps * 0.1),
        num_training_steps=total_steps,
    )

    # TensorBoard logging (optional, no-op if torch.utils.tensorboard unavailable)
    tb_writer = None
    try:
        from torch.utils.tensorboard import SummaryWriter
        import tempfile
        tb_dir = Path(tempfile.gettempdir()) / "classifier_lab_tb" / backbone.replace("/", "_")
        tb_writer = SummaryWriter(log_dir=str(tb_dir))
        logger.info("TensorBoard logging to {}", tb_dir)
    except ImportError:
        pass

    step = 0
    log_interval = max(1, total_steps // 50)  # ~50 log points per run
    # Validate every epoch or every 2000 steps (whichever is smaller)
    steps_per_epoch = len(train_loader)
    val_interval = min(steps_per_epoch, 2000)
    best_val_loss = float("inf")
    val_patience = 0
    max_val_patience = 2  # Stop if val loss increases 2 consecutive checks
    early_stopped = False

    model.train()
    for epoch_num in range(max(1, epochs)):
        epoch_loss = 0.0
        epoch_batches = 0
        for batch in train_loader:
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels = batch["labels"].to(device)

            optimizer.zero_grad()
            outputs = model(
                input_ids=input_ids, attention_mask=attention_mask
            )
            loss = criterion(outputs.logits, labels)
            loss.backward()
            optimizer.step()
            scheduler.step()
            step += 1
            epoch_loss += loss.item()
            epoch_batches += 1

            if step % log_interval == 0:
                avg_loss = epoch_loss / max(1, epoch_batches)
                lr = scheduler.get_last_lr()[0]
                logger.info(
                    "step={}/{} epoch={} loss={:.4f} lr={:.2e}",
                    step, max_steps, epoch_num + 1, avg_loss, lr,
                )
                if tb_writer:
                    tb_writer.add_scalar("train/loss", avg_loss, step)
                    tb_writer.add_scalar("train/lr", lr, step)
                    tb_writer.flush()

            # Validation loss check for early stopping
            if step % val_interval == 0 and step > int(total_steps * 0.1):
                model.eval()
                val_loss_total = 0.0
                val_batches = 0
                with torch.no_grad():
                    for vb in val_loader:
                        vi = vb["input_ids"].to(device)
                        va = vb["attention_mask"].to(device)
                        vl = vb["labels"].to(device)
                        vo = model(input_ids=vi, attention_mask=va)
                        vl_loss = criterion(vo.logits, vl)
                        val_loss_total += vl_loss.item()
                        val_batches += 1
                avg_val_loss = val_loss_total / max(1, val_batches)
                logger.info(
                    "step={} val_loss={:.4f} best_val_loss={:.4f}",
                    step, avg_val_loss, best_val_loss,
                )
                if tb_writer:
                    tb_writer.add_scalar("val/loss", avg_val_loss, step)
                    tb_writer.flush()
                if avg_val_loss < best_val_loss:
                    best_val_loss = avg_val_loss
                    val_patience = 0
                else:
                    val_patience += 1
                    logger.warning(
                        "val_loss not improving ({:.4f} >= {:.4f}), patience={}/{}",
                        avg_val_loss, best_val_loss, val_patience, max_val_patience,
                    )
                    if val_patience >= max_val_patience:
                        logger.warning("EARLY STOPPING at step {} (val loss not improving)", step)
                        early_stopped = True
                model.train()

            if step >= max_steps or early_stopped:
                break
        if step >= max_steps or early_stopped:
            break

    if tb_writer:
        try:
            tb_writer.close()
        except Exception:
            pass

    # Collect raw probabilities for per-class threshold optimization
    # IMPORTANT: Split val into tune/test halves to prevent threshold leakage.
    # Thresholds are optimized on tune_half; final metrics reported on test_half.
    model.eval()
    all_probs_list: List[List[float]] = []
    all_labels_list: List[List[int]] = []
    with torch.no_grad():
        for batch in val_loader:
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels = batch["labels"].to(device)
            outputs = model(
                input_ids=input_ids, attention_mask=attention_mask
            )
            probs = torch.sigmoid(outputs.logits)
            for i in range(probs.size(0)):
                all_probs_list.append(probs[i].cpu().tolist())
                label_indices = (
                    labels[i].nonzero(as_tuple=True)[0].cpu().tolist()
                )
                all_labels_list.append(label_indices)

    import numpy as np

    # Split val into tune_half (threshold optimization) and test_half (final metrics)
    n_val = len(all_probs_list)
    midpoint = n_val // 2
    # Shuffle with fixed seed for reproducibility before splitting
    indices = list(range(n_val))
    rng = np.random.RandomState(42)
    rng.shuffle(indices)
    tune_indices = indices[:midpoint]
    test_indices = indices[midpoint:]

    tune_probs = [all_probs_list[i] for i in tune_indices]
    tune_labels = [all_labels_list[i] for i in tune_indices]
    test_probs = [all_probs_list[i] for i in test_indices]
    test_labels = [all_labels_list[i] for i in test_indices]

    # Per-class threshold optimization on tune_half ONLY
    tune_probs_array = np.array(tune_probs)  # (n_tune, n_classes)
    best_thresholds = []
    for c in range(num_classes):
        true_c = np.array([1 if c in labels else 0 for labels in tune_labels])
        best_f1, best_t = 0.0, 0.5
        for t in np.arange(0.15, 0.85, 0.05):
            pred_c = (tune_probs_array[:, c] >= t).astype(int)
            tp = int(np.sum(pred_c * true_c))
            fp = int(np.sum(pred_c * (1 - true_c)))
            fn = int(np.sum((1 - pred_c) * true_c))
            denom = (2 * tp) + fp + fn
            f1 = 0.0 if denom == 0 else (2 * tp) / denom
            if f1 > best_f1:
                best_f1, best_t = f1, t
        best_thresholds.append(best_t)
    logger.info("optimized thresholds (on tune_half, n={}): {}", len(tune_probs), {idx_to_label[i]: f"{best_thresholds[i]:.2f}" for i in range(num_classes)})

    # Apply optimized thresholds to HELD-OUT test_half for unbiased metrics
    all_preds: List[List[int]] = []
    for row_probs in test_probs:
        pred_indices = [
            c for c in range(num_classes)
            if row_probs[c] >= best_thresholds[c]
        ]
        all_preds.append(pred_indices)

    macro_f1, per_class_f1 = _multilabel_macro_f1(
        all_preds, test_labels, num_classes
    )
    # Also compute tune_half F1 for comparison (expect this to be higher)
    tune_preds: List[List[int]] = []
    for row_probs in tune_probs:
        tune_preds.append([c for c in range(num_classes) if row_probs[c] >= best_thresholds[c]])
    tune_f1, _ = _multilabel_macro_f1(tune_preds, tune_labels, num_classes)
    logger.info("tune_half F1: {:.4f}, test_half F1: {:.4f} (gap: {:.4f})", tune_f1, macro_f1, tune_f1 - macro_f1)

    # Subset accuracy: predicted set == true set (on held-out test_half)
    exact_match = sum(
        1
        for p, l in zip(all_preds, test_labels)
        if set(p) == set(l)
    )
    accuracy = float(exact_match / max(1, len(all_preds)))

    per_label_f1 = {
        idx_to_label.get(int(k), k): v for k, v in per_class_f1.items()
    }

    sample_texts = [s.text for s in val_samples[:10]]
    latency = benchmark_latency(model, tokenizer, device, sample_texts)

    n_total = len(train_samples) + len(val_samples)

    # Save model + tokenizer + thresholds for deployment
    import tempfile
    save_dir = Path(tempfile.mkdtemp(prefix=f"multilabel_{backbone.replace('/', '_')}_"))
    model.save_pretrained(save_dir)
    tokenizer.save_pretrained(save_dir)
    thresholds_dict = {idx_to_label[i]: float(best_thresholds[i]) for i in range(num_classes)}
    (save_dir / "thresholds.json").write_text(json.dumps(thresholds_dict, indent=2))
    (save_dir / "label_map.json").write_text(json.dumps(idx_to_label, indent=2))
    logger.info("saved multilabel model to {}", save_dir)

    return {
        "backbone": backbone,
        "status": "ok",
        "accuracy": accuracy,
        "macro_f1": macro_f1,
        "tune_half_f1": tune_f1,
        "per_label_f1": per_label_f1,
        "wilson_score_lower": _wilson_score_lower(macro_f1, n_total),
        "latency_p50_ms": latency["latency_p50_ms"],
        "latency_p95_ms": latency["latency_p95_ms"],
        "train_samples": len(train_samples),
        "val_samples": len(val_samples),
        "test_half_samples": len(test_indices),
        "tune_half_samples": len(tune_indices),
        "num_classes": num_classes,
        "steps": step,
        "multilabel": True,
        "model_save_dir": str(save_dir),
        "thresholds": thresholds_dict,
        "threshold_leakage_fixed": True,
    }


def run_multilabel_benchmark(
    *,
    labels_jsonl: Path,
    backbones: Sequence[str],
    device: str = "cpu",
    batch_size: int = 16,
    epochs: int = 3,
    max_steps: int = 3000,
    max_length: int = 256,
    val_ratio: float = 0.15,
    seed: int = 42,
    train_jsonl: Optional[Path] = None,
    val_jsonl: Optional[Path] = None,
) -> Dict[str, Any]:
    """Benchmark text backbones for multi-label classification.

    Returns same output contract as run_text_benchmark with multilabel=True.
    """
    if train_jsonl is not None and val_jsonl is not None:
        train_samples, train_labels = samples_from_jsonl(train_jsonl)
        val_samples, val_labels = samples_from_jsonl(val_jsonl)
        all_labels = sorted(set(train_labels) | set(val_labels))
        source = {
            "mode": "jsonl",
            "train_jsonl": str(train_jsonl),
            "val_jsonl": str(val_jsonl),
        }
    else:
        all_samples, all_labels = samples_from_jsonl(labels_jsonl)
        train_samples, val_samples = stratified_split(
            all_samples, val_ratio=val_ratio, seed=seed
        )
        source = {"mode": "jsonl", "labels_jsonl": str(labels_jsonl)}

    if not train_samples or not val_samples:
        return {
            "status": "failed",
            "reason": "insufficient_data",
            "selected_backbone": None,
            "source": source,
            "results": [],
        }

    # Auto-imbalance detection: if max/min class ratio > 20, downsample majority
    from collections import Counter
    label_counts = Counter()
    for s in train_samples:
        for lbl in s.labels:
            label_counts[lbl] += 1
    if label_counts:
        max_count = max(label_counts.values())
        min_count = min(label_counts.values())
        imbalance_ratio = max_count / max(min_count, 1)
        if imbalance_ratio > 20:
            logger.warning(
                "High class imbalance detected: {:.0f}:1 ratio. Auto-downsampling majority classes.",
                imbalance_ratio,
            )
            # Identify rare labels (bottom 50% by count)
            sorted_labels = sorted(label_counts.items(), key=lambda x: x[1])
            median_count = sorted_labels[len(sorted_labels) // 2][1]
            rare_labels = {lbl for lbl, cnt in sorted_labels if cnt <= median_count}
            # Keep ALL samples with any rare label, downsample the rest
            rare_samples = [s for s in train_samples if set(s.labels) & rare_labels]
            majority_samples = [s for s in train_samples if not (set(s.labels) & rare_labels)]
            cap = min(len(rare_samples) * 2, len(majority_samples))  # 2:1 majority:rare ratio
            rng = random.Random(seed)
            rng.shuffle(majority_samples)
            train_samples = rare_samples + majority_samples[:cap]
            rng.shuffle(train_samples)
            new_counts = Counter()
            for s in train_samples:
                for lbl in s.labels:
                    new_counts[lbl] += 1
            logger.info("After downsampling: {} samples. Distribution: {}", len(train_samples),
                       {lbl: cnt for lbl, cnt in new_counts.most_common()})

    label_to_idx = {label: idx for idx, label in enumerate(all_labels)}
    results: List[Dict[str, Any]] = []

    for backbone_name in backbones:
        try:
            result = benchmark_backbone(
                backbone=backbone_name,
                train_samples=train_samples,
                val_samples=val_samples,
                label_to_idx=label_to_idx,
                device=device,
                batch_size=batch_size,
                epochs=epochs,
                max_steps=max_steps,
                max_length=max_length,
                seed=seed,
            )
            logger.info(
                "multilabel backbone={} macro_f1={:.4f} accuracy={:.4f}"
                " latency_p50={:.2f}ms",
                backbone_name,
                result["macro_f1"],
                result["accuracy"],
                result.get("latency_p50_ms", 0.0),
            )
        except Exception as exc:
            result = {
                "backbone": backbone_name,
                "status": "error",
                "error": str(exc),
            }
            logger.error("backbone={} error: {}", backbone_name, exc)
        results.append(result)

    ok_results = [r for r in results if r.get("status") == "ok"]
    if ok_results:
        best = max(ok_results, key=lambda r: r.get("macro_f1", 0.0))
    else:
        best = results[0] if results else {"backbone": None}

    return {
        "status": "ok" if ok_results else "failed",
        "selected_backbone": best.get("backbone"),
        "selected_metrics": {
            "macro_f1": best.get("macro_f1", 0.0),
            "accuracy": best.get("accuracy", 0.0),
            "wilson_score_lower": best.get("wilson_score_lower", 0.0),
            "latency_p50_ms": best.get("latency_p50_ms", 0.0),
            "latency_p95_ms": best.get("latency_p95_ms", 0.0),
        },
        "source": source,
        "results": results,
        "labels": all_labels,
        "multilabel": True,
    }
