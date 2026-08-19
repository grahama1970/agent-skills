#!/usr/bin/env python
"""Deterministic local conformance checks for the create-svg skill.

Inputs: one skill directory. Outputs: human-readable PASS/FAIL findings. Failure modes:
invalid frontmatter, missing evaluation posture, oversized or undocumented Python files,
unsafe Python patterns, incomplete dependencies, or a run.sh that bypasses uv isolation.
"""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path

import yaml

REQUIRED_FRONTMATTER = {"name", "description", "triggers", "provides", "composes", "complies"}
IMPORT_DISTRIBUTIONS = {
    "defusedxml": "defusedxml",
    "lxml": "lxml",
    "loguru": "loguru",
    "PIL": "pillow",
    "playwright": "playwright",
    "pydantic": "pydantic",
    "pytest": "pytest",
    "tinycss2": "tinycss2",
    "typer": "typer",
    "yaml": "pyyaml",
}
FRONTMATTER_GRAMMAR = re.compile(r"\A---\n(?P<body>.*?)\n---(?:\n|$)", re.DOTALL)


def _frontmatter(skill_md: Path) -> dict[str, object]:
    match = FRONTMATTER_GRAMMAR.match(skill_md.read_text(encoding="utf-8"))
    if not match:
        raise ValueError("SKILL.md must begin with standalone YAML frontmatter delimiters")
    parsed = yaml.safe_load(match.group("body"))
    if not isinstance(parsed, dict):
        raise ValueError("frontmatter must be a YAML mapping")
    return parsed


def _dependency_names(pyproject: Path) -> set[str]:
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    dependencies = data["project"].get("dependencies", [])
    dev = data.get("dependency-groups", {}).get("dev", [])
    names: set[str] = set()
    for item in [*dependencies, *dev]:
        name = re.split(r"[<>=!~\[ ;]", item, maxsplit=1)[0].strip().lower()
        names.add(name)
    return names


def _python_files(skill_dir: Path) -> tuple[Path, ...]:
    return tuple(
        path
        for path in sorted(skill_dir.rglob("*.py"))
        if not any(part in {".venv", "__pycache__"} for part in path.parts)
    )


def check(skill_dir: Path) -> list[str]:
    failures: list[str] = []
    skill_md = skill_dir / "SKILL.md"
    pyproject = skill_dir / "pyproject.toml"
    if not skill_md.exists():
        return ["missing SKILL.md"]
    if not pyproject.exists():
        return ["missing pyproject.toml"]

    frontmatter = _frontmatter(skill_md)
    missing = sorted(REQUIRED_FRONTMATTER - set(frontmatter))
    if missing:
        failures.append(f"missing frontmatter fields: {', '.join(missing)}")
    if frontmatter.get("name") != skill_dir.name:
        failures.append("frontmatter name must equal directory name")
    if "best-practices-skills" not in frontmatter.get("complies", []):
        failures.append("complies must include best-practices-skills")
    if "best-practices-python" not in frontmatter.get("complies", []):
        failures.append("complies must include best-practices-python")
    if "agentic-evals" not in frontmatter.get("composes", []):
        failures.append("composes must include agentic-evals")
    if not (skill_dir / "fixtures" / "agentic_eval.json").exists():
        failures.append("missing fixtures/agentic_eval.json")
    if (skill_dir / "CHANGELOG.md").exists():
        failures.append("CHANGELOG.md is not allowed in this skill")
    if len(skill_md.read_text(encoding="utf-8").splitlines()) > 500:
        failures.append("SKILL.md exceeds 500 lines")

    declared = _dependency_names(pyproject)
    imported_third_party: set[str] = set()
    for path in _python_files(skill_dir):
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()
        if len(lines) > 800:
            failures.append(f"{path.relative_to(skill_dir)} exceeds 800 lines")
        tree = ast.parse(source, filename=str(path))
        if ast.get_docstring(tree) is None:
            failures.append(f"{path.relative_to(skill_dir)} has no module docstring")
        if path.name == "__init__.py":
            if len(lines) > 20:
                failures.append(f"{path.relative_to(skill_dir)} exceeds 20 lines")
            allowed = (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign, ast.Expr)
            if any(not isinstance(node, allowed) for node in tree.body):
                failures.append(f"{path.relative_to(skill_dir)} contains business logic")
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_third_party.update(alias.name.split(".", 1)[0] for alias in node.names)
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                imported_third_party.add(node.module.split(".", 1)[0])
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
                failures.append(f"{path.relative_to(skill_dir)} uses {node.func.id}")
            if isinstance(node, ast.Call):
                for keyword in node.keywords:
                    if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                        failures.append(f"{path.relative_to(skill_dir)} uses shell=True")
        if re.search(r"(^|\n)\s*(import logging|from logging import)", source):
            failures.append(f"{path.relative_to(skill_dir)} imports stdlib logging instead of Loguru")
        if re.search(r"(^|\n)\s*(import requests|from requests import)", source):
            failures.append(f"{path.relative_to(skill_dir)} imports requests instead of httpx")

    for module, distribution in IMPORT_DISTRIBUTIONS.items():
        if module in imported_third_party and distribution not in declared:
            failures.append(f"pyproject.toml is missing dependency {distribution} for import {module}")

    run_sh = (skill_dir / "run.sh").read_text(encoding="utf-8")
    if 'uv run --project "$SCRIPT_DIR"' not in run_sh:
        failures.append("run.sh must execute through uv run --project")
    if re.search(r"\bpython3\b", run_sh):
        failures.append("run.sh contains a bare python3 invocation")
    return failures


def main() -> int:
    skill_dir = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    failures = check(skill_dir)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("PASS: best-practices-skills and best-practices-python local contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
