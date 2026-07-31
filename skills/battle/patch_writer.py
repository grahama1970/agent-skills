"""Compatibility re-export for legacy Battle patch-writer imports."""

from __future__ import annotations

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from battle_skill.patch_writer import (  # noqa: E402
    _ensure_git_repo,
    _resolve_code_runner_run,
    write_patch,
)

__all__ = ["_ensure_git_repo", "_resolve_code_runner_run", "write_patch"]
