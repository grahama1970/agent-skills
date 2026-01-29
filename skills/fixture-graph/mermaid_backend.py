#!/usr/bin/env python3
"""
Mermaid backend for fixture-graph skill.

Handles Mermaid diagram generation:
- Dependency diagrams
- Architecture diagrams
- Workflow diagrams
- Quick documentation diagrams (GitHub-compatible)
"""

import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import typer

from config import DependencyNode
from utils import check_mermaid


def render_mermaid(mermaid_code: str, output_path: Path, format: str = "pdf") -> bool:
    """Render Mermaid diagram to file."""
    # If format is mmd, just save the text directly
    if format == "mmd":
        mmd_output = output_path.with_suffix(".mmd") if output_path.suffix != ".mmd" else output_path
        mmd_output.write_text(mermaid_code)
        return True

    if not check_mermaid():
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


def generate_mermaid_dep_graph(
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
    return render_mermaid(mermaid_code, output_path, format)


def generate_mermaid_architecture(
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
    return render_mermaid(mermaid_code, output_path, format)


def generate_mermaid_workflow(
    stages: List[str],
    output_path: Path,
    format: str = "pdf",
    with_gates: bool = True,
) -> bool:
    """Generate workflow diagram using Mermaid."""
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

    return render_mermaid("\n".join(lines), output_path, format)
