"""Model health dashboard."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import typer
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.storage import MODELS_DIR, load_models

app = typer.Typer(add_completion=False)

OBSERVATIONS_PATH = Path(__file__).resolve().parent.parent / "data" / "observations.jsonl"
TRAINING_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "training_data.jsonl"


def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text().splitlines() if line.strip())


def _model_age_days(summary_path: Path) -> float:
    if not summary_path.exists():
        return -1.0
    data = json.loads(summary_path.read_text())
    trained_at = data.get("trained_at", "")
    if not trained_at:
        return -1.0
    try:
        dt = datetime.fromisoformat(trained_at.rstrip("Z"))
        return (datetime.utcnow() - dt).total_seconds() / 86400
    except ValueError:
        return -1.0


@app.command()
def main() -> None:
    """Report model health and readiness."""
    summary_path = MODELS_DIR / "training_summary.json"
    importance_path = MODELS_DIR / "feature_importance.json"

    print("=" * 60)
    print("LEARN-TIMEOUT STATUS")
    print("=" * 60)

    # Model availability
    dur_model, risk_model = load_models()
    print(f"\nDuration model: {'AVAILABLE' if dur_model else 'NOT FOUND'}")
    if dur_model:
        print(f"  Version:  {dur_model.version}")
        print(f"  Samples:  {dur_model.training_samples}")
        print(f"  MAE:      {dur_model.mae:.1f}s")
        print(f"  R²:       {dur_model.r2:.3f}")
        print(f"  Features: {len(dur_model.feature_names)}")

    risk_available = risk_model and risk_model.available
    print(f"\nRisk model: {'AVAILABLE' if risk_available else 'NOT FOUND'}")
    if risk_available:
        print(f"  Samples:   {risk_model.training_samples}")
        print(f"  Positives: {risk_model.positive_samples}")
        print(f"  ROC-AUC:   {risk_model.roc_auc:.3f}")

    # Model age
    age = _model_age_days(summary_path)
    print(f"\nModel age: ", end="")
    if age < 0:
        print("unknown (no training summary)")
    else:
        print(f"{age:.1f} days")
        if age > 7:
            print("  ⚠ STALE — consider retraining (./run.sh collect && ./run.sh train)")

    # Data counts
    training_count = _count_lines(TRAINING_DATA_PATH)
    observation_count = _count_lines(OBSERVATIONS_PATH)
    print(f"\nTraining data:  {training_count} samples")
    print(f"Observations:   {observation_count} feedback entries")

    # Retrain recommendation
    print(f"\nRetrain recommendation: ", end="")
    if not dur_model:
        print("YES — no model exists")
    elif age > 7:
        print("YES — model is stale (>{:.0f} days)".format(age))
    elif observation_count > 50 and observation_count > training_count * 0.1:
        print(f"YES — {observation_count} new observations available")
    else:
        print("NO — model is healthy")

    # Feature importance (top 5)
    if importance_path.exists():
        imp = json.loads(importance_path.read_text())
        top = list(imp.items())[:5]
        if top:
            print(f"\nTop features:")
            for name, score in top:
                bar = "█" * int(score * 50)
                print(f"  {name:30s} {score:.4f} {bar}")

    print()


if __name__ == "__main__":
    app()
