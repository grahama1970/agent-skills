#!/usr/bin/env python3
"""
figure_lab.py — Typer CLI for figure-lab skill.

Composes, evaluates, promotes, and manages D3 visualizations.
Uses d3_backend.render_d3() from /create-figure for rendering
and d3_catalog for type lookups.

Usage:
    python figure_lab.py compose --type bar --data sample.json --output gallery/bar_v1.html
    python figure_lab.py evaluate --input gallery/bar_v1.html
    python figure_lab.py promote --input gallery/bar_v1.html
    python figure_lab.py gallery
    python figure_lab.py catalog-status
    python figure_lab.py backlog
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

from evaluation import EvalScores, evaluate_html, print_scores, EVAL_WEIGHTS

# ---------------------------------------------------------------------------
# Path setup — import from sibling /create-figure skill
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent.parent / "create-figure"))

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SKILL_DIR = Path(__file__).resolve().parent
GALLERY_DIR = SKILL_DIR / "gallery"
FAILED_DIR = GALLERY_DIR / "_failed"
CREATE_FIGURE_DIR = Path(__file__).resolve().parent.parent / "create-figure"
D3_GALLERY_DIR = CREATE_FIGURE_DIR / "d3" / "gallery"

PROMOTE_THRESHOLD = 0.75

# Ensure directories exist
GALLERY_DIR.mkdir(parents=True, exist_ok=True)
FAILED_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Typer app
# ---------------------------------------------------------------------------
app = typer.Typer(
    name="figure-lab",
    help="Iterative D3 visualization composition, testing, and promotion.",
    no_args_is_help=True,
)
console = Console()


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------
@dataclass
class CompositionMeta:
    """Metadata for a gallery composition."""
    name: str
    viz_type: str = ""
    description: str = ""
    output_path: str = ""
    scores: dict[str, float] = field(default_factory=dict)
    overall_score: float = 0.0
    promoted: bool = False
    promoted_at: str | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls, path: Path) -> "CompositionMeta":
        data = json.loads(path.read_text())
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Helpers: import from create-figure
# ---------------------------------------------------------------------------
def _get_d3_backend():
    """Import d3_backend from /create-figure."""
    try:
        import d3_backend
        return d3_backend
    except ImportError:
        logger.error("Cannot import d3_backend from {}", CREATE_FIGURE_DIR)
        return None


def _get_d3_catalog():
    """Import d3_catalog from /create-figure."""
    try:
        import d3_catalog
        return d3_catalog
    except ImportError:
        logger.error("Cannot import d3_catalog from {}", CREATE_FIGURE_DIR)
        return None


def _get_catalog_types():
    """Import d3_catalog_types from /create-figure."""
    try:
        import d3_catalog_types
        return d3_catalog_types
    except ImportError:
        logger.error("Cannot import d3_catalog_types from {}", CREATE_FIGURE_DIR)
        return None


# ---------------------------------------------------------------------------
# Evaluation (delegated to evaluation.py)
# ---------------------------------------------------------------------------
def _evaluate_html(html: str) -> EvalScores:
    """Delegate to evaluation.py."""
    return evaluate_html(html)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
@app.command()
def compose(
    type: Optional[str] = typer.Option(None, "--type", "-t", help="d3_catalog type name (e.g. bar, scatter, heatmap)"),
    data: Optional[Path] = typer.Option(None, "--data", "-d", help="Path to JSON data file"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output HTML path (default: gallery/<type>_v1.html)"),
    description: str = typer.Option("", "--description", help="User description of the visualization"),
):
    """
    Compose a D3 visualization using d3_backend.render_d3() from /create-figure.

    Takes a d3_catalog type name or user description, renders to HTML,
    saves to the figure-lab gallery with metadata JSON.
    """
    backend = _get_d3_backend()
    catalog = _get_d3_catalog()

    if not backend:
        console.print("[red]d3_backend not available — is /create-figure present?[/red]")
        raise typer.Exit(1)

    # Resolve viz type
    viz_type = type
    if not viz_type and description and catalog:
        matches = catalog.match_keywords(description)
        if matches:
            viz_type = matches[0][0]
            logger.info("Matched description '{}' to viz type '{}'", description, viz_type)
        else:
            # Try profile_data if we have data
            if data and data.exists() and hasattr(catalog, "profile_data"):
                chart_data_raw = json.loads(data.read_text())
                if isinstance(chart_data_raw, list):
                    recs = catalog.profile_data(chart_data_raw, query=description)
                    if recs:
                        viz_type = recs[0][0]
                        logger.info("profile_data recommended '{}' for data", viz_type)
            if not viz_type:
                viz_type = "bar"
                logger.info("No keyword match for '{}', defaulting to 'bar'", description)
    elif not viz_type:
        console.print("[red]Provide --type or --description[/red]")
        raise typer.Exit(1)

    # Load data
    if data and data.exists():
        chart_data = json.loads(data.read_text())
    else:
        chart_data = [
            {"label": "A", "value": 42},
            {"label": "B", "value": 28},
            {"label": "C", "value": 65},
            {"label": "D", "value": 17},
            {"label": "E", "value": 53},
        ]
        if data:
            console.print(f"[yellow]Data file not found: {data}. Using sample data.[/yellow]")
        else:
            console.print("[dim]Using sample data (pass --data for real data)[/dim]")

    # Determine output path
    if not output:
        # Find next version number in gallery
        existing = sorted(GALLERY_DIR.glob(f"{viz_type}_v*.html"))
        if existing:
            last_ver = int(existing[-1].stem.split("_v")[-1])
            ver = last_ver + 1
        else:
            ver = 1
        output = GALLERY_DIR / f"{viz_type}_v{ver}.html"
    else:
        output = Path(output)

    output.parent.mkdir(parents=True, exist_ok=True)

    # Render using d3_backend.render_d3()
    title = description or f"{viz_type} visualization"
    logger.info("Composing '{}' → {}", viz_type, output)

    success = backend.render_d3(
        viz_name=viz_type,
        data=chart_data,
        output_path=output,
        title=title,
        canvas=True,
    )

    if not success:
        console.print(f"[red]render_d3() failed for type '{viz_type}'[/red]")
        raise typer.Exit(1)

    console.print(f"[green]Rendered: {output}[/green]")

    # Evaluate the output
    html = output.read_text()
    scores = _evaluate_html(html)

    # Save metadata JSON alongside
    meta = CompositionMeta(
        name=output.stem,
        viz_type=viz_type,
        description=title,
        output_path=str(output),
        scores=scores.to_dict(),
        overall_score=scores.overall,
    )
    meta_path = output.with_suffix(".json")
    meta.save(meta_path)
    logger.info("Metadata saved: {}", meta_path)

    # Print score table
    _print_scores(output.stem, scores)
    console.print(f"\nOverall: [bold]{scores.overall:.2f}[/bold]  "
                  f"{'[green]PASS[/green]' if scores.overall >= PROMOTE_THRESHOLD else '[yellow]BELOW THRESHOLD[/yellow]'}")


@app.command()
def evaluate(
    input: Path = typer.Option(..., "--input", "-i", help="Path to HTML file to evaluate"),
):
    """
    Evaluate a D3 visualization HTML file.

    Checks 5 dimensions: render_success, data_marks, axes_labels,
    intent_match, distance_aware. Returns overall score 0.0-1.0.
    """
    if not input.exists():
        console.print(f"[red]File not found: {input}[/red]")
        raise typer.Exit(1)

    html = input.read_text()
    scores = _evaluate_html(html)
    _print_scores(input.name, scores)

    verdict = (
        "[green]PROMOTE[/green]" if scores.overall >= PROMOTE_THRESHOLD
        else "[yellow]ITERATE[/yellow]" if scores.overall >= 0.50
        else "[red]RECOMPOSE[/red]"
    )
    console.print(f"\nOverall: [bold]{scores.overall:.2f}[/bold]  Verdict: {verdict}")

    return scores.overall


@app.command()
def promote(
    input: Path = typer.Option(..., "--input", "-i", help="Gallery HTML file to promote"),
):
    """
    Promote a figure-lab gallery composition to /create-figure/d3/gallery/.

    Copies the HTML to the create-figure D3 gallery and updates
    d3_catalog_entries to change the backend from NOT_YET to D3_INLINE
    for the viz type.
    """
    if not input.exists():
        console.print(f"[red]File not found: {input}[/red]")
        raise typer.Exit(1)

    # Validate the file contains D3 content
    html_content = input.read_text(encoding="utf-8")
    if "d3" not in html_content.lower() and "<svg" not in html_content.lower():
        console.print(
            "[red]File does not appear to contain D3 or SVG content. "
            "Only D3 visualizations can be promoted.[/red]"
        )
        raise typer.Exit(1)

    # Load and verify score
    meta_path = input.with_suffix(".json")
    if meta_path.exists():
        meta = CompositionMeta.load(meta_path)
        if meta.overall_score < PROMOTE_THRESHOLD:
            console.print(
                f"[red]Score {meta.overall_score:.2f} < {PROMOTE_THRESHOLD} threshold. "
                f"Run 'evaluate' and iterate first.[/red]"
            )
            raise typer.Exit(1)
        viz_type = meta.viz_type
    else:
        # Require metadata for promotion — prevents arbitrary file injection
        console.print(
            "[red]No metadata JSON found at {}. "
            "Run 'evaluate' first to generate scores before promoting.[/red]".format(meta_path)
        )
        raise typer.Exit(1)

    # 1. Copy HTML to create-figure d3/gallery/
    D3_GALLERY_DIR.mkdir(parents=True, exist_ok=True)
    dest = D3_GALLERY_DIR / f"{viz_type}.html"
    shutil.copy2(input, dest)
    console.print(f"[green]Copied {input.name} -> {dest}[/green]")

    # 2. Update d3_catalog_entries to change backend NOT_YET -> D3_INLINE
    _update_catalog_backend(viz_type)

    # 3. Update metadata
    if meta_path.exists():
        meta.promoted = True
        meta.promoted_at = datetime.now(timezone.utc).isoformat()
        meta.save(meta_path)

    console.print(f"\n[green]Promoted '{viz_type}' to /create-figure/d3/gallery/[/green]")
    console.print("[dim]Test with: cd ../create-figure && uv run python d3_backend.py[/dim]")


def _update_catalog_backend(viz_type: str) -> None:
    """Update d3_catalog_entries to change backend from NOT_YET to D3_INLINE for a viz type."""
    # Search both entry files
    for entry_file in ["d3_catalog_entries_basic.py", "d3_catalog_entries_advanced.py"]:
        path = CREATE_FIGURE_DIR / entry_file
        if not path.exists():
            continue

        text = path.read_text()

        # Look for the viz type registration block and change NOT_YET -> D3_INLINE
        # Pattern: name="<viz_type>", ... backend=RenderBackend.NOT_YET
        # We need to find the _register(VizType( block for this type
        pattern = rf'(name="{viz_type}".*?backend=RenderBackend\.)NOT_YET'
        if re.search(pattern, text, re.DOTALL):
            new_text = re.sub(pattern, r'\1D3_INLINE', text, flags=re.DOTALL)
            path.write_text(new_text)
            logger.info("Updated {} backend NOT_YET -> D3_INLINE in {}", viz_type, entry_file)
            console.print(f"[green]Updated {entry_file}: {viz_type} backend -> D3_INLINE[/green]")
            return

    logger.warning("Could not find backend=NOT_YET entry for '{}' in catalog entries", viz_type)
    console.print(f"[yellow]No NOT_YET entry found for '{viz_type}' — may already be D3_INLINE[/yellow]")


@app.command()
def iterate(
    input: Path = typer.Option(..., "--input", "-i", help="HTML file to iterate on"),
    data: Optional[Path] = typer.Option(None, "--data", "-d", help="JSON data file"),
    max_rounds: int = typer.Option(3, "--max-rounds", help="Max iteration rounds"),
    threshold: float = typer.Option(PROMOTE_THRESHOLD, "--threshold", help="Target score"),
):
    """
    Iterate on a composition to improve its evaluation score.

    Diagnoses the lowest-scoring dimension and applies rule-based fixes:
    - Low render_success: re-render with d3_backend (template might be missing)
    - Low data_marks: try a different viz family with more visual marks
    - Low axes_labels: re-render with axis-heavy type (bar, line, scatter)
    - Low distance_aware: re-render with canvas=True for 5ft mode
    - Low intent_match: try the next-best profile_data recommendation

    Falls back to render_with_fallback if all else fails.
    """
    if not input.exists():
        console.print(f"[red]File not found: {input}[/red]")
        raise typer.Exit(1)

    backend = _get_d3_backend()
    catalog = _get_d3_catalog()
    if not backend or not catalog:
        console.print("[red]d3_backend/d3_catalog not available[/red]")
        raise typer.Exit(1)

    # Load metadata if available
    meta_path = input.with_suffix(".json")
    viz_type = None
    if meta_path.exists():
        meta = CompositionMeta.load(meta_path)
        viz_type = meta.viz_type

    # Load data for re-rendering
    chart_data = None
    if data and data.exists():
        chart_data = json.loads(data.read_text())
    else:
        chart_data = [
            {"label": "A", "value": 42}, {"label": "B", "value": 28},
            {"label": "C", "value": 65}, {"label": "D", "value": 17},
            {"label": "E", "value": 53},
        ]

    # Viz families to try in order of mark richness
    axis_heavy = ["bar", "grouped_bar", "line", "scatter", "area"]
    mark_rich = ["scatter", "bubble", "heatmap", "treemap"]

    best_score = 0.0
    best_html_path = input

    for round_num in range(1, max_rounds + 1):
        console.print(f"\n[bold]--- Iteration {round_num}/{max_rounds} ---[/bold]")

        html = best_html_path.read_text()
        scores = _evaluate_html(html)
        _print_scores(f"Round {round_num}", scores)

        if scores.overall >= threshold:
            console.print(f"[green]Score {scores.overall:.2f} >= {threshold} threshold. Done![/green]")
            break

        if scores.overall > best_score:
            best_score = scores.overall

        # Diagnose: find lowest-scoring dimension
        dim_scores = {
            "render_success": scores.render_success,
            "data_marks": scores.data_marks,
            "axes_labels": scores.axes_labels,
            "intent_match": scores.intent_match,
            "distance_aware": scores.distance_aware,
        }
        worst_dim = min(dim_scores, key=dim_scores.get)
        console.print(f"[yellow]Weakest dimension: {worst_dim} ({dim_scores[worst_dim]:.2f})[/yellow]")

        # Apply fix based on worst dimension
        new_type = viz_type or "bar"
        if worst_dim == "axes_labels" and new_type not in axis_heavy:
            new_type = axis_heavy[round_num % len(axis_heavy)]
            console.print(f"  Switching to axis-heavy type: {new_type}")
        elif worst_dim == "data_marks" and new_type not in mark_rich:
            new_type = mark_rich[round_num % len(mark_rich)]
            console.print(f"  Switching to mark-rich type: {new_type}")
        elif worst_dim == "intent_match":
            # Try profile_data recommendations
            if hasattr(catalog, "profile_data") and isinstance(chart_data, list):
                recs = catalog.profile_data(chart_data)
                if len(recs) > round_num:
                    new_type = recs[round_num][0]
                    console.print(f"  Trying profile_data recommendation #{round_num}: {new_type}")
        elif worst_dim == "render_success":
            # Re-render same type — might have been a template issue
            console.print(f"  Re-rendering with {new_type}")

        # Re-render
        out_path = input.parent / f"{input.stem}_iter{round_num}.html"
        success = backend.render_d3(
            viz_name=new_type,
            data=chart_data,
            output_path=out_path,
            title=f"{new_type} (iteration {round_num})",
            canvas=True,  # Always use canvas for distance_aware boost
        )

        if success:
            new_scores = _evaluate_html(out_path.read_text())
            console.print(f"  New score: {new_scores.overall:.2f} (was {scores.overall:.2f})")
            if new_scores.overall > scores.overall:
                best_html_path = out_path
                best_score = new_scores.overall
                viz_type = new_type
                console.print(f"  [green]Improved! Using {new_type}[/green]")
            else:
                console.print(f"  [dim]No improvement, keeping previous[/dim]")
        else:
            console.print(f"  [red]Render failed for {new_type}[/red]")

    # Final evaluation
    final_scores = _evaluate_html(best_html_path.read_text())
    console.print(f"\n[bold]Final score: {final_scores.overall:.2f}[/bold]")

    verdict = (
        "[green]PROMOTE[/green]" if final_scores.overall >= threshold
        else "[yellow]BELOW THRESHOLD[/yellow]"
    )
    console.print(f"Verdict: {verdict}")

    # Update metadata
    if meta_path.exists():
        meta = CompositionMeta.load(meta_path)
        meta.scores = final_scores.to_dict()
        meta.overall_score = final_scores.overall
        if viz_type:
            meta.viz_type = viz_type
        meta.save(meta_path)

    if best_html_path != input:
        console.print(f"Best result: {best_html_path}")


@app.command()
def gallery():
    """List all compositions in the figure-lab gallery with scores."""
    json_files = sorted(GALLERY_DIR.glob("*.json"))
    if not json_files:
        console.print("[dim]Gallery is empty. Run 'compose' to create visualizations.[/dim]")
        return

    table = Table(title="Figure Lab Gallery")
    table.add_column("Name")
    table.add_column("Viz Type")
    table.add_column("Score", justify="right")
    table.add_column("Render", justify="right")
    table.add_column("Marks", justify="right")
    table.add_column("Axes", justify="right")
    table.add_column("Intent", justify="right")
    table.add_column("5ft", justify="right")
    table.add_column("Promoted")

    for f in json_files:
        try:
            meta = CompositionMeta.load(f)
        except Exception as e:
            logger.debug("Skipping {}: {}", f.name, e)
            continue

        scores = meta.scores
        promoted = "[green]Yes[/green]" if meta.promoted else ""
        overall = meta.overall_score
        score_style = "green" if overall >= PROMOTE_THRESHOLD else ("yellow" if overall >= 0.50 else "red")

        table.add_row(
            meta.name,
            meta.viz_type or "",
            f"[{score_style}]{overall:.2f}[/{score_style}]",
            f"{scores.get('render_success', 0):.2f}",
            f"{scores.get('data_marks', 0):.2f}",
            f"{scores.get('axes_labels', 0):.2f}",
            f"{scores.get('intent_match', 0):.2f}",
            f"{scores.get('distance_aware', 0):.2f}",
            promoted,
        )

    console.print(table)

    # Count failed
    failed_files = sorted(FAILED_DIR.glob("*.json"))
    if failed_files:
        console.print(f"\n[dim]{len(failed_files)} failed experiment(s) in _failed/[/dim]")


@app.command(name="catalog-status")
def catalog_status():
    """Show d3_catalog types grouped by backend (D3_INLINE vs NOT_YET)."""
    catalog = _get_d3_catalog()
    types_mod = _get_catalog_types()
    if not catalog or not types_mod:
        console.print("[red]d3_catalog not available[/red]")
        raise typer.Exit(1)

    D3_VIZ_CATALOG = types_mod.D3_VIZ_CATALOG
    RenderBackend = types_mod.RenderBackend

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

    for vt in sorted(
        D3_VIZ_CATALOG.values(),
        key=lambda v: (v.backend == RenderBackend.NOT_YET, v.family.value, v.name),
    ):
        if vt.backend != RenderBackend.NOT_YET:
            status = "[green]Implemented[/green]"
            backend_style = "green"
        else:
            status = "[yellow]NOT_YET[/yellow]"
            backend_style = "yellow"
        table.add_row(vt.name, vt.family.value, f"[{backend_style}]{vt.backend.value}[/{backend_style}]", status)

    console.print(table)
    console.print(f"\n[green]{len(implemented)} implemented[/green], [yellow]{len(not_yet)} pending[/yellow]")


@app.command()
def backlog():
    """List NOT_YET types from d3_catalog, ranked by keyword count."""
    catalog = _get_d3_catalog()
    types_mod = _get_catalog_types()
    if not catalog or not types_mod:
        console.print("[red]d3_catalog not available[/red]")
        raise typer.Exit(1)

    D3_VIZ_CATALOG = types_mod.D3_VIZ_CATALOG
    RenderBackend = types_mod.RenderBackend

    pending = [vt for vt in D3_VIZ_CATALOG.values() if vt.backend == RenderBackend.NOT_YET]
    pending.sort(key=lambda v: len(v.keywords), reverse=True)

    if not pending:
        console.print("[green]No backlog — all viz types are implemented![/green]")
        return

    table = Table(title=f"Backlog: {len(pending)} Types Awaiting Development")
    table.add_column("#", justify="right")
    table.add_column("Type")
    table.add_column("Family")
    table.add_column("Keywords", justify="right")
    table.add_column("Description")

    for i, vt in enumerate(pending, 1):
        desc = vt.description[:60] + "..." if len(vt.description) > 60 else vt.description
        table.add_row(str(i), vt.name, vt.family.value, str(len(vt.keywords)), desc)

    console.print(table)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _print_scores(name: str, scores: EvalScores) -> None:
    """Delegate to evaluation.print_scores()."""
    print_scores(name, scores)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app()
