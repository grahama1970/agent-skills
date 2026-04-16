#!/usr/bin/env python3
"""SPARTA QRA Reality Check - ADVERSARIAL data quality assessment.

This is a thin wrapper that bootstraps the refactored package and calls main().
The actual implementation lives in the submodules:
- config.py: Constants, paths, thresholds, domain knowledge
- annealing.py: Dynamic threshold management
- data_loader.py: Database access utilities
- statistical_tests.py: Data integrity and statistical validation
- adversarial.py: Corruption, contamination, hallucination detection
- brandon_review.py: Domain expert persona-based semantic validation
- convergence.py: Issue tracking and fix suggestion logic
- reporting.py: Console and client report generation
- cli.py: CLI entry points and orchestration
"""

import sys
from pathlib import Path

# Add the skill directory to sys.path so the package can be imported
# This allows 'from config import ...' style relative imports to work
# when the script is invoked directly via 'python check.py'
_skill_dir = Path(__file__).resolve().parent
if str(_skill_dir) not in sys.path:
    sys.path.insert(0, str(_skill_dir))

# Now import using absolute imports (since we can't use relative imports
# in a script that's run directly, but we've added the dir to sys.path)
from cli import main as _cli_main  # noqa: E402


if __name__ == "__main__":
    sys.exit(_cli_main())
