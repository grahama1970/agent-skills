#!/usr/bin/env python3
"""Enforce repository file-size ceilings for Python and React logic files."""

from __future__ import annotations

import sys
from pathlib import Path


SKIP_PARTS = {
    ".ask_artifacts",
    ".venv",
    "__pycache__",
    "archive",
    "build",
    "deprecated",
    "dist",
    "node_modules",
}


def iter_files(root: Path):
    """Yield source files that participate in the size contract."""

    for path in root.rglob("*"):
        if not path.is_file() or any(part in SKIP_PARTS for part in path.parts):
            continue
        if path.suffix in {".py", ".ts", ".tsx"}:
            yield path


def limit_for(path: Path) -> int:
    """Return the applicable ceiling."""

    if path.suffix == ".py":
        return 800
    if "components" in path.parts and "ui" in path.parts:
        return 400
    return 400


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    violations: list[str] = []
    for path in iter_files(root):
        lines = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
        limit = limit_for(path)
        if lines > limit:
            violations.append(f"{path.relative_to(root)}: {lines} > {limit}")
    if violations:
        print("File-size violations:", file=sys.stderr)
        for violation in violations:
            print(f"  {violation}", file=sys.stderr)
        return 1
    print("file-size contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
