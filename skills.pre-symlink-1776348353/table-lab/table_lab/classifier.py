"""ML Classifier integration for strategy prediction.

Uses the 95%+ accuracy ensemble from create-table-classifier skill
to provide informed baseline parameters before systematic sweep.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from loguru import logger

from .config import (
    CLASSIFIER_CONFIDENCE_THRESHOLD,
    CLASSIFIER_MODEL_PATH,
    LATTICE_LINE_SCALES,
    STREAM_EDGE_TOLS,
    USE_CLASSIFIER_BASELINE,
)


@dataclass
class ClassifierRecommendation:
    """Recommendation from the ML classifier."""
    strategy: str  # "lattice", "stream", "lattice_sensitive"
    line_scale: int
    edge_tol: int
    confidence: float
    available: bool = True

    def get_focused_lattice_scales(self) -> list[int]:
        """Get a focused lattice grid centered on predicted value."""
        if self.strategy in ("lattice", "lattice_sensitive"):
            # Use prediction +/- 5 as starting point
            center = self.line_scale
            focused = [max(5, center - 5), center, min(60, center + 5)]
            # Add defaults if not covered
            return sorted(set(focused + [15, 20]))
        return LATTICE_LINE_SCALES

    def get_focused_stream_tols(self) -> list[int]:
        """Get a focused stream grid centered on predicted value."""
        if self.strategy == "stream":
            center = self.edge_tol
            focused = [max(25, center - 50), center, min(200, center + 50)]
            return sorted(set(focused + [100]))
        return STREAM_EDGE_TOLS

    def should_try_lattice_first(self) -> bool:
        """Whether to try lattice strategies first based on prediction."""
        return self.strategy in ("lattice", "lattice_sensitive")


# Global predictor instance (lazy loaded)
_predictor = None


def _get_predictor():
    """Lazy load the table strategy predictor."""
    global _predictor
    if _predictor is not None:
        return _predictor

    if not USE_CLASSIFIER_BASELINE:
        return None

    if not CLASSIFIER_MODEL_PATH.exists():
        logger.debug(f"Classifier model not found at {CLASSIFIER_MODEL_PATH}")
        return None

    try:
        # Add the classifier scripts to path
        scripts_path = CLASSIFIER_MODEL_PATH.parent.parent / "scripts"
        if str(scripts_path) not in sys.path:
            sys.path.insert(0, str(scripts_path))

        from inference import TableStrategyPredictor
        _predictor = TableStrategyPredictor(CLASSIFIER_MODEL_PATH)
        logger.info(f"Loaded table classifier from {CLASSIFIER_MODEL_PATH}")
        return _predictor

    except Exception as e:
        logger.debug(f"Failed to load classifier: {e}")
        return None


def get_classifier_recommendation(
    pdf_path: Path,
    page_num: int = 0,
    preset: str = "",
) -> ClassifierRecommendation:
    """Get ML classifier recommendation for a table region.

    Args:
        pdf_path: Path to PDF file
        page_num: Page number (0-indexed)
        preset: Document preset hint

    Returns:
        ClassifierRecommendation with suggested strategy and parameters
    """
    predictor = _get_predictor()

    if predictor is None:
        return ClassifierRecommendation(
            strategy="lattice",
            line_scale=20,
            edge_tol=100,
            confidence=0.0,
            available=False,
        )

    try:
        import fitz
        from PIL import Image
        import io

        # Extract page image (center region as representative)
        doc = fitz.open(pdf_path)
        if page_num >= len(doc):
            page_num = 0
        page = doc[page_num]

        # Get center 60% of page as sample
        rect = page.rect
        margin_x = rect.width * 0.2
        margin_y = rect.height * 0.2
        clip = fitz.Rect(
            rect.x0 + margin_x,
            rect.y0 + margin_y,
            rect.x1 - margin_x,
            rect.y1 - margin_y,
        )

        mat = fitz.Matrix(2, 2)  # 2x zoom
        pix = page.get_pixmap(matrix=mat, clip=clip)
        img_data = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_data)).convert("RGB")
        doc.close()

        # Get prediction
        pred = predictor.predict(img, preset=preset or None)

        return ClassifierRecommendation(
            strategy=pred.strategy,
            line_scale=pred.line_scale,
            edge_tol=pred.edge_tol,
            confidence=pred.confidence,
            available=True,
        )

    except Exception as e:
        logger.debug(f"Classifier prediction failed: {e}")
        return ClassifierRecommendation(
            strategy="lattice",
            line_scale=20,
            edge_tol=100,
            confidence=0.0,
            available=False,
        )


def get_classifier_grid_recommendation(
    pdf_path: Path,
    page_num: int = 0,
    preset: str = "",
) -> tuple[list[int], list[int], str]:
    """Get recommended parameter grids from classifier.

    Returns:
        Tuple of (lattice_scales, stream_tols, strategy_order)
        strategy_order is "lattice_first" or "stream_first"
    """
    rec = get_classifier_recommendation(pdf_path, page_num, preset)

    if not rec.available or rec.confidence < CLASSIFIER_CONFIDENCE_THRESHOLD:
        # Fall back to defaults
        return LATTICE_LINE_SCALES, STREAM_EDGE_TOLS, "lattice_first"

    lattice_scales = rec.get_focused_lattice_scales()
    stream_tols = rec.get_focused_stream_tols()
    strategy_order = "lattice_first" if rec.should_try_lattice_first() else "stream_first"

    logger.info(
        f"Classifier recommends: {rec.strategy} "
        f"(conf={rec.confidence:.2f}, ls={rec.line_scale}, et={rec.edge_tol})"
    )

    return lattice_scales, stream_tols, strategy_order
