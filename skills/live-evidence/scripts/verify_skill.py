#!/usr/bin/env python3
"""Validate Live Evidence skill structure and Python house rules."""

from __future__ import annotations

import ast
import py_compile
import sys
from pathlib import Path

import yaml


REQUIRED_FRONTMATTER = {"name", "description", "triggers", "provides", "composes", "complies"}
REQUIRED_COMPLIANCE = {
    "best-practices-skills",
    "best-practices-python",
    "best-practices-react",
}
REQUIRED_COMPOSITION = {"agentic-evals"}
FORBIDDEN_SOURCE = {
    "shell=True": "subprocess shell execution",
    "import requests": "requests dependency",
    "from requests": "requests dependency",
    "sys.path.insert": "runtime import path surgery",
    "eval(": "dynamic eval",
    "exec(": "dynamic exec",
    "from arango": "direct ArangoDB access",
    "qdrant_client": "direct Qdrant access",
}


def parse_frontmatter(path: Path) -> dict:
    """Parse standalone YAML frontmatter from SKILL.md."""

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("SKILL.md must start with standalone ---")
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise ValueError("SKILL.md frontmatter is not closed") from exc
    payload = yaml.safe_load("\n".join(lines[1:end]))
    if not isinstance(payload, dict):
        raise ValueError("frontmatter must be a YAML object")
    return payload


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    problems: list[str] = []
    try:
        frontmatter = parse_frontmatter(root / "SKILL.md")
    except (OSError, ValueError, yaml.YAMLError) as exc:
        problems.append(str(exc))
        frontmatter = {}
    missing = REQUIRED_FRONTMATTER - set(frontmatter)
    if missing:
        problems.append(f"frontmatter missing: {sorted(missing)}")
    compliance = set(frontmatter.get("complies") or [])
    if not REQUIRED_COMPLIANCE.issubset(compliance):
        problems.append(f"complies missing: {sorted(REQUIRED_COMPLIANCE - compliance)}")
    composition = set(frontmatter.get("composes") or [])
    if not REQUIRED_COMPOSITION.issubset(composition):
        problems.append(f"composes missing: {sorted(REQUIRED_COMPOSITION - composition)}")

    for path in sorted((root / "src").rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            problems.append(f"{path.relative_to(root)}: syntax error {exc}")
            continue
        if not ast.get_docstring(tree):
            problems.append(f"{path.relative_to(root)}: missing module docstring")
        for needle, label in FORBIDDEN_SOURCE.items():
            if needle in source:
                problems.append(f"{path.relative_to(root)}: forbidden {label}")
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            problems.append(f"{path.relative_to(root)}: compile failed {exc}")

    heavy = {"node_modules", ".venv", "models", "outputs", "artifacts", "sessions"}
    for candidate in root.rglob("*"):
        if candidate.name not in heavy or candidate.is_symlink() or not candidate.is_dir():
            continue
        problems.append(
            f"heavy runtime directory present in source tree: {candidate.relative_to(root)}"
        )

    if problems:
        print("skill contract violations:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    print("skill structure and Python contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
