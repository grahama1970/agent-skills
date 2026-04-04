"""CLI entry point for /extract-pdf skill.

Uses Typer per best-practices-python. Delegates to pdf_oxide for all
Rust-native extraction; this file is the thin Python orchestrator.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

app = typer.Typer(
    name="extract-pdf",
    help="Rust-native PDF extraction via pdf_oxide.",
    no_args_is_help=True,
)


def _get_doc(pdf_path: str):
    """Import and instantiate PdfDocument (lazy to avoid import cost on --help)."""
    from pdf_oxide import PdfDocument

    return PdfDocument(pdf_path)


def _log_cascade_decisions(doc, path: Path) -> dict:
    """Run predict_extraction and log all cascade decision points.

    Returns a summary dict included in the output envelope. Failures
    are swallowed — cascade logging must never break extraction.
    """
    try:
        from extract_pdf.cascade import log_extraction_decisions, log_header_decisions

        prediction = doc.predict_extraction()
        summary = log_extraction_decisions(prediction, source_pdf=str(path))

        # Log header-level decisions (classify_blocks with disposition)
        page_count = doc.page_count()
        header_counts = log_header_decisions(doc, page_count, source_pdf=str(path))
        summary["header_counts"] = header_counts

        logger.debug(f"[cascade] Shadow logged: {summary}")
        return summary
    except Exception as e:
        logger.debug(f"[cascade] Shadow logging skipped: {e}")
        return {"error": str(e)}


@app.command()
def extract(
    pdf_path: str = typer.Argument(..., help="Path to PDF file"),
    output_dir: Optional[str] = typer.Option(None, help="Output directory for JSON"),
    features: Optional[str] = typer.Option(
        None, help="Comma-separated plugin features (arango,describe)"
    ),
    enrich_profile: bool = typer.Option(
        True, help="Include Rust profile fields in output"
    ),
) -> None:
    """Full extraction pipeline: profile + blocks + sections + tables + figures."""
    t0 = time.monotonic()
    path = Path(pdf_path)
    if not path.exists():
        logger.error(f"File not found: {pdf_path}")
        raise typer.Exit(code=1)

    logger.info(f"Extracting: {path.name}")
    doc = _get_doc(str(path))

    # Full Rust extraction pipeline
    result = doc.extract_document()
    elapsed = time.monotonic() - t0
    logger.info(
        f"Extracted in {elapsed:.2f}s: "
        f"{len(result.get('blocks', []))} blocks, "
        f"{len(result.get('sections', []))} sections"
    )

    # Shadow-LEGO cascade: log all decisions for classifier training
    cascade_summary = _log_cascade_decisions(doc, path)

    # Build output envelope
    envelope = {
        "version": "1.0",
        "engine": "pdf_oxide",
        "source_pdf": str(path),
        "page_count": doc.page_count(),
        **result,
        "timings": {"extraction_s": elapsed},
        "cascade": cascade_summary,
    }

    # Write or print
    if output_dir:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        out_path = out / f"{path.stem}.json"
        out_path.write_text(
            json.dumps(envelope, indent=2, ensure_ascii=False, default=str)
        )
        logger.info(f"Output: {out_path}")
    else:
        typer.echo(json.dumps(envelope, indent=2, ensure_ascii=False, default=str))


@app.command()
def survey(
    pdf_path: str = typer.Argument(..., help="Path to PDF file"),
    enrich_profile: bool = typer.Option(
        True, "--enrich-profile/--no-enrich-profile",
        help="Include Rust profile fields",
    ),
) -> None:
    """Lightweight page-by-page survey (profiling without full extraction)."""
    path = Path(pdf_path)
    if not path.exists():
        logger.error(f"File not found: {pdf_path}")
        raise typer.Exit(code=1)

    from pdf_oxide.survey import survey_document

    doc = _get_doc(str(path))
    result = survey_document(doc, enrich_profile=enrich_profile)
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False, default=str))


@app.command()
def text(
    pdf_path: str = typer.Argument(..., help="Path to PDF file"),
    page: Optional[int] = typer.Option(None, help="Specific page (0-indexed)"),
) -> None:
    """Raw text extraction only (fast, no pipeline)."""
    path = Path(pdf_path)
    if not path.exists():
        logger.error(f"File not found: {pdf_path}")
        raise typer.Exit(code=1)

    doc = _get_doc(str(path))
    if page is not None:
        typer.echo(doc.extract_text(page))
    else:
        for i in range(doc.page_count()):
            typer.echo(doc.extract_text(i))


@app.command()
def batch(
    dir_path: str = typer.Argument(..., help="Directory of PDF files"),
    output_dir: str = typer.Option("./results", help="Output directory"),
    workers: int = typer.Option(1, help="Parallel workers (future use)"),
) -> None:
    """Batch extraction across a directory of PDFs."""
    src = Path(dir_path)
    if not src.is_dir():
        logger.error(f"Not a directory: {dir_path}")
        raise typer.Exit(code=1)

    pdfs = sorted(src.glob("*.pdf"))
    if not pdfs:
        logger.warning(f"No PDFs found in {dir_path}")
        raise typer.Exit(code=0)

    logger.info(f"Batch: {len(pdfs)} PDFs -> {output_dir}")
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    success = 0
    errors = 0
    for pdf in pdfs:
        try:
            doc = _get_doc(str(pdf))
            result = doc.extract_document()

            # Shadow-LEGO cascade logging
            cascade_summary = _log_cascade_decisions(doc, pdf)

            envelope = {
                "version": "1.0",
                "engine": "pdf_oxide",
                "source_pdf": str(pdf),
                "page_count": doc.page_count(),
                **result,
                "cascade": cascade_summary,
            }
            out_path = out / f"{pdf.stem}.json"
            out_path.write_text(
                json.dumps(envelope, indent=2, ensure_ascii=False, default=str)
            )
            success += 1
        except Exception as e:
            logger.error(f"Failed: {pdf.name}: {e}")
            errors += 1

    logger.info(f"Batch complete: {success} ok, {errors} errors")


@app.command()
def profile(
    pdf_path: str = typer.Argument(..., help="Path to PDF file"),
) -> None:
    """Document profiling only (domain, preset, complexity, is_scanned)."""
    path = Path(pdf_path)
    if not path.exists():
        logger.error(f"File not found: {pdf_path}")
        raise typer.Exit(code=1)

    doc = _get_doc(str(path))
    result = doc.profile_document()
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False, default=str))


@app.command()
def pipeline(
    pdf_path: str = typer.Argument(..., help="Path to PDF file"),
    output_dir: str = typer.Option(..., "--output-dir", help="Pipeline output directory"),
) -> None:
    """Write extractor-compatible pipeline output (replaces S00-S06).

    Produces the same directory structure as run_pipeline.py so downstream
    stages (S05 tables, S05b/c, S06b VLM, S07+) work unchanged.
    """
    path = Path(pdf_path)
    if not path.exists():
        logger.error(f"File not found: {pdf_path}")
        raise typer.Exit(code=1)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    from extract_pdf.pipeline_adapter import run_pipeline_adapter

    t0 = time.monotonic()
    s02_path = run_pipeline_adapter(path, out)
    elapsed = time.monotonic() - t0

    logger.info(f"Pipeline output in {elapsed:.2f}s: {out}")
    typer.echo(json.dumps({"s02_path": s02_path, "output_dir": str(out)}, indent=2))


if __name__ == "__main__":
    app()
