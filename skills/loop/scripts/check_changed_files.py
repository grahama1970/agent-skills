#!/usr/bin/env python3
"""Check changed file paths against allow/deny globs."""
from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
from pathlib import PurePosixPath

DEFAULT_EXCLUDES = (
    ".loop/**",
    "**/__pycache__/**",
    "**/*.pyc",
    "**/*.pyo",
)


def safe_rel(path: str) -> bool:
    p = PurePosixPath(path.replace("\\", "/"))
    return bool(path) and not p.is_absolute() and ".." not in p.parts


def match_any(path: str, patterns: list[str]) -> bool:
    normalized = path.replace("\\", "/")
    return any(fnmatch.fnmatch(normalized, p) for p in patterns)


def read_git_names(args: list[str]) -> list[str]:
    proc = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"{' '.join(args)} failed")
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def read_files_from_git(base_ref: str | None, include_untracked: bool = True) -> list[str]:
    diff_cmd = ["git", "diff", "--no-renames", "--name-only"]
    cached_cmd = ["git", "diff", "--cached", "--no-renames", "--name-only"]
    if base_ref:
        diff_cmd.append(base_ref)
        cached_cmd.append(base_ref)

    files = read_git_names(diff_cmd)
    files.extend(read_git_names(cached_cmd))
    if include_untracked:
        files.extend(read_git_names(["git", "ls-files", "--others", "--exclude-standard"]))

    return sorted(dict.fromkeys(files))


def read_files_from_file(path: str) -> list[str]:
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify changed files are within allowed scope.")
    parser.add_argument("--include", action="append", default=[], help="Allowed glob. Repeatable.")
    parser.add_argument("--exclude", action="append", default=[], help="Forbidden glob. Repeatable.")
    parser.add_argument("--from-file", help="Read changed paths from a newline-delimited file instead of git diff.")
    parser.add_argument("--base-ref", help="Optional ref passed to git diff --name-only <base-ref>.")
    parser.add_argument(
        "--tracked-only",
        action="store_true",
        help="Only inspect tracked git diff paths; by default untracked files are included too.",
    )
    args = parser.parse_args()

    if not args.include:
        print("ERROR: at least one --include glob is required", file=sys.stderr)
        return 2

    try:
        files = read_files_from_file(args.from_file) if args.from_file else read_files_from_git(args.base_ref, not args.tracked_only)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: could not read changed files: {exc}", file=sys.stderr)
        return 2

    violations = []
    checked_files = []
    for f in files:
        if not safe_rel(f):
            violations.append((f, "not a safe relative path"))
        elif match_any(f, list(DEFAULT_EXCLUDES)):
            continue
        elif args.exclude and match_any(f, args.exclude):
            violations.append((f, "matches excluded pattern"))
        elif not match_any(f, args.include):
            violations.append((f, "does not match allowed include patterns"))
        else:
            checked_files.append(f)

    if violations:
        print("CHANGED FILE SCOPE INVALID", file=sys.stderr)
        for f, reason in violations:
            print(f"- {f}: {reason}", file=sys.stderr)
        return 1

    print(f"CHANGED FILE SCOPE VALID ({len(checked_files)} file(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
