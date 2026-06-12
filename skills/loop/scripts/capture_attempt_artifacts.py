#!/usr/bin/env python3
"""Capture attempt diff artifacts for a $loop run."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from check_changed_files import read_files_from_git


def run_git(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def exclude_loop_artifacts(paths: list[str]) -> list[str]:
    return [p for p in paths if not (p == ".loop" or p.startswith(".loop/"))]


def write_changed_files(out_dir: Path, paths: list[str]) -> None:
    text = "".join(f"{path}\n" for path in paths)
    (out_dir / "changed-files.txt").write_text(text, encoding="utf-8")


def git_diff(args: list[str]) -> str:
    proc = run_git(args)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout


def untracked_file_diff(path: str) -> str:
    proc = run_git(["diff", "--no-index", "--", "/dev/null", path])
    if proc.returncode not in (0, 1):
        raise RuntimeError(proc.stderr.strip() or f"git diff --no-index failed for {path}")
    return proc.stdout


def write_diff_patch(out_dir: Path, paths: list[str]) -> None:
    untracked = set(read_git_names(["ls-files", "--others", "--exclude-standard"]))
    tracked_paths = [p for p in paths if p not in untracked]
    diff_parts: list[str] = []

    if tracked_paths:
        diff_parts.append(git_diff(["diff", "--no-renames", "--", *tracked_paths]))
        diff_parts.append(git_diff(["diff", "--cached", "--no-renames", "--", *tracked_paths]))

    for path in paths:
        if path in untracked:
            diff_parts.append(untracked_file_diff(path))

    (out_dir / "diff.patch").write_text("".join(diff_parts), encoding="utf-8")


def read_git_names(args: list[str]) -> list[str]:
    proc = run_git(args)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture changed-files.txt and diff.patch for one loop attempt.")
    parser.add_argument("--out-dir", required=True, help="Attempt artifact directory.")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        paths = exclude_loop_artifacts(read_files_from_git(base_ref=None, include_untracked=True))
        write_changed_files(out_dir, paths)
        write_diff_patch(out_dir, paths)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: could not capture attempt artifacts: {exc}", file=sys.stderr)
        return 2

    print(f"CAPTURED ATTEMPT ARTIFACTS ({len(paths)} file(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
