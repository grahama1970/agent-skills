"""Validate DAG JSON for charting; messages match $ask validate_ask_dag where applicable."""

from __future__ import annotations

from typing import Any

from phart_dag_chart.constants import (
    ALLOWED_NODE_TYPES,
    ASK_DAG_SCHEMA_VERSION,
    NODE_ID_RE,
    SCILLM_EXEC_GRAPH_VERSION,
)
from phart_dag_chart.errors import DagChartError, ValidationIssue


def _topological_order(nodes: list[dict[str, Any]]) -> list[str]:
    indegree = {node["id"]: 0 for node in nodes}
    outgoing: dict[str, list[str]] = {node["id"]: [] for node in nodes}
    for node in nodes:
        for parent in node.get("depends_on", []):
            if parent not in indegree:
                continue
            indegree[node["id"]] += 1
            outgoing[parent].append(node["id"])
    ready = [node_id for node_id, degree in indegree.items() if degree == 0]
    order: list[str] = []
    while ready:
        current = ready.pop(0)
        order.append(current)
        for child in outgoing[current]:
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
    if len(order) != len(nodes):
        raise DagChartError(
            "DAG contains a dependency cycle; remove circular depends_on links.",
            code="cycle",
            hint="Ensure depends_on only points to earlier layers, not downstream nodes.",
        )
    return order


def _normalize_scillm_for_chart(dag: dict[str, Any]) -> dict[str, Any]:
    nodes_raw = dag.get("nodes")
    if not isinstance(nodes_raw, list) or not nodes_raw:
        raise DagChartError("DAG requires a non-empty nodes list.")
    normalized: list[dict[str, Any]] = []
    for index, raw_node in enumerate(nodes_raw, 1):
        if not isinstance(raw_node, dict):
            raise DagChartError(f"scillm exec graph node {index} must be an object.")
        node_id = str(raw_node.get("id") or "").strip()
        if not NODE_ID_RE.fullmatch(node_id) or node_id in {".", ".."}:
            raise DagChartError(f"DAG node {index} has an unsafe id {node_id!r}.")
        node_type = str(raw_node.get("type") or "skill.run").strip()
        depends_on = raw_node.get("depends_on", [])
        if depends_on is None:
            depends_on = []
        if isinstance(depends_on, str):
            depends_on = [depends_on]
        if not isinstance(depends_on, list) or not all(isinstance(item, str) for item in depends_on):
            raise DagChartError(f"DAG node {node_id!r} depends_on must be a string list.")
        normalized.append({
            "id": node_id,
            "type": node_type,
            "depends_on": depends_on,
            "allow_failure": bool(raw_node.get("allow_failure", False)),
        })
    return {
        "schema_version": ASK_DAG_SCHEMA_VERSION,
        "source_graph_version": SCILLM_EXEC_GRAPH_VERSION,
        "graph_id": str(dag.get("graph_id") or ""),
        "description": str(dag.get("description") or dag.get("graph_goal") or ""),
        "nodes": normalized,
    }


def validate_dag(
    dag: dict[str, Any],
    *,
    chart_only: bool = True,
) -> tuple[dict[str, Any], list[ValidationIssue]]:
    """Validate and normalize a DAG. chart_only skips skill.run registry checks."""
    warnings: list[ValidationIssue] = []
    if dag.get("exec_graph_version") == SCILLM_EXEC_GRAPH_VERSION:
        dag = _normalize_scillm_for_chart(dag)
    version = str(dag.get("schema_version") or ASK_DAG_SCHEMA_VERSION)
    if version != ASK_DAG_SCHEMA_VERSION:
        raise DagChartError(
            f"Unsupported DAG schema_version {version!r}; expected {ASK_DAG_SCHEMA_VERSION}.",
            code="schema_version",
            hint='Set "schema_version": "ask.dag.v1" or pass a scillm exec graph with exec_graph_version.',
        )
    nodes = dag.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise DagChartError("DAG requires a non-empty nodes list.")
    seen: set[str] = set()
    normalized_nodes: list[dict[str, Any]] = []
    for index, raw_node in enumerate(nodes, 1):
        if not isinstance(raw_node, dict):
            raise DagChartError(f"DAG node {index} must be an object.")
        node_id = str(raw_node.get("id") or "").strip()
        node_type = str(raw_node.get("type") or "").strip()
        if not NODE_ID_RE.fullmatch(node_id) or node_id in {".", ".."}:
            raise DagChartError(f"DAG node {index} has an unsafe id {node_id!r}.")
        if node_id in seen:
            raise DagChartError(f"DAG node id {node_id!r} is duplicated.")
        if node_type not in ALLOWED_NODE_TYPES:
            raise DagChartError(f"DAG node {node_id!r} has unsupported type {node_type!r}.")
        depends_on = raw_node.get("depends_on", [])
        if depends_on is None:
            depends_on = []
        if isinstance(depends_on, str):
            depends_on = [depends_on]
        if not isinstance(depends_on, list) or not all(isinstance(item, str) for item in depends_on):
            raise DagChartError(f"DAG node {node_id!r} depends_on must be a string list.")
        node_input = raw_node.get("input", {})
        if node_input is not None and not isinstance(node_input, dict):
            raise DagChartError(f"DAG node {node_id!r} input must be an object.")
        max_attempts = raw_node.get("max_attempts", 1)
        if not isinstance(max_attempts, int) or max_attempts < 1 or max_attempts > 10:
            raise DagChartError(f"DAG node {node_id!r} max_attempts must be an integer from 1 to 10.")
        allow_failure = raw_node.get("allow_failure", False)
        if not isinstance(allow_failure, bool):
            raise DagChartError(f"DAG node {node_id!r} allow_failure must be a boolean.")
        if chart_only and node_type == "skill.run":
            skill = str((node_input or {}).get("skill") or "").strip()
            if not skill:
                warnings.append(
                    ValidationIssue(
                        severity="warning",
                        code="skill_run_empty",
                        message=f"DAG node {node_id!r} skill.run has no skill name (chart will still render).",
                        hint='Set input.skill to a sibling skill name, e.g. "dogpile".',
                    )
                )
        normalized_nodes.append({
            **raw_node,
            "id": node_id,
            "type": node_type,
            "depends_on": depends_on,
            "input": node_input or {},
            "max_attempts": max_attempts,
            "allow_failure": allow_failure,
        })
        seen.add(node_id)
    missing = {
        dependency
        for node in normalized_nodes
        for dependency in node["depends_on"]
        if dependency not in seen
    }
    if missing:
        raise DagChartError(f"DAG has unknown dependencies: {sorted(missing)}.")
    order = _topological_order(normalized_nodes)
    max_concurrency = dag.get("max_concurrency", 8)
    if max_concurrency is not None and (
        not isinstance(max_concurrency, int) or max_concurrency < 1 or max_concurrency > 32
    ):
        raise DagChartError("DAG max_concurrency must be an integer from 1 to 32.")
    join_without_deps = [
        n["id"]
        for n in normalized_nodes
        if n["type"] == "skill.run" and not n.get("depends_on")
        and str((n.get("input") or {}).get("skill") or "") in {"ask", ""}
    ]
    if len(normalized_nodes) > 1 and join_without_deps:
        warnings.append(
            ValidationIssue(
                severity="warning",
                code="orphan_join",
                message=f"Nodes {join_without_deps!r} look like join/final nodes but have no depends_on.",
                hint="Add depends_on listing upstream node ids so the chart shows fan-in correctly.",
            )
        )
    normalized = {
        "schema_version": ASK_DAG_SCHEMA_VERSION,
        "description": str(dag.get("description") or ""),
        "source_graph_version": str(dag.get("source_graph_version") or ""),
        "graph_id": str(dag.get("graph_id") or ""),
        "max_concurrency": max_concurrency if isinstance(max_concurrency, int) else 8,
        "nodes": normalized_nodes,
    }
    return normalized, warnings


def validation_report(dag: dict[str, Any], *, chart_only: bool = True) -> dict[str, Any]:
    normalized, warnings = validate_dag(dag, chart_only=chart_only)
    layers: list[list[str]] = []
    remaining = {n["id"]: set(n.get("depends_on", [])) for n in normalized["nodes"]}
    while remaining:
        layer = [nid for nid, deps in remaining.items() if not deps]
        if not layer:
            break
        layers.append(sorted(layer))
        for nid in layer:
            del remaining[nid]
        for deps in remaining.values():
            deps -= set(layer)
    return {
        "ok": True,
        "schema_version": normalized["schema_version"],
        "graph_id": normalized.get("graph_id") or "",
        "node_count": len(normalized["nodes"]),
        "layer_count": len(layers),
        "topo_order": _topological_order(normalized["nodes"]),
        "warnings": [w.to_dict() for w in warnings],
        "errors": [],
    }
