"""Single, idempotent ``.env`` load for every module that reads the environment.

Purpose
    The watchdog runs from cron, where the shell profile is not sourced and the
    environment is nearly empty. Any operator override — ``UV_BIN``,
    ``PROJECT_WATCHDOG_STATE_ROOT``, ``PROJECT_WATCHDOG_WORKSPACE`` — therefore
    has to come from a file the skill loads itself.

Inputs
    ``<skill>/.env`` when present. The file is optional; absence is normal.

Outputs
    Environment variables populated in ``os.environ``. Values already present in
    the real environment always win, so an explicit ``UV_BIN=... ./run.sh`` and
    the test suite's ``monkeypatch.setenv`` are never overridden by the file.

Failure modes
    A missing ``.env`` is a no-op. A malformed one is logged at WARNING and
    skipped: the watchdog's safe default is "no overrides", never "refuse to
    start". Every module that reads the environment must call ``load_env()``
    at import so behaviour cannot depend on module import order.
"""

from __future__ import annotations

import os
from pathlib import Path

_LOADED = False


def env_file() -> Path:
    """Return the optional per-skill ``.env`` path."""
    return Path(__file__).resolve().parents[2] / ".env"


def load_env() -> bool:
    """Load ``<skill>/.env`` once. Returns ``True`` if a file was applied."""
    global _LOADED
    if _LOADED:
        return False
    _LOADED = True
    path = env_file()
    if not path.is_file():
        return False
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - dependency is declared in pyproject
        return False
    try:
        # override=False: the real environment always beats the file.
        return bool(load_dotenv(path, override=False))
    except (OSError, ValueError) as exc:
        from loguru import logger

        logger.warning("ignoring malformed {}: {}", path, exc)
        return False


def get(name: str, default: str | None = None) -> str | None:
    """Read one environment variable after ensuring ``.env`` has been applied."""
    load_env()
    return os.environ.get(name, default)
