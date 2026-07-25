"""Paths and defaults for browser-oracle."""

from __future__ import annotations

import os
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = SKILL_ROOT.parent

SUPPORTED_BACKENDS = (
    "webgpt",
    "cursor-browser",
    "webgemini",
    "webkimi",
    "webclaude",
    "webgrok",
)

BACKEND_PROJECT_ROOT_ENV = {
    "webgpt": "BROWSER_ORACLE_WEBGPT_PROJECT_ROOT",
    "cursor-browser": "BROWSER_ORACLE_CURSOR_BROWSER_PROJECT_ROOT",
    "webgemini": "BROWSER_ORACLE_WEBGEMINI_PROJECT_ROOT",
    "webkimi": "BROWSER_ORACLE_WEBKIMI_PROJECT_ROOT",
    "webclaude": "BROWSER_ORACLE_WEBCLAUDE_PROJECT_ROOT",
    "webgrok": "BROWSER_ORACLE_WEBGROK_PROJECT_ROOT",
}

DEFAULT_PROJECT_ROOTS = {
    "webgpt": Path.home() / ".pi" / "webgpt-projects",
    "cursor-browser": Path.home() / ".pi" / "cursor-browser-projects",
    "webgemini": Path.home() / ".pi" / "webgemini-projects",
    "webkimi": Path.home() / ".pi" / "webkimi-projects",
    "webclaude": Path.home() / ".pi" / "webclaude-projects",
    "webgrok": Path.home() / ".pi" / "webgrok-projects",
}


def project_root(backend: str) -> Path:
    backend = backend.strip().lower()
    if backend not in SUPPORTED_BACKENDS:
        raise ValueError(f"unsupported backend {backend!r}; use one of {SUPPORTED_BACKENDS}")
    env_key = BACKEND_PROJECT_ROOT_ENV[backend]
    override = os.environ.get(env_key, "").strip()
    if override:
        return Path(override).expanduser()
    return DEFAULT_PROJECT_ROOTS[backend]


def surf_run_path() -> Path:
    return Path(
        os.environ.get("BROWSER_ORACLE_SURF_RUN", str(SKILLS_DIR / "surf" / "run.sh"))
    ).expanduser()


def ask_run_path() -> Path:
    return Path(
        os.environ.get("BROWSER_ORACLE_ASK_RUN", str(SKILLS_DIR / "ask" / "run.sh"))
    ).expanduser()
