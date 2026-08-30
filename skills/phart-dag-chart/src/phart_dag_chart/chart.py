"""Render validated DAG JSON to PHART 1.5 ASCII decision tree."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

import networkx as nx
from phart import ASCIIRenderer, LayoutOptions, NodeStyle

from phart_dag_chart.dag_validate import validate_dag
from phart_dag_chart.errors import DagChartError


def _node_label(node: dict[str, Any]) -> str:
    node_input = node.get("input") or {}
    node_type = str(node.get("type") or "")
    display_type = str(node.get("display_type") or node_type)
    lines = [str(node["id"])]

    if node_type == "skill.run":
        skill = str(node_input.get("skill") or "missing-skill")
        lines.append(f"skill.run:{skill}")
    elif node_type == "ask.oracle":
        model = str(node_input.get("model") or "model?")
        lines.append(f"ask.oracle:{model}")
        reasoning = node_input.get("reasoning_effort")
        if reasoning:
            lines.append(f"reasoning: {reasoning}")
    elif node_type == "dogpile.search":
        lines.append("dogpile.search")
        query = node_input.get("query") or node_input.get("q")
        if query:
            lines.append(f"query: {str(query)[:30]}")
    elif node_type == "memory.recall":
        lines.append("memory.recall")
        query = node_input.get("query") or node_input.get("q")
        if query:
            lines.append(f"query: {str(query)[:30]}")
    else:
        lines.append(display_type)

    if node.get("allow_failure"):
        lines.append("optional")

    # Self-expanding refinement semantics (2026-08-27): a node may declare
    # `role` so the chart explains the expansion topology without prose.
    role = str(node.get("role") or "")
    if role == "expansion":
        lines.append(">> EXPANDS NEXT FANOUT <<")
    elif role == "gate":
        lines.append(">> DRY? settle : next ROUND <<")
    elif role == "terminal":
        lines.append("[terminal proof]")

    label = "\n".join(lines)
    if len(label) > 120:
        return label[:117] + "..."
    return label


_ROLE_MARKS = {"expansion": "»expands»", "gate": "?dry-gate?", "terminal": "=proof="}


def _metadata_lines(node: dict[str, Any]) -> list[str]:
    node_input = node.get("input") or {}
    lines: list[str] = []
    agent = str(node_input.get("agent") or node.get("agent") or "").strip()
    model = str(node_input.get("model") or node_input.get("handler") or node.get("model") or node.get("handler") or "").strip()
    executor = str(node_input.get("executor") or node.get("executor") or "").strip()
    skill = str(node_input.get("skill") or "").strip()
    skills_raw = node_input.get("skills") or node.get("skills") or []
    skills = [str(item) for item in skills_raw] if isinstance(skills_raw, list) else [str(skills_raw)] if skills_raw else []
    if agent:
        lines.append(f"agent:{agent}")
    if model:
        lines.append(f"model:{model}")
    if skill and skill != agent:
        lines.append(f"skill:{skill}")
    if skills:
        lines.append("skills:" + ",".join(skills[:4]))
    if executor:
        lines.append(f"exec:{executor}")
    max_attempts = node.get("max_attempts")
    if isinstance(max_attempts, int) and max_attempts > 1:
        lines.append(f"tries:{max_attempts}")
    return lines


def _display_name(node: dict[str, Any], *, show_meta: bool = False) -> str:
    """PHART's minimal style renders node NAMES, so important execution
    metadata must ride in the displayed name when requested."""
    mark = _ROLE_MARKS.get(str(node.get("role") or ""))
    lines = [f"{node['id']} {mark}" if mark else str(node["id"])]
    if show_meta:
        lines.extend(_metadata_lines(node))
    return "\n".join(lines)


def dag_to_nx(dag: dict[str, Any], *, show_meta: bool = False) -> nx.DiGraph:
    graph = nx.DiGraph()
    display = {node["id"]: _display_name(node, show_meta=show_meta) for node in dag["nodes"]}
    for node in dag["nodes"]:
        graph.add_node(display[node["id"]], label=_node_label(node))
    for node in dag["nodes"]:
        for parent_id in node.get("depends_on", []):
            if parent_id in display:
                graph.add_edge(display[parent_id], display[node["id"]])
    return graph


_ATTEMPT_RE = re.compile(r"^(?P<base>.+)-(?P<n>[1-9][0-9]*)$")


def _loop_parts(dag: dict[str, Any]) -> tuple[list[int], list[str], list[dict[str, Any]], list[dict[str, Any]]] | None:
    grouped: dict[int, list[str]] = defaultdict(list)
    nodes_by_id = {str(node["id"]): node for node in dag.get("nodes", [])}
    for node_id in nodes_by_id:
        match = _ATTEMPT_RE.fullmatch(node_id)
        if match:
            grouped[int(match.group("n"))].append(match.group("base"))
    if len(grouped) < 2:
        return None
    attempts = sorted(grouped)
    repeated = set(grouped[attempts[0]])
    for attempt in attempts[1:]:
        repeated &= set(grouped[attempt])
    if not repeated:
        return None
    preferred = ["creator-attempt", "surf-screenshot", "reviewer-visual-gate"]
    bases = [base for base in preferred if base in repeated] or sorted(repeated)
    creator_nodes = [nodes_by_id[f"creator-attempt-{attempt}"] for attempt in attempts if f"creator-attempt-{attempt}" in nodes_by_id]
    reviewer_nodes = [nodes_by_id[f"reviewer-visual-gate-{attempt}"] for attempt in attempts if f"reviewer-visual-gate-{attempt}" in nodes_by_id]
    return attempts, bases, creator_nodes, reviewer_nodes


def _loop_summary(dag: dict[str, Any]) -> str | None:
    parts = _loop_parts(dag)
    if not parts:
        return None
    attempts, bases, creator_nodes, reviewer_nodes = parts
    creator_meta = _metadata_lines(creator_nodes[0]) if creator_nodes else []
    reviewer_meta = _metadata_lines(reviewer_nodes[0]) if reviewer_nodes else []
    lines = [
        f"[visual loop x{len(attempts)} max]",
        "agents: 2 (creator + reviewer)",
    ]
    if creator_meta:
        lines.append("creator: " + " | ".join(creator_meta))
    if reviewer_meta:
        lines.append("reviewer: " + " | ".join(reviewer_meta))
    lines.append("body: " + " -> ".join(bases))
    return "\n".join(lines)


def _compact_loop_dag(dag: dict[str, Any]) -> dict[str, Any]:
    parts = _loop_parts(dag)
    if not parts:
        return dag
    attempts, bases, creator_nodes, reviewer_nodes = parts
    loop_ids = {f"{base}-{attempt}" for base in bases for attempt in attempts}
    failure_node_ids = {"triage-error", "ticket", "ticket-and-eval", "project-watchdog", "agentic-evals"}
    present_failure_ids = {str(node["id"]) for node in dag["nodes"] if str(node["id"]) in failure_node_ids}
    loop_id = f"visual-loop-x{len(attempts)}"
    compact_nodes: list[dict[str, Any]] = []
    for node in dag["nodes"]:
        if node["id"] not in loop_ids and node["id"] not in present_failure_ids:
            compact_nodes.append({**node, "depends_on": []})
    creator = creator_nodes[0] if creator_nodes else {}
    reviewer = reviewer_nodes[0] if reviewer_nodes else {}
    loop_node = {
        "id": loop_id,
        "type": "skill.run",
        "display_type": "tau.visual-loop",
        "depends_on": [],
        "max_attempts": len(attempts),
        "input": {
            "skill": "create-svg visual-loop",
            "agent": "2 agents",
            "executor": "tau",
            "model": f"creator={((creator.get('input') or {}).get('model') or creator.get('model') or '?')} reviewer={((reviewer.get('input') or {}).get('model') or reviewer.get('model') or '?')}",
            "skills": [
                "creator:create-svg+best-practices-svg-design",
                "reviewer:surf+best-practices-svg-design",
            ],
        },
    }
    compact_nodes.append(loop_node)
    if present_failure_ids:
        compact_nodes.append({
            "id": "global-error-sidecar",
            "type": "skill.run",
            "display_type": "tau.on-error",
            "depends_on": [],
            "max_attempts": 1,
            "input": {
                "skill": "runtime/contract on_error",
                "agent": "error-router",
                "executor": "concurrent-monitor",
                "skills": ["triage-error", "ticket", "project-watchdog", "agentic-evals"],
            },
        })
    by_id = {node["id"]: node for node in compact_nodes}
    edges: set[tuple[str, str]] = set()
    for node in dag["nodes"]:
        if node["id"] in present_failure_ids:
            child = "global-error-sidecar"
        else:
            child = loop_id if node["id"] in loop_ids else node["id"]
        for parent in node.get("depends_on", []):
            if parent in present_failure_ids:
                compact_parent = "global-error-sidecar"
            else:
                compact_parent = loop_id if parent in loop_ids else parent
            if compact_parent != child and compact_parent in by_id and child in by_id:
                if child == "global-error-sidecar":
                    continue
                edges.add((compact_parent, child))
    if "human" in by_id and "global-error-sidecar" in by_id:
        edges.add(("global-error-sidecar", "human"))
    for parent, child in sorted(edges):
        by_id[child].setdefault("depends_on", []).append(parent)
    return {**dag, "nodes": list(by_id.values())}


def render_chart(
    dag: dict[str, Any], *, validate: bool = True, plain: bool = False, show_meta: bool = False, compact_loops: bool = False
) -> str:
    source_dag = dag
    if validate:
        dag, _warnings = validate_dag(dag, chart_only=True)
    if not dag.get("nodes"):
        raise DagChartError("DAG has no nodes to render.")
    original_dag = dag
    if compact_loops:
        dag = _compact_loop_dag(dag)
    try:
        graph = dag_to_nx(dag, show_meta=show_meta)
        options = LayoutOptions(
            layout_strategy="layered",
            flow_direction="down",
            bboxes=True,
            node_style=NodeStyle.MINIMAL,
            layer_spacing=4,
            node_spacing=5,
            bbox_multiline_labels=True,
            hpad=1,
            vpad=0,
        )
        body = ASCIIRenderer(graph, options=options).render().rstrip()
    except Exception as exc:
        raise DagChartError(
            f"PHART render failed: {exc}",
            code="render_failed",
            hint="Run validate first; fix cycles, duplicate ids, or unknown depends_on.",
        ) from None
    graph_id = str(dag.get("graph_id") or "dag")
    schema_version = str(dag.get("schema_version") or "")
    source_graph_version = str(dag.get("source_graph_version") or "")
    schema = (
        f"{source_graph_version} -> {schema_version}"
        if source_graph_version
        else schema_version
    )
    header = [
        f"DAG decision tree · {graph_id} (phart 1.5 git)",
        f"schema={schema}",
        "",
    ]
    loop = _loop_summary(original_dag) if compact_loops else None
    if loop:
        header.append(loop)
        header.append("")
    on_error = source_dag.get("on_error") if isinstance(source_dag.get("on_error"), dict) else None
    if on_error:
        route = on_error.get("route") if isinstance(on_error.get("route"), list) else []
        header.extend([
            "on_error: " + str(on_error.get("scope") or "any_node_runtime_or_contract_failure"),
            "error route: " + " -> ".join(str(item) for item in route),
            "not error: " + str(on_error.get("not_for") or "visual_gate_not_ready"),
            "",
        ])
    footer = ["", "renderer: phart@github.com/scottvr/phart · layout=layered · bboxes"]
    lines = header + [body] + footer
    if plain:
        return "\n".join(lines)
    return "\n".join(["```text", *lines, "```"])
