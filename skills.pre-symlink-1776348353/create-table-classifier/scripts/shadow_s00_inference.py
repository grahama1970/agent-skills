#!/usr/bin/env python3
"""Shadow S00 inference API for pipeline integration.

Shadow-LEGO pattern: This is a SEED PRODUCER.
It returns predictions with confidence scores that S05 uses
to prioritize strategies. It NEVER gates or blocks extraction.

Usage from S05:
    from shadow_s00_inference import ShadowS00Predictor

    predictor = ShadowS00Predictor()  # lazy loads model
    prediction = predictor.predict(profile_data)
    # prediction.needs_stream -> bool
    # prediction.stream_confidence -> float (0-1)
    # prediction.predicted_class -> str
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from loguru import logger

# Default model path (relative to this file)
_DEFAULT_MODEL_DIR = Path(__file__).parent.parent / "models" / "shadow-s00"

# Override with env var
SHADOW_S00_MODEL_DIR = os.environ.get("SHADOW_S00_MODEL_DIR", "")


@dataclass
class ShadowPrediction:
    """Prediction from Shadow S00 classifier.

    This is a SEED, not a gate. S05 uses these signals to prioritize
    strategy ordering but never skips strategies based on them.
    """
    predicted_class: str      # 'needs_stream', 'lattice_sufficient', 'no_tables'
    needs_stream: bool        # True if predicted_class == 'needs_stream'
    stream_confidence: float  # Probability of needs_stream class (0-1)
    class_probabilities: dict # {class_name: probability}


class ShadowS00Predictor:
    """Lazy-loaded Shadow S00 classifier.

    Thread-safe singleton pattern — loads model on first predict() call.
    """

    _instance: Optional["ShadowS00Predictor"] = None

    def __init__(self, model_dir: Optional[Path] = None):
        self._model_dir = Path(model_dir or SHADOW_S00_MODEL_DIR or _DEFAULT_MODEL_DIR)
        self._model = None
        self._metadata: dict = {}
        self._feature_names: list[str] = []
        self._class_names: list[str] = []

    @classmethod
    def get_instance(cls) -> "ShadowS00Predictor":
        """Get or create singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _lazy_load(self):
        """Load model and metadata on first use."""
        if self._model is not None:
            return

        import joblib
        import numpy as np

        model_path = self._model_dir / "shadow_s00_model.joblib"
        metadata_path = self._model_dir / "metadata.json"

        if not model_path.exists():
            logger.warning(f"Shadow S00 model not found at {model_path}")
            raise FileNotFoundError(f"Shadow S00 model not found: {model_path}")

        self._model = joblib.load(model_path)

        with open(metadata_path) as f:
            self._metadata = json.load(f)

        self._feature_names = self._metadata["feature_names"]
        self._class_names = self._metadata["class_names"]
        logger.info(
            f"Shadow S00 loaded: {len(self._feature_names)} features, "
            f"classes={self._class_names}"
        )

    def predict(self, profile: dict) -> ShadowPrediction:
        """Predict table extraction needs from S00 profile data.

        Args:
            profile: S00 profile dict (from 00_profile_detector/profile.json)

        Returns:
            ShadowPrediction with class, confidence, and probabilities.
        """
        self._lazy_load()
        import numpy as np

        features = self._extract_features(profile)
        X = np.array([features])

        proba = self._model.predict_proba(X)[0]
        pred_idx = int(np.argmax(proba))
        pred_class = self._class_names[pred_idx]

        # Find needs_stream probability
        stream_idx = self._class_names.index("needs_stream") if "needs_stream" in self._class_names else -1
        stream_conf = float(proba[stream_idx]) if stream_idx >= 0 else 0.0

        return ShadowPrediction(
            predicted_class=pred_class,
            needs_stream=(pred_class == "needs_stream"),
            stream_confidence=stream_conf,
            class_probabilities={
                c: float(p) for c, p in zip(self._class_names, proba)
            },
        )

    def _extract_features(self, profile: dict) -> list[float]:
        """Extract feature vector from S00 profile, matching training schema."""
        elements = profile.get("elements", {})
        layout = profile.get("layout", {})
        hierarchy = profile.get("hierarchy", {})
        preset = profile.get("preset_match", {})

        # Must match harvest_shadow_s00.py feature extraction exactly
        feature_dict = {
            "page_count": profile.get("page_count", 0),
            "file_size_mb": profile.get("file_size_mb", 0.0),
            "complexity_score": profile.get("complexity_score", 0.0),
            "columns": layout.get("columns", 1),
            "has_structure": 1.0 if hierarchy.get("has_structure") else 0.0,
            "estimated_sections": hierarchy.get("estimated_sections", 0),
            "estimated_sections_regex": hierarchy.get("estimated_sections_regex", 0),
            "estimated_sections_font": hierarchy.get("estimated_sections_font", 0),
            "font_body_size": hierarchy.get("font_body_size", 0.0),
            "s00_tables_predicted": 1.0 if elements.get("tables") else 0.0,
            "s00_table_pages": elements.get("table_pages", 0),
            "s00_figures_predicted": 1.0 if elements.get("figures") else 0.0,
            "s00_image_pages": elements.get("image_pages", 0),
            "s00_formulas_predicted": 1.0 if elements.get("formulas") else 0.0,
            "s00_requirements_predicted": 1.0 if elements.get("requirements") else 0.0,
            "estimated_table_count": elements.get("estimated_table_count", 0),
            "is_accurate_route": 1.0 if profile.get("route") == "accurate" else 0.0,
            "preset_matched": 1.0 if preset.get("matched") else 0.0,
        }

        # Domain encoding
        domain_map = {
            "engineering": 1, "scientific": 2, "defense": 3,
            "legal": 4, "medical": 5, "financial": 6,
            "general": 7, "academic": 8,
        }
        feature_dict["domain_code"] = domain_map.get(profile.get("domain", ""), 0)

        # Section style encoding
        style_map = {"decimal": 1, "labeled": 2, "roman": 3, "alpha": 4, "none": 0}
        feature_dict["section_style_code"] = style_map.get(
            hierarchy.get("section_style", "none"), 0
        )

        # Section breakdown ratios
        breakdown = hierarchy.get("section_breakdown", {})
        total_sections = sum(breakdown.values()) or 1
        feature_dict["decimal_section_ratio"] = breakdown.get("decimal", 0) / total_sections
        feature_dict["labeled_section_ratio"] = breakdown.get("labeled", 0) / total_sections

        # Return in sorted order matching training
        return [float(feature_dict.get(k, 0)) for k in self._feature_names]
