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


if __name__ == "__main__":
    app()
