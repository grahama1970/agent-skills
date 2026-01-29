#!/usr/bin/env python3
"""
Plotly backend for fixture-graph skill.

Handles interactive visualizations:
- Sankey diagrams
- Sunburst charts
- Treemaps
- Parallel coordinates
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

import typer

from utils import check_plotly, check_matplotlib, check_squarify, check_pandas, apply_ieee_style
from config import IEEE_SINGLE_COLUMN


def generate_sankey_diagram(
    flows: List[Dict[str, Any]],
    output_path: Path,
    title: str = "Flow Diagram",
    format: str = "pdf",
) -> bool:
    """
    Generate Sankey diagram for flow/energy/mass balances.

    Args:
        flows: List of {source, target, value} dicts
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg, html)

    Returns:
        True if successful, False otherwise
    """
    if check_plotly():
        return generate_plotly_sankey(flows, output_path, title, format)
    elif check_matplotlib():
        return generate_matplotlib_sankey(flows, output_path, title, format)
    else:
        typer.echo("[ERROR] plotly or matplotlib required for Sankey diagram", err=True)
        return False


def generate_plotly_sankey(
    flows: List[Dict[str, Any]],
    output_path: Path,
    title: str,
    format: str,
) -> bool:
    """Generate Sankey diagram using Plotly."""
    import plotly.graph_objects as go

    # Build node list from unique sources and targets
    all_nodes = []
    for flow in flows:
        if flow['source'] not in all_nodes:
            all_nodes.append(flow['source'])
        if flow['target'] not in all_nodes:
            all_nodes.append(flow['target'])

    # Create index mappings
    node_idx = {node: i for i, node in enumerate(all_nodes)}

    # Build link data
    sources = [node_idx[f['source']] for f in flows]
    targets = [node_idx[f['target']] for f in flows]
    values = [f['value'] for f in flows]

    fig = go.Figure(data=[go.Sankey(
        node=dict(
            pad=15,
            thickness=20,
            line=dict(color="black", width=0.5),
            label=all_nodes,
            color="lightblue"
        ),
        link=dict(
            source=sources,
            target=targets,
            value=values,
            color="rgba(100, 149, 237, 0.3)"
        )
    )])

    fig.update_layout(
        title_text=title,
        font_size=10,
        title_font_size=12,
        margin=dict(l=20, r=20, t=40, b=20),
    )

    if format == "html":
        fig.write_html(str(output_path))
    else:
        # For static formats, use kaleido
        try:
            fig.write_image(str(output_path), format=format, scale=3)
        except Exception as e:
            typer.echo(f"[ERROR] Failed to export to {format}: {e}", err=True)
            html_path = output_path.with_suffix(".html")
            fig.write_html(str(html_path))
            typer.echo(f"[INFO] Saved as HTML instead: {html_path}")
            return True

    return True


def generate_matplotlib_sankey(
    flows: List[Dict[str, Any]],
    output_path: Path,
    title: str,
    format: str,
) -> bool:
    """Generate Sankey diagram using matplotlib (fallback)."""
    try:
        from matplotlib.sankey import Sankey
        import matplotlib.pyplot as plt
    except ImportError:
        typer.echo("[ERROR] matplotlib.sankey not available", err=True)
        return False

    apply_ieee_style()

    # Matplotlib Sankey is quite limited; use simple horizontal bar representation
    fig, ax = plt.subplots(figsize=(7, 4))

    # For simple flows, just show as stacked bars
    sources = list(set(f['source'] for f in flows))
    for i, source in enumerate(sources):
        source_flows = [f for f in flows if f['source'] == source]
        left = 0
        for flow in source_flows:
            width = flow['value']
            ax.barh(i, width, left=left, label=flow['target'], edgecolor='black')
            ax.text(left + width/2, i, f"{flow['target']}: {width:.0f}",
                   ha='center', va='center', fontsize=7)
            left += width

    ax.set_yticks(range(len(sources)))
    ax.set_yticklabels(sources)
    ax.set_xlabel('Value')
    ax.set_title(title, fontweight="bold")
    ax.grid(True, axis='x', alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_sunburst(
    hierarchy: Dict[str, Any],
    output_path: Path,
    title: str = "Sunburst",
    format: str = "pdf",
) -> bool:
    """
    Generate sunburst chart for hierarchical fault trees or breakdowns.

    Args:
        hierarchy: Nested dict {name, value?, children?}
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg, html)

    Returns:
        True if successful, False otherwise
    """
    if not check_plotly():
        typer.echo("[ERROR] plotly required for sunburst charts", err=True)
        return False

    import plotly.express as px

    # Flatten hierarchy to parallel arrays
    ids = []
    labels = []
    parents = []
    values = []

    def walk_tree(node: Dict[str, Any], parent_id: str = ""):
        node_id = f"{parent_id}/{node.get('name', 'root')}" if parent_id else node.get('name', 'root')
        ids.append(node_id)
        labels.append(node.get('name', node_id))
        parents.append(parent_id)
        values.append(node.get('value', 1))

        for child in node.get('children', []):
            walk_tree(child, node_id)

    walk_tree(hierarchy)

    fig = px.sunburst(
        ids=ids,
        names=labels,
        parents=parents,
        values=values,
        title=title,
    )

    fig.update_layout(margin=dict(l=0, r=0, t=40, b=0))

    if format == "html":
        fig.write_html(str(output_path))
    else:
        try:
            fig.write_image(str(output_path), format=format, scale=3)
        except Exception as e:
            typer.echo(f"[ERROR] Failed to export to {format}: {e}", err=True)
            html_path = output_path.with_suffix(".html")
            fig.write_html(str(html_path))
            typer.echo(f"[INFO] Saved as HTML instead: {html_path}")

    return True


def generate_treemap(
    data: Dict[str, float],
    output_path: Path,
    title: str = "Treemap",
    format: str = "pdf",
) -> bool:
    """
    Generate treemap for hierarchical size data.

    Args:
        data: Dict of {label: size}
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg, html)

    Returns:
        True if successful, False otherwise
    """
    if check_plotly():
        return generate_plotly_treemap(data, output_path, title, format)
    elif check_squarify():
        return generate_matplotlib_treemap(data, output_path, title, format)
    else:
        typer.echo("[ERROR] plotly or squarify required for treemap", err=True)
        return False


def generate_plotly_treemap(
    data: Dict[str, float],
    output_path: Path,
    title: str,
    format: str,
) -> bool:
    """Generate treemap using Plotly."""
    import plotly.express as px

    labels = list(data.keys())
    values = list(data.values())
    parents = [""] * len(labels)  # All at root level

    fig = px.treemap(
        names=labels,
        parents=parents,
        values=values,
        title=title,
    )

    fig.update_layout(margin=dict(l=0, r=0, t=40, b=0))

    if format == "html":
        fig.write_html(str(output_path))
    else:
        try:
            fig.write_image(str(output_path), format=format, scale=3)
        except Exception:
            html_path = output_path.with_suffix(".html")
            fig.write_html(str(html_path))
            typer.echo(f"[INFO] Saved as HTML: {html_path}")

    return True


def generate_matplotlib_treemap(
    data: Dict[str, float],
    output_path: Path,
    title: str,
    format: str,
) -> bool:
    """Generate treemap using squarify + matplotlib."""
    import matplotlib.pyplot as plt
    import squarify
    import numpy as np

    apply_ieee_style()

    labels = list(data.keys())
    sizes = list(data.values())
    colors = plt.cm.Blues(np.linspace(0.3, 0.8, len(sizes)))

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN * 1.5, IEEE_SINGLE_COLUMN))

    squarify.plot(sizes=sizes, label=labels, color=colors, alpha=0.8,
                 ax=ax, text_kwargs={'fontsize': 7})

    ax.set_title(title, fontweight="bold")
    ax.axis('off')

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_parallel_coordinates(
    data: List[Dict[str, float]],
    output_path: Path,
    title: str = "Parallel Coordinates",
    format: str = "pdf",
    color_by: Optional[str] = None,
) -> bool:
    """
    Generate parallel coordinates plot for multi-dimensional design space.

    Args:
        data: List of dicts with numeric values for each dimension
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg, html)
        color_by: Column name to use for coloring

    Returns:
        True if successful, False otherwise
    """
    if not check_pandas():
        typer.echo("[ERROR] pandas required for parallel coordinates", err=True)
        return False

    import pandas as pd

    df = pd.DataFrame(data)
    dimensions = list(df.columns)

    if check_plotly():
        import plotly.express as px

        color_col = color_by if color_by and color_by in dimensions else dimensions[0]

        fig = px.parallel_coordinates(
            df,
            dimensions=dimensions,
            color=color_col,
            color_continuous_scale=px.colors.diverging.Tealrose,
            title=title,
        )

        fig.update_layout(margin=dict(l=60, r=60, t=60, b=40))

        if format == "html":
            fig.write_html(str(output_path))
        else:
            try:
                fig.write_image(str(output_path), format=format, scale=3)
            except Exception:
                html_path = output_path.with_suffix(".html")
                fig.write_html(str(html_path))
                typer.echo(f"[INFO] Saved as HTML: {html_path}")

        return True

    else:
        # Matplotlib fallback
        from pandas.plotting import parallel_coordinates
        import matplotlib.pyplot as plt

        apply_ieee_style()

        fig, ax = plt.subplots(figsize=(7, 4))

        # Need a category column for matplotlib parallel_coordinates
        if color_by and color_by in dimensions:
            # Use binned values as category
            df['_category'] = pd.qcut(df[color_by], q=4, labels=['Q1', 'Q2', 'Q3', 'Q4'])
        else:
            df['_category'] = 'all'

        parallel_coordinates(df, '_category', ax=ax, colormap='viridis')

        ax.set_title(title, fontweight="bold")
        ax.legend(loc='upper right', fontsize=7)

        plt.tight_layout()
        plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
        plt.close()
        return True
