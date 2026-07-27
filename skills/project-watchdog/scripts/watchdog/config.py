"""Filesystem paths, routing markers, and environment resolution for project-watchdog.

Purpose
    Single source of truth for every path and constant the watchdog touches, so
    no other module hardcodes a location or re-derives one from ``$HOME``.

Inputs
    Environment variables, all optional:

    ``PROJECT_WATCHDOG_STATE_ROOT``
        Overrides the durable state root (default ``~/.local/state/project-watchdog``).
        Tests set this to a temporary directory to keep real receipts untouched.
    ``PROJECT_WATCHDOG_WORKSPACE``
        Overrides the workspace root that holds project worktrees
        (default ``~/workspace/experiments``).
    ``UV_BIN``
        Overrides the ``uv`` executable path (default ``~/.local/bin/uv``,
        falling back to whatever ``uv`` resolves to on ``PATH``).

Outputs
    Module-level ``Path`` constants. Every path is absolute and fully expanded.

Failure modes
    ``resolve_uv_bin`` returns the bare string ``"uv"`` when no executable is
    found, deferring the failure to the subprocess call so the resulting receipt
    records a real exit code instead of raising during import.

History
    Until 2026-07-27 this module's constants were written as
    ``Path("${HOME}/workspace/...")``. Python does not expand ``${HOME}``, so
    every such path was a *relative* path literally named ``${HOME}/...`` and
    none of them existed. Any dispatch would have failed. Use ``expanduser()``
    or the helpers here, never a shell-style variable inside ``Path(...)``.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from .dotenv_helper import get as env_get
from .dotenv_helper import load_env

load_env()

SKILL_DIR = Path(__file__).resolve().parents[2]
REGISTRY_DIR = SKILL_DIR / "registry"
PROJECTS_PATH = REGISTRY_DIR / "projects.json"
STATE_PATH = REGISTRY_DIR / "state.json"


def _env_path(name: str, default: Path) -> Path:
    raw = env_get(name)
    if not raw:
        return default
    return Path(raw).expanduser().resolve()


def state_root() -> Path:
    """Return the durable state root, honouring ``PROJECT_WATCHDOG_STATE_ROOT``."""
    return _env_path(
        "PROJECT_WATCHDOG_STATE_ROOT",
        Path.home() / ".local" / "state" / "project-watchdog",
    )


def log_dir() -> Path:
    return state_root() / "logs"


def receipt_root() -> Path:
    return state_root() / "receipts"


def lock_dir() -> Path:
    return state_root() / "lock"


def event_log_path() -> Path:
    return log_dir() / "project-watchdog.log"


def cron_log_path() -> Path:
    return log_dir() / "cron.log"


def workspace_root() -> Path:
    """Return the root directory that contains project worktrees."""
    return _env_path(
        "PROJECT_WATCHDOG_WORKSPACE",
        Path.home() / "workspace" / "experiments",
    )


def resolve_uv_bin() -> str:
    """Return the ``uv`` executable path, or the bare name if none is found."""
    override = env_get("UV_BIN")
    if override:
        candidate = Path(override).expanduser()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    default = Path.home() / ".local" / "bin" / "uv"
    if default.is_file() and os.access(default, os.X_OK):
        return str(default)
    found = shutil.which("uv")
    return found or "uv"


def agents_root() -> Path:
    return workspace_root() / "agent-skills" / "agents"


CRON_MARKER = "# project-watchdog global issue cron"
TAU_REPAIR_MARKER = "project-watchdog-action:add-tau-coder-command-spec"
TAU_HANDOFF_DISPATCH_MARKER = "project-watchdog-action:tau-handoff-dispatch"
TAU_ACTIVE_GOAL_HASH = "sha256:" + "1" * 64

LEASE_LABEL = "agent-active"
BLOCKED_LABEL = "agent-blocked"
DONE_LABEL = "agent-done"
READY_LABEL = "agent-work"

#: A lock older than this is treated as abandoned by a crashed or killed tick.
LOCK_STALE_SECONDS = 900
