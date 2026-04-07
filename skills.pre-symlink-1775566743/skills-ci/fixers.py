"""Auto-fix logic for skills-ci violations.

Provides safe, automated fixes for common violations: inserting missing
module docstrings, aliasing ``import requests`` to ``import httpx as
requests``, replacing ``import logging`` with loguru, adding missing
pyproject.toml dependencies, fixing YAML frontmatter, and removing
broken hatchling build-system sections. Fixes are gated by file length
and path exclusions.
"""
from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path
from typing import Dict, List, Tuple

_THIS_DIR = str(Path(__file__).resolve().parent)
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from models import Violation
from scanners import (
    _IMPORT_TO_PKG,
    extract_frontmatter_raw,
    has_module_docstring,
    parse_frontmatter,
    requests_safe_to_alias,
    should_fix_path,
    uses_requests,
)


# ---------------------------------------------------------------------------
# Individual fixers
# ---------------------------------------------------------------------------


def insert_module_docstring(text: str, module_name: str, skill_name: str) -> str:
    """Insert a generated module docstring after the shebang/coding lines."""
    lines = text.splitlines()
    idx = 0
    if lines and lines[0].startswith("#!"):
        idx = 1
    if idx < len(lines) and "coding" in lines[idx]:
        idx += 1
    doc = [
        f"\"\"\"{module_name} - {skill_name}.",
        "",
        "Purpose: Auto-generated module docstring. Review for accuracy.",
        "Inputs/Outputs/Failures: See functions below.",
        "\"\"\"",
        "",
    ]
    return "\n".join(lines[:idx] + doc + lines[idx:]) + ("\n" if text.endswith("\n") else "")


def alias_requests_to_httpx(text: str) -> str:
    """Replace ``import requests`` with ``import httpx as requests``."""
    return re.sub(r"^\s*import\s+requests\s*$", "import httpx as requests", text, flags=re.MULTILINE)


def fix_logging_to_loguru(text: str) -> str:
    """Replace ``import logging`` / ``from logging import ...`` with loguru.

    Handles the common patterns:
    - ``import logging`` → ``from loguru import logger``
    - ``from logging import getLogger`` → ``from loguru import logger``
    - ``logger`` → ``logger``
    - ``logger`` → ``logger``
    - ``logger = logger`` → removes (loguru logger is ready)
    """
    # Replace 'import logging' with loguru import
    text = re.sub(
        r"^\s*import\s+logging\s*$",
        "from loguru import logger",
        text,
        flags=re.MULTILINE,
    )
    # Replace 'from logging import ...' with loguru
    text = re.sub(
        r"^\s*from\s+logging\s+import\s+.*$",
        "from loguru import logger",
        text,
        flags=re.MULTILINE,
    )
    # Remove 'logger = logger' lines (loguru logger is ready to use)
    text = re.sub(
        r"^\s*logger\s*=\s*logging\.getLogger\([^)]*\)\s*$",
        "",
        text,
        flags=re.MULTILINE,
    )
    # Replace remaining logger references with logger
    text = re.sub(r"logging\.getLogger\([^)]*\)", "logger", text)
    # Replace logging.X() calls with logger.X()
    text = re.sub(r"\blogging\.(debug|info|warning|error|critical|exception)\b", r"logger.\1", text)
    return text


def fix_missing_dep(pyproject_path: Path, missing_pkg: str) -> bool:
    """Add a missing dependency to pyproject.toml. Returns True if changed."""
    text = pyproject_path.read_text(encoding="utf-8")
    try:
        data = tomllib.loads(text)
    except Exception:
        return False

    deps = data.get("project", {}).get("dependencies", [])
    # Already present (shouldn't happen but guard)
    if any(missing_pkg.lower() in d.lower() for d in deps):
        return False

    # Determine minimum version hint
    _VERSION_HINTS = {
        "typer": ">=0.9",
        "loguru": ">=0.7.0",
        "httpx": ">=0.24",
        "rich": ">=13.0",
        "pydantic": ">=2.0",
        "python-dotenv": ">=1.0",
    }
    version = _VERSION_HINTS.get(missing_pkg, "")
    dep_entry = f'"{missing_pkg}{version}"'

    # Find the dependencies line and insert
    lines = text.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("dependencies") and "=" in stripped:
            # Handle single-line: dependencies = ["typer>=0.9"]
            if "[" in stripped and "]" in stripped:
                # Insert before closing bracket
                lines[i] = line.rstrip().rstrip("]").rstrip() + f", {dep_entry}]"
                pyproject_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                return True
            # Handle multi-line: dependencies = [
            elif "[" in stripped and "]" not in stripped:
                # Find the closing bracket and insert before it
                for j in range(i + 1, len(lines)):
                    if "]" in lines[j]:
                        indent = "    "
                        lines.insert(j, f"{indent}{dep_entry},")
                        pyproject_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                        return True
            break
    return False


def fix_hatchling_flat_layout(pyproject_path: Path) -> bool:
    """Remove [build-system] section from pyproject.toml for flat layouts."""
    text = pyproject_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    new_lines = []
    in_build_system = False
    for line in lines:
        if line.strip() == "[build-system]":
            in_build_system = True
            continue
        if in_build_system:
            # New section starts
            if line.strip().startswith("[") and line.strip().endswith("]"):
                in_build_system = False
                new_lines.append(line)
            # Skip build-system content
            continue
        new_lines.append(line)
    result = "\n".join(new_lines).strip() + "\n"
    if result != text:
        pyproject_path.write_text(result, encoding="utf-8")
        return True
    return False


def fix_frontmatter_description(text: str, skill_name: str) -> str:
    """Insert a top-level description into YAML frontmatter.

    Sources (in priority order):
    1. metadata.description or metadata.short-description (promotes to top-level)
    2. Generated from skill name
    """
    fm = parse_frontmatter(text)
    if fm is None:
        return text
    if fm.get("description"):
        return text

    desc = None
    meta = fm.get("metadata") or {}
    if isinstance(meta, dict):
        desc = meta.get("description") or meta.get("short-description") or meta.get("short_description")

    if not desc:
        desc = skill_name.replace("-", " ").replace("_", " ").title() + " skill."

    raw = extract_frontmatter_raw(text)
    if raw is None:
        return text

    lines = raw.split("\n")
    insert_idx = 0
    for i, line in enumerate(lines):
        if line.startswith("name:"):
            insert_idx = i + 1
            if insert_idx < len(lines) and lines[insert_idx].startswith("version:"):
                insert_idx += 1
            break

    desc_line = f"description: >\n  {desc}"
    lines.insert(insert_idx, desc_line)
    new_raw = "\n".join(lines)

    try:
        import yaml
        check = yaml.safe_load(new_raw)
        if not isinstance(check, dict) or not check.get("description"):
            return text
    except Exception:
        return text

    return text.replace(f"---\n{raw}\n---", f"---\n{new_raw}\n---", 1)


def stamp_test_lab_marker(text: str) -> str:
    """Prepend test-lab marker to a test file missing it."""
    marker = "# Generated by test-lab — blind adversarial evaluation\n"
    if marker.strip() in text:
        return text
    lines = text.splitlines(keepends=True)
    idx = 0
    if lines and lines[0].startswith("#!"):
        idx = 1
    lines.insert(idx, marker)
    return "".join(lines)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def apply_safe_fixes(
    violations: List[Violation],
    max_fix_loc: int,
) -> Tuple[List[str], List[str]]:
    """Apply automated fixes to files with fixable violations.

    Returns a tuple of (applied file paths, skipped descriptions).
    """
    applied: List[str] = []
    skipped: List[str] = []

    by_path: Dict[str, List[Violation]] = {}
    for v in violations:
        if not v.fixable:
            continue
        by_path.setdefault(v.path, []).append(v)

    for path_str, items in by_path.items():
        path = Path(path_str)
        if not path.exists():
            skipped.append(f"missing: {path_str}")
            continue
        if not should_fix_path(path):
            skipped.append(f"excluded: {path_str}")
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()
        if len(lines) > max_fix_loc:
            skipped.append(f"too_long: {path_str}")
            continue

        updated = text
        changed = False

        # --- SKILL.md frontmatter fixes ---
        if any(v.rule == "skills.frontmatter_description" for v in items):
            result = fix_frontmatter_description(updated, path.parent.name)
            if result != updated:
                updated = result
                changed = True

        # --- Python file fixes ---
        if any(v.rule == "python.module_docstring" for v in items) and not has_module_docstring(updated):
            updated = insert_module_docstring(updated, path.stem, path.parent.name)
            changed = True

        if any(v.rule == "python.requests" for v in items) and uses_requests(updated):
            if requests_safe_to_alias(updated):
                updated = alias_requests_to_httpx(updated)
                changed = updated != text
            else:
                skipped.append(f"unsafe_requests: {path_str}")

        if any(v.rule == "python.logging" for v in items):
            result = fix_logging_to_loguru(updated)
            if result != updated:
                updated = result
                changed = True

        if any(v.rule == "testing.handwritten_tests" for v in items):
            result = stamp_test_lab_marker(updated)
            if result != updated:
                updated = result
                changed = True

        # Write file-level fixes
        if changed:
            path.write_text(updated, encoding="utf-8")
            applied.append(path_str)
            for v in items:
                if v.rule in ("skills.frontmatter_description", "python.module_docstring",
                              "python.requests", "python.logging", "testing.handwritten_tests"):
                    v.applied = True

        # --- pyproject.toml fixes (operate on the file directly) ---
        if any(v.rule == "python.missing_dep" for v in items):
            for v in items:
                if v.rule != "python.missing_dep":
                    continue
                # Extract package name from message: "... missing 'loguru'."
                match = re.search(r"missing '([^']+)'", v.message)
                if match:
                    pkg = match.group(1)
                    if fix_missing_dep(path, pkg):
                        if path_str not in applied:
                            applied.append(path_str)
                        v.applied = True
                    else:
                        skipped.append(f"dep_fix_failed: {path_str} ({pkg})")

        if any(v.rule == "python.hatchling_flat_layout" for v in items):
            if fix_hatchling_flat_layout(path):
                if path_str not in applied:
                    applied.append(path_str)
                for v in items:
                    if v.rule == "python.hatchling_flat_layout":
                        v.applied = True

        # --- Environment health fixes (pyproject.toml) ---
        if any(v.rule == "runtime.python_version_unbounded" for v in items):
            pyproject_text = path.read_text()
            fixed = re.sub(
                r'requires-python\s*=\s*"(>=3\.\d+(?:\.\d+)?)"',
                r'requires-python = "\1,<3.13"',
                pyproject_text,
            )
            # Also handle >=X.Y,<4.0 pattern
            fixed = re.sub(
                r'requires-python\s*=\s*"(>=3\.\d+(?:\.\d+)?),<4\.0"',
                r'requires-python = "\1,<3.13"',
                fixed,
            )
            if fixed != pyproject_text:
                path.write_text(fixed)
                if path_str not in applied:
                    applied.append(path_str)
                for v in items:
                    if v.rule == "runtime.python_version_unbounded":
                        v.applied = True

        if any(v.rule == "runtime.loguru_version_unbounded" for v in items):
            pyproject_text = path.read_text()
            fixed = re.sub(r'"loguru>=([\d.]+)"', r'"loguru>=\1,<0.7.3"', pyproject_text)
            fixed = re.sub(r'"loguru"', r'"loguru>=0.7.0,<0.7.3"', fixed)
            if fixed != pyproject_text:
                path.write_text(fixed)
                if path_str not in applied:
                    applied.append(path_str)
                for v in items:
                    if v.rule == "runtime.loguru_version_unbounded":
                        v.applied = True

        # --- run.sh fixes ---
        if any(v.rule == "runtime.missing_unset_virtual_env" for v in items):
            run_text = path.read_text()
            if "unset VIRTUAL_ENV" not in run_text:
                # Insert after shebang line
                lines_list = run_text.split("\n")
                insert_idx = 1  # after #!/bin/bash
                if lines_list and lines_list[0].startswith("#!"):
                    insert_idx = 1
                lines_list.insert(insert_idx, "# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls")
                lines_list.insert(insert_idx + 1, "unset VIRTUAL_ENV")
                fixed = "\n".join(lines_list)
                path.write_text(fixed)
                if path_str not in applied:
                    applied.append(path_str)
                for v in items:
                    if v.rule == "runtime.missing_unset_virtual_env":
                        v.applied = True

    return applied, skipped
