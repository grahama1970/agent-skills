#!/usr/bin/env python3
"""
Iterative training with conditional HF augmentation and holdout promotion gate.

Purpose:
- run two-phase classifier optimization (optional HP search + iterative train).
- auto-augment training labels from Hugging Face when local labels are sparse/
  imbalanced, with strict license/provenance controls.
- enforce holdout quality gate before promoting a model to best_model.pt.

Inputs:
- task config, labels JSONL, model architecture, and training/gating parameters.

Outputs:
- iteration checkpoints, optional promoted best model, and training summary JSON.

Failure modes:
- returns non-zero when quality threshold/holdout gate is not met.
"""

from __future__ import annotations

import json
import random
import shutil
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import torch
import yaml
from loguru import logger
from rich.console import Console
import typer

# specific to running from create-classifier dir
sys.path.append(str(Path(__file__).parent.parent))

console = Console()


class IterativeTrainer:
    """Iterative training with quality-driven + holdout-gated promotion."""

    def __init__(
        self,
        task_name: str,
        task_config_path: Path,
        labels_path: Path,
        model_name: str,
        output_dir: Path,
        quality_threshold: float = 0.90,
        max_iterations: int = 5,
        epochs_per_iteration: int = 10,
        device: str = "cuda",
        auto_hf_augment: bool = True,
        hf_config_path: Optional[Path] = None,
        min_samples_per_class: int = 300,
        imbalance_ratio_threshold: float = 0.35,
        hf_max_new_samples: int = 3000,
        allowed_hf_licenses: Optional[List[str]] = None,
        holdout_ratio: float = 0.10,
        holdout_threshold: Optional[float] = None,
        require_holdout_gate: bool = True,
        run_preflight_assess: bool = True,
        dogpile_when_uncertain: bool = True,
        dogpile_threshold: float = 0.70,
        split_seed: int = 42,
        benchmark_first: bool = True,
        classifier_lab_first: bool = True,
        classifier_lab_data_dir: Optional[Path] = None,
        classifier_lab_timeout_sec: int = 300,
        require_classifier_lab: bool = True,
        require_selection_pass: bool = True,
        candidate_backbones: Optional[List[str]] = None,
        quick_benchmark_epochs: int = 1,
        quick_benchmark_max_steps: int = 250,
    ):
        self.task_name = task_name
        self.task_config = self._load_yaml(task_config_path)
        self.labels_path = labels_path
        self.active_labels_path = labels_path
        self.model_name = model_name
        self.output_dir = output_dir
        self.quality_threshold = quality_threshold
        self.max_iterations = max_iterations
        self.epochs_per_iteration = epochs_per_iteration
        self.device = device
        self.auto_hf_augment = auto_hf_augment
        self.hf_config_path = hf_config_path
        self.min_samples_per_class = min_samples_per_class
        self.imbalance_ratio_threshold = imbalance_ratio_threshold
        self.hf_max_new_samples = hf_max_new_samples
        self.allowed_hf_licenses = allowed_hf_licenses or []
        self.holdout_ratio = holdout_ratio
        self.holdout_threshold = (
            holdout_threshold if holdout_threshold is not None else quality_threshold
        )
        self.require_holdout_gate = require_holdout_gate
        self.run_preflight_assess = run_preflight_assess
        self.dogpile_when_uncertain = dogpile_when_uncertain
        self.dogpile_threshold = dogpile_threshold
        self.split_seed = split_seed
        self.benchmark_first = benchmark_first
        self.classifier_lab_first = classifier_lab_first
        self.classifier_lab_data_dir = classifier_lab_data_dir
        self.classifier_lab_timeout_sec = classifier_lab_timeout_sec
        self.require_classifier_lab = require_classifier_lab
        self.require_selection_pass = require_selection_pass
        self.candidate_backbones = candidate_backbones
        self.quick_benchmark_epochs = quick_benchmark_epochs
        self.quick_benchmark_max_steps = quick_benchmark_max_steps

        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.best_accuracy = 0.0
        self.best_model_path: Optional[str] = None
        self.best_promoted_accuracy = 0.0
        self.best_promoted_model_path: Optional[str] = None
        self.iteration_results: List[Dict[str, Any]] = []
        self.augmentation_report: Dict[str, Any] = {"status": "not_run"}
        self.preflight_report: Dict[str, Any] = {"status": "not_run"}
        self.selection_report: Dict[str, Any] = {"status": "not_run"}
        self.split_summary: Dict[str, Any] = {}
        self._split_indices: Optional[Dict[str, List[int]]] = None

    def _load_yaml(self, path: Path) -> Dict[str, Any]:
        """Load YAML configuration."""
        with path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle)

    def _prepare_labels(self) -> None:
        """Conditionally augment labels before training."""
        if not self.auto_hf_augment:
            self.augmentation_report = {
                "status": "disabled",
                "output_labels_path": str(self.labels_path),
            }
            self.active_labels_path = self.labels_path
            return

        from scripts.hf_augment import DEFAULT_CONFIG_PATH, augment_labels_if_needed

        config_path = self.hf_config_path or DEFAULT_CONFIG_PATH
        report_dir = self.output_dir / "augmentation"
        report = augment_labels_if_needed(
            labels_path=self.labels_path,
            task_name=self.task_name,
            output_dir=report_dir,
            config_path=config_path,
            min_samples_per_class=self.min_samples_per_class,
            imbalance_ratio_threshold=self.imbalance_ratio_threshold,
            max_new_samples=self.hf_max_new_samples,
            allowed_licenses=self.allowed_hf_licenses,
            seed=self.split_seed,
        )
        self.augmentation_report = report

        out_path = report.get("output_labels_path")
        if isinstance(out_path, str) and out_path:
            self.active_labels_path = Path(out_path)
        else:
            self.active_labels_path = self.labels_path

        logger.info(
            "label_source={} augmentation_status={} imported_samples={}",
            self.active_labels_path,
            report.get("status"),
            report.get("imported_samples", 0),
        )

    def _run_preflight_assess(self) -> None:
        """Run initial task/data assessment and optional dogpile research."""
        if not self.run_preflight_assess:
            self.preflight_report = {"status": "disabled"}
            return
        from scripts.assess_task import assess_task

        self.preflight_report = assess_task(
            labels_path=self.labels_path,
            task_name=self.task_name,
            dogpile_when_uncertain=self.dogpile_when_uncertain,
            dogpile_threshold=self.dogpile_threshold,
        )
        logger.info(
            "preflight confidence={:.3f} family={} backbone={}",
            self.preflight_report.get("confidence_score", 0.0),
            self.preflight_report.get("recommendation", {}).get("family", "unknown"),
            self.preflight_report.get("recommendation", {}).get("backbone", "unknown"),
        )

    def _run_model_selection(self) -> None:
        """Run benchmark-first model selection and set active model name."""
        from scripts.model_selector import select_model

        try:
            self.selection_report = select_model(
                labels_path=self.active_labels_path,
                base_model=self.model_name,
                candidate_backbones=self.candidate_backbones,
                benchmark_first=self.benchmark_first,
                classifier_lab_first=self.classifier_lab_first,
                classifier_lab_data_dir=self.classifier_lab_data_dir,
                classifier_lab_timeout_sec=self.classifier_lab_timeout_sec,
                require_classifier_lab=self.require_classifier_lab,
                require_selection_pass=self.require_selection_pass,
                device=self.device,
                quick_epochs=self.quick_benchmark_epochs,
                quick_max_steps=self.quick_benchmark_max_steps,
                split_seed=self.split_seed,
            )
        except Exception as exc:
            self.selection_report = {
                "status": "failed",
                "error": str(exc),
                "selected_model": self.model_name,
                "path": "base_model_fallback",
            }
            logger.warning(
                "model selection failed; continuing with base model {}: {}",
                self.model_name,
                exc,
            )

        selected_model = self.selection_report.get("selected_model")
        if isinstance(selected_model, str) and selected_model.strip():
            if selected_model != self.model_name:
                logger.info(
                    "model selected via {}: {} -> {}",
                    self.selection_report.get("path", "unknown"),
                    self.model_name,
                    selected_model,
                )
            self.model_name = selected_model

        selection_report_path = self.output_dir / "model_selection_report.json"
        selection_report_path.write_text(
            json.dumps(self.selection_report, indent=2),
            encoding="utf-8",
        )
        logger.info("model selection report: {}", selection_report_path)
        if self.require_selection_pass and self.selection_report.get("status") != "ok":
            raise RuntimeError(
                f"model selection gate failed: {self.selection_report.get('path')}"
            )

    def run_phase1_hp_search(self, n_trials: int = 15) -> Dict[str, Any]:
        """Phase 1: Bayesian hyperparameter search with Optuna."""
        from scripts.bayesian_hyperparameter_search import objective
        import optuna

        logger.info("\n" + "=" * 60)
        logger.info("PHASE 1: Hyperparameter Search")
        logger.info("=" * 60)

        task_for_study = self.task_config.get("task_name", self.task_name)
        study_path = self.output_dir / "optuna_study.db"
        study = optuna.create_study(
            study_name=f"{task_for_study}_hp_search",
            storage=f"sqlite:///{study_path}",
            direction="minimize",
            load_if_exists=True,
        )

        study.optimize(
            lambda trial: objective(
                trial,
                model_name=self.model_name,
                labels_path=self.active_labels_path,
                max_steps=300,
                device=self.device,
            ),
            n_trials=n_trials,
            show_progress_bar=True,
        )

        best_params = study.best_params
        best_accuracy = -study.best_value

        logger.info("\nBest hyperparameters found:")
        logger.info("  Accuracy: {:.1%}", best_accuracy)
        for key, value in best_params.items():
            logger.info("  {}: {}", key, value)

        config_path = self.output_dir / "best_hyperparams.json"
        with config_path.open("w", encoding="utf-8") as handle:
            json.dump(
                {
                    "best_accuracy": best_accuracy,
                    "hyperparameters": best_params,
                    "model": self.model_name,
                    "n_trials": n_trials,
                },
                handle,
                indent=2,
            )

        logger.info("\nSaved to: {}", config_path)
        return best_params

    def _build_split_indices(self, labels: List[str]) -> Dict[str, List[int]]:
        """Build reproducible stratified train/val/holdout indices."""
        rng = random.Random(self.split_seed)
        by_label: Dict[str, List[int]] = defaultdict(list)
        for index, label in enumerate(labels):
            by_label[label].append(index)

        train: List[int] = []
        val: List[int] = []
        holdout: List[int] = []
        class_breakdown: Dict[str, Dict[str, int]] = {}

        for label, indices in sorted(by_label.items()):
            rng.shuffle(indices)
            total = len(indices)
            if total == 1:
                n_holdout = 0
                n_val = 0
            elif total == 2:
                n_holdout = 0
                n_val = 1
            else:
                n_holdout = max(1, int(round(total * self.holdout_ratio)))
                n_holdout = min(n_holdout, total - 2)
                remaining = total - n_holdout
                n_val = max(1, int(round(remaining * 0.15)))
                n_val = min(n_val, remaining - 1)

            holdout_part = indices[:n_holdout]
            val_part = indices[n_holdout : n_holdout + n_val]
            train_part = indices[n_holdout + n_val :]

            if not train_part and val_part:
                train_part.append(val_part.pop())
            if not train_part and holdout_part:
                train_part.append(holdout_part.pop())

            train.extend(train_part)
            val.extend(val_part)
            holdout.extend(holdout_part)
            class_breakdown[label] = {
                "train": len(train_part),
                "val": len(val_part),
                "holdout": len(holdout_part),
            }

        if not val and len(train) > 1:
            val.append(train.pop())

        if self.require_holdout_gate and not holdout and len(train) > 2:
            holdout.append(train.pop())

        rng.shuffle(train)
        rng.shuffle(val)
        rng.shuffle(holdout)

        self.split_summary = {
            "seed": self.split_seed,
            "train_count": len(train),
            "val_count": len(val),
            "holdout_count": len(holdout),
            "class_breakdown": class_breakdown,
        }
        return {"train": train, "val": val, "holdout": holdout}

    @staticmethod
    def _evaluate_loader(model: torch.nn.Module, loader: torch.utils.data.DataLoader, device: str) -> Dict[str, Any]:
        """Evaluate accuracy/F1 over one dataloader."""
        from sklearn.metrics import f1_score

        model.eval()
        all_preds: List[int] = []
        all_labels: List[int] = []
        with torch.no_grad():
            for images, text_feats, labels, _ in loader:
                images = images.to(device)
                text_feats = text_feats.to(device)
                labels = labels.to(device)
                logits, _ = model(images, text_feats)
                _, predicted = logits.max(1)
                all_preds.extend(predicted.cpu().numpy().tolist())
                all_labels.extend(labels.cpu().numpy().tolist())

        if not all_labels:
            return {"accuracy": None, "f1": None, "support": 0}

        correct = sum(1 for pred, label in zip(all_preds, all_labels) if pred == label)
        accuracy = correct / len(all_labels)
        f1 = f1_score(all_labels, all_preds, average="macro")
        return {"accuracy": float(accuracy), "f1": float(f1), "support": len(all_labels)}

    def _holdout_gate_pass(self, result: Dict[str, Any]) -> bool:
        """Return true when holdout gate constraints are met."""
        if not self.require_holdout_gate:
            return True
        holdout_acc = result.get("holdout_accuracy")
        holdout_f1 = result.get("holdout_f1")
        holdout_support = int(result.get("holdout_support", 0))
        if holdout_support == 0:
            return False
        if holdout_acc is None or holdout_f1 is None:
            return False
        return (
            float(holdout_acc) >= self.holdout_threshold
            and float(holdout_f1) >= self.holdout_threshold
        )

    def train_iteration(
        self,
        iteration: int,
        hyperparams: Dict[str, Any],
        checkpoint_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Train for N epochs and evaluate with validation + holdout."""
        from templates.vision_classifier import DocumentDataset, HybridClassifier
        from torch.utils.data import DataLoader, Subset
        from torchvision import transforms
        import torch.nn as nn
        import torch.optim as optim

        logger.info("\n{}", "=" * 60)
        logger.info("Iteration {}/{}", iteration + 1, self.max_iterations)
        logger.info("{}", "=" * 60)

        transform = transforms.Compose(
            [
                transforms.Resize((224, 224)),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.485, 0.456, 0.406],
                    std=[0.229, 0.224, 0.225],
                ),
            ]
        )

        dataset = DocumentDataset(self.active_labels_path, transform=transform)
        if self._split_indices is None:
            split_labels = [str(sample.get("label", "")) for sample in dataset.samples]
            self._split_indices = self._build_split_indices(split_labels)
            logger.info(
                "split counts train={} val={} holdout={}",
                len(self._split_indices["train"]),
                len(self._split_indices["val"]),
                len(self._split_indices["holdout"]),
            )

        train_subset = Subset(dataset, self._split_indices["train"])
        val_subset = Subset(dataset, self._split_indices["val"])
        holdout_subset = Subset(dataset, self._split_indices["holdout"])

        train_loader = DataLoader(
            train_subset,
            batch_size=hyperparams.get("batch_size", 16),
            shuffle=True,
            num_workers=4,
        )
        val_loader = DataLoader(val_subset, batch_size=16, shuffle=False, num_workers=4)
        holdout_loader = DataLoader(
            holdout_subset, batch_size=16, shuffle=False, num_workers=4
        )

        num_classes = len(dataset.label_to_idx)
        model = HybridClassifier(
            num_classes=num_classes,
            backbone=self.model_name,
            text_feature_dim=5,
        ).to(self.device)

        start_epoch = 0
        if checkpoint_path and checkpoint_path.exists():
            checkpoint = torch.load(checkpoint_path, map_location=self.device)
            model.load_state_dict(checkpoint["model_state_dict"])
            start_epoch = checkpoint.get("epoch", 0)
            logger.info("Resumed from epoch {}", start_epoch)

        optimizer_name = hyperparams.get("optimizer", "adamw")
        if optimizer_name == "adam":
            optimizer = optim.Adam(
                model.parameters(),
                lr=hyperparams.get("lr", 5e-4),
                weight_decay=hyperparams.get("weight_decay", 0.01),
            )
        elif optimizer_name == "adamw":
            optimizer = optim.AdamW(
                model.parameters(),
                lr=hyperparams.get("lr", 5e-4),
                weight_decay=hyperparams.get("weight_decay", 0.01),
            )
        else:
            optimizer = optim.SGD(
                model.parameters(),
                lr=hyperparams.get("lr", 1e-2),
                weight_decay=hyperparams.get("weight_decay", 1e-4),
                momentum=0.9,
            )

        criterion = nn.CrossEntropyLoss()
        for epoch in range(start_epoch, start_epoch + self.epochs_per_iteration):
            model.train()
            train_loss = 0.0

            for images, text_feats, labels, _ in train_loader:
                images = images.to(self.device)
                text_feats = text_feats.to(self.device)
                labels = labels.to(self.device)

                optimizer.zero_grad()
                logits, _ = model(images, text_feats)
                loss = criterion(logits, labels)
                loss.backward()
                optimizer.step()
                train_loss += loss.item()

            avg_train_loss = train_loss / max(1, len(train_loader))
            logger.info("Epoch {}: train_loss={:.4f}", epoch + 1, avg_train_loss)

        val_metrics = self._evaluate_loader(model, val_loader, self.device)
        holdout_metrics = self._evaluate_loader(model, holdout_loader, self.device)

        checkpoint_out = self.output_dir / f"iteration_{iteration + 1}.pt"
        torch.save(
            {
                "epoch": start_epoch + self.epochs_per_iteration,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "accuracy": val_metrics["accuracy"],
                "f1": val_metrics["f1"],
                "holdout_accuracy": holdout_metrics["accuracy"],
                "holdout_f1": holdout_metrics["f1"],
                "config": {"model": self.model_name, "hyperparams": hyperparams},
                "label_to_idx": dataset.label_to_idx,
                "idx_to_label": {str(v): k for k, v in dataset.label_to_idx.items()},
                "split_summary": self.split_summary,
            },
            checkpoint_out,
        )

        logger.info(
            "Val accuracy: {:.1%}, Val F1: {:.1%}",
            val_metrics["accuracy"] or 0.0,
            val_metrics["f1"] or 0.0,
        )
        if holdout_metrics["support"] > 0:
            logger.info(
                "Holdout accuracy: {:.1%}, Holdout F1: {:.1%} (threshold {:.1%})",
                holdout_metrics["accuracy"] or 0.0,
                holdout_metrics["f1"] or 0.0,
                self.holdout_threshold,
            )
        else:
            logger.warning("Holdout split is empty; holdout gate cannot pass.")

        return {
            "iteration": iteration + 1,
            "accuracy": val_metrics["accuracy"] or 0.0,
            "f1": val_metrics["f1"] or 0.0,
            "holdout_accuracy": holdout_metrics["accuracy"],
            "holdout_f1": holdout_metrics["f1"],
            "holdout_support": holdout_metrics["support"],
            "model_path": str(checkpoint_out),
            "holdout_gate_pass": self._holdout_gate_pass(
                {
                    "holdout_accuracy": holdout_metrics["accuracy"],
                    "holdout_f1": holdout_metrics["f1"],
                    "holdout_support": holdout_metrics["support"],
                }
            ),
        }

    def run_phase2_iterative_training(self, hyperparams: Dict[str, Any]) -> bool:
        """Phase 2: iterative training until quality + holdout thresholds are met."""
        logger.info("\n" + "=" * 60)
        logger.info("PHASE 2: Iterative Training")
        logger.info("=" * 60)
        logger.info("Val threshold: {:.1%}", self.quality_threshold)
        logger.info(
            "Holdout threshold: {:.1%} (required={})",
            self.holdout_threshold,
            self.require_holdout_gate,
        )
        logger.info("Max iterations: {}", self.max_iterations)
        logger.info("Epochs per iteration: {}", self.epochs_per_iteration)

        checkpoint_path = None
        for iteration in range(self.max_iterations):
            result = self.train_iteration(iteration, hyperparams, checkpoint_path)
            self.iteration_results.append(result)

            if result["accuracy"] > self.best_accuracy:
                self.best_accuracy = float(result["accuracy"])
                self.best_model_path = result["model_path"]

            if result["holdout_gate_pass"] and result["accuracy"] > self.best_promoted_accuracy:
                self.best_promoted_accuracy = float(result["accuracy"])
                self.best_promoted_model_path = result["model_path"]
                shutil.copy(result["model_path"], self.output_dir / "best_model.pt")

            threshold_met = (
                result["accuracy"] >= self.quality_threshold
                and result["f1"] >= self.quality_threshold
                and result["holdout_gate_pass"]
            )

            if threshold_met:
                console.print(
                    f"\n[bold green]✓ THRESHOLD MET at iteration {iteration + 1}![/bold green]"
                )
                console.print(f"  Val Accuracy: {result['accuracy']:.1%}")
                console.print(f"  Val F1: {result['f1']:.1%}")
                console.print(
                    f"  Holdout Accuracy: {result['holdout_accuracy']:.1%}"
                )
                console.print(f"  Holdout F1: {result['holdout_f1']:.1%}")
                return True

            console.print(
                f"\n[yellow]Iteration {iteration + 1}: "
                f"val_acc={result['accuracy']:.1%}, "
                f"val_f1={result['f1']:.1%}, "
                f"holdout_pass={result['holdout_gate_pass']}[/yellow]"
            )
            checkpoint_path = Path(result["model_path"])

        console.print("\n[bold red]✗ Max iterations reached without meeting thresholds[/bold red]")
        console.print(f"  Best val accuracy: {self.best_accuracy:.1%}")
        if self.require_holdout_gate:
            console.print(
                f"  Best promoted accuracy (holdout-passing): {self.best_promoted_accuracy:.1%}"
            )
        return False

    def run(self, run_hp_search: bool = False, hp_trials: int = 15) -> bool:
        """Run complete workflow."""
        self._run_preflight_assess()
        self._prepare_labels()
        self._run_model_selection()

        if run_hp_search:
            hyperparams = self.run_phase1_hp_search(n_trials=hp_trials)
        else:
            hp_path = self.output_dir / "best_hyperparams.json"
            if hp_path.exists():
                logger.info("Loading hyperparameters from {}", hp_path)
                with hp_path.open("r", encoding="utf-8") as handle:
                    data = json.load(handle)
                    hyperparams = data["hyperparameters"]
            else:
                logger.info("Using default hyperparameters from model registry")
                registry_path = Path(__file__).parent.parent / "model_registry.yaml"
                registry = self._load_yaml(registry_path)
                model_config = next(
                    (
                        model
                        for model in registry["models"]
                        if model["name"] == self.model_name
                    ),
                    None,
                )
                if model_config:
                    hp = model_config["hyperparameters"]

                    def get_default(param_name: str, fallback: Any) -> Any:
                        if param_name not in hp:
                            return fallback
                        value = hp[param_name]
                        if isinstance(value, dict) and "default" in value:
                            return value["default"]
                        return value

                    hyperparams = {
                        "lr": float(get_default("learning_rate", 5e-4)),
                        "weight_decay": float(get_default("weight_decay", 0.01)),
                        "dropout": float(get_default("dropout", 0.3)),
                        "batch_size": int(get_default("batch_size", 16)),
                        "optimizer": get_default("optimizer", "adamw"),
                    }
                else:
                    hyperparams = {
                        "lr": 5e-4,
                        "weight_decay": 0.01,
                        "dropout": 0.3,
                        "batch_size": 16,
                        "optimizer": "adamw",
                    }

        success = self.run_phase2_iterative_training(hyperparams)

        summary_path = self.output_dir / "training_summary.json"
        with summary_path.open("w", encoding="utf-8") as handle:
            json.dump(
                {
                    "task_name": self.task_name,
                    "model": self.model_name,
                    "quality_threshold": self.quality_threshold,
                    "holdout_threshold": self.holdout_threshold,
                    "require_holdout_gate": self.require_holdout_gate,
                    "threshold_met": success,
                    "best_accuracy": self.best_accuracy,
                    "best_model_path": str(self.best_model_path),
                    "best_promoted_accuracy": self.best_promoted_accuracy,
                    "best_promoted_model_path": str(self.best_promoted_model_path),
                    "active_labels_path": str(self.active_labels_path),
                    "preflight_report": self.preflight_report,
                    "augmentation_report": self.augmentation_report,
                    "selection_report": self.selection_report,
                    "split_summary": self.split_summary,
                    "iterations": self.iteration_results,
                    "hyperparameters": hyperparams,
                },
                handle,
                indent=2,
            )

        logger.info("\nTraining summary saved to: {}", summary_path)
        return success


def main(
    task: str = typer.Option(..., help="Task config name"),
    model: str = typer.Option(..., help="Model architecture name"),
    labels: Path = typer.Option(..., exists=True, file_okay=True, dir_okay=False),
    output_dir: Path = typer.Option(..., help="Output directory"),
    threshold: float = typer.Option(0.90, min=0.0, max=1.0),
    max_iterations: int = typer.Option(5, min=1),
    epochs_per_iter: int = typer.Option(10, min=1),
    run_hp_search: bool = typer.Option(
        False, help="Run Bayesian hyperparameter search before iterative training"
    ),
    hp_trials: int = typer.Option(15, min=1, help="HP search trials"),
    device: str = typer.Option(
        "cuda" if torch.cuda.is_available() else "cpu", help="Training device"
    ),
    auto_hf_augment: bool = typer.Option(
        True, help="Conditionally augment with Hugging Face datasets"
    ),
    run_preflight_assess: bool = typer.Option(
        True, help="Run initial task/data assess preflight"
    ),
    dogpile_when_uncertain: bool = typer.Option(
        True, help="Run dogpile during preflight when confidence is low"
    ),
    dogpile_threshold: float = typer.Option(
        0.70, min=0.0, max=1.0, help="Preflight confidence threshold for dogpile"
    ),
    hf_config: Optional[Path] = typer.Option(
        None, help="HF augmentation config path"
    ),
    min_samples_per_class: int = typer.Option(
        300, min=1, help="Trigger augmentation when class support is low"
    ),
    imbalance_ratio_threshold: float = typer.Option(
        0.35, min=0.0, max=1.0, help="Trigger augmentation when min/max ratio is low"
    ),
    hf_max_new_samples: int = typer.Option(3000, min=0),
    allowed_hf_licenses: str = typer.Option(
        "", help="Comma-separated license allowlist override"
    ),
    holdout_ratio: float = typer.Option(0.10, min=0.0, max=0.5),
    holdout_threshold: Optional[float] = typer.Option(
        None, help="Holdout promotion threshold (defaults to --threshold)"
    ),
    require_holdout_gate: bool = typer.Option(
        True, help="Require holdout pass before promoting best_model.pt"
    ),
    split_seed: int = typer.Option(42, help="Seed for split reproducibility"),
    benchmark_first: bool = typer.Option(
        True, help="Run benchmark-first model selection before training"
    ),
    classifier_lab_first: bool = typer.Option(
        True, help="Try classifier-lab benchmark before internal benchmark"
    ),
    classifier_lab_data_dir: Optional[Path] = typer.Option(
        None, help="Optional image dataset directory for classifier-lab benchmark"
    ),
    classifier_lab_timeout_sec: int = typer.Option(
        300, min=30, help="Timeout for classifier-lab benchmark command"
    ),
    require_classifier_lab: bool = typer.Option(
        True, help="Require classifier-lab benchmark success before training"
    ),
    require_selection_pass: bool = typer.Option(
        True, help="Fail training if model selection cannot produce a viable winner"
    ),
    candidate_backbones: str = typer.Option(
        "", help="Comma-separated candidate backbones for selection"
    ),
    quick_benchmark_epochs: int = typer.Option(
        1, min=1, help="Epochs per candidate for internal quick benchmark"
    ),
    quick_benchmark_max_steps: int = typer.Option(
        250, min=20, help="Max optimization steps per candidate benchmark"
    ),
) -> None:
    """Run iterative classifier training."""
    skill_dir = Path(__file__).parent.parent
    task_config_path = skill_dir / "configs" / f"{task}.yaml"
    if not task_config_path.exists():
        logger.error("Task config not found: {}", task_config_path)
        raise typer.Exit(code=1)

    allowed_licenses = [
        item.strip().lower()
        for item in allowed_hf_licenses.split(",")
        if item.strip()
    ]
    parsed_candidates = [
        item.strip() for item in candidate_backbones.split(",") if item.strip()
    ]

    trainer = IterativeTrainer(
        task_name=task,
        task_config_path=task_config_path,
        labels_path=labels,
        model_name=model,
        output_dir=output_dir,
        quality_threshold=threshold,
        max_iterations=max_iterations,
        epochs_per_iteration=epochs_per_iter,
        device=device,
        auto_hf_augment=auto_hf_augment,
        run_preflight_assess=run_preflight_assess,
        dogpile_when_uncertain=dogpile_when_uncertain,
        dogpile_threshold=dogpile_threshold,
        hf_config_path=hf_config,
        min_samples_per_class=min_samples_per_class,
        imbalance_ratio_threshold=imbalance_ratio_threshold,
        hf_max_new_samples=hf_max_new_samples,
        allowed_hf_licenses=allowed_licenses,
        holdout_ratio=holdout_ratio,
        holdout_threshold=holdout_threshold,
        require_holdout_gate=require_holdout_gate,
        split_seed=split_seed,
        benchmark_first=benchmark_first,
        classifier_lab_first=classifier_lab_first,
        classifier_lab_data_dir=classifier_lab_data_dir,
        classifier_lab_timeout_sec=classifier_lab_timeout_sec,
        require_classifier_lab=require_classifier_lab,
        require_selection_pass=require_selection_pass,
        candidate_backbones=parsed_candidates if parsed_candidates else None,
        quick_benchmark_epochs=quick_benchmark_epochs,
        quick_benchmark_max_steps=quick_benchmark_max_steps,
    )
    success = trainer.run(run_hp_search=run_hp_search, hp_trials=hp_trials)
    if not success:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    typer.run(main)
