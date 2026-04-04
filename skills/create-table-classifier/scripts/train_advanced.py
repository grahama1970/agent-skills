#!/usr/bin/env python3
"""
Advanced training with data augmentation for Table Strategy Classifier.

Implements:
- RandAugment for strong augmentation
- MixUp/CutMix for regularization
- Longer training with cosine annealing
- Label smoothing
- EMA (Exponential Moving Average)
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional
import random
import math

import typer
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader

try:
    import timm
    from timm.data import create_transform
    from timm.data.mixup import Mixup
    from timm.data.auto_augment import rand_augment_transform
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "timm", "-q"])
    import timm
    from timm.data import create_transform
    from timm.data.mixup import Mixup
    from timm.data.auto_augment import rand_augment_transform

try:
    from PIL import Image
    from torchvision import transforms
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "pillow", "torchvision", "-q"])
    from PIL import Image
    from torchvision import transforms

from loguru import logger
from tqdm import tqdm
import copy

app = typer.Typer(help="Advanced training with augmentation")

SKILL_DIR = Path(__file__).parent.parent
DATA_DIR = SKILL_DIR / "data"
MODELS_DIR = SKILL_DIR / "models"
LOGS_DIR = SKILL_DIR / "logs"

STRATEGIES = ["lattice", "stream", "lattice_sensitive"]
STRATEGY_TO_IDX = {s: i for i, s in enumerate(STRATEGIES)}
PRESETS = [
    "unknown", "arxiv_scientific", "requirements_spec", "archive_scanned",
    "government_report", "academic_thesis", "engineering_manual", "legal_document"
]
PRESET_TO_IDX = {p: i for i, p in enumerate(PRESETS)}


class TableStrategyModel(nn.Module):
    """Vision model for table strategy prediction."""

    def __init__(self, backbone: str = "efficientnet_b0", pretrained: bool = True,
                 num_strategies: int = 3, num_presets: int = 8, preset_embed_dim: int = 16,
                 drop_rate: float = 0.3):
        super().__init__()
        self.backbone = timm.create_model(backbone, pretrained=pretrained, num_classes=0,
                                          drop_rate=drop_rate)

        with torch.no_grad():
            dummy = torch.randn(1, 3, 224, 224)
            features = self.backbone(dummy)
            self.feature_dim = features.shape[-1]

        self.preset_embedding = nn.Embedding(num_presets, preset_embed_dim)
        combined_dim = self.feature_dim + preset_embed_dim

        self.strategy_head = nn.Sequential(
            nn.Linear(combined_dim, 256),
            nn.ReLU(),
            nn.Dropout(drop_rate),
            nn.Linear(256, num_strategies),
        )
        self.param_head = nn.Sequential(
            nn.Linear(combined_dim, 128),
            nn.ReLU(),
            nn.Dropout(drop_rate),
            nn.Linear(128, 2),
        )
        self.confidence_head = nn.Sequential(
            nn.Linear(combined_dim, 64),
            nn.ReLU(),
            nn.Linear(64, 1),
            nn.Sigmoid(),
        )

    def forward(self, images: torch.Tensor, preset_ids: Optional[torch.Tensor] = None) -> dict:
        features = self.backbone(images)
        if preset_ids is not None:
            preset_emb = self.preset_embedding(preset_ids)
            features = torch.cat([features, preset_emb], dim=-1)
        else:
            batch_size = features.shape[0]
            zero_emb = torch.zeros(batch_size, self.preset_embedding.embedding_dim, device=features.device)
            features = torch.cat([features, zero_emb], dim=-1)

        strategy_logits = self.strategy_head(features)
        params = self.param_head(features)
        params = torch.stack([
            10 + 40 * torch.sigmoid(params[:, 0]),
            100 + 500 * torch.sigmoid(params[:, 1]),
        ], dim=-1)
        confidence = self.confidence_head(features)

        return {"strategy_logits": strategy_logits, "params": params, "confidence": confidence.squeeze(-1)}


class AdvancedTableDataset(Dataset):
    """Dataset with advanced augmentation for table strategy classification."""

    def __init__(self, data_file: Path, image_dir: Path, image_size: int = 224,
                 use_randaugment: bool = True, randaugment_n: int = 2, randaugment_m: int = 9):
        self.examples = []
        self.image_dir = image_dir

        if data_file.exists():
            with data_file.open() as f:
                for line in f:
                    ex = json.loads(line)
                    if ex.get("image_path"):
                        self.examples.append(ex)

        logger.info(f"Loaded {len(self.examples)} examples from {data_file}")

        # Build transform with RandAugment
        if use_randaugment:
            self.transform = transforms.Compose([
                transforms.Resize((image_size, image_size)),
                transforms.RandomHorizontalFlip(p=0.3),
                rand_augment_transform(
                    config_str=f'rand-m{randaugment_m}-n{randaugment_n}',
                    hparams={'translate_const': 100, 'img_mean': (128, 128, 128)}
                ),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ])
        else:
            self.transform = transforms.Compose([
                transforms.Resize((image_size, image_size)),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ])

    def __len__(self):
        return len(self.examples)

    def __getitem__(self, idx):
        ex = self.examples[idx]
        img_path = SKILL_DIR / ex["image_path"]

        try:
            image = Image.open(img_path).convert("RGB")
            image = self.transform(image)
        except Exception as e:
            logger.warning(f"Failed to load image {img_path}: {e}")
            image = torch.zeros(3, 224, 224)

        strategy = ex.get("strategy", "lattice")
        strategy_idx = STRATEGY_TO_IDX.get(strategy, 0)
        params = ex.get("params", {})
        preset = ex.get("preset", "unknown")
        preset_idx = PRESET_TO_IDX.get(preset, 0)

        return {
            "image": image,
            "strategy": strategy_idx,
            "line_scale": params.get("line_scale", 15),
            "edge_tol": params.get("edge_tol", 300),
            "preset": preset_idx,
            "quality": ex.get("quality_score", 0.8),
        }


class EMA:
    """Exponential Moving Average of model weights."""

    def __init__(self, model: nn.Module, decay: float = 0.999):
        self.model = model
        self.decay = decay
        self.shadow = {}
        self.backup = {}

        for name, param in model.named_parameters():
            if param.requires_grad:
                self.shadow[name] = param.data.clone()

    def update(self):
        for name, param in self.model.named_parameters():
            if param.requires_grad:
                self.shadow[name] = self.decay * self.shadow[name] + (1 - self.decay) * param.data

    def apply_shadow(self):
        for name, param in self.model.named_parameters():
            if param.requires_grad:
                self.backup[name] = param.data
                param.data = self.shadow[name]

    def restore(self):
        for name, param in self.model.named_parameters():
            if param.requires_grad:
                param.data = self.backup[name]
        self.backup = {}


def mixup_data(x, y, alpha=0.2):
    """Apply MixUp to batch."""
    if alpha > 0:
        lam = random.betavariate(alpha, alpha)
    else:
        lam = 1

    batch_size = x.size(0)
    index = torch.randperm(batch_size, device=x.device)

    mixed_x = lam * x + (1 - lam) * x[index]
    y_a, y_b = y, y[index]
    return mixed_x, y_a, y_b, lam


def cutmix_data(x, y, alpha=1.0):
    """Apply CutMix to batch."""
    if alpha > 0:
        lam = random.betavariate(alpha, alpha)
    else:
        lam = 1

    batch_size = x.size(0)
    index = torch.randperm(batch_size, device=x.device)

    # Get bounding box
    W, H = x.size(2), x.size(3)
    cut_rat = math.sqrt(1 - lam)
    cut_w = int(W * cut_rat)
    cut_h = int(H * cut_rat)
    cx = random.randint(0, W)
    cy = random.randint(0, H)
    bbx1 = max(0, cx - cut_w // 2)
    bby1 = max(0, cy - cut_h // 2)
    bbx2 = min(W, cx + cut_w // 2)
    bby2 = min(H, cy + cut_h // 2)

    x[:, :, bbx1:bbx2, bby1:bby2] = x[index, :, bbx1:bbx2, bby1:bby2]
    lam = 1 - ((bbx2 - bbx1) * (bby2 - bby1) / (W * H))

    y_a, y_b = y, y[index]
    return x, y_a, y_b, lam


def train_epoch_advanced(model, dataloader, optimizer, device, ema=None,
                         use_mixup=True, use_cutmix=True, label_smoothing=0.1):
    """Train for one epoch with advanced augmentation."""
    model.train()
    total_loss = 0.0
    strategy_correct = 0
    total = 0

    criterion = nn.CrossEntropyLoss(label_smoothing=label_smoothing)

    for batch in tqdm(dataloader, desc="Training"):
        images = batch["image"].to(device)
        strategy_labels = batch["strategy"].to(device)
        preset_ids = batch["preset"].to(device)

        # Apply MixUp or CutMix randomly
        use_mix = random.random() < 0.5 and (use_mixup or use_cutmix)
        if use_mix:
            if use_cutmix and random.random() < 0.5:
                images, y_a, y_b, lam = cutmix_data(images, strategy_labels)
            else:
                images, y_a, y_b, lam = mixup_data(images, strategy_labels)

        optimizer.zero_grad()
        outputs = model(images, preset_ids)

        if use_mix:
            loss = lam * criterion(outputs["strategy_logits"], y_a) + \
                   (1 - lam) * criterion(outputs["strategy_logits"], y_b)
        else:
            loss = criterion(outputs["strategy_logits"], strategy_labels)

        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()

        if ema:
            ema.update()

        total_loss += loss.item()
        preds = outputs["strategy_logits"].argmax(dim=-1)
        if not use_mix:
            strategy_correct += (preds == strategy_labels).sum().item()
        total += len(images)

    return {"loss": total_loss / len(dataloader), "strategy_accuracy": strategy_correct / total if total > 0 else 0}


@torch.no_grad()
def evaluate_advanced(model, dataloader, device, use_ema=False, ema=None):
    """Evaluate with optional EMA."""
    if use_ema and ema:
        ema.apply_shadow()

    model.eval()
    strategy_correct = 0
    total = 0
    per_class_correct = {s: 0 for s in STRATEGIES}
    per_class_total = {s: 0 for s in STRATEGIES}

    for batch in tqdm(dataloader, desc="Evaluating"):
        images = batch["image"].to(device)
        strategy_labels = batch["strategy"].to(device)
        preset_ids = batch["preset"].to(device)

        outputs = model(images, preset_ids)
        preds = outputs["strategy_logits"].argmax(dim=-1)
        strategy_correct += (preds == strategy_labels).sum().item()
        total += len(images)

        # Per-class accuracy
        for i, (pred, label) in enumerate(zip(preds, strategy_labels)):
            label_name = STRATEGIES[label.item()]
            per_class_total[label_name] += 1
            if pred == label:
                per_class_correct[label_name] += 1

    if use_ema and ema:
        ema.restore()

    per_class_acc = {s: per_class_correct[s] / per_class_total[s] if per_class_total[s] > 0 else 0
                     for s in STRATEGIES}

    return {
        "strategy_accuracy": strategy_correct / total,
        "per_class_accuracy": per_class_acc,
        "per_class_counts": per_class_total,
    }


@app.command()
def train(
    train_file: Path = typer.Option(DATA_DIR / "labels" / "train_balanced.jsonl", help="Training data"),
    eval_file: Path = typer.Option(DATA_DIR / "labels" / "eval.jsonl", help="Evaluation data"),
    epochs: int = typer.Option(15, help="Number of epochs"),
    batch_size: int = typer.Option(32, help="Batch size"),
    learning_rate: float = typer.Option(5e-5, help="Learning rate"),
    backbone: str = typer.Option("efficientnet_b0", help="Backbone model"),
    output_dir: Path = typer.Option(MODELS_DIR / "table-classifier-advanced", help="Output directory"),
    use_mixup: bool = typer.Option(True, help="Use MixUp augmentation"),
    use_cutmix: bool = typer.Option(True, help="Use CutMix augmentation"),
    use_randaugment: bool = typer.Option(True, help="Use RandAugment"),
    use_ema: bool = typer.Option(True, help="Use EMA"),
    label_smoothing: float = typer.Option(0.1, help="Label smoothing"),
    drop_rate: float = typer.Option(0.3, help="Dropout rate"),
):
    """Train with advanced augmentation techniques."""
    logger.info("Starting advanced training")
    logger.info(f"Config: epochs={epochs}, backbone={backbone}")
    logger.info(f"Augmentation: mixup={use_mixup}, cutmix={use_cutmix}, randaugment={use_randaugment}")
    logger.info(f"Regularization: ema={use_ema}, label_smoothing={label_smoothing}, dropout={drop_rate}")

    output_dir.mkdir(parents=True, exist_ok=True)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"Device: {device}")

    # Model
    model = TableStrategyModel(backbone=backbone, pretrained=True, drop_rate=drop_rate)
    model = model.to(device)

    # EMA
    ema = EMA(model, decay=0.999) if use_ema else None

    # Datasets
    train_dataset = AdvancedTableDataset(train_file, DATA_DIR / "images", use_randaugment=use_randaugment)
    eval_dataset = AdvancedTableDataset(eval_file, DATA_DIR / "images", use_randaugment=False)

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, num_workers=4, pin_memory=True)
    eval_loader = DataLoader(eval_dataset, batch_size=batch_size, shuffle=False, num_workers=4)

    # Optimizer with weight decay
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=0.05)

    # Cosine annealing with warmup
    warmup_epochs = 2
    scheduler = torch.optim.lr_scheduler.CosineAnnealingWarmRestarts(optimizer, T_0=epochs - warmup_epochs, T_mult=1)

    best_accuracy = 0.0
    history = []

    for epoch in range(epochs):
        current_lr = optimizer.param_groups[0]['lr']
        logger.info(f"Epoch {epoch + 1}/{epochs} (lr={current_lr:.2e})")

        # Warmup
        if epoch < warmup_epochs:
            warmup_lr = learning_rate * (epoch + 1) / warmup_epochs
            for param_group in optimizer.param_groups:
                param_group['lr'] = warmup_lr

        train_metrics = train_epoch_advanced(
            model, train_loader, optimizer, device, ema=ema,
            use_mixup=use_mixup, use_cutmix=use_cutmix, label_smoothing=label_smoothing
        )
        logger.info(f"Train - Loss: {train_metrics['loss']:.4f}")

        # Evaluate with EMA
        eval_metrics = evaluate_advanced(model, eval_loader, device, use_ema=use_ema, ema=ema)
        logger.info(f"Eval - Accuracy: {eval_metrics['strategy_accuracy']:.4f}")
        logger.info(f"Per-class: {eval_metrics['per_class_accuracy']}")

        history.append({
            "epoch": epoch + 1,
            "train_loss": train_metrics["loss"],
            "eval_accuracy": eval_metrics["strategy_accuracy"],
            "per_class": eval_metrics["per_class_accuracy"],
        })

        # Save best
        if eval_metrics["strategy_accuracy"] > best_accuracy:
            best_accuracy = eval_metrics["strategy_accuracy"]
            if use_ema and ema:
                ema.apply_shadow()
            torch.save({
                "model_state_dict": model.state_dict(),
                "config": {"backbone": backbone, "num_strategies": len(STRATEGIES)},
                "epoch": epoch,
                "accuracy": best_accuracy,
            }, output_dir / "best_model.pth")
            if use_ema and ema:
                ema.restore()
            logger.info(f"Saved best model (accuracy: {best_accuracy:.4f})")

        if epoch >= warmup_epochs:
            scheduler.step()

    # Save final
    if use_ema and ema:
        ema.apply_shadow()
    torch.save({
        "model_state_dict": model.state_dict(),
        "config": {"backbone": backbone, "num_strategies": len(STRATEGIES), "strategies": STRATEGIES, "presets": PRESETS},
    }, output_dir / "model.pth")

    config = {
        "backbone": backbone,
        "num_strategies": len(STRATEGIES),
        "strategies": STRATEGIES,
        "presets": PRESETS,
        "final_accuracy": best_accuracy,
        "training": {
            "epochs": epochs,
            "use_mixup": use_mixup,
            "use_cutmix": use_cutmix,
            "use_randaugment": use_randaugment,
            "use_ema": use_ema,
            "label_smoothing": label_smoothing,
        }
    }
    (output_dir / "config.json").write_text(json.dumps(config, indent=2))
    (output_dir / "history.json").write_text(json.dumps(history, indent=2))

    logger.info(f"Training complete! Best accuracy: {best_accuracy:.4f}")
    return best_accuracy


if __name__ == "__main__":
    app()
