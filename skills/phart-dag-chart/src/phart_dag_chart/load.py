"""Load DAG JSON from disk with helpful, traceback-free errors."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phart_dag_chart.errors import DagChartError


def load_dag_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise DagChartError(
            f"DAG file not found: {path}",
            code="file_not_found",
            hint="Pass an existing path, e.g. ./run.sh chart plans/my.dag.json",
        )
    if not path.is_file():
        raise DagChartError(
            f"DAG path is not a file: {path}",
            code="not_a_file",
            hint="Pass a JSON file path, e.g. ./run.sh chart plans/my.dag.json",
        )
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DagChartError(
            f"Cannot read DAG file: {path} ({exc})",
            code="read_failed",
        ) from None
    if not raw.strip():
        raise DagChartError(
            f"DAG file is empty: {path}",
            code="empty_file",
            hint='Add a JSON object with schema_version and nodes, or exec_graph_version for scillm graphs.',
        )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DagChartError(
            f"DAG file is not valid JSON ({exc.msg} at line {exc.lineno}, column {exc.colno}).",
            code="json_parse",
            hint="Fix JSON syntax (trailing commas, unquoted keys, etc.) before re-running validate or chart.",
        ) from None
    if not isinstance(data, dict):
        raise DagChartError(
            "DAG root must be a JSON object.",
            code="json_shape",
            hint='Use {"schema_version": "ask.dag.v1", "nodes": [...]}',
        )
    return data
