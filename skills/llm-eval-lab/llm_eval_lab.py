"""
LLM Eval Lab: Model evaluation, comparison, and cost analysis.

Assembles all CLI command groups from split modules.
"""
import sys
from pathlib import Path

# Ensure this directory is importable when running as a script
ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval_app import app

# Import all command modules to register their commands with the app
import find_minimum  # noqa: F401 -- find-minimum
import grid_eval  # noqa: F401 -- grid-eval
import judge  # noqa: F401 -- judge, compare
import models_cmd  # noqa: F401 -- models, seed-memory
import judge_grid  # noqa: F401 -- judge-grid
import runner  # noqa: F401 -- run-matrix (multi-trial, deterministic-first, INFRA isolation)
import build_report  # noqa: F401 -- report (reusable evidence HTML)


if __name__ == "__main__":
    app()
