"""Check Python source files for the repo line-count policy.

Inputs: the current working tree, scanned recursively for ``*.py`` files.
Outputs: a human-readable pass/fail summary on stdout.
Failure modes: returns 2 when any non-generated Python file exceeds 800 lines.
"""

from __future__ import annotations

import sys
from pathlib import Path

MAX_LINES = 800


def count_lines(p: Path) -> int:
    # Count physical lines (simple, deterministic)
    return len(p.read_text(encoding="utf-8", errors="replace").splitlines())


def main() -> int:
    root = Path.cwd()
    offenders: list[tuple[Path, int]] = []

    for p in root.rglob("*.py"):
        if any(part in {".venv", "venv", "__pycache__", "dist", "build"} for part in p.parts):
            continue
        n = count_lines(p)
        if n > MAX_LINES:
            offenders.append((p, n))

    if offenders:
        print(f"ERROR: {len(offenders)} Python files exceed {MAX_LINES} lines:")
        for p, n in sorted(offenders, key=lambda x: x[1], reverse=True):
            print(f"  - {p} ({n} lines)")
        return 2

    print(f"OK: no .py files exceed {MAX_LINES} lines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
