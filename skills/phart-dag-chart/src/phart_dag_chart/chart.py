"""Render validated DAG JSON to PHART 1.5 ASCII decision tree."""

from __future__ import annotations

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

    label = "\n".join(lines)
    if len(label) > 120:
        return label[:117] + "..."
    return label


def dag_to_nx(dag: dict[str, Any]) -> nx.DiGraph:
    graph = nx.DiGraph()
    ids = {node["id"] for node in dag["nodes"]}
    for node in dag["nodes"]:
        graph.add_node(node["id"], label=_node_label(node))
    for node in dag["nodes"]:
        for parent_id in node.get("depends_on", []):
            if parent_id in ids:
                graph.add_edge(parent_id, node["id"])
    return graph


def render_chart(dag: dict[str, Any], *, validate: bool = True, plain: bool = False) -> str:
    if validate:
        dag, _warnings = validate_dag(dag, chart_only=True)
    if not dag.get("nodes"):
        raise DagChartError("DAG has no nodes to render.")
    try:
        graph = dag_to_nx(dag)
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
    schema = str(dag.get("schema_version") or dag.get("source_graph_version") or "")
    header = [
        f"DAG decision tree · {graph_id} (phart 1.5 git)",
        f"schema={schema}",
        "",
    ]
    footer = ["", "renderer: phart@github.com/scottvr/phart · layout=layered · bboxes"]
    lines = header + [body] + footer
    if plain:
        return "\n".join(lines)
    return "\n".join(["```text", *lines, "```"])
