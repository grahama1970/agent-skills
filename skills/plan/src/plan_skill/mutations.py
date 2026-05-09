"""Structured plan mutation helpers for the /plan CLI."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

import yaml
from loguru import logger

sys.path.append(str(Path(__file__).resolve().parents[3]))
from _shared.structured_plan import load_structured_plan  # type: ignore  # noqa: E402

ValidateFunc = Callable[[dict[str, Any]], dict[str, Any]]


def add_task_to_plan(filepath: Path, task: dict[str, Any], validate_func: ValidateFunc) -> dict[str, Any]:
    """Add a task dictionary to an existing YAML plan and validate the result."""
    data = load_structured_plan(filepath)
    existing_tasks = data.get("tasks") or []
    existing_ids = {str(item.get("id", "")) for item in existing_tasks if isinstance(item, dict)}

    task_id = str(task.get("id") or "")
    if not task_id or task_id in existing_ids:
        max_int = 0
        for existing_id in existing_ids:
            try:
                max_int = max(max_int, int(existing_id.split(".")[-1]))
            except ValueError:
                pass
        task_id = str(max_int + 1)
        task["id"] = task_id

    existing_tasks.append(task)
    data["tasks"] = existing_tasks

    lanes = data.get("lanes") or []
    lane_ids = {str(lane.get("id", "")) for lane in lanes if isinstance(lane, dict)}
    lane = str(task.get("lane") or "")
    if lane and lane not in lane_ids:
        lanes.append({"id": lane, "label": f"Wave {lane}"})
        data["lanes"] = lanes

    result = validate_func(data)
    filepath.write_text(yaml.safe_dump(data, sort_keys=False, default_flow_style=False))
    logger.info("Added task {} to {}", task_id, filepath)
    return {
        "task_id": task_id,
        "valid": result["valid"],
        "issues": result.get("issues", []),
        "warnings": result.get("warnings", []),
    }


def remove_task_from_plan(filepath: Path, task_id: str, validate_func: ValidateFunc) -> dict[str, Any]:
    """Remove a task from an existing YAML plan and clean up dangling deps."""
    data = load_structured_plan(filepath)
    tasks = data.get("tasks") or []
    before = len(tasks)
    tasks = [task for task in tasks if str(task.get("id", "")) != task_id]
    if len(tasks) == before:
        return {"removed": False, "error": f"Task {task_id} not found"}

    for task in tasks:
        deps = task.get("depends_on") or []
        task["depends_on"] = [dep for dep in deps if str(dep) != task_id]

    data["tasks"] = tasks
    result = validate_func(data)
    filepath.write_text(yaml.safe_dump(data, sort_keys=False, default_flow_style=False))
    logger.info("Removed task {} from {}", task_id, filepath)
    return {"removed": True, "valid": result["valid"], "issues": result.get("issues", [])}
