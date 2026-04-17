"""Style scanners for skills-ci.

Checks code style conventions that improve agent discoverability
and maintainability. Currently: thin __init__.py enforcement.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List

_THIS_DIR = str(Path(__file__).resolve().parent)
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from models import Violation
from scanners import should_skip_path

# ---------------------------------------------------------------------------
# style-thin-init-py: __init__.py must be thin (re-exports only, ≤20 LOC)
# ---------------------------------------------------------------------------

_INIT_PY_MAX_LINES = 20


def scan_style_thin_init_py(skill_dir: Path) -> List[Violation]:
    """Flag __init__.py files with business logic (>20 non-blank, non-comment lines).

    Rule: style.thin_init_py
    Severity: warn

    Rationale: Logic hidden in __init__.py is invisible to agents doing
    file-based search. On 2026-03-16 an agent misdiagnosed monitor-taxonomy
    because run_probes() lived in probes/__init__.py (122 lines) instead of
    a named module.
    """
    violations: List[Violation] = []
    skill_name = skill_dir.name

    for init_py in skill_dir.rglob("__init__.py"):
        if should_skip_path(init_py):
            continue
        try:
            text = init_py.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        lines = [
            ln for ln in text.splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        if len(lines) > _INIT_PY_MAX_LINES:
            violations.append(Violation(
                rule="style.thin_init_py",
                severity="warn",
                skill=skill_name,
                path=str(init_py),
                message=(
                    f"__init__.py has {len(lines)} non-blank lines "
                    f"(limit {_INIT_PY_MAX_LINES}); "
                    f"extract logic to a named module."
                ),
            ))

    return violations
