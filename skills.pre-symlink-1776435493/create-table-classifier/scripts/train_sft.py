#!/usr/bin/env python3
"""
Supervised Fine-Tuning (SFT) warmup for Table Strategy Classifier.

Uses MobileNetV2 pretrained on ImageNet with custom heads for:
- Strategy classification (3 classes: lattice, stream, lattice_sensitive)
- Parameter regression (line_scale, edge_tol)
- Optional preset embedding

This provides a warm start before GRPO training.
"""

import json
import os
import sys
from dataclasses import dataclass, field
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

try:
    import torch
    import torch.nn as nn
    from torch.utils.data import Dataset, DataLoader
except ImportError:
    print("Installing torch...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "torch", "torchvision", "-q"],
    env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
    )
    import torch
    import torch.nn as nn
    from torch.utils.data import Dataset, DataLoader

try:
    import timm
except ImportError:
    print("Installing timm...",
    env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "timm", "-q"],
    env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
    )
    import timm

try:
    from PIL import Image
    from torchvision import transforms
except ImportError:
    print("Installing pillow, torchvision...",
env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "pillow", "torchvision", "-q"],
    env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
    )
    from PIL import Image
    from torchvision import transforms

from loguru import logger
from tqdm import tqdm

app = typer.Typer(help="SFT warmup training for Table Strategy Classifier",
env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
)

# Skill paths
SKILL_DIR = Path(__file__).parent.parent
DATA_DIR = SKILL_DIR / "data"
MODELS_DIR = SKILL_DIR / "models"
LOGS_DIR = SKILL_DIR / "logs"

# Strategy labels
STRATEGIES = ["lattice", "stream", "lattice_sensitive"]
STRATEGY_TO_IDX = {s: i for i, s in enumerate(STRATEGIES)}

# Known presets for embedding
PRESETS = [
    "unknown", "arxiv_scientific", "requirements_spec", "archive_scanned",
    "government_report", "academic_thesis", "engineering_manual", "legal_document"
]
PRESET_TO_IDX = {p: i for i, p in enumerate(PRESETS)}


@dataclass
class TrainingConfig:
    """Training configuration."""
    # Model
    backbone: str = "mobilenetv2_100"
    pretrained: bool = True
    num_strategies: int = 3

    # Training
    epochs: int = 10
    batch_size: int = 32
    learning_rate: float = 1e-4
    weight_decay: float = 1e-5

    # Data
    train_file: Path = DATA_DIR / "labels" / "train.jsonl"
    eval_file: Optional[Path] = None
    image_size: int = 224

    # Output
    output_dir: Path = MODELS_DIR / "table-classifier-sft"
    log_file: Path = LOGS_DIR / "sft_training.log"

    # Hardware
    device: str = "cuda" if torch.cuda.is_available() else "cpu"
    num_workers: int = 4


class TableStrategyModel(nn.Module):
    """
    Vision model for table strategy prediction.

    Architecture:
    - MobileNetV2 backbone (pretrained ImageNet)
    - Strategy classification head (3 classes)
    - Parameter regression head (line_scale, edge_tol)
    - Optional preset embedding
    """

    def __init__(
        self,
        backbone: str = "mobilenetv2_100",
        pretrained: bool = True,
        num_strategies: int = 3,
        num_presets: int = 8,
        preset_embed_dim: int = 16,
    ):
        super().__init__()

        # Load pretrained backbone
        self.backbone = timm.create_model(
            backbone,
            pretrained=pretrained,
            num_classes=0,  # Remove classifier
        )

        # Get feature dimension
        with torch.no_grad():
            dummy = torch.randn(1, 3, 224, 224)
            features = self.backbone(dummy)
            self.feature_dim = features.shape[-1]

        # Preset embedding (optional input)
        self.preset_embedding = nn.Embedding(num_presets, preset_embed_dim)

        # Combined feature dimension
        combined_dim = self.feature_dim + preset_embed_dim

        # Classification head (strategy)
        self.strategy_head = nn.Sequential(
            nn.Linear(combined_dim, 256),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(256, num_strategies),
        )

        # Regression head (line_scale, edge_tol)
        self.param_head = nn.Sequential(
            nn.Linear(combined_dim, 128),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(128, 2),  # line_scale, edge_tol
        )

        # Confidence head
        self.confidence_head = nn.Sequential(
            nn.Linear(combined_dim, 64),
            nn.ReLU(),
            nn.Linear(64, 1),
            nn.Sigmoid(),
        )

    def forward(
        self,
        images: torch.Tensor,
        preset_ids: Optional[torch.Tensor] = None,
    ) -> dict:
        """
        Forward pass.

        Args:
            images: (B, 3, H, W) image tensor
            preset_ids: (B,) preset indices (optional)

        Returns:
            Dict with strategy_logits, params, confidence
        """
        # Extract image features
        features = self.backbone(images)  # (B, feature_dim)

        # Add preset embedding
        if preset_ids is not None:
            preset_emb = self.preset_embedding(preset_ids)
            features = torch.cat([features, preset_emb], dim=-1)
        else:
            # Use zero embedding if no preset
            batch_size = features.shape[0]
            zero_emb = torch.zeros(
                batch_size,
                self.preset_embedding.embedding_dim,
                device=features.device
            )
            features = torch.cat([features, zero_emb], dim=-1)

        # Predict strategy
        strategy_logits = self.strategy_head(features)

        # Predict parameters
        params = self.param_head(features)
        # Scale to reasonable ranges: line_scale [10, 50], edge_tol [100, 600]
        params = torch.stack([
            10 + 40 * torch.sigmoid(params[:, 0]),  # line_scale
            100 + 500 * torch.sigmoid(params[:, 1]),  # edge_tol
        ], dim=-1)

        # Predict confidence
        confidence = self.confidence_head(features)

        return {
            "strategy_logits": strategy_logits,
            "params": params,
            "confidence": confidence.squeeze(-1),
        }


class TableDataset(Dataset):
    """Dataset for table strategy classification."""

    def __init__(
        self,
        data_file: Path,
        image_dir: Path,
        image_size: int = 224,
        augment: bool = False,
    ):
        self.examples = []
        self.image_dir = image_dir

        # Load examples
        if data_file.exists():
            with data_file.open() as f:
                for line in f:
                    ex = json.loads(line)
                    # Only include examples with images
                    if ex.get("image_path"):
                        self.examples.append(ex)

        logger.info(f"Loaded {len(self.examples)} examples from {data_file}")

        # Image transforms
        if augment:
            self.transform = transforms.Compose([
                transforms.Resize((image_size, image_size)),
                transforms.RandomHorizontalFlip(p=0.3),
                transforms.RandomRotation(5),
                transforms.ColorJitter(brightness=0.2, contrast=0.2),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.485, 0.456, 0.406],
                    std=[0.229, 0.224, 0.225]
                ),
            ])
        else:
            self.transform = transforms.Compose([
                transforms.Resize((image_size, image_size)),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.485, 0.456, 0.406],
                    std=[0.229, 0.224, 0.225]
                ),
            ])

    def __len__(self):
        return len(self.examples)

    def __getitem__(self, idx):
        ex = self.examples[idx]

        # Load image
        img_path = SKILL_DIR / ex["image_path"]
        try:
            image = Image.open(img_path).convert("RGB")
            image = self.transform(image)
        except Exception as e:
            logger.warning(f"Failed to load image {img_path}: {e}")
            image = torch.zeros(3, 224, 224)

        # Get labels
        strategy = ex.get("strategy", "lattice")
        strategy_idx = STRATEGY_TO_IDX.get(strategy, 0)

        params = ex.get("params", {})
        line_scale = params.get("line_scale", 15)
        edge_tol = params.get("edge_tol", 300)

        preset = ex.get("preset", "unknown")
        preset_idx = PRESET_TO_IDX.get(preset, 0)

        quality = ex.get("quality_score", 0.8)

        return {
            "image": image,
            "strategy": strategy_idx,
            "line_scale": line_scale,
            "edge_tol": edge_tol,
            "preset": preset_idx,
            "quality": quality,
        }


def train_epoch(
    model: TableStrategyModel,
    dataloader: DataLoader,
    optimizer: torch.optim.Optimizer,
    device: str,
) -> dict:
    """Train for one epoch."""
    model.train()

    total_loss = 0.0
    strategy_correct = 0
    total = 0

    strategy_criterion = nn.CrossEntropyLoss()
    param_criterion = nn.MSELoss()

    for batch in tqdm(dataloader, desc="Training"):
        images = batch["image"].to(device)
        strategy_labels = batch["strategy"].to(device)
        line_scale_labels = batch["line_scale"].float().to(device)
        edge_tol_labels = batch["edge_tol"].float().to(device)
        preset_ids = batch["preset"].to(device)

        optimizer.zero_grad()

        # Forward pass
        outputs = model(images, preset_ids)

        # Strategy loss
        strategy_loss = strategy_criterion(
            outputs["strategy_logits"],
            strategy_labels
        )

        # Parameter loss (normalized)
        params_pred = outputs["params"]
        params_target = torch.stack([
            (line_scale_labels - 10) / 40,
            (edge_tol_labels - 100) / 500,
        ], dim=-1)
        params_pred_norm = torch.stack([
            (params_pred[:, 0] - 10) / 40,
            (params_pred[:, 1] - 100) / 500,
        ], dim=-1)
        param_loss = param_criterion(params_pred_norm, params_target)

        # Total loss
        loss = strategy_loss + 0.3 * param_loss

        loss.backward()
        optimizer.step()

        # Track metrics
        total_loss += loss.item()
        preds = outputs["strategy_logits"].argmax(dim=-1)
        strategy_correct += (preds == strategy_labels).sum().item()
        total += len(images)

    return {
        "loss": total_loss / len(dataloader),
        "strategy_accuracy": strategy_correct / total,
    }


@torch.no_grad()
def evaluate(
    model: TableStrategyModel,
    dataloader: DataLoader,
    device: str,
) -> dict:
    """Evaluate model on validation set."""
    model.eval()

    strategy_correct = 0
    param_mae = 0.0
    total = 0

    for batch in tqdm(dataloader, desc="Evaluating"):
        images = batch["image"].to(device)
        strategy_labels = batch["strategy"].to(device)
        line_scale_labels = batch["line_scale"].float().to(device)
        edge_tol_labels = batch["edge_tol"].float().to(device)
        preset_ids = batch["preset"].to(device)

        outputs = model(images, preset_ids)

        # Strategy accuracy
        preds = outputs["strategy_logits"].argmax(dim=-1)
        strategy_correct += (preds == strategy_labels).sum().item()

        # Parameter MAE
        params = outputs["params"]
        param_mae += (
            torch.abs(params[:, 0] - line_scale_labels).sum().item() +
            torch.abs(params[:, 1] - edge_tol_labels).sum().item()
        ) / 2

        total += len(images)

    return {
        "strategy_accuracy": strategy_correct / total,
        "param_mae": param_mae / total,
    }


@app.command()
def train(
    train_file: Path = typer.Option(
        DATA_DIR / "labels" / "train.jsonl",
        help="Training data JSONL"
    ),
    eval_file: Optional[Path] = typer.Option(
        None, help="Evaluation data JSONL (optional)"
    ),
    epochs: int = typer.Option(10, help="Number of epochs"),
    batch_size: int = typer.Option(32, help="Batch size"),
    learning_rate: float = typer.Option(1e-4, help="Learning rate"),
    output_dir: Path = typer.Option(
        MODELS_DIR / "table-classifier-sft",
        help="Output directory"
    ),
    backbone: str = typer.Option(
        "mobilenetv2_100", help="Timm backbone model"
    ),
    wandb: bool = typer.Option(False, help="Log to Weights & Biases"),
):
    """
    Train Table Strategy Classifier with supervised fine-tuning.

    Examples:
        ./run.sh warmup --train-file data/labels/train.jsonl --epochs 5
        ./run.sh warmup --wandb --backbone efficientnet_b0
    """
    logger.info("Starting SFT training")

    # Setup directories
    output_dir.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # Device
    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"Using device: {device}")

    # Create model
    model = TableStrategyModel(backbone=backbone, pretrained=True)
    model = model.to(device)
    logger.info(f"Model created with backbone: {backbone}")

    # Create datasets
    train_dataset = TableDataset(
        train_file,
        DATA_DIR / "images",
        augment=True
    )
    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=4,
        pin_memory=True,
    )

    eval_loader = None
    if eval_file and eval_file.exists():
        eval_dataset = TableDataset(
            eval_file,
            DATA_DIR / "images",
            augment=False
        )
        eval_loader = DataLoader(
            eval_dataset,
            batch_size=batch_size,
            shuffle=False,
            num_workers=4,
        )

    # Optimizer
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=learning_rate,
        weight_decay=1e-5
    )

    # Scheduler
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=epochs
    )

    # WandB
    if wandb:
        try:
            import wandb as wb
            wb.init(
                project="table-strategy-classifier",
                config={
                    "backbone": backbone,
                    "epochs": epochs,
                    "batch_size": batch_size,
                    "learning_rate": learning_rate,
                }
            )
        except ImportError:
            logger.warning("wandb not installed, skipping logging")
            wandb = False

    # Training loop
    best_accuracy = 0.0

    for epoch in range(epochs):
        logger.info(f"Epoch {epoch + 1}/{epochs}")

        # Train
        train_metrics = train_epoch(model, train_loader, optimizer, device)
        logger.info(f"Train - Loss: {train_metrics['loss']:.4f}, "
                    f"Accuracy: {train_metrics['strategy_accuracy']:.4f}")

        # Evaluate
        if eval_loader:
            eval_metrics = evaluate(model, eval_loader, device)
            logger.info(f"Eval - Accuracy: {eval_metrics['strategy_accuracy']:.4f}, "
                        f"Param MAE: {eval_metrics['param_mae']:.2f}")

            # Save best model
            if eval_metrics["strategy_accuracy"] > best_accuracy:
                best_accuracy = eval_metrics["strategy_accuracy"]
                torch.save({
                    "model_state_dict": model.state_dict(),
                    "config": {
                        "backbone": backbone,
                        "num_strategies": len(STRATEGIES),
                    },
                    "epoch": epoch,
                    "accuracy": best_accuracy,
                }, output_dir / "best_model.pth")
                logger.info(f"Saved best model (accuracy: {best_accuracy:.4f})")

        # Step scheduler
        scheduler.step()

        # Log to wandb
        if wandb:
            wb.log({
                "epoch": epoch,
                "train_loss": train_metrics["loss"],
                "train_accuracy": train_metrics["strategy_accuracy"],
                **(eval_metrics if eval_loader else {}),
            })

    # Save final model
    torch.save({
        "model_state_dict": model.state_dict(),
        "config": {
            "backbone": backbone,
            "num_strategies": len(STRATEGIES),
            "strategies": STRATEGIES,
            "presets": PRESETS,
        },
        "epoch": epochs,
    }, output_dir / "model.pth")

    # Save config
    config = {
        "backbone": backbone,
        "num_strategies": len(STRATEGIES),
        "strategies": STRATEGIES,
        "presets": PRESETS,
        "final_accuracy": best_accuracy if eval_loader else None,
    }
    (output_dir / "config.json").write_text(json.dumps(config, indent=2))

    logger.info(f"Training complete! Model saved to {output_dir}")


if __name__ == "__main__":
    app()
