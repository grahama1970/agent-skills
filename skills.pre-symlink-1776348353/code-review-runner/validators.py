"""T0 deterministic validators for /code-review-runner.

All functions are pure subprocess + regex — no LLM calls.
Each validator returns a list of T0Violation objects.
"""
from __future__ import annotations

import subprocess
import re
from pathlib import Path

from loguru import logger

from models import T0Violation

SKILLS_DIR = Path(__file__).resolve().parent.parent


# ── Ruff lint (Python files only) ────────────────────────────────────

def run_ruff(files: list[str], cwd: str) -> list[T0Violation]:
    """Run ruff on Python files and return violations."""
    py_files = [f for f in files if f.endswith(".py")]
    if not py_files:
        return []

    try:
        result = subprocess.run(
            ["ruff", "check", "--output-format=json", *py_files],
            capture_output=True, text=True, cwd=cwd, timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.warning(f"ruff not available or timed out: {exc}")
        return []

    if not result.stdout.strip():
        return []

    import json
    try:
        issues = json.loads(result.stdout)
    except json.JSONDecodeError:
        logger.warning("ruff output not valid JSON")
        return []

    violations = []
    for issue in issues:
        severity = _ruff_severity(issue.get("code", ""))
        violations.append(T0Violation(
            rule=f"ruff-{issue.get('code', 'unknown')}",
            severity=severity,
            file=issue.get("filename", ""),
            line=issue.get("location", {}).get("row", 0),
            message=issue.get("message", ""),
            source="ruff",
        ))
    return violations


def _ruff_severity(code: str) -> str:
    """Map ruff rule codes to severity levels."""
    if code.startswith("S"):  # Security (bandit)
        return "critical"
    if code.startswith("E9") or code.startswith("F"):  # Syntax/fatal
        return "major"
    if code.startswith("E"):  # Style
        return "minor"
    return "info"


# ── Python compile() check ──────────────────────────────────────────

def run_compile_check(files: list[str], cwd: str) -> list[T0Violation]:
    """Compile-check Python files for syntax errors."""
    py_files = [f for f in files if f.endswith(".py")]
    violations = []

    for f in py_files:
        fpath = Path(cwd) / f
        if not fpath.exists():
            violations.append(T0Violation(
                rule="file-missing",
                severity="critical",
                file=f,
                message=f"File does not exist: {f}",
                source="compile",
            ))
            continue
        try:
            source = fpath.read_text(encoding="utf-8")
            compile(source, str(fpath), "exec")
        except SyntaxError as exc:
            violations.append(T0Violation(
                rule="syntax-error",
                severity="critical",
                file=f,
                line=exc.lineno or 0,
                message=f"SyntaxError: {exc.msg}",
                source="compile",
            ))
    return violations


# ── File size check (800 LOC max per best-practices-python) ─────────

def run_file_limits(files: list[str], cwd: str, max_lines: int = 800) -> list[T0Violation]:
    """Check Python files don't exceed max LOC."""
    py_files = [f for f in files if f.endswith(".py")]
    violations = []

    for f in py_files:
        fpath = Path(cwd) / f
        if not fpath.exists():
            continue
        line_count = len(fpath.read_text(encoding="utf-8").splitlines())
        if line_count > max_lines:
            violations.append(T0Violation(
                rule="bp-python-file-limit",
                severity="major",
                file=f,
                message=f"File has {line_count} lines (max {max_lines})",
                source="best-practices-python",
            ))
    return violations


# ── best-practices-python checks ────────────────────────────────────

_BP_PYTHON_PATTERNS = [
    # (pattern_in_file, violation_rule, message, severity)
    (r"^import logging\b", "bp-python-loguru", "Use loguru, not logging", "major"),
    (r"^from logging\b", "bp-python-loguru", "Use loguru, not logging", "major"),
    (r"^import requests\b", "bp-python-httpx", "Use httpx, not requests", "major"),
    (r"^from requests\b", "bp-python-httpx", "Use httpx, not requests", "major"),
    (r"^\s*import argparse\b", "bp-python-typer", "Use typer, not argparse", "minor"),
    (r"^\s*from argparse\b", "bp-python-typer", "Use typer, not argparse", "minor"),
    (r"^\s*import click\b", "bp-python-typer", "Use typer, not click", "minor"),
]


def run_best_practices_python(files: list[str], cwd: str) -> list[T0Violation]:
    """Check Python files against best-practices-python rules."""
    py_files = [f for f in files if f.endswith(".py")]
    violations = []

    for f in py_files:
        fpath = Path(cwd) / f
        if not fpath.exists():
            continue
        try:
            lines = fpath.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue

        for line_num, line in enumerate(lines, 1):
            for pattern, rule, message, severity in _BP_PYTHON_PATTERNS:
                if re.search(pattern, line):
                    violations.append(T0Violation(
                        rule=rule,
                        severity=severity,
                        file=f,
                        line=line_num,
                        message=message,
                        source="best-practices-python",
                    ))

        # Check for module docstring
        if lines and not _has_module_docstring(lines):
            violations.append(T0Violation(
                rule="bp-python-module-docstring",
                severity="minor",
                file=f,
                message="Missing module-level docstring",
                source="best-practices-python",
            ))

    return violations


def _has_module_docstring(lines: list[str]) -> bool:
    """Check if file starts with a docstring (after comments/blank lines)."""
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith('"""') or stripped.startswith("'''"):
            return True
        if stripped.startswith("from __future__"):
            continue
        return False
    return False


# ── best-practices-d3 checks (TSX/TS files) ────────────────────────

_BP_D3_PATTERNS = [
    (r"\.on\(['\"]mouse", "bp-d3-pointer-events", "Use pointer events, not mouse events", "minor"),
    (r"(width|height)\s*[:=]\s*\d{3,}", "bp-d3-hardcoded-dims", "Avoid hardcoded dimensions", "minor"),
    (r"\.duration\(\d{4,}\)", "bp-d3-long-transition", "Transition duration >999ms is too long", "info"),
]


def run_best_practices_d3(files: list[str], cwd: str) -> list[T0Violation]:
    """Check D3 anti-patterns in TSX/TS files."""
    d3_files = [f for f in files if f.endswith((".tsx", ".ts", ".jsx", ".js"))]
    violations = []

    for f in d3_files:
        fpath = Path(cwd) / f
        if not fpath.exists():
            continue
        try:
            lines = fpath.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue

        for line_num, line in enumerate(lines, 1):
            for pattern, rule, message, severity in _BP_D3_PATTERNS:
                if re.search(pattern, line):
                    violations.append(T0Violation(
                        rule=rule,
                        severity=severity,
                        file=f,
                        line=line_num,
                        message=message,
                        source="best-practices-d3",
                    ))

    return violations


# ── best-practices-skills checks (SKILL.md structure) ──────────────

def run_best_practices_skills(files: list[str], cwd: str) -> list[T0Violation]:
    """Check SKILL.md files for required frontmatter fields."""
    skill_files = [f for f in files if f.endswith("SKILL.md")]
    violations = []

    for f in skill_files:
        fpath = Path(cwd) / f
        if not fpath.exists():
            continue
        try:
            content = fpath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        if not content.startswith("---"):
            violations.append(T0Violation(
                rule="bp-skills-frontmatter",
                severity="major",
                file=f,
                message="SKILL.md must start with YAML frontmatter (---)",
                source="best-practices-skills",
            ))
            continue

        # Check required fields
        frontmatter = content.split("---")[1] if "---" in content else ""
        for field in ["name:", "description:", "triggers:"]:
            if field not in frontmatter:
                violations.append(T0Violation(
                    rule=f"bp-skills-missing-{field.rstrip(':')}",
                    severity="major",
                    file=f,
                    message=f"SKILL.md frontmatter missing required field: {field.rstrip(':')}",
                    source="best-practices-skills",
                ))

    return violations


# ── Aggregate runner ────────────────────────────────────────────────

ALL_VALIDATORS = [
    ("compile", run_compile_check),
    ("ruff", run_ruff),
    ("file-limits", run_file_limits),
    ("best-practices-python", run_best_practices_python),
    ("best-practices-d3", run_best_practices_d3),
    ("best-practices-skills", run_best_practices_skills),
]


def run_all_validators(files: list[str], cwd: str) -> list[T0Violation]:
    """Run all T0 validators and return combined violations."""
    all_violations = []
    for name, validator in ALL_VALIDATORS:
        try:
            violations = validator(files, cwd)
            if violations:
                logger.info(f"T0 {name}: {len(violations)} violation(s)")
            all_violations.extend(violations)
        except Exception as exc:
            logger.warning(f"T0 {name} failed: {exc}")
    return all_violations
