"""Predict timeout from JSON features."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.features import TaskFeatures, dict_to_features
from lib.models import predict_timeout
from lib.storage import load_models

app = typer.Typer(add_completion=False)


@app.command()
def main(
    features_json: str = typer.Argument(..., help="JSON string or path to JSON file with task features"),
) -> None:
    """Load models and return a PredictionResult as JSON."""
    # Parse input
    raw: dict
    if features_json.startswith("{"):
        raw = json.loads(features_json)
    else:
        p = Path(features_json)
        if p.exists():
            raw = json.loads(p.read_text())
        else:
            logger.error(f"Not valid JSON and file not found: {features_json}")
            raise typer.Exit(1)

    feat = dict_to_features(raw)

    # Load models
    dur_model, risk_model = load_models()
    if dur_model is None:
        logger.error("No trained duration model found. Run './run.sh train' first.")
        # Fall back to heuristic
        _fallback_predict(feat)
        return

    result = predict_timeout(feat, dur_model, risk_model)
    print(result.to_json())


def _fallback_predict(feat: TaskFeatures) -> None:
    """Simple heuristic fallback when no model is available."""
    base = 120.0
    per_page = 2.0
    per_table = 30.0

    est = base + feat.page_count * per_page + feat.table_pages * per_table
    if feat.has_formulas:
        est *= 1.5
    if feat.has_requirements:
        est *= 1.3

    result = {
        "estimated_seconds": round(est, 1),
        "confidence_interval": [round(est * 0.5, 1), round(est * 2.0, 1)],
        "risk_probability": 0.0,
        "risk_label": "low",
        "recommended_timeout_seconds": round(est * 2.0, 1),
        "features_used": ["page_count", "table_pages"],
        "model_version": "heuristic_fallback",
        "duration_model_available": False,
        "risk_model_available": False,
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    app()
