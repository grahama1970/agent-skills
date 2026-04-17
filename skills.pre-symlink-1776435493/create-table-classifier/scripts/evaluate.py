#!/usr/bin/env python3
"""
Evaluation and data utilities for Table Strategy Classifier.

Commands:
- split: Split collected data into train/eval sets
- stats: Show dataset statistics
- run: Evaluate model on holdout set
"""

import os
import json
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Optional

try:
    import typer
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "typer", "-q"],
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )
    import typer

import torch
from loguru import logger
from tqdm import tqdm

# Local imports
from train_sft import (
    TableStrategyModel,
    TableDataset,
    STRATEGIES,
    STRATEGY_TO_IDX,
    evaluate as sft_evaluate,
)
from inference import TableStrategyPredictor

app = typer.Typer(help="Evaluation and data utilities")

# Paths
SKILL_DIR = Path(__file__).parent.parent
DATA_DIR = SKILL_DIR / "data"
LABELS_DIR = DATA_DIR / "labels"
MODELS_DIR = SKILL_DIR / "models"


@app.command()
def split(
    input_file: Path = typer.Option(
        LABELS_DIR / "collected.jsonl",
        help="Input JSONL file"
    ),
    train_ratio: float = typer.Option(0.85, help="Train split ratio"),
    seed: int = typer.Option(42, help="Random seed"),
    stratify: bool = typer.Option(True, help="Stratify by strategy"),
):
    """
    Split data into train/eval sets.

    Examples:
        ./run.sh split --input data/labels/collected.jsonl --train-ratio 0.85
    """
    if not input_file.exists():
        logger.error(f"Input file not found: {input_file}")
        raise typer.Exit(1)

    # Load data
    examples = []
    with input_file.open() as f:
        for line in f:
            examples.append(json.loads(line))

    logger.info(f"Loaded {len(examples)} examples")

    # Set seed
    random.seed(seed)

    if stratify:
        # Group by strategy
        by_strategy = {}
        for ex in examples:
            s = ex.get("strategy", "unknown")
            if s not in by_strategy:
                by_strategy[s] = []
            by_strategy[s].append(ex)

        train = []
        eval_set = []

        for strategy, exs in by_strategy.items():
            random.shuffle(exs)
            split_idx = int(len(exs) * train_ratio)
            train.extend(exs[:split_idx])
            eval_set.extend(exs[split_idx:])
    else:
        random.shuffle(examples)
        split_idx = int(len(examples) * train_ratio)
        train = examples[:split_idx]
        eval_set = examples[split_idx:]

    # Shuffle again
    random.shuffle(train)
    random.shuffle(eval_set)

    # Write output
    train_file = LABELS_DIR / "train.jsonl"
    eval_file = LABELS_DIR / "eval.jsonl"

    with train_file.open("w") as f:
        for ex in train:
            f.write(json.dumps(ex) + "\n")

    with eval_file.open("w") as f:
        for ex in eval_set:
            f.write(json.dumps(ex) + "\n")

    logger.info(f"Train: {len(train)} examples -> {train_file}")
    logger.info(f"Eval: {len(eval_set)} examples -> {eval_file}")

    # Show distribution
    train_dist = Counter(ex.get("strategy", "unknown") for ex in train)
    eval_dist = Counter(ex.get("strategy", "unknown") for ex in eval_set)

    print("\nTrain distribution:")
    for s, c in sorted(train_dist.items(), key=lambda x: -x[1]):
        print(f"  {s}: {c}")

    print("\nEval distribution:")
    for s, c in sorted(eval_dist.items(), key=lambda x: -x[1]):
        print(f"  {s}: {c}")


@app.command()
def stats(
    data_file: Path = typer.Option(
        LABELS_DIR / "collected.jsonl",
        help="Data file to analyze"
    ),
):
    """
    Show dataset statistics.

    Examples:
        ./run.sh stats --data-file data/labels/train.jsonl
    """
    if not data_file.exists():
        logger.error(f"File not found: {data_file}")
        raise typer.Exit(1)

    examples = []
    with data_file.open() as f:
        for line in f:
            examples.append(json.loads(line))

    print(f"\n{'='*50}")
    print(f"Dataset: {data_file}")
    print(f"{'='*50}")

    print(f"\nTotal examples: {len(examples)}")

    # Strategy distribution
    strategies = Counter(ex.get("strategy", "unknown") for ex in examples)
    print("\nStrategy distribution:")
    for s, c in sorted(strategies.items(), key=lambda x: -x[1]):
        pct = 100 * c / len(examples)
        print(f"  {s:20s}: {c:5d} ({pct:5.1f}%)")

    # Preset distribution
    presets = Counter(ex.get("preset", "unknown") for ex in examples)
    print("\nPreset distribution:")
    for p, c in sorted(presets.items(), key=lambda x: -x[1])[:10]:
        pct = 100 * c / len(examples)
        print(f"  {p:20s}: {c:5d} ({pct:5.1f}%)")

    # Quality distribution
    qualities = [ex.get("quality_score", 0) for ex in examples]
    if qualities:
        print(f"\nQuality scores:")
        print(f"  Mean: {sum(qualities)/len(qualities):.3f}")
        print(f"  Min:  {min(qualities):.3f}")
        print(f"  Max:  {max(qualities):.3f}")

    # Parameter stats
    line_scales = [ex.get("params", {}).get("line_scale", 15) for ex in examples]
    edge_tols = [ex.get("params", {}).get("edge_tol", 300) for ex in examples]

    print(f"\nParameter ranges:")
    print(f"  line_scale: {min(line_scales)}-{max(line_scales)} (mean: {sum(line_scales)/len(line_scales):.1f})")
    print(f"  edge_tol:   {min(edge_tols)}-{max(edge_tols)} (mean: {sum(edge_tols)/len(edge_tols):.1f})")

    # Image availability
    with_images = sum(1 for ex in examples if ex.get("image_path"))
    print(f"\nExamples with images: {with_images} ({100*with_images/len(examples):.1f}%)")


@app.command()
def run(
    model_path: Path = typer.Option(
        MODELS_DIR / "table-classifier-final",
        help="Model to evaluate"
    ),
    eval_file: Path = typer.Option(
        LABELS_DIR / "eval.jsonl",
        help="Evaluation data"
    ),
    batch_size: int = typer.Option(32, help="Batch size"),
    output_file: Optional[Path] = typer.Option(None, help="Output metrics JSON"),
):
    """
    Evaluate model on holdout set.

    Computes:
    - Strategy accuracy
    - Parameter MAE
    - Per-strategy metrics
    - Fallback rate prediction

    Examples:
        ./run.sh evaluate --model models/final --eval-file data/labels/eval.jsonl
    """
    if not eval_file.exists():
        logger.error(f"Eval file not found: {eval_file}")
        raise typer.Exit(1)

    device = "cuda" if torch.cuda.is_available() else "cpu"

    # Load model
    predictor = TableStrategyPredictor(model_path, device)
    if predictor.model is None:
        logger.error("No model loaded")
        raise typer.Exit(1)

    # Load data
    from torch.utils.data import DataLoader
    dataset = TableDataset(eval_file, DATA_DIR / "images", augment=False)
    dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=False)

    # Evaluate using SFT metrics
    metrics = sft_evaluate(predictor.model, dataloader, device)

    print(f"\n{'='*50}")
    print("Evaluation Results")
    print(f"{'='*50}")
    print(f"Strategy Accuracy: {metrics['strategy_accuracy']:.4f}")
    print(f"Parameter MAE: {metrics['param_mae']:.2f}")

    # Per-strategy analysis
    examples = []
    with eval_file.open() as f:
        for line in f:
            examples.append(json.loads(line))

    strategy_counts = Counter()
    strategy_correct = Counter()

    for ex in tqdm(examples, desc="Detailed evaluation"):
        img_path = ex.get("image_path")
        if not img_path:
            continue

        full_path = SKILL_DIR / img_path
        if not full_path.exists():
            continue

        true_strategy = ex.get("strategy", "unknown")
        preset = ex.get("preset", "unknown")

        pred = predictor.predict(full_path, preset)

        strategy_counts[true_strategy] += 1
        if pred.strategy == true_strategy:
            strategy_correct[true_strategy] += 1

    print("\nPer-Strategy Accuracy:")
    for s in STRATEGIES:
        if strategy_counts[s] > 0:
            acc = strategy_correct[s] / strategy_counts[s]
            print(f"  {s:20s}: {acc:.4f} ({strategy_correct[s]}/{strategy_counts[s]})")

    # Thresholds
    print("\nThreshold Checks:")
    strategy_acc = metrics['strategy_accuracy']
    param_mae = metrics['param_mae']

    print(f"  Strategy accuracy >= 85%: {'PASS' if strategy_acc >= 0.85 else 'FAIL'} ({strategy_acc:.1%})")
    print(f"  Parameter MAE <= 5: {'PASS' if param_mae <= 5 else 'FAIL'} ({param_mae:.2f})")

    # Save metrics
    if output_file:
        results = {
            "strategy_accuracy": metrics['strategy_accuracy'],
            "param_mae": metrics['param_mae'],
            "per_strategy": {
                s: {
                    "count": strategy_counts[s],
                    "correct": strategy_correct[s],
                    "accuracy": strategy_correct[s] / max(strategy_counts[s], 1),
                }
                for s in STRATEGIES
            },
            "thresholds": {
                "strategy_accuracy": strategy_acc >= 0.85,
                "param_mae": param_mae <= 5,
            },
        }
        output_file.write_text(json.dumps(results, indent=2))
        logger.info(f"Saved metrics to {output_file}")


if __name__ == "__main__":
    app()
