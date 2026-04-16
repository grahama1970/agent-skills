"""Configuration for learn-datalake skill.

Loads environment variables and defines paths for integrated skills.
"""

import os
from pathlib import Path

# Integrated skill paths (relative to pi-mono root or configurable via env)
PI_MONO_ROOT = Path(os.getenv("PI_MONO_ROOT", str(Path(__file__).resolve().parents[4])))
DEBUG_TABLE_PATH = Path(os.getenv("DEBUG_TABLE_PATH", PI_MONO_ROOT / ".pi/skills/table-lab"))
CREATE_TABLE_CLASSIFIER_PATH = Path(
    os.getenv("CREATE_TABLE_CLASSIFIER_PATH", PI_MONO_ROOT / ".pi/skills/create-table-classifier")
)
DEBUG_PDF_PATH = Path(os.getenv("DEBUG_PDF_PATH", PI_MONO_ROOT / ".pi/skills/debug-pdf"))

# Task Monitor
TASK_MONITOR_REGISTRY = Path.home() / ".pi" / "task-monitor" / "registry.json"

# Strategy outcome harvest (Shadow-LEGO feedback loop)
STRATEGY_OUTCOMES_GLOB = "data/**/05_strategy_outcomes.jsonl"
# Additional search paths for strategy outcomes (all datalake locations)
STRATEGY_OUTCOMES_EXTRA_DIRS = [
    Path("/mnt/storage12tb/extractor_data/output/synthetic_validation"),
    Path("/mnt/storage12tb/extractor_data/results"),
    Path("/mnt/storage12tb/extractor_corpus/results"),
    Path("/mnt/storage12tb/media/agents/shared/review-pdf/extracted_runs"),
]
STRATEGY_TRAINING_DIR = Path.home() / ".pi/assistant/training_data/table-strategy-selector"
MIN_TRAINING_EXAMPLES = 200  # gate for triggering sklearn training
MIN_PROMOTION_EXAMPLES = 500  # gate for shadow → active promotion
PROMOTION_F1_THRESHOLD = 0.85

# Extractor project root (for model output)
EXTRACTOR_ROOT = Path(os.getenv(
    "EXTRACTOR_ROOT",
    str(Path.home() / "workspace/experiments/extractor"),
))
STRATEGY_MODEL_DIR = EXTRACTOR_ROOT / "models" / "table-strategy-classifier"

# /assistant skill
ASSISTANT_RUN = Path.home() / ".pi/skills/assistant/run.sh"

# /classifier-lab skill (produces deployment-ready models)
CLASSIFIER_LAB_SCRIPTS = Path(os.getenv(
    "CLASSIFIER_LAB_SCRIPTS",
    str(Path.home() / ".pi/skills/classifier-lab/scripts"),
))
CLASSIFIER_LAB_VENV = Path(os.getenv(
    "CLASSIFIER_LAB_VENV",
    str(Path.home() / ".pi/skills/classifier-lab/.venv"),
))
