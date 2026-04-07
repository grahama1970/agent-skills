"""Configuration constants and paths for table-lab skill."""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Corpus paths
# ---------------------------------------------------------------------------
_EMBRY_STORAGE = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb"))
CORPUS_ROOT = Path(os.environ.get("CORPUS_ROOT", str(_EMBRY_STORAGE / "extractor_corpus")))
CORPUS_HINTS_PATH = CORPUS_ROOT / "metadata" / "table_hints.json"
CORPUS_TUNE_RESULTS_PATH = CORPUS_ROOT / "metadata" / "table_tune_results.jsonl"
CORPUS_MANIFEST_PATH = CORPUS_ROOT / "metadata" / "manifest.jsonl"

# ---------------------------------------------------------------------------
# Local data directories
# ---------------------------------------------------------------------------
DATA_DIR = Path(os.environ.get("DEBUG_TABLE_DATA", Path.home() / ".pi" / "table-lab"))
HINTS_DIR = DATA_DIR / "hints"
CHECKPOINT_DIR = DATA_DIR / "checkpoints"
RESULTS_DIR = DATA_DIR / "results"

# Ensure data dirs exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
HINTS_DIR.mkdir(parents=True, exist_ok=True)
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# Manifest path (NDJSON ledger of completed runs)
MANIFEST_PATH = DATA_DIR / "manifest.jsonl"

# ---------------------------------------------------------------------------
# Default parameter grids for systematic sweep
# ---------------------------------------------------------------------------
LATTICE_LINE_SCALES = [5, 10, 15, 20, 25, 30, 40, 60]
STREAM_EDGE_TOLS = [25, 50, 100, 150]

# ---------------------------------------------------------------------------
# Sampling config
# ---------------------------------------------------------------------------
MAX_SAMPLE_PAGES = 3
MIN_DRAWINGS_FOR_TABLE = 4  # minimum line segments to suspect a table

# ---------------------------------------------------------------------------
# Watchdog thresholds (env-configurable)
# ---------------------------------------------------------------------------
WATCHDOG_WARN_FRAGMENTATION_RATE = float(
    os.environ.get("WATCHDOG_WARN_FRAGMENTATION_RATE", "0.65"),
)
WATCHDOG_STOP_FRAGMENTATION_RATE = float(
    os.environ.get("WATCHDOG_STOP_FRAGMENTATION_RATE", "0.55"),
)
CIRCUIT_BREAKER_MAX_FAILURES = int(
    os.environ.get("CIRCUIT_BREAKER_MAX_FAILURES", "5"),
)

# ---------------------------------------------------------------------------
# Convergence settings
# ---------------------------------------------------------------------------
MAX_CONVERGENCE_ITERATIONS = int(
    os.environ.get("MAX_CONVERGENCE_ITERATIONS", "3"),
)
CONVERGENCE_SCORE_DELTA = float(
    os.environ.get("CONVERGENCE_SCORE_DELTA", "2.0"),
)
WATCHDOG_CHECKPOINT_INTERVAL = int(
    os.environ.get("WATCHDOG_CHECKPOINT_INTERVAL", "5"),
)

# Per-PDF timeout in seconds (default 5 minutes — prevents corrupted PDFs from hanging)
PDF_TUNE_TIMEOUT = int(
    os.environ.get("DT_PDF_TIMEOUT", "300"),
)

# ---------------------------------------------------------------------------
# Known presets — maps S00 preset names to broad categories so the tuner
# can select appropriate parameter grids automatically.
# ---------------------------------------------------------------------------
KNOWN_PRESETS: dict[str, str] = {
    "arxiv": "Scientific",
    "requirements_spec": "Engineering",
    "stress_test": "Engineering",
}

# ---------------------------------------------------------------------------
# ML Classifier integration (95%+ accuracy ensemble from create-table-classifier)
# ---------------------------------------------------------------------------
_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent
CLASSIFIER_MODEL_PATH = Path(os.environ.get(
    "TABLE_CLASSIFIER_MODEL_PATH",
    str(_SKILLS_DIR / "create-table-classifier" / "models" / "table-classifier-ensemble-final"),
))
USE_CLASSIFIER_BASELINE = os.environ.get("USE_TABLE_CLASSIFIER", "true").lower() in ("1", "true", "yes")
CLASSIFIER_CONFIDENCE_THRESHOLD = float(os.environ.get("CLASSIFIER_CONFIDENCE_THRESHOLD", "0.75"))

# ---------------------------------------------------------------------------
# Backend selection: "camelot" (legacy) or "rust" (pdf_oxide)
# ---------------------------------------------------------------------------
BACKEND = os.environ.get("TABLE_LAB_BACKEND", "camelot")
