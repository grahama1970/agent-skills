"""CLI: DAG JSON -> PHART 1.5 ASCII decision tree."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import networkx as nx
from phart import ASCIIRenderer, LayoutOptions, NodeStyle


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


def render_chart(dag: dict[str, Any]) -> str:
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
    graph_id = str(dag.get("graph_id") or "ask-dag")
    header = [
        "```text",
        f"DAG decision tree · {graph_id} (phart 1.5 git)",
        f"schema={dag.get('schema_version', dag.get('exec_graph_version', ''))}",
        "",
    ]
    footer = ["", "renderer: phart@github.com/scottvr/phart · layout=layered · bboxes"]
    return "\n".join(header + [body] + footer + ["```"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Render ask DAG JSON with PHART 1.5")
    parser.add_argument("dag_file", type=Path)
    args = parser.parse_args()
    dag = json.loads(args.dag_file.read_text(encoding="utf-8"))
    print(render_chart(dag))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
