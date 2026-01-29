#!/usr/bin/env python3
"""
Code analysis and architecture diagram generation for fixture-graph skill.

Handles:
- Architecture diagram generation
- Workflow diagram generation
- Lean4 theorem integration
- from-assess integration
"""

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List

import typer

from config import LEAN4_PROVE_SCRIPT
from graphviz_backend import generate_graphviz_architecture, generate_graphviz_workflow
from mermaid_backend import generate_mermaid_architecture, generate_mermaid_workflow
from matplotlib_backend import generate_metrics_chart, generate_latex_table
from graphviz_backend import generate_dependency_graph


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
        return generate_graphviz_architecture(project_name, components, output_path, format)
    else:
        return generate_mermaid_architecture(project_name, components, output_path, format)


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
        return generate_graphviz_workflow(stages, output_path, format, with_gates)
    else:
        return generate_mermaid_workflow(stages, output_path, format, with_gates)


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


def generate_from_assess(
    input_path: Path,
    output_dir: Path,
    backend: str = "graphviz",
) -> List[str]:
    """
    Generate all figures from /assess output.

    Args:
        input_path: Path to assess JSON output
        output_dir: Directory for generated figures
        backend: Diagram backend (graphviz, mermaid)

    Returns:
        List of generated file paths
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        typer.echo(f"[ERROR] Input file not found: {input_path}", err=True)
        return []

    data = json.loads(input_path.read_text())
    typer.echo(f"Generating figures from assess output...")

    generated = []

    # 1. Architecture diagram
    components = data.get("components", [])
    if components:
        arch_path = output_dir / "architecture.pdf"
        if generate_architecture_diagram(
            data.get("project_name", "Project"), components, arch_path, "pdf", backend
        ):
            typer.echo(f"  Generated: {arch_path}")
            generated.append(str(arch_path))

    # 2. Dependency graph (if project_path available)
    project_path = data.get("project_path")
    if project_path and Path(project_path).exists():
        deps_path = output_dir / "dependencies.pdf"
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
        metrics_path = output_dir / "features.pdf"
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
            issues_path = output_dir / "issues.pdf"
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
        table_path = output_dir / "comparison.tex"
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
        test_table_path = output_dir / "test_coverage.tex"
        if generate_latex_table("Test Coverage", headers, rows, test_table_path, "Test Coverage"):
            typer.echo(f"  Generated: {test_table_path}")
            generated.append(str(test_table_path))

    typer.echo(f"\nAll figures saved to: {output_dir}")
    typer.echo(f"Generated {len(generated)} figures")

    return generated
