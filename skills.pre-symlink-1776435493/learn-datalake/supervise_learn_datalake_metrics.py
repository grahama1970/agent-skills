"""supervise_learn_datalake metrics and quality-gate module.

Log metrics collection, quality-gate evaluation, and targeted
debug-chain orchestration.
"""

from __future__ import annotations

import shlex
import time
from pathlib import Path
from typing import Any

from supervise_learn_datalake_helpers import (
    DEBUG_TABLE_DIR,
    DIAG_DIR,
    DOC_ANALYZED_RE,
    DOC_MISSING_RE,
    DOC_TOTAL_RE,
    EXTRACT_CACHED_PROFILE_RE,
    EXTRACT_EVENT_PDF_RE,
    EXTRACT_FAIL_DETAIL_RE,
    EXTRACT_FAIL_RE,
    EXTRACT_PREFLIGHT_FAIL_RE,
    EXTRACT_SUCCESS_RE,
    EXTRACT_TIMEOUT_HINT_RE,
    FIXTURE_TRICKY_DIR,
    LOOP_HEALTH_RE,
    MEMORY_RETRY_DEAD_LETTER,
    MEMORY_RETRY_QUEUE,
    OVERALL_SCORE_RE,
    REVIEW_PDF_DIR,
    ROLLING_QUALITY_RE,
    TIMEOUT_MODEL_EVENT_RE,
    _count_jsonl_records,
    _normalize_pdf_path,
    _now_utc_iso,
    _run_shell_command,
    _tail_text,
)


def _append_recent_failure(
    *,
    metrics: dict[str, Any],
    pdf_path: str,
    reason: str,
    max_items: int = 32,
) -> None:
    normalized = _normalize_pdf_path(pdf_path)
    if not normalized:
        return
    events = list(metrics.get("recent_failed_events", []))
    events = [item for item in events if item.get("pdf") != normalized]
    events.append(
        {
            "pdf": normalized,
            "reason": reason,
            "timestamp": _now_utc_iso(),
        }
    )
    metrics["recent_failed_events"] = events[-max_items:]
    metrics["recent_failed_pdfs"] = [item["pdf"] for item in metrics["recent_failed_events"]]
    metrics["recent_failed_pdf_count"] = len(metrics["recent_failed_pdfs"])


def _recommended_watchdog_from_step00(
    timeout_seconds: int,
    page_count: int,
    step00_estimated: int,
) -> int:
    baseline = max(3600, timeout_seconds)
    estimate_component = max(0, step00_estimated) * 45
    page_component = max(0, page_count) * 90
    proposed = max(baseline, estimate_component, page_component)
    return int(max(3600, min(43200, proposed + 600)))


def _detect_phase(line: str) -> str | None:
    lowered = line.lower()
    if "discover_profiles" in lowered or "discover_pdfs" in lowered:
        return "discover"
    if "discover_progress" in lowered or "extract_missing status=" in lowered:
        return "extract"
    if "rolling_quality" in lowered or "documents_total=" in lowered:
        return "score"
    if "hard_fail" in lowered or "auto_debug" in lowered:
        return "debug"
    if "loop cycle=" in lowered:
        return "evaluate"
    if "review-pdf summary" in lowered:
        return "summary"
    return None


def _collect_run_metrics(
    *,
    run_log: Path,
    heartbeat_timeout_seconds: int,
) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "phase": "startup",
        "phase_age_seconds": 0,
        "documents_total": 0,
        "documents_analyzed": 0,
        "documents_missing": 0,
        "documents_missing_ratio": None,
        "rolling_docs_analyzed": 0,
        "rolling_avg_score": None,
        "rolling_fail_ratio": None,
        "rolling_critical_doc_ratio": None,
        "overall_average_score": None,
        "last_loop_healthy": None,
        "last_loop_score": None,
        "last_loop_fail_ratio": None,
        "loop_cycle_count": 0,
        "extraction_success_count": 0,
        "extraction_cached_profile_count": 0,
        "extraction_failed_count": 0,
        "extraction_timeout_count": 0,
        "extraction_missing_structural_count": 0,
        "extraction_timeout_hint_count": 0,
        "extraction_attempts": 0,
        "extraction_deferred_count": 0,
        "preflight_failed_count": 0,
        "extraction_timeout_rate_pct": 0.0,
        "extraction_fail_rate_pct": 0.0,
        "extraction_missing_structural_rate_pct": 0.0,
        "timeout_model_decisions": 0,
        "timeout_model_used_count": 0,
        "timeout_model_used_rate_pct": 0.0,
        "timeout_model_high_risk_count": 0,
        "timeout_model_last_risk": 0.0,
        "recent_failed_events": [],
        "recent_failed_pdfs": [],
        "recent_failed_pdf_count": 0,
        "recommended_watchdog_seconds": 0,
        "adaptive_heartbeat_timeout_seconds": heartbeat_timeout_seconds,
        "last_extracted_pdf": "",
        "memory_retry_queue_count": _count_jsonl_records(MEMORY_RETRY_QUEUE),
        "memory_retry_dead_letter_count": _count_jsonl_records(MEMORY_RETRY_DEAD_LETTER),
    }
    if not run_log.exists():
        return metrics

    phase_seen_at: dict[str, int] = {}
    lines = _tail_text(run_log, max_lines=3000).splitlines()
    now_epoch = int(time.time())
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Skip extremely long lines (base64 image data, serialized blobs)
        # to avoid regex catastrophic backtracking.
        if len(stripped) > 10000:
            continue
        phase = _detect_phase(stripped)
        if phase:
            metrics["phase"] = phase
            phase_seen_at[phase] = now_epoch
        if EXTRACT_SUCCESS_RE.search(stripped):
            metrics["extraction_success_count"] = int(metrics["extraction_success_count"]) + 1
            match_pdf = EXTRACT_EVENT_PDF_RE.search(stripped)
            if match_pdf:
                metrics["last_extracted_pdf"] = match_pdf.group("pdf").strip()
        if EXTRACT_CACHED_PROFILE_RE.search(stripped):
            metrics["extraction_cached_profile_count"] = (
                int(metrics["extraction_cached_profile_count"]) + 1
            )
        # Preflight failures -- triaged, don't count as extraction attempts
        preflight_match = EXTRACT_PREFLIGHT_FAIL_RE.search(stripped)
        if preflight_match:
            metrics["preflight_failed_count"] = int(metrics["preflight_failed_count"]) + 1
            _append_recent_failure(
                metrics=metrics,
                pdf_path=preflight_match.group("pdf") or "",
                reason=f"preflight_{preflight_match.group('reason') or 'unknown'}",
            )
            continue
        if EXTRACT_FAIL_RE.search(stripped):
            # Check if this is a Chutes transient failure -> defer, not fail
            if "chutes.ai" in stripped.lower() or "503" in stripped:
                metrics["extraction_deferred_count"] = int(metrics["extraction_deferred_count"]) + 1
            else:
                metrics["extraction_failed_count"] = int(metrics["extraction_failed_count"]) + 1
        fail_detail_match = EXTRACT_FAIL_DETAIL_RE.search(stripped)
        if fail_detail_match:
            timed_out = fail_detail_match.group("timed") == "1"
            missing_structural = fail_detail_match.group("missing_structural") == "1"
            if timed_out:
                metrics["extraction_timeout_count"] = int(metrics["extraction_timeout_count"]) + 1
            if missing_structural:
                metrics["extraction_missing_structural_count"] = (
                    int(metrics["extraction_missing_structural_count"]) + 1
                )
            _append_recent_failure(
                metrics=metrics,
                pdf_path=fail_detail_match.group("pdf"),
                reason="extract_timeout" if timed_out else "extract_failed",
            )
        event_match = EXTRACT_EVENT_PDF_RE.search(stripped)
        if event_match:
            status = event_match.group("status")
            pdf_path = event_match.group("pdf")
            if status not in {"extracted", "extract_failed", "cached_profile", "preflight_failed"}:
                _append_recent_failure(
                    metrics=metrics, pdf_path=pdf_path, reason=f"extract_{status}"
                )
        timeout_match = EXTRACT_TIMEOUT_HINT_RE.search(stripped)
        if timeout_match:
            metrics["extraction_timeout_hint_count"] = (
                int(metrics["extraction_timeout_hint_count"]) + 1
            )
            timeout_seconds = int(timeout_match.group("seconds"))
            page_count = int(timeout_match.group("page_count"))
            step00_estimated = int(timeout_match.group("step00_estimated"))
            recommended = _recommended_watchdog_from_step00(
                timeout_seconds=timeout_seconds,
                page_count=page_count,
                step00_estimated=step00_estimated,
            )
            metrics["recommended_watchdog_seconds"] = max(
                int(metrics["recommended_watchdog_seconds"]),
                recommended,
            )
        timeout_model_match = TIMEOUT_MODEL_EVENT_RE.search(stripped)
        if timeout_model_match:
            metrics["timeout_model_decisions"] = int(metrics["timeout_model_decisions"]) + 1
            risk = float(timeout_model_match.group("risk"))
            metrics["timeout_model_last_risk"] = round(risk, 4)
            if timeout_model_match.group("used") == "1":
                metrics["timeout_model_used_count"] = int(metrics["timeout_model_used_count"]) + 1
            if risk >= 0.5:
                metrics["timeout_model_high_risk_count"] = (
                    int(metrics["timeout_model_high_risk_count"]) + 1
                )
        rolling_match = ROLLING_QUALITY_RE.search(stripped)
        if rolling_match:
            metrics["rolling_docs_analyzed"] = int(rolling_match.group("analyzed"))
            metrics["rolling_avg_score"] = float(rolling_match.group("avg_score"))
            metrics["rolling_fail_ratio"] = float(rolling_match.group("fail_ratio"))
            metrics["rolling_critical_doc_ratio"] = float(rolling_match.group("critical_ratio"))
        loop_match = LOOP_HEALTH_RE.search(stripped)
        if loop_match:
            metrics["loop_cycle_count"] = int(loop_match.group("cycle"))
            metrics["last_loop_healthy"] = loop_match.group("healthy") == "True"
            metrics["last_loop_score"] = float(loop_match.group("score"))
            metrics["last_loop_fail_ratio"] = float(loop_match.group("fail_ratio"))
        total_match = DOC_TOTAL_RE.search(stripped)
        if total_match:
            metrics["documents_total"] = int(total_match.group("value"))
        analyzed_match = DOC_ANALYZED_RE.search(stripped)
        if analyzed_match:
            metrics["documents_analyzed"] = int(analyzed_match.group("value"))
        missing_match = DOC_MISSING_RE.search(stripped)
        if missing_match:
            metrics["documents_missing"] = int(missing_match.group("value"))
        score_match = OVERALL_SCORE_RE.search(stripped)
        if score_match:
            metrics["overall_average_score"] = float(score_match.group("value"))

    # Include cached_profile in attempts -- these are already-extracted PDFs and
    # should not inflate the fail rate.  Without this, a 93%-cached corpus shows
    # near-100% fail rate because only the handful of new (failing) extractions
    # are counted, triggering the quality gate restart loop.
    attempts = (
        int(metrics["extraction_success_count"])
        + int(metrics["extraction_failed_count"])
        + int(metrics["extraction_cached_profile_count"])
    )
    metrics["extraction_attempts"] = attempts
    if attempts > 0:
        metrics["extraction_timeout_rate_pct"] = round(
            100.0 * int(metrics["extraction_timeout_count"]) / attempts,
            2,
        )
        metrics["extraction_fail_rate_pct"] = round(
            100.0 * int(metrics["extraction_failed_count"]) / attempts,
            2,
        )
        metrics["extraction_missing_structural_rate_pct"] = round(
            100.0 * int(metrics["extraction_missing_structural_count"]) / attempts,
            2,
        )
    timeout_model_decisions = int(metrics["timeout_model_decisions"])
    if timeout_model_decisions > 0:
        metrics["timeout_model_used_rate_pct"] = round(
            100.0 * int(metrics["timeout_model_used_count"]) / timeout_model_decisions,
            2,
        )
    docs_total = int(metrics["documents_total"])
    if docs_total > 0:
        metrics["documents_missing_ratio"] = round(
            int(metrics["documents_missing"]) / docs_total,
            4,
        )
    effective_heartbeat = max(
        heartbeat_timeout_seconds,
        int(metrics["recommended_watchdog_seconds"] or 0),
    )
    metrics["adaptive_heartbeat_timeout_seconds"] = effective_heartbeat
    metrics["phase_age_seconds"] = (
        0 if not phase_seen_at else max(0, int(time.time()) - max(phase_seen_at.values()))
    )
    return metrics


def _apply_quality_gate(
    metrics: dict[str, Any],
    *,
    target_score: float,
    target_fail_ratio: float,
    blacklist_count: int = 0,
    expected_fail_floor: float = 0.0,
) -> dict[str, str]:
    docs_total = int(metrics.get("documents_total", 0) or 0)
    docs_analyzed = int(metrics.get("documents_analyzed", 0) or 0)
    docs_missing_ratio = metrics.get("documents_missing_ratio")
    phase = str(metrics.get("phase", "") or "")
    phase_age_seconds = int(metrics.get("phase_age_seconds", 0) or 0)
    loop_cycles = int(metrics.get("loop_cycle_count", 0) or 0)
    rolling_docs = int(metrics.get("rolling_docs_analyzed", 0) or 0)
    rolling_score = metrics.get("rolling_avg_score")
    rolling_fail = metrics.get("rolling_fail_ratio")
    extraction_attempts = int(metrics.get("extraction_attempts", 0) or 0)
    extraction_successes = int(metrics.get("extraction_success_count", 0) or 0)
    extraction_fail_rate_pct = float(metrics.get("extraction_fail_rate_pct", 0.0) or 0.0)
    extraction_missing_structural_rate_pct = float(
        metrics.get("extraction_missing_structural_rate_pct", 0.0) or 0.0
    )
    extraction_timeout_rate_pct = float(metrics.get("extraction_timeout_rate_pct", 0.0) or 0.0)

    preflight_failed = int(metrics.get("preflight_failed_count", 0) or 0)
    deferred = int(metrics.get("extraction_deferred_count", 0) or 0)

    # If preflight triage is actively filtering PDFs, the high fail rate on
    # remaining extractions is expected (we're in the hard tail). Don't escalate
    # when triage is making progress -- the system is working as designed.
    triage_active = preflight_failed >= 3 or deferred >= 3

    # Adjust fail rate threshold for known-unextractable PDFs.
    # The blacklist represents an inherent failure floor -- don't penalize the
    # pipeline for PDFs that will never extract (corrupted, encrypted, etc.).
    effective_fail_threshold = 60.0
    if expected_fail_floor > 0 and extraction_attempts > 0:
        floor_pct = expected_fail_floor * 100.0
        effective_fail_threshold = max(effective_fail_threshold, floor_pct + 10.0)

    # Only escalate when there are real (non-cached) attempts with zero success.
    # Cached profiles are a success state -- the PDF was already extracted.
    # With 93%+ corpus cached, batches of 50 can easily be all cached -> false escalation.
    extraction_cached = int(metrics.get("extraction_cached_profile_count", 0) or 0)
    real_attempts = extraction_attempts - extraction_cached
    if real_attempts >= 50 and extraction_successes == 0 and not triage_active:
        return {
            "quality_gate_action": "diagnose_debug_resume",
            "quality_gate_reason": "zero_extraction_success_after_50_attempts",
        }
    if extraction_attempts >= 20 and extraction_fail_rate_pct >= effective_fail_threshold and not triage_active:
        return {
            "quality_gate_action": "diagnose_debug_resume",
            "quality_gate_reason": f"extraction_fail_rate_high (threshold={effective_fail_threshold:.1f}%)",
        }
    # When triage is active but fail rate is still extreme, allow continuation
    # with a note -- the blacklist will grow and eventually clear the backlog
    if triage_active and extraction_attempts > 0 and extraction_fail_rate_pct >= 60.0:
        return {
            "quality_gate_action": "continue_extracting",
            "quality_gate_reason": (
                f"triage_active_high_fail_rate "
                f"preflight={preflight_failed} deferred={deferred} "
                f"fail_rate={extraction_fail_rate_pct:.1f}%"
            ),
        }
    if extraction_attempts >= 20 and extraction_missing_structural_rate_pct >= 40.0:
        return {
            "quality_gate_action": "diagnose_debug_resume",
            "quality_gate_reason": "missing_structural_rate_high",
        }
    if extraction_attempts >= 20 and extraction_timeout_rate_pct >= 20.0:
        return {
            "quality_gate_action": "diagnose_debug_resume",
            "quality_gate_reason": "timeout_rate_high",
        }
    if (
        docs_total >= 50
        and isinstance(docs_missing_ratio, (int, float))
        and float(docs_missing_ratio) > 0.20
    ):
        if phase in {"discover", "extract"} and phase_age_seconds < 1800:
            return {
                "quality_gate_action": "continue_extracting",
                "quality_gate_reason": "coverage_backlog_in_progress",
            }
        if loop_cycles == 0 or docs_analyzed < 50:
            return {
                "quality_gate_action": "continue_extracting",
                "quality_gate_reason": "coverage_pending_cycle_completion",
            }
        return {
            "quality_gate_action": "diagnose_debug_resume",
            "quality_gate_reason": "documents_missing_ratio_high",
        }
    if (
        rolling_docs >= 10
        and isinstance(rolling_score, (int, float))
        and float(rolling_score) < float(target_score)
    ):
        return {
            "quality_gate_action": "diagnose_debug_resume",
            "quality_gate_reason": "rolling_score_below_target_early",
        }
    if (
        rolling_docs >= 10
        and isinstance(rolling_fail, (int, float))
        and float(rolling_fail) > float(target_fail_ratio)
    ):
        return {
            "quality_gate_action": "diagnose_debug_resume",
            "quality_gate_reason": "rolling_fail_ratio_above_target_early",
        }
    return {
        "quality_gate_action": "continue_extracting",
        "quality_gate_reason": "within_thresholds",
    }


def _run_targeted_debug_chain(
    *,
    run_id: str,
    recent_failed_pdfs: list[str],
    timeout_seconds: int,
    max_failure_samples: int,
) -> dict[str, Any]:
    output_dir = DIAG_DIR / f"targeted_debug_{run_id}_{int(time.time())}"
    output_dir.mkdir(parents=True, exist_ok=True)
    selected_paths: list[Path] = []
    seen: set[str] = set()
    for raw in recent_failed_pdfs:
        normalized = _normalize_pdf_path(raw)
        if not normalized or normalized in seen:
            continue
        path = Path(normalized)
        if not path.exists():
            continue
        selected_paths.append(path)
        seen.add(normalized)
        if len(selected_paths) >= max_failure_samples:
            break
    if not selected_paths:
        return {
            "status": "skipped",
            "reason": "no_recent_failed_pdfs",
            "output_dir": str(output_dir),
        }

    per_pdf_timeout = max(600, min(2400, timeout_seconds // max(1, len(selected_paths))))
    pdf_results: list[dict[str, Any]] = []
    for index, pdf_path in enumerate(selected_paths, start=1):
        review_output_dir = output_dir / f"review_{index}"
        review_output_dir.mkdir(parents=True, exist_ok=True)
        review_cmd = (
            f"./run.sh check {shlex.quote(str(pdf_path))} "
            f"--output-dir {shlex.quote(str(review_output_dir))} "
            "--execute-jobs --max-jobs-per-doc 2 --extract-missing "
            "--ingest-memory --memory-scope datalake_pdf "
            "--taxonomy-collection operational"
        )
        review_result = _run_shell_command(
            cmd=review_cmd,
            cwd=REVIEW_PDF_DIR,
            timeout_seconds=per_pdf_timeout,
        )
        table_cmd = (
            f"./run.sh tune {shlex.quote(str(pdf_path))} --converge --max-iterations 2 --json"
        )
        table_result = _run_shell_command(
            cmd=table_cmd,
            cwd=DEBUG_TABLE_DIR,
            timeout_seconds=max(900, per_pdf_timeout),
        )
        pdf_results.append(
            {
                "pdf": str(pdf_path),
                "review_pdf_check": review_result,
                "debug_table_tune": table_result,
            }
        )

    fixture_dir = output_dir / "fixtures"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    fixture_commands = [
        (
            "gauntlet",
            f"./run.sh gauntlet --output {shlex.quote(str(fixture_dir / 'gauntlet.pdf'))}",
            1800,
        ),
        (
            "malformed_tables",
            f"./run.sh malformed-tables --output "
            f"{shlex.quote(str(fixture_dir / 'malformed_tables.pdf'))}",
            1200,
        ),
        (
            "cursed_text",
            f"./run.sh cursed-text --output {shlex.quote(str(fixture_dir / 'cursed_text.pdf'))}",
            1200,
        ),
    ]
    fixture_results: list[dict[str, Any]] = []
    for name, cmd, command_timeout in fixture_commands:
        result = _run_shell_command(
            cmd=cmd,
            cwd=FIXTURE_TRICKY_DIR,
            timeout_seconds=min(timeout_seconds, command_timeout),
        )
        result["name"] = name
        fixture_results.append(result)
    return {
        "status": "ok",
        "output_dir": str(output_dir),
        "sampled_pdf_count": len(selected_paths),
        "selected_pdfs": [str(path) for path in selected_paths],
        "pdf_results": pdf_results,
        "fixture_results": fixture_results,
    }
