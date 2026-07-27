#!/usr/bin/env python3
"""Fail when mocked test files claim end-to-end or production-level proof."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

MOCK_MARKERS = (
    re.compile(r"\bFake[A-Z]\w*"),
    re.compile(r"\bAsyncMock\b"),
    re.compile(r"\bMagicMock\b"),
    re.compile(r"\bunittest\.mock\b"),
    re.compile(r"\bfrom unittest import mock\b"),
    re.compile(r"@patch\("),
    re.compile(r"subagent-command-fixture"),
    re.compile(r"\bmonkeypatch\b"),
)

FORBIDDEN_TEST_PATTERNS = (
    re.compile(r"end[_-]?to[_-]?end", re.IGNORECASE),
    re.compile(r"production[_-]?ready", re.IGNORECASE),
    re.compile(r"real[_-]?repair[_-]?loop", re.IGNORECASE),
    re.compile(r"gate[_-]?correctness", re.IGNORECASE),
    re.compile(r"receipt[_-]?integrity", re.IGNORECASE),
    re.compile(r"(?<![a-z_])proved(?![a-z_])", re.IGNORECASE),
    re.compile(r"(?<![a-z_])validated(?![a-z_])", re.IGNORECASE),
)

TEST_DEF = re.compile(r"^\s*def (test_\w+)\(", re.MULTILINE)


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


SKIP_DIR_NAMES = {".venv", "node_modules", "__pycache__", ".git"}


def _skip_path(path: Path) -> bool:
    return any(part in SKIP_DIR_NAMES for part in path.parts)


def iter_test_files(root: Path) -> list[Path]:
    patterns = (
        root / "skills",
        root / "scripts" / "tests",
    )
    files: list[Path] = []
    for base in patterns:
        if not base.exists():
            continue
        for path in sorted(base.rglob("test_*.py")):
            if _skip_path(path):
                continue
            files.append(path)
    return files


def uses_mocks(content: str) -> bool:
    return any(marker.search(content) for marker in MOCK_MARKERS)


def forbidden_claims(content: str) -> list[str]:
    claims: list[str] = []
    for match in TEST_DEF.finditer(content):
        name = match.group(1)
        if any(pattern.search(name) for pattern in FORBIDDEN_TEST_PATTERNS):
            claims.append(f"test name `{name}`")
    return claims


def check_file(path: Path) -> list[str]:
    content = path.read_text(encoding="utf-8")
    if not uses_mocks(content):
        return []
    claims = forbidden_claims(content)
    if not claims:
        return []
    detail = ", ".join(claims)
    return [
        f"{path}: mocked test file must not claim real proof ({detail}). "
        "Mocks prove wiring only; use live/sanity checks before claiming validated, "
        "end-to-end, or production-ready behavior."
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Optional test files or directories (default: skills/**/tests, scripts/tests)",
    )
    args = parser.parse_args(argv)

    if args.paths:
        files: list[Path] = []
        for path in args.paths:
            path = path.expanduser().resolve()
            if path.is_dir():
                files.extend(sorted(path.rglob("test_*.py")))
            elif path.is_file():
                files.append(path)
    else:
        files = iter_test_files(repo_root())

    violations: list[str] = []
    for path in files:
        violations.extend(check_file(path))

    if violations:
        print("Mock evidence claim violations:", file=sys.stderr)
        for line in violations:
            print(line, file=sys.stderr)
        return 1

    print(f"OK: checked {len(files)} test file(s); no mock+proof claim violations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
