#!/usr/bin/env python3
"""
Inference API for cross-page table merge classifier.

Loads a model trained by classifier-lab and provides a thin ``predict()``
interface consumed by S05c ``_merge_with_classifier()``.

Supports:
  - Vision model (side-by-side page-half image → merge/separate)
  - Tabular model (feature vector → merge/separate)
  - Ensemble of both

Usage as library::

    from merge_inference import TableMergePredictor, get_merge_predictor

    pred = get_merge_predictor()
    result = pred.predict(pair_image_path)
    if result.should_merge and result.confidence > 0.7:
        ...

Usage as CLI::

    python merge_inference.py predict pair.png --json
"""

from __future__ import annotations

import json
import os
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from loguru import logger

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_sklearn_model(path: Path):
    """Load a sklearn model from .pkl or .joblib file."""
    path = Path(path)
    if path.suffix == ".joblib":
        try:
            import joblib
            return joblib.load(path)
        except ImportError:
            pass
    with open(path, "rb") as f:
        return pickle.load(f)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SKILL_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = SKILL_DIR / "models"
DEFAULT_MERGE_MODEL_PATH = MODELS_DIR / "merge-classifier-final"


# ---------------------------------------------------------------------------
# Prediction result
# ---------------------------------------------------------------------------

@dataclass
class MergePrediction:
    """Result of a merge/separate classification."""
    should_merge: bool
    confidence: float
    raw_score: float  # P(merge)
    model_type: str = "unknown"  # "vision", "tabular", "ensemble", "heuristic"

    def to_dict(self) -> dict:
        return {
            "should_merge": self.should_merge,
            "confidence": self.confidence,
            "raw_score": self.raw_score,
            "model_type": self.model_type,
        }


# ---------------------------------------------------------------------------
# Predictor
# ---------------------------------------------------------------------------

class TableMergePredictor:
    """Loads a classifier-lab trained model for merge prediction.

    Model types supported:

    * **Vision** — PyTorch image classifier (``best_model.pth`` or
      ``model.pth``) trained on side-by-side page-half images.
    * **Tabular** — scikit-learn model (``model.pkl``) trained on 9-feature
      vectors.
    * **Ensemble** — ``config.json`` with ``"type": "ensemble"`` pointing at
      a vision and a tabular sub-model.
    """

    def __init__(self, model_path: Optional[Path] = None):
        self.model_path = Path(model_path) if model_path else DEFAULT_MERGE_MODEL_PATH
        self._vision_model = None
        self._tabular_model = None
        self._transform = None
        self._config: Dict[str, Any] = {}
        self._model_type = "heuristic"
        self._loaded = False

    # -- lazy loading -------------------------------------------------------

    def _lazy_load(self):
        if self._loaded:
            return
        self._loaded = True

        if not self.model_path.exists():
            logger.warning(f"Merge model not found at {self.model_path}, using heuristic")
            return

        config_path = self.model_path / "config.json" if self.model_path.is_dir() else None
        if config_path and config_path.exists():
            self._config = json.loads(config_path.read_text())
        else:
            self._config = {}

        model_type = self._config.get("type", "vision")

        if model_type == "ensemble":
            self._load_ensemble()
        elif model_type == "tabular":
            self._load_tabular()
        else:
            self._load_vision()

    def _load_vision(self):
        """Load a PyTorch vision model."""
        try:
            import torch
            from torchvision import transforms

            ckpt_path = self._find_checkpoint(extensions=(".pth", ".pt"))
            if ckpt_path is None:
                return

            ckpt = torch.load(str(ckpt_path), map_location="cpu", weights_only=False)
            model_state = ckpt.get("model_state_dict", ckpt)
            backbone = self._config.get("backbone", "convnextv2_nano")

            # Use timm to create the model architecture
            import timm
            model = timm.create_model(backbone, pretrained=False, num_classes=2)
            model.load_state_dict(model_state, strict=False)
            model.eval()

            self._vision_model = model
            self._transform = transforms.Compose([
                transforms.Resize((224, 224)),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.485, 0.456, 0.406],
                    std=[0.229, 0.224, 0.225],
                ),
            ])
            self._model_type = "vision"
            logger.info(f"Loaded vision merge model from {ckpt_path} (backbone={backbone})")

        except Exception as e:
            logger.warning(f"Failed to load vision merge model: {e}")

    def _load_tabular(self):
        """Load a scikit-learn tabular model."""
        try:
            pkl_path = self._find_checkpoint(extensions=(".pkl", ".joblib"))
            if pkl_path is None:
                return
            self._tabular_model = _load_sklearn_model(pkl_path)
            self._model_type = "tabular"
            logger.info(f"Loaded tabular merge model from {pkl_path}")
        except Exception as e:
            logger.warning(f"Failed to load tabular merge model: {e}")

    def _load_ensemble(self):
        """Load both vision and tabular sub-models."""
        sub = self._config.get("models", {})
        base = self.model_path if self.model_path.is_dir() else self.model_path.parent

        if "vision" in sub:
            vp = base / sub["vision"].get("path", "vision")
            try:
                self._config_bak = self._config
                self._config = sub["vision"].get("config", {})
                self.model_path = vp
                self._load_vision()
                self._config = self._config_bak
            except Exception as e:
                logger.debug("loading failed: {}", e)

        if "tabular" in sub:
            tp = base / sub["tabular"].get("path", "tabular")
            try:
                # Check for model.pkl, model.joblib, best_model.joblib
                pkl = None
                for name in ("model.pkl", "model.joblib", "best_model.joblib"):
                    candidate = tp / name
                    if candidate.exists():
                        pkl = candidate
                        break
                if pkl is not None:
                    self._tabular_model = _load_sklearn_model(pkl)
            except Exception as e:
                logger.debug("loading failed: {}", e)

        if self._vision_model and self._tabular_model:
            self._model_type = "ensemble"
        elif self._vision_model:
            self._model_type = "vision"
        elif self._tabular_model:
            self._model_type = "tabular"

    def _find_checkpoint(self, extensions: tuple) -> Optional[Path]:
        p = self.model_path
        if p.is_file():
            return p
        if p.is_dir():
            for name in ("best_model", "model"):
                for ext in extensions:
                    candidate = p / f"{name}{ext}"
                    if candidate.exists():
                        return candidate
        return None

    # -- prediction ---------------------------------------------------------

    def predict(
        self,
        pair_image: Optional[Union[Path, str, Any]] = None,
        features: Optional[Dict[str, Any]] = None,
    ) -> MergePrediction:
        """Predict whether a table pair should be merged.

        Args:
            pair_image: Path to side-by-side PNG or a PIL Image.
            features: Dict with 9 tabular features (col_count_match,
                      width_ratio, horizontal_iou, etc.)

        Returns:
            MergePrediction with should_merge, confidence, raw_score.
        """
        self._lazy_load()

        if self._model_type == "ensemble":
            return self._ensemble_predict(pair_image, features)
        if self._model_type == "vision" and pair_image is not None:
            return self._vision_predict(pair_image)
        if self._model_type == "tabular" and features is not None:
            return self._tabular_predict(features)
        if pair_image is not None and self._vision_model is not None:
            return self._vision_predict(pair_image)
        if features is not None and self._tabular_model is not None:
            return self._tabular_predict(features)
        return self._heuristic_predict(features)

    def _vision_predict(self, image) -> MergePrediction:
        import torch
        from PIL import Image as PILImage

        if isinstance(image, (str, Path)):
            image = PILImage.open(image).convert("RGB")

        img_t = self._transform(image).unsqueeze(0)
        with torch.no_grad():
            logits = self._vision_model(img_t)
            prob = torch.softmax(logits, dim=1)

        # Determine merge class index from config (default: class 1)
        label_to_idx = self._config.get("label_to_idx", {})
        merge_idx = label_to_idx.get("merge", 1) if isinstance(label_to_idx.get("merge"), int) else 1
        merge_prob = prob[0, merge_idx].item()
        return MergePrediction(
            should_merge=merge_prob > 0.5,
            confidence=max(merge_prob, 1 - merge_prob),
            raw_score=merge_prob,
            model_type="vision",
        )

    def _tabular_predict(self, features: Dict[str, Any]) -> MergePrediction:
        import numpy as np

        feature_order = self._config.get("feature_keys", [
            "col_count_match", "width_ratio", "horizontal_iou",
            "title_has_continued", "same_section",
            "s05b_title_similarity", "gap_between_tables_px",
            "row_count_ratio",
        ])
        vec = []
        for k in feature_order:
            v = features.get(k, 0)
            vec.append(float(v) if not isinstance(v, bool) else float(v))

        X = np.array([vec])
        proba = self._tabular_model.predict_proba(X)
        # Determine merge class index from model's classes_ attribute
        # sklearn sorts classes alphabetically: ["merge", "separate"] → 0=merge, 1=separate
        merge_idx = 0
        if hasattr(self._tabular_model, "classes_"):
            classes = list(self._tabular_model.classes_)
            if "merge" in classes:
                merge_idx = classes.index("merge")
        merge_prob = float(proba[0, merge_idx])
        return MergePrediction(
            should_merge=merge_prob > 0.5,
            confidence=max(merge_prob, 1 - merge_prob),
            raw_score=merge_prob,
            model_type="tabular",
        )

    def _ensemble_predict(
        self,
        image=None,
        features: Optional[Dict] = None,
    ) -> MergePrediction:
        """Weighted average of vision + tabular predictions."""
        vision_weight = self._config.get("models", {}).get("vision", {}).get("weight", 0.6)
        tabular_weight = self._config.get("models", {}).get("tabular", {}).get("weight", 0.4)

        scores = []
        weights = []

        if self._vision_model is not None and image is not None:
            vp = self._vision_predict(image)
            scores.append(vp.raw_score)
            weights.append(vision_weight)

        if self._tabular_model is not None and features is not None:
            tp = self._tabular_predict(features)
            scores.append(tp.raw_score)
            weights.append(tabular_weight)

        if not scores:
            return self._heuristic_predict(features)

        total_w = sum(weights)
        merge_prob = sum(s * w for s, w in zip(scores, weights)) / total_w

        return MergePrediction(
            should_merge=merge_prob > 0.5,
            confidence=max(merge_prob, 1 - merge_prob),
            raw_score=merge_prob,
            model_type="ensemble",
        )

    @staticmethod
    def _heuristic_predict(features: Optional[Dict] = None) -> MergePrediction:
        """Fallback: simple rule-based heuristic."""
        if features is None:
            return MergePrediction(should_merge=False, confidence=0.5, raw_score=0.0, model_type="heuristic")

        score = 0.0
        if features.get("col_count_match"):
            score += 0.3
        if features.get("horizontal_iou", 0) > 0.5:
            score += 0.25
        if features.get("width_ratio", 0) > 0.85:
            score += 0.15
        if features.get("title_has_continued"):
            score += 0.25
        if features.get("s05b_title_similarity", 0) > 0.5:
            score += 0.05

        return MergePrediction(
            should_merge=score > 0.5,
            confidence=max(score, 1 - score),
            raw_score=score,
            model_type="heuristic",
        )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_predictor: Optional[TableMergePredictor] = None


def get_merge_predictor(model_path: Optional[Path] = None) -> TableMergePredictor:
    """Get or create global merge predictor (lazy singleton)."""
    global _predictor
    if _predictor is None:
        _predictor = TableMergePredictor(model_path or DEFAULT_MERGE_MODEL_PATH)
    return _predictor


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli():
    import typer

    cli_app = typer.Typer(help="Merge classifier inference")

    @cli_app.command()
    def predict(
        image: Path = typer.Argument(..., help="Path to pair image (side-by-side PNG)"),
        model_path: Optional[Path] = typer.Option(None, "--model", help="Model directory"),
        json_output: bool = typer.Option(False, "--json", help="JSON output"),
    ):
        """Predict merge/separate for a pair image."""
        predictor = TableMergePredictor(model_path)
        result = predictor.predict(pair_image=image)
        if json_output:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            verdict = "MERGE" if result.should_merge else "SEPARATE"
            print(f"{verdict}  confidence={result.confidence:.3f}  score={result.raw_score:.3f}  model={result.model_type}")

    cli_app()


if __name__ == "__main__":
    _cli()
