#!/usr/bin/env python3
"""Cost surrogate model — predict energy cost before Docker evaluation.

Trains a simple linear regressor on past execution data to predict
composition energy cost from structural features. Used to pre-filter
expensive compositions before running them in Docker sandbox.

Reference: Multi-objective optimization with surrogate models
           https://arxiv.org/abs/2210.10838

Usage:
    from cost_surrogate import CostSurrogate
    surrogate = CostSurrogate.load_or_create()
    surrogate.fit_from_traces()
    predicted_cost = surrogate.predict(chain)
    if predicted_cost > budget:
        skip(chain)
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).parent
STATE_DIR = SCRIPTS_DIR.parent / "state"
STATE_DIR.mkdir(exist_ok=True)

SURROGATE_FILE = STATE_DIR / "cost_surrogate.json"
TRACES_FILE = STATE_DIR / "execution_traces.jsonl"

# Feature encoding for skill categories
SKILL_CATEGORIES: dict[str, str] = {
    # Lightweight
    "memory": "lightweight", "taxonomy": "lightweight", "normalize": "lightweight",
    "edge-verifier": "lightweight", "embedding": "lightweight", "task-monitor": "lightweight",
    # Medium
    "brave-search": "medium", "arxiv": "medium",
    "fetcher": "medium", "review-pdf": "medium", "plan": "medium",
    # Heavy
    "doc2qra": "heavy", "extractor": "heavy", "dogpile": "heavy", "scillm": "heavy",
    "create-classifier": "heavy", "security-scan": "heavy",
    # Very heavy
    "create-movie": "very_heavy", "create-music": "very_heavy",
    "train-voice": "very_heavy", "tts-train": "very_heavy",
}

CATEGORY_WEIGHTS = {
    "lightweight": 0.1,
    "medium": 0.4,
    "heavy": 0.7,
    "very_heavy": 1.0,
    "unknown": 0.5,
}


class CostSurrogate:
    """Linear cost prediction model for skill compositions.

    Features:
    - chain_length: number of skills
    - category_sum: sum of category weights
    - category_max: max category weight (bottleneck skill)
    - has_heavy: 1 if any heavy/very_heavy skill
    - unique_ratio: unique skills / chain length

    Uses simple linear regression (no sklearn dependency).
    """

    def __init__(self) -> None:
        self.weights: list[float] = [0.0] * 6  # 5 features + bias
        self.n_samples: int = 0
        self.fitted: bool = False
        self.fit_error: float = float("inf")

    def _featurize(self, chain: list[str]) -> list[float]:
        """Extract features from a skill chain."""
        n = len(chain)
        cats = [SKILL_CATEGORIES.get(s, "unknown") for s in chain]
        cat_weights = [CATEGORY_WEIGHTS[c] for c in cats]
        return [
            n,                                    # chain_length
            sum(cat_weights),                     # category_sum
            max(cat_weights) if cat_weights else 0,  # category_max
            1.0 if any(c in ("heavy", "very_heavy") for c in cats) else 0.0,  # has_heavy
            len(set(chain)) / max(1, n),         # unique_ratio
        ]

    def predict(self, chain: list[str]) -> float:
        """Predict energy cost for a composition.

        Returns predicted ATP cost. Falls back to simple heuristic
        if model is not fitted.
        """
        if not self.fitted:
            return self._heuristic_predict(chain)

        features = self._featurize(chain)
        # Linear: w0*x0 + w1*x1 + ... + bias
        prediction = self.weights[-1]  # bias
        for i, x in enumerate(features):
            prediction += self.weights[i] * x
        return max(0.0, prediction)

    def _heuristic_predict(self, chain: list[str]) -> float:
        """Fallback heuristic when model isn't fitted."""
        from energy_model import estimate_skill_energy
        return sum(estimate_skill_energy(s) for s in chain)

    def fit_from_traces(self, min_samples: int = 20) -> dict[str, Any]:
        """Train the surrogate from execution traces.

        Uses simple closed-form linear regression (normal equation).
        Returns fit statistics.
        """
        if not TRACES_FILE.exists():
            return {"status": "no_traces", "n_samples": 0}

        # Collect training data from traces
        X: list[list[float]] = []
        y: list[float] = []

        for line in TRACES_FILE.read_text().splitlines():
            if not line.strip():
                continue
            try:
                trace = json.loads(line)
                chain = trace.get("chain", [])
                duration_ms = trace.get("duration_ms", 0)
                if not chain or duration_ms <= 0:
                    continue
                # Use duration as proxy for energy cost
                # Normalize: 1 ATP ≈ 1000ms
                energy_proxy = duration_ms / 1000.0
                X.append(self._featurize(chain))
                y.append(energy_proxy)
            except (json.JSONDecodeError, KeyError):
                continue

        if len(X) < min_samples:
            return {"status": "insufficient_data", "n_samples": len(X)}

        # Normal equation: w = (X^T X)^-1 X^T y
        # Add bias column
        X_b = [row + [1.0] for row in X]
        n_features = len(X_b[0])

        # X^T X
        XtX = [[0.0] * n_features for _ in range(n_features)]
        for row in X_b:
            for i in range(n_features):
                for j in range(n_features):
                    XtX[i][j] += row[i] * row[j]

        # Regularization (ridge) for numerical stability
        for i in range(n_features):
            XtX[i][i] += 0.01

        # X^T y
        Xty = [0.0] * n_features
        for row, yi in zip(X_b, y):
            for i in range(n_features):
                Xty[i] += row[i] * yi

        # Solve via Gauss elimination
        weights = _solve_linear_system(XtX, Xty)
        if weights is None:
            return {"status": "singular_matrix", "n_samples": len(X)}

        self.weights = weights
        self.n_samples = len(X)
        self.fitted = True

        # Compute fit error (RMSE)
        errors_sq = []
        for row, yi in zip(X_b, y):
            pred = sum(w * x for w, x in zip(weights, row))
            errors_sq.append((pred - yi) ** 2)
        self.fit_error = (sum(errors_sq) / len(errors_sq)) ** 0.5

        return {
            "status": "fitted",
            "n_samples": len(X),
            "rmse": round(self.fit_error, 4),
            "weights": [round(w, 4) for w in weights],
        }

    def should_skip(self, chain: list[str], budget_atp: float = 12.0) -> bool:
        """Return True if predicted cost exceeds budget."""
        return self.predict(chain) > budget_atp

    def save(self, path: Path | None = None) -> None:
        """Persist surrogate to JSON."""
        path = path or SURROGATE_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "weights": self.weights,
            "n_samples": self.n_samples,
            "fitted": self.fitted,
            "fit_error": self.fit_error,
        }
        path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load_or_create(cls, path: Path | None = None) -> CostSurrogate:
        """Load existing surrogate or create a new one."""
        path = path or SURROGATE_FILE
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text())
            s = cls()
            s.weights = data.get("weights", [0.0] * 6)
            s.n_samples = data.get("n_samples", 0)
            s.fitted = data.get("fitted", False)
            s.fit_error = data.get("fit_error", float("inf"))
            return s
        except (json.JSONDecodeError, OSError):
            return cls()


def _solve_linear_system(A: list[list[float]], b: list[float]) -> list[float] | None:
    """Solve Ax = b via Gaussian elimination with partial pivoting."""
    n = len(b)
    # Augmented matrix
    M = [row[:] + [bi] for row, bi in zip(A, b)]

    for col in range(n):
        # Partial pivoting
        max_row = col
        for row in range(col + 1, n):
            if abs(M[row][col]) > abs(M[max_row][col]):
                max_row = row
        M[col], M[max_row] = M[max_row], M[col]

        if abs(M[col][col]) < 1e-12:
            return None  # Singular

        # Eliminate
        for row in range(col + 1, n):
            factor = M[row][col] / M[col][col]
            for j in range(col, n + 1):
                M[row][j] -= factor * M[col][j]

    # Back substitution
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = M[i][n]
        for j in range(i + 1, n):
            x[i] -= M[i][j] * x[j]
        x[i] /= M[i][i]

    return x
