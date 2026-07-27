#!/usr/bin/env python3
"""Static guard against shell-style variables inside Python path literals.

Purpose
    Fail closed on the class of bug that silently disabled this watchdog's
    dispatch path: ``Path("${HOME}/workspace/...")``. Python never expands
    ``${HOME}``, so such a value is a *relative* path literally containing the
    characters ``${HOME}`` — it resolves to nothing and every use of it fails.

Inputs
    One or more directories or files. Defaults to the ``scripts`` directory
    beside this file.

Outputs
    Prints one ``path:line: offending source`` line per violation and exits 1.
    Exits 0 when clean.

Failure modes
    Uses the AST rather than a text search, so prose that *describes* the
    anti-pattern in a docstring or comment is correctly ignored while real code
    is still caught. Files that cannot be parsed are reported as violations
    rather than skipped.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

PATH_FACTORIES = {"Path", "PurePath", "PurePosixPath", "PosixPath"}


def _is_path_call(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id in PATH_FACTORIES
    if isinstance(func, ast.Attribute):
        return func.attr in PATH_FACTORIES
    return False


def scan_file(path: Path) -> list[tuple[int, str]]:
    """Return ``(lineno, source)`` for every path literal holding a shell variable."""
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return [(exc.lineno or 0, f"unparseable: {exc.msg}")]
    lines = source.splitlines()
    violations: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _is_path_call(node):
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and "$" in arg.value:
                lineno = getattr(node, "lineno", 0)
                text = lines[lineno - 1].strip() if 0 < lineno <= len(lines) else ""
                violations.append((lineno, text))
    return violations


def scan(targets: list[Path]) -> int:
    files: list[Path] = []
    for target in targets:
        files.extend(sorted(target.rglob("*.py")) if target.is_dir() else [target])
    failures = 0
    for file_path in files:
        for lineno, text in scan_file(file_path):
            print(f"{file_path}:{lineno}: {text}")
            failures += 1
    if failures:
        print(
            f"\n{failures} path literal(s) contain a shell variable. "
            "Python does not expand these; use Path.home(), expanduser(), or an "
            "environment lookup instead.",
            file=sys.stderr,
        )
    return 1 if failures else 0


def main() -> int:
    args = sys.argv[1:]
    targets = [Path(a) for a in args] if args else [Path(__file__).resolve().parent]
    return scan(targets)


if __name__ == "__main__":
    raise SystemExit(main())
