"""Task Monitor Utilities - Common helper functions.

This module provides utility functions used across the task-monitor skill.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from task_monitor.config import SCHEDULER_JOBS_FILE, BATCH_REPORT_PATHS
from task_monitor.models import TaskConfig


def read_task_state(state_file: str) -> dict:
    """Read state from a task's state file.

    Args:
        state_file: Path to the JSON state file

    Returns:
        Dictionary with standardized state fields
    """
    path = Path(state_file)

    if not path.exists():
        return {"error": "State file not found", "state_file": state_file}

    try:
        with open(path, encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return {"error": f"Failed to read state: {e}", "state_file": state_file}

    # Standard fields we look for
    return {
        "state_file": state_file,
        "completed": len(state.get("completed", [])) if isinstance(state.get("completed"), list) else state.get("completed", 0),
        "stats": state.get("stats", {}),
        "current_item": state.get("current_video", state.get("current_item", state.get("current", ""))),
        "current_method": state.get("current_method", ""),
        "last_updated": state.get("last_updated", ""),
        "consecutive_failures": state.get("consecutive_failures", 0),
        "raw": state,  # Include raw state for debugging
    }


def get_task_status(task: TaskConfig, include_raw: bool = False) -> dict:
    """Get full status for a task.

    Args:
        task: TaskConfig object
        include_raw: Whether to include raw state data

    Returns:
        Dictionary with task status information
    """
    state = read_task_state(task.state_file)

    # Add task config info
    state["name"] = task.name
    state["total"] = task.total
    state["description"] = task.description

    # Calculate progress percentage (allow 0% progress)
    if task.total and task.total > 0 and "completed" in state:
        completed = state.get("completed") or 0
        state["progress_pct"] = (completed / task.total) * 100
    else:
        state["progress_pct"] = None

    # Remove raw state from API responses (too verbose) unless requested
    if not include_raw and "raw" in state:
        del state["raw"]

    return state


def get_scheduled_jobs() -> list[dict]:
    """Get list of scheduled jobs from the scheduler.

    Returns:
        List of job dictionaries
    """
    if not SCHEDULER_JOBS_FILE.exists():
        return []
    try:
        with open(SCHEDULER_JOBS_FILE, encoding="utf-8") as f:
            data = json.load(f)
            return list(data.values())
    except (OSError, json.JSONDecodeError):
        return []


def find_batch_report_script() -> Optional[Path]:
    """Find the batch-report script in known locations.

    Returns:
        Path to the script if found, None otherwise
    """

    for path in BATCH_REPORT_PATHS:
        if path.exists():
            return path
    return None


def format_duration(seconds: float) -> str:
    """Format seconds as human-readable duration.

    Args:
        seconds: Number of seconds

    Returns:
        Formatted string like "1h 23m" or "45m"
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes:02d}:{secs:02d}"


def format_eta(hours: float) -> str:
    """Format ETA in hours as human-readable string.

    Args:
        hours: Number of hours

    Returns:
        Formatted string like "2.5h" or "1.2d"
    """
    if hours < 1:
        return f"{int(hours * 60)}m"
    elif hours < 24:
        return f"{hours:.1f}h"
    else:
        return f"{hours / 24:.1f}d"


def truncate_string(s: str, max_len: int) -> str:
    """Truncate string to max length.

    Args:
        s: Input string
        max_len: Maximum length

    Returns:
        Truncated string
    """
    if len(s) <= max_len:
        return s
    return s[:max_len - 3] + "..."
