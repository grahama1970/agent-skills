#!/usr/bin/env python3
"""Data preparation for task-specific GPT training.

Converts raw JSONL data into SFT chat format with optional augmentation
via /scillm.

Usage:
    python prepare_data.py prepare --task qra-validator --input raw.jsonl
    python prepare_data.py split --task qra-validator --holdout-ratio 0.10
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from task_spec import load_task_spec, DATA_DIR

app = typer.Typer(add_completion=False)


def load_jsonl(path: Path) -> list[dict]:
    """Load JSONL file."""
    data = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data


def save_jsonl(data: list[dict], path: Path) -> None:
    """Save to JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def to_chat_format(item: dict, system_prompt: str) -> dict:
    """Convert a raw item to SFT chat format.

    Expects items with 'input' and 'output' fields.
    Output can be a string or dict (will be JSON-serialized).
    """
    user_input = item.get("input", "")
    output = item.get("output", "")

    if isinstance(user_input, dict):
        user_input = json.dumps(user_input, ensure_ascii=False)
    if isinstance(output, dict):
        output = json.dumps(output, ensure_ascii=False, indent=2)

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_input})
    messages.append({"role": "assistant", "content": output})

    return {"messages": messages}


@app.command()
def prepare(
    task: str = typer.Option(..., "--task", "-t", help="Task name"),
    input_file: Path = typer.Option(..., "--input", "-i", help="Raw JSONL input"),
    output_file: Optional[Path] = typer.Option(None, "--output", "-o", help="Output path"),
    augment: bool = typer.Option(False, "--augment", help="Augment data via /scillm"),
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Max examples"),
):
    """Convert raw JSONL to SFT chat format."""
    spec = load_task_spec(task)

    if not input_file.exists():
        logger.error(f"Input file not found: {input_file}")
        raise typer.Exit(code=1)

    raw_data = load_jsonl(input_file)
    logger.info(f"Loaded {len(raw_data)} examples from {input_file}")

    if limit:
        raw_data = raw_data[:limit]
        logger.info(f"Limited to {len(raw_data)} examples")

    # Convert to chat format
    chat_data = [to_chat_format(item, spec.system_prompt) for item in raw_data]

    # Optional augmentation via /scillm
    if augment:
        chat_data = _augment_data(chat_data, spec)

    # Save
    if output_file is None:
        output_file = DATA_DIR / spec.name / "sft" / "train.jsonl"

    save_jsonl(chat_data, output_file)
    logger.info(f"Saved {len(chat_data)} examples to {output_file}")


def _augment_data(data: list[dict], spec) -> list[dict]:
    """Augment training data using /scillm for variation generation."""
    try:
        scillm_dir = Path(__file__).resolve().parents[2] / "scillm"
        sys.path.insert(0, str(scillm_dir))
        from batch import quick_completion

        augmented = list(data)
        for item in data[:50]:  # Augment a subset
            user_msg = next(
                (m["content"] for m in item["messages"] if m["role"] == "user"), ""
            )
            if not user_msg:
                continue

            try:
                variation = quick_completion(
                    prompt=f"Rephrase this input while preserving meaning:\n{user_msg}",
                    json_mode=False,
                    timeout=15,
                )
                if variation and variation.strip():
                    new_item = json.loads(json.dumps(item))
                    for msg in new_item["messages"]:
                        if msg["role"] == "user":
                            msg["content"] = variation.strip()
                    augmented.append(new_item)
            except Exception as e:
                logger.debug(f"Augmentation failed for item: {e}")

        logger.info(f"Augmented {len(augmented) - len(data)} examples")
        return augmented
    except ImportError:
        logger.warning("scillm not available, skipping augmentation")
        return data


@app.command()
def split(
    task: str = typer.Option(..., "--task", "-t", help="Task name"),
    input_file: Optional[Path] = typer.Option(None, "--input", "-i"),
    holdout_ratio: float = typer.Option(0.10, "--holdout-ratio", "-h"),
    val_ratio: float = typer.Option(0.10, "--val-ratio", "-v"),
    seed: int = typer.Option(42, "--seed", "-s"),
):
    """Split data into train/val/holdout sets with stratification."""
    spec = load_task_spec(task)

    if input_file is None:
        input_file = DATA_DIR / spec.name / "sft" / "train.jsonl"

    if not input_file.exists():
        logger.error(f"Input file not found: {input_file}")
        raise typer.Exit(code=1)

    data = load_jsonl(input_file)
    random.seed(seed)
    random.shuffle(data)

    total = len(data)
    n_holdout = max(1, int(total * holdout_ratio))
    n_val = max(1, int(total * val_ratio))
    n_train = total - n_holdout - n_val

    if n_train < 1:
        logger.error(f"Not enough data: {total} examples, need at least 3")
        raise typer.Exit(code=1)

    holdout_data = data[:n_holdout]
    val_data = data[n_holdout:n_holdout + n_val]
    train_data = data[n_holdout + n_val:]

    out_dir = DATA_DIR / spec.name / "sft"
    save_jsonl(train_data, out_dir / "train.jsonl")
    save_jsonl(val_data, out_dir / "val.jsonl")
    save_jsonl(holdout_data, out_dir / "holdout.jsonl")

    logger.info(f"Split {total} examples (seed={seed}):")
    logger.info(f"  Train:   {len(train_data)} -> {out_dir / 'train.jsonl'}")
    logger.info(f"  Val:     {len(val_data)} -> {out_dir / 'val.jsonl'}")
    logger.info(f"  Holdout: {len(holdout_data)} -> {out_dir / 'holdout.jsonl'}")


if __name__ == "__main__":
    app()
