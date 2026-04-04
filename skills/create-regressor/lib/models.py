"""Regression model wrappers with unified train/predict interface."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Any, Optional

import numpy as np
from loguru import logger
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import ElasticNet, Lasso, LinearRegression, Ridge
from sklearn.model_selection import cross_val_score


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class TrainResult:
    """Output from model training."""

    model_name: str
    model_type: str
    selected_by: str  # "explicit" or "auto_cv"
    mae: float
    rmse: float
    r2: float
    mape: float
    training_samples: int
    feature_count: int
    version: str
    cv_results: dict[str, dict[str, float]] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


@dataclass
class PredictResult:
    """Output from model prediction."""

    prediction: float
    confidence_interval: list[float]  # [lower, upper]
    features_used: list[str]
    model_name: str
    model_type: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------

MODEL_REGISTRY: dict[str, type] = {
    "linear": LinearRegression,
    "ridge": Ridge,
    "lasso": Lasso,
    "elasticnet": ElasticNet,
    "gbr": GradientBoostingRegressor,
    "rf": RandomForestRegressor,
}

# Default hyperparameters per model type
MODEL_DEFAULTS: dict[str, dict[str, Any]] = {
    "linear": {},
    "ridge": {"alpha": 1.0},
    "lasso": {"alpha": 1.0, "max_iter": 5000},
    "elasticnet": {"alpha": 1.0, "l1_ratio": 0.5, "max_iter": 5000},
    "gbr": {
        "n_estimators": 200,
        "max_depth": 5,
        "learning_rate": 0.1,
        "subsample": 0.8,
        "random_state": 42,
    },
    "rf": {
        "n_estimators": 200,
        "max_depth": None,
        "min_samples_leaf": 2,
        "random_state": 42,
    },
}

# Try importing XGBoost
try:
    from xgboost import XGBRegressor

    MODEL_REGISTRY["xgb"] = XGBRegressor
    MODEL_DEFAULTS["xgb"] = {
        "n_estimators": 200,
        "max_depth": 5,
        "learning_rate": 0.1,
        "subsample": 0.8,
        "random_state": 42,
    }
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False


# ---------------------------------------------------------------------------
# Regressor wrapper
# ---------------------------------------------------------------------------

class Regressor:
    """Unified wrapper around sklearn regression models.

    Handles training, prediction with confidence intervals,
    feature importance, and cross-validation model selection.
    """

    def __init__(self, model_type: str = "gbr", **kwargs: Any) -> None:
        if model_type not in MODEL_REGISTRY:
            raise ValueError(
                f"Unknown model type: {model_type}. "
                f"Available: {list(MODEL_REGISTRY.keys())}"
            )
        self.model_type = model_type
        params = {**MODEL_DEFAULTS.get(model_type, {}), **kwargs}
        self.model = MODEL_REGISTRY[model_type](**params)
        self.vectorizer: Optional[DictVectorizer] = None
        self.residuals: Optional[np.ndarray] = None
        self.training_samples: int = 0
        self.mae: float = 0.0
        self.rmse: float = 0.0
        self.r2: float = 0.0
        self.mape: float = 0.0
        self.feature_names: list[str] = []
        self.version: str = ""

    def train(
        self,
        feature_dicts: list[dict],
        targets: list[float],
    ) -> dict[str, float]:
        """Train on feature dicts + target values. Returns metrics dict."""
        self.vectorizer = DictVectorizer(sparse=False)
        X = self.vectorizer.fit_transform(feature_dicts)
        y = np.array(targets, dtype=np.float64)

        self.model.fit(X, y)

        # Compute metrics
        y_pred = self.model.predict(X)
        errors = np.abs(y - y_pred)
        self.residuals = np.sort(errors)
        self.training_samples = len(y)
        self.mae = float(np.mean(errors))
        self.rmse = float(np.sqrt(np.mean((y - y_pred) ** 2)))

        # Avoid division by zero for MAPE
        nonzero_mask = np.abs(y) > 1e-8
        if nonzero_mask.any():
            self.mape = float(np.mean(np.abs(errors[nonzero_mask] / y[nonzero_mask])))
        else:
            self.mape = 0.0

        self.r2 = float(self.model.score(X, y))
        self.feature_names = list(self.vectorizer.feature_names_)
        self.version = f"{date.today().isoformat()}_v1"

        logger.info(
            f"{self.model_type} trained: {self.training_samples} samples, "
            f"MAE={self.mae:.3f}, R2={self.r2:.4f}"
        )

        return {
            "mae": self.mae,
            "rmse": self.rmse,
            "r2": self.r2,
            "mape": self.mape,
        }

    def predict(self, feature_dict: dict) -> tuple[float, list[float]]:
        """Return (point_estimate, [lower, upper]) for a single sample."""
        if self.vectorizer is None:
            raise RuntimeError("Model not trained or loaded")

        X = self.vectorizer.transform([feature_dict])
        point = float(self.model.predict(X)[0])

        # Residual-based confidence interval (p10/p90)
        if self.residuals is not None and len(self.residuals) > 0:
            p90_residual = float(np.percentile(self.residuals, 90))
        else:
            p90_residual = abs(point) * 0.3

        interval = [point - p90_residual, point + p90_residual]
        return point, interval

    def predict_batch(self, feature_dicts: list[dict]) -> list[tuple[float, list[float]]]:
        """Predict for multiple samples."""
        return [self.predict(fd) for fd in feature_dicts]

    def feature_importance(self) -> dict[str, float]:
        """Return feature name -> importance, sorted descending."""
        if not self.feature_names:
            return {}

        if hasattr(self.model, "feature_importances_"):
            imp = dict(zip(self.feature_names, self.model.feature_importances_))
        elif hasattr(self.model, "coef_"):
            coef = np.atleast_1d(self.model.coef_)
            imp = dict(zip(self.feature_names, np.abs(coef)))
        else:
            return {}

        return dict(sorted(imp.items(), key=lambda x: x[1], reverse=True))

    def evaluate(
        self,
        feature_dicts: list[dict],
        targets: list[float],
    ) -> dict[str, float]:
        """Evaluate on held-out data. Returns metrics dict."""
        if self.vectorizer is None:
            raise RuntimeError("Model not trained or loaded")

        X = self.vectorizer.transform(feature_dicts)
        y = np.array(targets, dtype=np.float64)
        y_pred = self.model.predict(X)

        errors = np.abs(y - y_pred)
        mae = float(np.mean(errors))
        rmse = float(np.sqrt(np.mean((y - y_pred) ** 2)))
        r2 = float(self.model.score(X, y))

        nonzero_mask = np.abs(y) > 1e-8
        mape = float(np.mean(np.abs(errors[nonzero_mask] / y[nonzero_mask]))) if nonzero_mask.any() else 0.0

        return {"mae": mae, "rmse": rmse, "r2": r2, "mape": mape, "samples": len(y)}


# ---------------------------------------------------------------------------
# Auto model selection
# ---------------------------------------------------------------------------

AUTO_CANDIDATES = ["linear", "ridge", "gbr", "rf"]
if HAS_XGBOOST:
    AUTO_CANDIDATES.append("xgb")


def auto_select(
    feature_dicts: list[dict],
    targets: list[float],
    *,
    cv_folds: int = 5,
    candidates: Optional[list[str]] = None,
) -> tuple[str, dict[str, dict[str, float]]]:
    """Cross-validate candidates, return (best_model_key, cv_results).

    Selection metric: negative MAE (higher = better).
    """
    cands = candidates or AUTO_CANDIDATES
    vectorizer = DictVectorizer(sparse=False)
    X = vectorizer.fit_transform(feature_dicts)
    y = np.array(targets, dtype=np.float64)

    cv_results: dict[str, dict[str, float]] = {}
    best_key = cands[0]
    best_mae = float("inf")

    for key in cands:
        if key not in MODEL_REGISTRY:
            continue
        params = MODEL_DEFAULTS.get(key, {})
        model = MODEL_REGISTRY[key](**params)

        try:
            neg_mae_scores = cross_val_score(
                model, X, y, cv=min(cv_folds, len(y)), scoring="neg_mean_absolute_error"
            )
            mae = float(-neg_mae_scores.mean())
            r2_scores = cross_val_score(
                model, X, y, cv=min(cv_folds, len(y)), scoring="r2"
            )
            r2 = float(r2_scores.mean())

            cv_results[key] = {"mae": round(mae, 4), "r2": round(r2, 4)}
            logger.info(f"  {key}: CV MAE={mae:.4f}, R2={r2:.4f}")

            if mae < best_mae:
                best_mae = mae
                best_key = key
        except Exception as exc:
            logger.warning(f"  {key}: CV failed — {exc}")
            cv_results[key] = {"mae": float("inf"), "r2": 0.0, "error": str(exc)}

    logger.info(f"Auto-selected: {best_key} (CV MAE={best_mae:.4f})")
    return best_key, cv_results
