"""Shared constants, paths, and thresholds for monitor-skill-health.

Centralises configuration so that checkers, review, and reporting modules
all reference the same values without circular imports.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import typer
from loguru import logger
from rich.console import Console

# ---------------------------------------------------------------------------
# Path bootstrapping
# ---------------------------------------------------------------------------

SKILLS_ROOT = Path(__file__).resolve().parents[1]
if str(SKILLS_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILLS_ROOT))

try:
    from dotenv_helper import load_env as _load_env
except Exception:  # pragma: no cover - fallback for isolated environments
    def _load_env() -> None:
        try:
            from dotenv import find_dotenv, load_dotenv

            load_dotenv(find_dotenv(usecwd=True), override=False)
        except Exception as e:
            logger.debug("loading failed: {}", e)

_load_env()

# ---------------------------------------------------------------------------
# Skill / external tool paths
# ---------------------------------------------------------------------------

THIS_SKILL_DIR = Path(__file__).resolve().parent
ASSESS_RUN = SKILLS_ROOT / "assess" / "run.sh"
ASSESS_PY = SKILLS_ROOT / "assess" / "assess.py"
REVIEW_CODE_RUN = SKILLS_ROOT / "review-code" / "run.sh"
REVIEW_CODE_PY = SKILLS_ROOT / "review-code" / "code_review.py"
MEMORY_RUN = SKILLS_ROOT / "memory" / "run.sh"
SCHEDULER_RUN = SKILLS_ROOT / "scheduler" / "run.sh"

# ---------------------------------------------------------------------------
# State / output directories
# ---------------------------------------------------------------------------

STATE_DIR = Path(
    os.getenv(
        "MONITOR_SKILL_HEALTH_STATE_DIR",
        str(Path.home() / ".pi" / "monitor-skill-health"),
    )
)
RUNS_DIR = STATE_DIR / "runs"
LATEST_RESULTS_FILE = STATE_DIR / "latest_results.jsonl"
LATEST_SUMMARY_FILE = STATE_DIR / "latest_summary.json"
HISTORY_FILE = STATE_DIR / "history.jsonl"
TASK_STATE_FILE = STATE_DIR / "task_state.json"
TICKET_DRAFTS_DIR = STATE_DIR / "ticket_drafts"

# ---------------------------------------------------------------------------
# Console / logging
# ---------------------------------------------------------------------------

console = Console(stderr=True)
logger.remove()
logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level:<7} | {message}")

# ---------------------------------------------------------------------------
# Severity / risk thresholds
# ---------------------------------------------------------------------------

SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1}
RISK_BASE_SCORES = {"critical": 100, "high": 35, "medium": 8, "low": 1}
HIGH_RISK_MEDIUM_THRESHOLD = int(os.getenv("MONITOR_SKILL_HEALTH_HIGH_RISK_MEDIUM_THRESHOLD", "6"))
HIGH_RISK_SCORE_THRESHOLD = int(os.getenv("MONITOR_SKILL_HEALTH_HIGH_RISK_SCORE_THRESHOLD", "40"))
HIGH_RISK_MONOLITH_LINES = int(os.getenv("MONITOR_SKILL_HEALTH_HIGH_RISK_MONOLITH_LINES", "1500"))
MAX_DEEP_REVIEW_DEFAULT = int(os.getenv("MONITOR_SKILL_HEALTH_DEEP_REVIEW_MAX", "8"))
REVIEW_WORKSPACE_FILE_LIMIT = int(os.getenv("MONITOR_SKILL_HEALTH_REVIEW_WORKSPACE_FILE_LIMIT", "8"))
ARTIFACT_STORAGE_ROOT = Path(
    os.getenv("MONITOR_SKILL_HEALTH_ARTIFACT_ROOT", "/mnt/storage12tb/media")
)

# ---------------------------------------------------------------------------
# Noise / artifact filters
# ---------------------------------------------------------------------------

NOISE_PATH_PARTS = {
    ".artifacts",
    "artifacts",
    "reports",
    "report",
    "state",
    "tmp",
    "temp",
    "diagnostics",
    "runs",
    "output",
    "outputs",
    "history",
    "cache",
    ".cache",
    "checkpoints",
    "weights",
    "models",
    "datasets",
    "dataset",
    "sessions",
    "work",
    "extracted_runs",
    "review_output",
    "self_review_output",
    "review_our_changes",
    "unsloth_compiled_cache",
    "Qwen3-TTS",
    "third_party",
    "vendor",
    "test",
    "tests",
    "fixtures",
}

ASSESS_REFERENCE_PATH_PARTS = {
    "docs",
    "examples",
    "legacy-reports",
    "review_output",
    "review_our_changes",
    "review_brutal_output",
    "self_review_output",
}

HEAVY_ARTIFACT_DIRS = {
    "models",
    "outputs",
    "logs",
    "data",
    "datasets",
    "work",
    "extracted_runs",
    "checkpoints",
    "weights",
    "artifacts",
    "sessions",
    "papers",
}
HEAVY_ARTIFACT_SUFFIXES = {".safetensors", ".gguf", ".bin", ".pt", ".ckpt", ".pth"}

# ---------------------------------------------------------------------------
# Typer app
# ---------------------------------------------------------------------------

app = typer.Typer(
    no_args_is_help=True,
    help="Monitor skill health across registered skills with aggregate run summaries.",
)
