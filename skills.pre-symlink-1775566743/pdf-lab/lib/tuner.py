"""Convergence loop for pdf-lab.

The core algorithm:
1. Generate synthetic PDF reproducing detected patterns
2. Build parameter search space from patterns
3. Iterate: extract synthetic → measure delta → adjust params
4. If converged: return winning params (+ optional global fix write-back)
5. If not converged: return best-effort params

Two output paths:
- Runtime params: always returned for immediate re-extraction of THIS PDF
- Global fix: only written to pipeline code when proven systematic bug
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from .delta import ExtractionDelta, ReviewContext, Diagnosis, diagnose_delta
from .human import (
    HumanGuidance,
    should_escalate,
    escalate_to_human,
    apply_human_guidance,
    defer_question,
    lookup_guidance,
    load_answer_book,
)
from .params import TrialParams, build_param_space
from .synthetic import generate_synthetic, SyntheticSpec
from .writer import (
    WriteBackResult,
    write_fix_to_pipeline,
    store_in_memory,
    EXTRACTOR_ROOT,
    _build_runtime_params,
)


CONVERGENCE_THRESHOLD = 0.85  # Overall delta >= this = converged
FAILURE_RATE_THRESHOLD = 0.25  # If >25% of PDFs fail/defer, likely a pipeline bug


@dataclass
class TrialResult:
    """Result of a single extraction trial."""

    params: TrialParams
    delta: ExtractionDelta
    iteration: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "params": self.params.to_dict(),
            "delta": self.delta.to_dict(),
            "iteration": self.iteration,
        }


@dataclass
class TuneResult:
    """Final result of the convergence loop."""

    status: str  # "converged", "best_effort", "failed", "recalled"
    iterations: int = 0
    delta_before: float = 0.0
    delta_after: float = 0.0
    winning_params: Optional[TrialParams] = None
    write_back_result: Optional[WriteBackResult] = None
    runtime_params: Dict[str, Any] = field(default_factory=dict)
    synthetic_path: str = ""
    diagnosis: Optional[Diagnosis] = None
    trials: List[TrialResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "status": self.status,
            "iterations": self.iterations,
            "delta_before": round(self.delta_before, 4),
            "delta_after": round(self.delta_after, 4),
            "runtime_params": self.runtime_params,
            "synthetic_path": self.synthetic_path,
        }
        if self.winning_params:
            d["winning_params"] = self.winning_params.to_dict()
        if self.write_back_result:
            d["write_back_result"] = self.write_back_result.to_dict()
        if self.diagnosis:
            d["diagnosis"] = self.diagnosis.to_dict()
        d["trials"] = [t.to_dict() for t in self.trials]
        return d


def tune(
    pdf_path: Path,
    delta: ExtractionDelta,
    patterns: List[str],
    review_context: ReviewContext,
    max_iterations: int = 5,
    write_back: bool = False,
    dry_run: bool = False,
    converge: bool = True,
    interactive: bool = False,
    question_book: Optional[Path] = None,
    answer_book: Optional[Dict[str, HumanGuidance]] = None,
    batch_stats: Optional[Dict[str, int]] = None,
) -> TuneResult:
    """Run the convergence loop.

    Args:
        pdf_path: Path to the original PDF (for context)
        delta: The extraction delta to minimize
        patterns: Detected failure patterns
        review_context: Persona who flagged the issue
        max_iterations: Max convergence iterations
        write_back: Whether to write global fixes to pipeline code
        dry_run: Preview changes without writing
        converge: If False, just diagnose without tuning
        interactive: If True, escalate to human when stuck (via /interview + /pdf-screenshot).
            If False but question_book is set, defers questions to the book instead.
        question_book: Path to JSONL file for deferred questions (batch mode).
            When set and not interactive, stuck PDFs write questions here and skip.
        answer_book: Pre-loaded answers from a previous human review session.
            If guidance exists for this PDF, it's applied before the loop starts.
        batch_stats: Mutable dict tracking {"total": N, "failed": N, "deferred": N}
            across a batch run. If failure rate exceeds threshold, raises PipelineHaltError.

    Returns:
        TuneResult with winning params and optional write-back result
    """
    logger.info(
        f"Starting convergence loop: patterns={patterns}, "
        f"delta={delta.overall_delta:.2f}, max_iter={max_iterations}"
    )

    # Step 0: Diagnose
    diagnosis = diagnose_delta(delta, patterns, review_context.issue_codes)
    logger.info(f"Diagnosis: {diagnosis.root_cause}")

    # Step 0.5: Check answer book for pre-answered guidance (replay mode)
    if answer_book:
        pre_guidance = lookup_guidance(pdf_path, answer_book)
        if pre_guidance and pre_guidance.escalated:
            logger.info(f"Applying pre-answered guidance for {pdf_path.name}")
            if pre_guidance.skip_tuning:
                return TuneResult(
                    status="skipped_by_human",
                    delta_before=delta.overall_delta,
                    diagnosis=diagnosis,
                )
            # Apply guidance to patterns
            patterns, _ = apply_human_guidance(pre_guidance, patterns, {})
            # Re-diagnose with updated patterns
            diagnosis = diagnose_delta(delta, patterns, review_context.issue_codes)

    if not converge:
        return TuneResult(
            status="diagnosed",
            delta_before=delta.overall_delta,
            diagnosis=diagnosis,
        )

    # Step 1: Check /memory for known solutions
    recalled = _recall_from_memory(patterns)
    if recalled:
        logger.info(f"Recalled solution from /memory for patterns {patterns}")
        return TuneResult(
            status="recalled",
            delta_before=delta.overall_delta,
            winning_params=TrialParams.from_dict(recalled.get("winning_params", {})),
            runtime_params=recalled.get("winning_params", {}),
            diagnosis=diagnosis,
        )

    # Step 2: Generate synthetic PDF
    try:
        synthetic_pdf, synthetic_spec = generate_synthetic(
            patterns=patterns,
            target_sections=max(8, delta.estimated_sections // 3),
            target_tables=max(2, delta.estimated_tables),
            target_figures=max(1, delta.estimated_figures),
        )
    except Exception as e:
        logger.error(f"Synthetic generation failed: {e}")
        return TuneResult(
            status="failed",
            delta_before=delta.overall_delta,
            diagnosis=diagnosis,
        )

    # Step 3: Build parameter search space
    param_space = build_param_space(patterns, delta.overall_delta)

    # Step 4: Convergence loop
    best_result: Optional[TrialResult] = None
    correction_context: Dict[str, Any] = {}
    trials: List[TrialResult] = []
    consecutive_errors = 0
    MAX_CONSECUTIVE_ERRORS = 3
    delta_history: List[float] = []
    human_escalated = False  # Only escalate once per tune session
    human_guidance: Optional[HumanGuidance] = None

    for iteration in range(1, max_iterations + 1):
        logger.info(f"Iteration {iteration}/{max_iterations}")

        # Get next trial parameters
        trial_params = param_space.next_trial(correction_context if iteration > 1 else None)

        # Extract synthetic with trial parameters
        extraction_result = _extract_pdf(synthetic_pdf, trial_params)

        # Check for extraction errors
        if extraction_result.get("error"):
            consecutive_errors += 1
            logger.warning(
                f"  Trial {iteration}: extraction error ({consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}): "
                f"{extraction_result['error']}"
            )

            # Human escalation on repeated errors (before aborting)
            if (
                (interactive or question_book)
                and not human_escalated
                and consecutive_errors >= 2
            ):
                human_guidance = _try_human_escalation(
                    pdf_path, delta, diagnosis, trials, iteration,
                    max_iterations, consecutive_errors,
                    interactive=interactive,
                    question_book=question_book,
                    batch_stats=batch_stats,
                )
                human_escalated = True
                if human_guidance and human_guidance.skip_tuning:
                    logger.info("Human requested to stop tuning.")
                    break

            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                logger.error(
                    f"Aborting convergence: {MAX_CONSECUTIVE_ERRORS} consecutive extraction errors"
                )
                break
            continue
        consecutive_errors = 0

        # Compute delta against known synthetic structure
        synthetic_delta = _compute_synthetic_delta(synthetic_spec, extraction_result)

        trial = TrialResult(
            params=trial_params,
            delta=synthetic_delta,
            iteration=iteration,
        )
        trials.append(trial)
        delta_history.append(synthetic_delta.overall_delta)

        logger.info(
            f"  Trial {iteration}: delta={synthetic_delta.overall_delta:.2f} "
            f"(sections={synthetic_delta.section_delta:.2f}, "
            f"tables={synthetic_delta.table_delta:.2f})"
        )

        # Track best result
        if best_result is None or synthetic_delta.overall_delta > best_result.delta.overall_delta:
            best_result = trial

        # Check convergence
        if synthetic_delta.overall_delta >= CONVERGENCE_THRESHOLD:
            logger.info(f"Converged at iteration {iteration}!")
            break

        # Build correction context for next iteration
        correction_context = _analyze_failures(synthetic_delta, trial_params)

        # Human escalation: check if we're stuck and should ask the human
        if (
            (interactive or question_book)
            and not human_escalated
            and should_escalate(
                iteration=iteration,
                best_delta=best_result.delta.overall_delta if best_result else 0.0,
                current_delta=synthetic_delta.overall_delta,
                delta_history=delta_history,
                consecutive_errors=consecutive_errors,
                diagnosis=diagnosis,
            )
        ):
            human_guidance = _try_human_escalation(
                pdf_path, delta, diagnosis, trials, iteration,
                max_iterations, consecutive_errors,
                interactive=interactive,
                question_book=question_book,
                batch_stats=batch_stats,
            )
            human_escalated = True

            if human_guidance and human_guidance.skip_tuning:
                logger.info("Human requested to stop tuning.")
                break

            if human_guidance and human_guidance.escalated:
                # Apply human guidance to patterns and correction context
                patterns, correction_context = apply_human_guidance(
                    human_guidance, patterns, correction_context,
                )
                # Rebuild param space with updated patterns
                if human_guidance.pattern_overrides:
                    param_space = build_param_space(patterns, delta.overall_delta)

    if best_result is None:
        return TuneResult(
            status="failed",
            delta_before=delta.overall_delta,
            diagnosis=diagnosis,
            synthetic_path=str(synthetic_pdf),
            trials=trials,
        )

    converged = best_result.delta.overall_delta >= CONVERGENCE_THRESHOLD
    status = "converged" if converged else "best_effort"
    delta_after = best_result.delta.overall_delta

    # Step 5: Write-back (global fixes only) or return runtime params
    wb_result = None
    if write_back and delta_after > delta.overall_delta:
        wb_result = write_fix_to_pipeline(
            winning_params=best_result.params,
            patterns=patterns,
            delta=delta,
            diagnosis=diagnosis,
            review_context=review_context,
            new_delta_value=delta_after,
            dry_run=dry_run,
        )
    elif write_back:
        logger.info("No improvement found — skipping write-back.")

    # Step 6: Store in /memory (always)
    store_in_memory(
        winning_params=best_result.params,
        patterns=patterns,
        delta=delta,
        review_context=review_context,
        synthetic_path=str(synthetic_pdf),
        diagnosis=diagnosis,
        convergence_result={
            "status": status,
            "delta_after": delta_after,
            "iterations": len(trials),
        },
    )

    # Build runtime params (per-PDF tuning — always available)
    runtime_params = wb_result.runtime_params if wb_result else _build_runtime_params(best_result.params, patterns)

    return TuneResult(
        status=status,
        iterations=len(trials),
        delta_before=delta.overall_delta,
        delta_after=delta_after,
        winning_params=best_result.params,
        write_back_result=wb_result,
        runtime_params=runtime_params,
        synthetic_path=str(synthetic_pdf),
        diagnosis=diagnosis,
        trials=trials,
    )


class PipelineHaltError(Exception):
    """Raised when too many PDFs fail/defer, suggesting a pipeline-level bug."""

    def __init__(self, total: int, failed: int, deferred: int, rate: float):
        self.total = total
        self.failed = failed
        self.deferred = deferred
        self.rate = rate
        super().__init__(
            f"Pipeline halt: {failed + deferred}/{total} PDFs failed/deferred "
            f"({rate:.0%} > {FAILURE_RATE_THRESHOLD:.0%} threshold). "
            f"This looks like a pipeline bug, not individual PDF issues."
        )


def _check_batch_health(batch_stats: Optional[Dict[str, int]]) -> None:
    """Check if failure rate exceeds threshold — halt if likely pipeline bug."""
    if not batch_stats:
        return

    total = batch_stats.get("total", 0)
    if total < 4:  # Need minimum sample before triggering
        return

    failed = batch_stats.get("failed", 0)
    deferred = batch_stats.get("deferred", 0)
    rate = (failed + deferred) / total

    if rate > FAILURE_RATE_THRESHOLD:
        raise PipelineHaltError(total, failed, deferred, rate)


def _try_human_escalation(
    pdf_path: Path,
    delta: ExtractionDelta,
    diagnosis: Diagnosis,
    trials: List[TrialResult],
    iteration: int,
    max_iterations: int,
    consecutive_errors: int,
    *,
    interactive: bool = True,
    question_book: Optional[Path] = None,
    batch_stats: Optional[Dict[str, int]] = None,
) -> Optional[HumanGuidance]:
    """Attempt human escalation — interactive or deferred.

    Interactive mode: blocks and launches /interview immediately.
    Deferred mode (question_book set, not interactive): writes question
    to the book and returns a "deferred" guidance that tells the caller
    to skip this PDF.
    """
    if not interactive and question_book:
        # Deferred mode: write to book, skip PDF
        try:
            defer_question(
                pdf_path=pdf_path,
                delta=delta,
                diagnosis=diagnosis,
                trials_so_far=[t.to_dict() for t in trials],
                iteration=iteration,
                max_iterations=max_iterations,
                consecutive_errors=consecutive_errors,
                book_path=question_book,
            )
            if batch_stats is not None:
                batch_stats["deferred"] = batch_stats.get("deferred", 0) + 1
                _check_batch_health(batch_stats)
        except PipelineHaltError:
            raise  # Let this propagate up
        except Exception as e:
            logger.warning(f"Failed to defer question: {e}")

        # Return guidance that tells the loop to skip
        return HumanGuidance(escalated=True, skip_tuning=True)

    # Interactive mode: block and ask
    try:
        guidance = escalate_to_human(
            pdf_path=pdf_path,
            delta=delta,
            diagnosis=diagnosis,
            trials_so_far=[t.to_dict() for t in trials],
            iteration=iteration,
            max_iterations=max_iterations,
            consecutive_errors=consecutive_errors,
        )
        if guidance.escalated:
            return guidance
        logger.info("Human escalation skipped (skill unavailable or no response)")
        return None
    except Exception as e:
        logger.warning(f"Human escalation failed: {e}")
        return None


def _extract_pdf(pdf_path: Path, params: TrialParams) -> Dict[str, Any]:
    """Extract a PDF using the pipeline with given parameters.

    Sets environment variables from params and runs the extractor.
    Returns extraction counts.
    """
    if not EXTRACTOR_ROOT.is_dir():
        logger.error(f"EXTRACTOR_ROOT not found: {EXTRACTOR_ROOT}")
        return {"sections": 0, "tables": 0, "figures": 0, "pages": 0, "error": "EXTRACTOR_ROOT missing"}

    pipeline_script = EXTRACTOR_ROOT / "src" / "extractor" / "pipeline" / "run_pipeline.py"
    if not pipeline_script.exists():
        logger.error(f"Pipeline script not found: {pipeline_script}")
        return {"sections": 0, "tables": 0, "figures": 0, "pages": 0, "error": "pipeline script missing"}

    env = dict(os.environ)

    # Apply env overrides from trial params
    for key, value in params.env.items():
        env[key] = str(value)

    # Use a temp output directory
    with tempfile.TemporaryDirectory(prefix="pdf_lab_extract_") as tmpdir:
        output_dir = Path(tmpdir)

        try:
            # Run pipeline stages S00 + S02 + S04 + S05 (fast subset)
            result = subprocess.run(
                [
                    "python", "-m", "extractor.pipeline.run_pipeline",
                    str(pdf_path),
                    "-o", str(output_dir),
                    "--steps", "s00,s02,s04,s05",
                ],
                env=env,
                cwd=str(EXTRACTOR_ROOT),
                capture_output=True,
                text=True,
                timeout=120,
            )

            # Parse results from output directory
            return _parse_extraction_results(output_dir)

        except subprocess.TimeoutExpired:
            logger.warning("Extraction timed out (120s)")
            return {"sections": 0, "tables": 0, "figures": 0, "pages": 0, "error": "timeout"}
        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            return {"sections": 0, "tables": 0, "figures": 0, "pages": 0, "error": str(e)}


def _parse_extraction_results(output_dir: Path) -> Dict[str, Any]:
    """Parse extraction results from pipeline output directory."""
    results: Dict[str, Any] = {"sections": 0, "tables": 0, "figures": 0, "pages": 0}

    # Try S04 section output
    s04_dir = output_dir / "04_section_builder"
    if s04_dir.exists():
        for json_file in s04_dir.glob("*.json"):
            try:
                data = json.loads(json_file.read_text())
                if isinstance(data, dict):
                    results["sections"] = len(data.get("sections", []))
                elif isinstance(data, list):
                    results["sections"] = len(data)
                break
            except Exception:
                continue

    # Try S05 table output
    s05_dir = output_dir / "05_table_extractor"
    if s05_dir.exists():
        for json_file in s05_dir.glob("*.json"):
            try:
                data = json.loads(json_file.read_text())
                if isinstance(data, dict):
                    results["tables"] = len(data.get("tables", []))
                elif isinstance(data, list):
                    results["tables"] = len(data)
                break
            except Exception:
                continue

    # Try S00 profile for page count
    s00_dir = output_dir / "00_profile_detector"
    if s00_dir.exists():
        profile_file = s00_dir / "profile.json"
        if profile_file.exists():
            try:
                data = json.loads(profile_file.read_text())
                results["pages"] = data.get("page_count", 0)
            except Exception as e:
                logger.debug("result extraction failed: {}", e)

    return results


def _compute_synthetic_delta(
    spec: SyntheticSpec, extraction: Dict[str, Any]
) -> ExtractionDelta:
    """Compute delta between known synthetic structure and extraction result."""
    return ExtractionDelta(
        estimated_sections=spec.sections,
        estimated_tables=spec.tables,
        estimated_figures=spec.figures,
        estimated_pages=spec.pages,
        actual_sections=extraction.get("sections", 0),
        actual_tables=extraction.get("tables", 0),
        actual_figures=extraction.get("figures", 0),
        actual_pages=extraction.get("pages", spec.pages),
    )


def _analyze_failures(
    delta: ExtractionDelta, params: TrialParams
) -> Dict[str, Any]:
    """Analyze what went wrong in this trial to guide the next one."""
    ctx: Dict[str, Any] = {}

    if delta.section_delta < 0.7:
        ctx["section_undercount"] = True
    elif delta.section_ratio_raw > 1.5:
        ctx["section_overcount"] = True

    if delta.table_delta < 0.7:
        ctx["table_undercount"] = True
    elif delta.table_ratio_raw > 1.5:
        ctx["table_overcount"] = True

    if delta.table_delta < 0.5 and delta.section_delta > 0.8:
        ctx["table_boundary_issues"] = True

    return ctx


def _recall_from_memory(patterns: List[str]) -> Optional[Dict[str, Any]]:
    """Check /memory for a known solution to these patterns."""
    memory_cli = Path(os.environ.get(
        "MEMORY_SKILLS_DIR",
        str(Path.home() / "workspace/experiments/memory/.agents/skills"),
    )) / "memory"

    if not (memory_cli / "run.sh").exists():
        return None

    try:
        query = f"pdf_lab convergence patterns [{', '.join(patterns)}]"
        result = subprocess.run(
            [str(memory_cli / "run.sh"), "recall", "--q", query, "--k", "3"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            # Parse recalled solution
            for line in result.stdout.strip().split("\n"):
                try:
                    data = json.loads(line)
                    if data.get("status") == "converged":
                        return data
                except (json.JSONDecodeError, KeyError):
                    continue
    except Exception as e:
        logger.debug(f"Memory recall failed (non-fatal): {e}")

    return None
