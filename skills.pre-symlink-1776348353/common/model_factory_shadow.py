"""Shadow analysis helpers for ModelFactory.

Extracted from model_factory.py to keep module size under 800 lines.
Provides shadow_status() and check_mode_collapse() as standalone functions
that read from JSONL shadow files.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def shadow_status(shadow_file: Path, task: str, hours: int = 2160) -> Dict[str, Any]:
    """Read shadow file to get agreement stats for a task.

    Args:
        shadow_file: Path to the shadow JSONL file.
        task: Task name to filter by.
        hours: Only consider entries from the last N hours (default 90 days).
               Prevents old pre-retrain disagreements from permanently
               dragging down the agreement rate.
    """
    if not shadow_file.exists():
        return {"agreement_rate": 0.0, "sample_count": 0, "model_type": "gpt"}

    cutoff = datetime.now(timezone.utc).timestamp() - (hours * 3600)
    agree = 0
    total = 0
    source_counts: Counter[str] = Counter()

    with open(shadow_file) as f:
        for line in f:
            try:
                entry = json.loads(line)
                if entry.get("task") != task:
                    continue
                # Time-window filter: skip entries older than cutoff
                ts_str = entry.get("timestamp", "")
                if ts_str:
                    try:
                        ts = datetime.fromisoformat(ts_str).timestamp()
                        if ts < cutoff:
                            continue
                    except (ValueError, TypeError):
                        pass
                # Skip entries where teacher failed (empty result = no
                # valid comparison, should not count as disagreement)
                if not (entry.get("teacher_grade") or entry.get("teacher_result")):
                    continue
                total += 1
                if entry.get("agreed", False):
                    agree += 1
                source = entry.get("local_source", "gpt")
                source_counts[source] += 1
            except json.JSONDecodeError:
                continue

    # Use majority vote for model_type, not last-seen
    model_type = source_counts.most_common(1)[0][0] if source_counts else "gpt"

    return {
        "agreement_rate": agree / max(1, total),
        "sample_count": total,
        "model_type": model_type,
    }


def check_mode_collapse(
    shadow_file: Path, task: str, hours: int = 168,
) -> Dict[str, Any]:
    """Check for mode collapse in shadow data grade distribution.

    Mode collapse occurs when the student model predicts a single class
    for nearly all inputs, which can inflate agreement rate misleadingly.

    Flags collapse when:
      - max_class_fraction > 0.95 (one grade dominates)
      - entropy < 0.3 (for binary, max entropy ~0.69)

    Returns dict with grade_distribution, entropy, collapsed flag.
    """
    if not shadow_file.exists():
        return {
            "collapsed": False, "entropy": 0.0,
            "grade_distribution": {}, "reason": "no_data",
        }

    cutoff = datetime.now(timezone.utc).timestamp() - (hours * 3600)
    grade_counts: Counter[str] = Counter()

    with open(shadow_file) as f:
        for line in f:
            try:
                entry = json.loads(line)
                if entry.get("task") != task:
                    continue
                ts_str = entry.get("timestamp", "")
                if ts_str:
                    try:
                        ts = datetime.fromisoformat(ts_str).timestamp()
                        if ts < cutoff:
                            continue
                    except (ValueError, TypeError):
                        pass
                grade = entry.get("local_grade", "")
                if grade:
                    grade_counts[grade.upper()] += 1
            except json.JSONDecodeError:
                continue

    total = sum(grade_counts.values())
    if total == 0:
        return {
            "collapsed": False, "entropy": 0.0,
            "grade_distribution": {}, "reason": "no_data",
        }

    # Compute grade distribution and entropy
    distribution = {g: c / total for g, c in grade_counts.items()}
    entropy = -sum(p * math.log(p) for p in distribution.values() if p > 0)
    max_fraction = max(distribution.values())

    collapsed = max_fraction > 0.95 or entropy < 0.3
    reason = ""
    if max_fraction > 0.95:
        dominant = max(grade_counts, key=grade_counts.get)
        reason = f"dominant_class={dominant} ({max_fraction:.1%})"
    elif entropy < 0.3:
        reason = f"low_entropy={entropy:.3f}"

    return {
        "collapsed": collapsed,
        "entropy": round(entropy, 4),
        "max_class_fraction": round(max_fraction, 4),
        "grade_distribution": {g: round(p, 4) for g, p in distribution.items()},
        "total_samples": total,
        "reason": reason,
    }
