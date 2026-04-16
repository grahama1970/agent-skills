"""supervise_learn_datalake child process polling loop.

Monitors the running child process, collecting metrics, applying
quality gates, checking heartbeats, and writing state updates
each poll cycle.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any, Dict

from loguru import logger

from supervise_learn_datalake_helpers import (
    TASK_MONITOR_STATE_DIR,
    _aggregate_worker_states,
    _drain_memory_retry_queue,
    _failure_total,
    _now_utc_iso,
    _parse_iso_to_epoch,
    _record_learning_event,
    _safe_read_json,
    _terminate_process,
    _write_json,
)
from supervise_learn_datalake_metrics import (
    _apply_quality_gate,
    _collect_run_metrics,
)


def _poll_child(
    *,
    proc: subprocess.Popen[Any],
    stop_file: Path,
    run_log: Path,
    run_id: str,
    label: str,
    root: Path,
    child_start_epoch: float,
    heartbeat_timeout_seconds: int,
    supervisor_poll_seconds: int,
    quality_gate_consecutive_failures: int,
    target_score: float,
    target_fail_ratio: float,
    bl_count: int,
    eff_fail_floor: float,
    workers: int,
    dynamic_watchdog_seconds: int,
    run_metrics: Dict[str, Any],
    failure_buckets: Dict[str, int],
    restart_count: int,
    run_count: int,
    supervisor_state: Path,
    watchdog_task_state: Path,
    cycle_state: Path,
    review_state: Path,
    memory_events_path: Path,
    memory_write_strict: bool,
    gate_failure_streak: int,
    last_gate_action: str,
    last_gate_reason: str,
) -> str:
    """Poll the child process until it exits or is terminated.

    Returns the forced_reason string (empty if child exited on its own).
    """
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
        cycle_failures = int(cycle_payload.get("consecutive_failures", 0) or 0)
        run_metrics.update(
            _collect_run_metrics(
                run_log=run_log,
                heartbeat_timeout_seconds=heartbeat_timeout_seconds,
            )
        )
        memory_retry_status = _drain_memory_retry_queue(max_items=5, max_attempts=3)
        run_metrics.update(
            {
                "memory_retry_retried_count": memory_retry_status.get("retried_count", 0),
                "memory_retry_succeeded_count": memory_retry_status.get("succeeded_count", 0),
                "memory_retry_queue_count": memory_retry_status.get("queue_count_after", 0),
                "memory_retry_dead_letter_count": memory_retry_status.get(
                    "dead_lettered_count", 0
                ),
            }
        )
        child_age = int(now - child_start_epoch)
        run_metrics["loop_cycle_count"] = max(
            int(run_metrics.get("loop_cycle_count", 0) or 0),
            cycle_completed,
        )
        throughput_per_hour = 0.0
        if child_age > 0:
            throughput_per_hour = round(
                (3600.0 * float(run_metrics.get("extraction_success_count", 0) or 0)) / child_age,
                2,
            )
        run_metrics["extraction_throughput_per_hour"] = throughput_per_hour
        run_metrics["workers"] = workers
        worker_agg = _aggregate_worker_states(TASK_MONITOR_STATE_DIR)
        if worker_agg:
            run_metrics["worker_aggregate"] = worker_agg
        if int(run_metrics.get("recommended_watchdog_seconds", 0) or 0) > dynamic_watchdog_seconds:
            dynamic_watchdog_seconds = int(run_metrics["recommended_watchdog_seconds"])
            logger.info(f"adaptive_watchdog_seconds={dynamic_watchdog_seconds}")
        run_metrics["blacklist_count"] = bl_count
        run_metrics["expected_fail_floor"] = eff_fail_floor
        run_metrics.update(
            _apply_quality_gate(
                run_metrics,
                target_score=target_score,
                target_fail_ratio=target_fail_ratio,
                blacklist_count=bl_count,
                expected_fail_floor=eff_fail_floor,
            )
        )
        gate_action = str(run_metrics.get("quality_gate_action", "continue_extracting"))
        gate_reason = str(run_metrics.get("quality_gate_reason", "within_thresholds"))
        if gate_action == "diagnose_debug_resume":
            gate_failure_streak += 1
        else:
            gate_failure_streak = 0
        run_metrics["quality_gate_consecutive_failures"] = gate_failure_streak
        if gate_action != last_gate_action or gate_reason != last_gate_reason:
            event_type = "success" if gate_action == "continue_extracting" else "failure"
            if (
                gate_action == "diagnose_debug_resume"
                and last_gate_action == "continue_extracting"
            ):
                event_type = "regression"
            _record_learning_event(
                events_path=memory_events_path,
                event_type=event_type,
                root=root,
                label=label,
                run_id=run_id,
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
        if (
            gate_action == "diagnose_debug_resume"
            and int(run_metrics.get("quality_gate_consecutive_failures", 0) or 0)
            >= quality_gate_consecutive_failures
        ):
            forced_reason = "quality_gate_escalation"
            logger.warning(
                "quality gate escalation triggered "
                f"run_id={run_id} action={gate_action} reason={gate_reason} "
                f"streak={run_metrics.get('quality_gate_consecutive_failures', 0)}"
            )
            _terminate_process(proc)
            break

        review_last_updated = str(review_payload.get("last_updated", ""))
        review_epoch = _parse_iso_to_epoch(review_last_updated)
        heartbeat_is_fresh = (
            review_epoch is not None and review_epoch >= (child_start_epoch - 5.0)
        )
        review_age = int(now - review_epoch) if heartbeat_is_fresh else None
        effective_heartbeat_timeout = int(
            run_metrics.get("adaptive_heartbeat_timeout_seconds", heartbeat_timeout_seconds)
            or heartbeat_timeout_seconds
        )

        if (
            review_age is not None
            and review_age > effective_heartbeat_timeout
        ):
            forced_reason = "heartbeat_timeout"
            logger.warning(
                f"heartbeat_timeout age={review_age}s "
                f"limit={effective_heartbeat_timeout}s; terminating child"
            )
            _terminate_process(proc)
            break
        if (
            review_age is None
            and child_age > effective_heartbeat_timeout
        ):
            forced_reason = "heartbeat_timeout_startup"
            logger.warning(
                f"heartbeat_timeout_startup child_age={child_age}s "
                f"limit={effective_heartbeat_timeout}s; terminating child"
            )
            _terminate_process(proc)
            break

        _write_json(
            supervisor_state,
            {
                "label": label,
                "root": str(root),
                "status": "running",
                "updated_at": _now_utc_iso(),
                "run_id": run_id,
                "run_log": str(run_log),
                "child_pid": proc.pid,
                "restart_count": restart_count,
                "run_count": run_count,
                "cycle_completed": cycle_completed,
                "cycle_failures": cycle_failures,
                "child_age_seconds": child_age,
                "review_heartbeat_age_seconds": review_age,
                "review_heartbeat_fresh": heartbeat_is_fresh,
                "run_metrics": run_metrics,
                "failure_buckets": failure_buckets,
                "stop_file": str(stop_file),
            },
        )
        _write_json(
            watchdog_task_state,
            {
                "completed": 1 if heartbeat_is_fresh else 0,
                "errors": _failure_total(failure_buckets),
                "stats": {
                    "status": "running",
                    "run_id": run_id,
                    "child_pid": proc.pid,
                    "child_age_seconds": child_age,
                    "heartbeat_fresh": heartbeat_is_fresh,
                    "heartbeat_age_seconds": review_age,
                    "restart_count": restart_count,
                    "run_count": run_count,
                    "extracted_pdf_coverage_pct": cycle_payload.get("extracted_pdf_coverage_pct"),
                    "extraction_attempts": run_metrics.get("extraction_attempts"),
                    "extraction_success_count": run_metrics.get("extraction_success_count"),
                    "extraction_cached_profile_count": run_metrics.get(
                        "extraction_cached_profile_count"
                    ),
                    "extraction_failed_count": run_metrics.get("extraction_failed_count"),
                    "extraction_timeout_rate_pct": run_metrics.get("extraction_timeout_rate_pct"),
                    "extraction_timeout_hint_count": run_metrics.get(
                        "extraction_timeout_hint_count"
                    ),
                    "extraction_fail_rate_pct": run_metrics.get("extraction_fail_rate_pct"),
                    "extraction_missing_structural_count": run_metrics.get(
                        "extraction_missing_structural_count"
                    ),
                    "extraction_missing_structural_rate_pct": run_metrics.get(
                        "extraction_missing_structural_rate_pct"
                    ),
                    "extraction_throughput_per_hour": run_metrics.get(
                        "extraction_throughput_per_hour"
                    ),
                    "timeout_model_decisions": run_metrics.get("timeout_model_decisions"),
                    "timeout_model_used_count": run_metrics.get("timeout_model_used_count"),
                    "timeout_model_used_rate_pct": run_metrics.get("timeout_model_used_rate_pct"),
                    "timeout_model_high_risk_count": run_metrics.get(
                        "timeout_model_high_risk_count"
                    ),
                    "timeout_model_last_risk": run_metrics.get("timeout_model_last_risk"),
                    "rolling_docs_analyzed": run_metrics.get("rolling_docs_analyzed"),
                    "rolling_avg_score": run_metrics.get("rolling_avg_score"),
                    "rolling_fail_ratio": run_metrics.get("rolling_fail_ratio"),
                    "rolling_critical_doc_ratio": run_metrics.get("rolling_critical_doc_ratio"),
                    "documents_missing_ratio": run_metrics.get("documents_missing_ratio"),
                    "phase": run_metrics.get("phase"),
                    "quality_gate_action": run_metrics.get("quality_gate_action"),
                    "quality_gate_reason": run_metrics.get("quality_gate_reason"),
                    "quality_gate_consecutive_failures": run_metrics.get(
                        "quality_gate_consecutive_failures"
                    ),
                    "adaptive_watchdog_seconds": dynamic_watchdog_seconds,
                    "adaptive_heartbeat_timeout_seconds": effective_heartbeat_timeout,
                    "workers": workers,
                    "worker_aggregate": run_metrics.get("worker_aggregate"),
                    "recent_failed_pdf_count": run_metrics.get("recent_failed_pdf_count"),
                    "memory_retry_queue_count": run_metrics.get("memory_retry_queue_count"),
                    "memory_retry_dead_letter_count": run_metrics.get(
                        "memory_retry_dead_letter_count"
                    ),
                },
                "current_item": (
                    f"run_id={run_id} gate={run_metrics.get('quality_gate_action')} "
                    f"phase={run_metrics.get('phase')}"
                ),
                "consecutive_failures": 0 if heartbeat_is_fresh else 1,
                "last_updated": _now_utc_iso(),
            },
        )
        time.sleep(supervisor_poll_seconds)

    return forced_reason
