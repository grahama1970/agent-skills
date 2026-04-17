"""Batch tuning with convergence loop, watchdog, and corpus-report integration.

The heart of table-lab v2. Two key functions:
- tune_with_convergence(): iterative refinement for a single PDF
- tune_corpus(): batch loop with watchdog, checkpoint, and reporting
"""
from __future__ import annotations

import json
import multiprocessing
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from .bridge import format_memory_tags, tag_collection_dimensions, tag_extraction_result
from .checkpoint import TuneCheckpoint
from .config import (
    CONVERGENCE_SCORE_DELTA,
    CORPUS_MANIFEST_PATH,
    CORPUS_TUNE_RESULTS_PATH,
    MAX_CONVERGENCE_ITERATIONS,
    PDF_TUNE_TIMEOUT,
    WATCHDOG_CHECKPOINT_INTERVAL,
    WATCHDOG_STOP_FRAGMENTATION_RATE,
    WATCHDOG_WARN_FRAGMENTATION_RATE,
    CIRCUIT_BREAKER_MAX_FAILURES,
)
from .hints import normalize_hint_key, read_s00_profile, resolve_preset_category, save_hint
from .monitor import DebugTableTaskClient
from .tuner import TuneResult, tune
from .watchdog import WatchdogState, record_result as watchdog_record


def tune_with_convergence(
    pdf_path: Path,
    preset: str = "",
    category: str = "",
    max_iterations: int | None = None,
    score_delta: float | None = None,
) -> tuple[TuneResult, int, bool]:
    """Iterative refinement loop for a single PDF.

    Runs initial grid sweep, then refines around the best result
    if fragmentation > 0.

    Args:
        pdf_path: Path to the PDF.
        preset: S00 preset name.
        category: S00 category.
        max_iterations: Max convergence iterations (default from config).
        score_delta: Minimum score improvement to continue (default from config).

    Returns:
        (best_result, iterations_used, converged)
    """
    max_iter = max_iterations or MAX_CONVERGENCE_ITERATIONS
    delta = score_delta or CONVERGENCE_SCORE_DELTA

    # Iteration 1: full grid sweep
    result = tune(pdf_path, early_stop=True)
    best_result = result
    iterations = 1

    if not result.best_flavor or result.best_score < 0:
        return result, iterations, False

    # Already perfect — no refinement needed
    if result.best_fragmentation == 0:
        return result, iterations, True

    # Convergence loop: refine around best result
    prev_score = result.best_score

    for i in range(1, max_iter):
        iterations += 1

        # Build refined grid centered on best parameters
        if result.best_flavor == "lattice" and result.best_line_scale is not None:
            ls = result.best_line_scale
            refined_scales = sorted(set(
                v for v in range(max(1, ls - 5), ls + 6)
                if v not in [result.best_line_scale]  # skip already-tested exact value
            ))
            if not refined_scales:
                break
            refined = tune(
                pdf_path,
                lattice_scales=refined_scales,
                stream_tols=[],
                early_stop=True,
            )
        elif result.best_flavor == "stream" and result.best_edge_tol is not None:
            et = result.best_edge_tol
            refined_tols = sorted(set(
                v for v in range(max(1, et - 15), et + 16, 5)
                if v != result.best_edge_tol
            ))
            if not refined_tols:
                break
            refined = tune(
                pdf_path,
                lattice_scales=[],
                stream_tols=refined_tols,
                early_stop=True,
            )
        else:
            break

        # Check if refinement improved
        if refined.best_score > best_result.best_score:
            best_result = refined
            result = refined

        # Convergence check: stop if improvement < delta
        improvement = best_result.best_score - prev_score
        if improvement < delta:
            logger.info(f"Converged after {iterations} iterations "
                        f"(improvement {improvement:.1f} < delta {delta:.1f})")
            return best_result, iterations, True

        prev_score = best_result.best_score

        # Perfect result found during refinement
        if best_result.best_fragmentation == 0:
            return best_result, iterations, True

    return best_result, iterations, False


def _adaptive_timeout(pdf_path: Path, default_timeout: int) -> int:
    """Compute per-PDF timeout using S00's profile data.

    If S00 estimated a high table count, scale the timeout up from the default.
    This prevents large, table-heavy PDFs from being killed prematurely.
    """
    profile = read_s00_profile(pdf_path)
    if not profile:
        return default_timeout

    est_tables = profile.get("estimated_table_count", 0)
    page_count = profile.get("page_count", 0)

    # Base: 120s + 2s per page + 5s per estimated table region
    # The tuner probes fewer pages than S05, so per-table cost is lower
    estimated = 120 + page_count * 2 + est_tables * 5
    return max(estimated, default_timeout)


def _tune_worker(pdf_path_str: str, preset: str, category: str, max_iterations: int | None, result_file: str) -> None:
    """Worker function for multiprocessing timeout.

    Runs tune_with_convergence in a child process and writes result to a temp file.
    This allows the parent to kill the process if it hangs on a corrupted PDF.
    """
    try:
        pdf_path = Path(pdf_path_str)
        result, iterations, converged = tune_with_convergence(
            pdf_path, preset, category, max_iterations
        )
        data = {
            "status": "ok",
            "pdf_path": pdf_path_str,
            "best_flavor": result.best_flavor,
            "best_line_scale": result.best_line_scale,
            "best_edge_tol": result.best_edge_tol,
            "best_score": result.best_score,
            "best_fragmentation": result.best_fragmentation,
            "best_cell_count": result.best_cell_count,
            "pages_tested": result.pages_tested,
            "all_results": result.all_results,
            "tuned_at": result.tuned_at,
            "early_stop": result.early_stop,
            "iterations": iterations,
            "converged": converged,
        }
        Path(result_file).write_text(json.dumps(data))
    except Exception as exc:
        Path(result_file).write_text(json.dumps({
            "status": "error",
            "error": str(exc),
        }))


def _tune_with_timeout(
    pdf_path: Path,
    preset: str,
    category: str,
    max_iterations: int | None,
    timeout: int,
) -> tuple[bool, TuneResult | str | None, int, bool]:
    """Run tune_with_convergence in a child process with a hard timeout.

    Returns:
        (success, result_or_error, iterations, converged)
        If success is False, result_or_error is an error string.
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
        result_file = tmp.name

    proc = multiprocessing.Process(
        target=_tune_worker,
        args=(str(pdf_path), preset, category, max_iterations, result_file),
    )
    proc.start()
    proc.join(timeout=timeout)

    if proc.is_alive():
        logger.error(f"TIMEOUT: {pdf_path.name} exceeded {timeout}s — killing subprocess")
        proc.kill()
        proc.join(timeout=5)
        try:
            Path(result_file).unlink(missing_ok=True)
        except OSError:
            pass
        return False, f"timeout after {timeout}s", 0, False

    # Process completed — read result
    try:
        data = json.loads(Path(result_file).read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return False, f"failed to read result: {exc}", 0, False
    finally:
        try:
            Path(result_file).unlink(missing_ok=True)
        except OSError:
            pass

    if data.get("status") != "ok":
        return False, data.get("error", "unknown error"), 0, False

    # Reconstruct TuneResult from serialized data
    result = TuneResult(
        pdf_path=data.get("pdf_path", ""),
        best_flavor=data["best_flavor"],
        best_line_scale=data.get("best_line_scale"),
        best_edge_tol=data.get("best_edge_tol"),
        best_score=data["best_score"],
        best_fragmentation=data["best_fragmentation"],
        best_cell_count=data["best_cell_count"],
        pages_tested=data.get("pages_tested", []),
        all_results=data["all_results"],
        tuned_at=data.get("tuned_at", ""),
        early_stop=data.get("early_stop", False),
    )

    return True, result, data["iterations"], data["converged"]


def tune_corpus(
    corpus_dir: Path,
    task_name: str = "corpus_tune",
    glob_pattern: str = "**/*_clean.pdf",
    max_iterations: int | None = None,
    json_stream: bool = False,
    resume: bool = True,
) -> dict:
    """Batch tune all PDFs in a corpus directory with watchdog monitoring.

    Args:
        corpus_dir: Root directory to search for PDFs.
        task_name: Name for checkpoint/task-monitor.
        glob_pattern: Glob pattern for finding PDFs.
        max_iterations: Max convergence iterations per PDF.
        json_stream: If True, print NDJSON per result to stdout.
        resume: If True, resume from checkpoint.

    Returns:
        Summary dict with batch statistics.
    """
    # Discover PDFs
    pdfs = sorted(corpus_dir.glob(glob_pattern))
    if not pdfs:
        logger.warning(f"No PDFs found matching {glob_pattern} in {corpus_dir}")
        return {"error": "no_pdfs_found", "pattern": glob_pattern}

    logger.info(f"Found {len(pdfs)} PDFs to tune")

    # Initialize systems
    checkpoint = TuneCheckpoint.load_or_create(task_name, len(pdfs)) if resume else TuneCheckpoint(
        task_name=task_name, total_pdfs=len(pdfs)
    )
    watchdog = WatchdogState()
    monitor = DebugTableTaskClient(task_name, len(pdfs))

    skipped = 0

    for idx, pdf_path in enumerate(pdfs):
        pdf_name = pdf_path.name

        # Skip if already done
        if checkpoint.is_completed(pdf_name):
            skipped += 1
            continue

        # Check watchdog
        if watchdog.stopped:
            logger.error(f"Watchdog stopped: {watchdog.stop_reason}")
            break

        # Resolve preset/category from pipeline_context.json
        preset, category = resolve_preset_category(pdf_path)
        s05_key = normalize_hint_key(preset, category) if preset else ""

        # Tune with convergence (in subprocess with timeout for corrupted PDFs)
        timeout = _adaptive_timeout(pdf_path, PDF_TUNE_TIMEOUT)
        tune_ok, result, iterations, converged = _tune_with_timeout(
            pdf_path, preset, category, max_iterations, timeout,
        )

        if not tune_ok:
            error_msg = str(result) if result else "timeout"
            logger.error(f"Failed to tune {pdf_name}: {error_msg}")
            verdict = watchdog_record(
                watchdog, pdf_name,
                has_tables=False, table_count=0, cell_count=0,
                fragmentation=0, error=error_msg,
            )
            monitor.update(pdf_name, success=False)
            checkpoint.mark_completed(pdf_name, result={"error": error_msg, "pdf_name": pdf_name})
            if verdict == "stop":
                logger.error(f"Watchdog stopped: {watchdog.stop_reason}")
                break
            continue

        # Tag with Federated Taxonomy bridge attributes
        bridge_tags = tag_extraction_result(result)
        collection_tags = tag_collection_dimensions(result)

        # Save hint
        hint = result.to_hint(
            preset=preset, category=category,
            s05_key=s05_key, bridge_tags=bridge_tags,
        )
        save_hint(preset or "unknown", category or "unknown", hint)

        # Update checkpoint
        ndjson_record = result.to_ndjson_record(
            preset=preset, category=category,
            bridge_tags=bridge_tags,
            iterations=iterations, converged=converged,
        )
        checkpoint.mark_completed(pdf_name, result=ndjson_record)

        # Update task-monitor
        has_tables = result.best_score > 0
        monitor.update(pdf_name, success=has_tables)

        # Write to corpus-report NDJSON data contract
        _append_tune_result(ndjson_record)

        # Patch manifest.jsonl
        _patch_manifest(pdf_name, result, bridge_tags)

        # Record in watchdog
        verdict = watchdog_record(
            watchdog, pdf_name,
            has_tables=has_tables,
            table_count=sum(r.get("total_tables", 0) for r in result.all_results),
            cell_count=result.best_cell_count,
            fragmentation=result.best_fragmentation,
        )

        # NDJSON streaming
        if json_stream:
            print(json.dumps(ndjson_record), flush=True)

        # Periodic watchdog log
        processed = idx + 1 - skipped
        if processed > 0 and processed % WATCHDOG_CHECKPOINT_INTERVAL == 0:
            logger.info(f"Watchdog [{processed}/{len(pdfs)}]: "
                        f"frag_rate={watchdog.fragmentation_rate:.1%}, "
                        f"tables={watchdog.total_tables}, "
                        f"verdict={verdict}")

        if verdict == "warn":
            logger.warning(f"Watchdog warning: {watchdog.warnings[-1] if watchdog.warnings else 'unknown'}")
        elif verdict == "stop":
            logger.error(f"Watchdog stopped: {watchdog.stop_reason}")
            break

    # Finalize
    monitor.finish()
    summary = checkpoint.finalize()
    summary["watchdog"] = watchdog.to_dict()
    summary["skipped"] = skipped

    return summary


def _append_tune_result(record: dict) -> None:
    """Append a tune result to the corpus-level NDJSON file."""
    try:
        CORPUS_TUNE_RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CORPUS_TUNE_RESULTS_PATH, "a") as f:
            f.write(json.dumps(record) + "\n")
    except OSError as exc:
        logger.warning(f"Failed to write tune result to corpus: {exc}")


def _patch_manifest(pdf_name: str, result: TuneResult, bridge_tags: list[str]) -> None:
    """Patch manifest.jsonl entry with table tuning fields.

    Reads the manifest, finds the matching entry, adds s05_tune_* fields,
    and rewrites. This is an optional integration — failures are non-fatal.
    """
    if not CORPUS_MANIFEST_PATH.exists():
        return

    try:
        lines = CORPUS_MANIFEST_PATH.read_text().splitlines()
        updated = False
        new_lines = []

        for line in lines:
            if not line.strip():
                new_lines.append(line)
                continue
            try:
                entry = json.loads(line)
                filename = entry.get("filename", "")
                if pdf_name in filename or filename in pdf_name:
                    entry["s05_tune_strategy"] = (
                        f"{result.best_flavor}(ls={result.best_line_scale},et={result.best_edge_tol})"
                    )
                    entry["s05_tune_fragmentation"] = result.best_fragmentation
                    entry["s05_tune_bridge_tags"] = bridge_tags
                    updated = True
                new_lines.append(json.dumps(entry))
            except json.JSONDecodeError:
                new_lines.append(line)

        if updated:
            tmp = CORPUS_MANIFEST_PATH.with_suffix(".tmp")
            tmp.write_text("\n".join(new_lines) + "\n")
            tmp.rename(CORPUS_MANIFEST_PATH)

    except OSError as exc:
        logger.warning(f"Failed to patch manifest for {pdf_name}: {exc}")
