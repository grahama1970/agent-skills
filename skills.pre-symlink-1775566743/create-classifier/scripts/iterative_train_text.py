#!/usr/bin/env python3
"""
Iterative Text Classifier Training with Model Selection and HP Tuning.

Purpose:
- Select best text model backbone via latency-first benchmarking.
- Optimize hyperparameters using Bayesian search.
- Train iteratively until quality thresholds are met.
- Focus on minimal latency for voice pipeline integration.

Pipeline:
1. Model Selection: Benchmark candidates, select fastest that meets accuracy gate.
2. HP Search: Optuna-based hyperparameter optimization for selected model.
3. Iterative Training: Train until quality threshold, with holdout validation.
4. Export: Save best model with latency benchmarks.

Usage:
    python scripts/iterative_train_text.py \
        --train-data data/bridge_classifier/train.jsonl \
        --val-data data/bridge_classifier/val.jsonl \
        --output-dir models/bridge_classifier \
        --multilabel \
        --run-hp-search \
        --hp-trials 15 \
        --accuracy-threshold 0.80 \
        --max-latency-ms 10
"""

from __future__ import annotations

import json
import random
import shutil
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np
import torch
import torch.nn as nn
from loguru import logger
from rich.console import Console
from sklearn.metrics import f1_score, hamming_loss
from torch.utils.data import DataLoader, Dataset, Subset
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    get_linear_schedule_with_warmup,
)
import typer

try:
    import optuna
except ImportError:
    optuna = None
    logger.warning("Optuna not installed. HP search will be disabled.")


console = Console()


# Default text candidates ordered by latency
DEFAULT_TEXT_CANDIDATES = [
    "prajjwal1/bert-tiny",
    "sentence-transformers/all-MiniLM-L6-v2",
    "distilbert-base-uncased",
]


@dataclass
class TextTrainingConfig:
    """Configuration for text classifier training."""
    model_name: str = "distilbert-base-uncased"
    max_length: int = 256
    batch_size: int = 32
    learning_rate: float = 2e-5
    weight_decay: float = 0.01
    dropout: float = 0.1
    warmup_ratio: float = 0.1
    threshold: float = 0.5
    pos_weight_auto: bool = True


class TextDataset(Dataset):
    """Dataset for text classification."""

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

        if labels:
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
        self.idx_to_label = {i: label for label, i in self.label_to_idx.items()}

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


def compute_pos_weights(dataset: TextDataset, device: str) -> torch.Tensor:
    """Compute positive class weights for imbalanced data."""
    label_counts = torch.zeros(len(dataset.labels))
    total = len(dataset)

    for sample in dataset.samples:
        sample_labels = sample.get("labels", [sample.get("label", "")])
        if isinstance(sample_labels, str):
            sample_labels = [sample_labels]
        for lbl in sample_labels:
            if lbl in dataset.label_to_idx:
                label_counts[dataset.label_to_idx[lbl]] += 1

    neg_counts = total - label_counts
    pos_weights = neg_counts / (label_counts + 1e-6)
    pos_weights = torch.clamp(pos_weights, 1.0, 10.0)
    return pos_weights.to(device)


def benchmark_latency(
    model: nn.Module,
    tokenizer,
    device: str,
    n_warmup: int = 10,
    n_iterations: int = 100,
) -> dict[str, float]:
    """Benchmark inference latency."""
    model.eval()
    sample = "Evaluate the UI for accessibility and usability"

    inputs = tokenizer(
        sample,
        truncation=True,
        max_length=256,
        return_tensors="pt",
    ).to(device)

    with torch.no_grad():
        for _ in range(n_warmup):
            _ = model(**inputs)

    if device == "cuda":
        torch.cuda.synchronize()

    latencies = []
    with torch.no_grad():
        for _ in range(n_iterations):
            start = time.perf_counter()
            _ = model(**inputs)
            if device == "cuda":
                torch.cuda.synchronize()
            latencies.append((time.perf_counter() - start) * 1000)

    return {
        "latency_mean_ms": float(np.mean(latencies)),
        "latency_p50_ms": float(np.percentile(latencies, 50)),
        "latency_p95_ms": float(np.percentile(latencies, 95)),
    }


class IterativeTextTrainer:
    """Iterative text classifier trainer with model selection and HP tuning."""

    def __init__(
        self,
        train_data: Path,
        val_data: Path,
        output_dir: Path,
        multilabel: bool = False,
        device: str = "cuda",
        quality_threshold: float = 0.80,
        max_latency_ms: float = 20.0,
        max_iterations: int = 5,
        epochs_per_iteration: int = 3,
        holdout_ratio: float = 0.10,
        seed: int = 42,
        candidate_backbones: Optional[list[str]] = None,
        run_model_selection: bool = True,
        run_hp_search: bool = True,
        hp_trials: int = 15,
    ):
        self.train_data = train_data
        self.val_data = val_data
        self.output_dir = output_dir
        self.multilabel = multilabel
        self.device = device
        self.quality_threshold = quality_threshold
        self.max_latency_ms = max_latency_ms
        self.max_iterations = max_iterations
        self.epochs_per_iteration = epochs_per_iteration
        self.holdout_ratio = holdout_ratio
        self.seed = seed
        self.candidate_backbones = candidate_backbones or DEFAULT_TEXT_CANDIDATES
        self.run_model_selection = run_model_selection
        self.run_hp_search = run_hp_search
        self.hp_trials = hp_trials

        self.output_dir.mkdir(parents=True, exist_ok=True)

        random.seed(seed)
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)

        # State
        self.selected_model: Optional[str] = None
        self.best_hyperparams: dict[str, Any] = {}
        self.best_f1: float = 0.0
        self.best_model_path: Optional[Path] = None
        self.iteration_results: list[dict] = []
        self.selection_report: dict = {}
        self.hp_report: dict = {}

    def _run_model_selection(self) -> str:
        """Run model selection to pick best backbone."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from text_model_selector import select_text_model

        logger.info("\n" + "=" * 60)
        logger.info("PHASE 1: Model Selection")
        logger.info("=" * 60)

        self.selection_report = select_text_model(
            train_data=self.train_data,
            val_data=self.val_data,
            candidates=self.candidate_backbones,
            device=self.device,
            multilabel=self.multilabel,
            quick_epochs=2,
            accuracy_threshold=self.quality_threshold * 0.9,  # Slightly lower for selection
            max_latency_ms=self.max_latency_ms,
        )

        # Save selection report
        with open(self.output_dir / "model_selection.json", "w") as f:
            json.dump(self.selection_report, f, indent=2)

        selected = self.selection_report.get("selected_model")
        if not selected:
            logger.warning("Model selection failed, using default: distilbert-base-uncased")
            selected = "distilbert-base-uncased"

        logger.info("Selected model: {}", selected)
        return selected

    def _run_hp_search(self, model_name: str) -> dict[str, Any]:
        """Run Bayesian hyperparameter search."""
        if optuna is None:
            logger.warning("Optuna not available, using default hyperparameters")
            return {
                "learning_rate": 2e-5,
                "weight_decay": 0.01,
                "dropout": 0.1,
                "batch_size": 32,
                "warmup_ratio": 0.1,
            }

        logger.info("\n" + "=" * 60)
        logger.info("PHASE 2: Hyperparameter Search")
        logger.info("=" * 60)

        # Create Optuna study
        study_path = self.output_dir / "optuna_study.db"
        study = optuna.create_study(
            study_name=f"text_classifier_hp_search",
            storage=f"sqlite:///{study_path}",
            direction="maximize",  # Maximize F1
            load_if_exists=True,
        )

        def objective(trial: optuna.Trial) -> float:
            """Objective function for HP search."""
            hyperparams = {
                "learning_rate": trial.suggest_float("learning_rate", 1e-5, 5e-4, log=True),
                "weight_decay": trial.suggest_float("weight_decay", 1e-4, 1e-1, log=True),
                "dropout": trial.suggest_float("dropout", 0.05, 0.3),
                "batch_size": trial.suggest_categorical("batch_size", [16, 32, 64]),
                "warmup_ratio": trial.suggest_float("warmup_ratio", 0.0, 0.2),
            }

            try:
                f1 = self._quick_train_eval(model_name, hyperparams, epochs=2)
                logger.info(
                    "Trial {}: lr={:.2e}, wd={:.2e} -> F1={:.3f}",
                    trial.number,
                    hyperparams["learning_rate"],
                    hyperparams["weight_decay"],
                    f1,
                )
                return f1
            except Exception as e:
                logger.warning("Trial {} failed: {}", trial.number, e)
                return 0.0

        study.optimize(objective, n_trials=self.hp_trials, show_progress_bar=True)

        best_params = study.best_params
        self.hp_report = {
            "best_f1": study.best_value,
            "best_params": best_params,
            "n_trials": self.hp_trials,
        }

        # Save HP report
        with open(self.output_dir / "hp_search.json", "w") as f:
            json.dump(self.hp_report, f, indent=2)

        logger.info("Best HP: F1={:.3f}", study.best_value)
        for k, v in best_params.items():
            logger.info("  {}: {}", k, v)

        return best_params

    def _quick_train_eval(
        self,
        model_name: str,
        hyperparams: dict[str, Any],
        epochs: int = 2,
    ) -> float:
        """Quick training for HP search evaluation."""
        tokenizer = AutoTokenizer.from_pretrained(model_name)

        train_dataset = TextDataset(
            self.train_data,
            tokenizer,
            multilabel=self.multilabel,
        )
        val_dataset = TextDataset(
            self.val_data,
            tokenizer,
            labels=train_dataset.labels,
            multilabel=self.multilabel,
        )

        train_loader = DataLoader(
            train_dataset,
            batch_size=hyperparams.get("batch_size", 32),
            shuffle=True,
        )
        val_loader = DataLoader(val_dataset, batch_size=32, shuffle=False)

        model = AutoModelForSequenceClassification.from_pretrained(
            model_name,
            num_labels=len(train_dataset.labels),
            problem_type="multi_label_classification" if self.multilabel else "single_label_classification",
                    ).to(self.device)

        optimizer = torch.optim.AdamW(
            model.parameters(),
            lr=hyperparams.get("learning_rate", 2e-5),
            weight_decay=hyperparams.get("weight_decay", 0.01),
        )

        total_steps = len(train_loader) * epochs
        warmup_steps = int(total_steps * hyperparams.get("warmup_ratio", 0.1))
        scheduler = get_linear_schedule_with_warmup(
            optimizer, warmup_steps, total_steps
        )

        if self.multilabel:
            pos_weight = compute_pos_weights(train_dataset, self.device)
            criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
        else:
            criterion = nn.CrossEntropyLoss()

        # Train
        model.train()
        for _ in range(epochs):
            for batch in train_loader:
                input_ids = batch["input_ids"].to(self.device)
                attention_mask = batch["attention_mask"].to(self.device)
                labels = batch["labels"].to(self.device)

                optimizer.zero_grad()
                outputs = model(input_ids=input_ids, attention_mask=attention_mask)
                loss = criterion(outputs.logits, labels)
                loss.backward()
                optimizer.step()
                scheduler.step()

        # Evaluate
        model.eval()
        all_preds, all_labels = [], []
        with torch.no_grad():
            for batch in val_loader:
                input_ids = batch["input_ids"].to(self.device)
                attention_mask = batch["attention_mask"].to(self.device)
                labels = batch["labels"].to(self.device)

                outputs = model(input_ids=input_ids, attention_mask=attention_mask)
                if self.multilabel:
                    preds = (torch.sigmoid(outputs.logits) > 0.5).int()
                else:
                    preds = outputs.logits.argmax(dim=1)
                all_preds.append(preds.cpu().numpy())
                all_labels.append(labels.cpu().numpy())

        preds = np.concatenate(all_preds)
        labels = np.concatenate(all_labels)
        f1 = f1_score(labels, preds, average="macro", zero_division=0)
        return float(f1)

    def _build_split_indices(self, n_samples: int) -> dict[str, list[int]]:
        """Build train/val/holdout split indices."""
        rng = random.Random(self.seed)
        indices = list(range(n_samples))
        rng.shuffle(indices)

        n_holdout = max(1, int(n_samples * self.holdout_ratio))
        n_val = max(1, int((n_samples - n_holdout) * 0.15))

        holdout = indices[:n_holdout]
        val = indices[n_holdout:n_holdout + n_val]
        train = indices[n_holdout + n_val:]

        return {"train": train, "val": val, "holdout": holdout}

    def train_iteration(
        self,
        iteration: int,
        model_name: str,
        hyperparams: dict[str, Any],
        epochs: int,
    ) -> dict[str, Any]:
        """Train for one iteration and evaluate."""
        logger.info("\n" + "-" * 40)
        logger.info("Iteration {}/{}", iteration + 1, self.max_iterations)
        logger.info("-" * 40)

        tokenizer = AutoTokenizer.from_pretrained(model_name)

        train_dataset = TextDataset(
            self.train_data,
            tokenizer,
            multilabel=self.multilabel,
        )
        val_dataset = TextDataset(
            self.val_data,
            tokenizer,
            labels=train_dataset.labels,
            multilabel=self.multilabel,
        )

        # Split with holdout
        split = self._build_split_indices(len(train_dataset))

        train_loader = DataLoader(
            Subset(train_dataset, split["train"]),
            batch_size=hyperparams.get("batch_size", 32),
            shuffle=True,
        )
        val_loader = DataLoader(
            Subset(train_dataset, split["val"]),
            batch_size=32,
            shuffle=False,
        )
        holdout_loader = DataLoader(
            Subset(train_dataset, split["holdout"]),
            batch_size=32,
            shuffle=False,
        )

        # Load/create model
        model = AutoModelForSequenceClassification.from_pretrained(
            model_name,
            num_labels=len(train_dataset.labels),
            problem_type="multi_label_classification" if self.multilabel else "single_label_classification",
                    ).to(self.device)

        optimizer = torch.optim.AdamW(
            model.parameters(),
            lr=hyperparams.get("learning_rate", 2e-5),
            weight_decay=hyperparams.get("weight_decay", 0.01),
        )

        total_steps = len(train_loader) * epochs
        warmup_steps = int(total_steps * hyperparams.get("warmup_ratio", 0.1))
        scheduler = get_linear_schedule_with_warmup(optimizer, warmup_steps, total_steps)

        if self.multilabel:
            pos_weight = compute_pos_weights(train_dataset, self.device)
            criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
        else:
            criterion = nn.CrossEntropyLoss()

        # Train
        model.train()
        for epoch in range(epochs):
            total_loss = 0.0
            for batch in train_loader:
                input_ids = batch["input_ids"].to(self.device)
                attention_mask = batch["attention_mask"].to(self.device)
                labels = batch["labels"].to(self.device)

                optimizer.zero_grad()
                outputs = model(input_ids=input_ids, attention_mask=attention_mask)
                loss = criterion(outputs.logits, labels)
                loss.backward()
                optimizer.step()
                scheduler.step()
                total_loss += loss.item()

            logger.info(
                "  Epoch {}/{}: loss={:.4f}",
                epoch + 1,
                epochs,
                total_loss / len(train_loader),
            )

        # Evaluate
        def evaluate(loader):
            model.eval()
            all_preds, all_labels = [], []
            with torch.no_grad():
                for batch in loader:
                    input_ids = batch["input_ids"].to(self.device)
                    attention_mask = batch["attention_mask"].to(self.device)
                    labels = batch["labels"].to(self.device)

                    outputs = model(input_ids=input_ids, attention_mask=attention_mask)
                    if self.multilabel:
                        preds = (torch.sigmoid(outputs.logits) > 0.5).int()
                    else:
                        preds = outputs.logits.argmax(dim=1)
                    all_preds.append(preds.cpu().numpy())
                    all_labels.append(labels.cpu().numpy())

            preds = np.concatenate(all_preds)
            labels = np.concatenate(all_labels)
            return {
                "f1_macro": f1_score(labels, preds, average="macro", zero_division=0),
                "f1_micro": f1_score(labels, preds, average="micro", zero_division=0),
            }

        val_metrics = evaluate(val_loader)
        holdout_metrics = evaluate(holdout_loader)

        # Benchmark latency
        latency = benchmark_latency(model, tokenizer, self.device)

        result = {
            "iteration": iteration + 1,
            "val_f1_macro": val_metrics["f1_macro"],
            "val_f1_micro": val_metrics["f1_micro"],
            "holdout_f1_macro": holdout_metrics["f1_macro"],
            "holdout_f1_micro": holdout_metrics["f1_micro"],
            "latency_p50_ms": latency["latency_p50_ms"],
            "latency_p95_ms": latency["latency_p95_ms"],
            "passes_quality": val_metrics["f1_macro"] >= self.quality_threshold,
            "passes_latency": latency["latency_p50_ms"] <= self.max_latency_ms,
        }

        # Save if best
        if val_metrics["f1_macro"] > self.best_f1:
            self.best_f1 = val_metrics["f1_macro"]
            self.best_model_path = self.output_dir / "best_model"

            model.save_pretrained(self.best_model_path)
            tokenizer.save_pretrained(self.best_model_path)

            # Save config
            config = {
                "labels": train_dataset.labels,
                "id2label": train_dataset.idx_to_label,
                "label2id": train_dataset.label_to_idx,
                "multilabel": self.multilabel,
                "threshold": 0.5,
                "max_length": 256,
            }
            with open(self.best_model_path / "bridge_config.json", "w") as f:
                json.dump(config, f, indent=2)

        logger.info("  Val F1: {:.3f}, Holdout F1: {:.3f}, Latency: {:.1f}ms",
                    val_metrics["f1_macro"], holdout_metrics["f1_macro"], latency["latency_p50_ms"])

        return result

    def run(self) -> dict[str, Any]:
        """Run full training pipeline."""
        logger.info("=" * 60)
        logger.info("Iterative Text Classifier Training")
        logger.info("=" * 60)
        logger.info("Quality threshold: {:.1%}", self.quality_threshold)
        logger.info("Max latency: {:.1f}ms", self.max_latency_ms)
        logger.info("Max iterations: {}", self.max_iterations)

        # Phase 1: Model Selection
        if self.run_model_selection:
            self.selected_model = self._run_model_selection()
        else:
            self.selected_model = self.candidate_backbones[0]
            logger.info("Skipping model selection, using: {}", self.selected_model)

        # Phase 2: HP Search
        if self.run_hp_search:
            self.best_hyperparams = self._run_hp_search(self.selected_model)
        else:
            self.best_hyperparams = {
                "learning_rate": 2e-5,
                "weight_decay": 0.01,
                "dropout": 0.1,
                "batch_size": 32,
                "warmup_ratio": 0.1,
            }
            logger.info("Skipping HP search, using defaults")

        # Phase 3: Iterative Training
        logger.info("\n" + "=" * 60)
        logger.info("PHASE 3: Iterative Training")
        logger.info("=" * 60)

        threshold_met = False
        for iteration in range(self.max_iterations):
            result = self.train_iteration(
                iteration=iteration,
                model_name=self.selected_model,
                hyperparams=self.best_hyperparams,
                epochs=self.epochs_per_iteration,
            )
            self.iteration_results.append(result)

            if result["passes_quality"] and result["passes_latency"]:
                threshold_met = True
                console.print(
                    f"\n[bold green]THRESHOLD MET at iteration {iteration + 1}![/bold green]"
                )
                break

        # Final summary
        summary = {
            "status": "ok" if threshold_met else "threshold_not_met",
            "selected_model": self.selected_model,
            "best_f1_macro": self.best_f1,
            "best_model_path": str(self.best_model_path) if self.best_model_path else None,
            "hyperparameters": self.best_hyperparams,
            "iterations": self.iteration_results,
            "selection_report": self.selection_report,
            "hp_report": self.hp_report,
            "quality_threshold": self.quality_threshold,
            "max_latency_ms": self.max_latency_ms,
        }

        # Add final latency if model exists
        if self.best_model_path and self.best_model_path.exists():
            tokenizer = AutoTokenizer.from_pretrained(self.best_model_path)
            model = AutoModelForSequenceClassification.from_pretrained(
                self.best_model_path
            ).to(self.device)
            latency = benchmark_latency(model, tokenizer, self.device)
            summary["final_latency"] = latency

        # Save summary
        with open(self.output_dir / "training_summary.json", "w") as f:
            json.dump(summary, f, indent=2)

        logger.info("\n" + "=" * 60)
        logger.info("TRAINING COMPLETE")
        logger.info("=" * 60)
        logger.info("Selected model: {}", self.selected_model)
        logger.info("Best F1 (macro): {:.3f}", self.best_f1)
        if "final_latency" in summary:
            logger.info("Final latency: {:.2f}ms", summary["final_latency"]["latency_p50_ms"])
        logger.info("Model saved to: {}", self.best_model_path)
        logger.info("=" * 60)

        return summary


app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command()
def main(
    train_data: Path = typer.Option(..., exists=True, file_okay=True, dir_okay=False),
    val_data: Path = typer.Option(..., exists=True, file_okay=True, dir_okay=False),
    output_dir: Path = typer.Option(..., help="Output directory"),
    multilabel: bool = typer.Option(False, help="Multi-label classification"),
    candidates: str = typer.Option(
        ",".join(DEFAULT_TEXT_CANDIDATES),
        help="Comma-separated candidate backbones",
    ),
    accuracy_threshold: float = typer.Option(0.80, min=0.0, max=1.0),
    max_latency_ms: float = typer.Option(20.0, min=1.0),
    max_iterations: int = typer.Option(5, min=1),
    epochs_per_iter: int = typer.Option(3, min=1),
    run_model_selection: bool = typer.Option(True, help="Run model selection phase"),
    run_hp_search: bool = typer.Option(True, help="Run HP search phase"),
    hp_trials: int = typer.Option(15, min=1),
    device: str = typer.Option(
        "cuda" if torch.cuda.is_available() else "cpu",
        help="Training device",
    ),
    seed: int = typer.Option(42),
) -> None:
    """Run iterative text classifier training with model selection and HP tuning."""
    candidate_list = [c.strip() for c in candidates.split(",") if c.strip()]

    trainer = IterativeTextTrainer(
        train_data=train_data,
        val_data=val_data,
        output_dir=output_dir,
        multilabel=multilabel,
        device=device,
        quality_threshold=accuracy_threshold,
        max_latency_ms=max_latency_ms,
        max_iterations=max_iterations,
        epochs_per_iteration=epochs_per_iter,
        seed=seed,
        candidate_backbones=candidate_list,
        run_model_selection=run_model_selection,
        run_hp_search=run_hp_search,
        hp_trials=hp_trials,
    )

    summary = trainer.run()

    if summary["status"] != "ok":
        console.print("[yellow]Warning: Quality threshold not met[/yellow]")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
