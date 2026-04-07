#!/usr/bin/env python3
"""
Inference for Table Strategy Classifier.

Provides strategy prediction for integration with S05 table extractor.
Supports single models and ensemble models (EfficientNet-B0 + EdgeNeXt-small).

Can run as CLI or be imported as a library.
"""

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union, List, Dict

import torch
import torch.nn.functional as F
from torchvision import transforms
from PIL import Image
import typer

from loguru import logger

# Local imports
from train_sft import (
    TableStrategyModel,
    STRATEGIES,
    PRESETS,
    PRESET_TO_IDX,
)
try:
    from taxonomy_bridge import (
        get_preset_recommendation,
        get_strategy_bridges,
    )
except ImportError:
    # Fallback if taxonomy_bridge not available
    def get_preset_recommendation(preset):
        return {}
    def get_strategy_bridges(strategy):
        return []

app = typer.Typer(help="Strategy prediction and model export")

# Paths
SKILL_DIR = Path(__file__).parent.parent
MODELS_DIR = SKILL_DIR / "models"


@dataclass
class StrategyPrediction:
    """Predicted extraction strategy."""
    strategy: str  # "lattice", "stream", "lattice_sensitive"
    line_scale: int
    edge_tol: int
    confidence: float
    preset_hint: Optional[str] = None
    bridge_tags: list = None

    def __post_init__(self):
        if self.bridge_tags is None:
            self.bridge_tags = get_strategy_bridges(self.strategy)

    @property
    def flavor(self) -> str:
        """Get Camelot flavor parameter."""
        if self.strategy in ("lattice", "lattice_sensitive"):
            return "lattice"
        return "stream"

    def to_camelot_params(self) -> dict:
        """Convert to Camelot read_pdf kwargs."""
        params = {"flavor": self.flavor}
        if self.flavor == "lattice":
            params["line_scale"] = self.line_scale
        else:
            params["edge_tol"] = self.edge_tol
        return params

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "strategy": self.strategy,
            "line_scale": self.line_scale,
            "edge_tol": self.edge_tol,
            "confidence": self.confidence,
            "preset_hint": self.preset_hint,
            "bridge_tags": self.bridge_tags,
            "camelot_params": self.to_camelot_params(),
        }


class TableStrategyPredictor:
    """
    Predict optimal Camelot strategy for table region images.

    Supports:
    - Single model inference (EfficientNet, EdgeNeXt, MobileNet, etc.)
    - Ensemble inference with weighted voting (95%+ accuracy)

    Usage:
        predictor = TableStrategyPredictor("models/table-classifier-ensemble-final")
        pred = predictor.predict(region_image, preset="arxiv_scientific")

        if pred.confidence > 0.8:
            strategies_to_try = [pred.to_camelot_params()] + fallback_strategies
    """

    def __init__(
        self,
        model_path: Optional[Path] = None,
        device: str = None,
    ):
        """
        Initialize predictor.

        Args:
            model_path: Path to model checkpoint or ensemble config
            device: "cuda" or "cpu" (auto-detect if None)
        """
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = None
        self.models = []  # For ensemble
        self.weights = []  # Ensemble weights
        self.config = None
        self.is_ensemble = False

        if model_path and Path(model_path).exists():
            self._load_model(Path(model_path))
        else:
            logger.warning("No model found, using heuristic prediction")

        # Image preprocessing
        self.transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225]
            ),
        ])

    def _load_model(self, model_path: Path):
        """Load model from checkpoint or ensemble config."""
        try:
            # Check for ensemble config
            config_path = model_path / "config.json" if model_path.is_dir() else None
            if config_path and config_path.exists():
                config = json.loads(config_path.read_text())
                if config.get("type") == "ensemble":
                    self._load_ensemble(model_path, config)
                    return

            # Single model loading
            self._load_single_model(model_path)

        except Exception as e:
            logger.warning(f"Failed to load model: {e}")
            self.model = None
            self.models = []

    def _load_ensemble(self, model_path: Path, config: dict):
        """Load ensemble of models with weights."""
        self.config = config
        self.is_ensemble = True
        self.models = []
        self.weights = []

        # Paths in config are relative to SKILL_DIR (e.g., "models/table-classifier-efficientnet-b0")
        # So we need to use SKILL_DIR as the base
        base_dir = SKILL_DIR

        for model_name, model_info in config.get("models", {}).items():
            rel_path = model_info.get("path", f"models/{model_name}")
            full_path = base_dir / rel_path
            weight = model_info.get("weight", 0.5)

            try:
                model = self._load_single_model_from_path(full_path)
                if model is not None:
                    self.models.append(model)
                    self.weights.append(weight)
                    logger.info(f"Loaded ensemble member {model_name} (weight={weight})")
            except Exception as e:
                logger.warning(f"Failed to load ensemble member {model_name}: {e}")

        # Normalize weights
        total_weight = sum(self.weights)
        if total_weight > 0:
            self.weights = [w / total_weight for w in self.weights]

        logger.info(f"Loaded ensemble with {len(self.models)} models, accuracy={config.get('accuracy', 'unknown')}")

    def _load_single_model_from_path(self, model_path: Path) -> Optional[TableStrategyModel]:
        """Load a single model and return it."""
        if model_path.is_dir():
            ckpt_path = model_path / "best_model.pth"
            if not ckpt_path.exists():
                ckpt_path = model_path / "model.pth"
            config_path = model_path / "config.json"
        else:
            ckpt_path = model_path
            config_path = model_path.parent / "config.json"

        if not ckpt_path.exists():
            logger.warning(f"Model not found at {ckpt_path}")
            return None

        # Load config
        model_config = {}
        if config_path.exists():
            model_config = json.loads(config_path.read_text())

        ckpt = torch.load(ckpt_path, map_location=self.device, weights_only=False)
        ckpt_config = ckpt.get("config", {})

        # Merge configs (checkpoint takes precedence)
        final_config = {**model_config, **ckpt_config}
        backbone = final_config.get("backbone", "mobilenetv2_100")

        model = TableStrategyModel(
            backbone=backbone,
            pretrained=False,
        )
        model.load_state_dict(ckpt["model_state_dict"])
        model = model.to(self.device)
        model.eval()

        return model

    def _load_single_model(self, model_path: Path):
        """Load single model from checkpoint."""
        try:
            if model_path.is_dir():
                ckpt_path = model_path / "best_model.pth"
                if not ckpt_path.exists():
                    ckpt_path = model_path / "model.pth"
                config_path = model_path / "config.json"
            else:
                ckpt_path = model_path
                config_path = model_path.parent / "config.json"

            if not ckpt_path.exists():
                logger.warning(f"Model not found at {ckpt_path}")
                return

            # Load config
            if config_path.exists():
                self.config = json.loads(config_path.read_text())
            else:
                self.config = {}

            ckpt = torch.load(ckpt_path, map_location=self.device, weights_only=False)
            ckpt_config = ckpt.get("config", {})
            self.config = {**self.config, **ckpt_config}

            backbone = self.config.get("backbone", "mobilenetv2_100")

            self.model = TableStrategyModel(
                backbone=backbone,
                pretrained=False,
            )
            self.model.load_state_dict(ckpt["model_state_dict"])
            self.model = self.model.to(self.device)
            self.model.eval()

            logger.info(f"Loaded model from {ckpt_path} (backbone={backbone})")

        except Exception as e:
            logger.warning(f"Failed to load model: {e}")
            self.model = None

    def predict(
        self,
        image: Union[Image.Image, Path, str],
        preset: Optional[str] = None,
    ) -> StrategyPrediction:
        """
        Predict optimal extraction strategy for table image.

        Args:
            image: PIL Image, or path to image file
            preset: Optional document preset hint

        Returns:
            StrategyPrediction with strategy, params, confidence
        """
        # Load image if path
        if isinstance(image, (str, Path)):
            image = Image.open(image).convert("RGB")

        # Use ensemble if available
        if self.is_ensemble and len(self.models) > 0:
            return self._ensemble_predict(image, preset)

        # Use single model if available
        if self.model is not None:
            return self._model_predict(image, preset)

        # Fallback to heuristic
        return self._heuristic_predict(image, preset)

    @torch.no_grad()
    def _ensemble_predict(
        self,
        image: Image.Image,
        preset: Optional[str] = None,
    ) -> StrategyPrediction:
        """Predict using ensemble with weighted voting."""
        # Preprocess
        img_tensor = self.transform(image).unsqueeze(0).to(self.device)

        # Get preset index
        preset_idx = PRESET_TO_IDX.get(preset, 0)
        preset_tensor = torch.tensor([preset_idx], device=self.device)

        # Collect predictions from all models
        all_probs = []
        all_params = []

        for model in self.models:
            outputs = model(img_tensor, preset_tensor)
            logits = outputs["strategy_logits"][0]
            probs = F.softmax(logits, dim=-1)
            all_probs.append(probs)
            all_params.append(outputs["params"][0])

        # Weighted average of probabilities
        weighted_probs = torch.zeros(len(STRATEGIES), device=self.device)
        for probs, weight in zip(all_probs, self.weights):
            weighted_probs += probs * weight

        # Get final prediction
        strategy_idx = weighted_probs.argmax().item()
        confidence = weighted_probs[strategy_idx].item()

        # Weighted average of parameters
        line_scale = 0.0
        edge_tol = 0.0
        for params, weight in zip(all_params, self.weights):
            line_scale += params[0].item() * weight
            edge_tol += params[1].item() * weight

        return StrategyPrediction(
            strategy=STRATEGIES[strategy_idx],
            line_scale=int(line_scale),
            edge_tol=int(edge_tol),
            confidence=confidence,
            preset_hint=preset,
        )

    @torch.no_grad()
    def _model_predict(
        self,
        image: Image.Image,
        preset: Optional[str] = None,
    ) -> StrategyPrediction:
        """Predict using single trained model."""
        # Preprocess
        img_tensor = self.transform(image).unsqueeze(0).to(self.device)

        # Get preset index
        preset_idx = PRESET_TO_IDX.get(preset, 0)
        preset_tensor = torch.tensor([preset_idx], device=self.device)

        # Forward pass
        outputs = self.model(img_tensor, preset_tensor)

        # Get predictions
        logits = outputs["strategy_logits"][0]
        probs = F.softmax(logits, dim=-1)
        strategy_idx = probs.argmax().item()
        confidence = probs[strategy_idx].item()

        params = outputs["params"][0]
        line_scale = int(params[0].item())
        edge_tol = int(params[1].item())

        return StrategyPrediction(
            strategy=STRATEGIES[strategy_idx],
            line_scale=line_scale,
            edge_tol=edge_tol,
            confidence=confidence,
            preset_hint=preset,
        )

    def _heuristic_predict(
        self,
        image: Image.Image,
        preset: Optional[str] = None,
    ) -> StrategyPrediction:
        """
        Fallback heuristic prediction based on image analysis.

        Uses simple image features to guess strategy.
        """
        import numpy as np

        # Convert to grayscale and analyze
        gray = np.array(image.convert("L"))

        # Compute edge density (rough line detection proxy)
        from scipy import ndimage
        edges = ndimage.sobel(gray)
        edge_density = np.mean(np.abs(edges)) / 255.0

        # High edge density suggests lattice
        if edge_density > 0.15:
            strategy = "lattice"
            line_scale = 20
        elif edge_density > 0.08:
            strategy = "lattice_sensitive"
            line_scale = 15
        else:
            strategy = "stream"
            line_scale = 30

        # Adjust based on preset if available
        if preset:
            rec = get_preset_recommendation(preset)
            if rec:
                strategy = rec.get("recommended_strategy", strategy)
                ls_min, ls_max = rec.get("line_scale_range", (15, 30))
                line_scale = (ls_min + ls_max) // 2
                et_min, et_max = rec.get("edge_tol_range", (200, 400))
                edge_tol = (et_min + et_max) // 2
            else:
                edge_tol = 300
        else:
            edge_tol = 300

        return StrategyPrediction(
            strategy=strategy,
            line_scale=line_scale,
            edge_tol=edge_tol,
            confidence=0.6,  # Lower confidence for heuristic
            preset_hint=preset,
        )


# Global predictor instance for CLI
_predictor: Optional[TableStrategyPredictor] = None

# Default model path - ensemble with 95.07% accuracy
DEFAULT_MODEL_PATH = MODELS_DIR / "table-classifier-ensemble-final"


def get_predictor(model_path: Optional[Path] = None) -> TableStrategyPredictor:
    """Get or create global predictor instance."""
    global _predictor
    if _predictor is None:
        # Try ensemble first, fall back to single model
        if model_path:
            _predictor = TableStrategyPredictor(model_path)
        elif DEFAULT_MODEL_PATH.exists():
            _predictor = TableStrategyPredictor(DEFAULT_MODEL_PATH)
        else:
            # Fallback to table-classifier-final if ensemble not available
            fallback_path = MODELS_DIR / "table-classifier-final"
            _predictor = TableStrategyPredictor(fallback_path)
    return _predictor


@app.command()
def predict(
    image: Path = typer.Argument(..., help="Path to table image"),
    preset: Optional[str] = typer.Option(None, help="Document preset"),
    model_path: Optional[Path] = typer.Option(None, help="Model path"),
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
):
    """
    Predict extraction strategy for a table image.

    Examples:
        ./run.sh infer --image data/images/test/table.png
        ./run.sh infer --image table.png --preset arxiv_scientific --json
    """
    predictor = TableStrategyPredictor(model_path)
    pred = predictor.predict(image, preset)

    if json_output:
        print(json.dumps(pred.to_dict(), indent=2))
    else:
        print(f"Strategy: {pred.strategy}")
        print(f"Line Scale: {pred.line_scale}")
        print(f"Edge Tolerance: {pred.edge_tol}")
        print(f"Confidence: {pred.confidence:.2f}")
        print(f"Camelot Params: {pred.to_camelot_params()}")


@app.command()
def export(
    model_path: Path = typer.Option(
        MODELS_DIR / "table-classifier-grpo",
        help="Model to export"
    ),
    output_path: Path = typer.Option(
        MODELS_DIR / "table-classifier-final",
        help="Export destination"
    ),
    include_config: bool = typer.Option(True, help="Include config.json"),
):
    """
    Export trained model for S05 integration.

    Copies model and creates config for easy deployment.

    Examples:
        ./run.sh export --model-path models/grpo --output-path models/final
    """
    import shutil

    # Find best checkpoint
    if model_path.is_dir():
        # Find most recent attempt
        attempts = sorted(model_path.glob("attempt_*"))
        if attempts:
            source = attempts[-1] / "model.pth"
        else:
            source = model_path / "model.pth"
    else:
        source = model_path

    if not source.exists():
        logger.error(f"Model not found: {source}")
        raise typer.Exit(1)

    # Create output directory
    output_path.mkdir(parents=True, exist_ok=True)

    # Copy model
    shutil.copy(source, output_path / "model.pth")
    logger.info(f"Exported model to {output_path}/model.pth")

    # Load and save config
    if include_config:
        ckpt = torch.load(source, map_location="cpu")
        config = ckpt.get("config", {})
        config["exported_from"] = str(source)
        config["strategies"] = STRATEGIES
        config["presets"] = PRESETS

        (output_path / "config.json").write_text(
            json.dumps(config, indent=2)
        )
        logger.info(f"Saved config to {output_path}/config.json")

    # Create preset embeddings file for S05
    preset_mappings = {}
    for preset in PRESETS:
        rec = get_preset_recommendation(preset)
        preset_mappings[preset] = {
            "recommended_strategy": rec.get("recommended_strategy", "lattice"),
            "line_scale_range": rec.get("line_scale_range", (15, 30)),
            "edge_tol_range": rec.get("edge_tol_range", (200, 400)),
            "bridge_hints": rec.get("bridge_hints", []),
        }

    (output_path / "preset_embeddings.json").write_text(
        json.dumps(preset_mappings, indent=2)
    )
    logger.info(f"Saved preset embeddings to {output_path}/preset_embeddings.json")

    print(f"Export complete: {output_path}")


if __name__ == "__main__":
    app()
