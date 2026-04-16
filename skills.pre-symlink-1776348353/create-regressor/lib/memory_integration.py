"""Memory integration for create-regressor.

Purpose:
- Recall prior regression runs before training (avoid re-solving).
- Learn results after training (enable future recall).
- Bridge attribute extraction for taxonomy tagging.

Inputs:
- Model name, task description, metrics.

Outputs:
- Prior run context (if found).
- Stored lesson (after training).

Failure modes:
- /memory offline: logged as warning, non-fatal. Training continues.
"""

from __future__ import annotations
import os

import json
import subprocess
from pathlib import Path
from typing import Any, Optional

from loguru import logger

MEMORY_SKILL = Path(__file__).resolve().parent.parent.parent / "memory"


# ---------------------------------------------------------------------------
# Bridge attribute extraction (keyword-fast, matches create-classifier)
# ---------------------------------------------------------------------------

BRIDGE_KEYWORDS: dict[str, list[str]] = {
    "Precision": ["accuracy", "mae", "rmse", "r2", "mape", "calibrated", "exact", "precise"],
    "Resilience": ["robust", "outlier", "cross-validation", "holdout", "generalize", "stable"],
    "Fragility": ["overfit", "fragile", "unstable", "variance", "sensitive", "brittle"],
    "Corruption": ["noisy", "corrupt", "missing", "anomaly", "outlier"],
    "Loyalty": ["reproducible", "deterministic", "seed", "consistent", "reliable"],
    "Stealth": ["ensemble", "boosting", "hidden", "latent", "feature_importance"],
}


def extract_bridges(text: str) -> list[str]:
    """Extract bridge attributes from text using keyword matching."""
    text_lower = text.lower()
    bridges = []
    for attr, keywords in BRIDGE_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            bridges.append(attr)
    return bridges or ["Precision"]  # Default for regression


# ---------------------------------------------------------------------------
# Recall prior runs
# ---------------------------------------------------------------------------

def recall_prior_regressors(
    task_name: str,
    model_type: Optional[str] = None,
) -> Optional[dict]:
    """Recall prior regression runs from /memory.

    Returns dict with items if found, None if memory unavailable.
    """
    if not MEMORY_SKILL.exists():
        logger.warning(f"/memory skill not found at {MEMORY_SKILL}")
        return None

    query = f"regression model {task_name}"
    if model_type:
        query += f" {model_type}"

    try:
        result = subprocess.run(
            [
                str(MEMORY_SKILL / "run.sh"), "recall",
                "--q", query,
                "--tag", "create-regressor",
            ],
            capture_output=True, text=True, timeout=15,
            cwd=str(MEMORY_SKILL),
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode != 0:
            logger.warning(f"Memory recall failed: {result.stderr[:200]}")
            return None

        data = json.loads(result.stdout)
        if data.get("found"):
            items = data.get("items", [])
            logger.info(f"Memory recall: {len(items)} prior regression run(s) found for '{task_name}'")
            return data
        return None

    except subprocess.TimeoutExpired:
        logger.warning("Memory recall timed out")
        return None
    except Exception as exc:
        logger.warning(f"Memory recall error: {exc}")
        return None


# ---------------------------------------------------------------------------
# Learn results
# ---------------------------------------------------------------------------

def learn_regressor_run(
    model_name: str,
    model_type: str,
    metrics: dict[str, float],
    training_samples: int,
    feature_count: int,
    selected_by: str,
    cv_results: Optional[dict] = None,
    hp_search_trials: Optional[int] = None,
    iteration: Optional[int] = None,
) -> bool:
    """Store regression run results in /memory for future recall."""
    if not MEMORY_SKILL.exists():
        logger.warning(f"/memory skill not found at {MEMORY_SKILL}")
        return False

    problem = f"Regression model: {model_name}"
    if iteration:
        problem += f" (iteration {iteration})"

    solution_parts = [
        f"Model type={model_type}, selected_by={selected_by}.",
        f"MAE={metrics.get('mae', 0):.4f}, RMSE={metrics.get('rmse', 0):.4f}, "
        f"R2={metrics.get('r2', 0):.4f}, MAPE={metrics.get('mape', 0):.4f}.",
        f"{training_samples} samples, {feature_count} features.",
    ]
    if hp_search_trials:
        solution_parts.append(f"HP search: {hp_search_trials} Optuna trials.")
    if cv_results:
        best_cv = min(cv_results.items(), key=lambda x: x[1].get("mae", float("inf")))
        solution_parts.append(f"Best CV model: {best_cv[0]} (MAE={best_cv[1].get('mae', '?')}).")

    solution = " ".join(solution_parts)

    # Build tags
    bridges = extract_bridges(solution)
    tags = ["create-regressor", model_name, "learned-model", model_type] + bridges

    try:
        cmd = [
            str(MEMORY_SKILL / "run.sh"), "learn",
            "--problem", problem,
            "--solution", solution,
        ]
        for t in tags:
            cmd.extend(["--tag", str(t)])

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15,
            cwd=str(MEMORY_SKILL),
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode == 0:
            logger.info(f"Learned regression run to /memory: {model_name}")
            return True
        else:
            logger.warning(f"Memory learn failed: {result.stderr[:200]}")
            return False

    except Exception as exc:
        logger.warning(f"Memory learn error: {exc}")
        return False
