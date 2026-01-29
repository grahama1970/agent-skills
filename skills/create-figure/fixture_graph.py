#!/usr/bin/env python3
"""
Fixture-graph: Publication-quality figure generation for AI agents.

This is the CLI entry point. All visualization logic is in specialized modules:
- config.py: Constants, IEEE settings, domain groups
- utils.py: Backend checks, style utilities
- graphviz_backend.py: DOT/Graphviz rendering
- mermaid_backend.py: Mermaid diagram generation
- networkx_backend.py: NetworkX/D3 visualizations
- matplotlib_backend.py: Core matplotlib plots
- plotly_backend.py: Interactive Plotly charts
- control_systems.py: Control/aerospace visualizations
- ml_visualizations.py: ML/LLM evaluation plots
- analysis.py: Code analysis and architecture diagrams
- validation.py: Input validation framework
"""

import json
from pathlib import Path
from typing import List, Optional

import typer

# Import configuration
from config import (
    DOMAIN_GROUPS,
    DATA_TYPE_RECOMMENDATIONS,
    IEEE_FIGURE_SIZES,
    COLORBLIND_SAFE_CMAPS,
    PROBLEMATIC_CMAPS,
    LEAN4_PROVE_SCRIPT,
)

# Import utilities
from utils import (
    check_graphviz,
    check_mermaid,
    check_matplotlib,
    check_seaborn,
    check_plotly,
    check_networkx,
    check_pandas,
    check_squarify,
    check_scipy,
    check_control,
    check_pydeps,
    check_pyreverse,
)

# Import validation (optional)
try:
    from validation import (
        ValidationError,
        validate_json_file,
        validate_scaling_data,
        validate_metrics_data,
        validate_flow_data,
        create_validation_error_message,
    )
    VALIDATION_AVAILABLE = True
except ImportError:
    VALIDATION_AVAILABLE = False
    class ValidationError(Exception):
        pass

# Create Typer app
app = typer.Typer(
    name="fixture-graph",
    help="Generate publication-quality figures for papers and documentation.",
    no_args_is_help=True,
)


# =============================================================================
# Core Commands
# =============================================================================

@app.command()
def deps(
    project: str = typer.Option(..., "--project", "-p", help="Path to Python project"),
    output: str = typer.Option("dependencies.pdf", "--output", "-o", help="Output file"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg, dot, json"),
    depth: int = typer.Option(2, "--depth", "-d", help="Maximum dependency depth"),
    backend: str = typer.Option("graphviz", "--backend", "-b", help="Backend: graphviz, mermaid, networkx"),
) -> None:
    """Generate dependency graph from Python project."""
    from graphviz_backend import generate_dependency_graph

    project_path = Path(project)
    output_path = Path(output)

    success = generate_dependency_graph(project_path, output_path, format, depth, backend)
    if success:
        typer.echo(f"Generated: {output_path}")
    else:
        fallback = output_path.with_suffix(".dot" if backend == "graphviz" else ".mmd")
        if fallback.exists():
            typer.echo(f"Generated fallback: {fallback}")


@app.command()
def uml(
    project: str = typer.Option(..., "--project", "-p", help="Path to Python project"),
    output: str = typer.Option("classes.pdf", "--output", "-o", help="Output file"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg"),
) -> None:
    """Generate UML class diagram from Python project."""
    from graphviz_backend import generate_class_diagram

    project_path = Path(project)
    output_path = Path(output)

    success = generate_class_diagram(project_path, output_path, format)
    if success:
        typer.echo(f"Generated: {output_path}")


@app.command()
def architecture(
    project: str = typer.Option(..., "--project", "-p", help="Project path or assess JSON"),
    output: str = typer.Option("architecture.pdf", "--output", "-o", help="Output file"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg"),
    backend: str = typer.Option("graphviz", "--backend", "-b", help="Backend: graphviz, mermaid"),
) -> None:
    """Generate architecture diagram from project or assess output."""
    from analysis import generate_architecture_diagram

    output_path = Path(output)
    project_path = Path(project)

    if project_path.suffix == ".json" and project_path.exists():
        data = json.loads(project_path.read_text())
        components = data.get("components", [])
        project_name = data.get("project_name", project_path.stem)
    else:
        project_name = project_path.name if project_path.exists() else project
        components = [
            {"name": "Core", "type": "module"},
            {"name": "CLI", "type": "interface"},
            {"name": "Config", "type": "config"},
        ]

    success = generate_architecture_diagram(project_name, components, output_path, format, backend)
    if success:
        typer.echo(f"Generated: {output_path}")
    else:
        fallback = output_path.with_suffix(".dot" if backend == "graphviz" else ".mmd")
        if fallback.exists():
            typer.echo(f"Generated fallback: {fallback}")


@app.command()
def metrics(
    input: str = typer.Option(..., "--input", "-i", help="Input JSON file with metrics"),
    output: str = typer.Option("metrics.pdf", "--output", "-o", help="Output file"),
    type: str = typer.Option("bar", "--type", "-t", help="Chart type: bar, hbar, pie, line"),
    title: str = typer.Option("Code Metrics", "--title", help="Chart title"),
) -> None:
    """Generate metrics chart from JSON data."""
    from matplotlib_backend import generate_metrics_chart

    input_path = Path(input)
    output_path = Path(output)

    try:
        if VALIDATION_AVAILABLE:
            data = validate_json_file(input_path, "metrics data")
        else:
            data = json.loads(input_path.read_text())

        if isinstance(data, dict):
            metrics_data = data.get("metrics", data)
        elif isinstance(data, list):
            metrics_data = {item.get("name", f"item{i}"): item.get("value", 0)
                           for i, item in enumerate(data)}
        else:
            raise ValidationError("Invalid input format")

        if VALIDATION_AVAILABLE:
            metrics_data = validate_metrics_data(metrics_data)

    except ValidationError as e:
        typer.echo(f"[ERROR] {create_validation_error_message(e) if VALIDATION_AVAILABLE else str(e)}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"[ERROR] Failed to load input data: {e}", err=True)
        raise typer.Exit(1)

    format_ext = output_path.suffix.lstrip(".")
    success = generate_metrics_chart(title, metrics_data, output_path, type, format_ext)
    if success:
        typer.echo(f"Generated: {output_path}")
    else:
        typer.echo("[ERROR] Chart generation failed", err=True)
        raise typer.Exit(1)


@app.command()
def table(
    input: str = typer.Option(..., "--input", "-i", help="Input JSON file"),
    output: str = typer.Option("table.tex", "--output", "-o", help="Output .tex file"),
    caption: str = typer.Option("", "--caption", "-c", help="Table caption"),
) -> None:
    """Generate LaTeX table from JSON data."""
    from matplotlib_backend import generate_latex_table

    input_path = Path(input)
    output_path = Path(output)

    if not input_path.exists():
        typer.echo(f"[ERROR] Input file not found: {input_path}", err=True)
        raise typer.Exit(1)

    data = json.loads(input_path.read_text())

    if isinstance(data, dict):
        if "headers" in data and "rows" in data:
            headers = data["headers"]
            rows = data["rows"]
        else:
            headers = ["Key", "Value"]
            rows = [[k, str(v)] for k, v in data.items()]
    elif isinstance(data, list) and data:
        if isinstance(data[0], dict):
            headers = list(data[0].keys())
            rows = [[str(item.get(h, "")) for h in headers] for item in data]
        else:
            headers = ["Item"]
            rows = [[str(item)] for item in data]
    else:
        typer.echo("[ERROR] Invalid input format", err=True)
        raise typer.Exit(1)

    success = generate_latex_table("Data", headers, rows, output_path, caption or None)
    if success:
        typer.echo(f"Generated: {output_path}")


@app.command()
def workflow(
    stages: str = typer.Option(..., "--stages", "-s", help="Comma-separated stage names"),
    output: str = typer.Option("workflow.pdf", "--output", "-o", help="Output file"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg, mmd"),
    gates: bool = typer.Option(True, "--gates/--no-gates", help="Include quality gates"),
    backend: str = typer.Option("mermaid", "--backend", "-b", help="Backend: mermaid, graphviz"),
) -> None:
    """Generate workflow diagram from stage list."""
    from analysis import generate_workflow_diagram

    stage_list = [s.strip() for s in stages.split(",")]
    output_path = Path(output)

    success = generate_workflow_diagram(stage_list, output_path, format, gates, backend)
    if success:
        typer.echo(f"Generated: {output_path}")
    else:
        fallback = output_path.with_suffix(".mmd" if backend == "mermaid" else ".dot")
        if fallback.exists():
            typer.echo(f"Generated fallback: {fallback}")


@app.command()
def theorem(
    requirement: str = typer.Option(..., "--requirement", "-r", help="Requirement to formalize"),
    name: str = typer.Option("theorem", "--name", "-n", help="Theorem name"),
    output: str = typer.Option("theorem.lean", "--output", "-o", help="Output .lean file"),
) -> None:
    """Generate formally verified theorem from requirement (uses lean4-prove)."""
    from analysis import generate_lean4_theorem_figure

    output_path = Path(output)
    success = generate_lean4_theorem_figure(requirement, name, output_path)
    if success:
        typer.echo(f"Generated: {output_path}")


# =============================================================================
# Visualization Commands - Grouped by Domain
# =============================================================================

@app.command()
def heatmap(
    input: str = typer.Option(..., "--input", "-i", help="JSON file with nested dict {row: {col: value}}"),
    output: str = typer.Option("heatmap.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Heatmap", "--title", "-t", help="Chart title"),
    cmap: str = typer.Option("Blues", "--cmap", "-c", help="Colormap: Blues, viridis, plasma, etc."),
) -> None:
    """Generate heatmap for field distributions or correlation matrices."""
    from matplotlib_backend import generate_heatmap

    input_path = Path(input)
    output_path = Path(output)

    if not input_path.exists():
        typer.echo(f"[ERROR] Input file not found: {input_path}", err=True)
        raise typer.Exit(1)

    data = json.loads(input_path.read_text())
    format_ext = output_path.suffix.lstrip(".")

    success = generate_heatmap(data, output_path, title, format_ext, cmap)
    if success:
        typer.echo(f"Generated: {output_path}")


@app.command()
def sankey(
    input: str = typer.Option(..., "--input", "-i", help="JSON file with flows [{source, target, value}]"),
    output: str = typer.Option("sankey.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Flow Diagram", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg, html"),
) -> None:
    """Generate Sankey diagram for flow/energy/mass balances."""
    from plotly_backend import generate_sankey_diagram

    input_path = Path(input)
    output_path = Path(output)

    try:
        if VALIDATION_AVAILABLE:
            data = validate_json_file(input_path, "flow data")
        else:
            data = json.loads(input_path.read_text())

        flows = data if isinstance(data, list) else data.get("flows", [])

        if VALIDATION_AVAILABLE:
            flows = validate_flow_data(flows)

    except ValidationError as e:
        typer.echo(f"[ERROR] {create_validation_error_message(e) if VALIDATION_AVAILABLE else str(e)}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"[ERROR] Failed to load input data: {e}", err=True)
        raise typer.Exit(1)

    success = generate_sankey_diagram(flows, output_path, title, format)
    if success:
        typer.echo(f"Generated: {output_path}")


@app.command()
def treemap(
    input: str = typer.Option(..., "--input", "-i", help="JSON file with {label: size} dict"),
    output: str = typer.Option("treemap.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Treemap", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg, html"),
) -> None:
    """Generate treemap for hierarchical size data (modules, zones, etc.)."""
    from plotly_backend import generate_treemap

    input_path = Path(input)
    output_path = Path(output)

    if not input_path.exists():
        typer.echo(f"[ERROR] Input file not found: {input_path}", err=True)
        raise typer.Exit(1)

    data = json.loads(input_path.read_text())

    success = generate_treemap(data, output_path, title, format)
    if success:
        typer.echo(f"Generated: {output_path}")


@app.command()
def sunburst(
    input: str = typer.Option(..., "--input", "-i", help="JSON file with nested hierarchy"),
    output: str = typer.Option("sunburst.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Sunburst", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg, html"),
) -> None:
    """Generate sunburst chart for hierarchical fault trees or breakdowns."""
    from plotly_backend import generate_sunburst

    input_path = Path(input)
    output_path = Path(output)

    if not input_path.exists():
        typer.echo(f"[ERROR] Input file not found: {input_path}", err=True)
        raise typer.Exit(1)

    hierarchy = json.loads(input_path.read_text())

    success = generate_sunburst(hierarchy, output_path, title, format)
    if success:
        typer.echo(f"Generated: {output_path}")


@app.command("force-graph")
def force_graph(
    input: str = typer.Option(..., "--input", "-i", help="JSON file with {nodes: [...], edges: [...]}"),
    output: str = typer.Option("network.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Network", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg, json"),
    summary: bool = typer.Option(False, "--summary", "-s", help="Output JSON summary for agents"),
) -> None:
    """Generate force-directed graph for system topology or fault trees."""
    from networkx_backend import generate_force_directed

    input_path = Path(input)
    output_path = Path(output)

    if not input_path.exists():
        typer.echo(f"[ERROR] Input file not found: {input_path}", err=True)
        raise typer.Exit(1)

    data = json.loads(input_path.read_text())
    nodes = data.get("nodes", [])
    edges = data.get("edges", data.get("links", []))

    success = generate_force_directed(nodes, edges, output_path, title, format)
    if success:
        if summary:
            summary_data = {
                "status": "success",
                "output_file": str(output_path.absolute()),
                "format": format,
                "graph_type": "force_directed",
                "metrics": {
                    "nodes": len(nodes),
                    "edges": len(edges),
                    "density": (2 * len(edges)) / (len(nodes) * (len(nodes) - 1)) if len(nodes) > 1 else 0,
                },
            }
            typer.echo(json.dumps(summary_data, indent=2))
        else:
            typer.echo(f"Generated: {output_path}")


@app.command("parallel-coords")
def parallel_coords(
    input: str = typer.Option(..., "--input", "-i", help="JSON file with list of dicts [{dim1, dim2, ...}]"),
    output: str = typer.Option("parallel.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Parallel Coordinates", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg, html"),
    color_by: str = typer.Option("", "--color-by", "-c", help="Dimension to color by"),
) -> None:
    """Generate parallel coordinates for multi-dimensional design space analysis."""
    from plotly_backend import generate_parallel_coordinates

    input_path = Path(input)
    output_path = Path(output)

    if not input_path.exists():
        typer.echo(f"[ERROR] Input file not found: {input_path}", err=True)
        raise typer.Exit(1)

    data = json.loads(input_path.read_text())

    success = generate_parallel_coordinates(data, output_path, title, format, color_by if color_by else None)
    if success:
        typer.echo(f"Generated: {output_path}")


@app.command()
def radar(
    input: str = typer.Option(..., "--input", "-i", help="JSON file with {series: {dim: value}}"),
    output: str = typer.Option("radar.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Radar Chart", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg"),
) -> None:
    """Generate radar/spider chart for multi-attribute comparison."""
    from matplotlib_backend import generate_radar_chart

    input_path = Path(input)
    output_path = Path(output)

    if not input_path.exists():
        typer.echo(f"[ERROR] Input file not found: {input_path}", err=True)
        raise typer.Exit(1)

    data = json.loads(input_path.read_text())

    success = generate_radar_chart(data, output_path, title, format)
    if success:
        typer.echo(f"Generated: {output_path}")


# =============================================================================
# Control Systems Commands
# =============================================================================

@app.command()
def bode(
    num: str = typer.Option(..., "--num", "-n", help="Numerator coefficients: 1,2,3"),
    den: str = typer.Option(..., "--den", "-d", help="Denominator coefficients: 1,2,3,4"),
    output: str = typer.Option("bode.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Bode Plot", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg"),
    freq_min: float = typer.Option(0.01, "--freq-min", help="Min frequency (rad/s)"),
    freq_max: float = typer.Option(100.0, "--freq-max", help="Max frequency (rad/s)"),
) -> None:
    """Generate Bode plot (magnitude/phase vs frequency) for control systems."""
    from control_systems import generate_bode_plot

    output_path = Path(output)
    num_list = [float(x.strip()) for x in num.split(",")]
    den_list = [float(x.strip()) for x in den.split(",")]

    success = generate_bode_plot(num_list, den_list, output_path, title, format, (freq_min, freq_max))
    if success:
        typer.echo(f"Generated: {output_path}")


@app.command()
def nyquist(
    num: str = typer.Option(..., "--num", "-n", help="Numerator coefficients: 1,2,3"),
    den: str = typer.Option(..., "--den", "-d", help="Denominator coefficients: 1,2,3,4"),
    output: str = typer.Option("nyquist.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Nyquist Plot", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg"),
) -> None:
    """Generate Nyquist plot for stability analysis of control systems."""
    from control_systems import generate_nyquist_plot

    output_path = Path(output)
    num_list = [float(x.strip()) for x in num.split(",")]
    den_list = [float(x.strip()) for x in den.split(",")]

    success = generate_nyquist_plot(num_list, den_list, output_path, title, format)
    if success:
        typer.echo(f"Generated: {output_path}")


@app.command()
def rootlocus(
    num: str = typer.Option(..., "--num", "-n", help="Numerator coefficients: 1,2,3"),
    den: str = typer.Option(..., "--den", "-d", help="Denominator coefficients: 1,2,3,4"),
    output: str = typer.Option("rootlocus.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Root Locus", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg"),
    breakaway: bool = typer.Option(True, "--breakaway/--no-breakaway", help="Show breakaway points"),
    gain_min: float = typer.Option(0.01, "--gain-min", help="Minimum gain for analysis"),
    gain_max: float = typer.Option(100.0, "--gain-max", help="Maximum gain for analysis"),
) -> None:
    """Generate enhanced root locus plot for control system gain analysis."""
    from control_systems import generate_root_locus

    output_path = Path(output)
    num_list = [float(x.strip()) for x in num.split(",")]
    den_list = [float(x.strip()) for x in den.split(",")]

    success = generate_root_locus(num_list, den_list, output_path, title, format, breakaway, (gain_min, gain_max))
    if success:
        typer.echo(f"Generated: {output_path}")


@app.command("pole-zero")
def pole_zero(
    zeros: str = typer.Option("", "--zeros", "-z", help="Zero locations: 1+2j,1-2j,3"),
    poles: str = typer.Option(..., "--poles", "-p", help="Pole locations: -1+2j,-1-2j,-3"),
    output: str = typer.Option("polezero.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Pole-Zero Map", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg"),
    discrete: bool = typer.Option(False, "--discrete/--continuous", help="Discrete-time system"),
    sample_time: float = typer.Option(1.0, "--sample-time", help="Sample time for discrete systems"),
    damping: bool = typer.Option(True, "--damping/--no-damping", help="Show damping ratio lines"),
) -> None:
    """Generate pole-zero map with stability analysis for control systems."""
    from control_systems import generate_pole_zero_map

    output_path = Path(output)

    def parse_complex_list(s: str) -> List[complex]:
        if not s.strip():
            return []
        return [complex(x.strip()) for x in s.split(",")]

    zeros_list = parse_complex_list(zeros)
    poles_list = parse_complex_list(poles)

    success = generate_pole_zero_map(zeros_list, poles_list, output_path, title, format,
                                     True, damping, discrete, sample_time if discrete else None)
    if success:
        typer.echo(f"Generated: {output_path}")


# =============================================================================
# ML/LLM Visualization Commands
# =============================================================================

@app.command("confusion-matrix")
def confusion_matrix(
    input: str = typer.Option(..., "--input", "-i", help="JSON file with matrix and labels"),
    output: str = typer.Option("confusion.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Confusion Matrix", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg"),
    normalize: bool = typer.Option(False, "--normalize/--raw", help="Normalize to percentages"),
    cmap: str = typer.Option("Blues", "--cmap", "-c", help="Colormap"),
) -> None:
    """Generate confusion matrix for classification results."""
    from ml_visualizations import generate_confusion_matrix

    input_path = Path(input)
    output_path = Path(output)

    if not input_path.exists():
        typer.echo(f"[ERROR] Input file not found: {input_path}", err=True)
        raise typer.Exit(1)

    data = json.loads(input_path.read_text())
    matrix = data.get('matrix', [[]])
    labels = data.get('labels', [])

    success = generate_confusion_matrix(matrix, labels, output_path, title, format, normalize, cmap)
    if success:
        typer.echo(f"Generated: {output_path}")


@app.command("roc-curve")
def roc_curve(
    input: str = typer.Option(..., "--input", "-i", help="JSON file with {name: {fpr, tpr, auc}}"),
    output: str = typer.Option("roc.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("ROC Curve", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg"),
) -> None:
    """Generate ROC curve for binary classification."""
    from ml_visualizations import generate_roc_curve

    input_path = Path(input)
    output_path = Path(output)

    if not input_path.exists():
        typer.echo(f"[ERROR] Input file not found: {input_path}", err=True)
        raise typer.Exit(1)

    curves = json.loads(input_path.read_text())

    success = generate_roc_curve(curves, output_path, title, format)
    if success:
        typer.echo(f"Generated: {output_path}")


@app.command("training-curves")
def training_curves(
    input: str = typer.Option(..., "--input", "-i", help="JSON file with {name: {x, y, std}}"),
    output: str = typer.Option("training.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Training Curves", "--title", "-t", help="Chart title"),
    x_label: str = typer.Option("Step", "--x-label", help="X-axis label"),
    y_label: str = typer.Option("Loss", "--y-label", help="Y-axis label"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg"),
    log_y: bool = typer.Option(False, "--log-y/--linear-y", help="Use log scale for Y"),
) -> None:
    """Generate training curves for multiple runs."""
    from ml_visualizations import generate_training_curves

    input_path = Path(input)
    output_path = Path(output)

    if not input_path.exists():
        typer.echo(f"[ERROR] Input file not found: {input_path}", err=True)
        raise typer.Exit(1)

    runs = json.loads(input_path.read_text())

    success = generate_training_curves(runs, output_path, x_label, y_label, title, format, log_y)
    if success:
        typer.echo(f"Generated: {output_path}")


@app.command("scaling-law")
def scaling_law(
    input: str = typer.Option(..., "--input", "-i", help="JSON file with [{x: params, y: loss}] or {x: [..], y: [..]}"),
    output: str = typer.Option("scaling.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Scaling Law", "--title", "-t", help="Chart title"),
    x_label: str = typer.Option("Parameters", "--x-label", help="X-axis label"),
    y_label: str = typer.Option("Loss", "--y-label", help="Y-axis label"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg"),
    fit: bool = typer.Option(True, "--fit/--no-fit", help="Fit power law"),
) -> None:
    """Generate scaling law plot (log-log) common in LLM research."""
    from ml_visualizations import generate_scaling_law_plot

    input_path = Path(input)
    output_path = Path(output)

    try:
        if VALIDATION_AVAILABLE:
            data = validate_json_file(input_path, "scaling law data")
            data = validate_scaling_data(data)
        else:
            data = json.loads(input_path.read_text())
            if isinstance(data, dict) and 'x' in data and 'y' in data:
                data = [{'x': x, 'y': y} for x, y in zip(data['x'], data['y'])]
    except ValidationError as e:
        typer.echo(f"[ERROR] {create_validation_error_message(e) if VALIDATION_AVAILABLE else str(e)}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"[ERROR] Failed to load input data: {e}", err=True)
        raise typer.Exit(1)

    success = generate_scaling_law_plot(data, output_path, x_label, y_label, title, format, fit)
    if success:
        typer.echo(f"Generated: {output_path}")


# =============================================================================
# Utility Commands
# =============================================================================

@app.command()
def check() -> None:
    """Check available backends and dependencies."""
    typer.echo("Checking fixture-graph backends...")
    typer.echo("")

    checks = [
        ("Graphviz (dot)", check_graphviz()),
        ("Mermaid (mmdc)", check_mermaid()),
        ("matplotlib", check_matplotlib()),
        ("seaborn", check_seaborn()),
        ("plotly", check_plotly()),
        ("NetworkX", check_networkx()),
        ("pandas", check_pandas()),
        ("squarify", check_squarify()),
        ("scipy", check_scipy()),
        ("python-control", check_control()),
        ("pydeps", check_pydeps()),
        ("pyreverse", check_pyreverse()),
        ("lean4-prove", LEAN4_PROVE_SCRIPT.exists()),
    ]

    for name, available in checks:
        status = "[OK]" if available else "[NOT AVAILABLE]"
        typer.echo(f"  {name}: {status}")

    typer.echo("")
    available_count = sum(1 for _, a in checks if a)
    typer.echo(f"{available_count}/{len(checks)} backends available")


@app.command()
def domains() -> None:
    """List available visualization domains."""
    typer.echo("Available Visualization Domains")
    typer.echo("=" * 50)
    typer.echo("")

    for domain_name, info in DOMAIN_GROUPS.items():
        typer.echo(f"  {domain_name.upper()}")
        typer.echo(f"    {info['description']}")
        typer.echo(f"    Use when: {info['use_when']}")
        typer.echo(f"    Commands: {len(info['commands'])}")
        typer.echo("")

    typer.echo("Usage:")
    typer.echo("  fixture-graph list --domain <domain>  # Show commands for domain")
    typer.echo("  fixture-graph recommend --data-type <type>  # Get suggestions")


@app.command()
def presets() -> None:
    """Show IEEE figure size presets and colorblind-safe colormaps."""
    typer.echo("IEEE Figure Size Presets")
    typer.echo("=" * 40)
    for name, (w, h) in IEEE_FIGURE_SIZES.items():
        typer.echo(f"  {name:15} {w:.2f}\" x {h:.2f}\"")

    typer.echo("")
    typer.echo("Colorblind-Safe Colormaps (Recommended)")
    typer.echo("=" * 40)
    for cmap in COLORBLIND_SAFE_CMAPS:
        typer.echo(f"  {cmap}")

    typer.echo("")
    typer.echo("Avoid These Colormaps (Accessibility Issues)")
    typer.echo("=" * 40)
    for cmap in PROBLEMATIC_CMAPS:
        typer.echo(f"  {cmap}")


@app.command("list")
def list_commands(
    domain: str = typer.Option("", "--domain", "-d", help="Filter by domain"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full command descriptions"),
) -> None:
    """List available commands, optionally filtered by domain."""
    if domain:
        domain_lower = domain.lower()
        if domain_lower not in DOMAIN_GROUPS:
            typer.echo(f"[ERROR] Unknown domain: {domain}", err=True)
            typer.echo(f"Available: {', '.join(DOMAIN_GROUPS.keys())}")
            raise typer.Exit(1)

        info = DOMAIN_GROUPS[domain_lower]
        typer.echo(f"Domain: {domain_lower.upper()} - {info['description']}")
        typer.echo(f"Use when: {info['use_when']}")
        typer.echo("")
        typer.echo("Commands:")
        for cmd in info["commands"]:
            typer.echo(f"  - {cmd}")
    else:
        typer.echo("All Visualization Commands by Domain")
        typer.echo("=" * 50)
        for domain_name, info in DOMAIN_GROUPS.items():
            typer.echo(f"\n{domain_name.upper()}: {info['description']}")
            typer.echo(f"  {', '.join(info['commands'])}")


@app.command()
def recommend(
    data_type: str = typer.Option("", "--data-type", "-t", help="Type of data"),
    show_types: bool = typer.Option(False, "--show-types", "-s", help="Show all supported data types"),
) -> None:
    """Recommend visualization commands based on data type."""
    if show_types or not data_type:
        typer.echo("Supported Data Types and Recommended Visualizations")
        typer.echo("=" * 50)
        for dt, commands in sorted(DATA_TYPE_RECOMMENDATIONS.items()):
            typer.echo(f"  {dt}: {', '.join(commands)}")
        typer.echo("")
        typer.echo("Usage: fixture-graph recommend --data-type <type>")
        return

    data_type_lower = data_type.lower().replace("-", "_").replace(" ", "_")
    if data_type_lower not in DATA_TYPE_RECOMMENDATIONS:
        typer.echo(f"[ERROR] Unknown data type: {data_type}", err=True)
        typer.echo(f"Available: {', '.join(sorted(DATA_TYPE_RECOMMENDATIONS.keys()))}")
        raise typer.Exit(1)

    commands = DATA_TYPE_RECOMMENDATIONS[data_type_lower]
    typer.echo(f"Recommended visualizations for '{data_type}':")
    typer.echo("")
    for i, cmd in enumerate(commands, 1):
        domain = "core"
        for d_name, d_info in DOMAIN_GROUPS.items():
            if cmd in d_info["commands"]:
                domain = d_name
                break
        typer.echo(f"  {i}. {cmd} (domain: {domain})")

    typer.echo("")
    typer.echo(f"Run: fixture-graph {commands[0]} --help  # for usage")


@app.command("from-assess")
def from_assess(
    input: str = typer.Option(..., "--input", "-i", help="Input JSON from /assess"),
    output_dir: str = typer.Option("./figures", "--output-dir", "-o", help="Output directory"),
    backend: str = typer.Option("graphviz", "--backend", "-b", help="Diagram backend: graphviz, mermaid"),
) -> None:
    """Generate all figures from /assess output."""
    from analysis import generate_from_assess

    input_path = Path(input)
    output_path = Path(output_dir)

    generated = generate_from_assess(input_path, output_path, backend)

    if generated:
        typer.echo(f"\nGenerated {len(generated)} figures")


if __name__ == "__main__":
    app()
