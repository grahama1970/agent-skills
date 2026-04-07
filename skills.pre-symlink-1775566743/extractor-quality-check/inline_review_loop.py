#!/usr/bin/env python3
"""Self-improvement loop: extract -> review -> remediate -> re-extract -> until PASS.

Takes a single PDF, extracts it, scores via inline_reviewer.review_pdf(),
runs auto-executable escalation jobs if WARN/FAIL, then re-extracts and
re-reviews. Each iteration is stored in /memory with supersedes edges
linking them for convergence tracking.

Usage:
    from inline_review_loop import review_loop
    result = review_loop(pdf_path, corpus_root)

Split into submodules:
    - json_utils: safe JSON parsing with json_repair fallback
    - memory_bridge: MemoryClient (native/subprocess/stub), add_edge, taxonomy
    - extraction: _extract_pdf, _slug_for_pdf, timeout classifier
    - remediation: remediate_with_memory, interview dispatch, hard_tail, question book
    - adaptive_params: issue code + debug-pdf pattern -> extraction parameter mapping
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

# ---------------------------------------------------------------------------
# sys.path setup (must come before submodule imports)
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent
_REVIEW_PDF_DIR = _THIS_DIR.parent / "review-pdf"
_SKILLS_DIR = _THIS_DIR.parent  # pi-mono/.pi/skills -- for common.* imports

for _p in [str(_REVIEW_PDF_DIR), str(_THIS_DIR), str(_SKILLS_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Submodule imports
# ---------------------------------------------------------------------------
from adaptive_params import compute_adaptive_params  # noqa: E402
from extraction import (  # noqa: E402
    compute_remediation_timeout,
    extract_pdf,
    slug_for_pdf,
)
from inline_reviewer import review_pdf  # noqa: E402
from memory_bridge import HAS_MEMORY  # noqa: E402
from remediation import (  # noqa: E402
    DEFAULT_REMEDIATION_TIMEOUT,
    defer_to_question_book,
    get_worst_dimension,
    link_review_iterations,
    mark_hard_tail,
    remediate_with_memory,
)

# ---------------------------------------------------------------------------
# Re-exports for backward compatibility (old private names)
# ---------------------------------------------------------------------------
_parse_json_safe = None  # lazy -- rarely used externally
_extract_pdf = extract_pdf
_slug_for_pdf = slug_for_pdf
_remediate_with_memory = remediate_with_memory
_dispatch_to_interview = None  # available via remediation module
_link_review_iterations = link_review_iterations
_mark_hard_tail = mark_hard_tail
_defer_to_question_book = defer_to_question_book
_get_worst_dimension = get_worst_dimension
_compute_remediation_timeout = compute_remediation_timeout
_compute_adaptive_params = compute_adaptive_params

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_MAX_ITERATIONS = 3


def _collect_low_fidelity_pages(
    run_dir: Path,
    low_dims: list[str],
) -> dict[int, list[dict]]:
    """Collect page detections from S05/S06 output for human bbox correction.

    Returns {page_num: [{"type": "Table"|"Figure", "bbox": [x0,y0,x1,y1], "confidence": 0.5}]}
    """
    pages: dict[int, list[dict]] = {}

    if "table_fidelity" in low_dims:
        tables_dir = run_dir / "05_table_extractor" / "json_output"
        if tables_dir.exists():
            for tf in tables_dir.glob("*.json"):
                try:
                    data = json.loads(tf.read_text())
                    for table in (data if isinstance(data, list) else data.get("tables", [])):
                        pn = table.get("page_num", table.get("page", 0))
                        bbox = table.get("bbox", table.get("bounding_box"))
                        if bbox and len(bbox) == 4:
                            pages.setdefault(pn, []).append({
                                "type": "Table",
                                "bbox": bbox,
                                "confidence": 0.5,  # low confidence flag for review
                            })
                except (json.JSONDecodeError, OSError):
                    pass

    if "figure_fidelity" in low_dims:
        figures_dir = run_dir / "06_figure_extractor" / "json_output"
        if figures_dir.exists():
            for ff in figures_dir.glob("*.json"):
                try:
                    data = json.loads(ff.read_text())
                    for fig in (data if isinstance(data, list) else data.get("figures", [])):
                        pn = fig.get("page_num", fig.get("page", 0))
                        bbox = fig.get("bbox", fig.get("bounding_box"))
                        if bbox and len(bbox) == 4:
                            pages.setdefault(pn, []).append({
                                "type": "Figure",
                                "bbox": bbox,
                                "confidence": 0.5,
                            })
                except (json.JSONDecodeError, OSError):
                    pass

    return pages


def review_loop(
    pdf_path: Path,
    corpus_root: Path,
    extracted_runs_dir: Optional[Path] = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    run_id: str = "",
    remediation_timeout: int = DEFAULT_REMEDIATION_TIMEOUT,
    question_book: Optional[Path] = None,
) -> Dict[str, Any]:
    """Self-improvement loop: extract -> review -> remediate -> re-extract -> until PASS.

    Args:
        pdf_path: Path to the PDF file
        corpus_root: Root of the corpus directory
        extracted_runs_dir: Where to store extraction output (default: corpus_root/results)
        max_iterations: Maximum review-remediate cycles (default: 3)
        run_id: Optional run identifier
        remediation_timeout: Timeout per remediation job in seconds
        question_book: Path to JSONL question book for deferred human review.
            Falls back to PDF_LAB_QUESTION_BOOK env var if not provided.

    Returns:
        {
            "pdf_path": str,
            "iterations": int,
            "final_verdict": "PASS"|"WARN"|"FAIL",
            "final_score": float,
            "converged": bool,
            "reviews": list[dict],
            "remediation_actions": list[dict],
            "memory_edge_ids": list[str],
        }
    """
    # Resolve question book: explicit arg > env var > None
    if question_book is None:
        qbook_env = os.environ.get("PDF_LAB_QUESTION_BOOK", "")
        if qbook_env:
            question_book = Path(qbook_env)
    if extracted_runs_dir is None:
        extracted_runs_dir = corpus_root / "results"

    reviews: List[Dict[str, Any]] = []
    remediation_actions: List[Dict[str, Any]] = []
    memory_edge_ids: List[str] = []
    previous_assessment_problem: str = ""
    score_trajectory: List[float] = []
    worst_dims: List[str] = []

    # Adaptive extraction parameters -- populated after remediation, applied on next iteration
    adaptive_params: Dict[str, Any] = {"preset": None, "extra_flags": [], "env_overrides": {}}

    # Dynamic timeout via timeout classifier (page-count ML model + 1.5x safety)
    effective_timeout = compute_remediation_timeout(pdf_path, remediation_timeout)
    if effective_timeout != remediation_timeout:
        logger.info(f"Timeout classifier: {effective_timeout}s (fallback was {remediation_timeout}s)")

    # Compute run_dir for this PDF (same as extract_pdf uses internally)
    slug = slug_for_pdf(pdf_path)
    run_dir = extracted_runs_dir / slug

    for iteration in range(1, max_iterations + 1):
        logger.info(f"Iteration {iteration}/{max_iterations} for {pdf_path.name}")

        # Step 1: Extract (force re-extract on iterations > 1)
        # On iteration > 1, apply adaptive parameters from previous remediation
        force = iteration > 1
        profile_path = extract_pdf(
            pdf_path, extracted_runs_dir, force_reextract=force,
            preset=adaptive_params.get("preset") if force else None,
            extra_flags=adaptive_params.get("extra_flags") if force else None,
            env_overrides=adaptive_params.get("env_overrides") if force else None,
        )

        if profile_path is None:
            logger.error(f"Extraction failed on iteration {iteration}")
            # Use best score from prior iterations rather than hardcoded 0.0
            best_prior = max(score_trajectory) if score_trajectory else 0.0
            reviews.append({
                "iteration": iteration,
                "error": "extraction_failed",
                "verdict": "FAIL",
                "score": best_prior,
            })
            break

        # Step 2: Review
        iter_run_id = f"{run_id}_iter{iteration}" if run_id else f"iter{iteration}"
        review_result = review_pdf(
            profile_path=profile_path,
            corpus_root=corpus_root,
            run_id=iter_run_id,
            max_related_reviews=5,
        )
        current_score = review_result["overall_score"]
        score_trajectory.append(current_score)
        current_worst_dim = get_worst_dimension(review_result)
        worst_dims.append(current_worst_dim)

        # Score delta: how much did we improve vs previous iteration?
        score_delta = (current_score - score_trajectory[-2]) if len(score_trajectory) >= 2 else 0.0

        reviews.append({
            "iteration": iteration,
            "verdict": review_result["verdict"],
            "score": current_score,
            "grade": review_result["grade"],
            "margaret_verdict": review_result["margaret"]["verdict"],
            "jennifer_verdict": review_result["jennifer"]["verdict"],
            "reconciled_decision": review_result["reconciled"]["decision"],
            "assessment_id": review_result.get("memory_assessment_id"),
            "lesson_id": review_result.get("memory_lesson_id"),
            "escalation_jobs_count": len(review_result.get("escalation_jobs", [])),
            "estimate_delta": review_result.get("estimate_delta", {}),
            "score_delta": round(score_delta, 4),
            "worst_dimension": current_worst_dim,
        })

        # Step 3: Link to previous iteration via supersedes edge
        # Uses problem text (not _key) because add_edge() resolves by exact title match
        current_problem = review_result.get("memory_assessment_problem", "")
        if previous_assessment_problem and current_problem:
            edge_id = link_review_iterations(
                current_problem, previous_assessment_problem, str(pdf_path)
            )
            if edge_id:
                memory_edge_ids.append(edge_id)
        previous_assessment_problem = current_problem

        # Step 4: Oscillation detection -- if worst dim flips A->B->A in 3 iterations,
        # remediation is chasing its tail. Abort early to avoid wasted cycles.
        if len(worst_dims) >= 3:
            if (worst_dims[-1] == worst_dims[-3] and
                    worst_dims[-1] != worst_dims[-2] and
                    worst_dims[-1] != ""):
                logger.warning(
                    f"Oscillation detected: {worst_dims[-3]}->{worst_dims[-2]}->{worst_dims[-1]} "
                    f"-- aborting to avoid chasing tail"
                )
                print(
                    f"review-pdf inline_review_loop oscillation "
                    f"dims={worst_dims[-3]}->{worst_dims[-2]}->{worst_dims[-1]} "
                    f"pdf={pdf_path}",
                    flush=True,
                )
                break

        # Step 5: Check verdict
        if review_result["verdict"] == "PASS":
            logger.info(
                f"PASS on iteration {iteration}: "
                f"score={current_score:.3f} grade={review_result['grade']}"
            )
            print(
                f"review-pdf inline_review_loop converged "
                f"score={current_score:.3f} grade={review_result['grade']} "
                f"iterations={iteration} pdf={pdf_path}",
                flush=True,
            )
            return {
                "pdf_path": str(pdf_path),
                "iterations": iteration,
                "final_verdict": "PASS",
                "final_score": current_score,
                "converged": True,
                "reviews": reviews,
                "remediation_actions": remediation_actions,
                "memory_edge_ids": memory_edge_ids,
                "score_trajectory": score_trajectory,
            }

        # Step 5b: Human feedback for low-fidelity tables/figures (interactive only)
        _hf_enabled = os.environ.get("HUMAN_FEEDBACK_ENABLED", "false").lower() in ("true", "1")
        if _hf_enabled and iteration < max_iterations:
            dims = review_result.get("dimensions", {})
            _low_dims = [
                d for d in ("table_fidelity", "figure_fidelity")
                if dims.get(d, {}).get("score", 1.0) < 0.70
            ]
            if _low_dims:
                try:
                    from extractor.pipeline.utils.human_feedback import request_multi_page_feedback
                    # Build detection list from S05/S06 output for pages with issues
                    _pages_to_review = _collect_low_fidelity_pages(run_dir, _low_dims)
                    if _pages_to_review:
                        print(
                            f"review-pdf human_feedback requesting bbox correction "
                            f"dims={_low_dims} pages={list(_pages_to_review.keys())} "
                            f"pdf={pdf_path}",
                            flush=True,
                        )
                        _corrections = request_multi_page_feedback(
                            pdf_path=pdf_path,
                            pages=_pages_to_review,
                            context=f"Low fidelity: {', '.join(_low_dims)} (iteration {iteration})",
                        )
                        if _corrections:
                            # Store corrections for next extraction iteration
                            adaptive_params["human_corrections"] = _corrections
                            print(
                                f"review-pdf human_feedback corrections_received "
                                f"pages={list(_corrections.keys())} pdf={pdf_path}",
                                flush=True,
                            )
                except ImportError:
                    pass  # human_feedback not available in this env

        # Step 6: Run remediation if WARN/FAIL (only if not last iteration)
        # Personas RECALL known fixes, RUN skills, and LEARN the result.
        if iteration < max_iterations:
            esc_jobs = review_result.get("escalation_jobs", [])
            print(
                f"review-pdf inline_review_loop step6 "
                f"escalation_jobs={len(esc_jobs)} "
                f"has_memory={HAS_MEMORY} "  # native|subprocess|unavailable
                f"iteration={iteration}/{max_iterations} "
                f"pdf={pdf_path}",
                flush=True,
            )
            if esc_jobs:
                logger.info(f"Running {len(esc_jobs)} escalation jobs (timeout={effective_timeout}s)")
                results = remediate_with_memory(review_result, timeout=effective_timeout)
                remediation_actions.extend(results)
                launched = sum(1 for r in results if r["status"] in ("completed", "failed", "timeout"))
                learned = sum(1 for r in results if r.get("memory_learned"))
                logger.info(
                    f"Remediation: {launched} jobs executed, "
                    f"{learned} fixes stored in /memory"
                )
                print(
                    f"review-pdf inline_review_loop remediation "
                    f"executed={launched} learned={learned} "
                    f"skills={[r.get('skill','?') for r in results[:5]]} "
                    f"pdf={pdf_path}",
                    flush=True,
                )
            else:
                logger.info("No auto-executable escalation jobs -- re-extracting with fresh run")
                print(
                    f"review-pdf inline_review_loop no_escalation_jobs "
                    f"verdict={review_result['verdict']} "
                    f"score={current_score:.3f} "
                    f"pdf={pdf_path}",
                    flush=True,
                )

            # Step 6b: Compute adaptive extraction params for next iteration
            adaptive_params = compute_adaptive_params(review_result, run_dir, iteration=iteration)
            if adaptive_params.get("preset") or adaptive_params.get("extra_flags") or adaptive_params.get("env_overrides"):
                logger.info(
                    f"Adaptive params for next iteration: "
                    f"preset={adaptive_params.get('preset')} "
                    f"flags={adaptive_params.get('extra_flags')} "
                    f"env={list(adaptive_params.get('env_overrides', {}).keys())}"
                )
                print(
                    f"review-pdf inline_review_loop adaptive_params "
                    f"preset={adaptive_params.get('preset')} "
                    f"flags={adaptive_params.get('extra_flags')} "
                    f"env_keys={list(adaptive_params.get('env_overrides', {}).keys())} "
                    f"pdf={pdf_path}",
                    flush=True,
                )

    # Max iterations reached without PASS (or oscillation detected)
    final_review = reviews[-1] if reviews else {}
    # Use best score from trajectory (not last review which may be extraction_failed=0.0)
    final_score = max(score_trajectory) if score_trajectory else final_review.get("score", 0.0)
    # Use verdict from the iteration that achieved the best score, not the last iteration.
    # Remediation can make things worse (e.g., section_overseg -> section_alignment_low),
    # and using the last iteration's verdict would penalize the PDF unfairly.
    best_idx = score_trajectory.index(final_score) if score_trajectory and final_score in score_trajectory else -1
    if best_idx >= 0 and best_idx < len(reviews):
        final_verdict = reviews[best_idx].get("verdict", "FAIL")
    else:
        final_verdict = final_review.get("verdict", "FAIL")

    # Mark as hard_tail in /memory with trajectory for improving/degrading classification
    pdf_hash = ""
    try:
        _h = hashlib.sha256()
        with open(pdf_path, "rb") as _f:
            for _chunk in iter(lambda: _f.read(65536), b""):
                _h.update(_chunk)
        pdf_hash = _h.hexdigest()[:16]
    except Exception as e:
        logger.debug("value lookup failed: {}", e)
    if reviews and len(reviews) > 0:
        mark_hard_tail(str(pdf_path), pdf_hash, final_score, score_trajectory=score_trajectory)

    # Defer to question book + deferred_review queue for human review via /interview.
    # Deferred items are NOT retried by learn-datalake until the human resolves them.
    deferred = False
    _deferred_review_path = os.environ.get("DEFERRED_REVIEW_PATH", "")
    if _deferred_review_path and reviews:
        try:
            _dr = Path(_deferred_review_path)
            _dr.parent.mkdir(parents=True, exist_ok=True)
            _entry = json.dumps({
                "stem": pdf_path.stem,
                "path": str(pdf_path),
                "reason": "hard_tail",
                "detail": f"score={final_score:.3f} iters={len(reviews)} worst={worst_dims[:2]}",
                "timestamp": time.time(),
            }, default=str)
            with open(_dr, "a") as _f:
                _f.write(_entry + "\n")
        except OSError:
            pass  # non-critical
    if question_book and reviews:
        # Get the last full review result (not the summary in reviews[])
        # Re-run review_pdf to get estimate_delta (cheap -- just scoring, no extraction)
        last_review_summary = reviews[-1]
        # Build a minimal last_review dict from the summary + any estimate_delta
        # from the most recent iteration
        last_review_for_defer = {
            "estimate_delta": last_review_summary.get("estimate_delta", {}),
            "margaret": {"verdict": last_review_summary.get("margaret_verdict", "UNKNOWN"), "says": ""},
            "jennifer": {"verdict": last_review_summary.get("jennifer_verdict", "UNKNOWN"), "says": ""},
        }
        deferred = defer_to_question_book(
            question_book=question_book,
            pdf_path=str(pdf_path),
            final_score=final_score,
            score_trajectory=score_trajectory,
            worst_dims=worst_dims,
            last_review=last_review_for_defer,
            iterations=len(reviews),
            max_iterations=max_iterations,
        )

    logger.info(
        f"Max iterations reached: verdict={final_verdict} score={final_score:.3f} "
        f"iterations={len(reviews)} trajectory={score_trajectory}"
    )
    print(
        f"review-pdf inline_review_loop exhausted "
        f"verdict={final_verdict} score={final_score:.3f} "
        f"iterations={len(reviews)} trajectory={score_trajectory} "
        f"pdf={pdf_path}",
        flush=True,
    )

    return {
        "pdf_path": str(pdf_path),
        "iterations": len(reviews),
        "final_verdict": final_verdict,
        "final_score": final_score,
        "converged": False,
        "deferred_to_question_book": deferred,
        "reviews": reviews,
        "remediation_actions": remediation_actions,
        "memory_edge_ids": memory_edge_ids,
        "score_trajectory": score_trajectory,
    }


if __name__ == "__main__":
    import typer

    def _cli(
        pdf_path: Path = typer.Argument(..., help="Path to the PDF file"),
        corpus_root: Path = typer.Option(Path(os.environ.get("EXTRACTOR_CORPUS", os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb") + "/extractor_corpus")), help="Corpus root directory"),
        extracted_runs_dir: Optional[Path] = typer.Option(None, help="Where to store extraction output"),
        max_iterations: int = typer.Option(DEFAULT_MAX_ITERATIONS, help="Maximum review-remediate cycles"),
        run_id: str = typer.Option("", help="Run identifier"),
        remediation_timeout: int = typer.Option(DEFAULT_REMEDIATION_TIMEOUT, help="Timeout per remediation job"),
        question_book: Optional[Path] = typer.Option(None, help="JSONL file for deferred questions (batch mode)"),
        output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """Inline PDF review loop."""
        result = review_loop(
            pdf_path=pdf_path,
            corpus_root=corpus_root,
            extracted_runs_dir=extracted_runs_dir,
            max_iterations=max_iterations,
            run_id=run_id,
            remediation_timeout=remediation_timeout,
            question_book=question_book,
        )

        if output_json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(f"PDF: {result['pdf_path']}")
            print(f"Iterations: {result['iterations']}")
            print(f"Final verdict: {result['final_verdict']}")
            print(f"Final score: {result['final_score']:.4f}")
            print(f"Converged: {result['converged']}")
            for r in result['reviews']:
                print(f"  Iter {r['iteration']}: {r['verdict']} (score={r['score']:.3f})")
            if result['remediation_actions']:
                completed = sum(1 for a in result['remediation_actions'] if a['status'] == 'completed')
                print(f"Remediation: {completed}/{len(result['remediation_actions'])} completed")
            if result['memory_edge_ids']:
                print(f"Memory edges: {len(result['memory_edge_ids'])}")

    typer.run(_cli)
