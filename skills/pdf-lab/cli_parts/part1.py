#!/usr/bin/env python3
"""pdf-lab — Self-improving PDF extraction convergence loop.

CLI entry point using Typer. Two output paths:
- Per-PDF parameter tuning: runtime params returned for immediate re-extraction
- Global pipeline fixes: bug fixes/missing patterns written to pipeline code

Usage:
    python pdf_lab.py tune <pdf> [options]
    python pdf_lab.py tune-gt <pdf> [options]
    python pdf_lab.py diagnose <pdf> [options]
    python pdf_lab.py compare <pdf> <ground_truth> [options]
    python pdf_lab.py synthetic [options]
    python pdf_lab.py verify-real <pdf> <fixture_dir> [options]
    python pdf_lab.py status
    python pdf_lab.py rollback --sha <sha>
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

import typer
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

# Add lib to path
sys.path.insert(0, str(Path(__file__).parent))

from lib.delta import (
    ExtractionDelta,
    ReviewContext,
    compute_delta_from_json,
    compute_delta_from_review,
    diagnose_delta,
)
from lib.synthetic import generate_synthetic
from lib.human import (
    load_question_book,
    build_batch_interview,
    run_batch_interview,
    save_answer_book,
    load_answer_book,
    clear_question_book,
    DEFAULT_BOOK_DIR,
)
from lib.compare import compare as run_compare
from lib.convergence import run_convergence, ConvergenceResult
from lib.tuner import tune as run_tune, TuneResult, PipelineHaltError
from lib.verify import verify_real as run_verify_real, VerifyResult
from lib.writer import EXTRACTOR_ROOT
from lib.forensic import (
    run_forensic_page,
    run_non_pdf_oxide_table_scan,
    run_pdf_oxide_element_scan,
    run_preset_scan,
    run_toc_scan,
)
from lib.agentic import (
    compare_expected_actual,
    run_agent_scan,
    run_agentic_extract,
    run_final_agent_pass,
    run_pdf_oxide_pages,
)
from lib.memory_qa import MemoryQaConfig, write_memory_qa_report
from lib.status_report import StatusReportPaths, build_status_report, default_paths, render_html
from lib.coverage_loop import CoverageLoopConfig, build_coverage_loop

try:
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path.home() / ".pi" / "skills"))
    from common.task_monitor import TaskClient
except ImportError:
    TaskClient = None

# Memory + Taxonomy integration (graceful degradation)
try:
    from memory_integration import recall_prior_convergence, learn_convergence
    _HAS_MEMORY_INTEGRATION = True
except ImportError:
    _HAS_MEMORY_INTEGRATION = False

app = typer.Typer(
    name="pdf-lab",
    help="Self-improving PDF extraction convergence loop",
    no_args_is_help=True,
)


@app.command()
def tune(
    pdf: Path = typer.Argument(..., help="Path to the PDF file"),
    review_json: Optional[Path] = typer.Option(None, help="Review result JSON"),
    debug_json: Optional[Path] = typer.Option(None, help="Debug-pdf patterns JSON"),
    persona: str = typer.Option("Margaret Chen", help="Persona name"),
    persona_role: str = typer.Option("extraction quality", help="Persona role"),
    max_iterations: int = typer.Option(5, help="Max convergence iterations"),
    converge: bool = typer.Option(False, help="Enable convergence loop"),
    write_back: bool = typer.Option(False, help="Write global fixes to pipeline code"),
    dry_run: bool = typer.Option(False, help="Preview changes without writing"),
    interactive: bool = typer.Option(False, help="Block and escalate to human via /interview when stuck"),
    question_book: Optional[Path] = typer.Option(None, help="JSONL file for deferred questions (batch mode)"),
    answer_book_path: Optional[Path] = typer.Option(None, "--answers", help="Answer book JSONL to replay"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Diagnose, reproduce, converge, and optionally write fix back to pipeline."""
    if not pdf.exists():
        logger.error(f"PDF not found: {pdf}")
        raise typer.Exit(1)

    # Build delta from review JSON or defaults
    if review_json and review_json.exists():
        review_data = json.loads(review_json.read_text())
        delta = compute_delta_from_review(review_data)
        review_context = ReviewContext.from_review_json(review_data)
        review_context.persona_name = persona
        review_context.persona_role = persona_role
    else:
        # Try to find profile.json and structural.json from pipeline output
        delta = _try_auto_delta(pdf)
        review_context = ReviewContext(
            persona_name=persona,
            persona_role=persona_role,
            source_pdf=str(pdf),
        )

    # Pre-hook: Recall prior convergence results
    if _HAS_MEMORY_INTEGRATION:
        try:
            prior = recall_prior_convergence(str(pdf))
            if prior:
                logger.info(f"Recalled prior convergence context ({len(prior)} chars)")
        except Exception as e:
            logger.debug(f"Memory recall skipped: {e}")

    if delta.overall_delta >= 0.95:
        logger.info(f"Delta is {delta.overall_delta:.2f} — extraction looks good.")
        if output_json:
            typer.echo(json.dumps({"status": "good", "delta": delta.to_dict()}, indent=2))
        else:
            typer.echo(f"Delta: {delta.summary()}")
            typer.echo("Extraction quality is good — no tuning needed.")
        return

    # Get patterns from debug JSON or auto-detect
    patterns: List[str] = []
    if debug_json and debug_json.exists():
        debug_data = json.loads(debug_json.read_text())
        patterns = debug_data.get("patterns", [])

    # Load answer book if provided (replay mode)
    answers = load_answer_book(answer_book_path) if answer_book_path else None

    _monitor = TaskClient(f"pdf-lab/tune", total=max_iterations, description=f"Tuning {pdf.name}") if TaskClient else None

    # Run convergence
    result = run_tune(
        pdf_path=pdf,
        delta=delta,
        patterns=patterns,
        review_context=review_context,
        max_iterations=max_iterations,
        write_back=write_back,
        dry_run=dry_run,
        converge=converge,
        interactive=interactive,
        question_book=question_book,
        answer_book=answers,
    )

    if _monitor:
        _monitor.update(item=f"delta {result.delta_before:.2f}->{result.delta_after:.2f} iters={result.iterations}")
        _monitor.finish()

    # Post-hook: Learn convergence outcome
    if _HAS_MEMORY_INTEGRATION:
        try:
            learn_convergence(
                pdf_url=str(pdf),
                strategy=result.diagnosis.root_cause if result.diagnosis else "unknown",
                iterations=result.iterations,
                final_score=result.delta_after,
                improvements=[c.description for c in (result.write_back_result.changes if result.write_back_result and result.write_back_result.changes else [])],
                patterns=result.diagnosis.patterns if result.diagnosis else [],
                write_back_result=result.write_back_result.to_dict() if result.write_back_result else None,
            )
        except Exception as e:
            logger.debug(f"Memory learn skipped: {e}")

    # Output
    if output_json:
        typer.echo(json.dumps(result.to_dict(), indent=2))
    else:
        _print_tune_result(result)


@app.command()
def diagnose(
    pdf: Path = typer.Argument(..., help="Path to the PDF file"),
    profile_json: Optional[Path] = typer.Option(None, help="S00 profile JSON"),
    structural_json: Optional[Path] = typer.Option(None, help="S11 structural JSON"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Quick delta diagnosis — compute delta, no tuning."""
    if profile_json and structural_json:
        delta = compute_delta_from_json(profile_json, structural_json)
    else:
        delta = _try_auto_delta(pdf)

    diagnosis = diagnose_delta(delta)

    if output_json:
        typer.echo(json.dumps({
            "delta": delta.to_dict(),
            "diagnosis": diagnosis.to_dict(),
        }, indent=2))
    else:
        typer.echo(f"Delta: {delta.summary()}")
        typer.echo(f"Patterns: {', '.join(diagnosis.patterns) or 'none detected'}")
        typer.echo(f"Root cause: {diagnosis.root_cause}")
        typer.echo(f"Failing steps: {', '.join(diagnosis.failing_steps) or 'none'}")
        if diagnosis.s00_overestimated:
            typer.echo("NOTE: S00 appears to be systematically overestimating.")


@app.command()
def forensic(
    pdf: Path = typer.Argument(..., help="Path to the PDF file"),
    query: Optional[str] = typer.Option(None, help="Search request used to select an example page"),
    page: Optional[int] = typer.Option(None, help="1-based page number; bypasses query page search"),
    output_dir: Optional[Path] = typer.Option(None, "--out", help="Directory for PNG, JSON, and HTML artifacts"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Create a page PNG + beautified JSON/schema forensic report."""
    try:
        result = run_forensic_page(
            pdf=pdf,
            query=query,
            page=page,
            output_dir=output_dir,
        )
    except Exception as exc:
        logger.error(f"Forensic report failed: {exc}")
        raise typer.Exit(1) from exc

    if output_json:
        typer.echo(json.dumps(result.to_dict(), indent=2))
        return

    typer.echo("pdf-lab forensic report created")
    typer.echo(f"  page: {result.page}")
    typer.echo(f"  triage tasks: {result.triage_count}")
    typer.echo(f"  png: {result.png_path}")
    typer.echo(f"  raw extraction: {result.raw_extraction_path}")
    typer.echo(f"  schema: {result.schema_path}")
    typer.echo(f"  html: {result.html_path}")


@app.command(name="toc-scan")
def toc_scan(
    pdf: Path = typer.Argument(..., help="Path to the PDF file"),
    output_dir: Optional[Path] = typer.Option(None, "--out", help="Directory for TOC JSON and HTML"),
    toc_pages: int = typer.Option(12, help="Number of front-matter pages to inspect for printed TOC evidence"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Build a section map before table, element, or forensic scans."""
    try:
        result = run_toc_scan(pdf=pdf, output_dir=output_dir, toc_pages=toc_pages)
    except Exception as exc:
        logger.error(f"TOC scan failed: {exc}")
        raise typer.Exit(1) from exc

    if output_json:
        typer.echo(json.dumps(result.to_dict(), indent=2))
        return

    typer.echo("pdf-lab TOC scan created")
    typer.echo(f"  sections: {result.section_count}")
    typer.echo(f"  toc: {result.toc_path}")
    typer.echo(f"  html: {result.html_path}")


@app.command(name="preset-scan")
def preset_scan(
    pdf: Path = typer.Argument(..., help="Path to the PDF file"),
    output_dir: Optional[Path] = typer.Option(None, "--out", help="Directory for preset scan JSON, PNGs, and HTML"),
    top_k: int = typer.Option(5, help="Top pages to keep per preset"),
    max_rendered: int = typer.Option(16, help="Max high-signal pages to render"),
    dpi: int = typer.Option(95, help="Render DPI for candidate thumbnails"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Sweep every pdf_oxide preset against the PDF."""
    try:
        result = run_preset_scan(
            pdf=pdf,
            output_dir=output_dir,
            top_k=top_k,
            max_rendered=max_rendered,
            dpi=dpi,
        )
    except Exception as exc:
        logger.error(f"Preset scan failed: {exc}")
        raise typer.Exit(1) from exc

    if output_json:
        typer.echo(json.dumps(result.to_dict(), indent=2))
        return

    typer.echo("pdf-lab preset scan created")
    typer.echo(f"  presets: {result.preset_count}")
    typer.echo(f"  page count: {result.page_count}")
    typer.echo(f"  preset scan: {result.preset_scan_path}")
    typer.echo(f"  html: {result.html_path}")


@app.command(name="agent-scan")
def agent_scan(
    pdf: Path = typer.Argument(..., help="Path to the PDF file"),
    output_dir: Optional[Path] = typer.Option(None, "--out", help="Directory for expected_elements.json and scan artifacts"),
    max_pages: int = typer.Option(12, help="Max representative pages to select"),
    top_k: int = typer.Option(3, help="Top pages to retain per preset during preset scan"),
    preset_path: Optional[Path] = typer.Option(None, "--preset", help="Document-family preset JSON to apply to matching policy"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Create the provisional agent oracle expected_elements.json."""
    try:
        result = run_agent_scan(pdf=pdf, output_dir=output_dir, max_pages=max_pages, top_k=top_k, preset_path=preset_path)
    except Exception as exc:
        logger.error(f"Agent scan failed: {exc}")
        raise typer.Exit(1) from exc

    if output_json:
        typer.echo(json.dumps(result.to_dict(), indent=2))
        return

    typer.echo("pdf-lab agent scan created")
    typer.echo(f"  selected pages: {', '.join(str(page) for page in result.selected_pages)}")
    typer.echo(f"  expected elements: {result.expected_count}")
    typer.echo(f"  expected JSON: {result.expected_elements_path}")
    typer.echo(f"  toc JSON: {result.toc_path}")
    typer.echo(f"  preset JSON: {result.preset_scan_path}")


@app.command(name="extract-pages")
def extract_pages(
    pdf: Path = typer.Argument(..., help="Path to the PDF file"),
    pages: str = typer.Option(..., "--pages", help="Comma-separated 1-based pages to extract with pdf_oxide"),
    output_dir: Path = typer.Option(..., "--out", help="Directory for actual_elements.json"),
    preset_path: Optional[Path] = typer.Option(None, "--preset", help="Document-family preset JSON to apply to actual elements"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Run deterministic pdf_oxide extraction for selected pages."""
    try:
        page_numbers = _parse_page_list(pages)
        result = run_pdf_oxide_pages(pdf=pdf, pages=page_numbers, output_dir=output_dir, preset_path=preset_path)
    except Exception as exc:
        logger.error(f"Page extraction failed: {exc}")
        raise typer.Exit(1) from exc

    if output_json:
        typer.echo(json.dumps(result.to_dict(), indent=2))
        return

    typer.echo("pdf-lab deterministic page extraction created")
    typer.echo(f"  pages: {', '.join(str(page) for page in result.pages)}")
    typer.echo(f"  actual elements: {result.actual_count}")
    typer.echo(f"  actual JSON: {result.actual_elements_path}")


@app.command(name="compare-json")
def compare_json(
    expected_json: Path = typer.Argument(..., help="agent expected_elements.json"),
    actual_json: Path = typer.Argument(..., help="pdf_oxide actual_elements.json"),
    output_dir: Path = typer.Option(..., "--out", help="Directory for comparison.json"),
    target: float = typer.Option(0.95, help="Required match accuracy"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Compare agent scan JSON against pdf_oxide deterministic JSON."""
    try:
        result = compare_expected_actual(expected_json, actual_json, output_dir=output_dir, target=target)
    except Exception as exc:
        logger.error(f"JSON comparison failed: {exc}")
        raise typer.Exit(1) from exc

    if output_json:
        typer.echo(json.dumps(result.to_dict(), indent=2))
        return

    typer.echo("pdf-lab JSON comparison created")
    typer.echo(f"  accuracy: {result.accuracy:.3f}")
    typer.echo(f"  matched: {result.matched_count}/{result.total_expected}")
    typer.echo(f"  passed: {result.passed}")
    typer.echo(f"  comparison JSON: {result.comparison_path}")


@app.command(name="agentic-extract")
def agentic_extract(
    pdf: Path = typer.Argument(..., help="Path to the PDF file"),
    output_dir: Optional[Path] = typer.Option(None, "--out", help="Directory for agentic extraction artifacts"),
    target: float = typer.Option(0.95, help="Required JSON-to-JSON match accuracy"),
    max_iterations: int = typer.Option(5, help="Max extraction/compare iterations"),
    max_pages: int = typer.Option(12, help="Max representative pages selected by agent scan"),
    top_k: int = typer.Option(3, help="Top pages to retain per preset during preset scan"),
    preset_path: Optional[Path] = typer.Option(None, "--preset", help="Document-family preset JSON for isolated extraction tuning"),
    full_extract: bool = typer.Option(False, "--full-extract", help="Run full-document extraction if target is reached"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Run agent scan -> pdf_oxide extraction -> JSON comparison loop."""
    try:
        result = run_agentic_extract(
            pdf=pdf,
            output_dir=output_dir,
            target=target,
            max_iterations=max_iterations,
            max_pages=max_pages,
            top_k=top_k,
            preset_path=preset_path,
            full_extract=full_extract,
        )
    except Exception as exc:
        logger.error(f"Agentic extraction failed: {exc}")
        raise typer.Exit(1) from exc

    if output_json:
        typer.echo(json.dumps(result.to_dict(), indent=2))
        return

    typer.echo("pdf-lab agentic extraction run created")
    typer.echo(f"  accuracy: {result.accuracy:.3f}")
    typer.echo(f"  passed: {result.passed}")
    typer.echo(f"  iterations: {result.iterations}")
    typer.echo(f"  expected JSON: {result.expected_elements_path}")
    typer.echo(f"  actual JSON: {result.actual_elements_path}")
    typer.echo(f"  comparison JSON: {result.comparison_path}")
    typer.echo(f"  preset update plan: {result.preset_update_plan_path}")
    typer.echo(f"  summary: {result.summary_path}")


@app.command(name="final-pass")
def final_pass(
    extraction_path: Path = typer.Argument(..., help="Full-document final_extraction.json"),
    output_dir: Optional[Path] = typer.Option(None, "--out", help="Directory for human_triage_queue.json"),
    comparison_path: Optional[Path] = typer.Option(None, "--comparison", help="Representative-page comparison JSON"),
    preset_path: Optional[Path] = typer.Option(None, "--preset", help="Document-family preset JSON used for extraction"),
    max_tasks: Optional[int] = typer.Option(None, "--max-tasks", help="Optional cap for smoke tests"),
    second_pass_model: str = typer.Option("oc-kimi", "--second-pass-model", help="scillm multimodal model for live second-pass review"),
    second_pass_endpoint: str = typer.Option("http://localhost:4001/v1/chat/completions", "--second-pass-endpoint", help="scillm chat-completions endpoint"),
    second_pass_timeout_s: float = typer.Option(300.0, "--second-pass-timeout", help="Timeout in seconds for each live second-pass model call"),
    max_second_pass_cases: Optional[int] = typer.Option(None, "--max-second-pass-cases", help="Optional cap for live second-pass model calls"),
    offline_second_pass: bool = typer.Option(False, "--offline-second-pass", help="Do not call scillm; write deterministic guardrail artifacts only"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Generate final human_triage_queue.json from full deterministic extraction."""
    try:
        result = run_final_agent_pass(
            extraction_path=extraction_path,
            output_dir=output_dir,
            comparison_path=comparison_path,
            preset_path=preset_path,
            max_tasks=max_tasks,
            second_pass_model=None if offline_second_pass else second_pass_model,
            second_pass_endpoint=second_pass_endpoint,
            second_pass_timeout_s=second_pass_timeout_s,
            max_second_pass_cases=max_second_pass_cases,
        )
    except Exception as exc:
        logger.error(f"Final agent pass failed: {exc}")
        raise typer.Exit(1) from exc

    if output_json:
        typer.echo(json.dumps(result.to_dict(), indent=2))
        return

    typer.echo("pdf-lab final agent pass created")
    typer.echo(f"  pages: {result.page_count}")
    typer.echo(f"  triage tasks: {result.task_count}")
    typer.echo(f"  human triage queue: {result.triage_queue_path}")


@app.command(name="table-scan")
def table_scan(
    pdf: Path = typer.Argument(..., help="Path to the PDF file"),
    output_dir: Optional[Path] = typer.Option(None, "--out", help="Directory for candidate JSON, PNGs, and HTML"),
    max_candidates: int = typer.Option(10, help="Max rendered candidates"),
    dpi: int = typer.Option(110, help="Render DPI for candidate thumbnails"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Find likely table pages without using pdf_oxide extraction."""
    try:
        result = run_non_pdf_oxide_table_scan(
            pdf=pdf,
            output_dir=output_dir,
            max_candidates=max_candidates,
            dpi=dpi,
        )
    except Exception as exc:
        logger.error(f"Table candidate scan failed: {exc}")
        raise typer.Exit(1) from exc

    if output_json:
        typer.echo(json.dumps(result.to_dict(), indent=2))
        return

    typer.echo("pdf-lab table candidate scan created")
    typer.echo(f"  selected pages: {', '.join(str(page) for page in result.selected_pages)}")
    typer.echo(f"  candidates: {result.candidates_path}")
    typer.echo(f"  html: {result.html_path}")


@app.command(name="element-scan")
def element_scan(
    pdf: Path = typer.Argument(..., help="Path to the PDF file"),
    output_dir: Optional[Path] = typer.Option(None, "--out", help="Directory for element inventory JSON, PNGs, and HTML"),
    max_rendered: int = typer.Option(12, help="Max high-signal pages to render"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Inventory every per-page extraction layer exposed by pdf_oxide."""
    try:
        result = run_pdf_oxide_element_scan(
            pdf=pdf,
            output_dir=output_dir,
            max_rendered=max_rendered,
        )
    except Exception as exc:
        logger.error(f"Element scan failed: {exc}")
        raise typer.Exit(1) from exc

    if output_json:
        typer.echo(json.dumps(result.to_dict(), indent=2))
        return

    typer.echo("pdf-lab pdf_oxide element inventory created")
    typer.echo(f"  page count: {result.page_count}")
    typer.echo(f"  inventory: {result.inventory_path}")
    typer.echo(f"  html: {result.html_path}")


@app.command()
def compare(
    fixture_pdf: Path = typer.Argument(..., help="Path to the fixture PDF"),
    ground_truth: Path = typer.Argument(..., help="Path to the ground_truth.json sidecar"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show per-category details"),
):
    """Compare pdf_oxide extraction output against ground truth oracle.

    Runs pdf_oxide on the fixture PDF, parses sections/blocks/tables/figures/requirements,
    and computes deltas against the ground_truth.json generated by /fixture-tricky.
    """
    if not fixture_pdf.exists():
        logger.error(f"PDF not found: {fixture_pdf}")
        raise typer.Exit(1)
    if not ground_truth.exists():
        logger.error(f"Ground truth not found: {ground_truth}")
        raise typer.Exit(1)

    result = run_compare(fixture_pdf, ground_truth)

    if output_json:
        typer.echo(json.dumps(result, indent=2))
    else:
        _print_compare_result(result, verbose=verbose)


@app.command(name="tune-gt")
def tune_gt(
    fixture_pdf: Path = typer.Argument(..., help="Path to the fixture PDF"),
    ground_truth: Path = typer.Option(None, "--ground-truth", "-g", help="Path to ground_truth.json (default: <pdf_dir>/ground_truth.json)"),
    max_rounds: int = typer.Option(5, "--max-rounds", help="Max convergence rounds"),
    target_score: float = typer.Option(0.95, "--target", help="Target overall score (0..1)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show VLM raw responses and render debug"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
    vlm_endpoint: str = typer.Option(
        "http://localhost:4001/v1/chat/completions",
        "--vlm-endpoint",
        help="VLM API endpoint",
    ),
):
    """VLM-guided convergence loop: compare extraction vs ground truth, visually
    inspect pages where extraction diverges, reason about root causes, suggest
    parameter adjustments, and re-extract until score >= target or max_rounds.

    This is the CORE self-improving extraction command. It uses:
    1. pdf_oxide extraction + compare against ground_truth.json
    2. pdf_oxide page rendering to produce screenshots
    3. /scillm VLM to visually diagnose extraction errors
    4. Parameter adjustment and re-extraction loop

    Writes tune_overrides.json (extraction params) and fix_registry.json (results)
    to the fixture directory.
    """
    if not fixture_pdf.exists():
        logger.error(f"PDF not found: {fixture_pdf}")
        raise typer.Exit(1)

    # Default ground truth location
    if ground_truth is None:
        ground_truth = fixture_pdf.parent / "ground_truth.json"
    if not ground_truth.exists():
        logger.error(f"Ground truth not found: {ground_truth}")
        raise typer.Exit(1)

    _monitor = (
        TaskClient(
            "pdf-lab/tune-gt",
            total=max_rounds,
            description=f"Tuning {fixture_pdf.name} (VLM convergence)",
        )
        if TaskClient
        else None
    )

    result = run_convergence(
        fixture_pdf,
        ground_truth,
        max_rounds=max_rounds,
        target_score=target_score,
    )

    if _monitor:
        _monitor.update(
            item=f"{'CONVERGED' if result.converged else 'INCOMPLETE'} "
            f"score={result.final_score:.4f} rounds={result.rounds}"
        )
        _monitor.finish()

    if output_json:
        typer.echo(json.dumps(result.to_dict(), indent=2))
    else:
        _print_convergence_result(result)


@app.command(name="verify-real")
def verify_real(
    real_pdf: Path = typer.Argument(..., help="Path to the real PDF to re-extract"),
    fixture_dir: Path = typer.Argument(..., help="Fixture directory containing fix_registry.json"),
    pattern_name: Optional[str] = typer.Option(None, "--pattern", "-p", help="Pattern name to update in pattern_registry.json"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Re-extract a real PDF with tuned parameters from convergence and compare.

    Reads fix_registry.json from the fixture directory, applies the tuned
    overrides to the real PDF extraction, and compares against the old
    manifest entry. Updates manifest.jsonl and pattern_registry.json
    based on whether extraction improved.
    """
    if not real_pdf.exists():
        logger.error(f"Real PDF not found: {real_pdf}")
        raise typer.Exit(1)
    if not fixture_dir.exists():
        logger.error(f"Fixture directory not found: {fixture_dir}")
        raise typer.Exit(1)

    result = run_verify_real(
        real_pdf,
        fixture_dir,
        pattern_name=pattern_name,
    )

    if output_json:
        typer.echo(json.dumps(result.to_dict(), indent=2))
    else:
        _print_verify_result(result)


def _print_verify_result(result: VerifyResult) -> None:
    """Pretty-print a verify-real result."""
    status = "IMPROVED" if result.improved else "NO IMPROVEMENT"
    typer.echo(f"\n{'='*60}")
    typer.echo(f"pdf-lab Verify-Real: {Path(result.real_pdf).name} [{status}]")
    typer.echo(f"{'='*60}")
    typer.echo(f"Fixture: {result.fixture_id}")
    typer.echo(f"Result: {result.summary()}")

    if result.overrides_applied:
        typer.echo(f"\nOverrides applied:")
        for key, value in result.overrides_applied.items():
            typer.echo(f"  {key}: {value}")

    typer.echo(f"\nOld quality: {result.old_quality_signal}")
    typer.echo(f"New quality: {result.new_quality_signal}")

    if result.old_s00_s04_ratio is not None:
        typer.echo(f"Old S00/S04 ratio: {result.old_s00_s04_ratio:.2f}x")
    if result.new_s00_s04_ratio is not None:
        typer.echo(f"New S00/S04 ratio: {result.new_s00_s04_ratio:.2f}x")

    if result.manifest_updated:
        typer.echo(f"\nManifest: UPDATED")
    if result.pattern_updated:
        typer.echo(f"Pattern registry: UPDATED")

    if not result.improved:
        typer.echo(f"\nParameters reverted. Flagged for review.")

    typer.echo(f"{'='*60}")


def _print_convergence_result(result: ConvergenceResult) -> None:
    """Pretty-print a VLM convergence result."""
    status_label = "CONVERGED" if result.converged else "INCOMPLETE"
    typer.echo(f"\n{'='*60}")
    typer.echo(f"pdf-lab Tune-GT: {result.fixture_id} [{status_label}]")
    typer.echo(f"{'='*60}")

    for rr in result.round_history:
        typer.echo(f"\nRound {rr.round_num}/{rr.max_rounds}:")
        typer.echo(f"  Score: {rr.score:.4f} (target: {rr.target_score})")
        if rr.worst_category != "none":
            typer.echo(f"  Worst: {rr.worst_category} ({rr.worst_score:.2%} -- {rr.worst_detail})")
            typer.echo(f"  VLM diagnosis: {rr.diagnosis!r}")
            for adj in rr.adjustments:
                typer.echo(f"  Adjustment: {adj.parameter}: {adj.current} -> {adj.suggested}")
        else:
            typer.echo(f"  {rr.diagnosis}")

    typer.echo(f"\n--- Summary ---")
    typer.echo(f"Final score: {result.final_score:.4f}")
    typer.echo(f"Rounds: {result.rounds}")
    typer.echo(f"Total adjustments: {len(result.adjustments_applied)}")

    if result.overrides_path:
        typer.echo(f"Overrides: {result.overrides_path}")
    if result.registry_path:
        typer.echo(f"Registry: {result.registry_path}")
    typer.echo(f"{'='*60}")
