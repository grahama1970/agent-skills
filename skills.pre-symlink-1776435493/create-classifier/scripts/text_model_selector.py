#!/usr/bin/env python3
"""
Text Model Selector with Latency-First Benchmarking.

Purpose:
- Benchmark multiple text transformer backbones for latency AND accuracy.
- Select the fastest model that meets accuracy threshold.
- Critical for personaplex voice pipeline where latency impacts conversation flow.

Design principle:
- Latency is the PRIMARY constraint (voice systems need sub-20ms response).
- Accuracy is the GATE (must meet minimum threshold).
- Selection = fastest model passing accuracy gate.

Inputs:
- Training/validation data (JSONL)
- Candidate backbone list
- Accuracy threshold
- Max latency constraint

Outputs:
- Selection report with latency benchmarks
- Selected model name
- Training summary for each candidate

Usage:
    python scripts/text_model_selector.py \
        --train-data data/bridge_classifier/train.jsonl \
        --val-data data/bridge_classifier/val.jsonl \
        --candidates distilbert-base-uncased,prajjwal1/bert-tiny,sentence-transformers/all-MiniLM-L6-v2 \
        --accuracy-threshold 0.75 \
        --max-latency-ms 20 \
        --output-dir models/bridge_classifier/selection
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np
import torch
from loguru import logger
from sklearn.metrics import f1_score
from torch.utils.data import DataLoader, Dataset
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    get_linear_schedule_with_warmup,
)
import typer


# Default candidates ordered by expected latency (fastest first)
DEFAULT_TEXT_CANDIDATES = [
    "prajjwal1/bert-tiny",  # ~1.5ms
    "sentence-transformers/all-MiniLM-L6-v2",  # ~2.5ms
    "microsoft/MiniLM-L12-H384-uncased",  # ~3.5ms
    "distilbert-base-uncased",  # ~5ms
    "bert-base-uncased",  # ~12ms (baseline)
]


@dataclass
class BenchmarkResult:
    """Result from benchmarking a single model."""
    model_name: str
    status: str  # "ok", "failed", "timeout"
    latency_mean_ms: float = 0.0
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    f1_macro: float = 0.0
    f1_micro: float = 0.0
    accuracy: float = 0.0
    train_time_sec: float = 0.0
    error: Optional[str] = None
    passes_accuracy: bool = False
    passes_latency: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "status": self.status,
            "latency_mean_ms": self.latency_mean_ms,
            "latency_p50_ms": self.latency_p50_ms,
            "latency_p95_ms": self.latency_p95_ms,
            "f1_macro": self.f1_macro,
            "f1_micro": self.f1_micro,
            "accuracy": self.accuracy,
            "train_time_sec": self.train_time_sec,
            "passes_accuracy": self.passes_accuracy,
            "passes_latency": self.passes_latency,
            "error": self.error,
        }


class TextDataset(Dataset):
    """Simple text dataset for quick benchmarking."""

    def __init__(
        self,
        data_path: Path,
        tokenizer,
        max_length: int = 256,
        labels: Optional[list[str]] = None,
        multilabel: bool = False,
    ):
        self.samples = []
        self.tokenizer = tokenizer
        self.max_length = max_length
        self.multilabel = multilabel

        with open(data_path) as f:
            for line in f:
                if line.strip():
                    self.samples.append(json.loads(line))

        # Build label index (use provided labels or discover from data)
        if labels is not None:
            self.labels = labels
        else:
            all_labels = set()
            for sample in self.samples:
                sample_labels = sample.get("labels", [sample.get("label", "")])
                if isinstance(sample_labels, str):
                    sample_labels = [sample_labels]
                all_labels.update(sample_labels)
            self.labels = sorted(all_labels)
        self.label_to_idx = {label: i for i, label in enumerate(self.labels)}

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> dict[str, Any]:
        sample = self.samples[idx]
        text = sample.get("text", "")

        encoding = self.tokenizer(
            text,
            truncation=True,
            max_length=self.max_length,
            padding="max_length",
            return_tensors="pt",
        )

        sample_labels = sample.get("labels", [sample.get("label", "")])
        if isinstance(sample_labels, str):
            sample_labels = [sample_labels]

        if self.multilabel:
            label_tensor = torch.zeros(len(self.labels), dtype=torch.float)
            for lbl in sample_labels:
                if lbl in self.label_to_idx:
                    label_tensor[self.label_to_idx[lbl]] = 1.0
        else:
            label_tensor = torch.tensor(
                self.label_to_idx.get(sample_labels[0], 0),
                dtype=torch.long,
            )

        return {
            "input_ids": encoding["input_ids"].squeeze(0),
            "attention_mask": encoding["attention_mask"].squeeze(0),
            "labels": label_tensor,
        }


def benchmark_latency(
    model: torch.nn.Module,
    tokenizer,
    device: str,
    sample_texts: list[str],
    n_warmup: int = 10,
    n_iterations: int = 100,
) -> dict[str, float]:
    """Benchmark model inference latency with multiple samples."""
    model.eval()

    # Prepare inputs
    inputs_list = []
    for text in sample_texts[:5]:  # Use first 5 samples
        inputs = tokenizer(
            text,
            truncation=True,
            max_length=256,
            return_tensors="pt",
        ).to(device)
        inputs_list.append(inputs)

    # Warmup
    with torch.no_grad():
        for _ in range(n_warmup):
            for inputs in inputs_list:
                _ = model(**inputs)

    if device == "cuda":
        torch.cuda.synchronize()

    # Benchmark
    latencies = []
    with torch.no_grad():
        for _ in range(n_iterations):
            inputs = inputs_list[_ % len(inputs_list)]
            start = time.perf_counter()
            _ = model(**inputs)
            if device == "cuda":
                torch.cuda.synchronize()
            latencies.append((time.perf_counter() - start) * 1000)

    return {
        "latency_mean_ms": float(np.mean(latencies)),
        "latency_p50_ms": float(np.percentile(latencies, 50)),
        "latency_p95_ms": float(np.percentile(latencies, 95)),
        "latency_p99_ms": float(np.percentile(latencies, 99)),
    }


def quick_train_and_eval(
    model_name: str,
    train_data: Path,
    val_data: Path,
    device: str,
    multilabel: bool = False,
    epochs: int = 3,
    batch_size: int = 32,
    learning_rate: float = 2e-5,
) -> tuple[torch.nn.Module, Any, dict[str, float]]:
    """Quick training for model comparison."""
    tokenizer = AutoTokenizer.from_pretrained(model_name)

    # Create datasets with this tokenizer
    train_ds = TextDataset(train_data, tokenizer, multilabel=multilabel)
    val_ds = TextDataset(val_data, tokenizer, labels=train_ds.labels, multilabel=multilabel)

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False)

    # Load model
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name,
        num_labels=len(train_ds.labels),
        problem_type="multi_label_classification" if multilabel else "single_label_classification",
    ).to(device)

    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
    total_steps = len(train_loader) * epochs
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=int(total_steps * 0.1),
        num_training_steps=total_steps,
    )

    if multilabel:
        criterion = torch.nn.BCEWithLogitsLoss()
    else:
        criterion = torch.nn.CrossEntropyLoss()

    # Train
    model.train()
    for epoch in range(epochs):
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

    # Evaluate
    model.eval()
    all_preds = []
    all_labels = []

    with torch.no_grad():
        for batch in val_loader:
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels = batch["labels"].to(device)

            outputs = model(input_ids=input_ids, attention_mask=attention_mask)
            logits = outputs.logits

            if multilabel:
                probs = torch.sigmoid(logits)
                preds = (probs > 0.5).int()
                all_preds.append(preds.cpu().numpy())
            else:
                all_preds.append(logits.argmax(dim=1).cpu().numpy())
            all_labels.append(labels.cpu().numpy())

    preds = np.concatenate(all_preds, axis=0)
    labels = np.concatenate(all_labels, axis=0)

    if multilabel:
        f1_macro = f1_score(labels, preds, average="macro", zero_division=0)
        f1_micro = f1_score(labels, preds, average="micro", zero_division=0)
        accuracy = (preds == labels).all(axis=1).mean()
    else:
        f1_macro = f1_score(labels, preds, average="macro", zero_division=0)
        f1_micro = f1_score(labels, preds, average="micro", zero_division=0)
        accuracy = (preds == labels).mean()

    metrics = {
        "f1_macro": float(f1_macro),
        "f1_micro": float(f1_micro),
        "accuracy": float(accuracy),
    }

    return model, tokenizer, metrics


def benchmark_model(
    model_name: str,
    train_data: Path,
    val_data: Path,
    device: str,
    multilabel: bool = False,
    quick_epochs: int = 3,
    accuracy_threshold: float = 0.75,
    max_latency_ms: float = 20.0,
) -> BenchmarkResult:
    """Benchmark a single model for latency and accuracy."""
    logger.info("Benchmarking: {}", model_name)

    result = BenchmarkResult(model_name=model_name, status="pending")

    try:
        start_time = time.perf_counter()

        # Quick train
        model, tokenizer, metrics = quick_train_and_eval(
            model_name=model_name,
            train_data=train_data,
            val_data=val_data,
            device=device,
            multilabel=multilabel,
            epochs=quick_epochs,
        )

        result.train_time_sec = time.perf_counter() - start_time
        result.f1_macro = metrics["f1_macro"]
        result.f1_micro = metrics["f1_micro"]
        result.accuracy = metrics["accuracy"]

        # Benchmark latency with sample texts from val data
        with open(val_data) as f:
            val_samples = [json.loads(line) for line in f if line.strip()]
        sample_texts = [s.get("text", "") for s in val_samples[:10]]
        latency = benchmark_latency(model, tokenizer, device, sample_texts)

        result.latency_mean_ms = latency["latency_mean_ms"]
        result.latency_p50_ms = latency["latency_p50_ms"]
        result.latency_p95_ms = latency["latency_p95_ms"]

        # Check gates
        result.passes_accuracy = result.f1_macro >= accuracy_threshold
        result.passes_latency = result.latency_p50_ms <= max_latency_ms
        result.status = "ok"

        logger.info(
            "  {} - F1={:.3f}, latency={:.1f}ms (acc={}, lat={})",
            model_name,
            result.f1_macro,
            result.latency_p50_ms,
            "PASS" if result.passes_accuracy else "FAIL",
            "PASS" if result.passes_latency else "FAIL",
        )

    except Exception as e:
        result.status = "failed"
        result.error = str(e)
        logger.error("  {} - FAILED: {}", model_name, e)

    return result


def _try_classifier_lab_delegation(
    train_data: Path,
    val_data: Path,
    candidates: list[str],
    device: str,
    quick_epochs: int,
) -> Optional[dict[str, Any]]:
    """Attempt to delegate to classifier-lab's text benchmark engine."""
    import sys

    classifier_lab_scripts = Path(__file__).resolve().parent.parent.parent / "classifier-lab" / "scripts"
    if not classifier_lab_scripts.exists():
        return None

    try:
        sys.path.insert(0, str(classifier_lab_scripts))
        from text_benchmark import run_text_benchmark
        sys.path.pop(0)

        report = run_text_benchmark(
            labels_jsonl=train_data,  # unused when train/val split provided
            backbones=candidates,
            device=device,
            epochs=quick_epochs,
            train_jsonl=train_data,
            val_jsonl=val_data,
        )
        # Translate classifier-lab output to our expected format
        if report.get("status") == "ok":
            return {
                "status": "ok",
                "selected_model": report["selected_backbone"],
                "selection_path": "classifier_lab_delegation",
                "selected_metrics": report.get("selected_metrics", {}),
                "candidates": candidates,
                "results": report.get("results", []),
            }
        return None
    except Exception as exc:
        logger.debug("classifier-lab delegation failed: {}", exc)
        return None


def select_text_model(
    train_data: Path,
    val_data: Path,
    candidates: list[str],
    device: str = "cuda",
    multilabel: bool = False,
    quick_epochs: int = 3,
    accuracy_threshold: float = 0.75,
    max_latency_ms: float = 20.0,
) -> dict[str, Any]:
    """
    Select the best text model by benchmarking candidates.

    Selection strategy (latency-first for voice pipeline):
    1. Train each candidate for quick_epochs
    2. Measure latency (p50)
    3. Filter by accuracy threshold
    4. Select fastest model that passes accuracy gate

    When classifier-lab is available, delegates benchmarking there.
    Falls back to local implementation if unavailable.
    """
    # Try delegating to classifier-lab (the universal benchmark backend)
    if not multilabel:
        delegated = _try_classifier_lab_delegation(
            train_data=train_data,
            val_data=val_data,
            candidates=candidates,
            device=device,
            quick_epochs=quick_epochs,
        )
        if delegated is not None:
            logger.info("Delegated to classifier-lab text benchmark engine")
            return delegated

    logger.info("=" * 60)
    logger.info("Text Model Selection - Latency-First Benchmark")
    logger.info("=" * 60)
    logger.info("Candidates: {}", candidates)
    logger.info("Accuracy threshold: {:.1%}", accuracy_threshold)
    logger.info("Max latency: {:.1f}ms", max_latency_ms)
    logger.info("Device: {}", device)
    logger.info("=" * 60)

    results: list[BenchmarkResult] = []

    for model_name in candidates:
        result = benchmark_model(
            model_name=model_name,
            train_data=train_data,
            val_data=val_data,
            device=device,
            multilabel=multilabel,
            quick_epochs=quick_epochs,
            accuracy_threshold=accuracy_threshold,
            max_latency_ms=max_latency_ms,
        )
        results.append(result)

    # Select best model
    # Priority: passes both gates -> sort by latency (fastest first)
    passing_both = [r for r in results if r.passes_accuracy and r.passes_latency and r.status == "ok"]
    passing_accuracy = [r for r in results if r.passes_accuracy and r.status == "ok"]
    all_ok = [r for r in results if r.status == "ok"]

    if passing_both:
        selected = min(passing_both, key=lambda r: r.latency_p50_ms)
        selection_path = "both_gates"
    elif passing_accuracy:
        # Accuracy OK but latency exceeds - pick fastest anyway with warning
        selected = min(passing_accuracy, key=lambda r: r.latency_p50_ms)
        selection_path = "accuracy_only"
        logger.warning(
            "No model meets latency constraint ({:.1f}ms). Selected fastest accurate: {}",
            max_latency_ms,
            selected.model_name,
        )
    elif all_ok:
        # Nothing passes accuracy - pick highest F1
        selected = max(all_ok, key=lambda r: r.f1_macro)
        selection_path = "best_accuracy"
        logger.warning(
            "No model meets accuracy threshold ({:.1%}). Selected highest F1: {}",
            accuracy_threshold,
            selected.model_name,
        )
    else:
        # All failed
        selected = None
        selection_path = "all_failed"
        logger.error("All model benchmarks failed!")

    report = {
        "status": "ok" if selected else "failed",
        "selected_model": selected.model_name if selected else None,
        "selection_path": selection_path,
        "accuracy_threshold": accuracy_threshold,
        "max_latency_ms": max_latency_ms,
        "candidates": candidates,
        "results": [r.to_dict() for r in results],
    }

    if selected:
        report["selected_metrics"] = {
            "f1_macro": selected.f1_macro,
            "f1_micro": selected.f1_micro,
            "latency_p50_ms": selected.latency_p50_ms,
            "latency_p95_ms": selected.latency_p95_ms,
        }

    logger.info("\n" + "=" * 60)
    logger.info("SELECTION RESULT")
    logger.info("=" * 60)
    if selected:
        logger.info("Selected: {}", selected.model_name)
        logger.info("F1 (macro): {:.3f}", selected.f1_macro)
        logger.info("Latency (p50): {:.2f}ms", selected.latency_p50_ms)
        logger.info("Selection path: {}", selection_path)
    else:
        logger.error("No model selected - all benchmarks failed")
    logger.info("=" * 60)

    return report


app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command()
def main(
    train_data: Path = typer.Option(..., exists=True, file_okay=True, dir_okay=False),
    val_data: Path = typer.Option(..., exists=True, file_okay=True, dir_okay=False),
    candidates: str = typer.Option(
        ",".join(DEFAULT_TEXT_CANDIDATES),
        help="Comma-separated model names to benchmark",
    ),
    output_dir: Optional[Path] = typer.Option(None, help="Output directory for report"),
    multilabel: bool = typer.Option(False, help="Multi-label classification"),
    quick_epochs: int = typer.Option(3, min=1, help="Epochs per candidate"),
    accuracy_threshold: float = typer.Option(0.75, min=0.0, max=1.0),
    max_latency_ms: float = typer.Option(20.0, min=1.0, help="Max acceptable latency"),
    device: str = typer.Option(
        "cuda" if torch.cuda.is_available() else "cpu",
        help="Device for training/inference",
    ),
) -> None:
    """Select best text model by benchmarking latency and accuracy."""
    candidate_list = [c.strip() for c in candidates.split(",") if c.strip()]

    report = select_text_model(
        train_data=train_data,
        val_data=val_data,
        candidates=candidate_list,
        device=device,
        multilabel=multilabel,
        quick_epochs=quick_epochs,
        accuracy_threshold=accuracy_threshold,
        max_latency_ms=max_latency_ms,
    )

    # Save report
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / "text_model_selection.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
        logger.info("Report saved to: {}", report_path)

    # Print summary
    print(json.dumps(report, indent=2))

    if report["status"] != "ok":
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
