#!/usr/bin/env python3
"""
fixture_graph.py - Generate publication-quality figures from code analysis.

Multi-backend architecture:
- Graphviz: Deterministic layouts, CI-friendly, algorithmic graphs
- Mermaid: Quick documentation diagrams, GitHub-compatible
- NetworkX: Graph manipulation, D3.js export for interactive
- matplotlib/seaborn: Publication-quality charts (IEEE settings)
- plotly: Interactive Sankey, sunburst, treemap charts
- pydeps: Python module dependency analysis
- pyreverse: UML class diagrams from Python code
- lean4-prove: Formally verified requirement theorems

Advanced D3-style visualizations:
- Force-directed graphs (NetworkX)
- Sankey diagrams (flow conservation)
- Heatmaps (field distributions)
- Chord diagrams (interdependencies)
- Treemap/pack layouts (hierarchical)
- Sunburst charts (fault hierarchy)
- Parallel coordinates (multi-dimensional)

Outputs: PDF (vector), PNG (300-600 DPI), SVG, DOT, MMD, HTML (interactive)
"""
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import typer

# Import validation framework
try:
    from validation import (
        ValidationError,
        validate_json_file,
        validate_scaling_data,
        validate_metrics_data,
        validate_flow_data,
        validate_heatmap_data,
        validate_network_data,
        validate_output_path,
        create_validation_error_message
    )
    VALIDATION_AVAILABLE = True
except ImportError:
    VALIDATION_AVAILABLE = False
    # Fallback validation functions
    class ValidationError(Exception):
        pass
    
    def validate_json_file(file_path: Path, expected_structure: str = "") -> Dict[str, Any]:
        if not file_path.exists():
            raise ValidationError(f"Input file not found: {file_path}")
        return json.loads(file_path.read_text())
    
    def validate_scaling_data(data: Any) -> List[Dict[str, float]]:
        # Simple fallback - assume it's correct format
        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and 'x' in data and 'y' in data:
            # Convert old format
            if isinstance(data['x'], list) and isinstance(data['y'], list):
                return [{'x': float(x), 'y': float(y)} for x, y in zip(data['x'], data['y'])]
        return data

app = typer.Typer(help="Generate publication-quality figures from code analysis")

# --- Constants ---
SKILLS_DIR = Path(__file__).parent.parent
LEAN4_PROVE_SCRIPT = SKILLS_DIR / "lean4-prove" / "run.sh"

# IEEE publication settings for matplotlib
IEEE_RC_PARAMS = {
    "font.family": "serif",
    "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
    "font.size": 8,
    "axes.labelsize": 8,
    "axes.titlesize": 9,
    "legend.fontsize": 7,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "figure.dpi": 300,
    "savefig.dpi": 600,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.02,
    "pdf.fonttype": 42,  # TrueType fonts for Illustrator compatibility
    "ps.fonttype": 42,
    "axes.linewidth": 0.5,
    "lines.linewidth": 1.0,
    "lines.markersize": 4,
    "grid.linewidth": 0.3,
}

# IEEE column widths (inches)
IEEE_SINGLE_COLUMN = 3.5
IEEE_DOUBLE_COLUMN = 7.16

# IEEE figure size presets (width, height) in inches
# Use these to ensure figures match column widths exactly
IEEE_FIGURE_SIZES = {
    "single": (3.5, 2.5),      # Single column, standard height
    "single_tall": (3.5, 4.0), # Single column, tall (for multi-panel)
    "double": (7.16, 3.0),     # Double column, standard height
    "double_tall": (7.16, 5.0),# Double column, tall
    "square": (3.5, 3.5),      # Square, single column width
}

# Colorblind-safe colormaps (recommended for accessibility)
# These work for readers with color vision deficiency
COLORBLIND_SAFE_CMAPS = [
    "viridis",    # Default, perceptually uniform, colorblind-safe
    "plasma",     # Perceptually uniform
    "cividis",    # Specifically designed for colorblind accessibility
    "gray",       # Grayscale, universally accessible
    "Blues",      # Sequential, single hue
    "Oranges",    # Sequential, single hue
]

# Colormaps to avoid for accessibility
PROBLEMATIC_CMAPS = ["jet", "rainbow", "hsv", "spectral"]

# =============================================================================
# DOMAIN GROUPING - Helps project agents choose the right visualization
# =============================================================================
# Each domain contains commands relevant to that field. Agents should:
# 1. Identify the domain of their project (aerospace, ML, etc.)
# 2. Use `fixture-graph domains` to see available domains
# 3. Use `fixture-graph list --domain <name>` to see relevant commands
# 4. Use `fixture-graph recommend --data-type <type>` for suggestions

DOMAIN_GROUPS = {
    "core": {
        "description": "Universal visualizations for any project",
        "commands": ["metrics", "table", "workflow", "architecture", "deps", "uml", "heatmap"],
        "use_when": "Basic project analysis, documentation, code structure",
    },
    "control": {
        "description": "Control systems, aerospace, flight dynamics",
        "commands": ["bode", "nyquist", "rootlocus", "pole-zero", "state-space", "filter-response"],
        "use_when": "Transfer functions, stability analysis, frequency response",
    },
    "field": {
        "description": "Field distributions, nuclear/thermal analysis, physics",
        "commands": ["contour", "vector-field", "phase-portrait", "heatmap", "polar"],
        "use_when": "Flux distributions, temperature fields, flow visualization",
    },
    "project": {
        "description": "Project management, scheduling, requirements",
        "commands": ["gantt", "pert", "radar", "sankey", "parallel-coords"],
        "use_when": "Schedules, resource allocation, multi-criteria comparison",
    },
    "math": {
        "description": "Pure mathematics, 3D visualization, complex analysis",
        "commands": ["3d-surface", "3d-contour", "complex-plane", "polar", "phase-portrait"],
        "use_when": "Mathematical functions, complex numbers, dynamical systems",
    },
    "ml": {
        "description": "Machine learning, LLM evaluation, model analysis",
        "commands": [
            "confusion-matrix", "roc-curve", "pr-curve", "training-curves",
            "attention-heatmap", "embedding-scatter", "scaling-law", "roofline",
            "throughput-latency", "feature-importance", "calibration"
        ],
        "use_when": "Model evaluation, benchmarks, training analysis, interpretability",
    },
    "bio": {
        "description": "Bioinformatics, medical research, genomics",
        "commands": ["violin", "volcano", "survival-curve", "manhattan"],
        "use_when": "Gene expression, clinical trials, GWAS studies",
    },
    "hierarchy": {
        "description": "Hierarchical data, breakdowns, fault trees",
        "commands": ["treemap", "sunburst", "force-graph", "sankey"],
        "use_when": "Component breakdowns, fault analysis, flow diagrams",
    },
}

# Data type to command recommendations
DATA_TYPE_RECOMMENDATIONS = {
    "time_series": ["training-curves", "line", "gantt"],
    "classification": ["confusion-matrix", "roc-curve", "pr-curve", "calibration"],
    "distribution": ["violin", "heatmap", "histogram"],
    "comparison": ["radar", "metrics", "parallel-coords"],
    "flow": ["sankey", "workflow", "force-graph"],
    "hierarchy": ["treemap", "sunburst", "architecture"],
    "correlation": ["heatmap", "embedding-scatter"],
    "frequency": ["bode", "nyquist", "spectrogram"],
    "spatial": ["contour", "vector-field", "heatmap"],
    "complex": ["complex-plane", "polar", "phase-portrait"],
    "dependencies": ["deps", "architecture", "force-graph"],
    "schedule": ["gantt", "pert", "workflow"],
    "performance": ["roofline", "throughput-latency", "scaling-law"],
    "genomics": ["manhattan", "volcano", "violin"],
    "survival": ["survival-curve"],
    "transfer_function": ["bode", "nyquist", "rootlocus", "pole-zero"],
}


@dataclass
class FigureConfig:
    """Configuration for figure generation."""
    title: str
    width: float = IEEE_SINGLE_COLUMN
    height: float = 2.5
    dpi: int = 600
    format: str = "pdf"
    style: str = "ieee"  # ieee, acm, arxiv


@dataclass
class DependencyNode:
    """A node in a dependency graph."""
    name: str
    module_type: str = "module"  # module, package, external
    loc: int = 0
    imports: List[str] = field(default_factory=list)
    imported_by: List[str] = field(default_factory=list)


# --- Backend Checks ---

def _check_graphviz() -> bool:
    """Check if Graphviz (dot) is available."""
    try:
        result = subprocess.run(["dot", "-V"], capture_output=True, timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _check_mermaid() -> bool:
    """Check if mermaid-cli (mmdc) is available."""
    try:
        result = subprocess.run(["mmdc", "--version"], capture_output=True, timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _check_matplotlib() -> bool:
    """Check if matplotlib is available."""
    try:
        import matplotlib
        return True
    except ImportError:
        return False


def _check_seaborn() -> bool:
    """Check if seaborn is available."""
    try:
        import seaborn
        return True
    except ImportError:
        return False


def _check_plotly() -> bool:
    """Check if plotly is available (for Sankey, sunburst, treemap)."""
    try:
        import plotly
        return True
    except ImportError:
        return False


def _check_squarify() -> bool:
    """Check if squarify is available (for treemaps with matplotlib)."""
    try:
        import squarify
        return True
    except ImportError:
        return False


def _check_pandas() -> bool:
    """Check if pandas is available."""
    try:
        import pandas
        return True
    except ImportError:
        return False


def _check_control() -> bool:
    """Check if python-control is available (Bode, Nyquist, root locus)."""
    try:
        import control
        return True
    except ImportError:
        return False


def _check_scipy() -> bool:
    """Check if scipy is available (signal processing, interpolation)."""
    try:
        import scipy
        return True
    except ImportError:
        return False


def _check_networkx() -> bool:
    """Check if NetworkX is available."""
    try:
        import networkx
        return True
    except ImportError:
        return False


def _check_pydeps() -> bool:
    """Check if pydeps is available."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pydeps", "--version"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _check_pyreverse() -> bool:
    """Check if pyreverse (from pylint) is available."""
    try:
        result = subprocess.run(["pyreverse", "--version"], capture_output=True, timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# --- Rendering Functions ---

def _apply_ieee_style():
    """Apply IEEE publication style to matplotlib."""
    import matplotlib.pyplot as plt
    for key, value in IEEE_RC_PARAMS.items():
        try:
            plt.rcParams[key] = value
        except KeyError:
            pass  # Skip if key doesn't exist in this matplotlib version


def _check_colormap_accessibility(cmap: str) -> None:
    """Warn if colormap has accessibility issues."""
    if cmap.lower() in [c.lower() for c in PROBLEMATIC_CMAPS]:
        typer.echo(
            f"[WARN] Colormap '{cmap}' is not colorblind-safe. "
            f"Consider: {', '.join(COLORBLIND_SAFE_CMAPS[:3])}",
            err=True
        )


def _get_ieee_figsize(preset: str = "single") -> tuple:
    """Get IEEE figure size preset.

    Args:
        preset: One of 'single', 'single_tall', 'double', 'double_tall', 'square'

    Returns:
        (width, height) tuple in inches
    """
    return IEEE_FIGURE_SIZES.get(preset, IEEE_FIGURE_SIZES["single"])


def _render_graphviz(dot_code: str, output_path: Path, format: str = "pdf") -> bool:
    """Render DOT code to file using Graphviz."""
    if not _check_graphviz():
        typer.echo("[WARN] Graphviz not available, saving as .dot file", err=True)
        output_path.with_suffix(".dot").write_text(dot_code)
        return False

    with tempfile.NamedTemporaryFile(mode="w", suffix=".dot", delete=False) as f:
        f.write(dot_code)
        dot_path = f.name

    try:
        result = subprocess.run(
            ["dot", f"-T{format}", "-o", str(output_path), dot_path],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            typer.echo(f"[ERROR] Graphviz: {result.stderr}", err=True)
            return False
        return True
    except subprocess.TimeoutExpired:
        typer.echo("[ERROR] Graphviz rendering timed out", err=True)
        return False
    finally:
        Path(dot_path).unlink(missing_ok=True)


def _render_mermaid(mermaid_code: str, output_path: Path, format: str = "pdf") -> bool:
    """Render Mermaid diagram to file."""
    # If format is mmd, just save the text directly
    if format == "mmd":
        mmd_output = output_path.with_suffix(".mmd") if output_path.suffix != ".mmd" else output_path
        mmd_output.write_text(mermaid_code)
        return True

    if not _check_mermaid():
        typer.echo("[WARN] mermaid-cli not available, saving as .mmd file", err=True)
        output_path.with_suffix(".mmd").write_text(mermaid_code)
        return False

    with tempfile.NamedTemporaryFile(mode="w", suffix=".mmd", delete=False) as f:
        f.write(mermaid_code)
        mmd_path = f.name

    try:
        result = subprocess.run(
            ["mmdc", "-i", mmd_path, "-o", str(output_path), "-e", format],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            typer.echo(f"[ERROR] Mermaid: {result.stderr}", err=True)
            return False
        return True
    except subprocess.TimeoutExpired:
        typer.echo("[ERROR] Mermaid rendering timed out", err=True)
        return False
    finally:
        Path(mmd_path).unlink(missing_ok=True)


def _networkx_to_d3_json(G) -> Dict[str, Any]:
    """Convert NetworkX graph to D3.js-compatible JSON format."""
    import networkx as nx

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


# --- Figure Generation Functions ---

def generate_dependency_graph(
    project_path: Path,
    output_path: Path,
    format: str = "pdf",
    max_depth: int = 2,
    backend: str = "graphviz",
) -> bool:
    """
    Generate dependency graph from Python project using pydeps.

    Args:
        project_path: Path to Python package/module
        output_path: Output file path
        format: Output format (pdf, png, svg, dot)
        max_depth: Maximum dependency depth (--max-bacon)
        backend: Rendering backend (graphviz, mermaid, networkx)

    Returns:
        True if successful, False otherwise
    """
    if not project_path.exists():
        typer.echo(f"[ERROR] Project path not found: {project_path}", err=True)
        return False

    # Try pydeps first (most accurate for Python)
    if _check_pydeps() and backend == "graphviz":
        try:
            # Generate DOT output from pydeps
            result = subprocess.run(
                [
                    sys.executable, "-m", "pydeps",
                    str(project_path),
                    "--show-dot",
                    "--no-show",
                    "--max-bacon", str(max_depth),
                ],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=project_path.parent if project_path.is_file() else project_path.parent.parent,
            )

            if result.returncode == 0 and result.stdout.strip():
                dot_code = result.stdout
                return _render_graphviz(dot_code, output_path, format)
        except subprocess.TimeoutExpired:
            typer.echo("[WARN] pydeps timed out, falling back to static analysis", err=True)

    # Fallback: Static analysis with AST
    return _generate_dependency_graph_ast(project_path, output_path, format, backend)


def _generate_dependency_graph_ast(
    project_path: Path,
    output_path: Path,
    format: str,
    backend: str,
) -> bool:
    """Generate dependency graph using AST analysis (fallback)."""
    import ast

    # Collect all Python files
    if project_path.is_file():
        py_files = [project_path]
    else:
        py_files = list(project_path.rglob("*.py"))

    # Parse imports from each file
    modules: Dict[str, DependencyNode] = {}

    for py_file in py_files[:50]:  # Limit to prevent overwhelming
        try:
            tree = ast.parse(py_file.read_text())
            module_name = py_file.stem

            if module_name not in modules:
                modules[module_name] = DependencyNode(name=module_name)

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        import_name = alias.name.split(".")[0]
                        modules[module_name].imports.append(import_name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        import_name = node.module.split(".")[0]
                        modules[module_name].imports.append(import_name)
        except Exception:
            continue

    # Generate graph based on backend
    if backend == "mermaid":
        return _generate_mermaid_dep_graph(modules, output_path, format)
    elif backend == "networkx":
        return _generate_networkx_dep_graph(modules, output_path, format)
    else:  # graphviz
        return _generate_graphviz_dep_graph(modules, output_path, format)


def _generate_graphviz_dep_graph(
    modules: Dict[str, DependencyNode],
    output_path: Path,
    format: str,
) -> bool:
    """Generate Graphviz DOT dependency graph."""
    lines = [
        "digraph dependencies {",
        '    rankdir=LR;',
        '    node [shape=box, fontname="Helvetica", fontsize=10];',
        '    edge [color="#666666"];',
    ]

    # Filter to internal modules only
    internal_modules = set(modules.keys())

    for name, node in modules.items():
        safe_name = name.replace("-", "_").replace(".", "_")
        lines.append(f'    {safe_name} [label="{name}"];')

        for imp in set(node.imports):
            if imp in internal_modules:
                safe_imp = imp.replace("-", "_").replace(".", "_")
                lines.append(f"    {safe_name} -> {safe_imp};")

    lines.append("}")
    dot_code = "\n".join(lines)

    return _render_graphviz(dot_code, output_path, format)


def _generate_mermaid_dep_graph(
    modules: Dict[str, DependencyNode],
    output_path: Path,
    format: str,
) -> bool:
    """Generate Mermaid dependency graph."""
    lines = ["flowchart LR"]

    internal_modules = set(modules.keys())

    for name, node in modules.items():
        safe_name = name.replace("-", "_").replace(".", "_")
        lines.append(f'    {safe_name}["{name}"]')

        for imp in set(node.imports):
            if imp in internal_modules:
                safe_imp = imp.replace("-", "_").replace(".", "_")
                lines.append(f"    {safe_name} --> {safe_imp}")

    mermaid_code = "\n".join(lines)
    return _render_mermaid(mermaid_code, output_path, format)


def _generate_networkx_dep_graph(
    modules: Dict[str, DependencyNode],
    output_path: Path,
    format: str,
) -> bool:
    """Generate NetworkX dependency graph and export."""
    if not _check_networkx():
        typer.echo("[ERROR] NetworkX not available", err=True)
        return False

    import networkx as nx

    G = nx.DiGraph()
    internal_modules = set(modules.keys())

    for name, node in modules.items():
        G.add_node(name, module_type=node.module_type, loc=node.loc)

        for imp in set(node.imports):
            if imp in internal_modules:
                G.add_edge(name, imp)

    # Export based on format
    if format == "json":
        d3_data = _networkx_to_d3_json(G)
        output_path.write_text(json.dumps(d3_data, indent=2))
        return True
    elif format in ("dot", "gv"):
        from networkx.drawing.nx_pydot import to_pydot
        pydot_graph = to_pydot(G)
        output_path.write_text(pydot_graph.to_string())
        return True
    else:
        # Render with matplotlib
        if not _check_matplotlib():
            typer.echo("[ERROR] matplotlib not available for rendering", err=True)
            return False

        import matplotlib.pyplot as plt
        _apply_ieee_style()

        fig, ax = plt.subplots(figsize=(IEEE_DOUBLE_COLUMN, 4))
        pos = nx.spring_layout(G, k=2, iterations=50)
        nx.draw(G, pos, ax=ax, with_labels=True, node_color="lightblue",
                node_size=1000, font_size=7, arrows=True,
                arrowsize=10, edge_color="#666666")

        plt.tight_layout()
        plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
        plt.close()
        return True


def generate_class_diagram(
    project_path: Path,
    output_path: Path,
    format: str = "pdf",
) -> bool:
    """
    Generate UML class diagram using pyreverse.

    Args:
        project_path: Path to Python package/module
        output_path: Output file path
        format: Output format (pdf, png, svg, dot)

    Returns:
        True if successful, False otherwise
    """
    if not _check_pyreverse():
        typer.echo("[ERROR] pyreverse not available (pip install pylint)", err=True)
        return False

    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            result = subprocess.run(
                [
                    "pyreverse",
                    "-o", "dot",
                    "-p", project_path.name,
                    str(project_path),
                ],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=tmpdir,
            )

            if result.returncode != 0:
                typer.echo(f"[ERROR] pyreverse: {result.stderr}", err=True)
                return False

            # Find generated DOT file
            dot_files = list(Path(tmpdir).glob("*.dot"))
            if not dot_files:
                typer.echo("[ERROR] pyreverse produced no output", err=True)
                return False

            dot_code = dot_files[0].read_text()
            return _render_graphviz(dot_code, output_path, format)

        except subprocess.TimeoutExpired:
            typer.echo("[ERROR] pyreverse timed out", err=True)
            return False


def generate_metrics_chart(
    title: str,
    data: Dict[str, float],
    output_path: Path,
    chart_type: str = "bar",
    format: str = "pdf",
    figsize: Optional[Tuple[float, float]] = None,
) -> bool:
    """
    Generate publication-quality metrics chart using Seaborn (preferred) or matplotlib.

    Args:
        title: Chart title
        data: Dictionary of label -> value
        output_path: Output file path
        chart_type: bar, hbar, pie, line
        format: Output format (pdf, png, svg)
        figsize: Optional (width, height) in inches

    Returns:
        True if successful, False otherwise
    """
    if not _check_matplotlib():
        typer.echo("[ERROR] matplotlib not available", err=True)
        return False

    import matplotlib.pyplot as plt
    _apply_ieee_style()

    # Use seaborn for better aesthetics if available
    use_seaborn = _check_seaborn()
    if use_seaborn:
        import seaborn as sns
        # Set publication-quality seaborn theme
        sns.set_theme(style="whitegrid", context="paper", font_scale=0.9)
        sns.set_palette("Blues_d")

    if figsize is None:
        figsize = (IEEE_SINGLE_COLUMN, 2.5)

    fig, ax = plt.subplots(figsize=figsize)

    labels = list(data.keys())
    values = list(data.values())

    if use_seaborn and chart_type in ("bar", "hbar"):
        import pandas as pd
        df = pd.DataFrame({"Label": labels, "Value": values})

        if chart_type == "bar":
            sns.barplot(data=df, x="Label", y="Value", ax=ax, hue="Label",
                       palette="Blues_d", edgecolor="black", legend=False)
            ax.set_ylabel("Value")
            ax.set_xlabel("")
            # Add value labels on bars
            for i, (_, val) in enumerate(zip(labels, values)):
                ax.annotate(f'{val:.1f}' if isinstance(val, float) else str(val),
                           xy=(i, val),
                           xytext=(0, 3), textcoords="offset points",
                           ha='center', va='bottom', fontsize=7)
        else:  # hbar
            sns.barplot(data=df, x="Value", y="Label", ax=ax, hue="Label",
                       palette="Blues_d", edgecolor="black", orient="h", legend=False)
            ax.set_xlabel("Value")
            ax.set_ylabel("")

    elif use_seaborn and chart_type == "line":
        import pandas as pd
        df = pd.DataFrame({"Label": labels, "Value": values})
        sns.lineplot(data=df, x="Label", y="Value", ax=ax, marker="o",
                    color="steelblue", linewidth=2, markersize=8)
        ax.set_ylabel("Value")
        ax.set_xlabel("")

    else:
        # Fallback to matplotlib for pie charts or when seaborn unavailable
        colors = plt.cm.Blues(np.linspace(0.4, 0.8, len(labels))) if len(labels) > 1 else ["steelblue"]

        if chart_type == "bar":
            bars = ax.bar(labels, values, color=colors, edgecolor="black", linewidth=0.5)
            ax.set_ylabel("Value")
            for bar, val in zip(bars, values):
                height = bar.get_height()
                ax.annotate(f'{val:.1f}' if isinstance(val, float) else str(val),
                           xy=(bar.get_x() + bar.get_width() / 2, height),
                           xytext=(0, 2), textcoords="offset points",
                           ha='center', va='bottom', fontsize=6)

        elif chart_type == "hbar":
            bars = ax.barh(labels, values, color=colors, edgecolor="black", linewidth=0.5)
            ax.set_xlabel("Value")

        elif chart_type == "pie":
            ax.pie(values, labels=labels, autopct="%1.1f%%",
                   colors=colors, wedgeprops={"edgecolor": "black", "linewidth": 0.5})

        elif chart_type == "line":
            ax.plot(labels, values, marker="o", color="steelblue",
                    markeredgecolor="black", markeredgewidth=0.5)
            ax.set_ylabel("Value")

        else:
            ax.bar(labels, values, color=colors, edgecolor="black", linewidth=0.5)

    if chart_type != "pie":
        ax.set_title(title, fontweight="bold", fontsize=9)
        plt.xticks(rotation=45, ha="right")

    # Remove seaborn's grid for cleaner look in publications
    if use_seaborn:
        ax.grid(True, axis='y', alpha=0.3)
        sns.despine(ax=ax)

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_sankey_diagram(
    flows: List[Dict[str, Any]],
    output_path: Path,
    title: str = "Flow Diagram",
    format: str = "pdf",
) -> bool:
    """
    Generate Sankey diagram for flow visualization (energy/mass balances).

    Args:
        flows: List of dicts with 'source', 'target', 'value' keys
        output_path: Output file path
        title: Diagram title
        format: Output format (pdf, png, svg, html)

    Returns:
        True if successful, False otherwise
    """
    if _check_plotly():
        import plotly.graph_objects as go

        # Extract unique nodes
        nodes = []
        node_map = {}
        for flow in flows:
            for key in ['source', 'target']:
                if flow[key] not in node_map:
                    node_map[flow[key]] = len(nodes)
                    nodes.append(flow[key])

        # Build Sankey data
        fig = go.Figure(data=[go.Sankey(
            node=dict(
                pad=15,
                thickness=20,
                line=dict(color="black", width=0.5),
                label=nodes,
                color="steelblue",
            ),
            link=dict(
                source=[node_map[f['source']] for f in flows],
                target=[node_map[f['target']] for f in flows],
                value=[f['value'] for f in flows],
            )
        )])

        fig.update_layout(
            title_text=title,
            font_size=10,
            font_family="Times New Roman",
        )

        if format == "html":
            fig.write_html(str(output_path))
        else:
            fig.write_image(str(output_path), format=format, scale=3)
        return True

    elif _check_matplotlib():
        # Fallback to matplotlib sankey (simpler)
        from matplotlib.sankey import Sankey
        import matplotlib.pyplot as plt
        _apply_ieee_style()

        fig, ax = plt.subplots(figsize=(IEEE_DOUBLE_COLUMN, 4))
        sankey = Sankey(ax=ax, unit=None)

        # Simplified: just show first few flows as a single diagram
        flows_subset = flows[:5]
        sankey.add(flows=[f['value'] for f in flows_subset],
                  labels=[f['source'] for f in flows_subset],
                  orientations=[0] * len(flows_subset))
        sankey.finish()

        ax.set_title(title, fontweight="bold")
        plt.tight_layout()
        plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
        plt.close()
        return True

    typer.echo("[ERROR] Neither plotly nor matplotlib available for Sankey", err=True)
    return False


def generate_heatmap(
    data: Dict[str, Dict[str, float]],
    output_path: Path,
    title: str = "Heatmap",
    format: str = "pdf",
    cmap: str = "Blues",
) -> bool:
    """
    Generate heatmap for field distributions or correlation matrices.

    Args:
        data: Nested dict {row_label: {col_label: value}}
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)
        cmap: Colormap name

    Returns:
        True if successful, False otherwise
    """
    if not _check_matplotlib():
        typer.echo("[ERROR] matplotlib not available for heatmap", err=True)
        return False

    import matplotlib.pyplot as plt
    _apply_ieee_style()

    # Convert to 2D array
    row_labels = list(data.keys())
    col_labels = list(data[row_labels[0]].keys()) if row_labels else []
    matrix = [[data[r].get(c, 0) for c in col_labels] for r in row_labels]

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN))

    if _check_seaborn():
        import seaborn as sns
        import pandas as pd
        df = pd.DataFrame(matrix, index=row_labels, columns=col_labels)
        sns.heatmap(df, ax=ax, cmap=cmap, annot=True, fmt=".1f",
                   linewidths=0.5, cbar_kws={"shrink": 0.8})
    else:
        im = ax.imshow(matrix, cmap=cmap, aspect='auto')
        ax.set_xticks(range(len(col_labels)))
        ax.set_yticks(range(len(row_labels)))
        ax.set_xticklabels(col_labels, rotation=45, ha='right')
        ax.set_yticklabels(row_labels)
        plt.colorbar(im, ax=ax, shrink=0.8)

    ax.set_title(title, fontweight="bold")
    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_treemap(
    data: Dict[str, float],
    output_path: Path,
    title: str = "Treemap",
    format: str = "pdf",
) -> bool:
    """
    Generate treemap for hierarchical data visualization.

    Args:
        data: Dict of {label: size}
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg, html)

    Returns:
        True if successful, False otherwise
    """
    if _check_plotly():
        import plotly.express as px

        labels = list(data.keys())
        values = list(data.values())

        fig = px.treemap(
            names=labels,
            parents=[""] * len(labels),
            values=values,
            title=title,
        )
        fig.update_layout(font_family="Times New Roman")

        if format == "html":
            fig.write_html(str(output_path))
        else:
            fig.write_image(str(output_path), format=format, scale=3)
        return True

    elif _check_squarify() and _check_matplotlib():
        import squarify
        import matplotlib.pyplot as plt
        _apply_ieee_style()

        labels = list(data.keys())
        values = list(data.values())

        fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN))
        colors = plt.cm.Blues(np.linspace(0.3, 0.8, len(labels)))

        squarify.plot(sizes=values, label=labels, color=colors, alpha=0.8, ax=ax,
                     edgecolor="black", linewidth=0.5)
        ax.set_title(title, fontweight="bold")
        ax.axis('off')

        plt.tight_layout()
        plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
        plt.close()
        return True

    typer.echo("[ERROR] Neither plotly nor squarify available for treemap", err=True)
    return False


def generate_sunburst(
    hierarchy: Dict[str, Any],
    output_path: Path,
    title: str = "Sunburst",
    format: str = "pdf",
) -> bool:
    """
    Generate sunburst chart for hierarchical fault trees or component breakdown.

    Args:
        hierarchy: Nested dict representing hierarchy
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg, html)

    Returns:
        True if successful, False otherwise
    """
    if not _check_plotly():
        typer.echo("[ERROR] plotly required for sunburst charts", err=True)
        return False

    import plotly.express as px

    # Flatten hierarchy to ids, labels, parents, values
    ids, labels, parents, values = [], [], [], []

    def flatten(node, parent=""):
        if isinstance(node, dict):
            for key, child in node.items():
                ids.append(key)
                labels.append(key)
                parents.append(parent)
                values.append(child.get("value", 1) if isinstance(child, dict) else 1)
                if isinstance(child, dict):
                    flatten(child, key)
        elif isinstance(node, list):
            for item in node:
                if isinstance(item, str):
                    ids.append(item)
                    labels.append(item)
                    parents.append(parent)
                    values.append(1)
                elif isinstance(item, dict):
                    flatten(item, parent)

    flatten(hierarchy)

    fig = px.sunburst(
        ids=ids,
        names=labels,
        parents=parents,
        values=values,
        title=title,
    )
    fig.update_layout(font_family="Times New Roman")

    if format == "html":
        fig.write_html(str(output_path))
    else:
        fig.write_image(str(output_path), format=format, scale=3)
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
    if not _check_networkx():
        typer.echo("[ERROR] NetworkX required for force-directed graphs", err=True)
        return False

    import networkx as nx

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
        d3_data = _networkx_to_d3_json(G)
        output_path.write_text(json.dumps(d3_data, indent=2))
        return True

    # Render with matplotlib
    if not _check_matplotlib():
        typer.echo("[ERROR] matplotlib required for rendering", err=True)
        return False

    import matplotlib.pyplot as plt
    _apply_ieee_style()

    fig, ax = plt.subplots(figsize=(IEEE_DOUBLE_COLUMN, 4))

    # Use spring layout (force-directed)
    pos = nx.spring_layout(G, k=2, iterations=50, seed=42)

    # Color by group if available
    groups = [G.nodes[n].get('group', 0) for n in G.nodes()]
    colors = plt.cm.Set3(np.array(groups) % 12)

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


def generate_parallel_coordinates(
    data: List[Dict[str, float]],
    output_path: Path,
    title: str = "Parallel Coordinates",
    format: str = "pdf",
    color_by: Optional[str] = None,
) -> bool:
    """
    Generate parallel coordinates plot for multi-dimensional analysis.

    Args:
        data: List of dicts with same keys (dimensions)
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg, html)
        color_by: Optional dimension to color by

    Returns:
        True if successful, False otherwise
    """
    if not _check_pandas():
        typer.echo("[ERROR] pandas required for parallel coordinates", err=True)
        return False

    import pandas as pd

    df = pd.DataFrame(data)

    if _check_plotly():
        import plotly.express as px

        fig = px.parallel_coordinates(
            df,
            color=color_by,
            title=title,
        )
        fig.update_layout(font_family="Times New Roman")

        if format == "html":
            fig.write_html(str(output_path))
        else:
            fig.write_image(str(output_path), format=format, scale=3)
        return True

    elif _check_matplotlib():
        from pandas.plotting import parallel_coordinates
        import matplotlib.pyplot as plt
        _apply_ieee_style()

        fig, ax = plt.subplots(figsize=(IEEE_DOUBLE_COLUMN, 3))

        # Need a class column for pandas parallel_coordinates
        if color_by and color_by in df.columns:
            parallel_coordinates(df, color_by, ax=ax, colormap=plt.cm.Blues)
        else:
            df['_class'] = 'data'
            parallel_coordinates(df, '_class', ax=ax, color=['steelblue'])

        ax.set_title(title, fontweight="bold")
        ax.legend().set_visible(False)
        plt.tight_layout()
        plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
        plt.close()
        return True

    typer.echo("[ERROR] Neither plotly nor matplotlib available", err=True)
    return False


# --- Domain-Specific Visualizations ---

def generate_radar_chart(
    data: Dict[str, Dict[str, float]],
    output_path: Path,
    title: str = "Radar Chart",
    format: str = "pdf",
) -> bool:
    """
    Generate radar/spider chart for multi-attribute comparison.

    Args:
        data: Dict of {series_name: {dimension: value}}
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)

    Returns:
        True if successful, False otherwise
    """
    if not _check_matplotlib():
        typer.echo("[ERROR] matplotlib required for radar chart", err=True)
        return False

    import matplotlib.pyplot as plt
    _apply_ieee_style()

    # Get dimensions from first series
    first_series = list(data.values())[0]
    dimensions = list(first_series.keys())
    num_dims = len(dimensions)

    # Calculate angles for each axis
    angles = [n / float(num_dims) * 2 * 3.14159 for n in range(num_dims)]
    angles += angles[:1]  # Close the polygon

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN),
                          subplot_kw=dict(polar=True))

    colors = plt.cm.Set2(np.linspace(0, 1, len(data)))

    for i, (series_name, values_dict) in enumerate(data.items()):
        values = [values_dict.get(d, 0) for d in dimensions]
        values += values[:1]  # Close the polygon

        ax.plot(angles, values, 'o-', linewidth=1.5, label=series_name, color=colors[i])
        ax.fill(angles, values, alpha=0.25, color=colors[i])

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(dimensions, fontsize=7)
    ax.set_title(title, fontweight="bold", y=1.08)
    ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.0), fontsize=7)

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_bode_plot(
    num: List[float],
    den: List[float],
    output_path: Path,
    title: str = "Bode Plot",
    format: str = "pdf",
    freq_range: Optional[Tuple[float, float]] = None,
) -> bool:
    """
    Generate Bode plot (magnitude and phase vs frequency) for control systems.

    Args:
        num: Numerator polynomial coefficients [b_n, ..., b_1, b_0]
        den: Denominator polynomial coefficients [a_n, ..., a_1, a_0]
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)
        freq_range: Optional (min_freq, max_freq) in rad/s

    Returns:
        True if successful, False otherwise
    """
    if _check_control():
        import control as ctrl
        import matplotlib.pyplot as plt
        _apply_ieee_style()

        sys = ctrl.TransferFunction(num, den)

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(IEEE_SINGLE_COLUMN, 3.5))

        if freq_range:
            omega = np.logspace(np.log10(freq_range[0]), np.log10(freq_range[1]), 500)
            ctrl.bode_plot(sys, omega=omega, ax=(ax1, ax2), dB=True, deg=True)
        else:
            ctrl.bode_plot(sys, ax=(ax1, ax2), dB=True, deg=True)

        ax1.set_title(title, fontweight="bold")
        plt.tight_layout()
        plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
        plt.close()
        return True

    elif _check_scipy() and _check_matplotlib():
        # Fallback using scipy.signal
        from scipy import signal
        import matplotlib.pyplot as plt
        _apply_ieee_style()

        sys = signal.TransferFunction(num, den)

        if freq_range:
            w = np.logspace(np.log10(freq_range[0]), np.log10(freq_range[1]), 500)
        else:
            w = np.logspace(-2, 2, 500)

        w, H = signal.freqresp(sys, w)
        mag = 20 * np.log10(np.abs(H))
        phase = np.angle(H, deg=True)

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(IEEE_SINGLE_COLUMN, 3.5))

        ax1.semilogx(w, mag, 'b-', linewidth=1.5)
        ax1.set_ylabel('Magnitude (dB)')
        ax1.grid(True, which='both', linestyle='--', alpha=0.5)
        ax1.set_title(title, fontweight="bold")

        ax2.semilogx(w, phase, 'b-', linewidth=1.5)
        ax2.set_ylabel('Phase (deg)')
        ax2.set_xlabel('Frequency (rad/s)')
        ax2.grid(True, which='both', linestyle='--', alpha=0.5)

        plt.tight_layout()
        plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
        plt.close()
        return True

    typer.echo("[ERROR] Neither python-control nor scipy available for Bode plot", err=True)
    return False


def generate_nyquist_plot(
    num: List[float],
    den: List[float],
    output_path: Path,
    title: str = "Nyquist Plot",
    format: str = "pdf",
) -> bool:
    """
    Generate Nyquist plot for stability analysis.

    Args:
        num: Numerator polynomial coefficients
        den: Denominator polynomial coefficients
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)

    Returns:
        True if successful, False otherwise
    """
    if _check_control():
        import control as ctrl
        import matplotlib.pyplot as plt
        _apply_ieee_style()

        sys = ctrl.TransferFunction(num, den)

        fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN))
        ctrl.nyquist_plot(sys, ax=ax)

        # Mark critical point (-1, 0)
        ax.plot(-1, 0, 'rx', markersize=10, label='Critical Point (-1,0)')
        ax.set_title(title, fontweight="bold")
        ax.legend(fontsize=7)

        plt.tight_layout()
        plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
        plt.close()
        return True

    elif _check_scipy() and _check_matplotlib():
        from scipy import signal
        import matplotlib.pyplot as plt
        _apply_ieee_style()

        sys = signal.TransferFunction(num, den)
        w = np.logspace(-2, 2, 1000)
        w, H = signal.freqresp(sys, w)

        fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN))

        ax.plot(H.real, H.imag, 'b-', linewidth=1.5, label='Nyquist contour')
        ax.plot(H.real, -H.imag, 'b--', linewidth=1, alpha=0.5)  # Mirror
        ax.plot(-1, 0, 'rx', markersize=10, label='Critical Point (-1,0)')
        ax.axhline(y=0, color='k', linewidth=0.5)
        ax.axvline(x=0, color='k', linewidth=0.5)

        ax.set_xlabel('Real')
        ax.set_ylabel('Imaginary')
        ax.set_title(title, fontweight="bold")
        ax.legend(fontsize=7)
        ax.set_aspect('equal')
        ax.grid(True, linestyle='--', alpha=0.5)

        plt.tight_layout()
        plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
        plt.close()
        return True

    typer.echo("[ERROR] Neither python-control nor scipy available for Nyquist", err=True)
    return False


def generate_root_locus(
    num: List[float],
    den: List[float],
    output_path: Path,
    title: str = "Root Locus",
    format: str = "pdf",
    show_breakaway: bool = True,
    gain_range: Optional[Tuple[float, float]] = None,
) -> bool:
    """
    Generate enhanced root locus plot for control system gain analysis.

    Args:
        num: Numerator polynomial coefficients
        den: Denominator polynomial coefficients
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)
        show_breakaway: Highlight breakaway/break-in points
        gain_range: Optional (min_gain, max_gain) for analysis

    Returns:
        True if successful, False otherwise
    """
    if not _check_control():
        typer.echo("[ERROR] python-control required for root locus", err=True)
        return False

    import control as ctrl
    import matplotlib.pyplot as plt
    _apply_ieee_style()

    sys = ctrl.TransferFunction(num, den)

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN))
    
    # Enhanced root locus with breakaway points
    if show_breakaway:
        # Calculate and highlight breakaway points
        try:
            # Get root locus data
            roots, gains = ctrl.root_locus(sys, plot=False,
                                         kvect=np.logspace(-2, 2, 1000) if not gain_range else
                                         np.linspace(gain_range[0], gain_range[1], 1000))
            
            # Find breakaway/break-in points (where roots are real and repeated)
            breakaway_points = []
            for i in range(len(roots)-1):
                # Check for real repeated roots
                if len(roots[i]) > 0:
                    real_roots = [r.real for r in roots[i] if abs(r.imag) < 1e-6]
                    if len(real_roots) > 1:
                        # Check if any roots are very close (potential breakaway)
                        for j, r1 in enumerate(real_roots):
                            for k, r2 in enumerate(real_roots[j+1:], j+1):
                                if abs(r1 - r2) < 1e-3:
                                    breakaway_points.append(complex(r1, 0))
            
            # Plot enhanced root locus
            ctrl.root_locus_plot(sys, ax=ax, grid=True)
            
            # Highlight breakaway points
            if breakaway_points:
                ax.scatter([p.real for p in breakaway_points],
                          [p.imag for p in breakaway_points],
                          color='red', s=50, marker='x',
                          label='Breakaway/Break-in points', zorder=10)
                ax.legend(fontsize=7)
                
        except Exception:
            # Fallback to basic root locus
            ctrl.root_locus_plot(sys, ax=ax, grid=True)
    else:
        ctrl.root_locus_plot(sys, ax=ax, grid=True)

    ax.set_title(title, fontweight="bold")
    ax.axhline(y=0, color='k', linewidth=0.5)
    ax.axvline(x=0, color='k', linewidth=0.5)

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_pole_zero_map(
    zeros: List[complex],
    poles: List[complex],
    output_path: Path,
    title: str = "Pole-Zero Map",
    format: str = "pdf",
    show_grid: bool = True,
    show_damping: bool = True,
    is_discrete: bool = False,
    sample_time: Optional[float] = None,
) -> bool:
    """
    Generate pole-zero map with stability analysis for control systems.

    Args:
        zeros: List of zero locations (complex numbers)
        poles: List of pole locations (complex numbers)
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)
        show_grid: Show stability grid
        show_damping: Show damping ratio lines
        is_discrete: True for discrete-time systems
        sample_time: Sample time for discrete systems (required if is_discrete=True)

    Returns:
        True if successful, False otherwise
    """
    if not _check_matplotlib():
        typer.echo("[ERROR] matplotlib required for pole-zero map", err=True)
        return False

    import matplotlib.pyplot as plt
    _apply_ieee_style()

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN))

    # Plot poles (x) and zeros (o)
    if poles:
        ax.scatter([p.real for p in poles], [p.imag for p in poles],
                  marker='x', s=100, c='red', label='Poles', linewidth=2)
    
    if zeros:
        ax.scatter([z.real for z in zeros], [z.imag for z in zeros],
                  marker='o', s=100, c='blue', facecolors='none',
                  label='Zeros', linewidth=2)

    # Add stability analysis
    if is_discrete:
        # Discrete-time: stability inside unit circle
        theta = np.linspace(0, 2*np.pi, 100)
        unit_circle_x = np.cos(theta)
        unit_circle_y = np.sin(theta)
        ax.plot(unit_circle_x, unit_circle_y, 'k--', alpha=0.5,
                label='Unit Circle (Stable Region)')
        
        if show_grid and sample_time:
            # Add normalized frequency grid
            ax.set_title(f"{title} (T={sample_time}s)", fontweight="bold")
        else:
            ax.set_title(title, fontweight="bold")
    else:
        # Continuous-time: stability in left half plane
        ax.axvline(x=0, color='k', linestyle='--', alpha=0.5,
                  label='Imaginary Axis')
        
        if show_damping:
            # Add damping ratio lines
            damping_ratios = [0.1, 0.3, 0.5, 0.7, 0.9]
            for zeta in damping_ratios:
                if zeta > 0:
                    # Constant damping ratio lines: s = -zeta*omega_d ± j*omega_d*sqrt(1-zeta²)
                    omega_range = np.linspace(0.1, 10, 50)
                    s_real = -zeta * omega_range
                    s_imag_pos = omega_range * np.sqrt(1 - zeta**2)
                    s_imag_neg = -s_imag_pos
                    
                    ax.plot(s_real, s_imag_pos, 'g:', alpha=0.3, linewidth=0.5)
                    ax.plot(s_real, s_imag_neg, 'g:', alpha=0.3, linewidth=0.5)
        
        ax.set_title(title, fontweight="bold")

    # Add grid and stability annotations
    if show_grid:
        ax.grid(True, alpha=0.3)
        
        # Add stability region annotation
        if is_discrete:
            ax.text(0.3, 0.8, 'Stable Region\n(Inside Unit Circle)',
                   transform=ax.transAxes, fontsize=8,
                   bbox=dict(boxstyle="round,pad=0.3", facecolor="lightgreen", alpha=0.7))
        else:
            ax.text(0.05, 0.8, 'Stable Region\n(Left Half Plane)',
                   transform=ax.transAxes, fontsize=8,
                   bbox=dict(boxstyle="round,pad=0.3", facecolor="lightgreen", alpha=0.7))

    ax.set_xlabel('Real Part')
    ax.set_ylabel('Imaginary Part')
    ax.axhline(y=0, color='k', linewidth=0.5)
    
    if poles or zeros:
        ax.legend(loc='best', fontsize=7)

    # Set equal aspect ratio for proper circle visualization
    ax.set_aspect('equal')

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_spectrogram(
    signal: List[float],
    sample_rate: float,
    output_path: Path,
    title: str = "Spectrogram",
    format: str = "pdf",
    window_type: str = "hann",
    window_size: int = 256,
    overlap: float = 0.5,
    nfft: Optional[int] = None,
) -> bool:
    """
    Generate spectrogram for time-frequency signal analysis.

    Args:
        signal: Time-domain signal data
        sample_rate: Sampling rate in Hz
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)
        window_type: Window type: hann, hamming, blackman, rectangular
        window_size: Size of FFT window
        overlap: Overlap fraction (0-1)
        nfft: FFT size (defaults to window_size)

    Returns:
        True if successful, False otherwise
    """
    if not _check_scipy() or not _check_matplotlib():
        typer.echo("[ERROR] scipy and matplotlib required for spectrogram", err=True)
        return False

    from scipy import signal as sig
    import matplotlib.pyplot as plt
    _apply_ieee_style()

    # Convert signal to numpy array
    signal_array = np.array(signal, dtype=float)
    
    # Set default nfft
    if nfft is None:
        nfft = window_size

    # Get window function
    window_funcs = {
        "hann": sig.windows.hann,
        "hamming": sig.windows.hamming,
        "blackman": sig.windows.blackman,
        "rectangular": lambda x: np.ones(x)
    }
    
    if window_type not in window_funcs:
        typer.echo(f"[WARN] Unknown window type '{window_type}', using hann", err=True)
        window_type = "hann"
    
    window = window_funcs[window_type](window_size)
    noverlap = int(window_size * overlap)

    try:
        # Compute spectrogram
        f, t, Sxx = sig.spectrogram(signal_array, sample_rate, window=window,
                                   nperseg=window_size, noverlap=noverlap, nfft=nfft)
        
        fig, ax = plt.subplots(figsize=(IEEE_DOUBLE_COLUMN, IEEE_SINGLE_COLUMN))
        
        # Create spectrogram plot
        im = ax.pcolormesh(t, f, 10 * np.log10(Sxx + 1e-10), shading='gouraud', cmap='viridis')
        
        # Add colorbar
        cbar = plt.colorbar(im, ax=ax, shrink=0.8)
        cbar.set_label('Power Spectral Density [dB/Hz]', rotation=-90, va="bottom")
        
        ax.set_xlabel('Time [s]')
        ax.set_ylabel('Frequency [Hz]')
        ax.set_title(title, fontweight="bold")
        ax.grid(True, alpha=0.3)
        
        # Add window info as text
        window_info = f"Window: {window_type}, Size: {window_size}, Overlap: {overlap:.1%}"
        ax.text(0.02, 0.98, window_info, transform=ax.transAxes, fontsize=7,
               verticalalignment='top', bbox=dict(boxstyle="round,pad=0.2",
               facecolor="white", alpha=0.8))
        
        plt.tight_layout()
        plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
        plt.close()
        return True
        
    except Exception as e:
        typer.echo(f"[ERROR] Spectrogram computation failed: {e}", err=True)
        return False


def generate_filter_response(
    filter_coeffs: Dict[str, List[float]],
    sample_rate: float,
    output_path: Path,
    title: str = "Filter Response",
    format: str = "pdf",
    freq_range: Optional[Tuple[float, float]] = None,
) -> bool:
    """
    Generate frequency response analysis for digital filters.

    Args:
        filter_coeffs: Dict with 'b' (numerator) and 'a' (denominator) coefficients
        sample_rate: Sampling rate in Hz
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)
        freq_range: Optional (min_freq, max_freq) in Hz

    Returns:
        True if successful, False otherwise
    """
    if not _check_scipy() or not _check_matplotlib():
        typer.echo("[ERROR] scipy and matplotlib required for filter response", err=True)
        return False

    from scipy import signal as sig
    import matplotlib.pyplot as plt
    _apply_ieee_style()

    try:
        b = filter_coeffs.get('b', [1.0])
        a = filter_coeffs.get('a', [1.0])
        
        # Compute frequency response
        if freq_range:
            w, h = sig.freqz(b, a, worN=np.linspace(freq_range[0], freq_range[1], 1000),
                            fs=sample_rate)
        else:
            w, h = sig.freqz(b, a, worN=1000, fs=sample_rate)
        
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(IEEE_SINGLE_COLUMN, 3.5))
        
        # Magnitude response (dB)
        magnitude_db = 20 * np.log10(np.abs(h) + 1e-10)
        ax1.plot(w, magnitude_db, 'b-', linewidth=1.5)
        ax1.set_ylabel('Magnitude [dB]')
        ax1.set_title(title, fontweight="bold")
        ax1.grid(True, alpha=0.3)
        ax1.axhline(y=-3, color='r', linestyle='--', alpha=0.7, label='-3 dB')
        ax1.axhline(y=-20, color='orange', linestyle='--', alpha=0.7, label='-20 dB')
        ax1.legend(fontsize=7)
        
        # Phase response
        phase_deg = np.angle(h) * 180 / np.pi
        ax2.plot(w, phase_deg, 'b-', linewidth=1.5)
        ax2.set_xlabel('Frequency [Hz]')
        ax2.set_ylabel('Phase [degrees]')
        ax2.grid(True, alpha=0.3)
        
        # Add filter info
        filter_type = "FIR" if len(a) == 1 else "IIR"
        filter_info = f"Filter Type: {filter_type}, Order: {max(len(b), len(a))-1}"
        ax2.text(0.02, 0.02, filter_info, transform=ax2.transAxes, fontsize=7,
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.8))
        
        plt.tight_layout()
        plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
        plt.close()
        return True
        
    except Exception as e:
        typer.echo(f"[ERROR] Filter response computation failed: {e}", err=True)
        return False


def generate_state_space_visualization(
    A: List[List[float]],
    B: List[List[float]],
    C: List[List[float]],
    D: List[List[float]],
    output_path: Path,
    title: str = "State Space System",
    format: str = "pdf",
    show_poles_zeros: bool = True,
    show_eigenvalues: bool = True,
) -> bool:
    """
    Generate comprehensive state-space system visualization.

    Args:
        A: State matrix (n x n)
        B: Input matrix (n x m)
        C: Output matrix (p x n)
        D: Feedthrough matrix (p x m)
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)
        show_poles_zeros: Include pole-zero analysis
        show_eigenvalues: Show eigenvalue analysis

    Returns:
        True if successful, False otherwise
    """
    if not _check_matplotlib():
        typer.echo("[ERROR] matplotlib required for state-space visualization", err=True)
        return False

    import matplotlib.pyplot as plt
    import numpy as np
    from numpy.linalg import eig
    _apply_ieee_style()

    A_np = np.array(A)
    B_np = np.array(B)
    C_np = np.array(C)
    D_np = np.array(D)
    
    n_states = A_np.shape[0]
    n_inputs = B_np.shape[1] if B_np.ndim > 1 else 1
    n_outputs = C_np.shape[0] if C_np.ndim > 1 else 1

    # Create subplots based on what to show
    n_plots = 1  # Always show system info
    if show_eigenvalues:
        n_plots += 1
    if show_poles_zeros:
        n_plots += 1
    
    fig = plt.figure(figsize=(IEEE_DOUBLE_COLUMN, IEEE_SINGLE_COLUMN * n_plots))
    
    plot_idx = 1
    
    # 1. System matrices and dimensions
    ax1 = plt.subplot(n_plots, 1, plot_idx)
    ax1.axis('off')
    
    system_info = f"""State-Space System:
Dimensions: {n_states} states, {n_inputs} inputs, {n_outputs} outputs

A matrix ({n_states}×{n_states}):
{np.array2string(A_np, precision=3, suppress_small=True)}

B matrix ({n_states}×{n_inputs}):
{np.array2string(B_np, precision=3, suppress_small=True)}

C matrix ({n_outputs}×{n_states}):
{np.array2string(C_np, precision=3, suppress_small=True)}

D matrix ({n_outputs}×{n_inputs}):
{np.array2string(D_np, precision=3, suppress_small=True)}"""
    
    ax1.text(0.05, 0.95, system_info, transform=ax1.transAxes, fontsize=8,
             verticalalignment='top', fontfamily='monospace')
    plot_idx += 1
    
    # 2. Eigenvalue analysis
    if show_eigenvalues:
        ax2 = plt.subplot(n_plots, 1, plot_idx)
        
        eigenvals, eigenvecs = eig(A_np)
        
        # Plot eigenvalues in complex plane
        ax2.scatter(eigenvals.real, eigenvals.imag, s=100, c='red',
                   marker='x', label='Eigenvalues', linewidth=2)
        
        # Stability analysis
        is_stable = all(ev.real < 0 for ev in eigenvals)
        stability_text = f"System is {'STABLE' if is_stable else 'UNSTABLE'}"
        stability_color = 'green' if is_stable else 'red'
        
        ax2.axvline(x=0, color='k', linestyle='--', alpha=0.5, label='Imaginary Axis')
        ax2.axhline(y=0, color='k', linewidth=0.5)
        ax2.set_xlabel('Real Part')
        ax2.set_ylabel('Imaginary Part')
        ax2.set_title(f'Eigenvalue Analysis - {stability_text}', fontweight="bold",
                     color=stability_color)
        ax2.grid(True, alpha=0.3)
        ax2.legend(fontsize=7)
        ax2.set_aspect('equal')
        
        plot_idx += 1
    
    # 3. Pole-zero map (if requested)
    if show_poles_zeros:
        ax3 = plt.subplot(n_plots, 1, plot_idx)
        
        # Compute poles and zeros
        try:
            # Convert to transfer function to get poles/zeros
            from control import ss2tf
            num, den = ss2tf(A_np, B_np, C_np, D_np)
            
            # Find poles and zeros
            poles = np.roots(den[0]) if len(den) > 0 else []
            zeros = np.roots(num[0]) if len(num) > 0 and any(num[0]) else []
            
            # Plot pole-zero map
            if poles:
                ax3.scatter(poles.real, poles.imag, marker='x', s=100, c='red',
                           label='Poles', linewidth=2)
            if zeros:
                ax3.scatter(zeros.real, zeros.imag, marker='o', s=100, c='blue',
                           facecolors='none', label='Zeros', linewidth=2)
            
            ax3.axvline(x=0, color='k', linestyle='--', alpha=0.5, label='Imaginary Axis')
            ax3.axhline(y=0, color='k', linewidth=0.5)
            ax3.set_xlabel('Real Part')
            ax3.set_ylabel('Imaginary Part')
            ax3.set_title('Pole-Zero Map', fontweight="bold")
            ax3.grid(True, alpha=0.3)
            if poles or zeros:
                ax3.legend(fontsize=7)
            ax3.set_aspect('equal')
            
        except Exception as e:
            ax3.text(0.5, 0.5, f'Pole-Zero computation failed:\n{str(e)}',
                    transform=ax3.transAxes, ha='center', va='center',
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="yellow", alpha=0.7))
            ax3.set_title('Pole-Zero Map (Computation Error)', fontweight="bold")

    plt.suptitle(title, fontweight="bold", y=0.98)
    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_polar_plot(
    theta: List[float],
    r: List[float],
    output_path: Path,
    title: str = "Polar Plot",
    format: str = "pdf",
) -> bool:
    """
    Generate polar coordinate plot.

    Args:
        theta: Angles in radians
        r: Radii
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)

    Returns:
        True if successful, False otherwise
    """
    if not _check_matplotlib():
        typer.echo("[ERROR] matplotlib required for polar plot", err=True)
        return False

    import matplotlib.pyplot as plt
    _apply_ieee_style()

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN),
                          subplot_kw=dict(polar=True))

    ax.plot(theta, r, 'b-', linewidth=1.5)
    ax.fill(theta, r, alpha=0.25, color='steelblue')
    ax.set_title(title, fontweight="bold", y=1.08)

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_contour_plot(
    x: List[float],
    y: List[float],
    z: List[List[float]],
    output_path: Path,
    title: str = "Contour Plot",
    format: str = "pdf",
    levels: int = 15,
    cmap: str = "viridis",
    filled: bool = True,
) -> bool:
    """
    Generate contour plot for field distributions (flux, temperature, stress).

    Args:
        x: X coordinates
        y: Y coordinates
        z: 2D array of values z[y_idx][x_idx]
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)
        levels: Number of contour levels
        cmap: Colormap name
        filled: Use filled contours

    Returns:
        True if successful, False otherwise
    """
    if not _check_matplotlib():
        typer.echo("[ERROR] matplotlib required for contour plot", err=True)
        return False

    import matplotlib.pyplot as plt
    _apply_ieee_style()

    X, Y = np.meshgrid(x, y)
    Z = np.array(z)

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN))

    if filled:
        cs = ax.contourf(X, Y, Z, levels=levels, cmap=cmap)
    else:
        cs = ax.contour(X, Y, Z, levels=levels, cmap=cmap)

    plt.colorbar(cs, ax=ax, shrink=0.8)
    ax.set_xlabel('X')
    ax.set_ylabel('Y')
    ax.set_title(title, fontweight="bold")
    ax.set_aspect('equal')

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_gantt_chart(
    tasks: List[Dict[str, Any]],
    output_path: Path,
    title: str = "Project Schedule",
    format: str = "pdf",
) -> bool:
    """
    Generate Gantt chart for project scheduling.

    Args:
        tasks: List of {name, start, duration, color?} dicts
               start and duration are numeric (e.g., days)
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)

    Returns:
        True if successful, False otherwise
    """
    if not _check_matplotlib():
        typer.echo("[ERROR] matplotlib required for Gantt chart", err=True)
        return False

    import matplotlib.pyplot as plt
    _apply_ieee_style()

    fig, ax = plt.subplots(figsize=(IEEE_DOUBLE_COLUMN, len(tasks) * 0.4 + 1))

    colors = plt.cm.Set3(np.linspace(0, 1, len(tasks)))

    for i, task in enumerate(tasks):
        name = task.get('name', f'Task {i+1}')
        start = task.get('start', 0)
        duration = task.get('duration', 1)
        color = task.get('color', colors[i])

        ax.barh(i, duration, left=start, height=0.6, color=color,
               edgecolor='black', linewidth=0.5)
        ax.text(start + duration/2, i, name, ha='center', va='center', fontsize=7)

    ax.set_yticks(range(len(tasks)))
    ax.set_yticklabels([])
    ax.set_xlabel('Time')
    ax.set_title(title, fontweight="bold")
    ax.invert_yaxis()  # Tasks read top-to-bottom
    ax.grid(True, axis='x', linestyle='--', alpha=0.5)

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
    if not _check_networkx() or not _check_matplotlib():
        typer.echo("[ERROR] NetworkX and matplotlib required for PERT network", err=True)
        return False

    import networkx as nx
    import matplotlib.pyplot as plt
    _apply_ieee_style()

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


def generate_vector_field(
    x: List[float],
    y: List[float],
    u: List[List[float]],
    v: List[List[float]],
    output_path: Path,
    title: str = "Vector Field",
    format: str = "pdf",
    streamlines: bool = False,
) -> bool:
    """
    Generate vector field plot (flow fields, gradients).

    Args:
        x: X coordinates
        y: Y coordinates
        u: X-components of vectors u[y_idx][x_idx]
        v: Y-components of vectors v[y_idx][x_idx]
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)
        streamlines: Show streamlines instead of quiver

    Returns:
        True if successful, False otherwise
    """
    if not _check_matplotlib():
        typer.echo("[ERROR] matplotlib required for vector field", err=True)
        return False

    import matplotlib.pyplot as plt
    _apply_ieee_style()

    X, Y = np.meshgrid(x, y)
    U = np.array(u)
    V = np.array(v)

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN))

    if streamlines:
        speed = np.sqrt(U**2 + V**2)
        ax.streamplot(X, Y, U, V, color=speed, cmap='Blues', density=1.5,
                     linewidth=1, arrowsize=1)
    else:
        magnitude = np.sqrt(U**2 + V**2)
        ax.quiver(X, Y, U, V, magnitude, cmap='Blues', scale=20)

    ax.set_xlabel('X')
    ax.set_ylabel('Y')
    ax.set_title(title, fontweight="bold")
    ax.set_aspect('equal')

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_phase_portrait(
    x_range: Tuple[float, float],
    y_range: Tuple[float, float],
    dx_dy_func: str,
    output_path: Path,
    title: str = "Phase Portrait",
    format: str = "pdf",
    grid_size: int = 20,
) -> bool:
    """
    Generate phase portrait for dynamical systems (differential equations).

    Args:
        x_range: (x_min, x_max)
        y_range: (y_min, y_max)
        dx_dy_func: String defining dx/dt and dy/dt as Python expressions
                   e.g., "dx = y; dy = -x - 0.5*y"
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)
        grid_size: Number of points per axis

    Returns:
        True if successful, False otherwise
    """
    if not _check_matplotlib():
        typer.echo("[ERROR] matplotlib required for phase portrait", err=True)
        return False

    import matplotlib.pyplot as plt
    _apply_ieee_style()

    # Parse the dx/dy expressions
    try:
        parts = dx_dy_func.replace(' ', '').split(';')
        dx_expr = parts[0].split('=')[1]
        dy_expr = parts[1].split('=')[1]
    except (IndexError, ValueError):
        typer.echo("[ERROR] Invalid dx_dy_func format. Use: 'dx = y; dy = -x'", err=True)
        return False

    x = np.linspace(x_range[0], x_range[1], grid_size)
    y = np.linspace(y_range[0], y_range[1], grid_size)
    X, Y = np.meshgrid(x, y)

    # Evaluate vector field (SAFE: only allow numpy math)
    try:
        safe_dict = {"x": X, "y": Y, "np": np, "sin": np.sin, "cos": np.cos,
                    "exp": np.exp, "sqrt": np.sqrt, "abs": np.abs}
        DX = eval(dx_expr, {"__builtins__": {}}, safe_dict)
        DY = eval(dy_expr, {"__builtins__": {}}, safe_dict)
    except Exception as e:
        typer.echo(f"[ERROR] Failed to evaluate expressions: {e}", err=True)
        return False

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN))

    # Streamplot for phase portrait
    speed = np.sqrt(DX**2 + DY**2)
    ax.streamplot(X, Y, DX, DY, color=speed, cmap='Blues', density=1.5,
                 linewidth=1, arrowsize=1)

    ax.set_xlabel('x')
    ax.set_ylabel('y')
    ax.set_title(title, fontweight="bold")
    ax.set_xlim(x_range)
    ax.set_ylim(y_range)
    ax.set_aspect('equal')

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


# --- GPU/Hardware and LLM Visualizations ---

def generate_roofline_plot(
    peak_flops: float,
    peak_bandwidth: float,
    kernel_data: List[Dict[str, float]],
    output_path: Path,
    title: str = "Roofline Plot",
    format: str = "pdf",
    log_scale: bool = True,
) -> bool:
    """
    Generate roofline plot for GPU/hardware performance analysis.

    Args:
        peak_flops: Peak FLOPS (e.g., 19.5e12 for V100)
        peak_bandwidth: Peak memory bandwidth in bytes/s (e.g., 900e9 for V100)
        kernel_data: List of dicts with 'name', 'flops', 'bytes', 'achieved_flops'
        output_path: Output file path
        title: Chart title
        format: Output format
        log_scale: Use log-log scale (typical for roofline)

    Returns:
        True if successful, False otherwise
    """
    if not _check_matplotlib():
        typer.echo("[ERROR] matplotlib required for roofline plot", err=True)
        return False

    import matplotlib.pyplot as plt
    _apply_ieee_style()

    fig, ax = plt.subplots(figsize=(IEEE_DOUBLE_COLUMN, IEEE_SINGLE_COLUMN * 1.2))

    # Calculate ridge point (where compute and memory ceilings meet)
    ridge_point = peak_flops / peak_bandwidth  # FLOP/byte

    # Create x-axis (arithmetic intensity)
    x_min, x_max = 0.01, 1000
    x = np.logspace(np.log10(x_min), np.log10(x_max), 500) if log_scale else np.linspace(x_min, x_max, 500)

    # Memory ceiling: performance = bandwidth * arithmetic_intensity
    memory_ceiling = peak_bandwidth * x

    # Compute ceiling: performance = peak_flops
    compute_ceiling = np.full_like(x, peak_flops)

    # Roofline is the minimum of the two
    roofline = np.minimum(memory_ceiling, compute_ceiling)

    # Plot roofline
    ax.plot(x, roofline, 'b-', linewidth=2, label='Roofline')
    ax.axhline(y=peak_flops, color='b', linestyle='--', alpha=0.5, label=f'Peak: {peak_flops/1e12:.1f} TFLOPS')
    ax.axvline(x=ridge_point, color='gray', linestyle=':', alpha=0.5, label=f'Ridge: {ridge_point:.1f} FLOP/B')

    # Plot kernel data points
    colors = plt.cm.tab10(np.linspace(0, 1, len(kernel_data)))
    for i, kernel in enumerate(kernel_data):
        ai = kernel['flops'] / kernel['bytes'] if kernel['bytes'] > 0 else 1
        perf = kernel.get('achieved_flops', kernel['flops'])
        ax.scatter(ai, perf, s=100, c=[colors[i]], marker='o', label=kernel.get('name', f'Kernel {i}'), zorder=10)

    if log_scale:
        ax.set_xscale('log')
        ax.set_yscale('log')

    ax.set_xlabel('Arithmetic Intensity (FLOP/Byte)')
    ax.set_ylabel('Performance (FLOP/s)')
    ax.set_title(title, fontweight="bold")
    ax.legend(loc='lower right', fontsize=7)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_scaling_law_plot(
    data: List[Dict[str, float]],
    output_path: Path,
    x_label: str = "Parameters",
    y_label: str = "Loss",
    title: str = "Scaling Law",
    format: str = "pdf",
    fit_power_law: bool = True,
) -> bool:
    """
    Generate scaling law plot (log-log) common in LLM research.

    Args:
        data: List of dicts with 'x' and 'y' values (e.g., params vs loss)
        output_path: Output file path
        x_label: X-axis label
        y_label: Y-axis label
        title: Chart title
        format: Output format
        fit_power_law: Fit and display power law trend line

    Returns:
        True if successful, False otherwise
    """
    if not _check_matplotlib():
        typer.echo("[ERROR] matplotlib required for scaling law plot", err=True)
        return False

    # Validate input data
    if VALIDATION_AVAILABLE:
        try:
            data = validate_scaling_data(data)
        except ValidationError as e:
            typer.echo(f"[ERROR] {create_validation_error_message(e)}", err=True)
            return False
    else:
        # Fallback validation
        if not isinstance(data, list) or not data:
            typer.echo("[ERROR] Scaling data must be a non-empty list of dictionaries", err=True)
            return False

    import matplotlib.pyplot as plt
    _apply_ieee_style()

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN))

    x_vals = np.array([d['x'] for d in data])
    y_vals = np.array([d['y'] for d in data])

    # Plot data points
    ax.scatter(x_vals, y_vals, s=50, c='blue', alpha=0.7, label='Data')

    # Fit power law if requested (y = a * x^b)
    if fit_power_law and len(data) > 2:
        try:
            log_x = np.log(x_vals)
            log_y = np.log(y_vals)
            coeffs = np.polyfit(log_x, log_y, 1)
            b, log_a = coeffs[0], coeffs[1]
            a = np.exp(log_a)

            x_fit = np.logspace(np.log10(x_vals.min()), np.log10(x_vals.max()), 100)
            y_fit = a * x_fit ** b

            ax.plot(x_fit, y_fit, 'r--', linewidth=1.5, label=f'y = {a:.2e} * x^{b:.2f}')
        except Exception:
            pass  # Skip fit if it fails

    ax.set_xscale('log')
    ax.set_yscale('log')
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    ax.set_title(title, fontweight="bold")
    ax.legend(loc='best', fontsize=7)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_confusion_matrix(
    matrix: List[List[int]],
    labels: List[str],
    output_path: Path,
    title: str = "Confusion Matrix",
    format: str = "pdf",
    normalize: bool = False,
    cmap: str = "Blues",
) -> bool:
    """
    Generate confusion matrix for classification results.

    Args:
        matrix: 2D confusion matrix (actual rows, predicted cols)
        labels: Class labels
        output_path: Output file path
        title: Chart title
        format: Output format
        normalize: Normalize to percentages
        cmap: Colormap

    Returns:
        True if successful, False otherwise
    """
    if not _check_matplotlib():
        typer.echo("[ERROR] matplotlib required for confusion matrix", err=True)
        return False

    import matplotlib.pyplot as plt
    _apply_ieee_style()

    matrix_arr = np.array(matrix, dtype=float)

    if normalize:
        row_sums = matrix_arr.sum(axis=1, keepdims=True)
        matrix_arr = np.divide(matrix_arr, row_sums, where=row_sums != 0) * 100

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN))

    im = ax.imshow(matrix_arr, cmap=cmap)

    # Add colorbar
    cbar = ax.figure.colorbar(im, ax=ax, shrink=0.8)
    cbar.ax.set_ylabel('Count' if not normalize else 'Percentage (%)', rotation=-90, va="bottom")

    # Set ticks and labels
    ax.set_xticks(np.arange(len(labels)))
    ax.set_yticks(np.arange(len(labels)))
    ax.set_xticklabels(labels)
    ax.set_yticklabels(labels)

    # Rotate x labels
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right", rotation_mode="anchor")

    # Add text annotations
    thresh = matrix_arr.max() / 2
    for i in range(len(labels)):
        for j in range(len(labels)):
            val = matrix_arr[i, j]
            text = f'{val:.1f}%' if normalize else f'{int(val)}'
            color = "white" if val > thresh else "black"
            ax.text(j, i, text, ha="center", va="center", color=color, fontsize=7)

    ax.set_xlabel('Predicted')
    ax.set_ylabel('Actual')
    ax.set_title(title, fontweight="bold")

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_roc_curve(
    curves: Dict[str, Dict[str, List[float]]],
    output_path: Path,
    title: str = "ROC Curve",
    format: str = "pdf",
) -> bool:
    """
    Generate ROC curve for binary classification.

    Args:
        curves: Dict of {name: {'fpr': [...], 'tpr': [...], 'auc': float}}
        output_path: Output file path
        title: Chart title
        format: Output format

    Returns:
        True if successful, False otherwise
    """
    if not _check_matplotlib():
        typer.echo("[ERROR] matplotlib required for ROC curve", err=True)
        return False

    import matplotlib.pyplot as plt
    _apply_ieee_style()

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN))

    colors = plt.cm.tab10(np.linspace(0, 1, len(curves)))

    for i, (name, data) in enumerate(curves.items()):
        fpr = data['fpr']
        tpr = data['tpr']
        auc = data.get('auc', 0)
        ax.plot(fpr, tpr, color=colors[i], linewidth=1.5, label=f'{name} (AUC={auc:.3f})')

    # Diagonal reference line
    ax.plot([0, 1], [0, 1], 'k--', linewidth=1, alpha=0.5, label='Random')

    ax.set_xlim([0, 1])
    ax.set_ylim([0, 1.05])
    ax.set_xlabel('False Positive Rate')
    ax.set_ylabel('True Positive Rate')
    ax.set_title(title, fontweight="bold")
    ax.legend(loc='lower right', fontsize=7)
    ax.grid(True, alpha=0.3)
    ax.set_aspect('equal')

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_training_curves(
    runs: Dict[str, Dict[str, List[float]]],
    output_path: Path,
    x_label: str = "Step",
    y_label: str = "Loss",
    title: str = "Training Curves",
    format: str = "pdf",
    log_y: bool = False,
) -> bool:
    """
    Generate training curves for multiple runs (loss, accuracy, etc.).

    Args:
        runs: Dict of {run_name: {'x': [...], 'y': [...], 'std': [...]}}
        output_path: Output file path
        x_label: X-axis label
        y_label: Y-axis label
        title: Chart title
        format: Output format
        log_y: Use log scale for Y axis

    Returns:
        True if successful, False otherwise
    """
    if not _check_matplotlib():
        typer.echo("[ERROR] matplotlib required for training curves", err=True)
        return False

    import matplotlib.pyplot as plt
    _apply_ieee_style()

    fig, ax = plt.subplots(figsize=(IEEE_DOUBLE_COLUMN, IEEE_SINGLE_COLUMN))

    colors = plt.cm.tab10(np.linspace(0, 1, len(runs)))

    for i, (name, data) in enumerate(runs.items()):
        x = data['x']
        y = data['y']
        ax.plot(x, y, color=colors[i], linewidth=1.5, label=name)

        # Add shaded std region if available
        if 'std' in data:
            std = np.array(data['std'])
            y_arr = np.array(y)
            ax.fill_between(x, y_arr - std, y_arr + std, color=colors[i], alpha=0.2)

    if log_y:
        ax.set_yscale('log')

    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    ax.set_title(title, fontweight="bold")
    ax.legend(loc='best', fontsize=7)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_embedding_scatter(
    embeddings: List[Dict[str, Any]],
    output_path: Path,
    title: str = "Embedding Space",
    format: str = "pdf",
    method: str = "tsne",
    perplexity: int = 30,
) -> bool:
    """
    Generate t-SNE or UMAP scatter plot of embeddings.

    Args:
        embeddings: List of dicts with 'vector' (list of floats), 'label', 'text' (optional)
        output_path: Output file path
        title: Chart title
        format: Output format
        method: 'tsne' or 'umap'
        perplexity: t-SNE perplexity parameter

    Returns:
        True if successful, False otherwise
    """
    if not _check_matplotlib():
        typer.echo("[ERROR] matplotlib required for embedding scatter", err=True)
        return False

    import matplotlib.pyplot as plt
    _apply_ieee_style()

    # Check for sklearn
    try:
        from sklearn.manifold import TSNE
        has_tsne = True
    except ImportError:
        has_tsne = False

    # Check for UMAP
    try:
        from umap import UMAP
        has_umap = True
    except ImportError:
        has_umap = False

    vectors = np.array([e['vector'] for e in embeddings])
    labels = [e.get('label', 'unknown') for e in embeddings]
    unique_labels = list(set(labels))

    # Reduce dimensionality
    if method == 'umap' and has_umap:
        reducer = UMAP(n_components=2, random_state=42)
        coords = reducer.fit_transform(vectors)
    elif has_tsne:
        reducer = TSNE(n_components=2, perplexity=min(perplexity, len(vectors) - 1), random_state=42)
        coords = reducer.fit_transform(vectors)
    else:
        # Fallback: just use first 2 dimensions
        coords = vectors[:, :2] if vectors.shape[1] >= 2 else vectors

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN))

    colors = plt.cm.tab10(np.linspace(0, 1, len(unique_labels)))
    color_map = {label: colors[i] for i, label in enumerate(unique_labels)}

    for label in unique_labels:
        mask = [l == label for l in labels]
        ax.scatter(coords[mask, 0], coords[mask, 1], s=20, c=[color_map[label]],
                  label=label, alpha=0.7)

    ax.set_xlabel(f'{method.upper()} 1')
    ax.set_ylabel(f'{method.upper()} 2')
    ax.set_title(title, fontweight="bold")
    if len(unique_labels) <= 10:
        ax.legend(loc='best', fontsize=6)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_attention_heatmap(
    attention_weights: List[List[float]],
    tokens: List[str],
    output_path: Path,
    title: str = "Attention Weights",
    format: str = "pdf",
    cmap: str = "Blues",
) -> bool:
    """
    Generate attention heatmap for transformer models.

    Args:
        attention_weights: 2D attention matrix [query_len, key_len]
        tokens: List of token strings (for labels)
        output_path: Output file path
        title: Chart title
        format: Output format
        cmap: Colormap

    Returns:
        True if successful, False otherwise
    """
    if not _check_matplotlib():
        typer.echo("[ERROR] matplotlib required for attention heatmap", err=True)
        return False

    import matplotlib.pyplot as plt
    _apply_ieee_style()

    matrix = np.array(attention_weights)

    fig, ax = plt.subplots(figsize=(IEEE_DOUBLE_COLUMN, IEEE_DOUBLE_COLUMN * 0.8))

    im = ax.imshow(matrix, cmap=cmap, aspect='auto')

    # Colorbar
    cbar = ax.figure.colorbar(im, ax=ax, shrink=0.8)
    cbar.ax.set_ylabel('Attention Weight', rotation=-90, va="bottom")

    # Token labels
    ax.set_xticks(np.arange(len(tokens)))
    ax.set_yticks(np.arange(len(tokens)))
    ax.set_xticklabels(tokens, fontsize=6)
    ax.set_yticklabels(tokens, fontsize=6)

    plt.setp(ax.get_xticklabels(), rotation=45, ha="right", rotation_mode="anchor")

    ax.set_xlabel('Key Tokens')
    ax.set_ylabel('Query Tokens')
    ax.set_title(title, fontweight="bold")

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_throughput_latency(
    data: List[Dict[str, float]],
    output_path: Path,
    title: str = "Throughput vs Latency",
    format: str = "pdf",
) -> bool:
    """
    Generate throughput vs latency plot for GPU/inference benchmarks.

    Args:
        data: List of dicts with 'name', 'throughput', 'latency'
        output_path: Output file path
        title: Chart title
        format: Output format

    Returns:
        True if successful, False otherwise
    """
    if not _check_matplotlib():
        typer.echo("[ERROR] matplotlib required for throughput-latency plot", err=True)
        return False

    import matplotlib.pyplot as plt
    _apply_ieee_style()

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN))

    colors = plt.cm.tab10(np.linspace(0, 1, len(data)))

    for i, point in enumerate(data):
        ax.scatter(point['latency'], point['throughput'], s=100, c=[colors[i]],
                  label=point.get('name', f'Config {i}'), marker='o')

    ax.set_xlabel('Latency (ms)')
    ax.set_ylabel('Throughput (samples/s)')
    ax.set_title(title, fontweight="bold")
    ax.legend(loc='best', fontsize=7)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


# --- ML Classification and Biology Visualizations ---

def generate_precision_recall(
    curves: Dict[str, Dict[str, List[float]]],
    output_path: Path,
    title: str = "Precision-Recall Curve",
    format: str = "pdf",
) -> bool:
    """
    Generate Precision-Recall curve for classification.

    Args:
        curves: Dict of {name: {'precision': [...], 'recall': [...], 'ap': float}}
        output_path: Output file path
        title: Chart title
        format: Output format

    Returns:
        True if successful, False otherwise
    """
    if not _check_matplotlib():
        typer.echo("[ERROR] matplotlib required for PR curve", err=True)
        return False

    import matplotlib.pyplot as plt
    _apply_ieee_style()

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN))

    colors = plt.cm.tab10(np.linspace(0, 1, len(curves)))

    for i, (name, data) in enumerate(curves.items()):
        precision = data['precision']
        recall = data['recall']
        ap = data.get('ap', 0)
        ax.plot(recall, precision, color=colors[i], linewidth=1.5,
               label=f'{name} (AP={ap:.3f})')

    ax.set_xlim([0, 1])
    ax.set_ylim([0, 1.05])
    ax.set_xlabel('Recall')
    ax.set_ylabel('Precision')
    ax.set_title(title, fontweight="bold")
    ax.legend(loc='lower left', fontsize=7)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_violin_plot(
    data: Dict[str, List[float]],
    output_path: Path,
    title: str = "Violin Plot",
    format: str = "pdf",
    x_label: str = "",
    y_label: str = "Value",
) -> bool:
    """
    Generate violin plot for distribution comparison.

    Args:
        data: Dict of {group_name: [values]}
        output_path: Output file path
        title: Chart title
        format: Output format
        x_label: X-axis label
        y_label: Y-axis label

    Returns:
        True if successful, False otherwise
    """
    if not _check_matplotlib():
        typer.echo("[ERROR] matplotlib required for violin plot", err=True)
        return False

    import matplotlib.pyplot as plt
    _apply_ieee_style()

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN))

    positions = list(range(len(data)))
    labels = list(data.keys())
    values = list(data.values())

    parts = ax.violinplot(values, positions=positions, showmeans=True, showmedians=True)

    # Color the violins
    for pc in parts['bodies']:
        pc.set_facecolor('#1f77b4')
        pc.set_alpha(0.7)

    ax.set_xticks(positions)
    ax.set_xticklabels(labels, rotation=45, ha='right')
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    ax.set_title(title, fontweight="bold")
    ax.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_volcano_plot(
    data: List[Dict[str, float]],
    output_path: Path,
    title: str = "Volcano Plot",
    format: str = "pdf",
    fc_threshold: float = 1.0,
    pval_threshold: float = 0.05,
) -> bool:
    """
    Generate volcano plot for differential expression analysis.

    Args:
        data: List of dicts with 'gene', 'log2fc', 'pvalue'
        output_path: Output file path
        title: Chart title
        format: Output format
        fc_threshold: Log2 fold change threshold for significance
        pval_threshold: P-value threshold for significance

    Returns:
        True if successful, False otherwise
    """
    if not _check_matplotlib():
        typer.echo("[ERROR] matplotlib required for volcano plot", err=True)
        return False

    import matplotlib.pyplot as plt
    _apply_ieee_style()

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN))

    log2fc = np.array([d['log2fc'] for d in data])
    pvals = np.array([d['pvalue'] for d in data])
    neg_log_pval = -np.log10(pvals + 1e-300)  # Avoid log(0)

    # Color by significance
    colors = []
    for i in range(len(data)):
        if abs(log2fc[i]) >= fc_threshold and pvals[i] <= pval_threshold:
            colors.append('red' if log2fc[i] > 0 else 'blue')
        else:
            colors.append('gray')

    ax.scatter(log2fc, neg_log_pval, c=colors, s=10, alpha=0.6)

    # Threshold lines
    ax.axhline(y=-np.log10(pval_threshold), color='gray', linestyle='--', linewidth=0.5)
    ax.axvline(x=fc_threshold, color='gray', linestyle='--', linewidth=0.5)
    ax.axvline(x=-fc_threshold, color='gray', linestyle='--', linewidth=0.5)

    ax.set_xlabel('Log₂ Fold Change')
    ax.set_ylabel('-Log₁₀ P-value')
    ax.set_title(title, fontweight="bold")

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_survival_curve(
    curves: Dict[str, Dict[str, List[float]]],
    output_path: Path,
    title: str = "Kaplan-Meier Survival Curve",
    format: str = "pdf",
) -> bool:
    """
    Generate Kaplan-Meier survival curve.

    Args:
        curves: Dict of {group: {'time': [...], 'survival': [...], 'ci_lower': [...], 'ci_upper': [...]}}
        output_path: Output file path
        title: Chart title
        format: Output format

    Returns:
        True if successful, False otherwise
    """
    if not _check_matplotlib():
        typer.echo("[ERROR] matplotlib required for survival curve", err=True)
        return False

    import matplotlib.pyplot as plt
    _apply_ieee_style()

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN))

    colors = plt.cm.tab10(np.linspace(0, 1, len(curves)))

    for i, (name, data) in enumerate(curves.items()):
        time = data['time']
        survival = data['survival']
        ax.step(time, survival, where='post', color=colors[i], linewidth=1.5, label=name)

        # Confidence interval if available
        if 'ci_lower' in data and 'ci_upper' in data:
            ax.fill_between(time, data['ci_lower'], data['ci_upper'],
                          step='post', alpha=0.2, color=colors[i])

    ax.set_xlim([0, None])
    ax.set_ylim([0, 1.05])
    ax.set_xlabel('Time')
    ax.set_ylabel('Survival Probability')
    ax.set_title(title, fontweight="bold")
    ax.legend(loc='lower left', fontsize=7)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_manhattan_plot(
    data: List[Dict[str, Any]],
    output_path: Path,
    title: str = "Manhattan Plot",
    format: str = "pdf",
    genome_wide_line: float = 5e-8,
    suggestive_line: float = 1e-5,
) -> bool:
    """
    Generate Manhattan plot for GWAS results.

    Args:
        data: List of dicts with 'chr', 'pos', 'pvalue'
        output_path: Output file path
        title: Chart title
        format: Output format
        genome_wide_line: P-value threshold for genome-wide significance
        suggestive_line: P-value threshold for suggestive significance

    Returns:
        True if successful, False otherwise
    """
    if not _check_matplotlib():
        typer.echo("[ERROR] matplotlib required for Manhattan plot", err=True)
        return False

    import matplotlib.pyplot as plt
    _apply_ieee_style()

    fig, ax = plt.subplots(figsize=(IEEE_DOUBLE_COLUMN, IEEE_SINGLE_COLUMN))

    # Sort by chromosome and position
    sorted_data = sorted(data, key=lambda x: (x['chr'], x['pos']))

    # Calculate cumulative positions
    chr_offset = {}
    current_offset = 0
    prev_chr = None

    x_positions = []
    colors_list = []
    neg_log_pvals = []

    chr_colors = ['#1f77b4', '#aec7e8']  # Alternating colors

    for d in sorted_data:
        chr_num = d['chr']
        if chr_num != prev_chr:
            if prev_chr is not None:
                current_offset += max(p['pos'] for p in sorted_data if p['chr'] == prev_chr) + 1e7
            chr_offset[chr_num] = current_offset
            prev_chr = chr_num

        x_pos = chr_offset[chr_num] + d['pos']
        x_positions.append(x_pos)
        neg_log_pvals.append(-np.log10(d['pvalue'] + 1e-300))
        colors_list.append(chr_colors[int(chr_num) % 2] if isinstance(chr_num, int) else chr_colors[0])

    ax.scatter(x_positions, neg_log_pvals, c=colors_list, s=5, alpha=0.7)

    # Significance lines
    ax.axhline(y=-np.log10(genome_wide_line), color='red', linestyle='--', linewidth=0.5, label='Genome-wide')
    ax.axhline(y=-np.log10(suggestive_line), color='blue', linestyle='--', linewidth=0.5, label='Suggestive')

    ax.set_xlabel('Chromosome')
    ax.set_ylabel('-Log₁₀ P-value')
    ax.set_title(title, fontweight="bold")
    ax.legend(loc='upper right', fontsize=6)

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_feature_importance(
    features: Dict[str, float],
    output_path: Path,
    title: str = "Feature Importance",
    format: str = "pdf",
    top_n: int = 20,
) -> bool:
    """
    Generate horizontal bar chart of feature importances.

    Args:
        features: Dict of {feature_name: importance_score}
        output_path: Output file path
        title: Chart title
        format: Output format
        top_n: Show top N features

    Returns:
        True if successful, False otherwise
    """
    if not _check_matplotlib():
        typer.echo("[ERROR] matplotlib required for feature importance plot", err=True)
        return False

    import matplotlib.pyplot as plt
    _apply_ieee_style()

    # Sort by importance and take top N
    sorted_features = sorted(features.items(), key=lambda x: x[1], reverse=True)[:top_n]
    names = [f[0] for f in sorted_features][::-1]  # Reverse for bottom-to-top
    values = [f[1] for f in sorted_features][::-1]

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN * 1.2))

    ax.barh(range(len(names)), values, color='#1f77b4', alpha=0.8)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=7)
    ax.set_xlabel('Importance')
    ax.set_title(title, fontweight="bold")
    ax.grid(True, alpha=0.3, axis='x')

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_calibration_plot(
    data: Dict[str, Dict[str, List[float]]],
    output_path: Path,
    title: str = "Calibration Plot",
    format: str = "pdf",
) -> bool:
    """
    Generate calibration plot (reliability diagram) for classification.

    Args:
        data: Dict of {model_name: {'predicted_probs': [...], 'true_fractions': [...]}}
        output_path: Output file path
        title: Chart title
        format: Output format

    Returns:
        True if successful, False otherwise
    """
    if not _check_matplotlib():
        typer.echo("[ERROR] matplotlib required for calibration plot", err=True)
        return False

    import matplotlib.pyplot as plt
    _apply_ieee_style()

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN))

    # Diagonal line (perfect calibration)
    ax.plot([0, 1], [0, 1], 'k--', linewidth=1, label='Perfectly calibrated')

    colors = plt.cm.tab10(np.linspace(0, 1, len(data)))

    for i, (name, d) in enumerate(data.items()):
        predicted = d['predicted_probs']
        actual = d['true_fractions']
        ax.plot(predicted, actual, 's-', color=colors[i], linewidth=1.5,
               markersize=4, label=name)

    ax.set_xlim([0, 1])
    ax.set_ylim([0, 1])
    ax.set_xlabel('Mean Predicted Probability')
    ax.set_ylabel('Fraction of Positives')
    ax.set_title(title, fontweight="bold")
    ax.legend(loc='lower right', fontsize=7)
    ax.grid(True, alpha=0.3)
    ax.set_aspect('equal')

    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
    plt.close()
    return True


def generate_latex_table(
    title: str,
    headers: List[str],
    rows: List[List[str]],
    output_path: Path,
    caption: Optional[str] = None,
    label: Optional[str] = None,
) -> bool:
    """
    Generate LaTeX table with proper escaping and formatting.

    Args:
        title: Table title (for label if not provided)
        headers: Column headers
        rows: Table data rows
        output_path: Output .tex file path
        caption: Table caption (defaults to title)
        label: Table label (defaults to title-based)

    Returns:
        True if successful
    """
    def escape_latex(text: str) -> str:
        """Escape LaTeX special characters."""
        replacements = [
            ("\\", "\\textbackslash{}"),
            ("&", "\\&"),
            ("%", "\\%"),
            ("$", "\\$"),
            ("#", "\\#"),
            ("_", "\\_"),
            ("{", "\\{"),
            ("}", "\\}"),
            ("~", "\\textasciitilde{}"),
            ("^", "\\textasciicircum{}"),
        ]
        for old, new in replacements:
            text = text.replace(old, new)
        return text

    # Build column specification
    col_spec = "|" + "|".join(["l"] * len(headers)) + "|"

    # Generate label
    if label is None:
        label = "tab:" + title.lower().replace(" ", "_").replace("-", "_")

    lines = [
        "\\begin{table}[htbp]",
        "\\centering",
        "\\small",
        f"\\begin{{tabular}}{{{col_spec}}}",
        "\\hline",
        " & ".join(f"\\textbf{{{escape_latex(h)}}}" for h in headers) + " \\\\",
        "\\hline",
    ]

    for row in rows:
        escaped_row = [escape_latex(str(cell)) for cell in row]
        lines.append(" & ".join(escaped_row) + " \\\\")

    lines.extend([
        "\\hline",
        "\\end{tabular}",
        f"\\caption{{{escape_latex(caption or title)}}}",
        f"\\label{{{label}}}",
        "\\end{table}",
    ])

    output_path.write_text("\n".join(lines))
    return True


def generate_architecture_diagram(
    project_name: str,
    components: List[Dict[str, Any]],
    output_path: Path,
    format: str = "pdf",
    backend: str = "graphviz",
) -> bool:
    """
    Generate architecture diagram from component list.

    Args:
        project_name: Name of the project/system
        components: List of component dictionaries with name, type, dependencies
        output_path: Output file path
        format: Output format (pdf, png, svg)
        backend: Rendering backend (graphviz, mermaid)

    Returns:
        True if successful, False otherwise
    """
    if backend == "graphviz":
        return _generate_graphviz_architecture(project_name, components, output_path, format)
    else:
        return _generate_mermaid_architecture(project_name, components, output_path, format)


def _generate_graphviz_architecture(
    project_name: str,
    components: List[Dict[str, Any]],
    output_path: Path,
    format: str,
) -> bool:
    """Generate architecture diagram using Graphviz."""
    lines = [
        "digraph architecture {",
        '    rankdir=TB;',
        '    compound=true;',
        '    node [shape=box, fontname="Helvetica", fontsize=10, style="filled"];',
        '    edge [fontname="Helvetica", fontsize=8];',
        "",
        f'    subgraph cluster_{project_name.replace(" ", "_")} {{',
        f'        label="{project_name}";',
        '        style="rounded";',
        '        color="#333333";',
    ]

    # Define node colors by type
    type_colors = {
        "module": "#E3F2FD",      # Light blue
        "interface": "#E8F5E9",   # Light green
        "database": "#FFF3E0",    # Light orange
        "external": "#F3E5F5",    # Light purple
        "config": "#ECEFF1",      # Light gray
    }

    # Add nodes
    for comp in components[:15]:  # Limit components
        name = comp.get("name", "Unknown")
        comp_type = comp.get("type", "module")
        safe_name = name.replace(" ", "_").replace("-", "_").replace(".", "_")
        color = type_colors.get(comp_type, "#FFFFFF")

        lines.append(f'        {safe_name} [label="{name}\\n<{comp_type}>", fillcolor="{color}"];')

    lines.append("    }")
    lines.append("")

    # Add edges
    for comp in components[:15]:
        name = comp.get("name", "").replace(" ", "_").replace("-", "_").replace(".", "_")
        deps = comp.get("dependencies", [])

        comp_names = {c.get("name", "").replace(" ", "_").replace("-", "_").replace(".", "_")
                      for c in components}

        for dep in deps[:5]:
            dep_safe = dep.replace(" ", "_").replace("-", "_").replace(".", "_")
            if dep_safe in comp_names:
                lines.append(f"    {name} -> {dep_safe};")

    lines.append("}")
    dot_code = "\n".join(lines)

    return _render_graphviz(dot_code, output_path, format)


def _generate_mermaid_architecture(
    project_name: str,
    components: List[Dict[str, Any]],
    output_path: Path,
    format: str,
) -> bool:
    """Generate architecture diagram using Mermaid."""
    lines = [
        "flowchart TB",
        f'    subgraph {project_name.replace(" ", "_")}["{project_name}"]',
    ]

    for comp in components[:15]:
        name = comp.get("name", "Unknown")
        comp_type = comp.get("type", "module")
        safe_name = name.replace(" ", "_").replace("-", "_").replace(".", "_")
        lines.append(f'        {safe_name}["{name}<br/><i>{comp_type}</i>"]')

    lines.append("    end")

    # Add edges
    comp_names = {c.get("name", "").replace(" ", "_").replace("-", "_").replace(".", "_")
                  for c in components}

    for comp in components[:15]:
        name = comp.get("name", "").replace(" ", "_").replace("-", "_").replace(".", "_")
        for dep in comp.get("dependencies", [])[:5]:
            dep_safe = dep.replace(" ", "_").replace("-", "_").replace(".", "_")
            if dep_safe in comp_names:
                lines.append(f"    {name} --> {dep_safe}")

    mermaid_code = "\n".join(lines)
    return _render_mermaid(mermaid_code, output_path, format)


def generate_workflow_diagram(
    stages: List[str],
    output_path: Path,
    format: str = "pdf",
    with_gates: bool = True,
    backend: str = "mermaid",
) -> bool:
    """
    Generate workflow/pipeline diagram.

    Args:
        stages: List of stage names
        output_path: Output file path
        format: Output format
        with_gates: Include quality gates between stages
        backend: Rendering backend (mermaid, graphviz)

    Returns:
        True if successful, False otherwise
    """
    if backend == "graphviz":
        lines = [
            "digraph workflow {",
            '    rankdir=LR;',
            '    node [fontname="Helvetica", fontsize=10];',
        ]

        for i, stage in enumerate(stages):
            safe_name = f"S{i}"
            lines.append(f'    {safe_name} [label="{stage}", shape=box, style="filled", fillcolor="#E3F2FD"];')

            if i > 0:
                if with_gates:
                    gate = f"G{i-1}"
                    lines.append(f'    {gate} [label="", shape=diamond, width=0.3, height=0.3, style="filled", fillcolor="#FFE082"];')
                    lines.append(f"    S{i-1} -> {gate} -> {safe_name};")
                else:
                    lines.append(f"    S{i-1} -> {safe_name};")

        lines.append("}")
        return _render_graphviz("\n".join(lines), output_path, format)

    else:  # mermaid
        lines = ["flowchart LR"]

        # First define all stage nodes
        for i, stage in enumerate(stages):
            safe_name = f"S{i}"
            lines.append(f'    {safe_name}["{stage}"]')

        # Then define gates and connections
        for i in range(1, len(stages)):
            if with_gates:
                gate = f"G{i-1}"
                lines.append(f"    {gate}{{Gate}}")
                lines.append(f"    S{i-1} --> {gate}")
                lines.append(f"    {gate} --> S{i}")
            else:
                lines.append(f"    S{i-1} --> S{i}")

        return _render_mermaid("\n".join(lines), output_path, format)


def generate_lean4_theorem_figure(
    requirement: str,
    theorem_name: str,
    output_path: Path,
) -> bool:
    """
    Generate formally verified theorem using lean4-prove skill.

    Args:
        requirement: Natural language requirement to formalize
        theorem_name: Name for the theorem
        output_path: Output file for the Lean4 code

    Returns:
        True if successful, False otherwise
    """
    if not LEAN4_PROVE_SCRIPT.exists():
        typer.echo("[ERROR] lean4-prove skill not available", err=True)
        return False

    try:
        result = subprocess.run(
            [str(LEAN4_PROVE_SCRIPT), "prove", requirement, "--name", theorem_name],
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutes for proof
        )

        if result.returncode == 0:
            output_path.write_text(result.stdout)
            typer.echo(f"[OK] Verified theorem saved to {output_path}")
            return True
        else:
            typer.echo(f"[ERROR] lean4-prove: {result.stderr}", err=True)
            return False

    except subprocess.TimeoutExpired:
        typer.echo("[ERROR] lean4-prove timed out", err=True)
        return False


# --- CLI Commands ---

@app.command()
def deps(
    project: str = typer.Option(..., "--project", "-p", help="Path to Python project"),
    output: str = typer.Option("dependencies.pdf", "--output", "-o", help="Output file"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg, dot, json"),
    depth: int = typer.Option(2, "--depth", "-d", help="Maximum dependency depth"),
    backend: str = typer.Option("graphviz", "--backend", "-b", help="Backend: graphviz, mermaid, networkx"),
):
    """Generate dependency graph from Python project."""
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
):
    """Generate UML class diagram from Python project."""
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
):
    """Generate architecture diagram from project or assess output."""
    output_path = Path(output)
    project_path = Path(project)

    # Try to load assess output if project is a JSON file
    if project_path.suffix == ".json" and project_path.exists():
        data = json.loads(project_path.read_text())
        components = data.get("components", [])
        project_name = data.get("project_name", project_path.stem)
    else:
        # Create placeholder components from project name
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
):
    """Generate metrics chart from JSON data."""
    input_path = Path(input)
    output_path = Path(output)

    try:
        if VALIDATION_AVAILABLE:
            data = validate_json_file(input_path, "metrics data")
        else:
            data = json.loads(input_path.read_text())

        # Handle different input formats
        if isinstance(data, dict):
            if "metrics" in data:
                metrics_data = data["metrics"]
            else:
                metrics_data = data
        elif isinstance(data, list):
            metrics_data = {item.get("name", f"item{i}"): item.get("value", 0)
                           for i, item in enumerate(data)}
        else:
            raise ValidationError("Invalid input format - must be dictionary or list")

        # Validate metrics data
        if VALIDATION_AVAILABLE:
            metrics_data = validate_metrics_data(metrics_data)

    except ValidationError as e:
        typer.echo(f"[ERROR] {create_validation_error_message(e)}", err=True)
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
):
    """Generate LaTeX table from JSON data."""
    input_path = Path(input)
    output_path = Path(output)

    if not input_path.exists():
        typer.echo(f"[ERROR] Input file not found: {input_path}", err=True)
        raise typer.Exit(1)

    data = json.loads(input_path.read_text())

    # Extract headers and rows from various formats
    if isinstance(data, dict):
        if "headers" in data and "rows" in data:
            headers = data["headers"]
            rows = data["rows"]
        elif "features" in data:
            features = data["features"]
            headers = ["Feature", "Status", "LOC"]
            rows = [[f.get("name", ""), f.get("status", ""), str(f.get("loc", ""))]
                   for f in features]
        else:
            headers = ["Key", "Value"]
            rows = [[k, str(v)] for k, v in data.items()]
    elif isinstance(data, list):
        if data and isinstance(data[0], dict):
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
):
    """Generate workflow diagram from stage list."""
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
):
    """Generate formally verified theorem from requirement (uses lean4-prove)."""
    output_path = Path(output)

    success = generate_lean4_theorem_figure(requirement, name, output_path)
    if success:
        typer.echo(f"Generated: {output_path}")


# --- Advanced Scientific/Engineering Visualizations ---

@app.command()
def sankey(
    input: str = typer.Option(..., "--input", "-i", help="JSON file with flows [{source, target, value}]"),
    output: str = typer.Option("sankey.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Flow Diagram", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg, html"),
):
    """Generate Sankey diagram for flow/energy/mass balances."""
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
        typer.echo(f"[ERROR] {create_validation_error_message(e)}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"[ERROR] Failed to load input data: {e}", err=True)
        raise typer.Exit(1)

    success = generate_sankey_diagram(flows, output_path, title, format)
    if success:
        typer.echo(f"Generated: {output_path}")


@app.command()
def heatmap(
    input: str = typer.Option(..., "--input", "-i", help="JSON file with nested dict {row: {col: value}}"),
    output: str = typer.Option("heatmap.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Heatmap", "--title", "-t", help="Chart title"),
    cmap: str = typer.Option("Blues", "--cmap", "-c", help="Colormap: Blues, viridis, plasma, etc."),
):
    """Generate heatmap for field distributions or correlation matrices."""
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
def treemap(
    input: str = typer.Option(..., "--input", "-i", help="JSON file with {label: size} dict"),
    output: str = typer.Option("treemap.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Treemap", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg, html"),
):
    """Generate treemap for hierarchical size data (modules, zones, etc.)."""
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
):
    """Generate sunburst chart for hierarchical fault trees or breakdowns."""
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
):
    """Generate force-directed graph for system topology or fault trees."""
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
            # Output structured summary for agents
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
):
    """Generate parallel coordinates for multi-dimensional design space analysis."""
    input_path = Path(input)
    output_path = Path(output)

    if not input_path.exists():
        typer.echo(f"[ERROR] Input file not found: {input_path}", err=True)
        raise typer.Exit(1)

    data = json.loads(input_path.read_text())

    success = generate_parallel_coordinates(
        data, output_path, title, format,
        color_by if color_by else None
    )
    if success:
        typer.echo(f"Generated: {output_path}")


@app.command()
def radar(
    input: str = typer.Option(..., "--input", "-i", help="JSON file with {series: {dim: value}}"),
    output: str = typer.Option("radar.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Radar Chart", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg"),
):
    """Generate radar/spider chart for multi-attribute comparison."""
    input_path = Path(input)
    output_path = Path(output)

    if not input_path.exists():
        typer.echo(f"[ERROR] Input file not found: {input_path}", err=True)
        raise typer.Exit(1)

    data = json.loads(input_path.read_text())

    success = generate_radar_chart(data, output_path, title, format)
    if success:
        typer.echo(f"Generated: {output_path}")


@app.command()
def bode(
    num: str = typer.Option(..., "--num", "-n", help="Numerator coefficients: 1,2,3"),
    den: str = typer.Option(..., "--den", "-d", help="Denominator coefficients: 1,2,3,4"),
    output: str = typer.Option("bode.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Bode Plot", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg"),
    freq_min: float = typer.Option(0.01, "--freq-min", help="Min frequency (rad/s)"),
    freq_max: float = typer.Option(100.0, "--freq-max", help="Max frequency (rad/s)"),
):
    """Generate Bode plot (magnitude/phase vs frequency) for control systems."""
    output_path = Path(output)
    num_list = [float(x.strip()) for x in num.split(",")]
    den_list = [float(x.strip()) for x in den.split(",")]

    success = generate_bode_plot(
        num_list, den_list, output_path, title, format,
        (freq_min, freq_max)
    )
    if success:
        typer.echo(f"Generated: {output_path}")


@app.command()
def nyquist(
    num: str = typer.Option(..., "--num", "-n", help="Numerator coefficients: 1,2,3"),
    den: str = typer.Option(..., "--den", "-d", help="Denominator coefficients: 1,2,3,4"),
    output: str = typer.Option("nyquist.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Nyquist Plot", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg"),
):
    """Generate Nyquist plot for stability analysis of control systems."""
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
):
    """Generate enhanced root locus plot for control system gain analysis."""
    output_path = Path(output)
    num_list = [float(x.strip()) for x in num.split(",")]
    den_list = [float(x.strip()) for x in den.split(",")]

    success = generate_root_locus(num_list, den_list, output_path, title, format,
                                 breakaway, (gain_min, gain_max))
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
):
    """Generate pole-zero map with stability analysis for control systems."""
    output_path = Path(output)
    
    # Parse complex numbers
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


@app.command("state-space")
def state_space(
    A: str = typer.Option(..., "--A", help="State matrix: [[1,2],[3,4]]"),
    B: str = typer.Option(..., "--B", help="Input matrix: [[1],[0]]"),
    C: str = typer.Option(..., "--C", help="Output matrix: [[1,0]]"),
    D: str = typer.Option(..., "--D", help="Feedthrough matrix: [[0]]"),
    output: str = typer.Option("statespace.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("State Space System", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg"),
    poles_zeros: bool = typer.Option(True, "--poles-zeros/--no-poles-zeros", help="Include pole-zero analysis"),
    eigenvalues: bool = typer.Option(True, "--eigenvalues/--no-eigenvalues", help="Show eigenvalue analysis"),
):
    """Generate comprehensive state-space system visualization."""
    output_path = Path(output)
    
    # Parse matrices from JSON strings
    try:
        A_matrix = json.loads(A)
        B_matrix = json.loads(B)
        C_matrix = json.loads(C)
        D_matrix = json.loads(D)
    except json.JSONDecodeError as e:
        typer.echo(f"[ERROR] Invalid matrix format: {e}", err=True)
        raise typer.Exit(1)
    
    success = generate_state_space_visualization(
        A_matrix, B_matrix, C_matrix, D_matrix, output_path, title, format,
        poles_zeros, eigenvalues
    )
    if success:
        typer.echo(f"Generated: {output_path}")


@app.command()
def spectrogram(
    input: str = typer.Option(..., "--input", "-i", help="JSON file with {signal: [...], sample_rate: Hz}"),
    output: str = typer.Option("spectrogram.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Spectrogram", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg"),
    window: str = typer.Option("hann", "--window", "-w", help="Window type: hann, hamming, blackman, rectangular"),
    window_size: int = typer.Option(256, "--window-size", help="FFT window size"),
    overlap: float = typer.Option(0.5, "--overlap", help="Overlap fraction (0-1)"),
):
    """Generate spectrogram for time-frequency signal analysis."""
    input_path = Path(input)
    output_path = Path(output)
    
    try:
        if VALIDATION_AVAILABLE:
            data = validate_json_file(input_path, "spectrogram data")
        else:
            data = json.loads(input_path.read_text())
        
        signal = data.get('signal', [])
        sample_rate = data.get('sample_rate', 1.0)
        
        if not signal:
            raise ValidationError("Signal data cannot be empty")
        
    except ValidationError as e:
        typer.echo(f"[ERROR] {create_validation_error_message(e)}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"[ERROR] Failed to load input data: {e}", err=True)
        raise typer.Exit(1)
    
    success = generate_spectrogram(signal, sample_rate, output_path, title, format,
                                  window, window_size, overlap)
    if success:
        typer.echo(f"Generated: {output_path}")


@app.command("filter-response")
def filter_response(
    input: str = typer.Option(..., "--input", "-i", help="JSON file with {b: [...], a: [...], sample_rate: Hz}"),
    output: str = typer.Option("filter_response.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Filter Response", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg"),
    freq_min: float = typer.Option(0.0, "--freq-min", help="Minimum frequency [Hz]"),
    freq_max: float = typer.Option(None, "--freq-max", help="Maximum frequency [Hz]"),
):
    """Generate frequency response analysis for digital filters."""
    input_path = Path(input)
    output_path = Path(output)
    
    try:
        if VALIDATION_AVAILABLE:
            data = validate_json_file(input_path, "filter data")
        else:
            data = json.loads(input_path.read_text())
        
        filter_coeffs = {
            'b': data.get('b', [1.0]),
            'a': data.get('a', [1.0])
        }
        sample_rate = data.get('sample_rate', 1.0)
        
        freq_range = None
        if freq_max is not None:
            freq_range = (freq_min, freq_max)
        
    except ValidationError as e:
        typer.echo(f"[ERROR] {create_validation_error_message(e)}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"[ERROR] Failed to load input data: {e}", err=True)
        raise typer.Exit(1)
    
    success = generate_filter_response(filter_coeffs, sample_rate, output_path, title,
                                      format, freq_range)
    if success:
        typer.echo(f"Generated: {output_path}")


@app.command("3d-surface")
def surface_3d(
    function: str = typer.Option(..., "--function", "-f", help="Z function: sin(x) * cos(y)"),
    x_min: float = typer.Option(-5.0, "--x-min", help="X minimum"),
    x_max: float = typer.Option(5.0, "--x-max", help="X maximum"),
    y_min: float = typer.Option(-5.0, "--y-min", help="Y minimum"),
    y_max: float = typer.Option(5.0, "--y-max", help="Y maximum"),
    output: str = typer.Option("surface_3d.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("3D Surface", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg"),
    resolution: int = typer.Option(50, "--resolution", "-r", help="Grid resolution"),
    colormap: str = typer.Option("viridis", "--colormap", "-c", help="Colormap name"),
    elev: float = typer.Option(30.0, "--elev", help="Elevation angle"),
    azim: float = typer.Option(45.0, "--azim", help="Azimuth angle"),
):
    """Generate 3D surface plot for multivariate mathematical functions."""
    output_path = Path(output)
    
    success = generate_3d_surface(
        (x_min, x_max), (y_min, y_max), function, output_path, title, format,
        resolution, colormap, (elev, azim)
    )
    if success:
        typer.echo(f"Generated: {output_path}")


@app.command("3d-contour")
def contour_3d(
    function: str = typer.Option(..., "--function", "-f", help="Z function: sin(x) * cos(y)"),
    x_min: float = typer.Option(-5.0, "--x-min", help="X minimum"),
    x_max: float = typer.Option(5.0, "--x-max", help="X maximum"),
    y_min: float = typer.Option(-5.0, "--y-min", help="Y minimum"),
    y_max: float = typer.Option(5.0, "--y-max", help="Y maximum"),
    output: str = typer.Option("contour_3d.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("3D Contour", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg"),
    resolution: int = typer.Option(50, "--resolution", "-r", help="Grid resolution"),
    levels: int = typer.Option(20, "--levels", "-l", help="Number of contour levels"),
    colormap: str = typer.Option("viridis", "--colormap", "-c", help="Colormap name"),
):
    """Generate 3D contour plot for multivariate mathematical functions."""
    output_path = Path(output)
    
    success = generate_3d_contour(
        (x_min, x_max), (y_min, y_max), function, output_path, title, format,
        resolution, levels, colormap
    )
    if success:
        typer.echo(f"Generated: {output_path}")


@app.command("complex-plane")
def complex_plane(
    input: str = typer.Option(..., "--input", "-i", help="JSON file with complex numbers as [[real, imag], ...] or strings"),
    output: str = typer.Option("complex_plane.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Complex Plane", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg"),
    unit_circle: bool = typer.Option(True, "--unit-circle/--no-unit-circle", help="Show unit circle"),
    color_by_magnitude: bool = typer.Option(True, "--color-magnitude/--no-color-magnitude", help="Color by magnitude"),
):
    """Generate Argand diagram (complex plane visualization)."""
    input_path = Path(input)
    output_path = Path(output)

    if not input_path.exists():
        typer.echo(f"[ERROR] Input file not found: {input_path}", err=True)
        raise typer.Exit(1)

    try:
        data = json.loads(input_path.read_text())
    except json.JSONDecodeError as e:
        typer.echo(f"[ERROR] Invalid JSON format: {e}", err=True)
        raise typer.Exit(1)
    
    # Convert to complex numbers - support multiple formats
    complex_numbers = []
    try:
        for item in data:
            if isinstance(item, list) and len(item) == 2:
                # Format: [real, imag]
                complex_numbers.append(complex(item[0], item[1]))
            elif isinstance(item, (int, float)):
                # Format: real number
                complex_numbers.append(complex(item, 0))
            elif isinstance(item, str):
                # Format: "a+bj" or "a-bj"
                complex_numbers.append(complex(item))
            else:
                raise ValueError(f"Unsupported complex number format: {item}")
    except (ValueError, TypeError) as e:
        typer.echo(f"[ERROR] Invalid complex number format: {e}", err=True)
        typer.echo("[INFO] Supported formats: [[real, imag], ...], [real, ...], or ['a+bj', ...]")
        raise typer.Exit(1)

    success = generate_complex_plane(complex_numbers, output_path, title, format, unit_circle, color_by_magnitude)
    if success:
        typer.echo(f"Generated: {output_path}")


@app.command()
def polar(
    input: str = typer.Option(..., "--input", "-i", help="JSON file with {angle: radius} or [[theta, r], ...]"),
    output: str = typer.Option("polar.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Polar Plot", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg"),
):
    """Generate polar plot for directional data (antenna patterns, wind roses)."""
    input_path = Path(input)
    output_path = Path(output)

    if not input_path.exists():
        typer.echo(f"[ERROR] Input file not found: {input_path}", err=True)
        raise typer.Exit(1)

    data = json.loads(input_path.read_text())

    # Convert dict to list format if needed
    if isinstance(data, dict):
        theta = list(data.keys())
        r = list(data.values())
    else:
        theta = [item[0] for item in data]
        r = [item[1] for item in data]

    success = generate_polar_plot(theta, r, output_path, title, format)
    if success:
        typer.echo(f"Generated: {output_path}")


@app.command()
def contour(
    input: str = typer.Option(..., "--input", "-i", help="JSON file with {x: [], y: [], z: [[]]}"),
    output: str = typer.Option("contour.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Contour Plot", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg"),
    cmap: str = typer.Option("viridis", "--cmap", "-c", help="Colormap: viridis, plasma, Blues"),
    filled: bool = typer.Option(True, "--filled/--lines", help="Filled contours or just lines"),
    levels: int = typer.Option(20, "--levels", "-l", help="Number of contour levels"),
):
    """Generate contour plot for field distributions (flux, temp, stress)."""
    input_path = Path(input)
    output_path = Path(output)

    if not input_path.exists():
        typer.echo(f"[ERROR] Input file not found: {input_path}", err=True)
        raise typer.Exit(1)

    data = json.loads(input_path.read_text())
    x = data.get("x", [])
    y = data.get("y", [])
    z = data.get("z", [[]])

    success = generate_contour_plot(x, y, z, output_path, title, format, levels, cmap, filled)
    if success:
        typer.echo(f"Generated: {output_path}")


@app.command()
def gantt(
    input: str = typer.Option(..., "--input", "-i", help="JSON file with [{task, start, end, progress}]"),
    output: str = typer.Option("gantt.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Gantt Chart", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg"),
):
    """Generate Gantt chart for project scheduling and milestones."""
    input_path = Path(input)
    output_path = Path(output)

    if not input_path.exists():
        typer.echo(f"[ERROR] Input file not found: {input_path}", err=True)
        raise typer.Exit(1)

    tasks = json.loads(input_path.read_text())

    success = generate_gantt_chart(tasks, output_path, title, format)
    if success:
        typer.echo(f"Generated: {output_path}")


@app.command()
def pert(
    input: str = typer.Option(..., "--input", "-i", help="JSON file with {nodes: [...], edges: [{from, to, duration}]}"),
    output: str = typer.Option("pert.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("PERT Network", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg"),
):
    """Generate PERT network diagram for critical path analysis."""
    input_path = Path(input)
    output_path = Path(output)

    if not input_path.exists():
        typer.echo(f"[ERROR] Input file not found: {input_path}", err=True)
        raise typer.Exit(1)

    data = json.loads(input_path.read_text())
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])

    success = generate_pert_network(nodes, edges, output_path, title, format)
    if success:
        typer.echo(f"Generated: {output_path}")


@app.command("vector-field")
def vector_field(
    input: str = typer.Option(..., "--input", "-i", help="JSON file with {x: [], y: [], u: [[]], v: [[]]}"),
    output: str = typer.Option("vector_field.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Vector Field", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg"),
    streamlines: bool = typer.Option(False, "--streamlines/--quiver", help="Use streamlines instead of arrows"),
):
    """Generate vector field for flow visualization (velocity, gradients)."""
    input_path = Path(input)
    output_path = Path(output)

    if not input_path.exists():
        typer.echo(f"[ERROR] Input file not found: {input_path}", err=True)
        raise typer.Exit(1)

    data = json.loads(input_path.read_text())
    x = data.get("x", [])
    y = data.get("y", [])
    u = data.get("u", [[]])
    v = data.get("v", [[]])

    success = generate_vector_field(x, y, u, v, output_path, title, format, streamlines)
    if success:
        typer.echo(f"Generated: {output_path}")


@app.command("phase-portrait")
def phase_portrait(
    equations: str = typer.Option(..., "--equations", "-e", help="Differential equations: 'dx = y; dy = -x - 0.5*y'"),
    output: str = typer.Option("phase.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Phase Portrait", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg"),
    x_min: float = typer.Option(-5.0, "--x-min", help="X axis minimum"),
    x_max: float = typer.Option(5.0, "--x-max", help="X axis maximum"),
    y_min: float = typer.Option(-5.0, "--y-min", help="Y axis minimum"),
    y_max: float = typer.Option(5.0, "--y-max", help="Y axis maximum"),
    grid: int = typer.Option(20, "--grid", "-g", help="Grid resolution"),
):
    """Generate phase portrait for dynamical systems (differential equations)."""
    output_path = Path(output)

    success = generate_phase_portrait(
        (x_min, x_max),
        (y_min, y_max),
        equations,
        output_path,
        title,
        format,
        grid,
    )
    if success:
        typer.echo(f"Generated: {output_path}")


# --- GPU/Hardware and LLM CLI Commands ---

@app.command()
def roofline(
    input: str = typer.Option(..., "--input", "-i", help="JSON file with peak_flops, peak_bandwidth, kernels"),
    output: str = typer.Option("roofline.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Roofline Plot", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg"),
):
    """Generate roofline plot for GPU/hardware performance analysis."""
    input_path = Path(input)
    output_path = Path(output)

    if not input_path.exists():
        typer.echo(f"[ERROR] Input file not found: {input_path}", err=True)
        raise typer.Exit(1)

    data = json.loads(input_path.read_text())
    peak_flops = data.get('peak_flops', 19.5e12)  # V100 default
    peak_bandwidth = data.get('peak_bandwidth', 900e9)  # V100 default
    kernels = data.get('kernels', [])

    success = generate_roofline_plot(peak_flops, peak_bandwidth, kernels, output_path, title, format)
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
):
    """Generate scaling law plot (log-log) common in LLM research."""
    input_path = Path(input)
    output_path = Path(output)

    try:
        if VALIDATION_AVAILABLE:
            data = validate_json_file(input_path, "scaling law data")
            data = validate_scaling_data(data)
        else:
            data = json.loads(input_path.read_text())
    except ValidationError as e:
        typer.echo(f"[ERROR] {create_validation_error_message(e)}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"[ERROR] Failed to load input data: {e}", err=True)
        raise typer.Exit(1)

    success = generate_scaling_law_plot(data, output_path, x_label, y_label, title, format, fit)
    if success:
        typer.echo(f"Generated: {output_path}")


@app.command("confusion-matrix")
def confusion_matrix(
    input: str = typer.Option(..., "--input", "-i", help="JSON file with matrix and labels"),
    output: str = typer.Option("confusion.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Confusion Matrix", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg"),
    normalize: bool = typer.Option(False, "--normalize/--raw", help="Normalize to percentages"),
    cmap: str = typer.Option("Blues", "--cmap", "-c", help="Colormap"),
):
    """Generate confusion matrix for classification results."""
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
):
    """Generate ROC curve for binary classification."""
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
):
    """Generate training curves for multiple runs."""
    input_path = Path(input)
    output_path = Path(output)

    if not input_path.exists():
        typer.echo(f"[ERROR] Input file not found: {input_path}", err=True)
        raise typer.Exit(1)

    runs = json.loads(input_path.read_text())

    success = generate_training_curves(runs, output_path, x_label, y_label, title, format, log_y)
    if success:
        typer.echo(f"Generated: {output_path}")


@app.command("embedding-scatter")
def embedding_scatter(
    input: str = typer.Option(..., "--input", "-i", help="JSON file with [{vector, label}]"),
    output: str = typer.Option("embeddings.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Embedding Space", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg"),
    method: str = typer.Option("tsne", "--method", "-m", help="Reduction method: tsne, umap"),
    perplexity: int = typer.Option(30, "--perplexity", "-p", help="t-SNE perplexity"),
):
    """Generate t-SNE or UMAP scatter plot of embeddings."""
    input_path = Path(input)
    output_path = Path(output)

    if not input_path.exists():
        typer.echo(f"[ERROR] Input file not found: {input_path}", err=True)
        raise typer.Exit(1)

    embeddings = json.loads(input_path.read_text())

    success = generate_embedding_scatter(embeddings, output_path, title, format, method, perplexity)
    if success:
        typer.echo(f"Generated: {output_path}")


@app.command("attention-heatmap")
def attention_heatmap(
    input: str = typer.Option(..., "--input", "-i", help="JSON file with attention_weights and tokens"),
    output: str = typer.Option("attention.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Attention Weights", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg"),
    cmap: str = typer.Option("Blues", "--cmap", "-c", help="Colormap"),
):
    """Generate attention heatmap for transformer models."""
    input_path = Path(input)
    output_path = Path(output)

    if not input_path.exists():
        typer.echo(f"[ERROR] Input file not found: {input_path}", err=True)
        raise typer.Exit(1)

    data = json.loads(input_path.read_text())
    weights = data.get('attention_weights', [[]])
    tokens = data.get('tokens', [])

    success = generate_attention_heatmap(weights, tokens, output_path, title, format, cmap)
    if success:
        typer.echo(f"Generated: {output_path}")


@app.command("throughput-latency")
def throughput_latency(
    input: str = typer.Option(..., "--input", "-i", help="JSON file with [{name, throughput, latency}]"),
    output: str = typer.Option("throughput.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Throughput vs Latency", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg"),
):
    """Generate throughput vs latency plot for GPU/inference benchmarks."""
    input_path = Path(input)
    output_path = Path(output)

    if not input_path.exists():
        typer.echo(f"[ERROR] Input file not found: {input_path}", err=True)
        raise typer.Exit(1)

    data = json.loads(input_path.read_text())

    success = generate_throughput_latency(data, output_path, title, format)
    if success:
        typer.echo(f"Generated: {output_path}")


# --- ML Classification and Biology CLI Commands ---

@app.command("pr-curve")
def pr_curve(
    input: str = typer.Option(..., "--input", "-i", help="JSON file with {name: {precision, recall, ap}}"),
    output: str = typer.Option("pr.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Precision-Recall Curve", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg"),
):
    """Generate Precision-Recall curve for classification."""
    input_path = Path(input)
    output_path = Path(output)

    if not input_path.exists():
        typer.echo(f"[ERROR] Input file not found: {input_path}", err=True)
        raise typer.Exit(1)

    curves = json.loads(input_path.read_text())

    success = generate_precision_recall(curves, output_path, title, format)
    if success:
        typer.echo(f"Generated: {output_path}")


@app.command()
def violin(
    input: str = typer.Option(..., "--input", "-i", help="JSON file with {group: [values]}"),
    output: str = typer.Option("violin.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Violin Plot", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg"),
    y_label: str = typer.Option("Value", "--y-label", help="Y-axis label"),
):
    """Generate violin plot for distribution comparison."""
    input_path = Path(input)
    output_path = Path(output)

    if not input_path.exists():
        typer.echo(f"[ERROR] Input file not found: {input_path}", err=True)
        raise typer.Exit(1)

    data = json.loads(input_path.read_text())

    success = generate_violin_plot(data, output_path, title, format, "", y_label)
    if success:
        typer.echo(f"Generated: {output_path}")


@app.command()
def volcano(
    input: str = typer.Option(..., "--input", "-i", help="JSON file with [{gene, log2fc, pvalue}]"),
    output: str = typer.Option("volcano.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Volcano Plot", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg"),
    fc: float = typer.Option(1.0, "--fc", help="Log2 fold change threshold"),
    pval: float = typer.Option(0.05, "--pval", help="P-value threshold"),
):
    """Generate volcano plot for differential expression analysis."""
    input_path = Path(input)
    output_path = Path(output)

    if not input_path.exists():
        typer.echo(f"[ERROR] Input file not found: {input_path}", err=True)
        raise typer.Exit(1)

    data = json.loads(input_path.read_text())

    success = generate_volcano_plot(data, output_path, title, format, fc, pval)
    if success:
        typer.echo(f"Generated: {output_path}")


@app.command("survival-curve")
def survival_curve(
    input: str = typer.Option(..., "--input", "-i", help="JSON file with {group: {time, survival}}"),
    output: str = typer.Option("survival.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Kaplan-Meier Survival Curve", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg"),
):
    """Generate Kaplan-Meier survival curve."""
    input_path = Path(input)
    output_path = Path(output)

    if not input_path.exists():
        typer.echo(f"[ERROR] Input file not found: {input_path}", err=True)
        raise typer.Exit(1)

    curves = json.loads(input_path.read_text())

    success = generate_survival_curve(curves, output_path, title, format)
    if success:
        typer.echo(f"Generated: {output_path}")


@app.command()
def manhattan(
    input: str = typer.Option(..., "--input", "-i", help="JSON file with [{chr, pos, pvalue}]"),
    output: str = typer.Option("manhattan.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Manhattan Plot", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg"),
):
    """Generate Manhattan plot for GWAS results."""
    input_path = Path(input)
    output_path = Path(output)

    if not input_path.exists():
        typer.echo(f"[ERROR] Input file not found: {input_path}", err=True)
        raise typer.Exit(1)

    data = json.loads(input_path.read_text())

    success = generate_manhattan_plot(data, output_path, title, format)
    if success:
        typer.echo(f"Generated: {output_path}")


@app.command("feature-importance")
def feature_importance(
    input: str = typer.Option(..., "--input", "-i", help="JSON file with {feature: importance}"),
    output: str = typer.Option("importance.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Feature Importance", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg"),
    top_n: int = typer.Option(20, "--top-n", "-n", help="Show top N features"),
):
    """Generate feature importance bar chart."""
    input_path = Path(input)
    output_path = Path(output)

    if not input_path.exists():
        typer.echo(f"[ERROR] Input file not found: {input_path}", err=True)
        raise typer.Exit(1)

    data = json.loads(input_path.read_text())

    success = generate_feature_importance(data, output_path, title, format, top_n)
    if success:
        typer.echo(f"Generated: {output_path}")


@app.command()
def calibration(
    input: str = typer.Option(..., "--input", "-i", help="JSON file with {model: {predicted_probs, true_fractions}}"),
    output: str = typer.Option("calibration.pdf", "--output", "-o", help="Output file"),
    title: str = typer.Option("Calibration Plot", "--title", "-t", help="Chart title"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf, png, svg"),
):
    """Generate calibration plot (reliability diagram) for classification."""
    input_path = Path(input)
    output_path = Path(output)

    if not input_path.exists():
        typer.echo(f"[ERROR] Input file not found: {input_path}", err=True)
        raise typer.Exit(1)

    data = json.loads(input_path.read_text())

    success = generate_calibration_plot(data, output_path, title, format)
    if success:
        typer.echo(f"Generated: {output_path}")


@app.command("from-assess")
def from_assess(
    input: str = typer.Option(..., "--input", "-i", help="Input JSON from /assess"),
    output_dir: str = typer.Option("./figures", "--output-dir", "-o", help="Output directory"),
    backend: str = typer.Option("graphviz", "--backend", "-b", help="Diagram backend: graphviz, mermaid"),
):
    """Generate all figures from /assess output."""
    input_path = Path(input)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        typer.echo(f"[ERROR] Input file not found: {input_path}", err=True)
        raise typer.Exit(1)

    data = json.loads(input_path.read_text())
    typer.echo(f"Generating figures from assess output...")

    generated = []

    # 1. Architecture diagram
    components = data.get("components", [])
    if components:
        arch_path = output_path / "architecture.pdf"
        if generate_architecture_diagram(
            data.get("project_name", "Project"), components, arch_path, "pdf", backend
        ):
            typer.echo(f"  Generated: {arch_path}")
            generated.append(str(arch_path))

    # 2. Dependency graph (if project_path available)
    project_path = data.get("project_path")
    if project_path and Path(project_path).exists():
        deps_path = output_path / "dependencies.pdf"
        if generate_dependency_graph(Path(project_path), deps_path, "pdf", 2, backend):
            typer.echo(f"  Generated: {deps_path}")
            generated.append(str(deps_path))

    # 3. Feature metrics chart
    features = data.get("categories", {}).get("working_well", [])
    if features:
        metrics_data = {
            f.get("feature", f"f{i}")[:20]: f.get("loc", 1)
            for i, f in enumerate(features[:10])
        }
        metrics_path = output_path / "features.pdf"
        if generate_metrics_chart("Feature Distribution", metrics_data, metrics_path, "bar"):
            typer.echo(f"  Generated: {metrics_path}")
            generated.append(str(metrics_path))

    # 4. Issues chart
    issues = data.get("categories", {}).get("brittle", [])
    if issues:
        issue_counts = {}
        for issue in issues:
            severity = issue.get("severity", "unknown")
            issue_counts[severity] = issue_counts.get(severity, 0) + 1
        if issue_counts:
            issues_path = output_path / "issues.pdf"
            if generate_metrics_chart("Issue Severity", issue_counts, issues_path, "pie"):
                typer.echo(f"  Generated: {issues_path}")
                generated.append(str(issues_path))

    # 5. Feature comparison table
    if features:
        headers = ["Feature", "Status", "Notes"]
        rows = [
            [f.get("feature", ""), "Implemented", f.get("note", "")[:50]]
            for f in features[:10]
        ]
        table_path = output_path / "comparison.tex"
        if generate_latex_table("Features", headers, rows, table_path, "Feature Comparison"):
            typer.echo(f"  Generated: {table_path}")
            generated.append(str(table_path))

    # 6. Test coverage table
    test_coverage = data.get("test_coverage", [])
    if test_coverage:
        headers = ["Feature", "Test File", "Status"]
        rows = [
            [t.get("feature", ""), t.get("test_file", "MISSING"), t.get("status", "")]
            for t in test_coverage[:15]
        ]
        test_table_path = output_path / "test_coverage.tex"
        if generate_latex_table("Test Coverage", headers, rows, test_table_path, "Test Coverage"):
            typer.echo(f"  Generated: {test_table_path}")
            generated.append(str(test_table_path))

    typer.echo(f"\nAll figures saved to: {output_path}")
    typer.echo(f"Generated {len(generated)} figures")


@app.command()
def check():
    """Check available backends and dependencies."""
    typer.echo("Checking fixture-graph backends...")
    typer.echo("")

    checks = [
        ("Graphviz (dot)", _check_graphviz()),
        ("Mermaid (mmdc)", _check_mermaid()),
        ("matplotlib", _check_matplotlib()),
        ("seaborn", _check_seaborn()),
        ("plotly", _check_plotly()),
        ("NetworkX", _check_networkx()),
        ("pandas", _check_pandas()),
        ("squarify", _check_squarify()),
        ("scipy", _check_scipy()),
        ("python-control", _check_control()),
        ("pydeps", _check_pydeps()),
        ("pyreverse", _check_pyreverse()),
        ("lean4-prove", LEAN4_PROVE_SCRIPT.exists()),
    ]

    typer.echo("\nCapabilities:")
    capabilities = [
        ("Bar/line/pie charts", _check_matplotlib()),
        ("Heatmaps", _check_seaborn() or _check_matplotlib()),
        ("Sankey diagrams", _check_plotly() or _check_matplotlib()),
        ("Treemaps", _check_plotly() or _check_squarify()),
        ("Sunburst charts", _check_plotly()),
        ("Force-directed graphs", _check_networkx()),
        ("Parallel coordinates", _check_pandas()),
        ("Dependency graphs", _check_graphviz() or _check_mermaid()),
        ("UML diagrams", _check_pyreverse()),
        ("Formal proofs", LEAN4_PROVE_SCRIPT.exists()),
        ("Bode/Nyquist/Root locus", _check_control() or _check_scipy()),
        ("Contour/Vector fields", _check_matplotlib()),
        ("Gantt/PERT charts", _check_matplotlib()),
        ("Phase portraits", _check_matplotlib()),
        ("Radar charts", _check_matplotlib()),
        ("Polar plots", _check_matplotlib()),
        # GPU/Hardware & LLM
        ("Roofline plots", _check_matplotlib()),
        ("Scaling law plots", _check_matplotlib()),
        ("Confusion matrices", _check_matplotlib()),
        ("ROC curves", _check_matplotlib()),
        ("Training curves", _check_matplotlib()),
        ("Attention heatmaps", _check_matplotlib()),
        ("Embedding scatter (t-SNE)", _check_matplotlib()),  # sklearn optional
        ("Throughput/Latency", _check_matplotlib()),
        # ML Classification
        ("Precision-Recall curves", _check_matplotlib()),
        ("Feature importance", _check_matplotlib()),
        ("Calibration plots", _check_matplotlib()),
        # Biology
        ("Violin plots", _check_matplotlib()),
        ("Volcano plots", _check_matplotlib()),
        ("Survival curves", _check_matplotlib()),
        ("Manhattan plots", _check_matplotlib()),
    ]

    for name, available in capabilities:
        status = "[OK]" if available else "[NOT AVAILABLE]"
        typer.echo(f"  {name}: {status}")

    for name, available in checks:
        status = "[OK]" if available else "[NOT AVAILABLE]"
        typer.echo(f"  {name}: {status}")

    typer.echo("")
    available_count = sum(1 for _, a in checks if a)
    typer.echo(f"{available_count}/{len(checks)} backends available")


# =============================================================================
# DOMAIN NAVIGATION COMMANDS - Help agents find the right visualization
# =============================================================================

@app.command()
def domains():
    """
    List available visualization domains.

    Use this to find which domain matches your project type,
    then use `list --domain <name>` to see available commands.

    Example:
        fixture-graph domains
        fixture-graph list --domain ml
    """
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
def presets():
    """
    Show IEEE figure size presets and colorblind-safe colormaps.

    Use these to ensure publication-quality, accessible figures.

    Example:
        fixture-graph presets
    """
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

    typer.echo("")
    typer.echo("Usage in commands:")
    typer.echo("  --colormap viridis    # Colorblind-safe")
    typer.echo("  --figsize single      # IEEE single column")


@app.command("list")
def list_commands(
    domain: str = typer.Option("", "--domain", "-d", help="Filter by domain (core, control, field, project, math, ml, bio, hierarchy)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full command descriptions"),
):
    """
    List available commands, optionally filtered by domain.

    Domains: core, control, field, project, math, ml, bio, hierarchy

    Examples:
        fixture-graph list                    # All commands
        fixture-graph list --domain ml        # ML/LLM commands only
        fixture-graph list --domain control   # Control systems only
    """
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
    data_type: str = typer.Option("", "--data-type", "-t", help="Type of data (time_series, classification, flow, hierarchy, etc.)"),
    show_types: bool = typer.Option(False, "--show-types", "-s", help="Show all supported data types"),
):
    """
    Recommend visualization commands based on data type.

    Helps project agents quickly find the right visualization
    without browsing all 50+ commands.

    Examples:
        fixture-graph recommend --show-types
        fixture-graph recommend --data-type classification
        fixture-graph recommend --data-type flow
    """
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
        # Find which domain this command belongs to
        domain = "core"
        for d_name, d_info in DOMAIN_GROUPS.items():
            if cmd in d_info["commands"]:
                domain = d_name
                break
        typer.echo(f"  {i}. {cmd} (domain: {domain})")

    typer.echo("")
    typer.echo(f"Run: fixture-graph {commands[0]} --help  # for usage")


# Need numpy for color mapping
try:
    import numpy as np
except ImportError:
    # Fallback for when numpy isn't available
    class np:
        @staticmethod
        def linspace(start, stop, num):
            step = (stop - start) / (num - 1) if num > 1 else 0
            return [start + i * step for i in range(num)]


def generate_3d_surface(
    x_range: Tuple[float, float],
    y_range: Tuple[float, float],
    z_function: str,
    output_path: Path,
    title: str = "3D Surface",
    format: str = "pdf",
    resolution: int = 50,
    colormap: str = "viridis",
    view_angle: Tuple[float, float] = (30, 45),
) -> bool:
    """
    Generate 3D surface plot for multivariate mathematical functions.

    Args:
        x_range: (x_min, x_max) for x-axis
        y_range: (y_min, y_max) for y-axis
        z_function: String expression for z = f(x,y) (e.g., "sin(x) * cos(y)")
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)
        resolution: Grid resolution (number of points per axis)
        colormap: Matplotlib colormap name
        view_angle: (elevation, azimuth) in degrees

    Returns:
        True if successful, False otherwise
    """
    if not _check_matplotlib():
        typer.echo("[ERROR] matplotlib required for 3D surface plot\n\nInstall: pip install matplotlib", err=True)
        return False

    try:
        import matplotlib.pyplot as plt
    except ImportError as e:
        typer.echo(f"[ERROR] Failed to import matplotlib: {e}\n\nInstall: pip install --upgrade matplotlib", err=True)
        return False

    try:
        from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
    except (ImportError, ModuleNotFoundError) as e:
        typer.echo(f"[ERROR] 3D plotting unavailable (matplotlib version conflict): {e}\n\nFix: pip uninstall matplotlib && pip install matplotlib", err=True)
        return False

    _apply_ieee_style()

    try:
        # Validate inputs
        if resolution <= 0:
            typer.echo("[ERROR] resolution must be positive\n\nExample: resolution=50", err=True)
            return False
        if x_range[0] >= x_range[1] or y_range[0] >= y_range[1]:
            typer.echo("[ERROR] x_range/y_range must be (min, max) with min < max\n\nExample: x_range=(-2, 2)", err=True)
            return False

        # Create grid
        x = np.linspace(x_range[0], x_range[1], resolution)
        y = np.linspace(y_range[0], y_range[1], resolution)
        X, Y = np.meshgrid(x, y)

        # Evaluate function safely with whitelist
        safe_dict = {"x": X, "y": Y, "np": np, "sin": np.sin, "cos": np.cos,
                    "exp": np.exp, "sqrt": np.sqrt, "abs": np.abs, "log": np.log,
                    "tan": np.tan, "arctan": np.arctan, "pi": np.pi}
        try:
            Z = eval(z_function, {"__builtins__": {}}, safe_dict)
        except Exception as e:
            typer.echo(f"[ERROR] Invalid z_function '{z_function}': {e}\n\nExamples: 'sin(x) * cos(y)', 'exp(-(x**2 + y**2))'", err=True)
            return False
        
        fig = plt.figure(figsize=(IEEE_DOUBLE_COLUMN, IEEE_SINGLE_COLUMN * 1.2))
        ax = fig.add_subplot(111, projection='3d')
        
        # Create surface plot
        surf = ax.plot_surface(X, Y, Z, cmap=colormap, alpha=0.8,
                              linewidth=0, antialiased=True)
        
        # Add colorbar
        fig.colorbar(surf, shrink=0.5, aspect=5)
        
        ax.set_xlabel('X')
        ax.set_ylabel('Y')
        ax.set_zlabel('Z')
        ax.set_title(title, fontweight="bold")
        
        # Set viewing angle
        ax.view_init(elev=view_angle[0], azim=view_angle[1])
        
        plt.tight_layout()
        plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
        plt.close()
        return True
        
    except Exception as e:
        typer.echo(f"[ERROR] 3D surface computation failed: {e}", err=True)
        return False


def generate_3d_contour(
    x_range: Tuple[float, float],
    y_range: Tuple[float, float],
    z_function: str,
    output_path: Path,
    title: str = "3D Contour",
    format: str = "pdf",
    resolution: int = 50,
    levels: int = 20,
    colormap: str = "viridis",
) -> bool:
    """
    Generate 3D contour plot for multivariate mathematical functions.

    Args:
        x_range: (x_min, x_max) for x-axis
        y_range: (y_min, y_max) for y-axis
        z_function: String expression for z = f(x,y) (e.g., "sin(x) * cos(y)")
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)
        resolution: Grid resolution (number of points per axis)
        levels: Number of contour levels
        colormap: Matplotlib colormap name

    Returns:
        True if successful, False otherwise
    """
    if not _check_matplotlib():
        typer.echo("[ERROR] matplotlib required for 3D contour plot\n\nInstall: pip install matplotlib", err=True)
        return False

    try:
        import matplotlib.pyplot as plt
    except ImportError as e:
        typer.echo(f"[ERROR] Failed to import matplotlib: {e}\n\nInstall: pip install --upgrade matplotlib", err=True)
        return False

    try:
        from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
    except (ImportError, ModuleNotFoundError) as e:
        typer.echo(f"[ERROR] 3D plotting unavailable (matplotlib version conflict): {e}\n\nFix: pip uninstall matplotlib && pip install matplotlib", err=True)
        return False

    _apply_ieee_style()

    try:
        # Validate inputs
        if resolution <= 0:
            typer.echo("[ERROR] resolution must be positive\n\nExample: resolution=50", err=True)
            return False
        if x_range[0] >= x_range[1] or y_range[0] >= y_range[1]:
            typer.echo("[ERROR] x_range/y_range must be (min, max) with min < max\n\nExample: x_range=(-2, 2)", err=True)
            return False

        # Create grid
        x = np.linspace(x_range[0], x_range[1], resolution)
        y = np.linspace(y_range[0], y_range[1], resolution)
        X, Y = np.meshgrid(x, y)

        # Evaluate function safely with whitelist
        safe_dict = {"x": X, "y": Y, "np": np, "sin": np.sin, "cos": np.cos,
                    "exp": np.exp, "sqrt": np.sqrt, "abs": np.abs, "log": np.log,
                    "tan": np.tan, "arctan": np.arctan, "pi": np.pi}
        try:
            Z = eval(z_function, {"__builtins__": {}}, safe_dict)
        except Exception as e:
            typer.echo(f"[ERROR] Invalid z_function '{z_function}': {e}\n\nExamples: 'x**2 - y**2', 'sin(x) * sin(y)'", err=True)
            return False

        fig = plt.figure(figsize=(IEEE_DOUBLE_COLUMN, IEEE_SINGLE_COLUMN * 1.2))
        ax = fig.add_subplot(111, projection='3d')

        # Create 3D contour plot
        contour = ax.contour3D(X, Y, Z, levels=levels, cmap=colormap)
        
        # Add colorbar
        fig.colorbar(contour, shrink=0.5, aspect=5)
        
        ax.set_xlabel('X')
        ax.set_ylabel('Y')
        ax.set_zlabel('Z')
        ax.set_title(title, fontweight="bold")
        
        plt.tight_layout()
        plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
        plt.close()
        return True
        
    except Exception as e:
        typer.echo(f"[ERROR] 3D contour computation failed: {e}", err=True)
        return False


def generate_complex_plane(
    complex_numbers: List[complex],
    output_path: Path,
    title: str = "Complex Plane",
    format: str = "pdf",
    show_unit_circle: bool = True,
    color_by_magnitude: bool = True,
) -> bool:
    """
    Generate Argand diagram (complex plane visualization).

    Args:
        complex_numbers: List of complex numbers to plot
        output_path: Output file path
        title: Chart title
        format: Output format (pdf, png, svg)
        show_unit_circle: Show unit circle for reference
        color_by_magnitude: Color points by magnitude

    Returns:
        True if successful, False otherwise
    """
    if not _check_matplotlib():
        typer.echo("[ERROR] matplotlib required for complex plane visualization", err=True)
        return False

    import matplotlib.pyplot as plt
    _apply_ieee_style()

    try:
        fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN))
        
        if not complex_numbers:
            typer.echo("[WARN] No complex numbers provided for visualization", err=True)
            return False
        
        # Extract real and imaginary parts
        real_parts = [z.real for z in complex_numbers]
        imag_parts = [z.imag for z in complex_numbers]
        
        # Color by magnitude if requested
        if color_by_magnitude:
            magnitudes = [abs(z) for z in complex_numbers]
            scatter = ax.scatter(real_parts, imag_parts, c=magnitudes,
                               cmap='viridis', s=50, alpha=0.7)
            cbar = plt.colorbar(scatter, ax=ax, shrink=0.8)
            cbar.set_label('Magnitude', rotation=-90, va="bottom")
        else:
            ax.scatter(real_parts, imag_parts, s=50, alpha=0.7, color='blue')
        
        # Add unit circle if requested
        if show_unit_circle:
            theta = np.linspace(0, 2*np.pi, 100)
            unit_circle_x = np.cos(theta)
            unit_circle_y = np.sin(theta)
            ax.plot(unit_circle_x, unit_circle_y, 'k--', alpha=0.5,
                   label='Unit Circle')
            ax.legend(fontsize=7)
        
        # Add annotations for key points
        for i, (z, x, y) in enumerate(zip(complex_numbers, real_parts, imag_parts)):
            if i < 5:  # Limit annotations to avoid clutter
                ax.annotate(f'{z:.2f}', (x, y), xytext=(5, 5),
                           textcoords='offset points', fontsize=6,
                           bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.7))
        
        ax.set_xlabel('Real Part')
        ax.set_ylabel('Imaginary Part')
        ax.set_title(title, fontweight="bold")
        ax.grid(True, alpha=0.3)
        ax.set_aspect('equal')
        
        # Add quadrant labels
        ax.text(0.8, 0.8, 'I', transform=ax.transAxes, ha='center', va='center',
               fontsize=12, alpha=0.5)
        ax.text(0.2, 0.8, 'II', transform=ax.transAxes, ha='center', va='center',
               fontsize=12, alpha=0.5)
        ax.text(0.2, 0.2, 'III', transform=ax.transAxes, ha='center', va='center',
               fontsize=12, alpha=0.5)
        ax.text(0.8, 0.2, 'IV', transform=ax.transAxes, ha='center', va='center',
               fontsize=12, alpha=0.5)
        
        plt.tight_layout()
        plt.savefig(output_path, format=format, dpi=600, bbox_inches="tight")
        plt.close()
        return True
        
    except Exception as e:
        typer.echo(f"[ERROR] Complex plane visualization failed: {e}", err=True)
        return False


if __name__ == "__main__":
    app()
