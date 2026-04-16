"""
Prompt Lab: Systematic prompt engineering with ground truth evaluation.

Assembles all CLI command groups from split modules.
"""
import sys
from pathlib import Path

# Ensure this directory is importable when running as a script
ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pl_app import app

# Import all command modules to register their commands with the app
import pl_eval  # noqa: F401 -- eval
import pl_eval_sparta  # noqa: F401 -- eval-sparta, test-sparta
import pl_optimize  # noqa: F401 -- optimize
# pl_judge (judge, compare) → migrated to llm-eval-lab
# pl_find_minimum (find-minimum) → migrated to llm-eval-lab
import pl_tools  # noqa: F401 -- list-prompts, show-prompt, sync, history, extract-prompts
import pl_eval_qra  # noqa: F401 -- eval-qra
import pl_ground_truth  # noqa: F401 -- analyze, suggest-optimizations, build-ground-truth, build-llm-ground-truth
import pl_models  # noqa: F401 -- models, seed-memory, extract-prompts (models/seed-memory kept for compat)
import pl_eval_nlg  # noqa: F401 -- eval-nlg
import pl_eval_f36  # noqa: F401 -- eval-f36
import pl_eval_judge  # noqa: F401 -- eval-judge
import pl_eval_heart  # noqa: F401 -- eval-heart
import pl_eval_heart_rationale  # noqa: F401 -- eval-heart-rationale
import pl_eval_mind_rationale  # noqa: F401 -- eval-mind-rationale
import pl_eval_vision  # noqa: F401 -- eval-vision
import pl_eval_json  # noqa: F401 -- eval-json


if __name__ == "__main__":
    app()
