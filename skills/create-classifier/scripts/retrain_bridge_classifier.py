#!/usr/bin/env python3
"""Smart retraining for bridge classifier.

Only retrains when sufficient new data is available.
Designed to run nightly via scheduler.

Usage:
    python retrain_bridge_classifier.py --check      # Check if retraining needed
    python retrain_bridge_classifier.py --retrain    # Force retrain
    python retrain_bridge_classifier.py              # Check + retrain if needed

Trigger conditions:
    - New data increased by >20% since last training
    - At least 50 new examples available
    - Last training was >7 days ago (regardless of data)
"""

import typer
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger

# Paths
SKILL_DIR = Path(__file__).parent.parent
DATA_DIR = SKILL_DIR / "data" / "bridge_classifier"
MODEL_DIR = SKILL_DIR / "models" / "bridge_classifier"
STATE_FILE = DATA_DIR / ".training_state.json"

# Thresholds
MIN_NEW_EXAMPLES = 50
DATA_GROWTH_THRESHOLD = 0.20  # 20% more data triggers retrain
MAX_DAYS_WITHOUT_RETRAIN = 7


def get_data_hash(file_path: Path) -> str:
    """Get hash of training data file."""
    if not file_path.exists():
        return ""
    return hashlib.md5(file_path.read_bytes()).hexdigest()


def count_examples(file_path: Path) -> int:
    """Count examples in JSONL file."""
    if not file_path.exists():
        return 0
    return sum(1 for _ in open(file_path))


def load_state() -> dict:
    """Load training state."""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state: dict):
    """Save training state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))


def collect_new_data() -> int:
    """Collect training data from memory/taxonomy."""
    logger.info("Collecting training data from memory...")

    result = subprocess.run(
        [
            sys.executable,
            str(SKILL_DIR / "scripts" / "collect_bridge_data.py"),
            "--output", str(DATA_DIR / "raw.jsonl"),
            "--split",
            "--min-per-class", "200",
        ],
        capture_output=True,
        text=True,
        cwd=str(SKILL_DIR),
    )

    if result.returncode != 0:
        logger.error(f"Data collection failed: {result.stderr}")
        return 0

    return count_examples(DATA_DIR / "raw.jsonl")


def check_should_retrain() -> tuple[bool, str]:
    """Check if retraining is needed.

    Returns:
        (should_retrain, reason)
    """
    state = load_state()

    # Get current data stats
    train_file = DATA_DIR / "train.jsonl"
    current_count = count_examples(train_file)
    current_hash = get_data_hash(train_file)

    # Check last training info
    last_count = state.get("last_train_count", 0)
    last_hash = state.get("last_train_hash", "")
    last_date_str = state.get("last_train_date")

    if last_date_str:
        last_date = datetime.fromisoformat(last_date_str)
        days_since = (datetime.now() - last_date).days
    else:
        days_since = float("inf")

    # Check conditions

    # 1. Data changed and growth > threshold
    if current_hash != last_hash and last_count > 0:
        new_examples = current_count - last_count
        growth_rate = new_examples / last_count if last_count > 0 else 1.0

        if new_examples >= MIN_NEW_EXAMPLES and growth_rate >= DATA_GROWTH_THRESHOLD:
            return True, f"Data grew by {new_examples} examples ({growth_rate:.0%})"

    # 2. Never trained
    if not last_hash:
        return True, "No previous training found"

    # 3. Stale training
    if days_since >= MAX_DAYS_WITHOUT_RETRAIN:
        return True, f"Last training was {days_since} days ago"

    return False, f"No retraining needed (last: {days_since}d ago, data: {current_count})"


def run_training() -> bool:
    """Run the training pipeline."""
    logger.info("Starting bridge classifier training...")

    train_file = DATA_DIR / "train.jsonl"
    val_file = DATA_DIR / "val.jsonl"

    if not train_file.exists() or not val_file.exists():
        logger.error("Training data not found")
        return False

    # Run iterative training
    result = subprocess.run(
        [
            sys.executable,
            str(SKILL_DIR / "scripts" / "iterative_train_text.py"),
            "--train-data", str(train_file),
            "--val-data", str(val_file),
            "--output-dir", str(MODEL_DIR),
            "--multilabel",
            "--accuracy-threshold", "0.80",
            "--max-latency-ms", "10",
        ],
        capture_output=False,  # Stream output
        cwd=str(SKILL_DIR),
    )

    if result.returncode != 0:
        logger.error("Training failed")
        return False

    # Update state
    state = load_state()
    state.update({
        "last_train_date": datetime.now().isoformat(),
        "last_train_count": count_examples(train_file),
        "last_train_hash": get_data_hash(train_file),
    })
    save_state(state)

    logger.info("Training complete!")
    return True


app = typer.Typer(help="Smart bridge classifier retraining")


@app.command()
def main(
    check: bool = typer.Option(False, help="Only check if retraining needed"),
    retrain: bool = typer.Option(False, help="Force retraining"),
    collect: bool = typer.Option(False, help="Collect new data first"),
    verbose: bool = typer.Option(False, help="Verbose output"),
):
    if verbose:
        logger.remove()
        logger.add(sys.stderr, level="DEBUG")

    # Collect new data if requested
    if collect:
        count = collect_new_data()
        logger.info(f"Collected {count} examples")

    # Check if retraining needed
    should_retrain, reason = check_should_retrain()
    logger.info(f"Retraining check: {reason}")

    if check:
        print(f"Should retrain: {should_retrain}")
        print(f"Reason: {reason}")
        sys.exit(0 if not should_retrain else 1)

    if should_retrain or retrain:
        success = run_training()
        sys.exit(0 if success else 1)
    else:
        logger.info("Skipping retraining")
        sys.exit(0)


if __name__ == "__main__":
    app()
