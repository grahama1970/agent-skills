"""Timeout prediction models and result types."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date
from pathlib import Path
from typing import Optional

import numpy as np
from loguru import logger
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression

from lib.features import TaskFeatures, features_to_dict


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class PredictionResult:
    """Output contract for timeout predictions."""

    estimated_seconds: float
    confidence_interval: list[float]  # [p10, p90]
    risk_probability: float
    risk_label: str  # low / medium / high
    recommended_timeout_seconds: float
    features_used: list[str]
    model_version: str
    duration_model_available: bool
    risk_model_available: bool

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


def _risk_label(p: float) -> str:
    if p < 0.15:
        return "low"
    if p < 0.50:
        return "medium"
    return "high"


# ---------------------------------------------------------------------------
# Duration model
# ---------------------------------------------------------------------------

class DurationModel:
    """GradientBoosting regressor for predicting task duration in seconds.

    Uses residual-based confidence calibration for prediction intervals.
    No artificial cap on predictions — the model predicts honestly.
    """

    def __init__(self) -> None:
        self.model: Optional[GradientBoostingRegressor] = None
        self.vectorizer: Optional[DictVectorizer] = None
        self.residuals: Optional[np.ndarray] = None  # sorted absolute residuals
        self.training_samples: int = 0
        self.mae: float = 0.0
        self.r2: float = 0.0
        self.feature_names: list[str] = []
        self.version: str = ""

    def train(
        self,
        feature_dicts: list[dict],
        durations: list[float],
        *,
        n_estimators: int = 200,
        max_depth: int = 5,
        learning_rate: float = 0.1,
    ) -> dict:
        """Train on feature dicts + actual durations. Returns metrics."""
        self.vectorizer = DictVectorizer(sparse=False)
        X = self.vectorizer.fit_transform(feature_dicts)
        y = np.array(durations, dtype=np.float64)

        self.model = GradientBoostingRegressor(
            n_estimators=n_estimators,
            max_depth=max_depth,
            learning_rate=learning_rate,
            subsample=0.8,
            random_state=42,
        )
        self.model.fit(X, y)

        # Metrics
        y_pred = self.model.predict(X)
        errors = np.abs(y - y_pred)
        self.residuals = np.sort(errors)
        self.training_samples = len(y)
        self.mae = float(np.mean(errors))
        self.r2 = float(self.model.score(X, y))
        self.feature_names = list(self.vectorizer.feature_names_)
        self.version = f"{date.today().isoformat()}_v1"

        logger.info(
            f"Duration model trained: {self.training_samples} samples, "
            f"MAE={self.mae:.1f}s, R²={self.r2:.3f}"
        )

        return {
            "samples": self.training_samples,
            "mae": self.mae,
            "r2": self.r2,
            "feature_count": len(self.feature_names),
        }

    def predict(self, feat: TaskFeatures) -> tuple[float, list[float]]:
        """Return (point_estimate, [p10, p90]) for a single sample."""
        if self.model is None or self.vectorizer is None:
            raise RuntimeError("Duration model not trained or loaded")

        d = features_to_dict(feat)
        X = self.vectorizer.transform([d])
        point = float(self.model.predict(X)[0])
        point = max(0.0, point)  # duration is non-negative

        # Residual-based confidence interval
        if self.residuals is not None and len(self.residuals) > 0:
            p10_residual = float(np.percentile(self.residuals, 10))
            p90_residual = float(np.percentile(self.residuals, 90))
        else:
            p10_residual = point * 0.1
            p90_residual = point * 0.5

        interval = [
            max(0.0, point - p90_residual),
            point + p90_residual,
        ]

        return point, interval

    def feature_importance(self) -> dict[str, float]:
        """Return feature name → importance mapping, sorted descending."""
        if self.model is None:
            return {}
        imp = dict(zip(self.feature_names, self.model.feature_importances_))
        return dict(sorted(imp.items(), key=lambda x: x[1], reverse=True))


# ---------------------------------------------------------------------------
# Risk model
# ---------------------------------------------------------------------------

class RiskModel:
    """Logistic regression for predicting timeout risk (binary: timed_out).

    Only trained when >=5 real timeout events exist in the data.
    """

    MIN_POSITIVE_SAMPLES = 5

    def __init__(self) -> None:
        self.model: Optional[LogisticRegression] = None
        self.vectorizer: Optional[DictVectorizer] = None
        self.training_samples: int = 0
        self.positive_samples: int = 0
        self.roc_auc: float = 0.0

    @property
    def available(self) -> bool:
        return self.model is not None

    def train(
        self,
        feature_dicts: list[dict],
        timed_out: list[bool],
    ) -> Optional[dict]:
        """Train on feature dicts + timeout labels. Returns metrics or None."""
        positives = sum(timed_out)
        if positives < self.MIN_POSITIVE_SAMPLES:
            logger.warning(
                f"Only {positives} timeout events (need >={self.MIN_POSITIVE_SAMPLES}). "
                f"Risk model will not be trained."
            )
            return None

        self.vectorizer = DictVectorizer(sparse=False)
        X = self.vectorizer.fit_transform(feature_dicts)
        y = np.array(timed_out, dtype=np.int32)

        self.model = LogisticRegression(
            class_weight="balanced",
            max_iter=1000,
            random_state=42,
        )
        self.model.fit(X, y)

        self.training_samples = len(y)
        self.positive_samples = positives

        # ROC AUC on training data (indicative only)
        from sklearn.metrics import roc_auc_score
        try:
            y_prob = self.model.predict_proba(X)[:, 1]
            self.roc_auc = float(roc_auc_score(y, y_prob))
        except ValueError:
            self.roc_auc = 0.0

        logger.info(
            f"Risk model trained: {self.training_samples} samples, "
            f"{self.positive_samples} positives, ROC-AUC={self.roc_auc:.3f}"
        )

        return {
            "samples": self.training_samples,
            "positives": self.positive_samples,
            "roc_auc": self.roc_auc,
        }

    def predict_proba(self, feat: TaskFeatures) -> float:
        """Return probability of timeout for a single sample."""
        if self.model is None or self.vectorizer is None:
            return 0.0

        d = features_to_dict(feat)
        X = self.vectorizer.transform([d])
        return float(self.model.predict_proba(X)[0, 1])


# ---------------------------------------------------------------------------
# Combined prediction
# ---------------------------------------------------------------------------

MAX_RECOMMENDED_TIMEOUT = 86400  # 24 hours — configurable upper bound

RISK_SAFETY_MULTIPLIERS = {
    "low": 1.0,
    "medium": 1.2,
    "high": 1.5,
}


def predict_timeout(
    feat: TaskFeatures,
    duration_model: DurationModel,
    risk_model: Optional[RiskModel] = None,
) -> PredictionResult:
    """Combined prediction using both models."""
    point, interval = duration_model.predict(feat)

    risk_prob = 0.0
    risk_available = False
    if risk_model and risk_model.available:
        risk_prob = risk_model.predict_proba(feat)
        risk_available = True

    label = _risk_label(risk_prob)
    safety = RISK_SAFETY_MULTIPLIERS[label]

    # Recommended = upper confidence bound * safety multiplier
    recommended = min(interval[1] * safety, MAX_RECOMMENDED_TIMEOUT)

    # Determine which features were actually used (non-zero in the dict)
    d = features_to_dict(feat)
    used = [k for k, v in d.items() if v and not k.startswith("task_type=")]

    return PredictionResult(
        estimated_seconds=round(point, 1),
        confidence_interval=[round(interval[0], 1), round(interval[1], 1)],
        risk_probability=round(risk_prob, 4),
        risk_label=label,
        recommended_timeout_seconds=round(recommended, 1),
        features_used=used,
        model_version=duration_model.version,
        duration_model_available=True,
        risk_model_available=risk_available,
    )
