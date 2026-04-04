"""Iterative tuning loop: sweep parameter grid and find best settings.

The tuner provides the systematic sweep. The agent can also call
probe.probe_page() directly to try arbitrary values outside the grid.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from loguru import logger
from rich.console import Console
from rich.table import Table

from .config import BACKEND, LATTICE_LINE_SCALES, STREAM_EDGE_TOLS, USE_CLASSIFIER_BASELINE
from .evaluate import is_good_enough, score_result
from .memory_client import get_baseline_from_memory, learn_parameters
from .probe import ProbeResult, probe_page, probe_page_rust
from .sampler import find_pages_with_tables

# Classifier integration (optional, provides 95%+ accuracy predictions)
try:
    from .classifier import get_classifier_grid_recommendation
    CLASSIFIER_AVAILABLE = True
except ImportError:
    CLASSIFIER_AVAILABLE = False
    def get_classifier_grid_recommendation(*args, **kwargs):
        return LATTICE_LINE_SCALES, STREAM_EDGE_TOLS, "lattice_first"

console = Console()


@dataclass
class TuneResult:
    """Result of a full tuning sweep."""
    pdf_path: str
    best_flavor: str = ""
    best_line_scale: int | None = None
    best_edge_tol: int | None = None
    best_score: float = -1.0
    best_fragmentation: int = 0
    best_cell_count: int = 0
    pages_tested: list[int] = field(default_factory=list)
    all_results: list[dict] = field(default_factory=list)
    tuned_at: str = ""
    early_stop: bool = False

    def to_hint(self, preset: str = "", category: str = "", s05_key: str = "",
                 bridge_tags: list[str] | None = None) -> dict:
        """Convert to hint file format."""
        return {
            "preset": preset,
            "category": category,
            "flavor": self.best_flavor,
            "line_scale": self.best_line_scale,
            "edge_tol": self.best_edge_tol,
            "process_background": False,
            "fragmentation_score": self.best_fragmentation,
            "cell_count": self.best_cell_count,
            "pages_tested": self.pages_tested,
            "confidence": "high" if self.best_fragmentation == 0 else "medium",
            "tuned_at": self.tuned_at,
            "pdf_tested": Path(self.pdf_path).name,
            "s05_key": s05_key,
            "bridge_tags": bridge_tags or [],
        }

    def to_ndjson_record(self, preset: str = "", category: str = "",
                         bridge_tags: list[str] | None = None,
                         iterations: int = 1, converged: bool = False) -> dict:
        """Convert to NDJSON record for corpus-report data contract."""
        return {
            "pdf_name": Path(self.pdf_path).name,
            "preset": preset,
            "category": category,
            "best_flavor": self.best_flavor,
            "best_line_scale": self.best_line_scale,
            "best_edge_tol": self.best_edge_tol,
            "best_score": round(self.best_score, 1),
            "fragmentation": self.best_fragmentation,
            "cell_count": self.best_cell_count,
            "bridge_tags": bridge_tags or [],
            "iterations": iterations,
            "converged": converged,
            "early_stop": self.early_stop,
            "tuned_at": self.tuned_at,
        }


def tune(
    pdf_path: Path | str,
    sample_pages: list[int] | None = None,
    lattice_scales: list[int] | None = None,
    stream_tols: list[int] | None = None,
    early_stop: bool = True,
    on_strategy_complete: Callable[[dict], None] | None = None,
    preset: str = "",
    category: str = "",
    auto_learn: bool = True,
    use_classifier: bool = True,
    backend: str = BACKEND,
) -> TuneResult:
    """Sweep parameter grid across sample pages and find optimal settings.

    AUTOMATIC INTEGRATION (in priority order):
    1. ML Classifier - 95%+ accuracy predictions narrow the search space
    2. Memory recall - queries /memory for previously learned parameters
    3. Default grids - systematic sweep of full parameter space

    Args:
        pdf_path: Path to the PDF.
        sample_pages: Specific pages to test (0-based). Auto-detected if None.
        lattice_scales: line_scale values to try. Uses classifier/memory/defaults if None.
        stream_tols: edge_tol values to try. Uses classifier/memory/defaults if None.
        early_stop: Stop as soon as a zero-fragmentation result is found.
        preset: S00 preset name for memory queries.
        category: Document category for memory queries.
        auto_learn: Automatically store successful results to /memory.
        use_classifier: Use ML classifier for initial grid narrowing (default True).

    Returns:
        TuneResult with the best parameters found.
    """
    pdf_path = Path(pdf_path)
    strategy_order = "lattice_first"  # Default

    # Priority 1: ML CLASSIFIER - narrow search space with 95%+ accuracy predictions
    classifier_lattice, classifier_stream = None, None
    if use_classifier and USE_CLASSIFIER_BASELINE and CLASSIFIER_AVAILABLE:
        if lattice_scales is None or stream_tols is None:
            classifier_lattice, classifier_stream, strategy_order = get_classifier_grid_recommendation(
                pdf_path, page_num=0, preset=preset
            )
            logger.info(f"Classifier suggests: {strategy_order}, grids: ls={classifier_lattice}, et={classifier_stream}")

    # Priority 2: MEMORY RECALL - query /memory for learned parameters
    memory_lattice, memory_stream = None, None
    if lattice_scales is None or stream_tols is None:
        memory_lattice, memory_stream = get_baseline_from_memory(preset=preset, category=category)

    # Merge sources: explicit > classifier > memory > defaults
    scales = lattice_scales or classifier_lattice or memory_lattice or LATTICE_LINE_SCALES
    tols = stream_tols or classifier_stream or memory_stream or STREAM_EDGE_TOLS

    # Select probe function based on backend
    _probe = probe_page_rust if backend == "rust" else probe_page

    # Find sample pages
    if sample_pages is None:
        sample_pages = find_pages_with_tables(pdf_path, backend=backend)
        if not sample_pages:
            logger.warning("No pages with tables detected")
            return TuneResult(pdf_path=str(pdf_path))

    logger.info(f"Testing {len(sample_pages)} pages: {[p+1 for p in sample_pages]}")

    result = TuneResult(
        pdf_path=str(pdf_path),
        pages_tested=sample_pages,
        tuned_at=datetime.now(timezone.utc).isoformat(),
    )

    best_overall: ProbeResult | None = None
    best_overall_score = -1.0

    def _run_lattice_phase():
        """Run lattice strategy sweep."""
        nonlocal best_overall, best_overall_score
        for ls in scales:
            page_results = []
            for page_num in sample_pages:
                pr = _probe(pdf_path, page_num, "lattice", line_scale=ls)
                page_results.append(pr)

            agg = _aggregate_results(page_results, "lattice", line_scale=ls)
            result.all_results.append(agg)
            if on_strategy_complete:
                on_strategy_complete(agg)

            avg_score = agg["avg_score"]
            if avg_score > best_overall_score:
                best_overall_score = avg_score
                best_overall = ProbeResult(
                    page_num=-1,
                    flavor="lattice",
                    line_scale=ls,
                    table_count=agg["total_tables"],
                    cell_count=agg["total_cells"],
                    fragmentation=agg["total_fragmentation"],
                    duration_ms=agg["total_duration_ms"],
                )

            if early_stop and agg["total_fragmentation"] == 0 and agg["total_tables"] > 0:
                logger.info(f"Early stop: lattice(ls={ls}) achieves zero fragmentation")
                result.early_stop = True
                return

    def _run_stream_phase():
        """Run stream strategy sweep."""
        nonlocal best_overall, best_overall_score
        for et in tols:
            page_results = []
            for page_num in sample_pages:
                pr = _probe(pdf_path, page_num, "stream", edge_tol=et)
                page_results.append(pr)

            agg = _aggregate_results(page_results, "stream", edge_tol=et)
            result.all_results.append(agg)
            if on_strategy_complete:
                on_strategy_complete(agg)

            avg_score = agg["avg_score"]
            if avg_score > best_overall_score:
                best_overall_score = avg_score
                best_overall = ProbeResult(
                    page_num=-1,
                    flavor="stream",
                    edge_tol=et,
                    table_count=agg["total_tables"],
                    cell_count=agg["total_cells"],
                    fragmentation=agg["total_fragmentation"],
                    duration_ms=agg["total_duration_ms"],
                )

            if early_stop and agg["total_fragmentation"] == 0 and agg["total_tables"] > 0:
                logger.info(f"Early stop: stream(et={et}) achieves zero fragmentation")
                result.early_stop = True
                return

    # Run phases in order suggested by classifier (default: lattice first)
    if strategy_order == "stream_first":
        logger.info("Classifier recommends stream-first strategy order")
        _run_stream_phase()
        if not result.early_stop:
            _run_lattice_phase()
    else:
        # Default: lattice first (better for structured tables)
        _run_lattice_phase()
        if not result.early_stop:
            _run_stream_phase()

    # Set best results
    if best_overall:
        result.best_flavor = best_overall.flavor
        result.best_line_scale = best_overall.line_scale
        result.best_edge_tol = best_overall.edge_tol
        result.best_score = best_overall_score
        result.best_fragmentation = best_overall.fragmentation
        result.best_cell_count = best_overall.cell_count

    # AUTOMATIC MEMORY LEARN - store successful results
    if auto_learn and result.best_fragmentation == 0 and result.best_cell_count > 0:
        bridge_tags = ["Precision", "Resilience"]
        learn_parameters(
            preset=preset or "unknown",
            category=category or "unknown",
            flavor=result.best_flavor,
            line_scale=result.best_line_scale,
            edge_tol=result.best_edge_tol,
            fragmentation=result.best_fragmentation,
            cell_count=result.best_cell_count,
            pdf_name=Path(pdf_path).name,
            bridge_tags=bridge_tags,
        )

    return result


def print_tune_results(result: TuneResult) -> None:
    """Display tuning results as a Rich table."""
    if not result.all_results:
        console.print("[dim]No results to display.[/dim]")
        return

    t = Table(title=f"Tuning Results: {Path(result.pdf_path).name}")
    t.add_column("Strategy", style="bold")
    t.add_column("Tables", justify="right")
    t.add_column("Cells", justify="right")
    t.add_column("Frag", justify="right")
    t.add_column("Score", justify="right")
    t.add_column("Time (ms)", justify="right", style="dim")
    t.add_column("Winner")

    for agg in result.all_results:
        is_best = (
            agg["flavor"] == result.best_flavor
            and agg.get("line_scale") == result.best_line_scale
            and agg.get("edge_tol") == result.best_edge_tol
        )
        frag_style = "green" if agg["total_fragmentation"] == 0 else "red"
        winner = "[green]<<<[/green]" if is_best else ""

        t.add_row(
            agg["label"],
            str(agg["total_tables"]),
            str(agg["total_cells"]),
            f"[{frag_style}]{agg['total_fragmentation']}[/{frag_style}]",
            f"{agg['avg_score']:.0f}",
            str(agg["total_duration_ms"]),
            winner,
        )

    console.print(t)

    if result.best_flavor:
        console.print(f"\n[bold green]Best:[/bold green] {result.best_flavor}"
                      f"(line_scale={result.best_line_scale}, edge_tol={result.best_edge_tol})"
                      f" | score={result.best_score:.0f}"
                      f" | frag={result.best_fragmentation}"
                      f" | cells={result.best_cell_count}")
        if result.early_stop:
            console.print("[dim]Stopped early: zero fragmentation achieved[/dim]")


def _aggregate_results(
    page_results: list[ProbeResult],
    flavor: str,
    line_scale: int | None = None,
    edge_tol: int | None = None,
) -> dict:
    """Aggregate probe results across multiple pages."""
    total_tables = sum(r.table_count for r in page_results)
    total_cells = sum(r.cell_count for r in page_results)
    total_frag = sum(r.fragmentation for r in page_results)
    total_ms = sum(r.duration_ms for r in page_results)
    scores = [score_result(r) for r in page_results]
    avg_score = sum(s for s in scores if s >= 0) / max(1, sum(1 for s in scores if s >= 0))

    if flavor == "lattice":
        label = f"lattice(ls={line_scale})"
    else:
        label = f"stream(et={edge_tol})"

    return {
        "label": label,
        "flavor": flavor,
        "line_scale": line_scale,
        "edge_tol": edge_tol,
        "total_tables": total_tables,
        "total_cells": total_cells,
        "total_fragmentation": total_frag,
        "total_duration_ms": total_ms,
        "avg_score": avg_score,
        "pages": len(page_results),
        "errors": sum(1 for r in page_results if r.error),
    }
