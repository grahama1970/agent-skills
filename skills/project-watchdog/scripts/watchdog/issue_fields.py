"""Parsing and validation of watchdog directives embedded in GitHub issue bodies.

Purpose
    Turn untrusted issue-body text into validated dispatch inputs, or refuse.

Inputs
    Raw issue body text containing shell-style ``key=value`` tokens, and the
    project worktree the referenced paths must stay inside.

Outputs
    A ``dict[str, str]`` of fields, plus typed accessors that raise on bad input.

Failure modes
    All validators raise ``ValueError`` with the offending value included.
    ``repo_relative_existing_path`` refuses absolute paths, ``..`` traversal, and
    symlinks that escape the worktree — an issue body is attacker-controlled
    input, so path containment is a security boundary, not a convenience check.
"""

from __future__ import annotations

import shlex
from pathlib import Path, PurePosixPath


def parse_issue_fields(body: str) -> dict[str, str]:
    """Extract shell-style ``key=value`` fields from a GitHub issue body."""
    fields: dict[str, str] = {}
    try:
        tokens = shlex.split(body.replace("\r", " "))
    except ValueError as exc:
        raise ValueError(f"issue body is not shell-parseable: {exc}") from exc
    for token in tokens:
        key, sep, value = token.partition("=")
        if sep:
            fields[key.strip()] = value.strip()
    return fields


def repo_relative_existing_path(value: str, *, worktree: Path) -> Path:
    """Return a safe worktree-relative path, or raise ``ValueError``.

    Containment is checked after symlink resolution so a symlink inside the
    worktree cannot be used to reach a file outside it.
    """
    posix_path = PurePosixPath(value)
    if posix_path.is_absolute() or ".." in posix_path.parts:
        raise ValueError(f"path must be repo-relative without '..': {value}")
    resolved_root = worktree.resolve()
    candidate = (resolved_root / Path(value)).resolve()
    if not candidate.is_relative_to(resolved_root):
        raise ValueError(f"path escapes the project worktree: {value}")
    if not candidate.is_file():
        raise ValueError(f"path does not exist in {resolved_root}: {value}")
    return candidate


def parse_positive_int(value: str, *, field: str) -> int:
    if not value.isdecimal() or int(value) < 1:
        raise ValueError(f"{field} must be a positive integer: {value}")
    return int(value)


def parse_bool(value: str, *, field: str) -> bool:
    normalized = value.lower()
    if normalized not in {"true", "false"}:
        raise ValueError(f"{field} must be true or false: {value}")
    return normalized == "true"


def parse_goal_hash(value: str, *, field: str = "active_goal_hash") -> str:
    if not value.startswith("sha256:"):
        raise ValueError(f"{field} must start with 'sha256:': {value}")
    return value
