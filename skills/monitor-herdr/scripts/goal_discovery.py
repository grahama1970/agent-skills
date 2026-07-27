"""Immutable-goal discovery bounded to the pane project."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from loguru import logger


GOAL_FILE_NAMES = (
    "IMMUTABLE_GOAL.md",
    "GOAL.md",
    ".goal",
    ".codex/goal.json",
    ".codex/GOAL.md",
    ".tau/goal.json",
)


def discover_immutable_goal(cwd: str, *, boundary: Path | None = None) -> dict[str, Any]:
    if not cwd:
        return {"found": False, "source": None, "excerpt": ""}
    start = Path(cwd).expanduser()
    try:
        current = start.resolve()
    except OSError as exc:
        logger.error("Could not resolve cwd {} while discovering immutable goal: {}", cwd, exc)
        return {"found": False, "source": None, "excerpt": ""}
    stop_at = boundary.resolve() if boundary else current
    for root in [current, *current.parents]:
        if not root.is_relative_to(stop_at):
            break
        for name in GOAL_FILE_NAMES:
            path = root / name
            if not path.is_file():
                continue
            try:
                resolved_path = path.resolve()
            except OSError as exc:
                logger.error("Could not resolve immutable goal candidate {}: {}", path, exc)
                continue
            if not resolved_path.is_relative_to(stop_at):
                logger.error("Immutable goal candidate {} resolves outside boundary {}", path, stop_at)
                continue
            try:
                text = resolved_path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                logger.error("Could not read immutable goal candidate {}: {}", path, exc)
                continue
            return {"found": True, "source": str(resolved_path), "excerpt": compact_excerpt(text)}
        if root == stop_at or root == root.parent:
            break
    return {"found": False, "source": None, "excerpt": ""}


def compact_excerpt(text: str, limit: int = 700) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned[:limit]


def project_root_for_cwd(cwd: str, cwd_prefix: str) -> Path | None:
    try:
        current = Path(cwd).expanduser().resolve()
    except OSError:
        return None
    prefix = resolved_path(cwd_prefix)
    for root in [current, *current.parents]:
        if (root / ".git").exists():
            return root if prefix is None or root.is_relative_to(prefix) else prefix
        if prefix is not None and root == prefix:
            return current
    return current


def path_is_relative_to(child: str, parent: str) -> bool:
    child_path = resolved_path(child)
    parent_path = resolved_path(parent)
    return bool(child_path and parent_path and child_path.is_relative_to(parent_path))


def resolved_path(path: str) -> Path | None:
    try:
        return Path(path).expanduser().resolve()
    except OSError:
        return None
