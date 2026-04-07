#!/usr/bin/env python3
"""
Full training for vision classifiers with model saving.

Unlike benchmark.py (which is diagnostic-only), this script:
  - Trains with more epochs/steps and learning rate scheduling
  - Saves best checkpoint (by val F1) to disk
  - Exports config.json compatible with merge_inference.py
  - Supports early stopping

Usage::

    python train.py train \
        --data-dir /path/to/class_dirs \
        --backbone efficientnet_b0 \
        --epochs 20 \
        --output-dir models/my-model

    python train.py evaluate \
        --model-dir models/my-model \
        --data-dir /path/to/class_dirs
"""

from __future__ import annotations

import json
import random
import time
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from loguru import logger

try:
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path.home() / ".pi" / "skills"))
    from common.task_monitor import TaskClient
except ImportError:
    TaskClient = None

# Re-use benchmark utilities
from benchmark import (
    IMAGE_EXTS,
    Sample,
    _evaluate,
    _ImageDataset,
    _macro_f1,
    _samples_from_class_dirs,
    _samples_from_data_dir,
    _samples_from_jsonl,
    _stratified_split,
)


def train_vision(
    *,
    backbone: str,
    train_samples: Sequence[Sample],
    val_samples: Sequence[Sample],
    label_to_idx: Dict[str, int],
    output_dir: Path,
    device: str = "cuda",
    image_size: int = 224,
    batch_size: int = 16,
    epochs: int = 20,
    max_steps: int = 0,
    lr: float = 1e-3,
    weight_decay: float = 0.01,
    patience: int = 5,
    seed: int = 42,
) -> Dict[str, Any]:
    """Full training with checkpointing and early stopping."""
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.utils.data import DataLoader

    import timm

    torch.manual_seed(seed)
    num_classes = len(label_to_idx)
    idx_to_label = {v: k for k, v in label_to_idx.items()}

    train_dataset = _ImageDataset(train_samples, label_to_idx=label_to_idx, image_size=image_size)
    val_dataset = _ImageDataset(val_samples, label_to_idx=label_to_idx, image_size=image_size)
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, num_workers=2)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False, num_workers=2)

    model = timm.create_model(backbone, pretrained=True, num_classes=num_classes).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)

    # Cosine annealing LR schedule
    total_steps = len(train_loader) * epochs if max_steps <= 0 else max_steps
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=total_steps)

    output_dir.mkdir(parents=True, exist_ok=True)
    best_f1 = 0.0
    best_epoch = -1
    no_improve = 0
    step = 0
    history: List[Dict[str, Any]] = []

    logger.info(f"Training {backbone} | {len(train_samples)} train, {len(val_samples)} val | {num_classes} classes | device={device}")

    monitor = TaskClient("classifier-lab/train", total=epochs, description=f"Training {backbone}") if TaskClient else None

    for epoch in range(epochs):
        model.train()
        epoch_loss = 0.0
        epoch_steps = 0
        t0 = time.time()

        for images, targets in train_loader:
            images = images.to(device)
            targets = targets.to(device)
            optimizer.zero_grad()
            logits = model(images)
            loss = criterion(logits, targets)
            loss.backward()
            optimizer.step()
            scheduler.step()

            epoch_loss += loss.item()
            epoch_steps += 1
            step += 1

            if max_steps > 0 and step >= max_steps:
                break

        avg_loss = epoch_loss / max(epoch_steps, 1)

        # Validate
        metrics = _evaluate(model=model, loader=val_loader, device=device, num_classes=num_classes)
        elapsed = time.time() - t0

        epoch_info = {
            "epoch": epoch + 1,
            "train_loss": round(avg_loss, 4),
            "val_accuracy": round(metrics["accuracy"], 4),
            "val_f1": round(metrics["macro_f1"], 4),
            "lr": round(scheduler.get_last_lr()[0], 6),
            "elapsed_s": round(elapsed, 1),
            "step": step,
        }
        history.append(epoch_info)
        logger.info(
            f"Epoch {epoch+1}/{epochs} | loss={avg_loss:.4f} | val_f1={metrics['macro_f1']:.4f} | "
            f"val_acc={metrics['accuracy']:.4f} | lr={scheduler.get_last_lr()[0]:.6f} | {elapsed:.1f}s"
        )

        if monitor:
            monitor.update(item=f"epoch {epoch+1} f1={metrics['macro_f1']:.4f}")

        # Save best
        if metrics["macro_f1"] > best_f1:
            best_f1 = metrics["macro_f1"]
            best_epoch = epoch + 1
            no_improve = 0
            ckpt = {
                "model_state_dict": model.state_dict(),
                "backbone": backbone,
                "num_classes": num_classes,
                "label_to_idx": label_to_idx,
                "idx_to_label": idx_to_label,
                "image_size": image_size,
                "epoch": epoch + 1,
                "step": step,
                "val_f1": metrics["macro_f1"],
                "val_accuracy": metrics["accuracy"],
            }
            torch.save(ckpt, str(output_dir / "best_model.pth"))
            logger.info(f"  -> New best model saved (F1={best_f1:.4f})")
        else:
            no_improve += 1

        if no_improve >= patience:
            logger.info(f"Early stopping at epoch {epoch+1} (no improvement for {patience} epochs)")
            break

        if max_steps > 0 and step >= max_steps:
            logger.info(f"Reached max_steps={max_steps}")
            break

    # Write config.json
    config = {
        "type": "vision",
        "backbone": backbone,
        "num_classes": num_classes,
        "label_to_idx": label_to_idx,
        "idx_to_label": idx_to_label,
        "image_size": image_size,
        "training_samples": len(train_samples),
        "val_samples": len(val_samples),
        "class_distribution": {},
        "best_epoch": best_epoch,
        "best_val_f1": round(best_f1, 4),
        "total_steps": step,
        "training_history": history,
    }
    # Count class distribution
    for s in train_samples:
        config["class_distribution"][s.label] = config["class_distribution"].get(s.label, 0) + 1

    (output_dir / "config.json").write_text(json.dumps(config, indent=2))
    logger.info(f"Training complete. Best F1={best_f1:.4f} at epoch {best_epoch}. Model at {output_dir}")

    if monitor:
        monitor.finish()

    return {
        "status": "ok",
        "backbone": backbone,
        "best_f1": best_f1,
        "best_accuracy": history[best_epoch - 1]["val_accuracy"] if best_epoch > 0 else 0.0,
        "best_epoch": best_epoch,
        "total_epochs": len(history),
        "total_steps": step,
        "output_dir": str(output_dir),
    }


def evaluate_vision(
    *,
    model_dir: Path,
    data_dir: Optional[Path] = None,
    labels_jsonl: Optional[Path] = None,
    device: str = "cuda",
    batch_size: int = 16,
    image_size: int = 224,
) -> Dict[str, Any]:
    """Evaluate a saved model on a dataset."""
    import torch
    from torch.utils.data import DataLoader

    import timm

    config_path = model_dir / "config.json"
    if not config_path.exists():
        return {"status": "error", "error": f"No config.json in {model_dir}"}
    config = json.loads(config_path.read_text())

    ckpt_path = model_dir / "best_model.pth"
    if not ckpt_path.exists():
        return {"status": "error", "error": f"No best_model.pth in {model_dir}"}

    backbone = config.get("backbone", "efficientnet_b0")
    label_to_idx = config.get("label_to_idx", {})
    num_classes = config.get("num_classes", len(label_to_idx))

    # Load model
    ckpt = torch.load(str(ckpt_path), map_location=device, weights_only=False)
    model = timm.create_model(backbone, pretrained=False, num_classes=num_classes).to(device)
    model.load_state_dict(ckpt["model_state_dict"])
    model.eval()

    # Load data
    if labels_jsonl is not None:
        all_samples = _samples_from_jsonl(labels_jsonl)
        _, val_samples = _stratified_split(all_samples, val_ratio=0.15, seed=42)
    elif data_dir is not None:
        _, val_samples = _samples_from_data_dir(data_dir)
    else:
        return {"status": "error", "error": "Either data_dir or labels_jsonl required"}

    val_dataset = _ImageDataset(val_samples, label_to_idx=label_to_idx, image_size=image_size)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False, num_workers=2)

    metrics = _evaluate(model=model, loader=val_loader, device=device, num_classes=num_classes)

    return {
        "status": "ok",
        "backbone": backbone,
        "accuracy": metrics["accuracy"],
        "macro_f1": metrics["macro_f1"],
        "val_samples": len(val_samples),
        "model_dir": str(model_dir),
    }


# ---------------------------------------------------------------------------
# Target enum
# ---------------------------------------------------------------------------

class Target(str, Enum):
    """Training execution target."""
    local = "local"
    flash = "flash"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli():
    import typer

    app = typer.Typer(
        help=(
            "Train and evaluate vision classifiers.\n\n"
            "Use --target local (default) or --target flash to submit to RunPod cloud GPU."
        )
    )

    @app.command()
    def train(
        data_dir: Optional[Path] = typer.Option(None, "--data-dir", help="Directory with class subdirs"),
        labels_jsonl: Optional[Path] = typer.Option(None, "--labels-jsonl", help="JSONL with image_path + label"),
        backbone: str = typer.Option("efficientnet_b0", "--backbone", help="timm model name"),
        output_dir: Optional[Path] = typer.Option(None, "--output-dir", help="Where to save model"),
        epochs: int = typer.Option(20, "--epochs"),
        max_steps: int = typer.Option(0, "--max-steps", help="0 = unlimited"),
        batch_size: int = typer.Option(16, "--batch-size"),
        image_size: int = typer.Option(224, "--image-size"),
        lr: float = typer.Option(1e-3, "--lr"),
        patience: int = typer.Option(5, "--patience"),
        device: str = typer.Option("cuda", "--device"),
        seed: int = typer.Option(42, "--seed"),
        val_ratio: float = typer.Option(0.15, "--val-ratio"),
        target: Target = typer.Option(Target.local, "--target", help="Training target: local (default) or flash (RunPod cloud GPU)"),
    ):
        """Train a vision classifier and save best checkpoint."""
        # ------------------------------------------------------------------
        # Flash (RunPod cloud) path
        # ------------------------------------------------------------------
        if target == Target.flash:
            from flash_trainer import FlashTrainer

            if data_dir is None and labels_jsonl is None:
                raise typer.BadParameter("Either --data-dir or --labels-jsonl required")

            trainer = FlashTrainer()
            train_args: Dict[str, Any] = {
                "backbone": backbone,
                "epochs": epochs,
                "batch_size": batch_size,
                "image_size": image_size,
                "lr": lr,
                "patience": patience,
                "seed": seed,
                "val_ratio": val_ratio,
                "max_steps": max_steps,
            }

            volume_id: Optional[str] = None

            # Vision (timm) models need image data uploaded to a network volume
            if data_dir is not None:
                logger.info(f"Vision model detected — uploading dataset from {data_dir}")
                volume_id = trainer.upload_dataset(
                    data_dir,
                    dataset_name=data_dir.name,
                )
                train_args["data_dir"] = "/runpod-volume/" + data_dir.name
            elif labels_jsonl is not None:
                train_args["labels_jsonl"] = str(labels_jsonl)

            if output_dir is not None:
                train_args["output_dir"] = str(output_dir)

            pod_id = trainer.submit(
                script_path=Path(__file__),
                train_args=train_args,
                volume_id=volume_id,
            )
            result = {
                "status": "submitted",
                "target": "flash",
                "pod_id": pod_id,
                "monitor_url": f"https://www.runpod.io/console/pods/{pod_id}",
            }
            print(json.dumps(result, indent=2))
            return

        # ------------------------------------------------------------------
        # Local path (default)
        # ------------------------------------------------------------------
        import torch

        if not torch.cuda.is_available() and device == "cuda":
            device = "cpu"
            logger.warning("CUDA not available, using CPU")

        if data_dir is None and labels_jsonl is None:
            raise typer.BadParameter("Either --data-dir or --labels-jsonl required")

        if labels_jsonl is not None:
            all_samples = _samples_from_jsonl(labels_jsonl)
            train_samples, val_samples = _stratified_split(all_samples, val_ratio=val_ratio, seed=seed)
            source_name = labels_jsonl.stem
        else:
            train_samples, val_samples = _samples_from_data_dir(data_dir)
            source_name = data_dir.name

        labels = sorted({s.label for s in train_samples + val_samples})
        label_to_idx = {label: idx for idx, label in enumerate(labels)}

        if output_dir is None:
            output_dir = Path("models") / f"{source_name}-{backbone}"

        result = train_vision(
            backbone=backbone,
            train_samples=train_samples,
            val_samples=val_samples,
            label_to_idx=label_to_idx,
            output_dir=output_dir,
            device=device,
            image_size=image_size,
            batch_size=batch_size,
            epochs=epochs,
            max_steps=max_steps,
            lr=lr,
            weight_decay=0.01,
            patience=patience,
            seed=seed,
        )
        print(json.dumps(result, indent=2))

    @app.command()
    def evaluate(
        model_dir: Path = typer.Option(..., "--model-dir", help="Model directory with best_model.pth + config.json"),
        data_dir: Optional[Path] = typer.Option(None, "--data-dir"),
        labels_jsonl: Optional[Path] = typer.Option(None, "--labels-jsonl"),
        device: str = typer.Option("cuda", "--device"),
        batch_size: int = typer.Option(16, "--batch-size"),
    ):
        """Evaluate a trained model."""
        import torch

        if not torch.cuda.is_available() and device == "cuda":
            device = "cpu"

        result = evaluate_vision(
            model_dir=model_dir,
            data_dir=data_dir,
            labels_jsonl=labels_jsonl,
            device=device,
            batch_size=batch_size,
        )
        print(json.dumps(result, indent=2))

    app()


if __name__ == "__main__":
    _cli()
