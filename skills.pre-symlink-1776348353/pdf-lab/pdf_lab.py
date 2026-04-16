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
from loguru import logger

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


def _print_compare_result(result: dict, verbose: bool = False) -> None:
    """Pretty-print a comparison result."""
    fixture_id = result.get("fixture_id", "unknown")
    score = result.get("overall_score", 0)

    typer.echo(f"\n{'='*60}")
    typer.echo(f"pdf-lab Compare: {fixture_id}")
    typer.echo(f"{'='*60}")
    typer.echo(f"Overall Score: {score:.2%}")
    typer.echo()

    # Section delta
    sd = result.get("section_delta", {})
    typer.echo(f"  Sections:  expected={sd.get('expected', '?')}  got={sd.get('got', '?')}  "
               f"matched={sd.get('title_matched', '?')}  missed={sd.get('title_missed', '?')}  "
               f"score={sd.get('score', 0):.2%}")

    # Block delta
    bd = result.get("block_delta", {})
    typer.echo(f"  Blocks:    expected={bd.get('expected', '?')}  actual={bd.get('actual', '?')}  "
               f"type_match={bd.get('type_matches', '?')}  misclass={bd.get('misclassified', '?')}  "
               f"score={bd.get('score', 0):.2%}")

    # Table delta
    td = result.get("table_delta", {})
    typer.echo(f"  Tables:    real={td.get('expected_real', '?')}  false={td.get('expected_false', '?')}  "
               f"extracted={td.get('extracted', '?')}  "
               f"score={td.get('score', 0):.2%}")

    # Figure delta
    fd = result.get("figure_delta", {})
    typer.echo(f"  Figures:   expected={fd.get('expected', '?')}  got={fd.get('got', '?')}  "
               f"score={fd.get('score', 0):.2%}")

    # Requirement delta
    rd = result.get("requirement_delta", {})
    typer.echo(f"  Reqs:      real={rd.get('expected_real', '?')}  false={rd.get('expected_false', '?')}  "
               f"matched={rd.get('matched_real', '?')}  "
               f"score={rd.get('score', 0):.2%}")

    # Profile delta
    pd_delta = result.get("profile_delta", {})
    typer.echo(f"  Profile:   {pd_delta.get('matches', '?')}/{pd_delta.get('total', '?')} fields match  "
               f"score={pd_delta.get('score', 0):.2%}")

    if verbose:
        typer.echo(f"\n--- Profile Details ---")
        for key, detail in pd_delta.get("details", {}).items():
            status = "OK" if detail.get("match") else "MISMATCH"
            typer.echo(f"  {key}: expected={detail.get('expected')} got={detail.get('got')} [{status}]")

        typer.echo(f"\n--- Block Type Counts (GT) ---")
        for t, c in sorted(result.get("block_delta", {}).get("gt_type_counts", {}).items()):
            typer.echo(f"  {t}: {c}")

        typer.echo(f"\n--- Block Type Counts (Extracted) ---")
        for t, c in sorted(result.get("block_delta", {}).get("ext_type_counts", {}).items()):
            typer.echo(f"  {t}: {c}")

        typer.echo(f"\n--- Tricks ---")
        for trick in result.get("tricks", []):
            typer.echo(f"  - {trick}")

    typer.echo(f"{'='*60}")


@app.command()
def synthetic(
    patterns: str = typer.Option("[]", help="Pattern list as JSON array"),
    output: Optional[Path] = typer.Option(None, help="Output PDF path"),
    sections: int = typer.Option(8, help="Target section count"),
    tables: int = typer.Option(2, help="Target table count"),
    figures: int = typer.Option(1, help="Target figure count"),
):
    """Generate a synthetic reproduction PDF from patterns."""
    try:
        pattern_list = json.loads(patterns)
    except json.JSONDecodeError:
        # Try comma-separated
        pattern_list = [p.strip() for p in patterns.split(",") if p.strip()]

    if not pattern_list:
        logger.warning("No patterns specified. Using default test patterns.")
        pattern_list = ["section_undersegmentation", "missed_tables"]

    pdf_path, spec = generate_synthetic(
        patterns=pattern_list,
        target_sections=sections,
        target_tables=tables,
        target_figures=figures,
        output_path=output,
    )

    typer.echo(f"Generated: {pdf_path}")
    typer.echo(f"Spec: {json.dumps(spec.to_dict(), indent=2)}")


@app.command()
def metrics(
    sample_size: int = typer.Option(100, help="Number of sections to sample"),
    retrieval: bool = typer.Option(False, help="Run retrieval evaluation"),
    output_json: Path = typer.Option(None, help="Write JSON report to file"),
):
    """Run integrity checks and optional retrieval evaluation, then report."""
    from lib.integrity import check_integrity
    from lib.metrics_models import VerificationReport
    from lib.metrics_report import render_markdown, render_json, store_report

    summary, issues = check_integrity(sample_size=sample_size)
    retrieval_metrics = None
    if retrieval:
        from lib.retrieval_eval import build_auto_judgements, evaluate_retrieval
        judgements = build_auto_judgements()
        retrieval_metrics = evaluate_retrieval(judgements)
    report = VerificationReport(
        integrity_summary=summary,
        integrity_issues=issues,
        retrieval_metrics=retrieval_metrics,
    )
    typer.echo(render_markdown(report))
    store_report(report)
    if output_json:
        output_json.write_text(render_json(report))
        typer.echo(f"JSON report written to {output_json}")


@app.command()
def status():
    """Show recent tuning results from local data."""
    data_dir = Path(os.environ.get("PDF_LAB_DATA", Path.home() / ".pi" / "pdf-lab"))
    events_file = data_dir / "convergence_events.jsonl"

    typer.echo("=== pdf-lab Status ===\n")

    if events_file.exists():
        lines = events_file.read_text().strip().split("\n")
        recent = lines[-10:]  # Last 10 events
        typer.echo(f"Total convergence events: {len(lines)}")
        typer.echo(f"\nRecent events:")
        for line in recent:
            try:
                event = json.loads(line)
                ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(event["timestamp"]))
                tags = event.get("tags", [])
                pattern_tags = [t for t in tags if t.startswith("pattern:")]
                typer.echo(f"  {ts} | {' '.join(pattern_tags)}")
            except Exception:
                continue
    else:
        typer.echo("No convergence events yet. Run 'pdf-lab tune' to start.")

    # Show git history
    typer.echo("\nGit commits:")
    try:
        result = subprocess.run(
            ["git", "log", "--all", "--oneline", "--grep=pdf-lab:", "-5"],
            cwd=str(EXTRACTOR_ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.stdout.strip():
            typer.echo(result.stdout)
        else:
            typer.echo("  No pdf-lab commits found.")
    except Exception:
        typer.echo("  (git log unavailable)")


@app.command()
def rollback(
    sha: str = typer.Option(..., help="Commit SHA to revert"),
):
    """Rollback a specific pdf-lab fix by SHA."""
    typer.echo(f"Rolling back commit {sha}...")

    try:
        # Verify it's a pdf-lab commit
        result = subprocess.run(
            ["git", "log", "--format=%s", "-1", sha],
            cwd=str(EXTRACTOR_ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if "pdf-lab:" not in result.stdout:
            typer.echo(f"Commit {sha} is not a pdf-lab commit. Aborting.")
            raise typer.Exit(1)

        # Revert
        result = subprocess.run(
            ["git", "revert", "--no-edit", sha],
            cwd=str(EXTRACTOR_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            typer.echo(f"Successfully reverted {sha}")
        else:
            typer.echo(f"Revert failed: {result.stderr}")
            raise typer.Exit(1)

    except subprocess.TimeoutExpired:
        typer.echo("Git command timed out.")
        raise typer.Exit(1)


@app.command(name="regression-check")
def regression_check(
    sha: str = typer.Option(..., help="Commit SHA to check"),
):
    """Re-run regression test for a specific fix."""
    raise NotImplementedError(f"Regression check for {sha} not yet implemented")


@app.command()
def answer(
    book: Optional[Path] = typer.Option(None, help="Question book JSONL path"),
    mode: str = typer.Option("auto", help="Interview mode: auto, html, tui"),
    output: Optional[Path] = typer.Option(None, help="Save answer book to this path"),
):
    """Review and answer deferred questions from an overnight batch run.

    Opens the question book in /interview for the human to answer all at once.
    Saves answers to an answer book for replay on the next batch run.
    """
    questions = load_question_book(book)
    if not questions:
        typer.echo("No deferred questions found. Nothing to review.")
        return

    typer.echo(f"Found {len(questions)} deferred questions from batch run.")
    typer.echo("Opening /interview for review...\n")

    guidance_map = run_batch_interview(book_path=book, mode=mode)

    if not guidance_map:
        typer.echo("No answers collected (interview cancelled or failed).")
        return

    answered = sum(1 for g in guidance_map.values() if g.escalated)
    typer.echo(f"\nAnswered: {answered}/{len(questions)}")

    # Save answer book
    answer_path = save_answer_book(guidance_map, book_path=output)
    typer.echo(f"Answer book saved: {answer_path}")
    typer.echo(f"\nTo replay: pdf-lab tune <pdf> --answers {answer_path}")

    # Offer to clear the question book
    clear_question_book(book)
    typer.echo("Question book cleared.")


@app.command(name="book")
def show_book(
    book: Optional[Path] = typer.Option(None, help="Question book JSONL path"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Show pending deferred questions from the question book."""
    questions = load_question_book(book)
    if not questions:
        typer.echo("No deferred questions. Run a batch with --question-book to generate.")
        return

    if output_json:
        typer.echo(json.dumps([q.to_dict() for q in questions], indent=2))
        return

    typer.echo(f"=== pdf-lab Question Book: {len(questions)} questions ===\n")
    for i, q in enumerate(questions):
        typer.echo(f"  [{i+1}/{len(questions)}] {q.pdf_name}")
        typer.echo(f"    Reason: {q.reason}")
        typer.echo(f"    Delta: {q.delta_summary.get('overall_delta', '?')}")
        typer.echo(f"    Patterns: {', '.join(q.patterns) or 'none'}")
        typer.echo(f"    Screenshots: {len(q.screenshots)}")
        typer.echo()

    typer.echo(f"Run 'pdf-lab answer' to review and answer all questions.")


def _try_auto_delta(pdf: Path) -> ExtractionDelta:
    """Try to compute delta automatically by finding pipeline output."""
    # Look for pipeline output in common locations
    candidates = [
        pdf.parent / "pipeline_output",
        pdf.parent / "data" / "results" / "pipeline",
        Path("data/results/pipeline"),
    ]

    for candidate in candidates:
        profile = candidate / "00_profile_detector" / "profile.json"
        structural = candidate / "11_json_exporter" / "structural.json"
        if profile.exists() and structural.exists():
            return compute_delta_from_json(profile, structural)

    # Return empty delta (will trigger "looks good" or diagnosis)
    logger.warning("Could not find pipeline output. Using empty delta.")
    return ExtractionDelta()


def _print_tune_result(result: TuneResult) -> None:
    """Pretty-print a tune result."""
    typer.echo(f"\n{'='*60}")
    typer.echo(f"pdf-lab Convergence Result: {result.status.upper()}")
    typer.echo(f"{'='*60}")
    typer.echo(f"Delta: {result.delta_before:.2f} -> {result.delta_after:.2f}")
    typer.echo(f"Iterations: {result.iterations}")

    if result.diagnosis:
        typer.echo(f"Root cause: {result.diagnosis.root_cause}")
        typer.echo(f"Patterns: {', '.join(result.diagnosis.patterns)}")

    if result.runtime_params:
        typer.echo(f"\nRuntime params (per-PDF tuning):")
        for key, value in result.runtime_params.items():
            typer.echo(f"  {key}: {value}")

    if result.write_back_result:
        wb = result.write_back_result
        typer.echo(f"\nWrite-back: {wb.status}")
        if wb.changes:
            typer.echo(f"Code changes:")
            for c in wb.changes:
                typer.echo(f"  [{c.tier}] {c.file}: {c.description}")
        if wb.branch:
            typer.echo(f"Branch: {wb.branch}")
        if wb.commit_sha:
            typer.echo(f"Commit: {wb.commit_sha[:12]}")

    if result.synthetic_path:
        typer.echo(f"\nSynthetic PDF: {result.synthetic_path}")

    typer.echo(f"{'='*60}")


def main():
    app()


if __name__ == "__main__":
    main()
