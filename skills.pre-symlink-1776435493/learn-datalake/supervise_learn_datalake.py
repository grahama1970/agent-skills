#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "typer>=0.12.3",
#   "loguru>=0.7.0",
# ]
# ///
"""Active supervisor for learn-datalake long-running loops.

This script provides deterministic control around a non-deterministic pipeline:
- keep the child process alive (auto-restart)
- diagnose failure signatures from logs
- persist run diagnostics and failure buckets
- stop safely via stop-file

Implementation is split across submodules:
- supervise_learn_datalake_helpers: constants, JSON/JSONL helpers, memory, convergence, alerts
- supervise_learn_datalake_metrics: log parsing, quality gate, debug chain
- supervise_learn_datalake_reviews: persona review, stratified sampling, watchdog stats
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any, Dict

import typer
from loguru import logger

from supervise_learn_datalake_helpers import (
    DEFAULT_ROOT,
    DIAG_DIR,
    FAILED_PDF_BLACKLIST,
    LEARN_DATALAKE_RUN,
    MEMORY_RETRY_DEAD_LETTER,
    MEMORY_RETRY_QUEUE,
    RUN_DIR,
    SKILL_DIR,
    STATE_DIR,
    TASK_MONITOR_STATE_DIR,
    WATCHDOG_DIR,
    _aggregate_worker_states,
    _assert_required_paths,
    _build_child_command,
    _classify_failure,
    _count_blacklist,
    _count_deferred,
    _count_jsonl_records,
    _drain_memory_retry_queue,
    _failure_total,
    _now_utc_iso,
    _parse_iso_to_epoch,
    _record_learning_event,
    _register_supervisor_task,
    _run_alert_hook,
    _safe_read_json,
    _tail_text,
    _terminate_process,
    _write_json,
)
from supervise_learn_datalake_metrics import (
    _apply_quality_gate,
    _collect_run_metrics,
    _run_targeted_debug_chain,
)
from supervise_learn_datalake_reviews import (
    _build_watchdog_running_stats,
)

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command("run")
def run_supervisor(
    root: Path = typer.Argument(
        DEFAULT_ROOT, exists=True, file_okay=False, dir_okay=True,
    ),
    label: str = typer.Option("nasa", help="Run label used in state/log filenames"),
    target_score: float = typer.Option(0.95, min=0.0, max=1.0),
    target_fail_ratio: float = typer.Option(0.01, min=0.0, max=1.0),
    poll_seconds: int = typer.Option(300, min=10),
    watchdog_seconds: int = typer.Option(900, min=30),
    watchdog_poll_seconds: int = typer.Option(15, min=1),
    supervisor_poll_seconds: int = typer.Option(20, min=2),
    heartbeat_timeout_seconds: int = typer.Option(1800, min=60),
    quality_gate_consecutive_failures: int = typer.Option(
        2, min=1,
        help="Escalate diagnose/debug after this many consecutive quality gate failures",
    ),
    restart_max_backoff_seconds: int = typer.Option(600, min=5),
    max_restarts: int = typer.Option(
        0, min=0,
        help="0 means unlimited restart attempts; otherwise stop after this many",
    ),
    task_monitor: bool = typer.Option(True),
    task_monitor_project: str = typer.Option("datalake_training"),
    task_monitor_strict: bool = typer.Option(
        True, help="Hard-fail when task-monitor registration/update fails",
    ),
    alert_hook_command: str = typer.Option(
        "",
        help="Optional shell command to run on watchdog failures/restarts. "
        "Env includes LEARN_DATALAKE_* context vars.",
    ),
    alert_hook_strict: bool = typer.Option(
        False, help="Hard-fail supervisor if alert hook command fails",
    ),
    execute_jobs: bool = typer.Option(True),
    ingest_memory: bool = typer.Option(True),
    ingest_non_pdf: bool = typer.Option(True),
    debug_cycle_timeout_seconds: int = typer.Option(
        7200, min=600,
        help="Timeout in seconds for targeted diagnose/debug cycle",
    ),
    max_failure_samples: int = typer.Option(
        5, min=1, max=20,
        help="Maximum failed PDFs sampled for targeted debug per escalation",
    ),
    memory_events_path: Path = typer.Option(
        WATCHDOG_DIR / "supervisor_memory_events.jsonl",
        help="Mandatory memory event sink",
    ),
    memory_write_strict: bool = typer.Option(
        True, help="Hard-fail when memory write fails",
    ),
    inline_review: bool = typer.Option(
        False, help="Enable inline persona review after each PDF extraction",
    ),
    extract_missing: bool = typer.Option(
        True,
        help="Extract un-profiled PDFs during discovery (disable to skip extraction and only review)",
    ),
    workers: int = typer.Option(
        0, min=0,
        help="Number of parallel review-pdf workers passed to child (0=env/default, 1=sequential)",
    ),
    blacklist_path: Path = typer.Option(
        FAILED_PDF_BLACKLIST,
        help="Path to failed PDF blacklist JSONL. Used to compute expected failure floor.",
    ),
    expected_fail_floor: float = typer.Option(
        0.0, min=0.0, max=1.0,
        help="Expected failure floor as a fraction (0.0-1.0). "
        "If 0, auto-computed from blacklist_count / corpus_pdf_count. "
        "Quality gate adjusts thresholds to account for inherently unextractable PDFs.",
    ),
) -> None:
    """Keep learn-datalake running; diagnose and restart on failures."""
    _assert_required_paths(task_monitor_enabled=task_monitor)
    if not LEARN_DATALAKE_RUN.exists():
        raise typer.BadParameter(f"Missing run script: {LEARN_DATALAKE_RUN}")

    WATCHDOG_DIR.mkdir(parents=True, exist_ok=True)
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    DIAG_DIR.mkdir(parents=True, exist_ok=True)
    TASK_MONITOR_STATE_DIR.mkdir(parents=True, exist_ok=True)

    supervisor_state = WATCHDOG_DIR / f"supervisor_{label}.json"
    supervisor_log = WATCHDOG_DIR / f"supervisor_{label}.log"
    stop_file = WATCHDOG_DIR / f"STOP_{label}"
    cycle_state = STATE_DIR / "task_monitor" / "learn_datalake_start_cycle.json"
    review_state = STATE_DIR / "task_monitor" / "learn_datalake_start_review_pdf.json"
    watchdog_task_state = TASK_MONITOR_STATE_DIR / f"learn_datalake_supervisor_{label}.json"

    prior = _safe_read_json(supervisor_state)
    failure_buckets: Dict[str, int] = prior.get("failure_buckets", {})
    restart_count = int(prior.get("restart_count", 0))
    run_count = int(prior.get("run_count", 0))
    dynamic_watchdog_seconds = int(max(watchdog_seconds, 3600))
    consecutive_watchdog_failures = 0

    logger.remove()
    logger.add(
        str(supervisor_log), level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    )
    logger.add(lambda msg: print(msg, end=""), level="INFO")

    bl_count = _count_blacklist(blacklist_path)
    corpus_pdf_count = sum(1 for _ in root.rglob("*.pdf")) if root.is_dir() else 0
    if expected_fail_floor > 0:
        eff_fail_floor = expected_fail_floor
    elif bl_count > 0 and corpus_pdf_count > 0:
        eff_fail_floor = round(bl_count / corpus_pdf_count, 4)
    else:
        eff_fail_floor = 0.0

    logger.info(f"supervisor_start label={label} root={root} workers={workers}")
    logger.info(
        f"blacklist_count={bl_count} corpus_pdfs={corpus_pdf_count} "
        f"expected_fail_floor={eff_fail_floor:.4f}"
    )
    logger.info(f"stop_file={stop_file}")
    _register_supervisor_task(
        label=label, state_file=watchdog_task_state,
        project=task_monitor_project, enabled=task_monitor, strict=task_monitor_strict,
    )

    while True:
        if stop_file.exists():
            _write_json(watchdog_task_state, {
                "completed": 0, "errors": _failure_total(failure_buckets),
                "stats": {"status": "stopped_by_stop_file",
                          "restart_count": restart_count, "run_count": run_count},
                "current_item": f"label={label}",
                "consecutive_failures": 0, "last_updated": _now_utc_iso(),
            })
            logger.info(f"stop_file_detected={stop_file}")
            _write_json(supervisor_state, {
                "label": label, "root": str(root), "status": "stopped_by_stop_file",
                "updated_at": _now_utc_iso(), "restart_count": restart_count,
                "run_count": run_count, "failure_buckets": failure_buckets,
                "stop_file": str(stop_file),
            })
            raise typer.Exit(code=0)

        run_count += 1
        run_id = f"{label}_{int(time.time())}"
        run_log = RUN_DIR / f"learn_datalake_{run_id}.log"
        run_metrics: Dict[str, Any] = {
            "quality_gate_action": "continue_extracting",
            "quality_gate_reason": "startup",
            "quality_gate_consecutive_failures": 0,
            "recommended_watchdog_seconds": dynamic_watchdog_seconds,
            "adaptive_heartbeat_timeout_seconds": heartbeat_timeout_seconds,
            "recent_failed_pdfs": [], "recent_failed_pdf_count": 0,
            "timeout_model_decisions": 0, "timeout_model_used_count": 0,
            "timeout_model_used_rate_pct": 0.0,
            "timeout_model_high_risk_count": 0, "timeout_model_last_risk": 0.0,
            "memory_retry_queue_count": _count_jsonl_records(MEMORY_RETRY_QUEUE),
            "memory_retry_dead_letter_count": _count_jsonl_records(MEMORY_RETRY_DEAD_LETTER),
            "memory_retry_retried_count": 0, "memory_retry_succeeded_count": 0,
        }
        last_gate_action = ""
        last_gate_reason = ""
        gate_failure_streak = 0
        cmd = _build_child_command(
            root=root, target_score=target_score,
            target_fail_ratio=target_fail_ratio, poll_seconds=poll_seconds,
            watchdog_seconds=dynamic_watchdog_seconds,
            watchdog_poll_seconds=watchdog_poll_seconds,
            task_monitor=task_monitor, task_monitor_project=task_monitor_project,
            execute_jobs=execute_jobs, ingest_memory=ingest_memory,
            ingest_non_pdf=ingest_non_pdf, workers=workers,
            inline_review=inline_review, extract_missing=extract_missing,
        )

        logger.info(f"child_start run_id={run_id} cmd={' '.join(cmd)}")
        with open(run_log, "ab", buffering=0) as log_file:
            child_start_epoch = time.time()
            proc = subprocess.Popen(
                cmd, cwd=str(SKILL_DIR), stdout=log_file,
                stderr=subprocess.STDOUT, start_new_session=True,
            )
            _write_json(supervisor_state, {
                "label": label, "root": str(root), "status": "running",
                "updated_at": _now_utc_iso(), "run_id": run_id,
                "run_log": str(run_log), "child_pid": proc.pid,
                "restart_count": restart_count, "run_count": run_count,
                "cycle_completed": 0, "cycle_failures": 0,
                "child_age_seconds": 0, "review_heartbeat_age_seconds": None,
                "review_heartbeat_fresh": False, "run_metrics": run_metrics,
                "failure_buckets": failure_buckets, "stop_file": str(stop_file),
            })
            _write_json(watchdog_task_state, {
                "completed": 0, "errors": _failure_total(failure_buckets),
                "stats": {
                    "status": "running", "run_id": run_id,
                    "child_pid": proc.pid, "child_age_seconds": 0,
                    "heartbeat_fresh": False, "heartbeat_age_seconds": None,
                    "restart_count": restart_count, "run_count": run_count,
                    "phase": run_metrics.get("phase"),
                    "quality_gate_action": run_metrics.get("quality_gate_action"),
                    "quality_gate_reason": run_metrics.get("quality_gate_reason"),
                    "quality_gate_consecutive_failures": run_metrics.get(
                        "quality_gate_consecutive_failures"),
                },
                "current_item": f"run_id={run_id} gate=startup phase=startup",
                "consecutive_failures": 0, "last_updated": _now_utc_iso(),
            })

            forced_reason = ""
            while True:
                if stop_file.exists():
                    forced_reason = "stopped_by_stop_file"
                    logger.info("stop_file detected while child running; terminating child")
                    _terminate_process(proc)
                    break
                rc = proc.poll()
                if rc is not None:
                    break

                now = time.time()
                cycle_payload = _safe_read_json(cycle_state)
                review_payload = _safe_read_json(review_state)
                cycle_completed = int(cycle_payload.get("completed", 0) or 0)
                run_metrics = _collect_run_metrics(
                    run_log=run_log,
                    heartbeat_timeout_seconds=heartbeat_timeout_seconds,
                )
                retry_st = _drain_memory_retry_queue(max_items=5, max_attempts=3)
                run_metrics.update({
                    "memory_retry_retried_count": retry_st.get("retried_count", 0),
                    "memory_retry_succeeded_count": retry_st.get("succeeded_count", 0),
                    "memory_retry_queue_count": retry_st.get("queue_count_after", 0),
                    "memory_retry_dead_letter_count": retry_st.get("dead_lettered_count", 0),
                })
                child_age = int(now - child_start_epoch)
                run_metrics["loop_cycle_count"] = max(
                    int(run_metrics.get("loop_cycle_count", 0) or 0), cycle_completed,
                )
                if child_age > 0:
                    run_metrics["extraction_throughput_per_hour"] = round(
                        3600.0 * float(run_metrics.get("extraction_success_count", 0) or 0)
                        / child_age, 2,
                    )
                else:
                    run_metrics["extraction_throughput_per_hour"] = 0.0
                run_metrics["workers"] = workers
                worker_agg = _aggregate_worker_states(TASK_MONITOR_STATE_DIR)
                if worker_agg:
                    run_metrics["worker_aggregate"] = worker_agg
                if int(run_metrics.get("recommended_watchdog_seconds", 0) or 0) > dynamic_watchdog_seconds:
                    dynamic_watchdog_seconds = int(run_metrics["recommended_watchdog_seconds"])
                    logger.info(f"adaptive_watchdog_seconds={dynamic_watchdog_seconds}")
                run_metrics["blacklist_count"] = bl_count
                run_metrics["deferred_review_count"] = _count_deferred()
                run_metrics["expected_fail_floor"] = eff_fail_floor
                run_metrics.update(_apply_quality_gate(
                    run_metrics, target_score=target_score,
                    target_fail_ratio=target_fail_ratio,
                    blacklist_count=bl_count, expected_fail_floor=eff_fail_floor,
                ))
                gate_action = str(run_metrics.get("quality_gate_action", "continue_extracting"))
                gate_reason = str(run_metrics.get("quality_gate_reason", "within_thresholds"))
                if gate_action == "diagnose_debug_resume":
                    gate_failure_streak += 1
                else:
                    gate_failure_streak = 0
                run_metrics["quality_gate_consecutive_failures"] = gate_failure_streak

                if gate_action != last_gate_action or gate_reason != last_gate_reason:
                    evt = "success" if gate_action == "continue_extracting" else "failure"
                    if gate_action == "diagnose_debug_resume" and last_gate_action == "continue_extracting":
                        evt = "regression"
                    _record_learning_event(
                        events_path=memory_events_path, event_type=evt,
                        root=root, label=label, run_id=run_id,
                        summary=f"{gate_action}:{gate_reason}",
                        details={
                            "quality_gate_action": gate_action,
                            "quality_gate_reason": gate_reason,
                            "rolling_avg_score": run_metrics.get("rolling_avg_score"),
                            "rolling_fail_ratio": run_metrics.get("rolling_fail_ratio"),
                            "documents_missing_ratio": run_metrics.get("documents_missing_ratio"),
                            "phase": run_metrics.get("phase"),
                            "phase_age_seconds": run_metrics.get("phase_age_seconds"),
                        },
                        strict=memory_write_strict,
                    )
                    last_gate_action = gate_action
                    last_gate_reason = gate_reason

                if (gate_action == "diagnose_debug_resume"
                        and int(run_metrics.get("quality_gate_consecutive_failures", 0) or 0)
                        >= quality_gate_consecutive_failures):
                    forced_reason = "quality_gate_escalation"
                    logger.warning(
                        f"quality gate escalation triggered run_id={run_id} "
                        f"action={gate_action} reason={gate_reason} "
                        f"streak={run_metrics.get('quality_gate_consecutive_failures', 0)}"
                    )
                    _terminate_process(proc)
                    break

                review_epoch = _parse_iso_to_epoch(str(review_payload.get("last_updated", "")))
                heartbeat_is_fresh = (
                    review_epoch is not None and review_epoch >= (child_start_epoch - 5.0)
                )
                review_age = int(now - review_epoch) if heartbeat_is_fresh else None
                eff_hb = int(
                    run_metrics.get("adaptive_heartbeat_timeout_seconds", heartbeat_timeout_seconds)
                    or heartbeat_timeout_seconds
                )
                if review_age is not None and review_age > eff_hb:
                    forced_reason = "heartbeat_timeout"
                    logger.warning(f"heartbeat_timeout age={review_age}s limit={eff_hb}s; terminating child")
                    _terminate_process(proc)
                    break
                if review_age is None and child_age > eff_hb:
                    forced_reason = "heartbeat_timeout_startup"
                    logger.warning(f"heartbeat_timeout_startup child_age={child_age}s limit={eff_hb}s; terminating child")
                    _terminate_process(proc)
                    break

                cycle_failures = int(cycle_payload.get("consecutive_failures", 0) or 0)
                _write_json(supervisor_state, {
                    "label": label, "root": str(root), "status": "running",
                    "updated_at": _now_utc_iso(), "run_id": run_id,
                    "run_log": str(run_log), "child_pid": proc.pid,
                    "restart_count": restart_count, "run_count": run_count,
                    "cycle_completed": cycle_completed, "cycle_failures": cycle_failures,
                    "child_age_seconds": child_age,
                    "review_heartbeat_age_seconds": review_age,
                    "review_heartbeat_fresh": heartbeat_is_fresh,
                    "run_metrics": run_metrics, "failure_buckets": failure_buckets,
                    "stop_file": str(stop_file),
                })
                _write_json(watchdog_task_state, _build_watchdog_running_stats(
                    run_id=run_id, child_pid=proc.pid, child_age=child_age,
                    heartbeat_is_fresh=heartbeat_is_fresh, review_age=review_age,
                    restart_count=restart_count, run_count=run_count,
                    cycle_payload=cycle_payload, run_metrics=run_metrics,
                    dynamic_watchdog_seconds=dynamic_watchdog_seconds,
                    effective_heartbeat_timeout=eff_hb,
                    failure_buckets=failure_buckets,
                ))
                time.sleep(supervisor_poll_seconds)

        # --- Child exited ---
        exit_code = proc.returncode if proc.returncode is not None else 1
        log_tail = _tail_text(run_log)
        failure_signature = _classify_failure(exit_code, log_tail, forced_reason=forced_reason)
        failure_buckets[failure_signature] = failure_buckets.get(failure_signature, 0) + 1
        restart_count += 1

        debug_result: Dict[str, Any] | None = None
        if failure_signature in {"quality_gate_escalation", "watchdog_failure", "hard_fail"}:
            debug_result = _run_targeted_debug_chain(
                run_id=run_id,
                recent_failed_pdfs=list(run_metrics.get("recent_failed_pdfs", [])),
                timeout_seconds=debug_cycle_timeout_seconds,
                max_failure_samples=max_failure_samples,
            )

        # Adaptive watchdog backoff / cap / reset
        if failure_signature == "watchdog_failure":
            _prev = dynamic_watchdog_seconds
            dynamic_watchdog_seconds = min(43200, max(dynamic_watchdog_seconds * 2, 3600))
            consecutive_watchdog_failures += 1
            if dynamic_watchdog_seconds >= 43200 and consecutive_watchdog_failures >= 3:
                logger.warning(
                    f"adaptive watchdog AT CAP (12h) for {consecutive_watchdog_failures} "
                    "consecutive failures -- resetting to 3600s with fresh state"
                )
                dynamic_watchdog_seconds = 3600
                consecutive_watchdog_failures = 0
            elif dynamic_watchdog_seconds >= 43200:
                logger.warning(
                    f"adaptive watchdog AT CAP (12h): {dynamic_watchdog_seconds}s -- "
                    f"systemic stall (consecutive={consecutive_watchdog_failures})"
                )
            else:
                logger.warning(f"adaptive watchdog: {_prev}s -> {dynamic_watchdog_seconds}s")
        else:
            consecutive_watchdog_failures = 0

        diag_path = DIAG_DIR / f"diagnostic_{label}_{int(time.time())}.json"
        _write_json(diag_path, {
            "timestamp": _now_utc_iso(), "label": label, "root": str(root),
            "run_id": run_id, "run_log": str(run_log), "exit_code": exit_code,
            "forced_reason": forced_reason, "failure_signature": failure_signature,
            "failure_bucket_count": failure_buckets[failure_signature],
            "restart_count": restart_count, "run_count": run_count,
            "run_metrics": run_metrics, "log_tail": log_tail,
            "debug_result": debug_result,
        })
        _write_json(supervisor_state, {
            "label": label, "root": str(root), "status": "restarting",
            "updated_at": _now_utc_iso(), "last_run_id": run_id,
            "last_run_log": str(run_log), "last_exit_code": exit_code,
            "last_failure_signature": failure_signature,
            "last_diagnostic": str(diag_path), "last_debug_result": debug_result,
            "restart_count": restart_count, "run_count": run_count,
            "failure_buckets": failure_buckets, "stop_file": str(stop_file),
        })
        _write_json(watchdog_task_state, {
            "completed": 0, "errors": _failure_total(failure_buckets),
            "stats": {"status": "restarting", "last_exit_code": exit_code,
                      "last_failure_signature": failure_signature,
                      "restart_count": restart_count, "run_count": run_count},
            "current_item": f"run_id={run_id}",
            "consecutive_failures": failure_buckets.get(failure_signature, 1),
            "last_updated": _now_utc_iso(),
        })

        if failure_signature == "stopped_by_stop_file":
            _record_learning_event(
                events_path=memory_events_path, event_type="success",
                root=root, label=label, run_id=run_id,
                summary="stopped_by_operator",
                details={"failure_signature": failure_signature,
                         "exit_code": exit_code, "diagnostic": str(diag_path)},
                strict=memory_write_strict,
            )
        else:
            _record_learning_event(
                events_path=memory_events_path, event_type="failure",
                root=root, label=label, run_id=run_id,
                summary=f"{failure_signature} exit_code={exit_code}",
                details={
                    "failure_signature": failure_signature, "exit_code": exit_code,
                    "quality_gate_action": run_metrics.get("quality_gate_action"),
                    "quality_gate_reason": run_metrics.get("quality_gate_reason"),
                    "rolling_avg_score": run_metrics.get("rolling_avg_score"),
                    "rolling_fail_ratio": run_metrics.get("rolling_fail_ratio"),
                    "documents_missing_ratio": run_metrics.get("documents_missing_ratio"),
                    "phase": run_metrics.get("phase"),
                    "debug_result_status": (debug_result or {}).get("status"),
                    "diagnostic": str(diag_path),
                },
                strict=memory_write_strict,
            )
            _run_alert_hook(
                command=alert_hook_command, strict=alert_hook_strict,
                env_extra={
                    "LEARN_DATALAKE_LABEL": label,
                    "LEARN_DATALAKE_ROOT": str(root),
                    "LEARN_DATALAKE_RUN_ID": run_id,
                    "LEARN_DATALAKE_FAILURE_SIGNATURE": failure_signature,
                    "LEARN_DATALAKE_EXIT_CODE": str(exit_code),
                    "LEARN_DATALAKE_RESTART_COUNT": str(restart_count),
                    "LEARN_DATALAKE_RUN_COUNT": str(run_count),
                    "LEARN_DATALAKE_DIAGNOSTIC": str(diag_path),
                    "LEARN_DATALAKE_LOG": str(run_log),
                },
            )

        logger.warning(
            f"child_exit run_id={run_id} exit_code={exit_code} "
            f"signature={failure_signature} restart_count={restart_count}"
        )
        if forced_reason == "stopped_by_stop_file":
            logger.info("supervisor stopped by stop-file request")
            raise typer.Exit(code=0)
        if max_restarts > 0 and restart_count >= max_restarts:
            logger.error(f"max_restarts_reached={max_restarts} stopping supervisor")
            raise typer.Exit(code=1)

        backoff = min(restart_max_backoff_seconds, 10 + (failure_buckets[failure_signature] * 15))
        logger.info(f"restart_backoff_seconds={backoff}")
        time.sleep(backoff)


if __name__ == "__main__":
    app()
