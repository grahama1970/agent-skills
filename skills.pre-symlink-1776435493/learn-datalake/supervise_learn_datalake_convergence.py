"""supervise_learn_datalake convergence state tracking module.

Tracks extraction convergence over multiple cycles, aligned with the
SPARTA convergence_state.json format. Detects converging, plateau,
regressing, and stalled states.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from supervise_learn_datalake_helpers import (
    MEMORY_DIR,
    WATCHDOG_DIR,
    _append_jsonl,
    _now_utc_iso,
    _safe_read_json,
    _write_json,
)

CONVERGENCE_REGRESSION_LIMIT = 3  # consecutive regressions -> stalled


def _convergence_state_path(label: str) -> Path:
    return WATCHDOG_DIR / f"convergence_{label}.json"


def _load_convergence_state(label: str) -> dict[str, Any]:
    path = _convergence_state_path(label)
    state = _safe_read_json(path)
    if not state:
        state = {
            "label": label,
            "cycles": [],
            "started": _now_utc_iso(),
            "updated": _now_utc_iso(),
            "status": "running",
        }
    return state


def _convergence_trend(cycles: list) -> str:
    """Determine trend from recent cycle issue counts.

    Returns: converging, plateau, regressing, or insufficient.
    """
    if len(cycles) < 3:
        return "insufficient"
    recent = [c.get("fail_count", 0) for c in cycles[-3:]]
    if recent[-1] < recent[-2] < recent[-3]:
        return "converging"
    if recent[-1] > recent[-2] > recent[-3]:
        return "regressing"
    if recent[-1] == recent[-2] == recent[-3]:
        return "plateau"
    # Mixed -- check overall direction
    if recent[-1] <= recent[0]:
        return "converging"
    return "regressing"


def _update_convergence_state(
    *,
    label: str,
    run_id: str,
    run_metrics: dict[str, Any],
    gate_action: str,
    gate_reason: str,
) -> dict[str, Any]:
    """Append a cycle record to convergence state and persist.

    Returns the updated convergence state dict.
    """
    state = _load_convergence_state(label)
    cycles = state.get("cycles", [])

    extraction_success = int(run_metrics.get("extraction_success_count", 0) or 0)
    extraction_failed = int(run_metrics.get("extraction_failed_count", 0) or 0)
    extraction_attempts = int(run_metrics.get("extraction_attempts", 0) or 0)

    # Skip empty cycles (no work done)
    if extraction_attempts == 0:
        return state

    # Build cycle record aligned with SPARTA format
    cycle_number = len(cycles) + 1
    fail_count = extraction_failed
    if gate_action == "continue_extracting":
        status = "PASS"
    elif gate_action == "diagnose_debug_resume":
        status = "WARN" if gate_reason == "within_thresholds" else "FAIL"
    else:
        status = "PASS"

    cycle_record = {
        "cycle": cycle_number,
        "timestamp": _now_utc_iso(),
        "run_id": run_id,
        "status": status,
        "extraction_attempts": extraction_attempts,
        "extraction_success": extraction_success,
        "extraction_failed": extraction_failed,
        "fail_count": fail_count,
        "fail_rate_pct": float(run_metrics.get("extraction_fail_rate_pct", 0) or 0),
        "throughput_per_hour": float(run_metrics.get("extraction_throughput_per_hour", 0) or 0),
        "action": gate_action,
        "gate_reason": gate_reason,
        "rolling_avg_score": run_metrics.get("rolling_avg_score"),
        "rolling_fail_ratio": run_metrics.get("rolling_fail_ratio"),
    }
    cycles.append(cycle_record)

    trend = _convergence_trend(cycles)
    consecutive_regressions = 0
    for c in reversed(cycles):
        if c.get("status") in ("FAIL", "WARN"):
            consecutive_regressions += 1
        else:
            break

    # Determine overall status
    if consecutive_regressions >= CONVERGENCE_REGRESSION_LIMIT:
        overall_status = "stalled"
    elif trend == "plateau" and len(cycles) >= 5:
        overall_status = "plateau"
    elif gate_action == "continue_extracting" and fail_count == 0:
        overall_status = "target_reached_PASS"
    else:
        overall_status = "running"

    state.update(
        {
            "cycles": cycles,
            "updated": _now_utc_iso(),
            "status": overall_status,
            "trend": trend,
            "consecutive_regressions": consecutive_regressions,
            "total_cycles": len(cycles),
            "total_extracted": sum(c.get("extraction_success", 0) for c in cycles),
            "total_failed": sum(c.get("extraction_failed", 0) for c in cycles),
        }
    )
    _write_json(_convergence_state_path(label), state)

    # Emit convergence event to shared memory artifacts (SPARTA-compatible)
    convergence_events_path = MEMORY_DIR / ".artifacts" / "extractor_convergence_events.jsonl"
    convergence_event = {
        "event_type": "extractor_convergence_cycle",
        "timestamp": _now_utc_iso(),
        "label": label,
        "run_id": run_id,
        "cycle": cycle_number,
        "status": status,
        "trend": trend,
        "overall_status": overall_status,
        "extraction_attempts": extraction_attempts,
        "extraction_success": extraction_success,
        "extraction_failed": extraction_failed,
        "fail_rate_pct": cycle_record["fail_rate_pct"],
        "throughput_per_hour": cycle_record["throughput_per_hour"],
        "rolling_avg_score": cycle_record.get("rolling_avg_score"),
        "rolling_fail_ratio": cycle_record.get("rolling_fail_ratio"),
        "consecutive_regressions": consecutive_regressions,
        "total_cycles": len(cycles),
        "total_extracted": state["total_extracted"],
        "total_failed": state["total_failed"],
        "gate_action": gate_action,
        "gate_reason": gate_reason,
    }
    try:
        _append_jsonl(convergence_events_path, convergence_event)
    except Exception as exc:
        logger.warning(f"convergence_event_write_failed error={type(exc).__name__}")

    return state
