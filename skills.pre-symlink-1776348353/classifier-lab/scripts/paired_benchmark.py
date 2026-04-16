#!/usr/bin/env python3
"""
Paired/Siamese benchmark for classifier-lab.

Trains a Siamese network where two image crops are compared to predict
whether they should be merged or kept separate. Uses a shared backbone
with a comparison head (concatenation + MLP classifier).

Data format:
  data_dir/
    train/
      merge/     — paired crops that SHOULD be merged (side-by-side 448x224 images)
      separate/  — paired crops that should NOT be merged
    val/
    test/

Each image is a 448x224 composite (left=region_A, right=region_B) or two
separate images referenced by a JSONL manifest.

Architecture:
  backbone(crop_A) → features_A
  backbone(crop_B) → features_B
  [features_A, features_B, |features_A - features_B|] → MLP → {merge, separate}
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from loguru import logger
import timm
import torch
torch.backends.cudnn.enabled = False  # workaround: CUDNN_STATUS_NOT_INITIALIZED on this host
from torch import nn, optim
from torch.utils.data import DataLoader, Dataset
from torchvision import datasets, transforms
from PIL import Image


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


class SiameseModel(nn.Module):
    """Shared-backbone Siamese with 4-way comparison head.

    Feature combination: [f_a, f_b, |f_a - f_b|, f_a * f_b]
    From InferSent (Conneau et al., 2017) — proven for pair classification.
    The element-wise product captures feature co-activation; the absolute
    difference captures how regions differ. Both are needed.
    """

    def __init__(self, backbone_name: str, num_classes: int = 2, pretrained: bool = True, dropout: float = 0.3):
        super().__init__()
        self.backbone = timm.create_model(backbone_name, pretrained=pretrained, num_classes=0)
        feat_dim = self.backbone.num_features
        # 4-way comparison head: [f_a, f_b, |f_a-f_b|, f_a*f_b] = 4 * feat_dim
        self.head = nn.Sequential(
            nn.Linear(feat_dim * 4, 512),
            nn.BatchNorm1d(512),
            nn.ReLU(inplace=True),
            nn.Dropout(dropout),
            nn.Linear(512, 128),
            nn.ReLU(inplace=True),
            nn.Dropout(dropout),
            nn.Linear(128, num_classes),
        )

    def forward(self, x_a: torch.Tensor, x_b: torch.Tensor) -> torch.Tensor:
        f_a = self.backbone(x_a)
        f_b = self.backbone(x_b)
        combined = torch.cat([f_a, f_b, torch.abs(f_a - f_b), f_a * f_b], dim=1)
        return self.head(combined)


class PairedImageDataset(Dataset):
    """
    Loads paired images. Each image is a side-by-side composite (W=2*H).
    Splits into left and right halves as the two inputs.
    """

    def __init__(
        self,
        root: str,
        image_size: int = 224,
        augment: bool = False,
        random_erasing: float = 0.0,
    ):
        self.ds = datasets.ImageFolder(root)
        self.classes = self.ds.classes
        self.image_size = image_size
        self.augment = augment

        self.base_transform = transforms.Compose(
            [
                transforms.Resize((image_size, image_size)),
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            ]
        )
        aug_steps: list[Any] = [
            transforms.Resize((image_size, image_size)),
            transforms.RandomRotation(3),
            transforms.ColorJitter(brightness=0.15, contrast=0.15),
            transforms.ToTensor(),
        ]
        if random_erasing > 0:
            aug_steps.append(transforms.RandomErasing(p=random_erasing))
        aug_steps.append(transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]))
        self.aug_transform = transforms.Compose(aug_steps)

    def __len__(self) -> int:
        return len(self.ds)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor, int]:
        img, label = self.ds[idx]
        if img.mode != "RGB":
            img = img.convert("RGB")

        w, h = img.size
        # Images are composites of two adjacent page regions
        # Split vertically into left (region A) and right (region B)
        mid = w // 2
        crop_a = img.crop((0, 0, mid, h))
        crop_b = img.crop((mid, 0, w, h))

        tf = self.aug_transform if self.augment else self.base_transform
        return tf(crop_a), tf(crop_b), label


def _macro_f1(preds: List[int], labels: List[int], num_classes: int) -> float:
    """Compute macro F1 score."""
    f1s = []
    for c in range(num_classes):
        tp = sum(1 for p, l in zip(preds, labels) if p == c and l == c)
        fp = sum(1 for p, l in zip(preds, labels) if p == c and l != c)
        fn = sum(1 for p, l in zip(preds, labels) if p != c and l == c)
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        f1s.append(f1)
    return sum(f1s) / len(f1s) if f1s else 0.0


def _wilson_score_lower(accuracy: float, n: int, z: float = 1.96) -> float:
    if n == 0:
        return 0.0
    p = accuracy
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    spread = z * ((p * (1 - p) + z * z / (4 * n)) / n) ** 0.5
    return max(0.0, float((centre - spread) / denom))


def _mixup_pair_batch(
    x_a: torch.Tensor,
    x_b: torch.Tensor,
    labels: torch.Tensor,
    alpha: float,
) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, float]:
    if alpha <= 0:
        return x_a, x_b, labels, labels, 1.0
    lam = float(torch.distributions.Beta(alpha, alpha).sample().item())
    index = torch.randperm(x_a.size(0), device=x_a.device)
    mixed_a = (lam * x_a) + ((1.0 - lam) * x_a[index, :])
    mixed_b = (lam * x_b) + ((1.0 - lam) * x_b[index, :])
    return mixed_a, mixed_b, labels, labels[index], lam


def _cutmix_pair_batch(
    x_a: torch.Tensor,
    x_b: torch.Tensor,
    labels: torch.Tensor,
    alpha: float,
) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, float]:
    if alpha <= 0:
        return x_a, x_b, labels, labels, 1.0
    lam = float(torch.distributions.Beta(alpha, alpha).sample().item())
    batch_size, _channels, height, width = x_a.size()
    index = torch.randperm(batch_size, device=x_a.device)

    cut_ratio = (1.0 - lam) ** 0.5
    cut_w = int(width * cut_ratio)
    cut_h = int(height * cut_ratio)

    cx = int(torch.randint(0, width, (1,), device=x_a.device).item())
    cy = int(torch.randint(0, height, (1,), device=x_a.device).item())

    x1 = max(cx - cut_w // 2, 0)
    y1 = max(cy - cut_h // 2, 0)
    x2 = min(cx + cut_w // 2, width)
    y2 = min(cy + cut_h // 2, height)

    mixed_a = x_a.clone()
    mixed_b = x_b.clone()
    mixed_a[:, :, y1:y2, x1:x2] = x_a[index, :, y1:y2, x1:x2]
    mixed_b[:, :, y1:y2, x1:x2] = x_b[index, :, y1:y2, x1:x2]
    area = max((x2 - x1) * (y2 - y1), 1)
    lam_adjusted = 1.0 - (area / float(width * height))
    return mixed_a, mixed_b, labels, labels[index], lam_adjusted


def run_paired_benchmark(
    *,
    data_dir: Path,
    backbones: Sequence[str],
    device: str = "cuda",
    image_size: int = 224,
    batch_size: int = 16,
    epochs: int = 20,
    lr: float = 1e-4,
    weight_decay: float = 0.01,
    label_smoothing: float = 0.1,
    dropout: float = 0.3,
    mixup_alpha: float = 0.0,
    cutmix_alpha: float = 0.0,
    random_erasing: float = 0.0,
    num_workers: int = 4,
    seed: int = 42,
) -> Dict[str, Any]:
    """Run Siamese benchmark on paired image data."""
    torch.manual_seed(seed)
    random.seed(seed)

    train_ds = PairedImageDataset(str(data_dir / "train"), image_size, augment=True, random_erasing=random_erasing)
    val_ds = PairedImageDataset(str(data_dir / "val"), image_size, augment=False)
    classes = train_ds.classes
    num_classes = len(classes)
    logger.info(f"Paired benchmark: {num_classes} classes, {len(train_ds)} train, {len(val_ds)} val")

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, num_workers=num_workers)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False, num_workers=num_workers)

    results: List[Dict[str, Any]] = []

    for backbone_name in backbones:
        logger.info(f"Training Siamese {backbone_name}...")
        try:
            model = SiameseModel(backbone_name, num_classes=num_classes, dropout=dropout).to(device)
            criterion = nn.CrossEntropyLoss(label_smoothing=label_smoothing)

            # Two-phase training (from dogpile research):
            # Phase 1: freeze backbone, train head only (5 epochs)
            # Phase 2: unfreeze all, differential LR (backbone=lr/10, head=lr)
            warmup_epochs = min(5, epochs // 4)
            finetune_epochs = epochs - warmup_epochs

            # Phase 1: Head-only warmup
            for param in model.backbone.parameters():
                param.requires_grad = False
            optimizer = optim.AdamW(model.head.parameters(), lr=lr, weight_decay=weight_decay)
            logger.info(f"  Phase 1: head-only warmup ({warmup_epochs} epochs)")

            best_val_f1 = 0.0
            val_acc = 0.0
            for epoch in range(warmup_epochs):
                model.train()
                total_loss = 0.0
                for x_a, x_b, targets in train_loader:
                    x_a, x_b, targets = x_a.to(device), x_b.to(device), targets.to(device)
                    optimizer.zero_grad()
                    if cutmix_alpha > 0:
                        x_a_train, x_b_train, y_a, y_b, lam = _cutmix_pair_batch(x_a, x_b, targets, cutmix_alpha)
                        logits = model(x_a_train, x_b_train)
                        loss = lam * criterion(logits, y_a) + (1 - lam) * criterion(logits, y_b)
                    elif mixup_alpha > 0:
                        x_a_mix, x_b_mix, y_a, y_b, lam = _mixup_pair_batch(x_a, x_b, targets, mixup_alpha)
                        logits = model(x_a_mix, x_b_mix)
                        loss = lam * criterion(logits, y_a) + (1 - lam) * criterion(logits, y_b)
                    else:
                        logits = model(x_a, x_b)
                        loss = criterion(logits, targets)
                    loss.backward()
                    optimizer.step()
                    total_loss += loss.item()
                if (epoch + 1) == warmup_epochs:
                    model.eval(); preds, labels = [], []
                    with torch.no_grad():
                        for x_a, x_b, targets in val_loader:
                            x_a, x_b = x_a.to(device), x_b.to(device)
                            preds.extend(model(x_a, x_b).argmax(1).cpu().tolist()); labels.extend(targets.tolist())
                    val_f1 = _macro_f1(preds, labels, num_classes)
                    val_acc = sum(1 for p, l in zip(preds, labels) if p == l) / len(labels) if labels else 0
                    logger.info(f"  Warmup done: loss={total_loss/len(train_loader):.4f} val_f1={val_f1:.4f}")
                    best_val_f1 = max(best_val_f1, val_f1)

            # Phase 2: Full fine-tune with differential LR
            for param in model.backbone.parameters():
                param.requires_grad = True
            optimizer = optim.AdamW([
                {"params": model.backbone.parameters(), "lr": lr / 10},
                {"params": model.head.parameters(), "lr": lr},
            ], weight_decay=weight_decay)
            scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=finetune_epochs)
            logger.info(f"  Phase 2: full fine-tune ({finetune_epochs} epochs, backbone LR={lr/10:.1e})")

            for epoch in range(finetune_epochs):
                model.train()
                total_loss = 0.0
                for x_a, x_b, targets in train_loader:
                    x_a, x_b, targets = x_a.to(device), x_b.to(device), targets.to(device)
                    optimizer.zero_grad()
                    if cutmix_alpha > 0:
                        x_a_train, x_b_train, y_a, y_b, lam = _cutmix_pair_batch(x_a, x_b, targets, cutmix_alpha)
                        logits = model(x_a_train, x_b_train)
                        loss = lam * criterion(logits, y_a) + (1 - lam) * criterion(logits, y_b)
                    elif mixup_alpha > 0:
                        x_a_mix, x_b_mix, y_a, y_b, lam = _mixup_pair_batch(x_a, x_b, targets, mixup_alpha)
                        logits = model(x_a_mix, x_b_mix)
                        loss = lam * criterion(logits, y_a) + (1 - lam) * criterion(logits, y_b)
                    else:
                        logits = model(x_a, x_b)
                        loss = criterion(logits, targets)
                    loss.backward()
                    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                    optimizer.step()
                    total_loss += loss.item()
                scheduler.step()

                # Validate every 5 epochs
                if (epoch + 1) % 5 == 0 or epoch == finetune_epochs - 1:
                    model.eval()
                    preds, labels = [], []
                    with torch.no_grad():
                        for x_a, x_b, targets in val_loader:
                            x_a, x_b = x_a.to(device), x_b.to(device)
                            logits = model(x_a, x_b)
                            preds.extend(logits.argmax(1).cpu().tolist())
                            labels.extend(targets.tolist())
                    val_f1 = _macro_f1(preds, labels, num_classes)
                    val_acc = sum(1 for p, l in zip(preds, labels) if p == l) / len(labels) if labels else 0
                    logger.info(f"  Epoch {warmup_epochs+epoch+1}/{epochs}: loss={total_loss/len(train_loader):.4f} val_f1={val_f1:.4f} val_acc={val_acc:.4f}")
                    best_val_f1 = max(best_val_f1, val_f1)

            n_total = len(train_ds) + len(val_ds)
            results.append({
                "backbone": backbone_name,
                "status": "ok",
                "accuracy": val_acc,
                "macro_f1": best_val_f1,
                "wilson_score_lower": _wilson_score_lower(val_acc, n_total),
                "train_samples": len(train_ds),
                "val_samples": len(val_ds),
                "num_classes": num_classes,
                "architecture": "siamese",
            })
        except Exception as e:
            logger.error(f"Failed {backbone_name}: {e}")
            results.append({"backbone": backbone_name, "status": "error", "error": str(e)})

    # Select winner
    viable = [r for r in results if r.get("status") == "ok"]
    if not viable:
        return {"status": "failed", "reason": "all_backbones_failed", "results": results, "source": {"mode": "paired", "data_dir": str(data_dir)}}

    winner = max(viable, key=lambda r: (r.get("macro_f1", 0), r.get("accuracy", 0)))
    return {
        "status": "ok",
        "selected_backbone": winner["backbone"],
        "selected_metrics": {
            "macro_f1": float(winner.get("macro_f1", 0)),
            "accuracy": float(winner.get("accuracy", 0)),
            "wilson_score_lower": float(winner.get("wilson_score_lower", 0)),
        },
        "source": {"mode": "paired", "data_dir": str(data_dir)},
        "results": results,
    }
