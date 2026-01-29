#!/usr/bin/env python3
"""
NetworkX backend for fixture-graph skill.

Handles NetworkX-based visualizations:
- Force-directed graphs
- Network topology
- D3.js JSON export
- Graph manipulation and analysis
"""

import json
from pathlib import Path
from typing import Any, Dict, List

import typer

from config import IEEE_DOUBLE_COLUMN, DependencyNode
from utils import check_networkx, check_matplotlib, apply_ieee_style, get_numpy


def networkx_to_d3_json(G) -> Dict[str, Any]:
    """Convert NetworkX graph to D3.js-compatible JSON format."""
    nodes = []
    for node, attrs in G.nodes(data=True):
        node_data = {"id": str(node), "name": str(node)}
        node_data.update(attrs)
        nodes.append(node_data)

    links = []
    for source, target, attrs in G.edges(data=True):
        link_data = {"source": str(source), "target": str(target)}
        link_data.update(attrs)
        links.append(link_data)

    return {"nodes": nodes, "links": links}


def generate_networkx_dep_graph(
    modules: Dict[str, DependencyNode],
    output_path: Path,
    format: str,
) -> bool:
    """Generate NetworkX dependency graph and export."""
    if not check_networkx():
        typer.echo("[ERROR] NetworkX not available", err=True)
        return False

    import networkx as nx
    np = get_numpy()

    G = nx.DiGraph()
    internal_modules = set(modules.keys())

    for name, node in modules.items():
        G.add_node(name, module_type=node.module_type, loc=node.loc)

        for imp in set(node.imports):
            if imp in internal_modules:
                G.add_edge(name, imp)

    # Export based on format
    if format == "json":
        d3_data = networkx_to_d3_json(G)
        output_path.write_text(json.dumps(d3_data, indent=2))
        return True
    elif format in ("dot", "gv"):
        from networkx.drawing.nx_pydot import to_pydot
        pydot_graph = to_pydot(G)
        output_path.write_text(pydot_graph.to_string())
        return True
    else:
        # Render with matplotlib
        if not check_matplotlib():
            typer.echo("[ERROR] matplotlib not available for rendering", err=True)
            return False

        import matplotlib.pyplot as plt
        apply_ieee_style()

        fig, ax = plt.subplots(figsize=(IEEE_DOUBLE_COLUMN, 4))
        pos = nx.spring_layout(G, k=2, iterations=50)
        nx.draw(G, pos, ax=ax, with_labels=True, node_color="lightblue",
                node_size=1000, font_size=7, arrows=True,
                arrowsize=10, edge_color="#666666")

        plt.tight_layout()
        plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
        plt.close()
        return True


def generate_force_directed(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    output_path: Path,
    title: str = "Network",
    format: str = "pdf",
) -> bool:
    """
    Generate force-directed graph for system topology or fault trees.

    Args:
        nodes: List of {id, label, group?} dicts
        edges: List of {source, target, weight?} dicts
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg, json)

    Returns:
        True if successful, False otherwise
    """
    if not check_networkx():
        typer.echo("[ERROR] NetworkX required for force-directed graphs", err=True)
        return False

    import networkx as nx
    np = get_numpy()

    G = nx.Graph()

    # Add nodes with attributes
    for node in nodes:
        G.add_node(node.get('id', node.get('label', '')),
                  label=node.get('label', ''),
                  group=node.get('group', 0))

    # Add edges
    for edge in edges:
        G.add_edge(edge['source'], edge['target'],
                  weight=edge.get('weight', 1))

    # Export to D3 JSON format
    if format == "json":
        d3_data = networkx_to_d3_json(G)
        output_path.write_text(json.dumps(d3_data, indent=2))
        return True

    # Render with matplotlib
    if not check_matplotlib():
        typer.echo("[ERROR] matplotlib required for rendering", err=True)
        return False

    import matplotlib.pyplot as plt
    import numpy as np_real
    apply_ieee_style()

    fig, ax = plt.subplots(figsize=(IEEE_DOUBLE_COLUMN, 4))

    # Use spring layout (force-directed)
    pos = nx.spring_layout(G, k=2, iterations=50, seed=42)

    # Color by group if available
    groups = [G.nodes[n].get('group', 0) for n in G.nodes()]
    colors = plt.cm.Set3(np_real.array(groups) % 12)

    nx.draw(G, pos, ax=ax,
            with_labels=True,
            node_color=colors,
            node_size=800,
            font_size=7,
            edge_color="#666666",
            width=1,
            alpha=0.9)

    ax.set_title(title, fontweight="bold")
    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_pert_network(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    output_path: Path,
    title: str = "PERT Network",
    format: str = "pdf",
) -> bool:
    """
    Generate PERT network diagram for project planning.

    Args:
        nodes: List of {id, label, x?, y?} dicts (activities/milestones)
        edges: List of {source, target, label?, critical?} dicts
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)

    Returns:
        True if successful, False otherwise
    """
    if not check_networkx() or not check_matplotlib():
        typer.echo("[ERROR] NetworkX and matplotlib required for PERT network", err=True)
        return False

    import networkx as nx
    import matplotlib.pyplot as plt
    apply_ieee_style()

    G = nx.DiGraph()

    for node in nodes:
        G.add_node(node['id'], label=node.get('label', node['id']))

    for edge in edges:
        G.add_edge(edge['source'], edge['target'],
                  label=edge.get('label', ''),
                  critical=edge.get('critical', False))

    fig, ax = plt.subplots(figsize=(IEEE_DOUBLE_COLUMN, 3))

    # Use hierarchical layout if possible
    try:
        pos = nx.planar_layout(G)
    except nx.NetworkXException:
        pos = nx.spring_layout(G, k=2, seed=42)

    # Draw non-critical edges
    non_critical = [(u, v) for u, v, d in G.edges(data=True) if not d.get('critical')]
    nx.draw_networkx_edges(G, pos, edgelist=non_critical, ax=ax,
                          edge_color='gray', arrows=True, arrowsize=15,
                          connectionstyle="arc3,rad=0.1")

    # Draw critical path in red
    critical = [(u, v) for u, v, d in G.edges(data=True) if d.get('critical')]
    nx.draw_networkx_edges(G, pos, edgelist=critical, ax=ax,
                          edge_color='red', width=2, arrows=True, arrowsize=15,
                          connectionstyle="arc3,rad=0.1")

    # Draw nodes
    nx.draw_networkx_nodes(G, pos, ax=ax, node_color='lightblue',
                          node_size=800, edgecolors='black', linewidths=1)

    # Draw labels
    labels = nx.get_node_attributes(G, 'label')
    nx.draw_networkx_labels(G, pos, labels, ax=ax, font_size=7)

    # Draw edge labels
    edge_labels = nx.get_edge_attributes(G, 'label')
    nx.draw_networkx_edge_labels(G, pos, edge_labels, ax=ax, font_size=6)

    ax.set_title(title, fontweight="bold")
    ax.axis('off')

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True
