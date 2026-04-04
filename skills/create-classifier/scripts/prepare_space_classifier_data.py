#!/usr/bin/env python3
"""
Prepare training data for Space Cybersecurity Classifier.

Extracts labeled examples from SPARTA QRA corpus with Brandon assessment labels.
Outputs train/val/test splits in HuggingFace datasets format.

Usage:
    python prepare_space_classifier_data.py --qra-corpus /path/to/qras.jsonl --output data/space_classifier/

Expected QRA format:
{
    "qra_id": "QRA-001",
    "question": "How do spacecraft authenticate commands?",
    "answer": "Spacecraft use cryptographic authentication...",
    "control_id": "AC-0012",
    "technique_id": "EXE-0003",
    "grounding_score": 0.92,
    "brandon_assessment": {
        "space_aware": true,
        "confidence": 0.95,
        "reasoning": "Uses space-specific terminology..."
    }
}
"""

import typer
import json
import random
from pathlib import Path
from typing import Optional
from collections import Counter

from loguru import logger


def load_qra_corpus(path: Path) -> list[dict]:
    """Load QRA corpus from JSONL file."""
    qras = []
    with open(path) as f:
        for line in f:
            if line.strip():
                qras.append(json.loads(line))
    return qras


def extract_label(qra: dict) -> Optional[str]:
    """Extract space_cybersecurity/generic_it label from QRA."""
    # Try Brandon assessment first
    assessment = qra.get("brandon_assessment", {})
    if "space_aware" in assessment:
        return "space_cybersecurity" if assessment["space_aware"] else "generic_it"

    # Fallback: Use grounding score as proxy
    # High grounding (>0.8) suggests space-specific, low suggests generic
    grounding = qra.get("grounding_score", 0)
    if grounding >= 0.8:
        return "space_cybersecurity"
    elif grounding < 0.6:
        return "generic_it"

    # Unknown - skip
    return None


def build_text_sample(qra: dict, include_question: bool = True) -> str:
    """Build text sample for classification."""
    parts = []

    if include_question and qra.get("question"):
        parts.append(f"Question: {qra['question']}")

    if qra.get("answer"):
        parts.append(f"Answer: {qra['answer']}")

    # Add context hints
    if qra.get("control_id"):
        parts.append(f"Control: {qra['control_id']}")
    if qra.get("technique_id"):
        parts.append(f"Technique: {qra['technique_id']}")

    return "\n".join(parts)


def prepare_dataset(
    qra_corpus_path: Path,
    output_dir: Path,
    train_ratio: float = 0.8,
    val_ratio: float = 0.1,
    test_ratio: float = 0.1,
    max_samples: Optional[int] = None,
    balance_classes: bool = True,
    seed: int = 42,
):
    """Prepare train/val/test splits from QRA corpus."""
    random.seed(seed)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load corpus
    logger.info(f"Loading QRA corpus from {qra_corpus_path}")
    qras = load_qra_corpus(qra_corpus_path)
    logger.info(f"Loaded {len(qras)} QRAs")

    # Extract labeled samples
    samples = []
    skipped = 0

    for qra in qras:
        label = extract_label(qra)
        if label is None:
            skipped += 1
            continue

        text = build_text_sample(qra)
        if len(text) < 50:  # Skip very short samples
            skipped += 1
            continue

        samples.append(
            {
                "id": qra.get("qra_id", f"sample_{len(samples)}"),
                "text": text,
                "label": label,
                "label_id": 0 if label == "space_cybersecurity" else 1,
                # Metadata for analysis
                "grounding_score": qra.get("grounding_score"),
                "control_id": qra.get("control_id"),
                "technique_id": qra.get("technique_id"),
            }
        )

    logger.info(f"Extracted {len(samples)} labeled samples (skipped {skipped})")

    # Class distribution
    label_counts = Counter(s["label"] for s in samples)
    logger.info(f"Class distribution: {dict(label_counts)}")

    # Balance classes if requested
    if balance_classes:
        min_count = min(label_counts.values())
        balanced = []

        for label in label_counts:
            label_samples = [s for s in samples if s["label"] == label]
            random.shuffle(label_samples)
            balanced.extend(label_samples[:min_count])

        samples = balanced
        random.shuffle(samples)
        logger.info(f"Balanced to {len(samples)} samples ({min_count} per class)")

    # Limit samples if requested
    if max_samples and len(samples) > max_samples:
        samples = samples[:max_samples]
        logger.info(f"Limited to {max_samples} samples")

    # Split into train/val/test
    n = len(samples)
    n_train = int(n * train_ratio)
    n_val = int(n * val_ratio)

    random.shuffle(samples)
    train_samples = samples[:n_train]
    val_samples = samples[n_train : n_train + n_val]
    test_samples = samples[n_train + n_val :]

    logger.info(f"Split: train={len(train_samples)}, val={len(val_samples)}, test={len(test_samples)}")

    # Save splits
    for name, split_samples in [
        ("train", train_samples),
        ("val", val_samples),
        ("test", test_samples),
    ]:
        output_path = output_dir / f"{name}.jsonl"
        with open(output_path, "w") as f:
            for sample in split_samples:
                f.write(json.dumps(sample) + "\n")
        logger.info(f"Saved {len(split_samples)} samples to {output_path}")

    # Save label mapping
    label_map = {"space_cybersecurity": 0, "generic_it": 1}
    with open(output_dir / "label_map.json", "w") as f:
        json.dump(label_map, f, indent=2)

    # Save dataset info
    info = {
        "task": "space_cybersecurity_detection",
        "classes": list(label_map.keys()),
        "num_classes": len(label_map),
        "train_samples": len(train_samples),
        "val_samples": len(val_samples),
        "test_samples": len(test_samples),
        "total_samples": len(samples),
        "source": str(qra_corpus_path),
        "balanced": balance_classes,
        "seed": seed,
    }
    with open(output_dir / "dataset_info.json", "w") as f:
        json.dump(info, f, indent=2)

    logger.info(f"\nDataset prepared at {output_dir}")
    logger.info(f"  Train: {output_dir / 'train.jsonl'}")
    logger.info(f"  Val: {output_dir / 'val.jsonl'}")
    logger.info(f"  Test: {output_dir / 'test.jsonl'}")

    return info


app = typer.Typer(help="Prepare training data for Space Cybersecurity Classifier")


@app.command()
def main(
    qra_corpus: Path = typer.Option(..., help="Path to QRA corpus JSONL (with brandon_assessment labels)"),
    output: Path = typer.Option(Path("data/space_classifier"), help="Output directory for train/val/test splits"),
    train_ratio: float = typer.Option(0.8, help="Training set ratio"),
    val_ratio: float = typer.Option(0.1, help="Validation set ratio"),
    test_ratio: float = typer.Option(0.1, help="Test set ratio"),
    max_samples: Optional[int] = typer.Option(None, help="Maximum samples to use"),
    no_balance: bool = typer.Option(False, help="Don't balance classes (use natural distribution)"),
    seed: int = typer.Option(42, help="Random seed"),
):
    prepare_dataset(
        qra_corpus_path=qra_corpus,
        output_dir=output,
        train_ratio=train_ratio,
        val_ratio=val_ratio,
        test_ratio=test_ratio,
        max_samples=max_samples,
        balance_classes=not no_balance,
        seed=seed,
    )


if __name__ == "__main__":
    app()
