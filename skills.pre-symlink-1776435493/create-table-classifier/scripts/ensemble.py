#!/usr/bin/env python3
"""
Ensemble prediction combining multiple table strategy classifiers.

Combines EfficientNet-B0 (94.54%) and EdgeNeXt-small (94.41%) for potentially
higher accuracy through weighted voting.
"""

import json
import sys
from pathlib import Path
from typing import Optional

import typer
import torch
import torch.nn as nn
import torch.nn.functional as F

try:
    import timm
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "timm", "-q"])
    import timm

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

app = typer.Typer(help="Ensemble table strategy classifier")

SKILL_DIR = Path(__file__).parent.parent
MODELS_DIR = SKILL_DIR / "models"
DATA_DIR = SKILL_DIR / "data"

STRATEGIES = ["lattice", "stream", "lattice_sensitive"]
PRESETS = [
    "unknown", "arxiv_scientific", "requirements_spec", "archive_scanned",
    "government_report", "academic_thesis", "engineering_manual", "legal_document"
]


class TableStrategyModel(nn.Module):
    """Vision model for table strategy prediction."""

    def __init__(self, backbone: str = "efficientnet_b0", pretrained: bool = False,
                 num_strategies: int = 3, num_presets: int = 8, preset_embed_dim: int = 16):
        super().__init__()
        self.backbone = timm.create_model(backbone, pretrained=pretrained, num_classes=0)

        with torch.no_grad():
            dummy = torch.randn(1, 3, 224, 224)
            features = self.backbone(dummy)
            self.feature_dim = features.shape[-1]

        self.preset_embedding = nn.Embedding(num_presets, preset_embed_dim)
        combined_dim = self.feature_dim + preset_embed_dim

        self.strategy_head = nn.Sequential(
            nn.Linear(combined_dim, 256), nn.ReLU(), nn.Dropout(0.2),
            nn.Linear(256, num_strategies),
        )
        self.param_head = nn.Sequential(
            nn.Linear(combined_dim, 128), nn.ReLU(), nn.Dropout(0.2),
            nn.Linear(128, 2),
        )
        self.confidence_head = nn.Sequential(
            nn.Linear(combined_dim, 64), nn.ReLU(), nn.Linear(64, 1), nn.Sigmoid(),
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


class EnsemblePredictor:
    """Ensemble of multiple table strategy classifiers."""

    def __init__(self, model_paths: list[Path], weights: Optional[list[float]] = None, device: str = "cuda"):
        self.device = device if torch.cuda.is_available() else "cpu"
        self.models = []
        self.weights = weights or [1.0 / len(model_paths)] * len(model_paths)

        assert len(self.weights) == len(model_paths), "Weights must match number of models"
        assert abs(sum(self.weights) - 1.0) < 0.01, "Weights must sum to 1.0"

        for path in model_paths:
            config_file = path / "config.json"
            model_file = path / "model.pth"

            if not config_file.exists() or not model_file.exists():
                logger.warning(f"Skipping {path}: missing config or model")
                continue

            config = json.loads(config_file.read_text())
            backbone = config.get("backbone", "efficientnet_b0")

            model = TableStrategyModel(backbone=backbone, pretrained=False)
            checkpoint = torch.load(model_file, map_location=self.device)
            model.load_state_dict(checkpoint["model_state_dict"])
            model.to(self.device)
            model.eval()

            self.models.append(model)
            logger.info(f"Loaded {backbone} from {path}")

        self.transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])

    @torch.no_grad()
    def predict(self, image: Image.Image, preset_idx: int = 0) -> dict:
        """Ensemble prediction with weighted voting."""
        img_tensor = self.transform(image).unsqueeze(0).to(self.device)
        preset_tensor = torch.tensor([preset_idx], device=self.device)

        # Collect predictions from all models
        all_logits = []
        all_params = []
        all_confidences = []

        for model in self.models:
            outputs = model(img_tensor, preset_tensor)
            all_logits.append(outputs["strategy_logits"])
            all_params.append(outputs["params"])
            all_confidences.append(outputs["confidence"])

        # Weighted average of softmax probabilities
        ensemble_probs = torch.zeros_like(all_logits[0])
        for logits, weight in zip(all_logits, self.weights):
            ensemble_probs += weight * F.softmax(logits, dim=-1)

        # Weighted average of parameters
        ensemble_params = torch.zeros_like(all_params[0])
        for params, weight in zip(all_params, self.weights):
            ensemble_params += weight * params

        # Weighted average of confidence
        ensemble_conf = sum(c * w for c, w in zip(all_confidences, self.weights))

        strategy_idx = ensemble_probs.argmax(dim=-1).item()

        return {
            "strategy": STRATEGIES[strategy_idx],
            "strategy_idx": strategy_idx,
            "probabilities": ensemble_probs[0].cpu().tolist(),
            "line_scale": ensemble_params[0, 0].item(),
            "edge_tol": ensemble_params[0, 1].item(),
            "confidence": ensemble_conf.item(),
        }


@app.command()
def evaluate(
    model_dirs: str = typer.Option(
        "models/table-classifier-efficientnet-b0,models/table-classifier-edgenext-small",
        help="Comma-separated model directories"
    ),
    weights: str = typer.Option("0.55,0.45", help="Comma-separated weights (must sum to 1.0)"),
    eval_file: Path = typer.Option(DATA_DIR / "labels" / "eval.jsonl", help="Evaluation JSONL"),
):
    """Evaluate ensemble on holdout set."""
    model_paths = [SKILL_DIR / d.strip() for d in model_dirs.split(",")]
    weight_list = [float(w.strip()) for w in weights.split(",")]

    logger.info(f"Creating ensemble with {len(model_paths)} models")
    logger.info(f"Weights: {weight_list}")

    ensemble = EnsemblePredictor(model_paths, weight_list)

    # Load eval data
    examples = []
    with eval_file.open() as f:
        for line in f:
            examples.append(json.loads(line))

    logger.info(f"Evaluating on {len(examples)} examples")

    correct = 0
    total = 0

    for ex in tqdm(examples, desc="Evaluating"):
        img_path = SKILL_DIR / ex["image_path"]
        if not img_path.exists():
            continue

        image = Image.open(img_path).convert("RGB")
        pred = ensemble.predict(image)

        if pred["strategy"] == ex["strategy"]:
            correct += 1
        total += 1

    accuracy = correct / total if total > 0 else 0
    logger.info(f"Ensemble Accuracy: {accuracy:.4f} ({correct}/{total})")

    return accuracy


@app.command()
def export(
    model_dirs: str = typer.Option(
        "models/table-classifier-efficientnet-b0,models/table-classifier-edgenext-small",
        help="Comma-separated model directories"
    ),
    weights: str = typer.Option("0.55,0.45", help="Comma-separated weights"),
    output_dir: Path = typer.Option(MODELS_DIR / "table-classifier-ensemble", help="Output directory"),
):
    """Export ensemble configuration."""
    output_dir.mkdir(parents=True, exist_ok=True)

    model_paths = [d.strip() for d in model_dirs.split(",")]
    weight_list = [float(w.strip()) for w in weights.split(",")]

    config = {
        "type": "ensemble",
        "models": model_paths,
        "weights": weight_list,
        "strategies": STRATEGIES,
        "presets": PRESETS,
    }

    (output_dir / "config.json").write_text(json.dumps(config, indent=2))
    logger.info(f"Exported ensemble config to {output_dir}")


if __name__ == "__main__":
    app()
