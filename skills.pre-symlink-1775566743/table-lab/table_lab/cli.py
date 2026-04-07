"""Typer CLI for table-lab. Six commands: tune, probe, show, apply, tune-corpus, watchdog."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

from .config import BACKEND, CHECKPOINT_DIR, CORPUS_HINTS_PATH
from .evaluate import quality_grade, score_result
from .hints import export_to_corpus, list_hints, load_hint, save_hint
from .probe import probe_page, probe_page_rust
from .sampler import page_summary
from .tuner import TuneResult, print_tune_results, tune

try:
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path.home() / ".pi" / "skills"))
    from common.task_monitor import TaskClient
except ImportError:
    TaskClient = None

app = typer.Typer(
    name="table-lab",
    help="Iterative Camelot parameter tuning for table extraction.",
    add_completion=False,
)
console = Console()


@app.command("tune")
def tune_cmd(
    pdf: Path = typer.Argument(..., help="Path to PDF file"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show sample pages only"),
    json_out: bool = typer.Option(False, "--json", help="JSON output"),
    preset: Optional[str] = typer.Option(None, "--preset", help="S00 preset for hint storage"),
    category: Optional[str] = typer.Option(None, "--category", help="PDF category for hint storage"),
    no_early_stop: bool = typer.Option(False, "--no-early-stop", help="Try all strategies even if perfect found"),
    converge: bool = typer.Option(False, "--converge", help="Enable convergence loop for iterative refinement"),
    max_iterations: int = typer.Option(3, "--max-iterations", help="Max convergence iterations"),
    backend: str = typer.Option(BACKEND, "--backend", help="Extraction backend: camelot or rust (pdf_oxide)"),
) -> None:
    """Sweep parameter grid and find best extraction settings for a PDF."""
    if not pdf.exists():
        console.print(f"[red]File not found: {pdf}[/red]")
        raise typer.Exit(1)

    if dry_run:
        summary = page_summary(pdf, backend=backend)
        if json_out:
            console.print_json(json.dumps(summary))
        else:
            console.print(f"[bold]{pdf.name}[/bold]: {summary['total_pages']} pages, "
                          f"{summary['pages_with_tables']} with tables")
            console.print(f"Sample pages (1-based): {[p+1 for p in summary['sample_pages']]}")
        return

    _monitor = TaskClient(f"table-lab/tune", total=max_iterations if converge else 1, description=f"Tuning {pdf.name}") if TaskClient else None

    if converge:
        from .corpus import tune_with_convergence
        result, iterations, converged = tune_with_convergence(
            pdf, preset=preset or "", category=category or "",
            max_iterations=max_iterations,
        )
    else:
        result = tune(pdf, early_stop=not no_early_stop, backend=backend)
        iterations = 1
        converged = result.early_stop

    if _monitor:
        _monitor.update(item=f"score={result.best_score} flavor={result.best_flavor}")
        _monitor.finish()

    if json_out:
        data = {
            "pdf": str(pdf),
            "best_flavor": result.best_flavor,
            "best_line_scale": result.best_line_scale,
            "best_edge_tol": result.best_edge_tol,
            "best_score": result.best_score,
            "best_fragmentation": result.best_fragmentation,
            "best_cell_count": result.best_cell_count,
            "pages_tested": result.pages_tested,
            "early_stop": result.early_stop,
            "all_results": result.all_results,
        }
        if converge:
            data["iterations"] = iterations
            data["converged"] = converged
        console.print_json(json.dumps(data))
    else:
        print_tune_results(result)
        if converge:
            console.print(f"[dim]Convergence: {iterations} iteration(s), converged={converged}[/dim]")

    # Auto-save hint if preset/category provided
    if preset or category:
        from .bridge import tag_extraction_result
        bridge_tags = tag_extraction_result(result)
        hint = result.to_hint(preset=preset or "", category=category or "",
                              bridge_tags=bridge_tags)
        save_hint(preset or "", category or "", hint)
        console.print(f"\n[green]Hint saved for {preset or '?'}:{category or '?'}[/green]")
        if bridge_tags:
            console.print(f"[dim]Bridge tags: {', '.join(bridge_tags)}[/dim]")


@app.command("probe")
def probe_cmd(
    pdf: Path = typer.Argument(..., help="Path to PDF file"),
    flavor: str = typer.Option("lattice", "--flavor", help="lattice or stream"),
    line_scale: Optional[int] = typer.Option(None, "--line-scale", help="Camelot line_scale (lattice)"),
    edge_tol: Optional[int] = typer.Option(None, "--edge-tol", help="Camelot edge_tol (stream)"),
    page: Optional[int] = typer.Option(None, "--page", help="Page number (1-based)"),
    json_out: bool = typer.Option(False, "--json", help="JSON output"),
    backend: str = typer.Option(BACKEND, "--backend", help="Extraction backend: camelot or rust (pdf_oxide)"),
) -> None:
    """Single extraction attempt with specific parameters."""
    if not pdf.exists():
        console.print(f"[red]File not found: {pdf}[/red]")
        raise typer.Exit(1)

    # Default line_scale/edge_tol
    if flavor == "lattice" and line_scale is None:
        line_scale = 15
    if flavor == "stream" and edge_tol is None:
        edge_tol = 50

    # Auto-pick page if not specified
    if page is None:
        from .sampler import find_pages_with_tables
        pages = find_pages_with_tables(pdf, max_pages=1, backend=backend)
        if not pages:
            console.print("[yellow]No pages with tables detected. Use --page to specify.[/yellow]")
            raise typer.Exit(1)
        page_0 = pages[0]
    else:
        page_0 = page - 1  # convert to 0-based

    _probe = probe_page_rust if backend == "rust" else probe_page
    result = _probe(pdf, page_0, flavor, line_scale=line_scale, edge_tol=edge_tol)
    sc = score_result(result)

    if json_out:
        console.print_json(json.dumps({
            "page": page_0 + 1,
            "flavor": result.flavor,
            "line_scale": result.line_scale,
            "edge_tol": result.edge_tol,
            "table_count": result.table_count,
            "cell_count": result.cell_count,
            "fragmentation": result.fragmentation,
            "score": sc,
            "duration_ms": result.duration_ms,
            "error": result.error,
        }))
    else:
        frag_color = "green" if result.fragmentation == 0 else "red"
        console.print(
            f"[bold]Page {page_0+1}[/bold] | "
            f"{flavor}(ls={line_scale}, et={edge_tol}) | "
            f"tables={result.table_count} | "
            f"cells={result.cell_count} | "
            f"frag=[{frag_color}]{result.fragmentation}[/{frag_color}] | "
            f"score={sc:.0f} | "
            f"{result.duration_ms}ms"
        )
        if result.error:
            console.print(f"[red]Error: {result.error}[/red]")

        # Show table preview
        if result.tables_data:
            for i, table_data in enumerate(result.tables_data):
                if len(table_data) > 0:
                    t = Table(title=f"Table {i+1} ({len(table_data)} rows)")
                    ncols = len(table_data[0]) if table_data else 0
                    for c in range(ncols):
                        t.add_column(f"Col {c+1}", max_width=30)
                    for row in table_data[:8]:  # show first 8 rows
                        t.add_row(*[str(cell)[:30] for cell in row])
                    if len(table_data) > 8:
                        t.add_row(*["..." for _ in range(ncols)])
                    console.print(t)


@app.command()
def show(
    preset: Optional[str] = typer.Option(None, "--preset", help="Filter by preset"),
    category: Optional[str] = typer.Option(None, "--category", help="Filter by category"),
    json_out: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Display stored strategy hints."""
    if preset or category:
        hint = load_hint(preset or "", category or "")
        if hint:
            if json_out:
                console.print_json(json.dumps(hint))
            else:
                console.print(f"[bold]{preset or '?'}:{category or '?'}[/bold]")
                console.print(f"  flavor: {hint.get('flavor')}")
                console.print(f"  line_scale: {hint.get('line_scale')}")
                console.print(f"  edge_tol: {hint.get('edge_tol')}")
                console.print(f"  fragmentation: {hint.get('fragmentation_score')}")
                console.print(f"  cells: {hint.get('cell_count')}")
                console.print(f"  confidence: {hint.get('confidence')}")
                console.print(f"  pdf: {hint.get('pdf_tested')}")
                console.print(f"  tuned: {hint.get('tuned_at')}")
        else:
            console.print("[dim]No hint found for this preset/category.[/dim]")
        return

    hints = list_hints()
    if json_out:
        console.print_json(json.dumps({"hints": hints}))
        return

    if not hints:
        console.print("[dim]No hints stored yet. Run 'tune' on a PDF first.[/dim]")
        return

    t = Table(title="Stored Hints")
    t.add_column("Preset", style="bold")
    t.add_column("Category")
    t.add_column("Flavor")
    t.add_column("Params")
    t.add_column("Frag", justify="right")
    t.add_column("Cells", justify="right")
    t.add_column("Confidence")
    t.add_column("PDF", max_width=30)

    for h in hints:
        params = []
        if h.get("line_scale") is not None:
            params.append(f"ls={h['line_scale']}")
        if h.get("edge_tol") is not None:
            params.append(f"et={h['edge_tol']}")
        t.add_row(
            h.get("preset", "—"),
            h.get("category", "—"),
            h.get("flavor", "—"),
            ", ".join(params) or "—",
            str(h.get("fragmentation_score", "—")),
            str(h.get("cell_count", "—")),
            h.get("confidence", "—"),
            h.get("pdf_tested", "—"),
        )
    console.print(t)


@app.command()
def apply(
    preset: Optional[str] = typer.Option(None, "--preset", help="Preset to export"),
    category: Optional[str] = typer.Option(None, "--category", help="Category to export"),
    to_corpus: bool = typer.Option(False, "--to-corpus", help="Write to corpus metadata"),
    json_out: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Export hints to corpus metadata for S05 pickup."""
    if to_corpus:
        path = export_to_corpus()
        if json_out:
            console.print_json(json.dumps({"exported_to": str(path)}))
        else:
            console.print(f"[green]Exported hints to {path}[/green]")
    else:
        console.print("[yellow]Use --to-corpus to write to corpus metadata.[/yellow]")
        console.print(f"[dim]Target: {CORPUS_HINTS_PATH}[/dim]")


@app.command("tune-corpus")
def tune_corpus_cmd(
    corpus_dir: Path = typer.Argument(..., help="Corpus directory to scan"),
    task_name: str = typer.Option("corpus_tune", "--task-name", help="Name for checkpoint/monitor"),
    glob_pattern: str = typer.Option("**/*_clean.pdf", "--glob", help="Glob pattern for PDFs"),
    max_iterations: int = typer.Option(3, "--max-iterations", help="Max convergence iterations per PDF"),
    json_stream: bool = typer.Option(False, "--json-stream", help="NDJSON output per PDF"),
    no_resume: bool = typer.Option(False, "--no-resume", help="Start fresh, ignore checkpoint"),
    json_out: bool = typer.Option(False, "--json", help="JSON summary output"),
) -> None:
    """Batch tune all PDFs in a corpus with watchdog monitoring."""
    if not corpus_dir.exists():
        console.print(f"[red]Directory not found: {corpus_dir}[/red]")
        raise typer.Exit(1)

    from .corpus import tune_corpus

    summary = tune_corpus(
        corpus_dir=corpus_dir,
        task_name=task_name,
        glob_pattern=glob_pattern,
        max_iterations=max_iterations,
        json_stream=json_stream,
        resume=not no_resume,
    )

    if json_out:
        console.print_json(json.dumps(summary, default=str))
    else:
        wd = summary.get("watchdog", {})
        console.print(f"\n[bold]Batch Tune Summary[/bold]")
        console.print(f"  Completed: {summary.get('completed_count', 0)}/{summary.get('total_pdfs', 0)}")
        console.print(f"  Skipped (checkpoint): {summary.get('skipped', 0)}")
        console.print(f"  Frag rate: {wd.get('fragmentation_rate', 0):.1%}")
        console.print(f"  Tables found: {wd.get('total_tables', 0)}")
        console.print(f"  Warnings: {wd.get('warnings_count', 0)}")
        if wd.get("stopped"):
            console.print(f"  [red]Stopped: {wd.get('stop_reason')}[/red]")
        console.print(f"  Results: {summary.get('results_file', 'N/A')}")


@app.command("tune-merge")
def tune_merge_cmd(
    pdf: Path = typer.Argument(..., help="Path to PDF file"),
    profile_dir: Optional[Path] = typer.Option(None, "--profile-dir", help="Pipeline output dir with S05/S05b"),
    tables_json: Optional[Path] = typer.Option(None, "--tables-json", help="Path to pre-merge tables JSON"),
    label_mode: bool = typer.Option(False, "--label", help="Interactive labeling mode (terminal)"),
    visual_mode: bool = typer.Option(False, "--visual", help="Visual labeling via /interview HTML panes"),
    json_out: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Diagnose cross-page merge decisions and collect human labels."""
    if not pdf.exists():
        console.print(f"[red]File not found: {pdf}[/red]")
        raise typer.Exit(1)

    from .merge_tuner import diagnose_merges, record_human_label, corrections_count, should_retrain

    diagnoses = diagnose_merges(pdf, tables_json=tables_json, profile_dir=profile_dir)

    if not diagnoses:
        console.print("[dim]No cross-page table pairs found.[/dim]")
        return

    if json_out:
        console.print_json(json.dumps([d.to_dict() for d in diagnoses], indent=2))
        return

    # Display diagnosis table
    t = Table(title=f"Merge Diagnosis: {pdf.name}")
    t.add_column("#", justify="right")
    t.add_column("Pages")
    t.add_column("Heuristic")
    t.add_column("Classifier")
    t.add_column("Conf", justify="right")
    t.add_column("Model")
    t.add_column("Disagree")

    for d in diagnoses:
        heur = "[green]MERGE[/green]" if d.heuristic_merge else "[red]SEPARATE[/red]"
        if d.classifier_merge is None:
            cls_str = "[dim]n/a[/dim]"
        elif d.classifier_merge:
            cls_str = "[green]MERGE[/green]"
        else:
            cls_str = "[red]SEPARATE[/red]"

        disagree = "[bold yellow]YES[/bold yellow]" if d.disagreement else ""

        t.add_row(
            str(d.pair_index),
            f"P{d.page_n+1}→P{d.page_n1+1}",
            heur,
            cls_str,
            f"{d.classifier_confidence:.2f}" if d.classifier_merge is not None else "—",
            d.classifier_model,
            disagree,
        )
    console.print(t)

    # Summary
    n_disagree = sum(1 for d in diagnoses if d.disagreement)
    console.print(f"\n{len(diagnoses)} pairs, {n_disagree} disagreement(s)")

    n_corrections = corrections_count()
    console.print(f"[dim]Human corrections on file: {n_corrections} (retrain at 50)[/dim]")

    # Visual labeling via /interview HTML panes
    if visual_mode:
        from .merge_tuner import run_visual_labeling
        console.print("\n[bold]Launching visual labeling in browser...[/bold]")
        n_labeled = run_visual_labeling(diagnoses, pdf)
        console.print(f"[green]Recorded {n_labeled} label(s)[/green]")
        if should_retrain():
            console.print("\n[bold yellow]Retrain threshold reached! Run classifier-lab retrain.[/bold yellow]")
        return

    # Terminal labeling mode
    if label_mode and n_disagree > 0:
        console.print("\n[bold]Label disagreements:[/bold]")
        for d in diagnoses:
            if not d.disagreement:
                continue
            console.print(f"\n  Pair #{d.pair_index}: P{d.page_n+1}→P{d.page_n1+1}")
            console.print(f"    Heuristic: {'MERGE' if d.heuristic_merge else 'SEPARATE'}")
            console.print(f"    Classifier: {'MERGE' if d.classifier_merge else 'SEPARATE'} ({d.classifier_confidence:.2f})")
            choice = typer.prompt("  Your label (merge/separate/skip)", default="skip")
            if choice in ("merge", "separate"):
                record_human_label(d, choice, pdf_name=pdf.name)
                console.print(f"    [green]Recorded: {choice}[/green]")

        if should_retrain():
            console.print("\n[bold yellow]Retrain threshold reached! Run classifier-lab retrain.[/bold yellow]")


@app.command("watchdog")
def watchdog_cmd(
    task_name: str = typer.Option("corpus_tune", "--task-name", help="Task name to check"),
    json_out: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Show checkpoint and watchdog status for a batch task."""
    cp_path = CHECKPOINT_DIR / f"{task_name}.json"
    if not cp_path.exists():
        console.print(f"[dim]No checkpoint found for task '{task_name}'[/dim]")
        raise typer.Exit(0)

    data = json.loads(cp_path.read_text())

    if json_out:
        console.print_json(json.dumps(data))
    else:
        console.print(f"[bold]Task: {data.get('task_name')}[/bold]")
        console.print(f"  Completed: {data.get('completed_count', 0)}/{data.get('total_pdfs', 0)}")
        console.print(f"  Created: {data.get('created_at', 'unknown')}")
        console.print(f"  Updated: {data.get('updated_at', 'unknown')}")
        metrics = data.get("metrics_snapshot", {})
        if metrics:
            console.print(f"  Metrics: {json.dumps(metrics, indent=2)}")


# Allow `python -m table_lab.cli <command>`
if __name__ == "__main__":
    app()
