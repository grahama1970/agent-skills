#!/usr/bin/env python3
"""Static preflight for the $loop skill project.

This script deliberately avoids calling Codex. It checks that the reusable loop
surface is installed and that the expected project-scoped custom agents exist.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

EXPECTED_FILES = [
    ".agents/skills/loop/SKILL.md",
    ".agents/skills/loop/scripts/validate_loop_receipt.py",
    ".agents/skills/loop/scripts/check_changed_files.py",
    ".agents/skills/loop/scripts/capture_attempt_artifacts.py",
    ".agents/skills/loop/scripts/render_cron.py",
    ".agents/skills/loop/scripts/loop_cron_runner.sh",
    ".codex/config.toml",
    ".codex/agents/explorer.toml",
    ".codex/agents/coder.toml",
    ".codex/agents/technical-writer.toml",
    ".codex/agents/code-reviewer.toml",
]
EXPECTED_AGENT_NAMES = {
    ".codex/agents/explorer.toml": "explorer",
    ".codex/agents/coder.toml": "coder",
    ".codex/agents/technical-writer.toml": "technical-writer",
    ".codex/agents/code-reviewer.toml": "code-reviewer",
}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_toml_name(text: str) -> str | None:
    match = re.search(r'^\s*name\s*=\s*"([^"]+)"\s*$', text, re.MULTILINE)
    return match.group(1) if match else None


def parse_toml_int(text: str, key: str) -> int | None:
    match = re.search(rf'^\s*{re.escape(key)}\s*=\s*(\d+)\s*$', text, re.MULTILINE)
    return int(match.group(1)) if match else None


def git_status(repo: Path) -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "status", "--short"],
            cwd=repo,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError:
        return ["git not available"]
    if proc.returncode != 0:
        return [f"git status failed: {proc.stderr.strip() or proc.stdout.strip()}"]
    return [line for line in proc.stdout.splitlines() if line.strip()]


def check(repo: Path, require_clean: bool) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    for rel in EXPECTED_FILES:
        if not (repo / rel).exists():
            errors.append(f"missing required file: {rel}")

    for rel, expected_name in EXPECTED_AGENT_NAMES.items():
        path = repo / rel
        if path.exists():
            actual = parse_toml_name(read(path))
            if actual != expected_name:
                errors.append(f"{rel}: expected name={expected_name!r}, found {actual!r}")

    config = repo / ".codex/config.toml"
    if config.exists():
        text = read(config)
        max_depth = parse_toml_int(text, "max_depth")
        max_threads = parse_toml_int(text, "max_threads")
        if max_depth is None:
            warnings.append(".codex/config.toml: agents.max_depth not found; default may be okay but explicit 1 is recommended")
        elif max_depth != 1:
            warnings.append(f".codex/config.toml: agents.max_depth={max_depth}; 1 is recommended for predictable direct-child loops")
        if max_threads is not None and max_threads < 3:
            warnings.append(f".codex/config.toml: agents.max_threads={max_threads}; at least 3 is useful for parent + children")

    status = git_status(repo)
    dirty_lines = [s for s in status if not s.startswith("git ")]
    if require_clean and dirty_lines:
        errors.append("working tree is dirty; start from a clean worktree or record the dirty-state exception")
    elif dirty_lines:
        warnings.append(f"working tree has {len(dirty_lines)} changed/untracked path(s); loop must preserve unrelated changes")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "repo": str(repo),
        "expected_agents": list(EXPECTED_AGENT_NAMES.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight-check a repository for the $loop skill.")
    parser.add_argument("--repo", default=".", help="Repository root to check")
    parser.add_argument("--require-clean", action="store_true", help="Fail when git status is not clean")
    parser.add_argument("--print-json", action="store_true", help="Print JSON instead of text")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    result = check(repo, args.require_clean)

    if args.print_json:
        print(json.dumps(result, indent=2))
    else:
        print("LOOP DOCTOR PASS" if result["ok"] else "LOOP DOCTOR FAIL")
        for err in result["errors"]:
            print(f"ERROR: {err}", file=sys.stderr)
        for warning in result["warnings"]:
            print(f"WARNING: {warning}", file=sys.stderr)

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
