#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "typer>=0.12.3",
#   "loguru>=0.7.0",
# ]
# ///
"""learn-datalake orchestrator.

Purpose:
- Provide one user-facing entrypoint that continuously learns a document directory
  into graph memory while maintaining PDF extraction quality.

Inputs:
- Root content directory and runtime options.

Outputs:
- Invokes review-pdf quality loops for PDFs and memory acquire for non-PDF files.

Failure modes:
- Subprocess failures are surfaced as non-zero exits in strict modes.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import typer
from loguru import logger

from config import (
    SECTOR_KEYS,
    SKILLS_DIR as _SKILLS_DIR,
    STATE_DIR,
    TASK_MONITOR_STATE_DIR,
    CommandResult,
    ReviewConfig,
)
from corpus_analysis import (
    coverage_report,
    downloaded_url_set,
    next_expansion_batch_dir,
    read_candidate_urls,
    run_fetcher_manifest,
    urls_by_sector,
    write_manifest,
)
from storage import archive_extracted_to_hdd, setup_nvme_staging
from subprocess_exec import ensure_not_stalled
from task_monitor_client import (
    tm_add_accomplishment,
    tm_end_session,
    tm_register_task,
    tm_start_session,
    write_task_state,
)
from worker_pool import (
    resolve_workers,
    run_parallel_review,
    run_review_pdf_once,
    summarize_review_output,
)

app = typer.Typer(no_args_is_help=True, add_completion=False)
quarantine_app = typer.Typer(no_args_is_help=True, add_completion=False, help="Review and resolve quarantined PDFs.")
app.add_typer(quarantine_app, name="review-quarantine")

MEMORY_SOCKET = "/run/user/1000/embry/memory.sock"
MEMORY_BASE_URL = "http://localhost"
COMPUTE_DELTA_SCRIPT = Path(__file__).resolve().parent.parent / "create-evidence-case" / "tools" / "compute_threat_delta.py"
SKILL_DIR = Path(__file__).resolve().parent


@app.command("once")
def cmd_once(
    root: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True),
    target_score: float = typer.Option(0.95, min=0.0, max=1.0),
    target_fail_ratio: float = typer.Option(0.01, min=0.0, max=1.0),
    execute_jobs: bool = typer.Option(True),
    ingest_memory: bool = typer.Option(True),
    memory_scope_pdf: str = typer.Option("datalake_pdf"),
    taxonomy_collection: str = typer.Option("operational"),
    task_monitor: bool = typer.Option(True),
    task_monitor_project: str = typer.Option("datalake_training"),
    task_monitor_strict: bool = typer.Option(True),
    watchdog_seconds: int = typer.Option(900, min=30),
    watchdog_poll_seconds: int = typer.Option(15, min=1),
    review_incremental: bool = typer.Option(True),
    inline_review: bool = typer.Option(False, help="Enable inline persona review after each PDF extraction"),
    extract_missing: bool = typer.Option(True, help="Extract un-profiled PDFs during discovery"),
) -> None:
    """Run one datalake learning cycle."""
    cfg = ReviewConfig(
        root=root,
        target_score=target_score,
        target_fail_ratio=target_fail_ratio,
        poll_seconds=300,
        execute_jobs=execute_jobs,
        ingest_memory=ingest_memory,
        memory_scope=memory_scope_pdf,
        taxonomy_collection=taxonomy_collection,
        watchdog_seconds=watchdog_seconds,
        watchdog_poll_seconds=watchdog_poll_seconds,
        review_incremental=review_incremental,
        inline_review=inline_review,
        extract_missing=extract_missing,
    )
    cycle_state = TASK_MONITOR_STATE_DIR / "learn_datalake_once_cycle.json"
    review_state = TASK_MONITOR_STATE_DIR / "learn_datalake_once_review_pdf.json"

    tm_start_session(project=task_monitor_project, enabled=task_monitor, strict=task_monitor_strict)
    tm_register_task(
        name="learn_datalake_once_cycle", state_file=cycle_state, total=1,
        description="One-shot datalake learning cycle",
        project=task_monitor_project, enabled=task_monitor, strict=task_monitor_strict,
    )
    tm_register_task(
        name="learn_datalake_once_review_pdf", state_file=review_state, total=1,
        description="review-pdf one-shot pass",
        project=task_monitor_project, enabled=task_monitor, strict=task_monitor_strict,
    )

    review = CommandResult(cmd="", returncode=1, stdout="", stderr="")
    final_notes = "learn-datalake once failed"
    try:
        write_task_state(
            cycle_state,
            {"completed": 0, "stats": {"phase": "review_pdf"}, "current_item": str(root)},
        )
        review = run_review_pdf_once(cfg, state_file=review_state)
        ensure_not_stalled(review, "review-pdf")
        if review.stderr.strip():
            logger.info(review.stderr.splitlines()[-1])
        write_task_state(
            review_state,
            {
                "completed": 1,
                "stats": {"returncode": review.returncode},
                "current_item": str(root),
                "consecutive_failures": 1 if review.returncode != 0 else 0,
            },
        )

        # Post-ingestion taxonomy validation gate
        _validate_taxonomy_coverage(memory_scope_pdf)
        _run_threat_delta_check()

        write_task_state(
            cycle_state,
            {
                "completed": 1,
                "stats": {
                    "review_returncode": review.returncode,
                },
                "current_item": str(root),
                "consecutive_failures": 1 if review.returncode != 0 else 0,
            },
        )
        if review.returncode != 0:
            final_notes = "learn-datalake once completed with failures"
            raise typer.Exit(code=1)

        final_notes = "learn-datalake once completed"
        tm_add_accomplishment(
            text=(
                f"one-shot cycle complete root={root} "
                f"review_rc={review.returncode}"
            ),
            enabled=task_monitor, strict=task_monitor_strict,
        )
    finally:
        tm_end_session(notes=final_notes, enabled=task_monitor, strict=task_monitor_strict)


@app.command("start")
def cmd_start(
    root: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True),
    target_score: float = typer.Option(0.95, min=0.0, max=1.0),
    target_fail_ratio: float = typer.Option(0.01, min=0.0, max=1.0),
    poll_seconds: int = typer.Option(300, min=10),
    execute_jobs: bool = typer.Option(True),
    ingest_memory: bool = typer.Option(True),
    memory_scope_pdf: str = typer.Option("datalake_pdf"),
    taxonomy_collection: str = typer.Option("operational"),
    task_monitor: bool = typer.Option(True),
    task_monitor_project: str = typer.Option("datalake_training"),
    task_monitor_strict: bool = typer.Option(True),
    watchdog_seconds: int = typer.Option(900, min=30),
    watchdog_poll_seconds: int = typer.Option(15, min=1),
    review_incremental: bool = typer.Option(True),
    workers: int = typer.Option(0, min=0),
    inline_review: bool = typer.Option(False, help="Enable inline persona review after each PDF extraction"),
    extract_missing: bool = typer.Option(True, help="Extract un-profiled PDFs during discovery"),
) -> None:
    """Continuously learn directory content into memory and monitor PDF quality."""
    effective_workers = resolve_workers(workers)
    cfg = ReviewConfig(
        root=root,
        target_score=target_score,
        target_fail_ratio=target_fail_ratio,
        poll_seconds=poll_seconds,
        execute_jobs=execute_jobs,
        ingest_memory=ingest_memory,
        memory_scope=memory_scope_pdf,
        taxonomy_collection=taxonomy_collection,
        watchdog_seconds=watchdog_seconds,
        watchdog_poll_seconds=watchdog_poll_seconds,
        review_incremental=review_incremental,
        inline_review=inline_review,
        extract_missing=extract_missing,
    )
    cycle_state = TASK_MONITOR_STATE_DIR / "learn_datalake_start_cycle.json"
    review_state = TASK_MONITOR_STATE_DIR / "learn_datalake_start_review_pdf.json"

    tm_start_session(project=task_monitor_project, enabled=task_monitor, strict=task_monitor_strict)
    tm_register_task(
        name="learn_datalake_start_cycle", state_file=cycle_state, total=None,
        description=f"Continuous learn-datalake cycles (workers={effective_workers})",
        project=task_monitor_project, enabled=task_monitor, strict=task_monitor_strict,
    )
    tm_register_task(
        name="learn_datalake_start_review_pdf", state_file=review_state, total=None,
        description=f"Continuous review-pdf cycle runs (workers={effective_workers})",
        project=task_monitor_project, enabled=task_monitor, strict=task_monitor_strict,
    )

    setup_nvme_staging()

    print(f"watch_root={root}")
    print(f"target_score={target_score:.3f}")
    print(f"poll_seconds={poll_seconds}")
    print(f"workers={effective_workers}")

    # Write initial heartbeat so supervisor sees us alive from the start.
    # Without this, the first review cycle (which may take 30+ min for extraction)
    # never writes review_state, and supervisor kills us with heartbeat_timeout_startup.
    write_task_state(
        review_state,
        {
            "completed": 0,
            "stats": {"status": "starting", "workers": effective_workers},
            "current_item": "startup",
            "consecutive_failures": 0,
        },
    )

    cycle_count = 0
    cycle_failures = 0
    try:
        while True:
            cycle_count += 1
            write_task_state(
                cycle_state,
                {
                    "completed": cycle_count - 1,
                    "stats": {"cycle_failures": cycle_failures, "workers": effective_workers},
                    "current_item": f"cycle_{cycle_count}",
                    "consecutive_failures": cycle_failures,
                },
            )

            if effective_workers > 1:
                review_rc, review_summary = _run_parallel_cycle(
                    cfg, effective_workers, review_state, cycle_count,
                )
            else:
                review_rc, review_summary = _run_sequential_cycle(
                    cfg, review_state, cycle_count,
                )
                _run_threat_delta_check()

            if review_rc != 0:
                cycle_failures += 1
            else:
                cycle_failures = 0

            write_task_state(
                cycle_state,
                {
                    "completed": cycle_count,
                    "stats": {
                        "cycle_failures": cycle_failures,
                        "last_review_returncode": review_rc,
                        "last_extracted_new_max": review_summary.get("extracted_new_max", 0),
                        "last_timeout_count": review_summary.get("timeout_count", 0),
                        "workers": effective_workers,
                    },
                    "current_item": f"cycle_{cycle_count}",
                    "consecutive_failures": cycle_failures,
                },
            )
            tm_add_accomplishment(
                text=(
                    f"cycle={cycle_count} review_rc={review_rc} "
                    f"workers={effective_workers} "
                    f"consecutive_failures={cycle_failures}"
                ),
                enabled=task_monitor, strict=task_monitor_strict,
            )
            archived_count = archive_extracted_to_hdd()
            if archived_count:
                print(f"cycle={cycle_count} archived_to_hdd={archived_count}", flush=True)

            time.sleep(poll_seconds)
    finally:
        tm_end_session(
            notes=f"learn-datalake start stopped after cycles={cycle_count} workers={effective_workers}",
            enabled=task_monitor, strict=task_monitor_strict,
        )


def _run_parallel_cycle(
    cfg: ReviewConfig,
    effective_workers: int,
    review_state: Path,
    cycle_count: int,
) -> tuple[int, Dict]:
    """Execute a parallel review cycle, returning (returncode, summary)."""
    # Heartbeat before long-running parallel review so supervisor knows we're alive
    write_task_state(
        review_state,
        {
            "completed": cycle_count - 1,
            "stats": {"status": "parallel_review_starting", "workers": effective_workers},
            "current_item": f"cycle_{cycle_count}_starting",
            "consecutive_failures": 0,
        },
    )
    parallel = run_parallel_review(
        cfg=cfg, workers=effective_workers, state_file_base=review_state,
    )
    if parallel.any_stalled or parallel.any_timed_out:
        logger.error(
            f"parallel review watchdog failure "
            f"stalled={parallel.any_stalled} timed_out={parallel.any_timed_out}"
        )
        raise typer.Exit(code=2)

    review_summary = parallel.aggregate_summary
    review_rc = parallel.worst_returncode

    write_task_state(
        review_state,
        {
            "completed": cycle_count,
            "stats": {
                "review_returncode": review_rc,
                "extracted_new_max": review_summary.get("extracted_new_max", 0),
                "timeout_count": review_summary.get("timeout_count", 0),
                "discover_scanned_max": review_summary.get("discover_scanned_max", 0),
                "discover_new_max": review_summary.get("discover_new_max", 0),
                "incremental_skipped": review_summary.get("incremental_skipped", False),
                "changed_pdfs": review_summary.get("changed_pdfs", 0),
                "workers_used": parallel.workers_used,
                "pending_pdf_count": parallel.pending_pdf_count,
            },
            "current_item": f"cycle_{cycle_count}",
            "consecutive_failures": 0,
        },
    )
    print(
        f"cycle={cycle_count} review_rc={review_rc} "
        f"workers_used={parallel.workers_used} "
        f"pending_pdfs={parallel.pending_pdf_count} "
        f"extracted_new_total={review_summary.get('extracted_new_max', 0)} "
        f"timeout_count={review_summary.get('timeout_count', 0)}",
        flush=True,
    )
    return review_rc, review_summary


def _run_sequential_cycle(
    cfg: ReviewConfig,
    review_state: Path,
    cycle_count: int,
) -> tuple[int, Dict]:
    """Execute a sequential (single-worker) review cycle."""
    # Heartbeat before long-running review so supervisor knows we're alive
    write_task_state(
        review_state,
        {
            "completed": cycle_count - 1,
            "stats": {"status": "sequential_review_starting"},
            "current_item": f"cycle_{cycle_count}_starting",
            "consecutive_failures": 0,
        },
    )
    review = run_review_pdf_once(cfg, state_file=review_state)
    ensure_not_stalled(review, "review-pdf")
    review_summary = summarize_review_output(review)

    if (
        cfg.review_incremental
        and review_summary["incremental_skipped"]
        and int(review_summary["changed_pdfs"]) == 0
    ):
        print(
            "review-pdf backlog_pass_triggered "
            "reason=incremental_skip_no_changes mode=full",
            flush=True,
        )
        full_cfg = ReviewConfig(
            root=cfg.root,
            target_score=cfg.target_score,
            target_fail_ratio=cfg.target_fail_ratio,
            poll_seconds=cfg.poll_seconds,
            execute_jobs=cfg.execute_jobs,
            ingest_memory=cfg.ingest_memory,
            memory_scope=cfg.memory_scope,
            taxonomy_collection=cfg.taxonomy_collection,
            watchdog_seconds=cfg.watchdog_seconds,
            watchdog_poll_seconds=cfg.watchdog_poll_seconds,
            review_incremental=False,
        )
        full_pass = run_review_pdf_once(full_cfg, state_file=review_state)
        ensure_not_stalled(full_pass, "review-pdf-full-pass")
        review = full_pass
        review_summary = summarize_review_output(review)

    if review.stderr.strip():
        logger.info(review.stderr.splitlines()[-1])
    review_rc = review.returncode

    write_task_state(
        review_state,
        {
            "completed": cycle_count,
            "stats": {
                "review_returncode": review_rc,
                "extracted_new_max": review_summary["extracted_new_max"],
                "timeout_count": review_summary["timeout_count"],
                "discover_scanned_max": review_summary["discover_scanned_max"],
                "discover_new_max": review_summary["discover_new_max"],
                "incremental_skipped": review_summary["incremental_skipped"],
                "changed_pdfs": review_summary["changed_pdfs"],
            },
            "current_item": f"cycle_{cycle_count}",
            "consecutive_failures": 0,
        },
    )
    print(
        f"cycle={cycle_count} review_rc={review_rc} "
        f"extracted_new_max={review_summary['extracted_new_max']} "
        f"timeout_count={review_summary['timeout_count']} "
        f"scanned_max={review_summary['discover_scanned_max']} "
        f"incremental_skipped={str(review_summary['incremental_skipped']).lower()} "
        f"changed_pdfs={review_summary['changed_pdfs']}",
        flush=True,
    )
    _validate_taxonomy_coverage(cfg.memory_scope)
    _run_threat_delta_check()
    return review_rc, review_summary


@app.command("assess-coverage")
def cmd_assess_coverage(
    root: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True),
    target_pdf_per_sector: int = typer.Option(500, min=1),
    output_json: Path = typer.Option(STATE_DIR / "coverage" / "coverage_latest.json"),
) -> None:
    """Assess datalake corpus coverage and write a machine-readable report."""
    report = coverage_report(root, target_pdf_per_sector)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    sectors_below = report["sectors"]["sectors_below_target"]
    print(
        f"coverage_report={output_json} "
        f"pdf_total={report['totals']['pdf']} "
        f"sectors_below_target={len(sectors_below)}"
    )
    if sectors_below:
        print("sectors_below_target=" + ",".join(sectors_below))


@app.command("plan-gap-download")
def cmd_plan_gap_download(
    root: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True),
    target_pdf_per_sector: int = typer.Option(500, min=1),
    per_sector_limit: int = typer.Option(250, min=1),
    output_manifest: Path = typer.Option(STATE_DIR / "coverage" / "gap_manifest_urls.txt"),
    output_plan_json: Path = typer.Option(STATE_DIR / "coverage" / "gap_plan.json"),
    execute_fetch: bool = typer.Option(False),
    fetch_output_dir: Optional[Path] = typer.Option(None),
    task_monitor: bool = typer.Option(True),
    task_monitor_project: str = typer.Option("datalake_training"),
    task_monitor_strict: bool = typer.Option(True),
    watchdog_seconds: int = typer.Option(900, min=30),
    watchdog_poll_seconds: int = typer.Option(15, min=1),
) -> None:
    """Plan and optionally execute URL downloads to fill sector PDF gaps."""
    report = coverage_report(root, target_pdf_per_sector)
    sector_gap_counts = report["sectors"]["pdf_gap_counts"]
    downloaded = downloaded_url_set(root)
    candidates = read_candidate_urls()
    grouped = urls_by_sector(candidates)

    selected_urls: List[str] = []
    selected_by_sector: Dict[str, int] = {}
    available_by_sector: Dict[str, int] = {}

    for sector in SECTOR_KEYS:
        need = sector_gap_counts.get(sector, 0)
        if need <= 0:
            selected_by_sector[sector] = 0
            available_by_sector[sector] = len(grouped.get(sector, []))
            continue
        pool = [url for url in grouped.get(sector, []) if url not in downloaded]
        available_by_sector[sector] = len(pool)
        take = min(need, per_sector_limit, len(pool))
        chosen = pool[:take]
        selected_urls.extend(chosen)
        selected_by_sector[sector] = len(chosen)

    seen: set[str] = set()
    final_urls: List[str] = []
    for url in selected_urls:
        if url in seen:
            continue
        seen.add(url)
        final_urls.append(url)
    final_urls_by_sector = urls_by_sector(final_urls)

    write_manifest(output_manifest, final_urls)
    plan_payload = {
        "root": str(root),
        "timestamp": int(time.time()),
        "target_pdf_per_sector": target_pdf_per_sector,
        "per_sector_limit": per_sector_limit,
        "coverage_report": report,
        "candidate_urls_total": len(candidates),
        "already_downloaded_urls": len(downloaded),
        "selected_manifest_path": str(output_manifest),
        "selected_url_count": len(final_urls),
        "selected_by_sector": selected_by_sector,
        "available_by_sector": available_by_sector,
        "execute_fetch": execute_fetch,
        "fetch_result": None,
    }

    if execute_fetch:
        plan_payload["fetch_result"] = _execute_gap_fetch(
            root=root,
            final_urls=final_urls,
            final_urls_by_sector=final_urls_by_sector,
            output_manifest=output_manifest,
            output_plan_json=output_plan_json,
            plan_payload=plan_payload,
            fetch_output_dir=fetch_output_dir,
            task_monitor=task_monitor,
            task_monitor_project=task_monitor_project,
            task_monitor_strict=task_monitor_strict,
            watchdog_seconds=watchdog_seconds,
            watchdog_poll_seconds=watchdog_poll_seconds,
        )

    output_plan_json.parent.mkdir(parents=True, exist_ok=True)
    output_plan_json.write_text(json.dumps(plan_payload, indent=2), encoding="utf-8")
    print(
        f"gap_plan={output_plan_json} "
        f"manifest={output_manifest} "
        f"selected_urls={len(final_urls)}"
    )


def _execute_gap_fetch(
    *,
    root: Path,
    final_urls: List[str],
    final_urls_by_sector: Dict[str, List[str]],
    output_manifest: Path,
    output_plan_json: Path,
    plan_payload: Dict,
    fetch_output_dir: Optional[Path],
    task_monitor: bool,
    task_monitor_project: str,
    task_monitor_strict: bool,
    watchdog_seconds: int,
    watchdog_poll_seconds: int,
) -> Dict:
    """Execute the fetcher for gap-fill downloads. Returns fetch result dict."""
    fetch_state = TASK_MONITOR_STATE_DIR / "learn_datalake_gap_fetch.json"
    tm_start_session(project=task_monitor_project, enabled=task_monitor, strict=task_monitor_strict)
    tm_register_task(
        name="learn_datalake_gap_fetch", state_file=fetch_state, total=len(final_urls),
        description="Gap-fill fetcher run",
        project=task_monitor_project, enabled=task_monitor, strict=task_monitor_strict,
    )

    if not final_urls:
        print("selected_url_count=0 fetch_skipped=true")
        tm_end_session(notes="gap-fetch completed", enabled=task_monitor, strict=task_monitor_strict)
        return {"status": "skipped", "reason": "no_selected_urls"}

    cumulative_completed = 0
    sector_results: list = []
    for sector in SECTOR_KEYS:
        sector_urls = final_urls_by_sector.get(sector, [])
        if not sector_urls:
            continue
        sector_manifest = output_manifest.parent / f"gap_manifest_urls_{sector}.txt"
        write_manifest(sector_manifest, sector_urls)
        sector_root = (fetch_output_dir / sector) if fetch_output_dir else (root / sector)
        out_dir = next_expansion_batch_dir(sector_root)
        write_task_state(
            fetch_state,
            {
                "completed": cumulative_completed,
                "stats": {"selected_url_count": len(final_urls), "sector": sector, "sector_url_count": len(sector_urls)},
                "current_item": str(sector_manifest),
            },
        )
        fetch_proc = run_fetcher_manifest(
            sector_manifest, out_dir,
            watchdog_seconds=watchdog_seconds, watchdog_poll_seconds=watchdog_poll_seconds,
            state_file=fetch_state,
        )
        ensure_not_stalled(fetch_proc, f"gap-fetch-{sector}")
        sector_result = {
            "sector": sector,
            "url_count": len(sector_urls),
            "manifest_path": str(sector_manifest),
            "status": "ok" if fetch_proc.returncode == 0 else "failed",
            "returncode": fetch_proc.returncode,
            "out_dir": str(out_dir),
            "stdout_tail": "\n".join(fetch_proc.stdout.splitlines()[-40:]),
            "stderr_tail": "\n".join(fetch_proc.stderr.splitlines()[-40:]),
            "elapsed_seconds": round(fetch_proc.elapsed_seconds, 2),
            "stalled": fetch_proc.stalled,
            "timed_out": fetch_proc.timed_out,
        }
        sector_results.append(sector_result)
        print(f"fetch_sector={sector} fetch_status={sector_result['status']} fetch_out_dir={out_dir}")
        if fetch_proc.returncode != 0:
            write_task_state(fetch_state, {
                "completed": cumulative_completed,
                "stats": {"sector": sector, "returncode": fetch_proc.returncode},
                "current_item": str(out_dir), "consecutive_failures": 1,
            })
            output_plan_json.parent.mkdir(parents=True, exist_ok=True)
            plan_payload["fetch_result"] = {"mode": "sector_scoped", "status": "failed", "results": sector_results}
            output_plan_json.write_text(json.dumps(plan_payload, indent=2), encoding="utf-8")
            tm_end_session(notes=f"gap-fetch failed sector={sector}", enabled=task_monitor, strict=task_monitor_strict)
            raise typer.Exit(code=1)
        cumulative_completed += len(sector_urls)
        write_task_state(fetch_state, {
            "completed": cumulative_completed,
            "stats": {"sector": sector, "returncode": fetch_proc.returncode},
            "current_item": str(out_dir), "consecutive_failures": 0,
        })

    tm_add_accomplishment(
        text=f"gap-fetch completed urls={len(final_urls)} sectors={len(sector_results)}",
        enabled=task_monitor, strict=task_monitor_strict,
    )
    tm_end_session(notes="gap-fetch completed", enabled=task_monitor, strict=task_monitor_strict)
    return {"mode": "sector_scoped", "status": "ok", "results": sector_results}


@quarantine_app.command("list")
def cmd_quarantine_list() -> None:
    """List all pending deferred/quarantined PDFs."""
    from pdf_discovery import load_all_deferred

    entries = load_all_deferred()
    if not entries:
        print("No quarantined PDFs pending review.")
        raise typer.Exit(0)

    print(f"{'STEM':<50} {'REASON':<20} {'CONFIDENCE':<12} {'TIMESTAMP'}")
    print("-" * 110)
    for entry in entries:
        stem = entry.get("stem", "?")[:49]
        reason = entry.get("reason", "?")[:19]
        confidence = entry.get("metadata", {}).get("confidence", "n/a")
        if isinstance(confidence, float):
            confidence = f"{confidence:.3f}"
        timestamp = entry.get("timestamp", "?")[:25]
        print(f"{stem:<50} {reason:<20} {str(confidence):<12} {timestamp}")
    print(f"\nTotal: {len(entries)} quarantined item(s)")


@quarantine_app.command("resolve")
def cmd_quarantine_resolve(
    stem: str = typer.Argument(..., help="PDF stem to launch interview for"),
) -> None:
    """Launch an /interview session for a specific quarantined PDF."""
    from pdf_discovery import launch_interview

    try:
        session = launch_interview(stem)
    except ValueError as exc:
        logger.error(str(exc))
        raise typer.Exit(code=1)

    print(f"interview_session_ready stem={stem} reason={session['reason']}")
    print(f"questions={len(session['questions'])}")
    session_path = STATE_DIR / "interview_sessions" / f"{stem}.json"
    print(f"session_file={session_path}")
    print(
        "\nTo run the interview:\n"
        f"  /interview --file {session_path}"
    )


@quarantine_app.command("approve-all")
def cmd_quarantine_approve_all(
    min_confidence: float = typer.Option(0.8, min=0.0, max=1.0, help="Minimum confidence threshold for auto-approval"),
) -> None:
    """Batch-resolve quarantined entries above a confidence threshold."""
    from pdf_discovery import load_all_deferred, resolve_deferred

    entries = load_all_deferred()
    if not entries:
        print("No quarantined PDFs pending review.")
        raise typer.Exit(0)

    approved = 0
    skipped = 0
    for entry in entries:
        confidence = entry.get("metadata", {}).get("confidence")
        if confidence is None or not isinstance(confidence, (int, float)):
            skipped += 1
            continue
        if confidence >= min_confidence:
            stem = entry["stem"]
            resolution = {
                "action": "auto_approved",
                "answered_by": "batch_approve",
                "min_confidence": min_confidence,
                "actual_confidence": confidence,
            }
            resolve_deferred(stem, resolution)
            approved += 1
            print(f"approved stem={stem} confidence={confidence:.3f}")
        else:
            skipped += 1

    print(f"\nBatch complete: approved={approved} skipped={skipped} threshold={min_confidence:.3f}")


def _validate_taxonomy_coverage(scope: str) -> None:
    """Post-ingestion check: warn if lessons in scope are missing taxonomy.

    Does NOT block the pipeline — logs a warning and triggers a sweep if needed.
    """
    import subprocess as _sp

    try:
        # Query for lessons missing bridge_attributes in this scope
        check_cmd = (
            f"cd {_SKILLS_DIR.parent.parent.parent / 'memory'} && "
            f'.venv/bin/python -c "'
            f"from src.graph_memory.arango_client import get_db; "
            f"db = get_db(); "
            f"missing = list(db.aql.execute("
            f"'FOR d IN lessons FILTER d.scope == @scope "
            f"FILTER d.bridge_attributes == null OR LENGTH(d.bridge_attributes) == 0 "
            f"COLLECT WITH COUNT INTO c RETURN c', "
            f"bind_vars={{'scope': '{scope}'}})); "
            f"print(missing[0] if missing else 0)"
            f'"'
        )
        result = _sp.run(
            ["bash", "-lc", check_cmd],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if result.returncode == 0:
            count = int(result.stdout.strip() or "0")
            if count > 0:
                logger.warning(
                    f"TAXONOMY VIOLATION: {count} lessons in scope={scope} "
                    f"stored without taxonomy. Running sweep..."
                )
                sweep_cmd = (
                    f"cd {_SKILLS_DIR}/taxonomy && "
                    f'./run.sh sweep --collection lessons --scope "{scope}" '
                    f"--mode keyword --limit {count + 100}"
                )
                _sp.run(
                    ["bash", "-lc", sweep_cmd],
                    capture_output=True, text=True, timeout=600, check=False,
                )
    except Exception as e:
        logger.warning(f"taxonomy validation check failed: {e}")


def _run_threat_delta_check() -> None:
    """Non-blocking post-ingestion check for recent control changes and threat deltas."""
    import subprocess as _sp

    try:
        import httpx

        since = int(time.time()) - 3600
        query_payload = {
            "aql": (
                "FOR e IN chunk_control_edges "
                "FILTER e.created_at >= @since "
                "COLLECT ctrl = e.control_id INTO g "
                "RETURN DISTINCT ctrl"
            ),
            "bind_vars": {"since": since},
        }

        transport = httpx.HTTPTransport(uds=MEMORY_SOCKET)
        with httpx.Client(transport=transport, base_url=MEMORY_BASE_URL, timeout=30.0) as client:
            response = client.post("/query", json=query_payload)
            response.raise_for_status()
            body = response.json()

        rows = body if isinstance(body, list) else body.get("results", [])
        control_ids: list[str] = []
        for row in rows:
            if isinstance(row, str) and row.strip():
                control_ids.append(row.strip())
            elif isinstance(row, dict):
                ctrl = row.get("ctrl")
                if isinstance(ctrl, str) and ctrl.strip():
                    control_ids.append(ctrl.strip())

        deduped: list[str] = []
        seen: set[str] = set()
        for control_id in control_ids:
            if control_id not in seen:
                deduped.append(control_id)
                seen.add(control_id)

        if not deduped:
            logger.info("threat delta check skipped: no recent chunk_control_edges")
            return

        env = {**os.environ, "SCILLM_MODEL": "text"}
        proc = _sp.run(
            [sys.executable, str(COMPUTE_DELTA_SCRIPT), "--control-ids", ",".join(deduped)],
            cwd=SKILL_DIR,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
            env=env,
        )

        delta_count = 0
        for line in proc.stdout.splitlines():
            if line.startswith("delta_count="):
                try:
                    delta_count = int(line.split("=", 1)[1].strip())
                    break
                except ValueError:
                    pass

        logger.info(
            "threat delta check complete: controls={} deltas={} returncode={}",
            len(deduped),
            delta_count,
            proc.returncode,
        )
        if proc.returncode != 0 and proc.stderr.strip():
            logger.warning("threat delta check stderr: {}", proc.stderr.splitlines()[-1])
    except Exception as e:
        logger.warning(f"threat delta check failed: {e}")


if __name__ == "__main__":
    app()
