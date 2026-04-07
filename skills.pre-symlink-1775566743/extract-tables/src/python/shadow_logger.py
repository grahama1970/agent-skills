"""Shadow logging for self-correction.

Logs every extraction result to shadow.jsonl for:
1. Strategy disagreement detection (predicted vs actual best)
2. Quality trend monitoring
3. Nightly parameter tuning via /table-lab
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
SHADOW_LOG = SKILL_DIR / "shadow.jsonl"


def log_extraction(
    filepath: str,
    pages: str,
    flavor: str,
    confidence: float,
    num_tables: int,
    accuracy: float,
    elapsed_seconds: float,
    strategy_actual: str | None = None,
) -> None:
    """Log an extraction result for self-correction tracking."""
    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "filepath": os.path.basename(filepath),
        "pages": pages,
        "strategy_predicted": flavor,
        "strategy_actual": strategy_actual or flavor,
        "confidence": round(confidence, 3),
        "agree": strategy_actual is None or strategy_actual == flavor,
        "num_tables": num_tables,
        "accuracy": round(accuracy, 2),
        "elapsed_seconds": round(elapsed_seconds, 3),
    }

    try:
        with open(SHADOW_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass  # Non-critical — don't fail extraction on log error
