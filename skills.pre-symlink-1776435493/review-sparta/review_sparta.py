#!/usr/bin/env python3
"""
review-sparta: Brandon Bailey persona-driven SPARTA quality assessment.

Comprehensive assessment across 6 dimensions:
1. QRA Quality (25%): Verbatim grounding, citations, hallucination
2. Source Fidelity (20%): DB matches SPARTA-Data.xlsx
3. CWE Relevance (20%): Space-applicable CWEs only
4. Cross-Reference (15%): MITRE ATT&CK, NIST 800-53, D3FEND accuracy
5. Coverage (10%): All 216 techniques, 91 countermeasures
6. Control Quality (10%): Meaningful comparisons

Implementation is split across:
- review_sparta_constants.py: Persona constants, CWE lists, dataclasses, helpers
- review_sparta_checks.py: 6 dimension checker functions
"""

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path.home() / ".pi" / "skills"))
    from common.task_monitor import TaskClient
except ImportError:
    TaskClient = None

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

# Re-export all public names from sub-modules for backward compatibility
from review_sparta_constants import (  # noqa: F401
    BRANDON_BAILEY_INTRO,
    GRADING_SCALE,
    SPACE_CWES,
    NON_SPACE_CWES,
    SPACE_TERMS,
    DimensionResult,
    AssessmentResult,
    has_verbatim_phrase,
    get_db_connection,
    generate_brandon_commentary,
)

from review_sparta_checks import (  # noqa: F401
    check_qra_quality,
    check_source_fidelity,
    check_cwe_relevance,
    check_cross_reference,
    check_coverage,
    check_control_quality,
)

app = typer.Typer(help="Brandon Bailey persona-driven SPARTA assessment")
console = Console()


# ─────────────────────────────────────────────────────────────────────────────
# CLI Commands
# ─────────────────────────────────────────────────────────────────────────────

@app.command()
def review(
    run_id: str = typer.Option(..., "--run-id", "-r", help="Run ID to assess"),
    full: bool = typer.Option(False, "--full", "-f", help="Run all dimension checks"),
    focus: Optional[str] = typer.Option(None, "--focus", help="Comma-separated dimensions to focus on"),
    samples: int = typer.Option(100, "--samples", "-n", help="Number of samples for sampling checks"),
    report: Optional[str] = typer.Option(None, "--report", help="Output markdown report to file"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    store: bool = typer.Option(False, "--store", help="Store findings in /memory"),
):
    """Run Brandon Bailey assessment on SPARTA data."""
    console.print(Panel(BRANDON_BAILEY_INTRO, title="SPARTA Assessment", border_style="cyan"))

    # Connect to database
    try:
        conn = get_db_connection(run_id)
    except FileNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    # Determine which dimensions to run
    all_dimensions = ["qra_quality", "source_fidelity", "cwe_relevance", "cross_reference", "coverage", "control_quality"]
    if focus:
        dimensions_to_run = [d.strip() for d in focus.split(",")]
    elif full:
        dimensions_to_run = all_dimensions
    else:
        dimensions_to_run = ["qra_quality", "source_fidelity", "cwe_relevance"]

    # Run dimension checks
    result = AssessmentResult(
        run_id=run_id,
        timestamp=datetime.now().isoformat()
    )

    monitor = TaskClient("review-sparta", total=len(dimensions_to_run)) if TaskClient else None

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        for dim in dimensions_to_run:
            task = progress.add_task(f"Checking {dim}...", total=1)

            if dim == "qra_quality":
                dim_result = check_qra_quality(conn, samples)
            elif dim == "source_fidelity":
                dim_result = check_source_fidelity(conn)
            elif dim == "cwe_relevance":
                dim_result = check_cwe_relevance(conn, samples)
            elif dim == "cross_reference":
                dim_result = check_cross_reference(conn)
            elif dim == "coverage":
                dim_result = check_coverage(conn)
            elif dim == "control_quality":
                dim_result = check_control_quality(conn, samples)
            else:
                continue

            result.dimensions[dim] = dim_result
            progress.update(task, completed=1)
            if monitor:
                monitor.update(item=dim)

    conn.close()

    # Calculate overall score
    result.calculate_overall()
    result.brandon_commentary = generate_brandon_commentary(result)

    if monitor:
        monitor.finish()

    # Output
    if json_output:
        output = {
            "persona": "Brandon Bailey",
            "run_id": result.run_id,
            "timestamp": result.timestamp,
            "dimensions": {k: asdict(v) for k, v in result.dimensions.items()},
            "overall": {
                "score": result.overall_score,
                "grade": result.grade,
                "verdict": result.verdict,
                "critical_issues": result.critical_issues,
                "warnings": result.warnings,
            },
            "brandon_commentary": result.brandon_commentary,
        }
        console.print_json(json.dumps(output, indent=2))
    else:
        # Rich table output
        console.print("\n[bold]Dimension Results[/bold]")
        table = Table(show_header=True)
        table.add_column("Dimension")
        table.add_column("Weight")
        table.add_column("Score")
        table.add_column("Status")

        for dim_name, dim in result.dimensions.items():
            status = "[green]PASS[/green]" if dim.passed else "[red]FAIL[/red]"
            table.add_row(
                dim_name,
                f"{dim.weight:.0%}",
                f"{dim.score:.2f}",
                status
            )

        console.print(table)

        # Overall result
        grade_color = "green" if result.grade in ["A+", "A"] else "yellow" if result.grade == "B" else "red"
        console.print(f"\n[bold]Overall Score:[/bold] {result.overall_score:.2f}")
        console.print(f"[bold]Grade:[/bold] [{grade_color}]{result.grade} {result.verdict}[/{grade_color}]")

        if result.critical_issues > 0 or result.warnings > 0:
            console.print(f"\n[bold]Issues:[/bold] {result.critical_issues} critical, {result.warnings} warnings")

        # Brandon's commentary
        console.print(Panel(
            result.brandon_commentary,
            title="Brandon Bailey's Assessment",
            border_style="cyan"
        ))

        # Issues summary
        all_issues = []
        all_suggestions = []
        for dim in result.dimensions.values():
            all_issues.extend(dim.issues)
            all_suggestions.extend(dim.suggestions)

        if all_issues:
            console.print("\n[bold]Issues Found:[/bold]")
            for issue in all_issues:
                console.print(f"  [red]*[/red] {issue}")

        if all_suggestions:
            console.print("\n[bold]Suggestions:[/bold]")
            for suggestion in all_suggestions:
                console.print(f"  [blue]->[/blue] {suggestion}")

    # Save report if requested
    if report:
        report_path = Path(report)
        with open(report_path, "w") as f:
            f.write(f"# Brandon Bailey SPARTA Assessment\n\n")
            f.write(f"**Run ID:** {result.run_id}\n")
            f.write(f"**Date:** {result.timestamp}\n")
            f.write(f"**Grade:** {result.grade} ({result.verdict})\n")
            f.write(f"**Overall Score:** {result.overall_score:.2f}\n\n")
            f.write(f"## Brandon's Commentary\n\n{result.brandon_commentary}\n\n")
            f.write("## Dimension Results\n\n")
            for dim_name, dim in result.dimensions.items():
                f.write(f"### {dim_name} ({dim.weight:.0%})\n")
                f.write(f"Score: {dim.score:.2f}\n\n")
                if dim.issues:
                    f.write("**Issues:**\n")
                    for issue in dim.issues:
                        f.write(f"- {issue}\n")
                    f.write("\n")
        console.print(f"\n[dim]Report saved to: {report_path}[/dim]")


@app.command()
def status(
    run_id: str = typer.Option(..., "--run-id", "-r", help="Run ID to check"),
):
    """Quick health check for a SPARTA run."""
    try:
        conn = get_db_connection(run_id)

        qra_count = conn.execute("SELECT COUNT(*) FROM qra").fetchone()[0]
        avg_grounding = conn.execute(
            "SELECT AVG(grounding_score) FROM qra WHERE grounding_score > 0"
        ).fetchone()[0] or 0.0

        conn.close()

        console.print(f"[bold]Run:[/bold] {run_id}")
        console.print(f"[bold]QRAs:[/bold] {qra_count:,}")
        console.print(f"[bold]Avg Grounding:[/bold] {avg_grounding:.3f}")

        if avg_grounding >= 0.85:
            console.print("[green]Status: Healthy[/green]")
        elif avg_grounding >= 0.70:
            console.print("[yellow]Status: Needs Review[/yellow]")
        else:
            console.print("[red]Status: Critical Issues[/red]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def compare(
    run_a: str = typer.Argument(..., help="First run ID"),
    run_b: str = typer.Argument(..., help="Second run ID"),
    dimension: Optional[str] = typer.Option(None, "--dimension", "-d", help="Focus on specific dimension"),
):
    """Compare two SPARTA runs."""
    raise NotImplementedError("compare command not yet implemented")


@app.command()
def convergence(
    last: int = typer.Option(10, "--last", "-n", help="Show last N assessments"),
):
    """Track improvement over time."""
    raise NotImplementedError("convergence command not yet implemented")


if __name__ == "__main__":
    app()
