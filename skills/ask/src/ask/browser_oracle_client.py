"""Subprocess client for the sibling browser-oracle skill."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from loguru import logger

from .ask_config import BROWSER_ORACLE_RUN, SKILLS_DIR


class BrowserOracleResolveError(RuntimeError):
    """browser-oracle resolve failed or returned needs_attention."""


def browser_oracle_run_path() -> Path:
    override = os.environ.get("ASK_BROWSER_ORACLE_RUN", "").strip()
    if override:
        return Path(override).expanduser()
    if BROWSER_ORACLE_RUN.exists():
        return BROWSER_ORACLE_RUN
    fallback = SKILLS_DIR / "browser-oracle" / "run.sh"
    return fallback


def resolve_browser_oracle(
    *,
    from_path: str | Path = ".",
    backend: str = "webgpt",
    project: str = "",
    lane: str = "",
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Call ``browser-oracle resolve --json`` and return parsed payload."""
    if os.environ.get("ASK_BROWSER_ORACLE_DISABLE", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        return {"status": "skipped", "reason": "ASK_BROWSER_ORACLE_DISABLE"}

    run_sh = browser_oracle_run_path()
    if not run_sh.exists():
        logger.error("browser-oracle run.sh not found at {}", run_sh)
        return {"status": "skipped", "reason": "browser_oracle_missing", "path": str(run_sh)}

    resolved_from = str(Path(from_path).expanduser().resolve())
    cmd = [
        str(run_sh),
        "resolve",
        "--from",
        resolved_from,
        "--backend",
        backend,
        "--json",
    ]
    if project.strip():
        cmd.extend(["--project", project.strip()])
    if lane.strip():
        cmd.extend(["--lane", lane.strip()])

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=run_sh.parent,
        )
    except subprocess.TimeoutExpired as exc:
        raise BrowserOracleResolveError(
            f"browser-oracle resolve timed out after {timeout:.0f}s"
        ) from exc

    stdout = (proc.stdout or "").strip()
    if not stdout:
        raise BrowserOracleResolveError(
            f"browser-oracle resolve produced no output (exit={proc.returncode}): "
            f"{(proc.stderr or '')[-500:]}"
        )

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise BrowserOracleResolveError(
            f"browser-oracle resolve returned non-JSON: {stdout[:500]}"
        ) from exc

    if proc.returncode != 0 and payload.get("status") == "needs_attention":
        return payload
    if proc.returncode != 0:
        raise BrowserOracleResolveError(
            payload.get("resume_hint")
            or payload.get("reason")
            or f"browser-oracle resolve exit {proc.returncode}"
        )
    return payload


def apply_webgpt_browser_oracle(
    *,
    from_path: str | Path,
    project: str,
    tab_id: str,
    url: str,
    create_tab: bool,
    lane: str = "",
) -> tuple[str, str, str, dict[str, Any]]:
    """Fill missing webgpt project/tab/url from browser-oracle walk-up."""
    if tab_id.strip() or url.strip() or create_tab:
        return project, tab_id, url, {"status": "skipped", "reason": "explicit_target"}

    try:
        payload = resolve_browser_oracle(
            from_path=from_path,
            backend="webgpt",
            project=project,
            lane=lane,
        )
    except BrowserOracleResolveError as exc:
        logger.error("browser-oracle resolve failed: {}", exc)
        return project, tab_id, url, {"status": "error", "error": str(exc)}

    if payload.get("status") == "skipped":
        return project, tab_id, url, payload

    resolved_project = (project or payload.get("project") or "").strip()
    resolved_tab = (tab_id or str(payload.get("tab_id") or "")).strip()
    resolved_url = (url or str(payload.get("conversation_url") or "")).strip()
    applied = bool(resolved_project or resolved_tab or resolved_url)
    meta = {
        **payload,
        "browser_oracle_applied": applied,
        "resolved_project": resolved_project,
    }
    return resolved_project, resolved_tab, resolved_url, meta
