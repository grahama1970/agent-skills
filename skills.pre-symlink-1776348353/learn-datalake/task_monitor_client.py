"""Task-monitor integration for learn-datalake.

Thin wrapper: subprocess-based tm_* functions call the task-monitor CLI binary.
write_task_state uses the shared TaskClient's state-writing pattern.

Inputs:
- Task names, state files, project identifiers.

Outputs:
- Side effects: task-monitor subprocess calls, state file writes.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from config import TASK_MONITOR_DIR, TASK_MONITOR_RUN

# Re-export TaskClient for any callers that might want it directly
from common.task_monitor import TaskClient


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _task_monitor_cmd(
    args: List[str],
    *,
    strict: bool,
    timeout: int = 120,
) -> bool:
    """Execute a task-monitor command. Returns True on success."""
    if not TASK_MONITOR_RUN.exists():
        msg = f"task-monitor missing at {TASK_MONITOR_RUN}"
        if strict:
            raise RuntimeError(msg)
        logger.warning(msg)
        return False
    proc = subprocess.run(
        [str(TASK_MONITOR_RUN), *args],
        cwd=str(TASK_MONITOR_DIR),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        msg = (
            f"task-monitor command failed rc={proc.returncode} "
            f"args={' '.join(args)} "
            f"stderr_tail={proc.stderr.splitlines()[-1] if proc.stderr else ''}"
        )
        if strict:
            raise RuntimeError(msg)
        logger.warning(msg)
        return False
    return True


def tm_start_session(*, project: str, enabled: bool, strict: bool) -> None:
    """Start a task-monitor session."""
    if not enabled:
        return
    _task_monitor_cmd(["start-session", "--project", project], strict=strict)


def tm_end_session(*, notes: str, enabled: bool, strict: bool) -> None:
    """End the current task-monitor session."""
    if not enabled:
        return
    _task_monitor_cmd(["end-session", "--notes", notes], strict=strict)


def tm_add_accomplishment(*, text: str, enabled: bool, strict: bool) -> None:
    """Record an accomplishment in task-monitor."""
    if not enabled:
        return
    _task_monitor_cmd(["add-accomplishment", text], strict=strict)


def tm_register_task(
    *,
    name: str,
    state_file: Path,
    total: Optional[int],
    description: str,
    project: str,
    enabled: bool,
    strict: bool,
) -> None:
    """Register a named task with task-monitor."""
    if not enabled:
        return
    args = [
        "register",
        "--name", name,
        "--state", str(state_file),
        "--desc", description,
        "--project", project,
    ]
    if total is not None:
        args.extend(["--total", str(total)])
    _task_monitor_cmd(args, strict=strict)


def write_task_state(state_file: Path, payload: Dict[str, Any]) -> None:
    """Write task progress state to a JSON file for task-monitor consumption."""
    state_file.parent.mkdir(parents=True, exist_ok=True)
    payload.setdefault("last_updated", _utc_now())
    state_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
