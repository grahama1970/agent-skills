"""
Paper Writer Skill - Figures
Figure generation and management using fixture-graph skill.
"""
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List

import typer

from config import FIXTURE_GRAPH_SCRIPT, ProjectAnalysis
from loguru import logger


def generate_figures(
    project_path: Path,
    analysis: ProjectAnalysis,
    figures_dir: Path,
) -> List[str]:
    """Generate publication-quality figures using fixture-graph skill.

    Args:
        project_path: Path to the project
        analysis: Project analysis results
        figures_dir: Directory to save figures

    Returns:
        List of generated figure filenames
    """
    generated = []
    figures_dir.mkdir(parents=True, exist_ok=True)

    if not FIXTURE_GRAPH_SCRIPT.exists():
        logger.warning("fixture-graph skill not available, skipping figure generation")
        return generated

    typer.echo("Generating figures...")

    # 1. Architecture diagram
    generated.extend(_generate_architecture_diagram(project_path, figures_dir))

    # 2. Dependency graph
    generated.extend(_generate_dependency_graph(project_path, figures_dir))

    # 3. Workflow diagram
    generated.extend(_generate_workflow_diagram(figures_dir))

    # 4. Feature metrics chart
    if analysis.features:
        generated.extend(_generate_feature_metrics(analysis, figures_dir))

    typer.echo(f"  Total figures generated: {len(generated)}")
    return generated


def _generate_architecture_diagram(project_path: Path, figures_dir: Path) -> List[str]:
    """Generate architecture diagram.

    Args:
        project_path: Path to the project
        figures_dir: Directory to save figure

    Returns:
        List of generated filenames (0 or 1)
    """
    try:
        result = subprocess.run(
            [
                str(FIXTURE_GRAPH_SCRIPT), "architecture",
                "--project", str(project_path),
                "--output", str(figures_dir / "architecture.pdf"),
                "--backend", "graphviz",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            typer.echo("  Generated: architecture.pdf")
            return ["architecture.pdf"]
        else:
            logger.warning(f"Architecture diagram failed: {result.stderr[:100]}")
    except subprocess.TimeoutExpired:
        logger.warning("Architecture diagram timed out")
    return []


def _generate_dependency_graph(project_path: Path, figures_dir: Path) -> List[str]:
    """Generate dependency graph.

    Args:
        project_path: Path to the project
        figures_dir: Directory to save figure

    Returns:
        List of generated filenames (0 or 1)
    """
    try:
        result = subprocess.run(
            [
                str(FIXTURE_GRAPH_SCRIPT), "deps",
                "--project", str(project_path),
                "--output", str(figures_dir / "dependencies.pdf"),
                "--backend", "graphviz",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            typer.echo("  Generated: dependencies.pdf")
            return ["dependencies.pdf"]
        else:
            logger.warning(f"Dependency graph failed: {result.stderr[:100]}")
    except subprocess.TimeoutExpired:
        logger.warning("Dependency graph timed out")
    return []


def _generate_workflow_diagram(figures_dir: Path) -> List[str]:
    """Generate workflow diagram.

    Args:
        figures_dir: Directory to save figure

    Returns:
        List of generated filenames (0 or 1)
    """
    try:
        result = subprocess.run(
            [
                str(FIXTURE_GRAPH_SCRIPT), "workflow",
                "--stages", "Scope,Analysis,Search,Learn,Draft",
                "--output", str(figures_dir / "workflow.pdf"),
                "--backend", "graphviz",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            typer.echo("  Generated: workflow.pdf")
            return ["workflow.pdf"]
    except subprocess.TimeoutExpired:
        pass
    return []


def _generate_feature_metrics(analysis: ProjectAnalysis, figures_dir: Path) -> List[str]:
    """Generate feature metrics chart.

    Args:
        analysis: Project analysis results
        figures_dir: Directory to save figure

    Returns:
        List of generated filenames (0 or 1)
    """
    try:
        metrics_data = {
            f.get("feature", f"f{i}")[:15]: f.get("loc", 1)
            for i, f in enumerate(analysis.features[:8])
        }
        metrics_file = figures_dir / "metrics_data.json"
        metrics_file.write_text(json.dumps(metrics_data))

        result = subprocess.run(
            [
                str(FIXTURE_GRAPH_SCRIPT), "metrics",
                "--input", str(metrics_file),
                "--output", str(figures_dir / "features.pdf"),
                "--type", "bar",
                "--title", "Feature Distribution",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            typer.echo("  Generated: features.pdf")
            # Clean up temp file
            metrics_file.unlink(missing_ok=True)
            return ["features.pdf"]

        # Clean up temp file on failure too
        metrics_file.unlink(missing_ok=True)
    except Exception as e:
        logger.debug("value lookup failed: {}", e)
    return []
