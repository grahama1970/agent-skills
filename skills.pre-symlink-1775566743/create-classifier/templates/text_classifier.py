#!/usr/bin/env python3
"""Text Classifier Training - DeBERTa-based for Space/Generic IT Classification.

Usage:
    python text_classifier.py \
        --train-file data/space_classifier_v2/train.jsonl \
        --val-file data/space_classifier_v2/val.jsonl \
        --output-dir models/space_classifier \
        --model microsoft/deberta-v3-small \
        --epochs 10

Based on HuggingFace Transformers text classification pipeline.
"""

import typer
import json
import os
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import torch
from datasets import Dataset, DatasetDict
from loguru import logger
from sklearn.metrics import accuracy_score, f1_score, precision_recall_fscore_support
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    DataCollatorWithPadding,
    EarlyStoppingCallback,
    Trainer,
    TrainingArguments,
)


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Load JSONL file."""
    data = []
    with open(path) as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))
    return data


def compute_metrics(eval_pred):
    """Compute evaluation metrics."""
    logits, labels = eval_pred
    predictions = np.argmax(logits, axis=-1)

    accuracy = accuracy_score(labels, predictions)
    precision, recall, f1, _ = precision_recall_fscore_support(
        labels, predictions, average="weighted"
    )
    f1_macro = f1_score(labels, predictions, average="macro")

    return {
        "accuracy": accuracy,
        "f1": f1,
        "f1_macro": f1_macro,
        "precision": precision,
        "recall": recall,
    }


def main(
    train_file: str = typer.Option(..., help=""),
    val_file: str = typer.Option(..., help=""),
    test_file: str = typer.Option(None, help=""),
    output_dir: str = typer.Option(..., help=""),
    model: str = typer.Option("microsoft/deberta-v3-small", help=""),
    epochs: int = typer.Option(10, help=""),
    batch_size: int = typer.Option(16, help=""),
    learning_rate: float = typer.Option(2e-5, help=""),
    max_length: int = typer.Option(512, help=""),
    warmup_ratio: float = typer.Option(0.1, help=""),
    weight_decay: float = typer.Option(0.01, help=""),
    seed: int = typer.Option(42, help=""),
    early_stopping: int = typer.Option(3, help="Early stopping patience (0 to disable)"),
):

    output_dir = Path(output_dir)

    # Set seed
    torch.manual_seed(seed)
    np.random.seed(seed)

    # Load data
    logger.info(f"Loading training data from {train_file}")
    train_data = load_jsonl(train_file)
    val_data = load_jsonl(val_file)

    logger.info(f"Train samples: {len(train_data)}, Val samples: {len(val_data)}")

    # Get label mapping — accept "label", "class", or "className" field
    def get_label(d: dict) -> str:
        return d.get("label", d.get("class", d.get("className", "")))
    labels = sorted(set(get_label(d) for d in train_data if get_label(d)))
    label2id = {label: i for i, label in enumerate(labels)}
    id2label = {i: label for label, i in label2id.items()}
    num_labels = len(labels)

    logger.info(f"Labels: {labels}")
    logger.info(f"Label mapping: {label2id}")

    # Calculate class weights if needed
    class_weights = None
    if class_weights:
        label_counts = {}
        for d in train_data:
            label_counts[get_label(d)] = label_counts.get(get_label(d), 0) + 1
        total = sum(label_counts.values())
        class_weights = torch.tensor([
            total / (num_labels * label_counts[id2label[i]])
            for i in range(num_labels)
        ])
        logger.info(f"Class weights: {dict(zip(labels, class_weights.tolist()))}")

    # Create datasets
    def create_dataset(data: List[Dict]) -> Dataset:
        return Dataset.from_dict({
            "text": [d["text"] for d in data],
            "label": [label2id[get_label(d)] for d in data],
        })

    datasets = DatasetDict({
        "train": create_dataset(train_data),
        "validation": create_dataset(val_data),
    })

    if test_file:
        test_data = load_jsonl(test_file)
        datasets["test"] = create_dataset(test_data)

    # Load tokenizer and model
    model_name = model
    logger.info(f"Loading model: {model_name}")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name,
        num_labels=num_labels,
        id2label=id2label,
        label2id=label2id,
        ignore_mismatched_sizes=True,
    )

    # Tokenize
    def tokenize_function(examples):
        return tokenizer(
            examples["text"],
            truncation=True,
            max_length=max_length,
            padding=False,  # Will pad in data collator
        )

    logger.info("Tokenizing datasets...")
    tokenized_datasets = datasets.map(
        tokenize_function,
        batched=True,
        remove_columns=["text"],
    )

    # Data collator
    data_collator = DataCollatorWithPadding(tokenizer=tokenizer)

    # Custom trainer with class weights
    class WeightedTrainer(Trainer):
        def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
            labels = inputs.pop("labels")
            outputs = model(**inputs)
            logits = outputs.logits

            if class_weights is not None:
                weights = class_weights.to(logits.device)
                loss_fct = torch.nn.CrossEntropyLoss(weight=weights)
            else:
                loss_fct = torch.nn.CrossEntropyLoss()

            loss = loss_fct(logits.view(-1, self.model.config.num_labels), labels.view(-1))
            return (loss, outputs) if return_outputs else loss

    # Training arguments
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

    # Trainer
    trainer_cls = WeightedTrainer if class_weights else Trainer
    trainer = trainer_cls(
        model=model,
        args=training_args,
        train_dataset=tokenized_datasets["train"],
        eval_dataset=tokenized_datasets["validation"],
        processing_class=tokenizer,  # Updated for transformers 5.x
        data_collator=data_collator,
        compute_metrics=compute_metrics,
        callbacks=callbacks,
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

    # Save label mapping
    with open(best_model_dir / "label_map.json", "w") as f:
        json.dump({"label2id": label2id, "id2label": id2label}, f, indent=2)

    # Save training summary
    summary = {
        "model": model_name,
        "epochs": epochs,
        "train_samples": len(train_data),
        "val_samples": len(val_data),
        "labels": labels,
        "class_weights": class_weights.tolist() if class_weights is not None else None,
        "val_metrics": val_metrics,
    }
    if test_file:
        summary["test_metrics"] = test_metrics

    with open(output_dir / "training_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    logger.info(f"Training complete! Best model saved to {best_model_dir}")
    logger.info(f"Final F1 (macro): {val_metrics.get('eval_f1_macro', 'N/A'):.4f}")

    return val_metrics


if __name__ == "__main__":
    typer.run(main)
