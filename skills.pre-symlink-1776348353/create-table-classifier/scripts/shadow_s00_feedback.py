#!/usr/bin/env python3
"""Co-evolutionary feedback for Shadow S00 classifier.

Shadow-LEGO pattern: After inline review scores table_fidelity,
this module stores the verdict as a training signal for the next
iteration of the Shadow S00 classifier.

When enough new verdicts accumulate (retrain_threshold), it triggers
a retrain via the training script.

Usage from inline_reviewer.py:
    from shadow_s00_feedback import record_shadow_feedback, check_retrain

    # After scoring:
    record_shadow_feedback(
        pdf_hash="abc123",
        s00_profile=profile_data,
        s05_actual_tables=42,
        s05_stream_tables=15,
        table_fidelity_score=0.82,
        shadow_prediction={"needs_stream": True, "stream_confidence": 0.91},
    )

    # Periodically:
    if check_retrain():
        trigger_retrain()
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Optional


# Feedback storage location
_FEEDBACK_DIR = Path(os.environ.get(
    "SHADOW_S00_FEEDBACK_DIR",
    str(Path(__file__).parent.parent / "data" / "feedback"),
))
_FEEDBACK_FILE = _FEEDBACK_DIR / "shadow_s00_verdicts.jsonl"
_RETRAIN_THRESHOLD = int(os.environ.get("SHADOW_S00_RETRAIN_THRESHOLD", "50"))


def record_shadow_feedback(
    pdf_hash: str,
    s00_profile: dict,
    s05_actual_tables: int,
    s05_stream_tables: int,
    table_fidelity_score: float,
    shadow_prediction: Optional[dict] = None,
    source_pdf: str = "",
) -> bool:
    """Record a training signal for Shadow S00 co-evolutionary feedback.

    Each verdict provides ground truth: what did S05 actually find,
    and how good was the table extraction (table_fidelity from scoring)?

    Args:
        pdf_hash: Unique PDF identifier
        s00_profile: S00 profile dict (features for retraining)
        s05_actual_tables: Number of tables S05 actually extracted
        s05_stream_tables: Number of tables found by stream mode
        table_fidelity_score: Score from review-pdf (0-1)
        shadow_prediction: What Shadow S00 predicted (if available)
        source_pdf: PDF filename for debugging

    Returns:
        True if recorded successfully
    """
    _FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)

    # Derive the ground truth label from actual outcomes
    if s05_actual_tables == 0:
        actual_label = "no_tables"
    elif s05_stream_tables > 0:
        actual_label = "needs_stream"
    else:
        actual_label = "lattice_sufficient"

    # Check if shadow prediction was correct
    prediction_correct = None
    if shadow_prediction:
        prediction_correct = (
            shadow_prediction.get("predicted_class") == actual_label
        )

    record = {
        "pdf_hash": pdf_hash,
        "source_pdf": source_pdf,
        "actual_label": actual_label,
        "s05_actual_tables": s05_actual_tables,
        "s05_stream_tables": s05_stream_tables,
        "table_fidelity_score": table_fidelity_score,
        "shadow_prediction": shadow_prediction or {},
        "prediction_correct": prediction_correct,
        "s00_profile": s00_profile,
    }

    try:
        with open(_FEEDBACK_FILE, "a") as f:
            f.write(json.dumps(record) + "\n")
        return True
    except OSError as e:
        print(f"[shadow_s00_feedback] Write failed: {e}")
        return False


def check_retrain() -> bool:
    """Check if enough new verdicts have accumulated for retraining.

    Returns True if verdict count >= retrain_threshold.
    """
    if not _FEEDBACK_FILE.exists():
        return False

    count = 0
    with open(_FEEDBACK_FILE) as f:
        for _ in f:
            count += 1

    return count >= _RETRAIN_THRESHOLD


def get_feedback_stats() -> dict:
    """Get statistics about accumulated feedback."""
    if not _FEEDBACK_FILE.exists():
        return {"count": 0, "labels": {}, "prediction_accuracy": None}

    from collections import Counter
    label_counts = Counter()
    correct = 0
    total_with_prediction = 0

    with open(_FEEDBACK_FILE) as f:
        for line in f:
            try:
                d = json.loads(line)
                label_counts[d.get("actual_label", "unknown")] += 1
                if d.get("prediction_correct") is not None:
                    total_with_prediction += 1
                    if d["prediction_correct"]:
                        correct += 1
            except json.JSONDecodeError:
                continue

    accuracy = correct / total_with_prediction if total_with_prediction > 0 else None
    return {
        "count": sum(label_counts.values()),
        "labels": dict(label_counts),
        "prediction_accuracy": accuracy,
        "predictions_evaluated": total_with_prediction,
        "retrain_threshold": _RETRAIN_THRESHOLD,
        "retrain_ready": sum(label_counts.values()) >= _RETRAIN_THRESHOLD,
    }


def trigger_retrain() -> dict:
    """Trigger Shadow S00 retraining using accumulated feedback.

    Merges feedback with original training data, retrains the model,
    and archives the feedback file.
    """
    if not _FEEDBACK_FILE.exists():
        return {"status": "no_feedback", "message": "No feedback file found"}

    stats = get_feedback_stats()
    if not stats.get("retrain_ready"):
        return {
            "status": "not_ready",
            "count": stats["count"],
            "threshold": _RETRAIN_THRESHOLD,
        }

    # Merge feedback into training format
    merged_path = _FEEDBACK_DIR / "merged_training.jsonl"
    original_path = Path(__file__).parent.parent / "data" / "shadow_s00.jsonl"

    from harvest_shadow_s00 import _extract_s00_features

    with open(merged_path, "w") as out:
        # Copy original training data
        if original_path.exists():
            with open(original_path) as f:
                for line in f:
                    out.write(line)

        # Add feedback verdicts as new training data
        added = 0
        with open(_FEEDBACK_FILE) as f:
            for line in f:
                try:
                    d = json.loads(line)
                    profile = d.get("s00_profile", {})
                    if not profile:
                        continue
                    features = _extract_s00_features(profile)
                    row = {
                        "features": features,
                        "label": d["actual_label"],
                        "source_dir": f"feedback_{d.get('pdf_hash', 'unknown')}",
                        "actual_table_count": d.get("s05_actual_tables", 0),
                        "stream_table_count": d.get("s05_stream_tables", 0),
                        "table_fidelity": d.get("table_fidelity_score", 0),
                    }
                    out.write(json.dumps(row) + "\n")
                    added += 1
                except (json.JSONDecodeError, KeyError):
                    continue

    # Run retraining
    train_script = Path(__file__).parent / "train_shadow_s00.py"
    model_dir = Path(__file__).parent.parent / "models" / "shadow-s00"

    skill_root = Path(__file__).resolve().parent.parent
    clean_env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    result = subprocess.run(
        [
            "uv", "run", "--project", str(skill_root),
            "python", str(train_script),
            "--data", str(merged_path),
            "--model-dir", str(model_dir),
        ],
        capture_output=True, text=True, timeout=120,
        cwd=str(skill_root), env=clean_env,
    )

    # Archive feedback file
    import shutil
    from datetime import datetime
    archive_name = f"verdicts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    archive_path = _FEEDBACK_DIR / "archive" / archive_name
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(_FEEDBACK_FILE), str(archive_path))

    return {
        "status": "ok" if result.returncode == 0 else "failed",
        "original_samples": sum(1 for _ in open(original_path)) if original_path.exists() else 0,
        "feedback_samples": added,
        "total_samples": (sum(1 for _ in open(original_path)) if original_path.exists() else 0) + added,
        "retrain_rc": result.returncode,
        "retrain_stdout_tail": result.stdout[-500:] if result.stdout else "",
        "archived_to": str(archive_path),
    }
