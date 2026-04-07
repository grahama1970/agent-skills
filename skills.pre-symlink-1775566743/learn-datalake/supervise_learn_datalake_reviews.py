"""supervise_learn_datalake reviews and remediation module.

Persona batch review, stratified sample review, memory convergence query,
remediation job execution, and child-exit diagnostics handling.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from loguru import logger

from supervise_learn_datalake_helpers import (
    DIAG_DIR,
    STATE_DIR,
    _classify_failure,
    _failure_total,
    _now_utc_iso,
    _record_learning_event,
    _run_alert_hook,
    _tail_text,
    _write_json,
)
from supervise_learn_datalake_metrics import (
    _run_targeted_debug_chain,
)

EXTRACTOR_QUALITY_CHECK_DIR = (
    Path.home()
    / "workspace"
    / "experiments"
    / "pi-mono"
    / ".pi"
    / "skills"
    / "extractor-quality-check"
)

SAMPLE_LOG = STATE_DIR / "stratified_sample_log.jsonl"
SAMPLE_EVERY_N_POLLS = 3  # Every ~60s at 20s poll interval
MIN_PROFILES_FOR_SAMPLING = 1  # Sample fires as soon as child starts discovering profiles

MEMORY_CONVERGENCE_LOG = STATE_DIR / "memory_convergence_log.jsonl"
MEMORY_CONVERGENCE_EVERY_N_POLLS = 3  # Same cadence as stratified sample


def _run_persona_batch_review(
    run_id: str,
    run_metrics: dict,
    gate_action: str = "",
    gate_reason: str = "",
) -> dict | None:
    """Run Margaret Chen + Jennifer Cheung batch review (optional).

    Returns review dict with decision/margaret_says/jennifer_says,
    or None if the skill is not installed or fails.
    """
    batch_review_script = EXTRACTOR_QUALITY_CHECK_DIR / "batch_review.py"
    if not batch_review_script.exists():
        return None

    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location("batch_review", str(batch_review_script))
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)

        # Ensure annealing.py is importable from the same directory
        import sys as _sys

        skill_dir_str = str(EXTRACTOR_QUALITY_CHECK_DIR)
        if skill_dir_str not in _sys.path:
            _sys.path.insert(0, skill_dir_str)

        spec.loader.exec_module(mod)

        return mod.run_batch_review(
            run_id=run_id,
            run_metrics=run_metrics,
            recent_failed_pdfs=run_metrics.get("recent_failed_pdfs", []),
            gate_action=gate_action,
            gate_reason=gate_reason,
        )
    except Exception as exc:
        logger.debug(f"persona_batch_review failed: {exc}")
        return None


def _run_stratified_sample_review(
    root: Path,
    run_id: str,
    sample_per_sector: int = 3,
) -> dict | None:
    """Run stratified sample review from disk (optional).

    Returns sample result dict with decision/overall_score/worst_pdfs,
    or None if the skill is not installed or fails.
    """
    batch_review_script = EXTRACTOR_QUALITY_CHECK_DIR / "batch_review.py"
    if not batch_review_script.exists():
        return None

    try:
        import importlib.util
        import sys as _sys

        spec = importlib.util.spec_from_file_location("batch_review", str(batch_review_script))
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)

        # Ensure annealing.py is importable from the same directory
        skill_dir_str = str(EXTRACTOR_QUALITY_CHECK_DIR)
        if skill_dir_str not in _sys.path:
            _sys.path.insert(0, skill_dir_str)

        spec.loader.exec_module(mod)

        return mod.stratified_sample_review(
            corpus_root=root,
            sample_per_sector=sample_per_sector,
            run_id=run_id,
        )
    except Exception as exc:
        logger.warning(f"stratified_sample_review failed: {type(exc).__name__}: {exc}")
        return None


def _run_remediation_jobs(escalation_jobs_list: list[dict]) -> list[dict]:
    """Execute remediation jobs via batch_review's fire-and-forget Popen launcher.

    Returns list of {command, skill, status} dicts. Non-blocking.
    """
    batch_review_script = EXTRACTOR_QUALITY_CHECK_DIR / "batch_review.py"
    if not batch_review_script.exists():
        return []

    try:
        import importlib.util
        import sys as _sys

        spec = importlib.util.spec_from_file_location("batch_review", str(batch_review_script))
        if spec is None or spec.loader is None:
            return []
        mod = importlib.util.module_from_spec(spec)

        skill_dir_str = str(EXTRACTOR_QUALITY_CHECK_DIR)
        if skill_dir_str not in _sys.path:
            _sys.path.insert(0, skill_dir_str)

        spec.loader.exec_module(mod)
        return mod._execute_remediation_jobs(escalation_jobs_list)
    except Exception as exc:
        logger.debug(f"_run_remediation_jobs failed: {exc}")
        return []


def _query_memory_convergence(
    root: Path,
    run_id: str,
) -> dict | None:
    """Query /memory for convergence status as alternative to stratified sampling.

    When --inline-review is active, each PDF is reviewed inline and stored in
    /memory.  Instead of scoring a stratified sample ourselves, we ask the
    convergence_tracker to compute trend from the reviews already in /memory.

    Returns a dict with same decision vocabulary as _run_stratified_sample_review:
        {
            "decision": "CONTINUE"|"SPOT_FIX"|"RESTART",
            "reason": str,
            "overall_score": float,
            "trend": str,
            "phase": str,
            "coverage_pct": float,
            "reviews_total": int,
            "sector_details": dict,
        }
    or None if convergence_tracker is unavailable.
    """
    convergence_tracker_script = EXTRACTOR_QUALITY_CHECK_DIR / "convergence_tracker.py"
    if not convergence_tracker_script.exists():
        return None

    try:
        import importlib.util
        import sys as _sys

        spec = importlib.util.spec_from_file_location(
            "convergence_tracker", str(convergence_tracker_script)
        )
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)

        # Ensure imports work from the skill directory
        skill_dir_str = str(EXTRACTOR_QUALITY_CHECK_DIR)
        if skill_dir_str not in _sys.path:
            _sys.path.insert(0, skill_dir_str)

        spec.loader.exec_module(mod)

        status = mod.get_convergence_status(corpus_root=root, window_size=50)
    except Exception as exc:
        logger.warning(f"memory_convergence_query failed: {type(exc).__name__}: {exc}")
        return None

    trend = status.get("trend", "insufficient_data")
    avg_score = status.get("avg_score", 0.0)
    phase = status.get("phase", "Bootstrap")
    reviews_total = status.get("reviews_total", 0)

    # Map trend + score to supervisor decision
    # Phase-aware thresholds (tighter at higher coverage)
    phase_thresholds = {
        "Bootstrap": 0.50,
        "Early Growth": 0.60,
        "Mid Growth": 0.70,
        "Late Growth": 0.78,
        "Refinement": 0.85,
        "Certification": 0.90,
    }
    phase_min = phase_thresholds.get(phase, 0.65)

    if trend == "insufficient_data":
        decision = "CONTINUE"
        reason = f"insufficient_data reviews={reviews_total} (need >=5)"
    elif trend == "degrading" and avg_score < phase_min:
        # Catastrophic regression -- average score below phase minimum AND dropping
        decision = "RESTART"
        reason = (
            f"catastrophic_regression trend={trend} avg={avg_score:.3f} "
            f"phase_min={phase_min:.2f} phase={phase}"
        )
    elif trend == "degrading":
        # Score still above threshold but trending down
        decision = "SPOT_FIX"
        reason = (
            f"degrading_trend avg={avg_score:.3f} slope={status.get('slope', 0):.4f} phase={phase}"
        )
    elif trend == "plateau" and avg_score >= phase_min:
        decision = "CONTINUE"
        reason = (
            f"plateau_above_threshold avg={avg_score:.3f} phase_min={phase_min:.2f} phase={phase}"
        )
    elif trend == "plateau":
        # Plateau but below phase minimum
        decision = "SPOT_FIX"
        reason = (
            f"plateau_below_threshold avg={avg_score:.3f} phase_min={phase_min:.2f} phase={phase}"
        )
    else:  # improving
        decision = "CONTINUE"
        reason = f"improving avg={avg_score:.3f} slope={status.get('slope', 0):.4f} phase={phase}"

    return {
        "decision": decision,
        "reason": reason,
        "overall_score": avg_score,
        "trend": trend,
        "phase": phase,
        "coverage_pct": status.get("coverage_pct", 0.0),
        "reviews_total": reviews_total,
        "sector_details": status.get("sectors", {}),
    }


def _build_watchdog_running_stats(
    *,
    run_id: str,
    child_pid: int,
    child_age: int,
    heartbeat_is_fresh: bool,
    review_age: int | None,
    restart_count: int,
    run_count: int,
    cycle_payload: dict[str, Any],
    run_metrics: dict[str, Any],
    dynamic_watchdog_seconds: int,
    effective_heartbeat_timeout: int,
    failure_buckets: dict[str, int],
) -> dict[str, Any]:
    """Build the watchdog task-monitor state payload for a running child.

    Extracts the projection of run_metrics into the task-monitor stats dict
    that the supervisor writes every poll cycle.
    """
    return {
        "completed": 1 if heartbeat_is_fresh else 0,
        "errors": _failure_total(failure_buckets),
        "stats": {
            "status": "running",
            "run_id": run_id,
            "child_pid": child_pid,
            "child_age_seconds": child_age,
            "heartbeat_fresh": heartbeat_is_fresh,
            "heartbeat_age_seconds": review_age,
            "restart_count": restart_count,
            "run_count": run_count,
            "extracted_pdf_coverage_pct": cycle_payload.get("extracted_pdf_coverage_pct"),
            "extraction_attempts": run_metrics.get("extraction_attempts"),
            "extraction_success_count": run_metrics.get("extraction_success_count"),
            "extraction_cached_profile_count": run_metrics.get("extraction_cached_profile_count"),
            "extraction_failed_count": run_metrics.get("extraction_failed_count"),
            "extraction_timeout_rate_pct": run_metrics.get("extraction_timeout_rate_pct"),
            "extraction_timeout_hint_count": run_metrics.get("extraction_timeout_hint_count"),
            "extraction_fail_rate_pct": run_metrics.get("extraction_fail_rate_pct"),
            "extraction_missing_structural_count": run_metrics.get(
                "extraction_missing_structural_count"
            ),
            "extraction_missing_structural_rate_pct": run_metrics.get(
                "extraction_missing_structural_rate_pct"
            ),
            "extraction_throughput_per_hour": run_metrics.get("extraction_throughput_per_hour"),
            "timeout_model_decisions": run_metrics.get("timeout_model_decisions"),
            "timeout_model_used_count": run_metrics.get("timeout_model_used_count"),
            "timeout_model_used_rate_pct": run_metrics.get("timeout_model_used_rate_pct"),
            "timeout_model_high_risk_count": run_metrics.get("timeout_model_high_risk_count"),
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
            "workers": run_metrics.get("workers"),
            "worker_aggregate": run_metrics.get("worker_aggregate"),
            "recent_failed_pdf_count": run_metrics.get("recent_failed_pdf_count"),
            "memory_retry_queue_count": run_metrics.get("memory_retry_queue_count"),
            "memory_retry_dead_letter_count": run_metrics.get("memory_retry_dead_letter_count"),
        },
        "current_item": (
            f"run_id={run_id} gate={run_metrics.get('quality_gate_action')} "
            f"phase={run_metrics.get('phase')}"
        ),
        "consecutive_failures": 0 if heartbeat_is_fresh else 1,
        "last_updated": _now_utc_iso(),
    }


def _handle_child_exit(
    *,
    proc_returncode: int | None,
    run_log: Path,
    forced_reason: str,
    failure_buckets: dict[str, int],
    restart_count: int,
    run_count: int,
    run_id: str,
    run_metrics: dict[str, Any],
    label: str,
    root: Path,
    dynamic_watchdog_seconds: int,
    debug_cycle_timeout_seconds: int,
    max_failure_samples: int,
    supervisor_state: Path,
    watchdog_task_state: Path,
    stop_file: Path,
    memory_events_path: Path,
    memory_write_strict: bool,
    alert_hook_command: str,
    alert_hook_strict: bool,
) -> dict[str, Any]:
    """Handle child process exit: diagnostics, state persistence, alerts.

    Mutates failure_buckets in place. Returns a dict with:
        - restart_count: updated restart count
        - failure_signature: classified failure type
        - dynamic_watchdog_seconds: possibly updated watchdog timeout
        - debug_result: result from targeted debug chain (or None)
        - diag_path: path to the written diagnostic JSON
    """
    exit_code = proc_returncode if proc_returncode is not None else 1
    log_tail = _tail_text(run_log)
    failure_signature = _classify_failure(exit_code, log_tail, forced_reason=forced_reason)
    failure_buckets[failure_signature] = failure_buckets.get(failure_signature, 0) + 1
    restart_count += 1
    debug_result: dict[str, Any] | None = None
    if failure_signature in {"quality_gate_escalation", "watchdog_failure", "hard_fail"}:
        debug_result = _run_targeted_debug_chain(
            run_id=run_id,
            recent_failed_pdfs=list(run_metrics.get("recent_failed_pdfs", [])),
            timeout_seconds=debug_cycle_timeout_seconds,
            max_failure_samples=max_failure_samples,
        )
    if failure_signature == "watchdog_failure":
        dynamic_watchdog_seconds = min(43200, max(dynamic_watchdog_seconds * 2, 3600))
        logger.warning(
            f"adaptive watchdog increased after watchdog_failure: {dynamic_watchdog_seconds}s"
        )

    diag_path = DIAG_DIR / f"diagnostic_{label}_{int(time.time())}.json"
    _write_json(
        diag_path,
        {
            "timestamp": _now_utc_iso(),
            "label": label,
            "root": str(root),
            "run_id": run_id,
            "run_log": str(run_log),
            "exit_code": exit_code,
            "forced_reason": forced_reason,
            "failure_signature": failure_signature,
            "failure_bucket_count": failure_buckets[failure_signature],
            "restart_count": restart_count,
            "run_count": run_count,
            "run_metrics": run_metrics,
            "log_tail": log_tail,
            "debug_result": debug_result,
        },
    )

    _write_json(
        supervisor_state,
        {
            "label": label,
            "root": str(root),
            "status": "restarting",
            "updated_at": _now_utc_iso(),
            "last_run_id": run_id,
            "last_run_log": str(run_log),
            "last_exit_code": exit_code,
            "last_failure_signature": failure_signature,
            "last_diagnostic": str(diag_path),
            "last_debug_result": debug_result,
            "restart_count": restart_count,
            "run_count": run_count,
            "failure_buckets": failure_buckets,
            "stop_file": str(stop_file),
        },
    )
    _write_json(
        watchdog_task_state,
        {
            "completed": 0,
            "errors": _failure_total(failure_buckets),
            "stats": {
                "status": "restarting",
                "last_exit_code": exit_code,
                "last_failure_signature": failure_signature,
                "restart_count": restart_count,
                "run_count": run_count,
            },
            "current_item": f"run_id={run_id}",
            "consecutive_failures": failure_buckets.get(failure_signature, 1),
            "last_updated": _now_utc_iso(),
        },
    )
    if failure_signature == "stopped_by_stop_file":
        _record_learning_event(
            events_path=memory_events_path,
            event_type="success",
            root=root,
            label=label,
            run_id=run_id,
            summary="stopped_by_operator",
            details={
                "failure_signature": failure_signature,
                "exit_code": exit_code,
                "diagnostic": str(diag_path),
            },
            strict=memory_write_strict,
        )
    else:
        _record_learning_event(
            events_path=memory_events_path,
            event_type="failure",
            root=root,
            label=label,
            run_id=run_id,
            summary=f"{failure_signature} exit_code={exit_code}",
            details={
                "failure_signature": failure_signature,
                "exit_code": exit_code,
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
    if failure_signature != "stopped_by_stop_file":
        _run_alert_hook(
            command=alert_hook_command,
            strict=alert_hook_strict,
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

    return {
        "restart_count": restart_count,
        "failure_signature": failure_signature,
        "dynamic_watchdog_seconds": dynamic_watchdog_seconds,
        "debug_result": debug_result,
        "diag_path": diag_path,
    }
