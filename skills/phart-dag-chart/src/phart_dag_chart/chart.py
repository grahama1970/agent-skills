"""Render validated DAG JSON to PHART 1.5 ASCII decision tree."""

from __future__ import annotations

from typing import Any

import networkx as nx
from phart import ASCIIRenderer, LayoutOptions, NodeStyle

from phart_dag_chart.dag_validate import validate_dag
from phart_dag_chart.errors import DagChartError


def _display_name(node: dict[str, Any]) -> str:
    short = str(node.get("type", "")).split(".")[-1]
    opt = "?" if node.get("allow_failure") else ""
    return f"{node['id']}\n{short}{opt}"[:40]


def dag_to_nx(dag: dict[str, Any]) -> nx.DiGraph:
    graph = nx.DiGraph()
    names = {node["id"]: _display_name(node) for node in dag["nodes"]}
    for node in dag["nodes"]:
        graph.add_node(names[node["id"]], label=names[node["id"]])
    for node in dag["nodes"]:
        child = names[node["id"]]
        for parent_id in node.get("depends_on", []):
            if parent_id in names:
                graph.add_edge(names[parent_id], child)
    return graph


def render_chart(dag: dict[str, Any], *, validate: bool = True) -> str:
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
        "```text",
        f"DAG decision tree · {graph_id} (phart 1.5 git)",
        f"schema={schema}",
        "",
    ]
    footer = ["", "renderer: phart@github.com/scottvr/phart · layout=layered · bboxes"]
    return "\n".join(header + [body] + footer + ["```"])
