"""Live-ish terminal monitor for Tau DAG progress artifacts.

Inputs are a static DAG JSON file plus Tau-authored progress JSON. The DAG file
provides graph structure; the progress file provides authoritative runtime state.
The monitor never infers success from the graph alone and never mutates Tau
state.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from phart_dag_chart.chart import render_chart
from phart_dag_chart.dag_validate import validate_dag
from phart_dag_chart.errors import DagChartError
from phart_dag_chart.load import load_dag_file

TERMINAL_STATUSES = frozenset({"PASS", "FAIL", "FAILED", "BLOCKED", "NEEDS_ATTENTION", "CANCELLED", "ERROR"})
PASS_STATUSES = frozenset({"PASS", "COMPLETED", "ACCEPTED", "DONE", "SUCCESS"})
RUNNING_STATUSES = frozenset({"RUNNING", "ACTIVE", "STARTED", "IN_PROGRESS"})
BLOCKED_STATUSES = frozenset({"BLOCKED", "NEEDS_ATTENTION"})
FAIL_STATUSES = frozenset({"FAIL", "FAILED", "ERROR", "CANCELLED"})

_STATUS_SYMBOLS = {
    "PASS": "✓",
    "COMPLETED": "✓",
    "ACCEPTED": "✓",
    "DONE": "✓",
    "SUCCESS": "✓",
    "RUNNING": "●",
    "ACTIVE": "●",
    "STARTED": "●",
    "IN_PROGRESS": "●",
    "BLOCKED": "!",
    "NEEDS_ATTENTION": "!",
    "FAIL": "✗",
    "FAILED": "✗",
    "ERROR": "✗",
    "CANCELLED": "✗",
    "SKIPPED": "-",
    "TERMINAL": "✓",
    "PENDING": "○",
}


def progress_path_from_options(*, dag_file: Path, run_dir: Path | None, progress_file: Path | None) -> Path:
    """Resolve the Tau progress JSON path for a watch invocation."""

    if progress_file is not None:
        return progress_file
    if run_dir is not None:
        return run_dir / "dag-progress.json"
    return dag_file.parent / "dag-progress.json"


def load_progress_file(path: Path) -> dict[str, Any]:
    """Read a Tau progress file or raise a friendly validation error."""

    if not path.exists():
        raise DagChartError(
            f"progress file not found: {path}",
            code="progress_not_found",
            hint="Pass --progress /path/dag-progress.json or --run-dir /path/to/tau-run.",
        )
    if not path.is_file():
        raise DagChartError(
            f"progress path is not a file: {path}",
            code="progress_not_a_file",
            hint="Pass Tau's dag-progress.json, not the run directory itself.",
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DagChartError(
            f"progress file is not valid JSON ({exc.msg} at line {exc.lineno}, column {exc.colno}).",
            code="progress_json_parse",
        ) from None
    except OSError as exc:
        raise DagChartError(f"cannot read progress file: {path} ({exc})", code="progress_read_failed") from None
    if not isinstance(payload, dict):
        raise DagChartError("progress file root must be a JSON object.", code="progress_json_shape")
    return payload


def render_watch_frame(
    dag_file: Path,
    progress_file: Path,
    *,
    include_chart: bool = True,
) -> str:
    """Render one bounded terminal frame from DAG structure plus progress state."""

    raw_dag = load_dag_file(dag_file)
    dag, _warnings = validate_dag(raw_dag, chart_only=True)
    progress = load_progress_file(progress_file)
    lines = _summary_lines(dag, progress, progress_file)
    if include_chart:
        lines.extend(["", _strip_fences(render_chart(dag, validate=False, plain=True))])
    return "\n".join(lines).rstrip()


def watch_until_terminal(
    dag_file: Path,
    progress_file: Path,
    *,
    interval_seconds: float,
    max_seconds: float,
    include_chart: bool,
    clear: bool,
    emit: Any,
) -> str:
    """Poll progress until Tau reaches a terminal status or the window expires."""

    started = time.monotonic()
    last_status = "UNKNOWN"
    while True:
        frame = render_watch_frame(dag_file, progress_file, include_chart=include_chart)
        if clear:
            emit("\033[2J\033[H" + frame)
        else:
            emit(frame)
        progress = load_progress_file(progress_file)
        last_status = _overall_status(progress)
        if last_status in TERMINAL_STATUSES:
            return last_status
        if time.monotonic() - started >= max_seconds:
            raise DagChartError(
                f"watch timed out after {max_seconds:g}s; last status={last_status}",
                code="watch_timeout",
                hint="Inspect Tau events.jsonl/dag-progress.json, then rerun watch with a larger --max-seconds if work is still active.",
            )
        time.sleep(max(interval_seconds, 0.1))


def _summary_lines(dag: dict[str, Any], progress: dict[str, Any], progress_file: Path) -> list[str]:
    graph_id = str(progress.get("dag_id") or dag.get("graph_id") or "dag")
    status = _overall_status(progress)
    event_count = progress.get("event_count", progress.get("recent_event_count", "?"))
    active = _node_ids(progress.get("active_subagents"))
    completed = _node_ids(progress.get("completed_subagents"))
    node_status = _node_status_map(progress)
    if not node_status:
        node_status.update({node_id: "RUNNING" for node_id in active})
        node_status.update({node_id: "COMPLETED" for node_id in completed})

    lines = [
        f"Tau DAG terminal monitor · {graph_id}",
        f"State: {status}  events: {event_count}  progress: {progress_file}",
    ]
    last_event = progress.get("last_event")
    if isinstance(last_event, dict):
        event = str(last_event.get("event") or "?")
        node = str(last_event.get("node_id") or last_event.get("plan_id") or "")
        ts = str(last_event.get("ts") or last_event.get("timestamp") or "")
        lines.append(f"Last: {event}{(' · ' + node) if node else ''}{(' · ' + ts) if ts else ''}")
    lines.append("")
    for node in dag.get("nodes", []):
        node_id = str(node["id"])
        status_value = node_status.get(node_id)
        if status_value is None:
            status_value = "TERMINAL" if status == "PASS" and _is_human_terminal(node) else "PENDING"
        attempt = _attempt_for(progress, node_id)
        attempt_suffix = f" attempt {attempt}" if attempt else ""
        lines.append(f"{_status_symbol(status_value)} {node_id:<24} {status_value}{attempt_suffix}")
    return lines


def _is_human_terminal(node: dict[str, Any]) -> bool:
    node_input = node.get("input") if isinstance(node.get("input"), dict) else {}
    return str(node_input.get("executor") or node_input.get("skill") or "").lower() == "human"


def _overall_status(progress: dict[str, Any]) -> str:
    value = progress.get("verdict") or progress.get("status") or "UNKNOWN"
    return str(value).upper()


def _node_status_map(progress: dict[str, Any]) -> dict[str, str]:
    statuses: dict[str, str] = {}
    node_progress = progress.get("node_progress")
    if isinstance(node_progress, list):
        for item in node_progress:
            if not isinstance(item, dict):
                continue
            node_id = str(item.get("node_id") or "").strip()
            if not node_id:
                continue
            statuses[node_id] = str(item.get("status") or "UNKNOWN").upper()
    terminal_states = progress.get("node_terminal_states")
    if isinstance(terminal_states, dict):
        for node_id, status in terminal_states.items():
            statuses[str(node_id)] = str(status).upper()
    return statuses


def _attempt_for(progress: dict[str, Any], node_id: str) -> int | None:
    node_progress = progress.get("node_progress")
    if isinstance(node_progress, list):
        for item in node_progress:
            if isinstance(item, dict) and item.get("node_id") == node_id:
                attempt = item.get("attempt")
                return attempt if isinstance(attempt, int) and attempt > 0 else None
    node_attempts = progress.get("node_attempts")
    if isinstance(node_attempts, dict):
        attempt = node_attempts.get(node_id)
        return attempt if isinstance(attempt, int) and attempt > 0 else None
    return None


def _node_ids(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    ids: set[str] = set()
    for item in value:
        if isinstance(item, dict):
            node_id = str(item.get("node_id") or "").strip()
            if node_id:
                ids.add(node_id)
        elif isinstance(item, str):
            ids.add(item)
    return ids


def _status_symbol(status: str) -> str:
    return _STATUS_SYMBOLS.get(status.upper(), "?")


def _strip_fences(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].strip() == "```text":
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines)
