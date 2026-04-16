"""
Blind evaluation checks for best-practices-python rules.

Composes /treesitter violations for AST-based checks (banned imports,
bare except, mutable defaults, eval/exec, shell=True, file length).
Keeps file-content checks (module docstring, line count) that treesitter
doesn't produce pass/fail pairs for.

Inputs: target directory path
Outputs: list of TestCheck results
Failure modes: treesitter unavailable (fallback to basic checks)
"""

from __future__ import annotations
import os

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from loguru import logger

# Avoid circular import at module level
_parent = str(Path(__file__).parent.parent)
if _parent not in sys.path:
    sys.path.insert(0, _parent)

from test_lab import TestCheck

# Resolve /treesitter run.sh
_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent
_TREESITTER_RUN = _SKILLS_DIR / "treesitter" / "run.sh"

# Treesitter rules relevant to Python best-practices
_PYTHON_RULES = [
    "banned-import-logging", "banned-import-requests", "banned-import-argparse",
    "bare-except", "mutable-default", "eval-exec", "shell-true", "file-length",
]

# Map treesitter rule names to TestCheck names and categories
_RULE_MAP: dict[str, tuple[str, str, str, str]] = {
    # rule -> (check_name_suffix, category, fail_desc, pass_desc)
    "banned-import-logging": ("no_logging", "conventions", "Uses `import logging` — should use loguru", "Correctly avoids stdlib logging"),
    "banned-import-requests": ("no_requests", "conventions", "Uses `import requests` — should use httpx", "Correctly avoids requests library"),
    "banned-import-argparse": ("no_argparse", "conventions", "Uses `import argparse` — should use typer", "Correctly avoids argparse"),
    "bare-except": ("no_bare_except", "correctness", "Has bare `except:` clause — should catch specific exceptions", "No bare except clauses"),
    "mutable-default": ("no_mutable_defaults", "correctness", "Has mutable default argument (list/dict/set) — use None + factory", "No mutable default arguments"),
    "eval-exec": ("no_eval_exec", "security", "Uses eval() or exec() — security risk", "No eval/exec usage"),
    "shell-true": ("no_shell_true", "security", "Uses subprocess with shell=True — command injection risk", "No shell=True in subprocess calls"),
    "file-length": ("max_lines", "style", "File exceeds 800 lines", "File within line limit"),
}


def _run_treesitter(target_dir: Path) -> list[dict[str, Any]]:
    """Call /treesitter violations and return parsed results."""
    cmd = [
        str(_TREESITTER_RUN), "violations", str(target_dir),
        "--rules", ",".join(_PYTHON_RULES), "--json",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.stdout.strip():
            return json.loads(result.stdout)
        return []
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as e:
        logger.warning("treesitter violations unavailable: {}", e)
        return []


def run_checks(target_dir: Path) -> list[TestCheck]:
    """Run all Python best-practices checks against target directory."""
    checks: list[TestCheck] = []
    py_files = [
        f for f in target_dir.rglob("*.py")
        if not any(part in f.parts for part in (".venv", "venv", "__pycache__", ".git", "node_modules"))
    ]

    if not py_files:
        checks.append(TestCheck(
            name="python_files_exist",
            category="structure",
            passed=True,
            description="No Python files found (nothing to check)",
        ))
        return checks

    # Run treesitter violations for all AST-based checks
    violations = _run_treesitter(target_dir)

    # Group violations by file and rule
    violated: dict[str, set[str]] = {}  # file -> set of rule names
    for v in violations:
        fpath = v.get("file", "")
        rule = v.get("rule", "")
        violated.setdefault(fpath, set()).add(rule)

    # Generate TestCheck results per file
    for py_file in py_files:
        rel = py_file.name
        file_violations = violated.get(str(py_file), set())

        # Module docstring check (not an AST violation rule — keep as file-content)
        try:
            source = py_file.read_text(encoding="utf-8", errors="ignore")
            has_docstring = source.lstrip().startswith(('"""', "'''", 'r"""', "r'''"))
            checks.append(TestCheck(
                name=f"{rel}:module_docstring",
                category="style",
                passed=has_docstring,
                description="Missing module docstring" if not has_docstring else "Module docstring present",
            ))
        except Exception:
            pass

        # Convert treesitter violations to pass/fail TestChecks
        for rule, (suffix, category, fail_desc, pass_desc) in _RULE_MAP.items():
            has_violation = rule in file_violations
            checks.append(TestCheck(
                name=f"{rel}:{suffix}",
                category=category,
                passed=not has_violation,
                description=fail_desc if has_violation else pass_desc,
            ))

    return checks
