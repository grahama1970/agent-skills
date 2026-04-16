#!/usr/bin/env python3
"""
Train table strategy classifier using DiT (Document Image Transformer) backbone.

DiT is pre-trained on 42M document images, making it ideal for table classification.
"""

import json
import sys
from pathlib import Path

import typer
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader

try:
    from transformers import AutoModel, AutoImageProcessor
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "transformers", "-q"])
    from transformers import AutoModel, AutoImageProcessor

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

app = typer.Typer(help="DiT-based table strategy classifier")

SKILL_DIR = Path(__file__).parent.parent
MODELS_DIR = SKILL_DIR / "models"
DATA_DIR = SKILL_DIR / "data"

STRATEGIES = ["lattice", "stream", "lattice_sensitive"]
PRESETS = [
    "unknown", "arxiv_scientific", "requirements_spec", "archive_scanned",
    "government_report", "academic_thesis", "engineering_manual", "legal_document"
]


class TableImageDataset(Dataset):
    """Dataset for table region images."""

    def __init__(self, jsonl_path: Path, transform=None, processor=None):
        self.examples = []
        self.transform = transform
        self.processor = processor
        self.base_dir = jsonl_path.parent.parent

        with jsonl_path.open() as f:
            for line in f:
                ex = json.loads(line)
                self.examples.append(ex)

        logger.info(f"Loaded {len(self.examples)} examples from {jsonl_path}")

    def __len__(self):
        return len(self.examples)

    def __getitem__(self, idx):
        ex = self.examples[idx]
        img_path = self.base_dir / ex["image_path"]

        try:
            image = Image.open(img_path).convert("RGB")
        except Exception:
            image = Image.new("RGB", (224, 224), (255, 255, 255))

        # Use processor if available, otherwise transform
        if self.processor:
            inputs = self.processor(images=image, return_tensors="pt")
            pixel_values = inputs["pixel_values"].squeeze(0)
        else:
            pixel_values = self.transform(image)

        strategy_idx = STRATEGIES.index(ex["strategy"])
        preset = ex.get("preset", "unknown")
        preset_idx = PRESETS.index(preset) if preset in PRESETS else 0  # Default to "unknown"

        return {
            "pixel_values": pixel_values,
            "strategy_label": strategy_idx,
            "preset_idx": preset_idx,
        }


class DiTClassifier(nn.Module):
    """DiT backbone with classification head."""

    def __init__(self, model_name: str = "microsoft/dit-base", num_strategies: int = 3,
                 num_presets: int = 8, preset_embed_dim: int = 16, freeze_backbone: bool = False):
        super().__init__()
        self.backbone = AutoModel.from_pretrained(model_name, trust_remote_code=True)

        if freeze_backbone:
            for param in self.backbone.parameters():
                param.requires_grad = False

        # DiT-base has hidden_size of 768
        self.hidden_size = self.backbone.config.hidden_size

        self.preset_embedding = nn.Embedding(num_presets, preset_embed_dim)
        combined_dim = self.hidden_size + preset_embed_dim

        self.strategy_head = nn.Sequential(
            nn.Linear(combined_dim, 256),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(256, num_strategies),
        )

        self.param_head = nn.Sequential(
            nn.Linear(combined_dim, 128),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(128, 2),
        )

        self.confidence_head = nn.Sequential(
            nn.Linear(combined_dim, 64),
            nn.ReLU(),
            nn.Linear(64, 1),
            nn.Sigmoid(),
        )

    def forward(self, pixel_values: torch.Tensor, preset_ids: torch.Tensor = None) -> dict:
        # Get DiT features - use CLS token (first token)
        outputs = self.backbone(pixel_values=pixel_values)
        features = outputs.last_hidden_state[:, 0]  # CLS token

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

        return {
            "strategy_logits": strategy_logits,
            "params": params,
            "confidence": confidence.squeeze(-1),
        }


@app.command()
def train(
    train_file: Path = typer.Option(DATA_DIR / "labels" / "train_balanced.jsonl", help="Training data"),
    eval_file: Path = typer.Option(DATA_DIR / "labels" / "eval.jsonl", help="Evaluation data"),
    epochs: int = typer.Option(10, help="Number of epochs"),
    batch_size: int = typer.Option(16, help="Batch size (smaller due to DiT size)"),
    learning_rate: float = typer.Option(2e-5, help="Learning rate"),
    model_name: str = typer.Option("microsoft/dit-base", help="DiT model variant"),
    output_dir: Path = typer.Option(MODELS_DIR / "table-classifier-dit", help="Output directory"),
    freeze_backbone: bool = typer.Option(False, help="Freeze DiT backbone (fine-tune heads only)"),
):
    """Train DiT-based table strategy classifier."""
    logger.info(f"Starting DiT training with {model_name}")
    logger.info(f"Config: epochs={epochs}, batch_size={batch_size}, freeze_backbone={freeze_backbone}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"Device: {device}")

    # Load processor and create datasets
    processor = AutoImageProcessor.from_pretrained(model_name)

    train_dataset = TableImageDataset(train_file, processor=processor)
    eval_dataset = TableImageDataset(eval_file, processor=processor)

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, num_workers=4)
    eval_loader = DataLoader(eval_dataset, batch_size=batch_size, shuffle=False, num_workers=4)

    # Create model
    model = DiTClassifier(model_name=model_name, freeze_backbone=freeze_backbone)
    model.to(device)

    # Optimizer
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=0.01)

    # Scheduler
    total_steps = len(train_loader) * epochs
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=total_steps)

    best_accuracy = 0.0
    output_dir.mkdir(parents=True, exist_ok=True)
    history = []

    for epoch in range(epochs):
        # Training
        model.train()
        total_loss = 0.0

        for batch in tqdm(train_loader, desc=f"Epoch {epoch+1}/{epochs}"):
            pixel_values = batch["pixel_values"].to(device)
            strategy_labels = batch["strategy_label"].to(device)
            preset_ids = batch["preset_idx"].to(device)

            optimizer.zero_grad()
            outputs = model(pixel_values, preset_ids)

            loss = F.cross_entropy(outputs["strategy_logits"], strategy_labels)
            loss.backward()

            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()

            total_loss += loss.item()

        avg_loss = total_loss / len(train_loader)
        logger.info(f"Epoch {epoch+1} - Train Loss: {avg_loss:.4f}")

        # Evaluation
        model.eval()
        correct = 0
        total = 0
        per_class_correct = {s: 0 for s in STRATEGIES}
        per_class_total = {s: 0 for s in STRATEGIES}

        with torch.no_grad():
            for batch in tqdm(eval_loader, desc="Evaluating"):
                pixel_values = batch["pixel_values"].to(device)
                strategy_labels = batch["strategy_label"].to(device)
                preset_ids = batch["preset_idx"].to(device)

                outputs = model(pixel_values, preset_ids)
                preds = outputs["strategy_logits"].argmax(dim=-1)

                correct += (preds == strategy_labels).sum().item()
                total += strategy_labels.size(0)

                for pred, label in zip(preds.cpu().numpy(), strategy_labels.cpu().numpy()):
                    strategy = STRATEGIES[label]
                    per_class_total[strategy] += 1
                    if pred == label:
                        per_class_correct[strategy] += 1

        accuracy = correct / total if total > 0 else 0
        per_class_acc = {s: per_class_correct[s] / per_class_total[s] if per_class_total[s] > 0 else 0
                         for s in STRATEGIES}

        logger.info(f"Eval Accuracy: {accuracy:.4f}")
        logger.info(f"Per-class: {per_class_acc}")

        history.append({
            "epoch": epoch + 1,
            "train_loss": avg_loss,
            "eval_accuracy": accuracy,
            "per_class": per_class_acc,
        })

        # Save best model
        if accuracy > best_accuracy:
            best_accuracy = accuracy
            torch.save({
                "model_state_dict": model.state_dict(),
                "epoch": epoch + 1,
                "accuracy": accuracy,
            }, output_dir / "best_model.pth")
            logger.info(f"Saved best model (accuracy: {accuracy:.4f})")

    # Save final model and config
    torch.save({
        "model_state_dict": model.state_dict(),
        "epoch": epochs,
        "accuracy": accuracy,
    }, output_dir / "model.pth")

    config = {
        "backbone": model_name,
        "backbone_type": "dit",
        "num_strategies": len(STRATEGIES),
        "strategies": STRATEGIES,
        "presets": PRESETS,
        "final_accuracy": best_accuracy,
        "training": {
            "epochs": epochs,
            "batch_size": batch_size,
            "learning_rate": learning_rate,
            "freeze_backbone": freeze_backbone,
        }
    }
    (output_dir / "config.json").write_text(json.dumps(config, indent=2))
    (output_dir / "history.json").write_text(json.dumps(history, indent=2))

    logger.info(f"Training complete. Best accuracy: {best_accuracy:.4f}")
    return best_accuracy


if __name__ == "__main__":
    app()
