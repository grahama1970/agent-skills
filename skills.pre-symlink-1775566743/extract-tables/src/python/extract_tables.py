#!/usr/bin/env python3
"""extract-tables: Native PDF table extraction.

Hybrid Rust + compiled-Python architecture. Shadow-LEGO self-correcting
strategy routing via /assistant classify.

Usage:
    from extract_tables import read_pdf
    tables = read_pdf("document.pdf", pages="1", flavor="lattice")
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import typer
from loguru import logger

from .strategy_router import select_strategy, get_fallback, remember_strategy
from .shadow_logger import log_extraction
from .models import ExtractionResult, Table

# Quarantine reasons
_QUARANTINE_REASONS = {
    "password": "password_required",
    "corrupt": "corrupt_pdf",
    "low_accuracy": "low_accuracy",
}


def _try_quarantine(pdf_path: str, reason: str, detail: str) -> None:
    """Best-effort quarantine a PDF for human review via /interview."""
    try:
        import sys
        _ld_dir = str(Path(__file__).resolve().parent.parent.parent.parent.parent / "learn-datalake")
        if _ld_dir not in sys.path:
            sys.path.insert(0, _ld_dir)
        from pdf_discovery import defer_pdf
        defer_pdf(Path(pdf_path), reason=reason, detail=detail)
    except Exception:
        pass  # Quarantine is best-effort; extraction continues

SKILL_DIR = Path(__file__).resolve().parent.parent.parent


def _parse_page_range(pages: str, total_pages: int) -> list[int]:
    """Parse page range string into 0-indexed page indices.

    Examples:
        "1" -> [0]
        "1,3,5" -> [0, 2, 4]
        "1-5" -> [0, 1, 2, 3, 4]
        "all" -> [0, 1, ..., total_pages-1]
        "1-end" -> [0, 1, ..., total_pages-1]
        "2-end" -> [1, 2, ..., total_pages-1]
    """
    pages = pages.strip()
    if pages.lower() == "all":
        return list(range(total_pages))

    result: list[int] = []
    for part in pages.split(","):
        part = part.strip()
        if "-" in part:
            start_str, end_str = part.split("-", 1)
            start = int(start_str.strip())
            if end_str.strip().lower() == "end":
                end = total_pages
            else:
                end = int(end_str.strip())
            for p in range(start, end + 1):
                idx = p - 1  # Convert to 0-indexed
                if 0 <= idx < total_pages:
                    result.append(idx)
        else:
            idx = int(part) - 1
            if 0 <= idx < total_pages:
                result.append(idx)

    return sorted(set(result))


def _is_phantom_table(table: "Table") -> bool:
    """Detect tables that are likely text blocks misdetected as tables.

    Characteristics of phantom tables:
    - Very high row count with only 2-3 columns — full-page text
    - Low accuracy combined with high row count
    - High-accuracy tables are never phantom (genuine large tables exist)
    """
    rows, cols = table.rows, table.cols
    acc = table.accuracy

    # High-accuracy tables are never phantom
    if acc >= 85:
        return False

    # 2-3 column tables with >50 rows and mediocre accuracy are text blocks
    if cols <= 3 and rows > 50 and acc < 85:
        return True

    # Tables with >30 rows, few columns, and low accuracy
    if cols <= 3 and rows > 30 and acc < 55:
        return True

    return False


def _get_parser(strategy: str):
    """Instantiate the parser for the given strategy name."""
    from .parsers.lattice import LatticeParser
    from .parsers.stream import StreamParser
    from .parsers.network import NetworkParser
    from .parsers.hybrid import HybridParser

    parsers = {
        "lattice": LatticeParser,
        "stream": StreamParser,
        "network": NetworkParser,
        "hybrid": HybridParser,
    }
    cls = parsers.get(strategy)
    if cls is None:
        raise ValueError(f"Unknown strategy: {strategy!r}. Valid: {list(parsers)}")
    return cls()


def read_pdf(
    filepath: str,
    pages: str = "1",
    flavor: str = "auto",
    password: str | None = None,
    suppress_stdout: bool = False,
    parallel: bool = False,
    layout_kwargs: dict[str, Any] | None = None,
    **kwargs,
) -> ExtractionResult:
    """Extract tables from a PDF file.

    Drop-in replacement for camelot.io.read_pdf(). When flavor="auto",
    uses Shadow-LEGO strategy routing to pick the best parser.

    Parameters
    ----------
    filepath : str
        Path or URL to PDF file.
    pages : str
        Comma-separated page numbers. Example: '1,3,4' or '1,4-end' or 'all'.
    flavor : str
        Parser flavor: 'lattice', 'stream', 'network', 'hybrid', or 'auto'.
    password : str, optional
        PDF password for decryption.
    suppress_stdout : bool
        Suppress parser output.
    parallel : bool
        Process pages in parallel (not yet implemented).
    layout_kwargs : dict, optional
        pdfminer LAParams kwargs (unused in native pipeline).
    **kwargs
        Additional parser-specific parameters.

    Returns
    -------
    ExtractionResult
        Result containing extracted tables, strategy history, etc.
    """
    start_time = time.monotonic()

    from .pdf_bridge import get_page_count, extract_text_elements, get_page_dimensions
    from .metrics import compute_accuracy
    from .title_extractor import extract_title_from_context, batch_infer_titles
    from .merger import merge_split_tables

    # Get total page count — quarantine on failure
    try:
        total_pages = get_page_count(filepath)
    except Exception as e:
        err_msg = str(e).lower()
        if "password" in err_msg or "encrypted" in err_msg:
            _try_quarantine(filepath, "password_required",
                            f"PDF requires password: {e}")
        elif "corrupt" in err_msg or "invalid" in err_msg:
            _try_quarantine(filepath, "corrupt_pdf",
                            f"PDF appears corrupt: {e}")
        raise
    page_indices = _parse_page_range(pages, total_pages)

    all_tables: list[Table] = []
    strategy_history: list[dict] = []

    # Multi-page learning: track which strategy+config actually works
    # within this PDF to avoid re-probing and re-falling-back on every page.
    auto_chosen: str | None = None
    auto_confidence: float = 0.0
    cached_lattice_params: dict[str, Any] | None = None
    # Track the strategy that actually wins (after fallback) to try it
    # first on subsequent pages.
    winning_strategy: str | None = None
    win_count: int = 0

    for page_idx in page_indices:
        page_start = time.monotonic()

        # Select strategy: use winning strategy from prior pages if known
        if flavor == "auto":
            if winning_strategy and win_count >= 2:
                # After 2+ pages won by the same strategy, trust it
                chosen, confidence = winning_strategy, 0.85
            elif auto_chosen is not None:
                chosen, confidence = auto_chosen, auto_confidence
            else:
                chosen, confidence = select_strategy(filepath, page_idx, **kwargs)
                if len(page_indices) > 1:
                    auto_chosen = chosen
                    auto_confidence = confidence
        else:
            chosen = flavor
            confidence = 1.0

        # Extract tables. Pass cached lattice config to skip the
        # 3-config probe on subsequent lattice pages (~3x speedup).
        parser = _get_parser(chosen)
        extract_kwargs: dict[str, Any] = {"password": password}
        if cached_lattice_params and chosen in ("lattice", "hybrid"):
            extract_kwargs.update(cached_lattice_params)
        tables = parser.extract_tables(filepath, page_idx, **extract_kwargs)

        # Cache the lattice probe config after first extraction.
        # Even if no tables found, cache the default config to skip
        # re-probing on subsequent pages.
        if (
            cached_lattice_params is None
            and chosen in ("lattice", "hybrid")
            and hasattr(parser, "_last_probe_results")
            and parser._last_probe_results
        ):
            viable = [p for p in parser._last_probe_results if p.table_count > 0]
            if viable:
                def _probe_score(p):
                    return (
                        not p.has_spurious,
                        p.total_joints,
                        p.max_grid_area,
                        -p.table_count if p.table_count > 10 else 0,
                    )
                best = max(viable, key=_probe_score)
                cached_lattice_params = {
                    "line_scale": best.line_scale,
                    "threshold_blocksize": best.threshold_blocksize,
                    "threshold_constant": best.threshold_constant,
                }
            else:
                # No tables found by any config — use default to skip probing
                cached_lattice_params = {
                    "line_scale": 15,
                    "threshold_blocksize": 15,
                    "threshold_constant": -2,
                }

        # Compute accuracy for each table
        for table in tables:
            table.accuracy = compute_accuracy(table)

        # Filter phantom tables (text blocks misdetected as tables)
        tables = [t for t in tables if not _is_phantom_table(t)]

        # Self-correction: retry with fallback only if accuracy is poor
        avg_accuracy = (
            sum(t.accuracy for t in tables) / len(tables) if tables else 0
        )
        # Only try fallbacks when primary found no tables or accuracy is
        # very poor (<50%). Max 1 fallback attempt per page.
        if not tables or (avg_accuracy < 50 and tables):
            best_tables = tables
            best_name = chosen
            best_avg = avg_accuracy

            fallback_list = get_fallback(chosen)
            if chosen == "lattice" and tables and avg_accuracy >= 50:
                fallback_list = [f for f in fallback_list if f != "network"]
            fallback_list = fallback_list[:1]

            for fallback_name in fallback_list:
                try:
                    alt_parser = _get_parser(fallback_name)
                    fb_kwargs: dict[str, Any] = {"password": password}
                    if cached_lattice_params and fallback_name in ("lattice", "hybrid"):
                        fb_kwargs.update(cached_lattice_params)
                    alt_tables = alt_parser.extract_tables(
                        filepath, page_idx, **fb_kwargs
                    )
                    for t in alt_tables:
                        t.accuracy = compute_accuracy(t)
                    # Filter phantoms from fallback too
                    alt_tables = [t for t in alt_tables if not _is_phantom_table(t)]
                    alt_avg = (
                        sum(t.accuracy for t in alt_tables) / len(alt_tables)
                        if alt_tables
                        else 0
                    )
                    # Only accept fallback if it meets minimum quality bar
                    # (prevents phantom tables from pages with no real tables)
                    if alt_avg < 50:
                        continue
                    if (alt_tables and not best_tables) or alt_avg > best_avg + 10:
                        best_tables = alt_tables
                        best_name = fallback_name
                        best_avg = alt_avg
                    if best_avg >= 70:
                        break
                except Exception:
                    continue
            tables = best_tables
            chosen = best_name
            avg_accuracy = best_avg

        # Track winning strategy across pages for multi-page learning
        if tables:
            if chosen == winning_strategy:
                win_count += 1
            else:
                winning_strategy = chosen
                win_count = 1

        # Remember which strategy worked best for this PDF domain
        if avg_accuracy >= 70:
            remember_strategy(filepath, chosen, avg_accuracy)

        # Set page info and strategy on all tables
        for t in tables:
            t.page_index = page_idx
            t.page_number = page_idx + 1
            if not t.strategy:
                t.strategy = chosen

        # Title extraction: search for title + store bbox in fitz coords
        try:
            from .section_detector import find_table_title, detect_headers_on_page
            for t in tables:
                if t.title is None and t.bbox != (0.0, 0.0, 0.0, 0.0):
                    title_text, title_bbox = find_table_title(
                        filepath, page_idx, t.bbox, password=password
                    )
                    if title_text:
                        t.title = title_text
                        t.title_bbox = title_bbox

            # Assign section_id from nearest header above each table
            headers = detect_headers_on_page(filepath, page_idx, password=password)
            if headers:
                for t in tables:
                    if t.bbox == (0.0, 0.0, 0.0, 0.0):
                        continue
                    # Find closest header above this table
                    best = None
                    for h in headers:
                        if h.bbox[3] <= t.bbox[1]:  # header bottom above table top
                            if best is None or h.bbox[1] > best.bbox[1]:
                                best = h
                    if best:
                        t.section_id = best.text
        except Exception:
            # Section/title detection is best-effort; fall back to text heuristic
            try:
                text_elements = extract_text_elements(filepath, page_idx, password=password)
                page_dims = get_page_dimensions(filepath, page_idx)
                for t in tables:
                    if t.title is None and t.bbox != (0.0, 0.0, 0.0, 0.0):
                        t.title = extract_title_from_context(
                            text_elements, t.bbox, page_dims
                        )
            except Exception:
                pass

        page_elapsed = time.monotonic() - page_start
        strategy_history.append({
            "page": page_idx,
            "strategy": chosen,
            "tables": len(tables),
            "accuracy": avg_accuracy,
            "elapsed_s": round(page_elapsed, 3),
        })
        all_tables.extend(tables)

    # Cross-page merging: detect tables split across page breaks
    all_tables = merge_split_tables(all_tables, pdf_path=filepath, password=password)

    # Post-merge phantom filter: merging may create oversized tables
    all_tables = [t for t in all_tables if not _is_phantom_table(t)]

    # VLM batch title inference for tables without titles (graceful if unavailable)
    try:
        all_tables = batch_infer_titles(all_tables)
    except Exception:
        pass  # VLM is optional

    elapsed = time.monotonic() - start_time

    # Quarantine PDFs with consistently low accuracy across all pages
    overall_accuracy = (
        sum(t.accuracy for t in all_tables) / len(all_tables)
        if all_tables
        else 0
    )
    if all_tables and overall_accuracy < 30:
        _try_quarantine(
            filepath, "low_accuracy",
            f"All {len(all_tables)} tables have avg accuracy {overall_accuracy:.1f}%. "
            f"Pages: {pages}. May need manual review or different strategy."
        )

    # Shadow logging
    log_extraction(
        filepath=filepath,
        pages=pages,
        flavor=strategy_history[0]["strategy"] if strategy_history else flavor,
        confidence=confidence if strategy_history else 0.0,
        num_tables=len(all_tables),
        accuracy=overall_accuracy,
        elapsed_seconds=elapsed,
    )

    return ExtractionResult(
        tables=all_tables,
        pages_processed=len(page_indices),
        elapsed=elapsed,
        strategy_history=strategy_history,
    )


# -- CLI ---------------------------------------------------------------

cli = typer.Typer(help="extract-tables: PDF table extraction.")


@cli.command()
def extract(
    pdf_path: str = typer.Argument(..., help="Path to PDF file"),
    pages: str = typer.Option("1", help="Pages to extract (e.g., '1', 'all', '1-end')"),
    flavor: str = typer.Option("auto", "--strategy", help="Strategy: lattice, stream, network, hybrid, auto"),
    output: str = typer.Option("json", help="Output format: json, csv, markdown"),
    line_scale: int = typer.Option(15, help="Line scale for lattice parser"),
):
    """Extract tables from a PDF."""
    kwargs = {}
    if flavor in ("lattice", "auto"):
        kwargs["line_scale"] = line_scale

    result = read_pdf(pdf_path, pages=pages, flavor=flavor, **kwargs)

    typer.echo(f"Found {len(result)} table(s)")
    for i, table in enumerate(result.tables):
        typer.echo(
            f"  Table {i+1}: rows={table.rows} cols={table.cols} "
            f"accuracy={table.accuracy}"
        )

        if output == "json":
            typer.echo(table.to_json())
        elif output == "csv":
            typer.echo(table.to_csv())


@cli.command()
def batch(
    pdf_dir: str = typer.Argument(..., help="Directory of PDF files"),
    output_dir: str = typer.Option(".", help="Output directory"),
    flavor: str = typer.Option("auto", "--strategy"),
):
    """Batch extract from a directory of PDFs."""
    pdf_dir_p = Path(pdf_dir)
    output_dir_p = Path(output_dir)
    output_dir_p.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(pdf_dir_p.glob("*.pdf"))
    typer.echo(f"Processing {len(pdfs)} PDFs...")

    for pdf in pdfs:
        try:
            result = read_pdf(str(pdf), pages="all", flavor=flavor)
            out_file = output_dir_p / f"{pdf.stem}_tables.json"
            results_data = []
            for t in result.tables:
                results_data.append({
                    "page": t.page_number,
                    "accuracy": t.accuracy,
                    "rows": t.rows,
                    "cols": t.cols,
                    "data": t._data,
                })
            out_file.write_text(json.dumps(results_data, indent=2))
            typer.echo(f"  {pdf.name}: {len(result)} tables -> {out_file.name}")
        except Exception as e:
            logger.error(f"{pdf.name}: {e}")
            typer.echo(f"  {pdf.name}: ERROR - {e}", err=True)


@cli.command("review-quarantine")
def review_quarantine():
    """List PDFs quarantined for human review."""
    try:
        _ld_dir = str(Path(__file__).resolve().parent.parent.parent.parent.parent / "learn-datalake")
        if _ld_dir not in sys.path:
            sys.path.insert(0, _ld_dir)
        from pdf_discovery import load_deferred_with_questions, load_deferred
    except ImportError:
        typer.echo("learn-datalake skill not found", err=True)
        raise typer.Exit(code=1)

    # Show all deferred PDFs
    deferred = load_deferred()
    with_questions = load_deferred_with_questions()

    typer.echo(f"Quarantined PDFs: {len(deferred)} total, {len(with_questions)} with questions\n")

    for entry in with_questions:
        typer.echo(f"  {entry['stem']}")
        typer.echo(f"    Reason: {entry.get('reason', 'unknown')}")
        typer.echo(f"    Detail: {entry.get('detail', '')[:100]}")
        typer.echo(f"    Questions: {len(entry.get('questions', []))}")
        if entry.get("screenshot_paths"):
            typer.echo(f"    Screenshots: {len(entry['screenshot_paths'])}")
        typer.echo()


@cli.command("train-classifier")
def train_classifier_cmd(
    stats: bool = typer.Option(False, "--stats", is_flag=True, help="Print stats only, don't train"),
):
    """Train strategy classifier from shadow logs."""
    from .train_strategy_classifier import load_shadow_data, compute_stats, prepare_training_data, train_classifier

    entries = load_shadow_data()
    if not entries:
        typer.echo("No training data found.")
        return

    s = compute_stats(entries)
    typer.echo(f"Training data: {s['total_entries']} entries, {s['unique_files']} files")
    typer.echo(f"Strategy distribution: {s['strategy_distribution']}")
    typer.echo(f"Agreement rate: {s['agreement_rate']}%")
    typer.echo(f"Avg accuracy: {s['avg_accuracy']}%")

    if stats:
        return

    X, y, feature_names = prepare_training_data(entries)
    if len(X) < 10:
        typer.echo(f"Insufficient data: {len(X)} samples (need >= 10)")
        return

    typer.echo(f"\nTraining on {len(X)} samples...")
    train_classifier(X, y, feature_names)
    typer.echo("Done.")


if __name__ == "__main__":
    cli()
