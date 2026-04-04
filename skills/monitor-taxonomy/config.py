"""Configuration for monitor-taxonomy cascade quality monitor.

Centralises paths, thresholds, and state directories.
All env vars are loaded via dotenv before first access.

Inputs: environment variables, dotenv file.
Outputs: module-level constants consumed by probes and cascade.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from loguru import logger

# --- dotenv (MUST be before any os.getenv) ---
SKILLS_DIR = Path(__file__).resolve().parents[1]
if str(SKILLS_DIR) not in sys.path:
    sys.path.append(str(SKILLS_DIR))

try:
    from dotenv_helper import load_env as _load_env
except Exception:
    def _load_env():
        try:
            from dotenv import load_dotenv, find_dotenv
            load_dotenv(find_dotenv(usecwd=True), override=False)
        except Exception as e:
            logger.debug("loading failed: {}", e)

_load_env()

# --- Skill paths ---
SKILL_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SKILL_DIR.parents[2]

# --- ArangoDB ---
ARANGO_URL = os.getenv("ARANGO_URL", "http://127.0.0.1:8529")
ARANGO_DB = os.getenv("ARANGO_DB", "memory")

# --- State ---
STATE_DIR = Path(os.getenv(
    "MONITOR_TAXONOMY_STATE_DIR",
    str(Path.home() / ".pi" / "monitor-taxonomy"),
))
SHADOW_FILE = STATE_DIR / "shadow.jsonl"
METRICS_FILE = STATE_DIR / "metrics.jsonl"
TRAINING_LABELS_FILE = STATE_DIR / "training_labels.jsonl"

# --- Thresholds ---
RETRAIN_LABEL_THRESHOLD = int(os.getenv("TAXONOMY_RETRAIN_THRESHOLD", "50"))
SAMPLE_SIZE = int(os.getenv("TAXONOMY_SAMPLE_SIZE", "100"))
COHERENCE_THRESHOLD = float(os.getenv("TAXONOMY_COHERENCE_THRESHOLD", "0.20"))
STALE_DAYS = int(os.getenv("TAXONOMY_STALE_DAYS", "90"))

# --- Cascade ---
T0_CONFIDENCE_THRESHOLD = 0.80
T15_CONFIDENCE_THRESHOLD = 0.85
