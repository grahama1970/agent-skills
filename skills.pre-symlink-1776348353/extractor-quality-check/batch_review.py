#!/usr/bin/env python3
"""Batch review — Margaret Chen + Jennifer Cheung persona-driven quality gate.

Mirrors Brandon Bailey's watchdog pattern in sparta/scripts/qra_brandon_watchdog.py.
Called by the supervisor loop after quality gate evaluation, before escalation decision.

Stratified sampling lives in batch_sampling.py (split for module size).

Usage:
    # Standalone test
    python batch_review.py --run-id corpus_1770904449

    # Programmatic (called by supervisor)
    from batch_review import run_batch_review
    result = run_batch_review(run_id=..., run_metrics=..., ...)
"""

import typer
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path.home() / ".pi" / "skills"))
    from common.task_monitor import TaskClient
except ImportError:
    TaskClient = None

from annealing import (
    get_annealing_thresholds,
    jennifer_evaluates,
    margaret_evaluates,
    reconcile,
    should_continue_extraction,
)

# Import shared state utilities and stratified sampling from batch_sampling.
# stratified_sample_review is re-exported here for backward compatibility —
# the supervisor loads batch_review via importlib and calls mod.stratified_sample_review().
from batch_sampling import (
    _collect_state,
    _compute_coverage_pct,
    stratified_sample_review,
)

# Rate-limit dogpile calls: at most once per 30 minutes
_DOGPILE_COOLDOWN_SECONDS = 1800
_DOGPILE_STATE_FILE = Path(__file__).parent / ".dogpile_last_run"


def run_batch_review(
    run_id: str,
    run_metrics: dict,
    recent_failed_pdfs: list[str] | None = None,
    gate_action: str = "",
    gate_reason: str = "",
) -> dict:
    """Margaret Chen + Jennifer Cheung batch review.

    Called after quality gate evaluation. Returns a decision that can
    override or escalate the gate's verdict.

    Args:
        run_id: Current supervisor run ID
        run_metrics: Run metrics dict from supervisor
        recent_failed_pdfs: List of recently failed PDF paths
        gate_action: Quality gate action (continue_extracting, diagnose_debug_resume)
        gate_reason: Quality gate reason string

    Returns:
        {
            "decision": "CONTINUE" | "STOP_AND_FIX" | "ESCALATE",
            "phase": str,
            "adjustments": [...],
            "margaret_says": str,
            "jennifer_says": str,
            "thresholds": dict,
            "metrics": dict,
            "timestamp": str,
        }
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    recent_failed_pdfs = recent_failed_pdfs or []
    monitor = TaskClient("extractor-quality-check", total=5) if TaskClient else None

    # Collect live state
    state = _collect_state()
    if monitor:
        monitor.update(item="collect_state")
    coverage_pct = _compute_coverage_pct(state)

    # Extract scoring metrics
    avg_score = run_metrics.get("rolling_avg_score")
    fail_ratio = run_metrics.get("rolling_fail_ratio", 0.0) or 0.0
    critical_ratio = run_metrics.get("rolling_critical_doc_ratio", 0.0) or 0.0

    # Extract dimension scores from review aggregate
    agg = state.get("review_aggregate", {})
    dim_scores = agg.get("average_dimension_scores", {})

    # Independent persona evaluations
    margaret_result = margaret_evaluates(
        coverage_pct=coverage_pct,
        dim_scores=dim_scores,
        fail_ratio=fail_ratio,
        critical_ratio=critical_ratio,
        run_metrics=run_metrics,
        state=state,
    )
    jennifer_result = jennifer_evaluates(
        coverage_pct=coverage_pct,
        dim_scores=dim_scores,
        fail_ratio=fail_ratio,
        critical_ratio=critical_ratio,
        run_metrics=run_metrics,
        state=state,
    )
    reconciled = reconcile(margaret_result, jennifer_result)
    if monitor:
        monitor.update(item="persona_evaluation")

    # Build decision dict — preserves interface for supervisor hook
    thresholds = get_annealing_thresholds(coverage_pct)
    decision = {
        "decision": reconciled["decision"],
        "phase": thresholds["phase_name"],
        "thresholds": thresholds,
        "margaret_says": margaret_result["says"],
        "jennifer_says": jennifer_result["says"],
        "consensus": reconciled["consensus"],
        "margaret_verdict": reconciled["margaret_verdict"],
        "jennifer_verdict": reconciled["jennifer_verdict"],
        "disagreement_reason": reconciled.get("disagreement_reason"),
        "margaret_weighted_score": margaret_result["weighted_score"],
        "jennifer_weighted_score": jennifer_result["weighted_score"],
        "metrics": {
            "avg_score": avg_score,
            "fail_ratio": fail_ratio,
            "critical_ratio": critical_ratio,
        },
    }

    # If both had issues, merge them
    all_issues = margaret_result.get("issues", []) + jennifer_result.get("issues", [])
    if all_issues:
        decision["issues"] = all_issues

    # Build adjustments based on diagnosis
    adjustments = _compute_adjustments(
        run_metrics=run_metrics,
        recent_failed_pdfs=recent_failed_pdfs,
        gate_action=gate_action,
        gate_reason=gate_reason,
        state=state,
    )

    # Check for specific red flags that personas care about
    red_flags = _check_red_flags(run_metrics, state)
    if red_flags:
        # Red flags can escalate a CONTINUE to STOP_AND_FIX
        if decision["decision"] == "CONTINUE" and len(red_flags) >= 2:
            decision["decision"] = "STOP_AND_FIX"
            decision["margaret_says"] = (
                f"Gate says continue but I see {len(red_flags)} red flags: "
                f"{'; '.join(red_flags)}. Pausing until addressed."
            )
            decision["jennifer_says"] = (
                "Concur with Margaret. These flags indicate systemic issues."
            )

    if monitor:
        monitor.update(item="red_flags")
    # Diagnose failure patterns
    diagnosis = _diagnose_failures(recent_failed_pdfs, run_metrics, state)

    # Enrich persona commentary with diagnosis
    if diagnosis["failure_count"] > 0:
        if diagnosis["margaret_diagnosis"] and decision.get("margaret_says"):
            decision["margaret_says"] += f" Diagnosis: {diagnosis['margaret_diagnosis']}"
        if diagnosis["jennifer_diagnosis"] and decision.get("jennifer_says"):
            decision["jennifer_says"] += f" Assessment: {diagnosis['jennifer_diagnosis']}"

    # Merge disagreement research queries with diagnosis queries
    all_research_queries = diagnosis.get("research_queries", [])
    if reconciled.get("research_queries"):
        all_research_queries = reconciled["research_queries"] + all_research_queries
    all_research_queries = all_research_queries[:3]  # Cap at 3

    if monitor:
        monitor.update(item="diagnosis")
    # Trigger /dogpile research if STOP_AND_FIX and we have research queries
    dogpile_results = _maybe_dogpile(
        all_research_queries,
        decision["decision"],
    )

    if monitor:
        monitor.finish()
    return {
        **decision,
        "adjustments": adjustments,
        "red_flags": red_flags,
        "diagnosis": diagnosis,
        "dogpile_results": dogpile_results,
        "run_id": run_id,
        "gate_action": gate_action,
        "gate_reason": gate_reason,
        "coverage_pct": coverage_pct,
        "timestamp": timestamp,
    }


def _compute_adjustments(
    run_metrics: dict,
    recent_failed_pdfs: list[str],
    gate_action: str,
    gate_reason: str,
    state: dict,
) -> list[dict]:
    """Compute specific adjustments based on diagnosis."""
    adjustments = []

    # High timeout rate
    timeout_rate = run_metrics.get("extraction_timeout_rate_pct", 0)
    if timeout_rate > 10:
        adjustments.append({
            "type": "timeout_model",
            "action": "tune_page_bounds",
            "reason": f"Timeout rate {timeout_rate:.1f}% exceeds 10%",
            "margaret_says": "Timeout model needs tighter page-count bounds.",
        })

    # High fail rate
    fail_rate = run_metrics.get("extraction_fail_rate_pct", 0)
    if fail_rate > 20:
        adjustments.append({
            "type": "extraction_config",
            "action": "diagnose_failures",
            "reason": f"Extraction fail rate {fail_rate:.1f}% exceeds 20%",
            "margaret_says": "Something is systematically wrong. Check stderr logs.",
        })

    # Dead letter queue growing
    dead_letters = run_metrics.get("memory_retry_dead_letter_count", 0)
    if dead_letters > 20:
        adjustments.append({
            "type": "memory_pipeline",
            "action": "drain_dead_letters",
            "reason": f"Dead letter queue at {dead_letters}",
            "jennifer_says": "Memory pipeline is backing up. Investigate retry failures.",
        })

    # Restart count high
    sup = state.get("supervisor", {})
    restart_count = sup.get("restart_count", 0)
    if restart_count > 20:
        adjustments.append({
            "type": "stability",
            "action": "investigate_restarts",
            "reason": f"Supervisor has restarted {restart_count} times",
            "jennifer_says": "Pipeline instability. Root-cause the restart pattern.",
        })

    # Coverage gaps
    coverage = state.get("coverage", {})
    gaps = coverage.get("sector_gaps", {})
    critical_gap_sectors = [s for s, g in gaps.items() if g >= 500 and s in ("faa", "nasa", "dtic")]
    if critical_gap_sectors:
        adjustments.append({
            "type": "coverage",
            "action": "prioritize_sectors",
            "sectors": critical_gap_sectors,
            "reason": f"Safety-critical sectors with zero coverage: {', '.join(critical_gap_sectors)}",
            "margaret_says": f"We have ZERO coverage in {', '.join(critical_gap_sectors)}. Unacceptable.",
        })

    return adjustments


def _check_red_flags(run_metrics: dict, state: dict) -> list[str]:
    """Check for red flags that personas would flag."""
    flags = []

    # Gate consecutive failures
    gate_failures = run_metrics.get("quality_gate_consecutive_failures", 0)
    if gate_failures >= 2:
        flags.append(f"quality_gate_consecutive_failures={gate_failures}")

    # Extraction fail rate high
    fail_rate = run_metrics.get("extraction_fail_rate_pct", 0)
    if fail_rate > 30:
        flags.append(f"extraction_fail_rate={fail_rate:.1f}%")

    # Missing structural rate high
    missing_structural = run_metrics.get("extraction_missing_structural_rate_pct", 0)
    if missing_structural > 15:
        flags.append(f"missing_structural_rate={missing_structural:.1f}%")

    # Recent convergence regressions
    events = state.get("convergence_events", [])
    recent_regressions = sum(1 for e in events[-5:] if e.get("event_type") == "regression")
    if recent_regressions >= 3:
        flags.append(f"recent_regressions={recent_regressions}/5")

    # No scores after many extractions
    attempts = run_metrics.get("extraction_attempts", 0)
    avg_score = run_metrics.get("rolling_avg_score")
    if attempts > 50 and avg_score is None:
        flags.append(f"no_scores_after_{attempts}_extractions")

    return flags


def _diagnose_failures(
    recent_failed_pdfs: list[str],
    run_metrics: dict,
    state: dict,
) -> dict:
    """Analyze failure patterns to generate diagnosis and research queries.

    Returns:
        {
            "failure_count": int,
            "patterns": [{"pattern": str, "count": int, "pdfs": list}],
            "sector_breakdown": {sector: count},
            "dominant_failure_type": str,
            "research_queries": [str],  # For /dogpile
            "margaret_diagnosis": str,
            "jennifer_diagnosis": str,
        }
    """
    if not recent_failed_pdfs:
        return {"failure_count": 0, "patterns": [], "sector_breakdown": {},
                "dominant_failure_type": "none", "research_queries": [],
                "margaret_diagnosis": "No recent failures.",
                "jennifer_diagnosis": "Clean run."}

    # Sector breakdown — extract sector from corpus path
    sector_breakdown: dict[str, int] = {}
    corpus_prefix = os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb") + "/extractor_corpus/"
    for pdf in recent_failed_pdfs:
        if pdf.startswith(corpus_prefix):
            rel = pdf[len(corpus_prefix):]
            sector = rel.split("/")[0] if "/" in rel else "unknown"
        else:
            sector = "external"
        sector_breakdown[sector] = sector_breakdown.get(sector, 0) + 1

    # Failure type patterns from run_metrics
    patterns = []
    timeout_count = run_metrics.get("extraction_timeout_count", 0)
    fail_count = run_metrics.get("extraction_failed_count", 0)
    missing_structural = run_metrics.get("extraction_missing_structural_count", 0)

    if timeout_count > 0:
        patterns.append({"pattern": "timeout", "count": timeout_count,
                         "pdfs": [p for p in recent_failed_pdfs if "timeout" in p.lower()]})
    if fail_count > 0:
        patterns.append({"pattern": "extraction_error", "count": fail_count,
                         "pdfs": recent_failed_pdfs[:5]})
    if missing_structural > 0:
        patterns.append({"pattern": "missing_structural", "count": missing_structural, "pdfs": []})

    # Identify filename patterns (e.g., "archive_" prefix = historical docs)
    archive_count = sum(1 for p in recent_failed_pdfs if "archive_" in Path(p).name.lower())
    if archive_count > len(recent_failed_pdfs) * 0.5:
        patterns.append({"pattern": "archive_documents", "count": archive_count,
                         "pdfs": [p for p in recent_failed_pdfs if "archive_" in Path(p).name.lower()][:3]})

    # Dominant failure type
    dominant = "unknown"
    if timeout_count > fail_count and timeout_count > missing_structural:
        dominant = "timeout"
    elif fail_count > timeout_count:
        dominant = "extraction_error"
    elif missing_structural > 0:
        dominant = "missing_structural"

    # Build research queries for /dogpile
    research_queries = []
    top_sector = max(sector_breakdown, key=sector_breakdown.get) if sector_breakdown else None

    if dominant == "timeout" and top_sector:
        research_queries.append(
            f"PDF extraction timeout optimization for {top_sector} documents "
            f"large page count OCR performance"
        )
    if dominant == "extraction_error":
        # Look at recent_failed_events from run_metrics for stderr hints
        recent_events = run_metrics.get("recent_failed_events", [])
        if recent_events:
            last_reason = recent_events[-1].get("reason", "")
            research_queries.append(
                f"PDF extraction failure {last_reason} troubleshooting document processing"
            )
    if top_sector == "dtic":
        research_queries.append(
            "DTIC technical report PDF structure common extraction issues "
            "defense document formatting OCR challenges"
        )
    elif top_sector == "nasa":
        research_queries.append(
            "NASA technical report PDF extraction multi-column layout "
            "scientific document table extraction"
        )
    elif top_sector == "faa":
        research_queries.append(
            "FAA advisory circular PDF extraction DO-178C document structure "
            "aviation regulatory document processing"
        )

    if archive_count > 0:
        research_queries.append(
            "scanned historical document OCR extraction quality "
            "archive PDF poor quality text extraction"
        )

    # Persona diagnoses
    margaret = []
    jennifer = []

    if timeout_count > 3:
        margaret.append(f"{timeout_count} timeouts — timeout model needs recalibration")
    if fail_count > 3:
        margaret.append(f"{fail_count} extraction failures — check stderr logs for root cause")
    if missing_structural > 0:
        margaret.append(f"{missing_structural} missing structural outputs — pipeline stage failure")
    if archive_count > 2:
        margaret.append(f"{archive_count} archive docs failing — likely poor scan quality")

    if top_sector in ("dtic", "faa", "nasa", "defense"):
        jennifer.append(f"Failures concentrated in {top_sector} — safety-critical sector, priority fix")
    if sector_breakdown and len(sector_breakdown) == 1:
        jennifer.append(f"All failures in single sector ({top_sector}) — likely sector-specific issue")
    elif sector_breakdown and len(sector_breakdown) > 3:
        jennifer.append(f"Failures spread across {len(sector_breakdown)} sectors — systemic issue")

    return {
        "failure_count": len(recent_failed_pdfs),
        "patterns": patterns,
        "sector_breakdown": sector_breakdown,
        "dominant_failure_type": dominant,
        "research_queries": research_queries[:3],  # Cap at 3
        "margaret_diagnosis": " | ".join(margaret) if margaret else "Failures within acceptable limits.",
        "jennifer_diagnosis": " | ".join(jennifer) if jennifer else "No sector-specific concerns.",
    }


def _maybe_dogpile(research_queries: list[str], decision: str) -> list[dict]:
    """Run /dogpile for research if STOP_AND_FIX and cooldown has elapsed.

    Rate-limited to avoid blocking the supervisor poll loop.
    Returns list of research results (may be empty).
    """
    if decision != "STOP_AND_FIX" or not research_queries:
        return []

    # Check cooldown
    now = datetime.now(timezone.utc).timestamp()
    if _DOGPILE_STATE_FILE.exists():
        try:
            last_run = float(_DOGPILE_STATE_FILE.read_text().strip())
            if now - last_run < _DOGPILE_COOLDOWN_SECONDS:
                return []
        except (ValueError, OSError):
            pass

    results = []
    pi_mono = Path(os.path.expanduser("~/workspace/experiments/pi-mono"))
    dogpile_run = pi_mono / ".pi" / "skills" / "dogpile" / "run.sh"

    if not dogpile_run.exists():
        return []

    # Only run first query (keep it fast)
    query = research_queries[0]
    try:
        result = subprocess.run(
            [str(dogpile_run), "search", query, "--limit", "3", "--json"],
            capture_output=True, text=True, timeout=120,
            cwd=str(dogpile_run.parent),
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode == 0 and result.stdout.strip():
            try:
                data = json.loads(result.stdout)
                results.append({
                    "query": query,
                    "results": data if isinstance(data, list) else [data],
                })
            except json.JSONDecodeError:
                results.append({"query": query, "results": [], "raw": result.stdout[:500]})

        # Update cooldown file
        _DOGPILE_STATE_FILE.write_text(str(now))
    except Exception as e:
        print(f"[batch_review] dogpile failed: {e}", file=sys.stderr)

    return results


# ── Remediation execution ──

# Rate-limit remediation: at most once per 30 minutes
_REMEDIATION_COOLDOWN_SECONDS = 1800
_REMEDIATION_STATE_FILE = Path(__file__).parent / ".remediation_last_run"
MAX_REMEDIATION_JOBS = 3  # Cap background jobs per trigger


def _execute_remediation_jobs(escalation_jobs_list: list[dict]) -> list[dict]:
    """Fire auto-executable escalation jobs as background processes.

    Rate-limited to avoid hammering skills. Returns list of launched/skipped results.
    Non-blocking — uses Popen, not run().
    """
    if not escalation_jobs_list:
        return []

    # Check cooldown
    now = time.time()
    if _REMEDIATION_STATE_FILE.exists():
        try:
            last = float(_REMEDIATION_STATE_FILE.read_text().strip())
            if now - last < _REMEDIATION_COOLDOWN_SECONDS:
                remaining = int(_REMEDIATION_COOLDOWN_SECONDS - (now - last))
                return [{"status": "cooldown", "seconds_remaining": remaining}]
        except (ValueError, OSError):
            pass

    # Write cooldown BEFORE launching jobs to prevent duplicate remediation
    # if the process crashes mid-launch and restarts.
    try:
        _REMEDIATION_STATE_FILE.write_text(str(now))
    except OSError:
        pass

    results = []
    launched = 0
    for job in escalation_jobs_list:
        if not job.get("auto_executable"):
            results.append({
                "command": job["command"],
                "skill": job.get("skill", "?"),
                "status": "skipped_not_auto",
            })
            continue
        if launched >= MAX_REMEDIATION_JOBS:
            results.append({
                "command": job["command"],
                "skill": job.get("skill", "?"),
                "status": "skipped_max_reached",
            })
            continue

        try:
            _remed_log = Path(__file__).parent / ".remediation_stderr.log"
            _remed_fh = open(_remed_log, "a")
            subprocess.Popen(
                ["bash", "-lc", job["command"]],
                stdout=subprocess.DEVNULL,
                stderr=_remed_fh,
                start_new_session=True,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            launched += 1
            results.append({
                "command": job["command"],
                "skill": job.get("skill", "?"),
                "status": "launched",
            })
        except OSError as exc:
            results.append({
                "command": job["command"],
                "skill": job.get("skill", "?"),
                "status": "launch_failed",
                "error": str(exc),
            })

    return results


def main(
    run_id: str = typer.Option(..., help="Supervisor run ID"),
    gate_action: str = typer.Option("continue_extracting", help=""),
    gate_reason: str = typer.Option("within_thresholds", help=""),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):

    # For standalone test, build minimal run_metrics from state
    state = _collect_state()
    sup = state.get("supervisor", {})
    run_metrics = sup.get("run_metrics", {})

    result = run_batch_review(
        run_id=run_id,
        run_metrics=run_metrics,
        recent_failed_pdfs=run_metrics.get("recent_failed_pdfs", []),
        gate_action=gate_action,
        gate_reason=gate_reason,
    )

    if json:
        json.dump(result, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
    else:
        print(f"Decision: {result['decision']}")
        print(f"Phase: {result.get('phase', 'N/A')} ({result.get('coverage_pct', 0):.1f}% coverage)")
        consensus = result.get("consensus")
        if consensus is not None:
            mv = result.get("margaret_verdict", "?")
            jv = result.get("jennifer_verdict", "?")
            tag = "CONSENSUS" if consensus else "DISAGREEMENT"
            print(f"Verdicts: Margaret={mv} Jennifer={jv} [{tag}]")
            if not consensus and result.get("disagreement_reason"):
                print(f"  Reason: {result['disagreement_reason']}")
        print(f"Margaret says: {result.get('margaret_says', '')}")
        print(f"Jennifer says: {result.get('jennifer_says', '')}")
        if result.get("red_flags"):
            print(f"Red flags: {', '.join(result['red_flags'])}")
        if result.get("adjustments"):
            print(f"Adjustments: {len(result['adjustments'])}")
            for adj in result["adjustments"]:
                print(f"  - [{adj['type']}] {adj['reason']}")
        diag = result.get("diagnosis", {})
        if diag.get("failure_count", 0) > 0:
            print(f"\nFailure diagnosis ({diag['failure_count']} failures):")
            print(f"  Dominant type: {diag.get('dominant_failure_type', 'unknown')}")
            for sector, count in sorted(diag.get("sector_breakdown", {}).items()):
                print(f"  - {sector}: {count} failures")
            if diag.get("research_queries"):
                print(f"  Research queries: {len(diag['research_queries'])}")
                for q in diag["research_queries"]:
                    print(f"    - {q}")
        dogpile = result.get("dogpile_results", [])
        if dogpile:
            print(f"\nDogpile research ({len(dogpile)} queries):")
            for dr in dogpile:
                print(f"  Query: {dr['query']}")
                for r in dr.get("results", [])[:2]:
                    if isinstance(r, dict):
                        print(f"    - {r.get('title', r.get('url', str(r)[:80]))}")


if __name__ == "__main__":
    main()
