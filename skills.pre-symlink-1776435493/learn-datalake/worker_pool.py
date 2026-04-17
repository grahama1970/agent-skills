"""Worker pool orchestration for parallel PDF review in learn-datalake.

Purpose:
- Resolve worker counts, partition PDFs, run parallel review-pdf workers.
- Single-worker review-pdf execution.

Inputs:
- ReviewConfig, corpus root, worker count.

Outputs:
- CommandResult / ParallelReviewResult with aggregated worker outcomes.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from config import (
    REVIEW_PDF_DIR,
    CommandResult,
    ParallelReviewResult,
    RE_DISCOVER_PROGRESS,
    RE_EXTRACT_NEW,
    RE_EXTRACT_TIMEOUT,
    RE_INCREMENTAL_SKIP,
    ReviewConfig,
)
from pdf_discovery import (
    blacklist_failed_from_output,
    discover_pending_pdfs,
    filter_by_extractability,
)
from subprocess_exec import run_with_watchdog
from task_monitor_client import write_task_state


def resolve_workers(cli_value: int) -> int:
    """Resolve worker count from CLI flag, env var, or auto-tuning.

    Resolution order:
    1. Explicit CLI value (--workers N where N > 0)
    2. LEARN_DATALAKE_WORKERS env var
    3. Auto-tune based on available CPU and RAM headroom
    """
    if cli_value > 0:
        return cli_value
    env_val = os.environ.get("LEARN_DATALAKE_WORKERS", "").strip()
    if env_val.isdigit() and int(env_val) > 0:
        return int(env_val)
    return _auto_tune_workers()


def _auto_tune_workers() -> int:
    """Pick worker count based on current CPU and RAM headroom.

    Each review-pdf worker uses ~1-2 CPU cores and ~2 GB RAM.
    Leaves 25% CPU and 30% RAM margin for OS and other services.
    """
    import multiprocessing

    cpu_count = multiprocessing.cpu_count()

    try:
        load_1min = os.getloadavg()[0]
    except OSError:
        load_1min = cpu_count * 0.5

    cpu_available = max(0.0, cpu_count - load_1min)
    cpu_budget = max(0.0, cpu_available - (cpu_count * 0.25))
    workers_by_cpu = int(cpu_budget / 2)

    try:
        with open("/proc/meminfo") as f:
            meminfo = {}
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    meminfo[parts[0].rstrip(":")] = int(parts[1])
        total_kb = meminfo.get("MemTotal", 0)
        avail_kb = meminfo.get("MemAvailable", 0)
    except (OSError, ValueError):
        total_kb = 0
        avail_kb = 0

    if total_kb > 0 and avail_kb > 0:
        ram_reserve_kb = total_kb * 0.30
        ram_budget_kb = max(0.0, avail_kb - ram_reserve_kb)
        ram_budget_gb = ram_budget_kb / (1024 * 1024)
        workers_by_ram = int(ram_budget_gb / 2)
    else:
        workers_by_ram = 999

    workers = min(workers_by_cpu, workers_by_ram)
    workers = max(1, min(workers, 8))

    logger.info(
        "auto_tune_workers cpus={} load_1m={:.1f} cpu_budget_cores={:.1f} "
        "ram_avail_gb={:.1f} workers_by_cpu={} workers_by_ram={} => workers={}",
        cpu_count,
        load_1min,
        cpu_budget,
        avail_kb / (1024 * 1024) if avail_kb else 0,
        workers_by_cpu,
        workers_by_ram,
        workers,
    )
    return workers


def _partition_list(items: List[Any], n: int) -> List[List[Any]]:
    """Split items into n roughly-equal chunks using round-robin."""
    chunks: List[List[Any]] = [[] for _ in range(n)]
    for idx, item in enumerate(items):
        chunks[idx % n].append(item)
    return [c for c in chunks if c]


def _create_worker_symlink_dir(
    worker_id: int,
    pdf_paths: List[Path],
    root: Path,
) -> Path:
    """Create a temp directory mirroring the corpus subtree with symlinks to assigned PDFs."""
    worker_dir = Path(tempfile.mkdtemp(prefix=f"learn_datalake_worker_{worker_id}_"))
    for pdf_path in pdf_paths:
        try:
            rel = pdf_path.relative_to(root)
        except ValueError:
            rel = Path(pdf_path.name)
        link_path = worker_dir / rel
        link_path.parent.mkdir(parents=True, exist_ok=True)
        link_path.symlink_to(pdf_path)
    return worker_dir


def run_review_pdf_once(
    cfg: ReviewConfig,
    *,
    state_file: Optional[Path] = None,
) -> CommandResult:
    """Run a single review-pdf extraction cycle."""
    review_watchdog_seconds = max(cfg.watchdog_seconds, 3600)
    cmd = (
        f"cd {REVIEW_PDF_DIR} && ./run.sh loop \"{cfg.root}\" "
        f"--target-score {cfg.target_score} --target-fail-ratio {cfg.target_fail_ratio} "
        "--no-watch --max-cycles 1 "
        f"--poll-seconds {cfg.poll_seconds} "
        f"{'--execute-jobs ' if cfg.execute_jobs else ''}"
        f"{'--extract-missing ' if cfg.extract_missing else ''}"
        f"{'--ingest-memory ' if cfg.ingest_memory else ''}"
        f"{'--incremental ' if cfg.review_incremental else '--no-incremental '}"
        f"--memory-scope \"{cfg.memory_scope}\" "
        f"--taxonomy-collection \"{cfg.taxonomy_collection}\""
        f"{' --inline-review' if cfg.inline_review else ''}"
    )
    return run_with_watchdog(
        cmd,
        timeout=21600,
        watchdog_seconds=review_watchdog_seconds,
        watchdog_poll_seconds=cfg.watchdog_poll_seconds,
        stream_stdout=True,
        progress_callback=(
            (lambda progress: write_task_state(
                state_file,
                {
                    "completed": 0,
                    "stats": {
                        "elapsed_seconds": round(progress["elapsed_seconds"], 2),
                        "last_output_age_seconds": round(progress["last_output_age_seconds"], 2),
                    },
                    "current_item": "review-pdf loop",
                },
            ))
            if state_file is not None
            else None
        ),
    )


def _run_worker_batch(
    *,
    worker_id: int,
    worker_dir: Path,
    cfg: ReviewConfig,
    state_file: Path,
    main_state_file: Optional[Path] = None,
) -> CommandResult:
    """Run review-pdf on a worker's assigned PDF subset."""
    review_watchdog_seconds = max(cfg.watchdog_seconds, 3600)
    cmd = (
        f"cd {REVIEW_PDF_DIR} && ./run.sh loop \"{worker_dir}\" "
        f"--target-score {cfg.target_score} --target-fail-ratio {cfg.target_fail_ratio} "
        "--no-watch --max-cycles 1 "
        f"--poll-seconds {cfg.poll_seconds} "
        f"{'--execute-jobs ' if cfg.execute_jobs else ''}"
        f"{'--extract-missing ' if cfg.extract_missing else ''}"
        f"{'--ingest-memory ' if cfg.ingest_memory else ''}"
        "--no-incremental "
        f"--memory-scope \"{cfg.memory_scope}\" "
        f"--taxonomy-collection \"{cfg.taxonomy_collection}\""
        f"{' --inline-review' if cfg.inline_review else ''}"
        f" --corpus-root \"{cfg.root}\""
    )

    def _heartbeat_callback(progress: dict) -> None:
        """Write per-worker state AND refresh main state heartbeat."""
        stats = {
            "worker_id": worker_id,
            "elapsed_seconds": round(progress["elapsed_seconds"], 2),
            "last_output_age_seconds": round(progress["last_output_age_seconds"], 2),
        }
        write_task_state(
            state_file,
            {"completed": 0, "stats": stats, "current_item": f"worker_{worker_id}"},
        )
        # Also touch main state file so supervisor heartbeat stays fresh
        if main_state_file is not None:
            write_task_state(
                main_state_file,
                {
                    "completed": 0,
                    "stats": {"status": "worker_active", "worker_id": worker_id, **stats},
                    "current_item": f"worker_{worker_id}_active",
                    "consecutive_failures": 0,
                },
            )

    return run_with_watchdog(
        cmd,
        timeout=21600,
        watchdog_seconds=review_watchdog_seconds,
        watchdog_poll_seconds=cfg.watchdog_poll_seconds,
        stream_stdout=True,
        progress_callback=_heartbeat_callback,
    )


def summarize_review_output(result: CommandResult) -> Dict[str, Any]:
    """Extract key metrics from review-pdf stdout/stderr output."""
    text = f"{result.stdout}\n{result.stderr}"
    extracted_new_max = 0
    timeout_count = 0
    scanned_max = 0
    discover_new_max = 0
    changed_pdfs = -1
    incremental_skipped = False
    for line in text.splitlines():
        match_extract = RE_EXTRACT_NEW.search(line)
        if match_extract:
            extracted_new_max = max(extracted_new_max, int(match_extract.group("count")))
        match_timeout = RE_EXTRACT_TIMEOUT.search(line)
        if match_timeout:
            timeout_count += 1
        match_discover = RE_DISCOVER_PROGRESS.search(line)
        if match_discover:
            scanned_max = max(scanned_max, int(match_discover.group("scanned")))
            discover_new_max = max(discover_new_max, int(match_discover.group("new_count")))
        match_skip = RE_INCREMENTAL_SKIP.search(line)
        if match_skip:
            incremental_skipped = True
            changed_pdfs = int(match_skip.group("changed"))
    return {
        "extracted_new_max": extracted_new_max,
        "timeout_count": timeout_count,
        "discover_scanned_max": scanned_max,
        "discover_new_max": discover_new_max,
        "incremental_skipped": incremental_skipped,
        "changed_pdfs": changed_pdfs,
    }


def run_parallel_review(
    *,
    cfg: ReviewConfig,
    workers: int,
    state_file_base: Path,
) -> ParallelReviewResult:
    """Discover pending PDFs, partition across workers, run in parallel."""
    result = ParallelReviewResult()

    # Heartbeat before discovery (can take 20+ min on large corpus)
    write_task_state(
        state_file_base,
        {
            "completed": 0,
            "stats": {"status": "discovering_pdfs", "workers": workers},
            "current_item": "discovery_scanning",
            "consecutive_failures": 0,
        },
    )
    pending = discover_pending_pdfs(cfg.root)

    # Safety cap: if discovery returns an absurd number of "pending" files,
    # something is wrong with the matching logic. Log a warning and cap it
    # to prevent OOM/hang from creating 100k+ symlinks or worker partitions.
    _MAX_PENDING = 20_000
    if len(pending) > _MAX_PENDING:
        logger.warning(
            "discover_pending returned {} files (likely a matching bug); "
            "capping at {} to prevent hang",
            len(pending), _MAX_PENDING,
        )
        pending = pending[:_MAX_PENDING]

    # Heartbeat after discovery, before extractability filter
    write_task_state(
        state_file_base,
        {
            "completed": 0,
            "stats": {"status": "filtering_extractability", "pending_raw": len(pending), "workers": workers},
            "current_item": f"discovered_{len(pending)}_pdfs",
            "consecutive_failures": 0,
        },
    )
    pending = filter_by_extractability(pending)
    result.pending_pdf_count = len(pending)

    if not pending:
        logger.info("parallel_review pending_pdfs=0 running single full pass")
        single = run_review_pdf_once(cfg, state_file=state_file_base)
        summary = summarize_review_output(single)
        result.worker_results = [single]
        result.worker_summaries = [summary]
        result.aggregate_summary = summary
        result.worst_returncode = single.returncode
        result.any_stalled = single.stalled
        result.any_timed_out = single.timed_out
        result.workers_used = 1
        return result

    effective_workers = min(workers, len(pending))
    result.workers_used = effective_workers
    chunks = _partition_list(pending, effective_workers)

    print(
        f"parallel_review pending_pdfs={len(pending)} "
        f"workers={effective_workers} chunk_sizes={[len(c) for c in chunks]}",
        flush=True,
    )

    # Heartbeat: workers partitioned and about to start
    write_task_state(
        state_file_base,
        {
            "completed": 0,
            "stats": {
                "status": "parallel_workers_starting",
                "pending_pdfs": len(pending),
                "workers": effective_workers,
            },
            "current_item": f"launching_{effective_workers}_workers",
            "consecutive_failures": 0,
        },
    )

    worker_dirs: List[Path] = []
    futures_map: Dict[Any, int] = {}

    try:
        with ThreadPoolExecutor(max_workers=effective_workers) as executor:
            for idx, chunk in enumerate(chunks):
                worker_dir = _create_worker_symlink_dir(idx, chunk, cfg.root)
                worker_dirs.append(worker_dir)
                worker_state = state_file_base.parent / f"review_state_worker_{idx}.json"
                future = executor.submit(
                    _run_worker_batch,
                    worker_id=idx,
                    worker_dir=worker_dir,
                    cfg=cfg,
                    state_file=worker_state,
                    main_state_file=state_file_base,
                )
                futures_map[future] = idx

            workers_done = 0
            for future in as_completed(futures_map):
                idx = futures_map[future]
                try:
                    worker_result = future.result()
                except Exception as exc:
                    logger.error(f"worker_{idx} raised {type(exc).__name__}: {exc}")
                    worker_result = CommandResult(
                        cmd=f"worker_{idx}",
                        returncode=1,
                        stdout="",
                        stderr=str(exc),
                    )
                result.worker_results.append(worker_result)
                summary = summarize_review_output(worker_result)
                summary["worker_id"] = idx
                result.worker_summaries.append(summary)
                workers_done += 1

                # Update main state file as each worker finishes — keeps supervisor heartbeat fresh
                write_task_state(
                    state_file_base,
                    {
                        "completed": 0,
                        "stats": {
                            "status": "parallel_workers_running",
                            "workers_done": workers_done,
                            "workers_total": effective_workers,
                            "last_worker_done": idx,
                        },
                        "current_item": f"workers_{workers_done}/{effective_workers}",
                        "consecutive_failures": 0,
                    },
                )

                print(
                    f"worker_{idx} rc={worker_result.returncode} "
                    f"extracted_new={summary['extracted_new_max']} "
                    f"timeouts={summary['timeout_count']} "
                    f"stalled={worker_result.stalled} "
                    f"timed_out={worker_result.timed_out}",
                    flush=True,
                )
    finally:
        for wd in worker_dirs:
            shutil.rmtree(wd, ignore_errors=True)

    result.worst_returncode = max(
        (r.returncode for r in result.worker_results), default=0
    )
    result.any_stalled = any(r.stalled for r in result.worker_results)
    result.any_timed_out = any(r.timed_out for r in result.worker_results)

    total_blacklisted = 0
    for wr in result.worker_results:
        total_blacklisted += blacklist_failed_from_output(wr.stdout)
    if total_blacklisted:
        logger.info(f"blacklisted_failed_pdfs={total_blacklisted}")

    agg: Dict[str, Any] = {
        "extracted_new_max": sum(s.get("extracted_new_max", 0) for s in result.worker_summaries),
        "timeout_count": sum(s.get("timeout_count", 0) for s in result.worker_summaries),
        "discover_scanned_max": sum(s.get("discover_scanned_max", 0) for s in result.worker_summaries),
        "discover_new_max": sum(s.get("discover_new_max", 0) for s in result.worker_summaries),
        "incremental_skipped": all(s.get("incremental_skipped", False) for s in result.worker_summaries),
        "changed_pdfs": sum(max(0, s.get("changed_pdfs", 0)) for s in result.worker_summaries),
        "blacklisted_count": total_blacklisted,
        "workers_used": effective_workers,
        "pending_pdf_count": len(pending),
    }
    result.aggregate_summary = agg
    return result
