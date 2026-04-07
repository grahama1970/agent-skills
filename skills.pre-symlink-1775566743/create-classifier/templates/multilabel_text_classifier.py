#!/usr/bin/env python3
"""Multi-Label Text Classifier Training for Federated Taxonomy Bridges.

Usage:
    python multilabel_text_classifier.py \
        --train-file data/bridge_classifier/train.jsonl \
        --val-file data/bridge_classifier/val.jsonl \
        --output-dir models/bridge_classifier \
        --model distilbert-base-uncased \
        --epochs 10

Training data format (JSONL):
    {"text": "Evaluate the UI for accessibility", "labels": ["Precision", "Fragility"]}
    {"text": "How does stress affect decisions", "labels": ["Resilience", "Fragility", "Corruption"]}

Based on HuggingFace Transformers multi-label classification.
"""

import typer
import json
from pathlib import Path
from typing import Any

import numpy as np
import torch
from datasets import Dataset, DatasetDict
from loguru import logger
from sklearn.metrics import f1_score, hamming_loss, precision_recall_fscore_support
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    DataCollatorWithPadding,
    EarlyStoppingCallback,
    Trainer,
    TrainingArguments,
)


# Federated Taxonomy bridges
BRIDGE_LABELS = [
    "Corruption",
    "Precision",
    "Resilience",
    "Fragility",
    "Loyalty",
    "Stealth",
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load JSONL file."""
    data = []
    with open(path) as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))
    return data


def labels_to_vector(labels: list[str], label2id: dict[str, int]) -> list[float]:
    """Convert list of labels to multi-hot vector."""
    vector = [0.0] * len(label2id)
    for label in labels:
        if label in label2id:
            vector[label2id[label]] = 1.0
    return vector


def vector_to_labels(vector: list[float], id2label: dict[int, str], threshold: float = 0.5) -> list[str]:
    """Convert prediction vector to list of labels."""
    return [id2label[i] for i, v in enumerate(vector) if v >= threshold]


def compute_metrics(eval_pred, threshold: float = 0.5):
    """Compute multi-label evaluation metrics."""
    logits, labels = eval_pred
    # Apply sigmoid to get probabilities
    probs = torch.sigmoid(torch.tensor(logits)).numpy()
    # Threshold to get predictions
    predictions = (probs >= threshold).astype(int)
    labels = labels.astype(int)

    # Micro F1 (global)
    f1_micro = f1_score(labels, predictions, average="micro", zero_division=0)
    # Macro F1 (per-class average)
    f1_macro = f1_score(labels, predictions, average="macro", zero_division=0)
    # Hamming loss (fraction of wrong labels)
    h_loss = hamming_loss(labels, predictions)
    # Exact match ratio (all labels correct)
    exact_match = np.all(predictions == labels, axis=1).mean()

    # Per-class metrics
    precision, recall, f1_per_class, _ = precision_recall_fscore_support(
        labels, predictions, average=None, zero_division=0
    )

    return {
        "f1_micro": f1_micro,
        "f1_macro": f1_macro,
        "hamming_loss": h_loss,
        "exact_match_ratio": exact_match,
        # Per-class F1 for debugging
        "f1_Corruption": f1_per_class[0] if len(f1_per_class) > 0 else 0,
        "f1_Precision": f1_per_class[1] if len(f1_per_class) > 1 else 0,
        "f1_Resilience": f1_per_class[2] if len(f1_per_class) > 2 else 0,
        "f1_Fragility": f1_per_class[3] if len(f1_per_class) > 3 else 0,
        "f1_Loyalty": f1_per_class[4] if len(f1_per_class) > 4 else 0,
        "f1_Stealth": f1_per_class[5] if len(f1_per_class) > 5 else 0,
    }


class MultiLabelTrainer(Trainer):
    """Trainer with BCEWithLogitsLoss or FocalBCE for multi-label classification."""

    def __init__(self, *args, pos_weight=None, focal_gamma: float = 0.0, **kwargs):
        super().__init__(*args, **kwargs)
        self.pos_weight = pos_weight
        self.focal_gamma = focal_gamma

    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        labels = inputs.pop("labels")
        outputs = model(**inputs)
        logits = outputs.logits

        if self.focal_gamma > 0 and self.pos_weight is not None:
            loss_fct = FocalBCEWithLogitsLoss(
                gamma=self.focal_gamma,
                pos_weight=self.pos_weight.to(logits.device),
            )
        elif self.pos_weight is not None:
            weights = self.pos_weight.to(logits.device)
            loss_fct = torch.nn.BCEWithLogitsLoss(pos_weight=weights)
        else:
            loss_fct = torch.nn.BCEWithLogitsLoss()

        loss = loss_fct(logits, labels.float())
        return (loss, outputs) if return_outputs else loss


class FocalBCEWithLogitsLoss(torch.nn.Module):
    """Focal loss for multi-label classification (from classifier-lab multilabel_benchmark.py).

    Downweights easy examples, focuses on hard ones. gamma=0 is standard BCE.
    """

    def __init__(self, gamma: float, pos_weight: torch.Tensor):
        super().__init__()
        self.gamma = gamma
        self.pos_weight = pos_weight

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        p = torch.sigmoid(logits)
        p_t = targets * p + (1 - targets) * (1 - p)
        focal_weight = (1 - p_t) ** self.gamma
        bce = torch.nn.functional.binary_cross_entropy_with_logits(
            logits, targets, reduction="none"
        )
        weight = targets * self.pos_weight.unsqueeze(0) + (1 - targets)
        loss = focal_weight * weight * bce
        return loss.mean()


def main(
    train_file: str = typer.Option(..., help="Path to training JSONL"),
    val_file: str = typer.Option(..., help="Path to validation JSONL"),
    test_file: str = typer.Option(None, help="Path to test JSONL"),
    output_dir: Path = typer.Option(..., help="Output directory for model"),
    model: str = typer.Option("distilbert-base-uncased", help="HuggingFace model name"),
    epochs: int = typer.Option(10, help="Training epochs"),
    batch_size: int = typer.Option(32, help="Batch size"),
    learning_rate: float = typer.Option(2e-5, help="Learning rate"),
    max_length: int = typer.Option(256, help="Max token length"),
    warmup_ratio: float = typer.Option(0.1, help="Warmup ratio"),
    weight_decay: float = typer.Option(0.01, help="Weight decay"),
    seed: int = typer.Option(42, help="Random seed"),
    pos_weight_auto: bool = typer.Option(True, help="Auto-compute positive class weights"),
    early_stopping: int = typer.Option(3, help="Early stopping patience (0=disabled)"),
    threshold: float = typer.Option(0.5, help="Classification threshold"),
    focal_gamma: float = typer.Option(0.0, help="Focal loss gamma (0=standard BCE)"),
    labels_list: str = typer.Option(None, help="Comma-separated label names (auto-detected if omitted)"),
):

    # Set seed
    torch.manual_seed(seed)
    np.random.seed(seed)

    # Load data FIRST so we can detect labels
    logger.info(f"Loading training data from {train_file}")
    train_data = load_jsonl(train_file)
    val_data = load_jsonl(val_file)

    # Auto-detect labels from data if not provided
    if labels_list:
        labels = [l.strip() for l in labels_list.split(",")]
    else:
        label_set = set()
        for d in train_data + val_data:
            for lbl in d.get("labels", []):
                label_set.add(lbl)
        labels = sorted(label_set)
        if not labels:
            labels = BRIDGE_LABELS
            logger.warning("No labels found in data, falling back to BRIDGE_LABELS")

    # Label mapping
    label2id = {label: i for i, label in enumerate(labels)}
    id2label = {i: label for label, i in label2id.items()}
    num_labels = len(labels)

    logger.info(f"Labels ({num_labels}): {labels}")
    logger.info(f"Train samples: {len(train_data)}, Val samples: {len(val_data)}")

    # --- Class imbalance detection (ported from classifier-lab) ---
    label_counts = {label: 0 for label in labels}
    for d in train_data:
        for label in d.get("labels", []):
            if label in label_counts:
                label_counts[label] += 1

    logger.info("Class distribution:")
    for label in sorted(label_counts, key=label_counts.get, reverse=True):
        pct = 100.0 * label_counts[label] / max(len(train_data), 1)
        logger.info(f"  {label:>20s}: {label_counts[label]:>6d} ({pct:5.1f}%)")

    max_count = max(label_counts.values()) if label_counts else 1
    min_count = max(min(label_counts.values()), 1) if label_counts else 1
    imbalance_ratio = max_count / min_count
    if imbalance_ratio > 20:
        logger.warning(
            f"CLASS IMBALANCE DETECTED: {imbalance_ratio:.0f}:1 ratio. "
            f"Consider --focal-gamma 2.0 or rebalancing data."
        )

    # Calculate positive weights
    pos_weight = None
    if pos_weight_auto:
        total = len(train_data)
        pos_weight = torch.clamp(
            torch.tensor([
                (total - label_counts[label]) / max(label_counts[label], 1)
                for label in labels
            ]),
            min=1.0,
            max=50.0,
        )
        logger.info(f"Positive weights (clamped [1,50]): {dict(zip(labels, pos_weight.tolist()))}")

    # Create datasets
    def create_dataset(data: list[dict]) -> Dataset:
        texts = [d["text"] for d in data]
        label_vectors = [labels_to_vector(d.get("labels", []), label2id) for d in data]
        return Dataset.from_dict({
            "text": texts,
            "labels": label_vectors,
        })

    datasets = DatasetDict({
        "train": create_dataset(train_data),
        "validation": create_dataset(val_data),
    })

    if test_file:
        test_data = load_jsonl(test_file)
        datasets["test"] = create_dataset(test_data)

    # Load tokenizer and model
    model_name = model  # save before shadowing
    logger.info(f"Loading model: {model_name}")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name,
        num_labels=num_labels,
        id2label=id2label,
        label2id=label2id,
        problem_type="multi_label_classification",
    )

    # Tokenize
    def tokenize_function(examples):
        return tokenizer(
            examples["text"],
            truncation=True,
            max_length=max_length,
            padding=False,
        )

    logger.info("Tokenizing datasets...")
    tokenized_datasets = datasets.map(
        tokenize_function,
        batched=True,
        remove_columns=["text"],
    )

    # Data collator
    data_collator = DataCollatorWithPadding(tokenizer=tokenizer)

    # Training arguments
    output_dir = Path(output_dir) if not isinstance(output_dir, Path) else output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    training_args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size * 2,
        learning_rate=learning_rate,
        warmup_ratio=warmup_ratio,
        weight_decay=weight_decay,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1_macro",
        greater_is_better=True,
        logging_dir=str(output_dir / "logs"),
        logging_steps=50,
        save_total_limit=3,
        seed=seed,
        fp16=torch.cuda.is_available(),
        report_to="none",
    )

    # Callbacks
    callbacks = []
    if early_stopping > 0:
        callbacks.append(EarlyStoppingCallback(early_stopping_patience=early_stopping))

    if focal_gamma > 0:
        logger.info(f"Using Focal Loss with gamma={focal_gamma}")

    # Trainer
    trainer = MultiLabelTrainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_datasets["train"],
        eval_dataset=tokenized_datasets["validation"],
        processing_class=tokenizer,
        data_collator=data_collator,
        compute_metrics=compute_metrics,
        callbacks=callbacks,
        pos_weight=pos_weight,
        focal_gamma=focal_gamma,
    )

    # Train
    logger.info("Starting training...")
    trainer.train()

    # Evaluate
    logger.info("Evaluating on validation set...")
    val_metrics = trainer.evaluate()
    logger.info(f"Validation metrics: {val_metrics}")

    if test_file:
        logger.info("Evaluating on test set...")
        test_metrics = trainer.evaluate(tokenized_datasets["test"])
        logger.info(f"Test metrics: {test_metrics}")

    # Save best model
    best_model_dir = output_dir / "best_model"
    trainer.save_model(str(best_model_dir))
    tokenizer.save_pretrained(str(best_model_dir))

    # Save label mapping and config
    config = {
        "label2id": label2id,
        "id2label": {str(k): v for k, v in id2label.items()},
        "threshold": threshold,
        "labels": labels,
    }
    with open(best_model_dir / "bridge_config.json", "w") as f:
        json.dump(config, f, indent=2)

    # Save training summary
    summary = {
        "model": model_name,
        "epochs": epochs,
        "train_samples": len(train_data),
        "val_samples": len(val_data),
        "labels": labels,
        "threshold": threshold,
        "pos_weight": pos_weight.tolist() if pos_weight is not None else None,
        "val_metrics": {k: float(v) for k, v in val_metrics.items()},
    }
    if test_file:
        summary["test_metrics"] = {k: float(v) for k, v in test_metrics.items()}

    with open(output_dir / "training_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    logger.info(f"Training complete! Best model saved to {best_model_dir}")
    logger.info(f"Final F1 (macro): {val_metrics.get('eval_f1_macro', 'N/A'):.4f}")
    logger.info(f"Final F1 (micro): {val_metrics.get('eval_f1_micro', 'N/A'):.4f}")

    return val_metrics


if __name__ == "__main__":
    typer.run(main)
