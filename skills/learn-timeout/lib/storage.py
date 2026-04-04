"""Model persistence and /memory integration."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
from loguru import logger

from lib.models import DurationModel, RiskModel


MODELS_DIR = Path(__file__).resolve().parent.parent / "models" / "timeout"


def save_models(
    duration: DurationModel,
    risk: Optional[RiskModel] = None,
    *,
    models_dir: Optional[Path] = None,
) -> Path:
    """Persist trained models and metadata to disk."""
    out = models_dir or MODELS_DIR
    out.mkdir(parents=True, exist_ok=True)

    # Duration model
    joblib.dump(
        {
            "model": duration.model,
            "vectorizer": duration.vectorizer,
            "residuals": duration.residuals,
            "training_samples": duration.training_samples,
            "mae": duration.mae,
            "r2": duration.r2,
            "feature_names": duration.feature_names,
            "version": duration.version,
        },
        out / "duration_model.joblib",
    )

    # Risk model (optional)
    if risk and risk.available:
        joblib.dump(
            {
                "model": risk.model,
                "vectorizer": risk.vectorizer,
                "training_samples": risk.training_samples,
                "positive_samples": risk.positive_samples,
                "roc_auc": risk.roc_auc,
            },
            out / "risk_model.joblib",
        )

    # Training summary
    summary = {
        "trained_at": datetime.utcnow().isoformat() + "Z",
        "duration_model": {
            "samples": duration.training_samples,
            "mae": duration.mae,
            "r2": duration.r2,
            "features": len(duration.feature_names),
            "version": duration.version,
        },
        "risk_model": None,
    }
    if risk and risk.available:
        summary["risk_model"] = {
            "samples": risk.training_samples,
            "positives": risk.positive_samples,
            "roc_auc": risk.roc_auc,
        }
    (out / "training_summary.json").write_text(json.dumps(summary, indent=2))

    # Feature importance
    imp = duration.feature_importance()
    (out / "feature_importance.json").write_text(json.dumps(imp, indent=2))

    logger.info(f"Models saved to {out}")
    return out


def load_models(
    models_dir: Optional[Path] = None,
) -> tuple[Optional[DurationModel], Optional[RiskModel]]:
    """Load trained models from disk."""
    src = models_dir or MODELS_DIR

    dur = _load_duration(src / "duration_model.joblib")
    risk = _load_risk(src / "risk_model.joblib")

    return dur, risk


def _load_duration(path: Path) -> Optional[DurationModel]:
    if not path.exists():
        return None

    try:
        data = joblib.load(path)
    except Exception as exc:
        logger.error(f"Failed to load duration model: {exc}")
        return None

    dm = DurationModel()
    dm.model = data["model"]
    dm.vectorizer = data["vectorizer"]
    dm.residuals = data.get("residuals")
    dm.training_samples = data.get("training_samples", 0)
    dm.mae = data.get("mae", 0.0)
    dm.r2 = data.get("r2", 0.0)
    dm.feature_names = data.get("feature_names", [])
    dm.version = data.get("version", "unknown")
    return dm


def _load_risk(path: Path) -> Optional[RiskModel]:
    if not path.exists():
        return None

    try:
        data = joblib.load(path)
    except Exception as exc:
        logger.error(f"Failed to load risk model: {exc}")
        return None

    rm = RiskModel()
    rm.model = data["model"]
    rm.vectorizer = data["vectorizer"]
    rm.training_samples = data.get("training_samples", 0)
    rm.positive_samples = data.get("positive_samples", 0)
    rm.roc_auc = data.get("roc_auc", 0.0)
    return rm


def store_to_memory(duration: DurationModel, risk: Optional[RiskModel] = None) -> bool:
    """Store model summary in /memory for cross-skill persistence."""
    try:
        import httpx

        solution_parts = [
            f"Learned timeout model (GradientBoosting): "
            f"MAE={duration.mae:.1f}s, R²={duration.r2:.3f}, "
            f"{duration.training_samples} samples, version={duration.version}.",
        ]
        if risk and risk.available:
            solution_parts.append(
                f"Risk model (LogisticRegression): "
                f"{risk.positive_samples} timeout events, ROC-AUC={risk.roc_auc:.3f}."
            )

        payload = {
            "problem": "General-purpose timeout estimation for all task types",
            "solution": " ".join(solution_parts),
            "tags": ["Precision", "timeout-prediction", "learn-timeout", "learned-model"],
        }

        resp = httpx.post(
            "http://127.0.0.1:8601/learn",
            json=payload,
            timeout=10.0,
        )
        return resp.status_code == 200

    except Exception as exc:
        logger.warning(f"Could not store to /memory: {exc}")
        return False
