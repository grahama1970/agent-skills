#!/usr/bin/env python3
"""
Create Train/Validation Splits

Reads labels from JSONL and creates stratified splits.
"""

import typer
import json
import random
from pathlib import Path
from collections import defaultdict
from loguru import logger
import sys

logger.remove()
logger.add(sys.stderr, level="INFO")


def create_splits(labels_path: Path, output_dir: Path, val_ratio: float = 0.15):
    """Create train/val splits."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load labels
    labels = []
    with open(labels_path) as f:
        for line in f:
            labels.append(json.loads(line))
            
    logger.info(f"Loaded {len(labels)} labels")
    
    # Stratify by label
    by_label = defaultdict(list)
    for label in labels:
        by_label[label["label"]].append(label)
        
    train_set = []
    val_set = []
    
    logger.info("Splits by class:")
    for label_name, items in by_label.items():
        # Shuffle
        random.shuffle(items)
        
        # Split
        n_val = max(1, int(len(items) * val_ratio))
        # Ensure at least one training item if possible
        if len(items) > 1:
            n_val = min(n_val, len(items) - 1)
        else:
            n_val = 0 # If only 1 item, put in train
            
        val_items = items[:n_val]
        train_items = items[n_val:]
        
        train_set.extend(train_items)
        val_set.extend(val_items)
        
        logger.info(f"  {label_name}: {len(train_items)} train, {len(val_items)} val")
        
    # Shuffle final sets
    random.shuffle(train_set)
    random.shuffle(val_set)
    
    # Save
    train_path = output_dir / "train.jsonl"
    val_path = output_dir / "val.jsonl"
    
    with open(train_path, "w") as f:
        for item in train_set:
            f.write(json.dumps(item) + "\n")
            
    with open(val_path, "w") as f:
        for item in val_set:
            f.write(json.dumps(item) + "\n")
            
    logger.info(f"Saved splits to {output_dir}")
    logger.info(f"  Train: {len(train_set)}")
    logger.info(f"  Val:   {len(val_set)}")


app = typer.Typer(help="Create train/val splits")


@app.command()
def main(
    labels: Path = typer.Option(..., help="Input labels JSONL"),
    output: Path = typer.Option(Path("data/splits"), help="Output directory"),
    val_ratio: float = typer.Option(0.15, help="Validation ratio"),
):
    create_splits(labels, output, val_ratio)


if __name__ == "__main__":
    app()
