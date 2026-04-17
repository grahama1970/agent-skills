"""text_classifier - templates.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

import json
import os
from typing import Dict, List, Optional

import numpy as np
import torch
from datasets import Dataset, load_metric
from sklearn.metrics import f1_score
from torch.utils.data import DataLoader
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    DataCollatorWithPadding,
    Trainer,
    TrainingArguments,
)

def load_data(train_file: str, val_file: str) -> Dict[str, Dataset]:
    train_data = [json.loads(line) for line in open(train_file)]
    val_data = [json.loads(line) for line in open(val_file)]

    train_dataset = Dataset.from_dict({
        "text": [x["text"] for x in train_data],
        "label": [x["label"] for x in train_data]
    })
    val_dataset = Dataset.from_dict({
        "text": [x["text"] for x in val_data],
        "label": [x["label"] for x in val_data]
    })

    return {"train": train_dataset, "val": val_dataset}

def preprocess_data(tokenizer, datasets: Dict[str, Dataset], max_length: int) -> Dict[str, Dataset]:
    def tokenize_function(examples):
        return tokenizer(examples["text"], truncation=True, max_length=max_length)

    tokenized_datasets = {
        k: v.map(tokenize_function, batched=True) for k, v in datasets.items()
    }
    return tokenized_datasets

def compute_metrics(eval_pred):
    logits, labels = eval_pred
    predictions = np.argmax(logits, axis=-1)
    return {"eval_f1_macro": f1_score(labels, predictions, average="macro")}

def train(
    train_file: str,
    val_file: str,
    output_dir: str,
    model_name: str,
    epochs: int,
    batch_size: int,
    learning_rate: float,
    max_length: int,
    early_stopping: int,
):
    datasets = load_data(train_file, val_file)
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    tokenized_datasets = preprocess_data(tokenizer, datasets, max_length)

    model = AutoModelForSequenceClassification.from_pretrained(
        model_name, num_labels=2
    )

    training_args = TrainingArguments(
        output_dir=output_dir,
        evaluation_strategy="epoch",
        learning_rate=learning_rate,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        num_train_epochs=epochs,
        weight_decay=0.01,
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="eval_f1_macro",
        greater_is_better=True,
        save_total_limit=early_stopping,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_datasets["train"],
        eval_dataset=tokenized_datasets["val"],
        tokenizer=tokenizer,
        compute_metrics=compute_metrics,
    )

    trainer.train()

    metrics = trainer.evaluate()
    with open(os.path.join(output_dir, "training_summary.json"), "w") as f:
        json.dump({"val_metrics": metrics}, f)

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--train-file", required=True)
    parser.add_argument("--val-file", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--max-length", type=int, default=128)
    parser.add_argument("--early-stopping", type=int, default=3)
    args = parser.parse_args()

    train(
        args.train_file,
        args.val_file,
        args.output_dir,
        args.model,
        args.epochs,
        args.batch_size,
        args.learning_rate,
        args.max_length,
        args.early_stopping,
    )