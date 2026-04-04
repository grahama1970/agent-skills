"""Model persistence and /memory integration for create-regressor.

Purpose:
- Save/load trained regression models to disk (joblib).
- Store model summaries in /memory for cross-skill recall.

Inputs:
- Trained Regressor instance.
- Model name (user-chosen identifier).

Outputs:
- Saved model files at models/<name>/.
- Optional /memory learn entry.

Failure modes:
- Disk full: joblib.dump fails, logged and re-raised.
- /memory offline: logged as warning, non-fatal.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import joblib
from loguru import logger


MODELS_DIR = Path(__file__).resolve().parent.parent / "models"


def save_model(
    regressor: "Regressor",
    name: str,
    *,
    config: Optional[dict] = None,
    models_dir: Optional[Path] = None,
) -> Path:
    """Persist a trained regressor and metadata to disk."""
    from lib.models import Regressor  # noqa: F811 — deferred to avoid circular

    out = (models_dir or MODELS_DIR) / name
    out.mkdir(parents=True, exist_ok=True)

    # Model + vectorizer bundle
    joblib.dump(
        {
            "model": regressor.model,
            "vectorizer": regressor.vectorizer,
            "residuals": regressor.residuals,
            "training_samples": regressor.training_samples,
            "mae": regressor.mae,
            "rmse": regressor.rmse,
            "r2": regressor.r2,
            "mape": regressor.mape,
            "feature_names": regressor.feature_names,
            "version": regressor.version,
            "model_type": regressor.model_type,
        },
        out / "model.joblib",
    )

    # Training summary
    summary = {
        "trained_at": datetime.utcnow().isoformat() + "Z",
        "model_name": name,
        "model_type": regressor.model_type,
        "samples": regressor.training_samples,
        "mae": regressor.mae,
        "rmse": regressor.rmse,
        "r2": regressor.r2,
        "mape": regressor.mape,
        "features": len(regressor.feature_names),
        "version": regressor.version,
    }
    (out / "training_summary.json").write_text(json.dumps(summary, indent=2))

    # Feature importance — convert numpy types for JSON serialization
    imp = regressor.feature_importance()
    imp = {k: float(v) for k, v in imp.items()}
    (out / "feature_importance.json").write_text(json.dumps(imp, indent=2))

    # Training config (for reproducibility)
    if config:
        (out / "config.json").write_text(json.dumps(config, indent=2))

    logger.info(f"Model '{name}' saved to {out}")
    return out


def load_model(
    name: str,
    *,
    models_dir: Optional[Path] = None,
) -> "Regressor":
    """Load a trained regressor from disk."""
    from lib.models import Regressor

    src = (models_dir or MODELS_DIR) / name / "model.joblib"
    if not src.exists():
        raise FileNotFoundError(f"Model not found: {src}")

    data = joblib.load(src)

    reg = Regressor.__new__(Regressor)
    reg.model = data["model"]
    reg.vectorizer = data["vectorizer"]
    reg.residuals = data.get("residuals")
    reg.training_samples = data.get("training_samples", 0)
    reg.mae = data.get("mae", 0.0)
    reg.rmse = data.get("rmse", 0.0)
    reg.r2 = data.get("r2", 0.0)
    reg.mape = data.get("mape", 0.0)
    reg.feature_names = data.get("feature_names", [])
    reg.version = data.get("version", "unknown")
    reg.model_type = data.get("model_type", "unknown")
    return reg


def list_models(models_dir: Optional[Path] = None) -> list[dict]:
    """List all trained models with their summaries."""
    root = models_dir or MODELS_DIR
    if not root.exists():
        return []

    results = []
    for d in sorted(root.iterdir()):
        summary_path = d / "training_summary.json"
        if summary_path.exists():
            summary = json.loads(summary_path.read_text())
            results.append(summary)
    return results


def store_to_memory(
    name: str,
    regressor: "Regressor",
) -> bool:
    """Store model summary in /memory for cross-skill persistence."""
    try:
        import httpx

        payload = {
            "problem": f"Regression model: {name}",
            "solution": (
                f"Model type={regressor.model_type}, MAE={regressor.mae:.3f}, "
                f"R2={regressor.r2:.4f}, RMSE={regressor.rmse:.3f}, "
                f"{regressor.training_samples} samples, "
                f"{len(regressor.feature_names)} features, "
                f"version={regressor.version}."
            ),
            "tags": [
                "Precision",
                "create-regressor",
                name,
                "learned-model",
                regressor.model_type,
            ],
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
