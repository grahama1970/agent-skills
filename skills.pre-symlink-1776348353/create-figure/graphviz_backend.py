#!/usr/bin/env python3
"""
Graphviz backend for fixture-graph skill.

Handles DOT rendering and Graphviz-based visualizations:
- Dependency graphs
- Architecture diagrams
- UML class diagrams (via pyreverse)
- Workflow diagrams
"""

import ast
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import typer

from config import DependencyNode
from utils import check_graphviz, check_pydeps, check_pyreverse


def render_graphviz(dot_code: str, output_path: Path, format: str = "pdf") -> bool:
    """Render DOT code to file using Graphviz."""
    if not check_graphviz():
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
    if check_pydeps() and backend == "graphviz":
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
                return render_graphviz(dot_code, output_path, format)
        except subprocess.TimeoutExpired:
            typer.echo("[WARN] pydeps timed out, falling back to static analysis", err=True)

    # Fallback: Static analysis with AST
    return generate_dependency_graph_ast(project_path, output_path, format, backend)


def generate_dependency_graph_ast(
    project_path: Path,
    output_path: Path,
    format: str,
    backend: str,
) -> bool:
    """Generate dependency graph using AST analysis (fallback)."""
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
        from mermaid_backend import generate_mermaid_dep_graph
        return generate_mermaid_dep_graph(modules, output_path, format)
    elif backend == "networkx":
        from networkx_backend import generate_networkx_dep_graph
        return generate_networkx_dep_graph(modules, output_path, format)
    else:  # graphviz
        return generate_graphviz_dep_graph(modules, output_path, format)


def generate_graphviz_dep_graph(
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

    return render_graphviz(dot_code, output_path, format)


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
    if not check_pyreverse():
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
            return render_graphviz(dot_code, output_path, format)

        except subprocess.TimeoutExpired:
            typer.echo("[ERROR] pyreverse timed out", err=True)
            return False


def generate_graphviz_architecture(
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

    return render_graphviz(dot_code, output_path, format)


def generate_graphviz_workflow(
    stages: List[str],
    output_path: Path,
    format: str = "pdf",
    with_gates: bool = True,
) -> bool:
    """Generate workflow diagram using Graphviz."""
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
    return render_graphviz("\n".join(lines), output_path, format)
