"""
CLI for figure-lab — iterative visualization composition and testing.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from figure_lab.config import (
    GALLERY_DIR,
    FAILED_DIR,
    PROMOTE_THRESHOLD,
    MAX_ITERATIONS,
    CREATE_FIGURE_DIR,
)
from figure_lab.composer import Composition, compose_from_type, compose_from_description
from figure_lab.evaluator import evaluate_html, evaluate_file, diagnose_failures

app = typer.Typer(
    name="figure-lab",
    help="Iterative D3 visualization composition, testing, and promotion.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def compose(
    description: str = typer.Argument("", help="Natural language description or chart type name"),
    type_name: Optional[str] = typer.Option(None, "--type", "-t", help="d3_catalog type name"),
    data: Optional[Path] = typer.Option(None, "--data", "-d", help="JSON data file"),
    iterate: bool = typer.Option(False, "--iterate", "-i", help="Run self-improvement loop"),
    max_rounds: int = typer.Option(MAX_ITERATIONS, "--max-rounds", help="Max iteration rounds"),
    canvas: bool = typer.Option(True, "--canvas/--no-canvas", help="Canvas mode (5ft distance)"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output HTML file"),
):
    """Compose a new D3 visualization from description or type name."""
    # Load data
    if data and data.exists():
        chart_data = json.loads(data.read_text())
        if isinstance(chart_data, dict):
            chart_data = [chart_data]
    else:
        # Sample data for testing
        chart_data = [
            {"label": "A", "value": 42},
            {"label": "B", "value": 28},
            {"label": "C", "value": 65},
            {"label": "D", "value": 17},
            {"label": "E", "value": 53},
        ]
        console.print("[dim]Using sample data (pass --data for real data)[/dim]")

    # Compose
    if type_name:
        comp = compose_from_type(type_name, chart_data, title=description, canvas=canvas)
    elif description:
        comp = compose_from_description(description, chart_data, canvas=canvas)
    else:
        console.print("[red]Provide a description or --type name[/red]")
        raise typer.Exit(1)

    # Evaluate
    result = evaluate_html(comp.html, intent=description or type_name or "", data_count=len(chart_data))
    comp.scores = {
        "render_success": result.render_success,
        "data_marks": result.data_marks,
        "axes_labels": result.axes_labels,
        "intent_match": result.intent_match,
        "distance_aware": result.distance_aware,
    }

    # Display scores
    _print_eval_table(comp.name, result)

    # Self-improvement loop
    if iterate and result.verdict == "ITERATE":
        for round_num in range(1, max_rounds):
            console.print(f"\n[yellow]Iteration {round_num + 1}/{max_rounds}[/yellow]")
            suggestions = diagnose_failures(result)
            for s in suggestions:
                console.print(f"  [dim]{s}[/dim]")

            # Re-compose with diagnostics context
            comp.iterations = round_num + 1
            comp.version = round_num + 1

            # Re-evaluate
            result = evaluate_html(comp.html, intent=description or type_name or "", data_count=len(chart_data))
            comp.scores = {
                "render_success": result.render_success,
                "data_marks": result.data_marks,
                "axes_labels": result.axes_labels,
                "intent_match": result.intent_match,
                "distance_aware": result.distance_aware,
            }
            _print_eval_table(f"{comp.name} v{comp.version}", result)

            if result.verdict == "PROMOTE":
                console.print("[green]Converged! Ready for promotion.[/green]")
                break

    # Save
    failed = result.overall < PROMOTE_THRESHOLD
    saved_path = comp.save(failed=failed)

    # Write output if requested
    if output:
        output.write_text(comp.html)
        console.print(f"[green]Output: {output}[/green]")

    verdict_color = {"PROMOTE": "green", "ITERATE": "yellow", "RECOMPOSE": "red"}[result.verdict]
    console.print(f"\n[{verdict_color}]Verdict: {result.verdict}[/{verdict_color}] (score: {result.overall:.2f})")
    console.print(f"Saved: {saved_path}")


@app.command()
def evaluate(
    path: Path = typer.Argument(..., help="HTML file to evaluate"),
    intent: str = typer.Option("", "--intent", help="User's original intent/description"),
):
    """Evaluate a composition for quality."""
    if not path.exists():
        console.print(f"[red]File not found: {path}[/red]")
        raise typer.Exit(1)

    result = evaluate_file(path, intent=intent)
    _print_eval_table(path.name, result)

    if result.errors:
        console.print("\n[red]Errors:[/red]")
        for e in result.errors:
            console.print(f"  - {e}")

    if result.diagnostics:
        console.print("\n[yellow]Diagnostics:[/yellow]")
        for d in result.diagnostics:
            console.print(f"  - {d}")

    suggestions = diagnose_failures(result)
    if suggestions:
        console.print("\n[blue]Suggestions:[/blue]")
        for s in suggestions:
            console.print(f"  - {s}")


@app.command(name="evaluate-all")
def evaluate_all():
    """Batch evaluate all compositions in the gallery."""
    html_files = sorted(GALLERY_DIR.glob("*.html"))
    if not html_files:
        console.print("[dim]Gallery is empty[/dim]")
        return

    table = Table(title="Gallery Evaluation")
    table.add_column("Name")
    table.add_column("Score", justify="right")
    table.add_column("Verdict")
    table.add_column("Render")
    table.add_column("Marks")
    table.add_column("Axes")
    table.add_column("Intent")
    table.add_column("5ft")

    for f in html_files:
        result = evaluate_file(f)
        verdict_style = {"PROMOTE": "green", "ITERATE": "yellow", "RECOMPOSE": "red"}[result.verdict]
        table.add_row(
            f.stem,
            f"{result.overall:.2f}",
            f"[{verdict_style}]{result.verdict}[/{verdict_style}]",
            f"{result.render_success:.1f}",
            f"{result.data_marks:.1f}",
            f"{result.axes_labels:.1f}",
            f"{result.intent_match:.1f}",
            f"{result.distance_aware:.1f}",
        )

    console.print(table)


@app.command()
def promote(
    path: Path = typer.Argument(..., help="Gallery HTML or JSON to promote"),
    name: str = typer.Option(..., "--name", "-n", help="Command name for /create-figure"),
    family: str = typer.Option("", "--family", "-f", help="Visualization family"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would change"),
):
    """Promote a gallery composition to /create-figure as a first-class command."""
    # Load the composition
    json_path = path.with_suffix(".json") if path.suffix == ".html" else path
    if not json_path.exists():
        console.print(f"[red]Composition metadata not found: {json_path}[/red]")
        raise typer.Exit(1)

    comp = Composition.load(json_path)

    # Verify it passes quality threshold
    if comp.overall_score < PROMOTE_THRESHOLD:
        console.print(
            f"[red]Score {comp.overall_score:.2f} < {PROMOTE_THRESHOLD} threshold. "
            f"Run 'iterate' first.[/red]"
        )
        raise typer.Exit(1)

    console.print(f"[green]Promoting '{name}' to /create-figure[/green]")
    console.print(f"  Family: {family or comp.family}")
    console.print(f"  Score: {comp.overall_score:.2f}")
    console.print(f"  Iterations: {comp.iterations}")

    if dry_run:
        console.print("\n[yellow]Dry run — changes that would be made:[/yellow]")
        console.print(f"  1. Update d3_catalog.py: {name} backend NOT_YET → D3_INLINE")
        console.print(f"  2. Add D3 generator to composer.py")
        console.print(f"  3. Register in _CHART_TO_FIGURE_CMD mapping")
        console.print(f"  4. Learn to /memory")
        return

    # Mark as promoted
    comp.promoted = True
    from datetime import datetime, timezone

    comp.promoted_at = datetime.now(timezone.utc).isoformat()
    comp.save(failed=False)

    console.print(f"\n[green]Promoted! Gallery preset saved.[/green]")
    console.print("[dim]Next steps:[/dim]")
    console.print(f"  1. Add D3 generator for '{name}' to composer.py")
    console.print(f"  2. Update d3_catalog.py backend: NOT_YET → D3_INLINE")
    console.print(f"  3. Test: ./run.sh compose --type {name} --data sample.json")


@app.command()
def gallery():
    """List all compositions in the gallery."""
    json_files = sorted(GALLERY_DIR.glob("*.json"))
    if not json_files:
        console.print("[dim]Gallery is empty. Run 'compose' to create visualizations.[/dim]")
        return

    table = Table(title="Figure Lab Gallery")
    table.add_column("Name")
    table.add_column("Version", justify="right")
    table.add_column("Family")
    table.add_column("Score", justify="right")
    table.add_column("Promoted")
    table.add_column("Iterations", justify="right")

    for f in json_files:
        comp = Composition.load(f)
        promoted = "[green]Yes[/green]" if comp.promoted else ""
        table.add_row(
            comp.name,
            str(comp.version),
            comp.family,
            f"{comp.overall_score:.2f}",
            promoted,
            str(comp.iterations),
        )

    console.print(table)

    # Also show failed experiments
    failed_files = sorted(FAILED_DIR.glob("*.json"))
    if failed_files:
        console.print(f"\n[dim]{len(failed_files)} failed experiment(s) in _failed/[/dim]")


@app.command(name="catalog-status")
def catalog_status():
    """Show d3_catalog coverage: implemented vs NOT_YET types."""
    sys.path.insert(0, str(CREATE_FIGURE_DIR))
    try:
        from d3_catalog import D3_VIZ_CATALOG, RenderBackend
    except ImportError:
        console.print("[red]d3_catalog not found at create-figure skill[/red]")
        raise typer.Exit(1)

    implemented = []
    not_yet = []

    for vt in D3_VIZ_CATALOG.values():
        if vt.backend == RenderBackend.NOT_YET:
            not_yet.append(vt)
        else:
            implemented.append(vt)

    table = Table(title=f"d3_catalog Coverage ({len(implemented)}/{len(D3_VIZ_CATALOG)} implemented)")
    table.add_column("Type")
    table.add_column("Family")
    table.add_column("Backend")
    table.add_column("Status")

    for vt in sorted(D3_VIZ_CATALOG.values(), key=lambda v: (v.backend == RenderBackend.NOT_YET, v.family.value, v.name)):
        status = "[green]Implemented[/green]" if vt.backend != RenderBackend.NOT_YET else "[yellow]NOT_YET[/yellow]"
        table.add_row(vt.name, vt.family.value, vt.backend.value, status)

    console.print(table)
    console.print(f"\n[green]{len(implemented)} implemented[/green], [yellow]{len(not_yet)} pending[/yellow]")


@app.command()
def backlog():
    """List NOT_YET types ranked by potential user demand (keywords)."""
    sys.path.insert(0, str(CREATE_FIGURE_DIR))
    try:
        from d3_catalog import D3_VIZ_CATALOG, RenderBackend
    except ImportError:
        console.print("[red]d3_catalog not found[/red]")
        raise typer.Exit(1)

    pending = [vt for vt in D3_VIZ_CATALOG if vt.backend == RenderBackend.NOT_YET]

    # Rank by keyword count (proxy for user demand)
    pending.sort(key=lambda v: len(v.keywords), reverse=True)

    table = Table(title=f"Backlog: {len(pending)} Types Awaiting Development")
    table.add_column("Priority", justify="right")
    table.add_column("Type")
    table.add_column("Family")
    table.add_column("Keywords", justify="right")
    table.add_column("Description")

    for i, vt in enumerate(pending, 1):
        table.add_row(
            str(i),
            vt.name,
            vt.family.value,
            str(len(vt.keywords)),
            vt.description[:60] + "..." if len(vt.description) > 60 else vt.description,
        )

    console.print(table)


def _print_eval_table(name: str, result) -> None:
    """Print evaluation scores as a Rich table."""
    table = Table(title=f"Evaluation: {name}")
    table.add_column("Dimension")
    table.add_column("Score", justify="right")
    table.add_column("Weight", justify="right")
    table.add_column("Weighted", justify="right")

    from figure_lab.config import EVAL_WEIGHTS

    for dim, weight in EVAL_WEIGHTS.items():
        score = getattr(result, dim, 0.0)
        weighted = score * weight
        style = "green" if score >= 0.8 else ("yellow" if score >= 0.5 else "red")
        table.add_row(
            dim.replace("_", " ").title(),
            f"[{style}]{score:.2f}[/{style}]",
            f"{weight:.2f}",
            f"{weighted:.2f}",
        )

    table.add_row("", "", "[bold]Total[/bold]", f"[bold]{result.overall:.2f}[/bold]")
    console.print(table)
