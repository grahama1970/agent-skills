"""conftest - adversarial.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

if str(SRC) in sys.path:
    sys.path.remove(str(SRC))
sys.path.insert(0, str(SRC))

shadow = sys.modules.get("code_runner")
if shadow is not None and not hasattr(shadow, "__path__"):
    sys.modules.pop("code_runner", None)
