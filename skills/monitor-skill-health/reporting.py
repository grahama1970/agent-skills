"""Reporting, persistence, and rendering for monitor-skill-health.

Handles task-state updates, summary building, result persistence to disk,
memory integration, and Rich table output.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger
from rich.panel import Panel
from rich.table import Table

from checkers import AuditResult, rank_high_risk, risk_score
from config import (
    HISTORY_FILE,
    LATEST_RESULTS_FILE,
    LATEST_SUMMARY_FILE,
    MEMORY_RUN,
    RUNS_DIR,
    SEVERITY_ORDER,
    STATE_DIR,
    TASK_STATE_FILE,
    console,
)


def now_utc() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Task state (live progress visibility)
# ---------------------------------------------------------------------------


def update_task_state(
    current_item: str,
    completed: int,
    total: int,
    status: str,
    stats: dict[str, int],
) -> None:
    """Write a task-monitor compatible state file for live progress."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "completed": completed,
        "total": total,
        "description": "monitor-skill-health audit",
        "current_item": current_item,
        "stats": stats,
        "progress_pct": round((completed / total * 100), 1) if total > 0 else 0,
        "status": status,
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    tmp = TASK_STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, TASK_STATE_FILE)


# ---------------------------------------------------------------------------
# Summary building
# ---------------------------------------------------------------------------


def build_summary(results: list[AuditResult], run_id: str, started_at: str) -> dict[str, Any]:
    """Aggregate per-target results into a run summary."""
    status_counts = {"healthy": 0, "warning": 0, "critical": 0}
    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    pack_counts: dict[str, int] = {}
    top_issues: list[dict[str, Any]] = []
    deep_review_counts = {"requested": 0, "completed": 0, "failed": 0, "skipped": 0}

    for result in results:
        status_counts[result.status] = status_counts.get(result.status, 0) + 1
        deep = result.deep_review or {}
        deep_status = str(deep.get("status", "skipped"))
        if deep_status != "skipped":
            deep_review_counts["requested"] += 1
        if deep_status in deep_review_counts:
            deep_review_counts[deep_status] += 1
        else:
            deep_review_counts["failed"] += 1

        for issue in result.needs_fix + result.aspirational_gaps:
            sev = str(issue.get("severity", "low"))
            if sev not in severity_counts:
                severity_counts[sev] = 0
            severity_counts[sev] += 1

            pack = str(issue.get("rule_pack", "unknown"))
            pack_counts[pack] = pack_counts.get(pack, 0) + 1

            top_issues.append(
                {
                    "skill": result.skill,
                    "target_type": result.target_type,
                    "target": result.target or f"{result.target_type}s/{result.skill}",
                    "severity": sev,
                    "rule": issue.get("rule", "unknown"),
                    "file": issue.get("file", "unknown"),
                    "message": issue.get("message", ""),
                }
            )

    top_issues.sort(key=lambda x: SEVERITY_ORDER.get(str(x["severity"]), 0), reverse=True)

    overall_status = "healthy"
    if status_counts.get("critical", 0) > 0:
        overall_status = "critical"
    elif status_counts.get("warning", 0) > 0:
        overall_status = "warning"

    ranked_high_risk = rank_high_risk(results)

    # Build figure_data for visualization
    targets_with_violations = sum(1 for result in results if result.needs_fix or result.aspirational_gaps)
    targets_passing = len(results) - targets_with_violations
    target_type_counts: dict[str, int] = {}
    for result in results:
        target_type_counts[result.target_type] = target_type_counts.get(result.target_type, 0) + 1
    total_violations = sum(len(result.needs_fix) for result in results)

    figure_data = {
        "bar": {
            "metrics": {
                "total_skills_scanned": len(results),
                "total_targets_scanned": len(results),
                "skills_passing_all_checks": targets_passing,
                "targets_passing_all_checks": targets_passing,
                "skills_with_violations": targets_with_violations,
                "targets_with_violations": targets_with_violations,
                "total_violations_found": total_violations,
                "critical_violations": severity_counts.get("critical", 0),
                "high_violations": severity_counts.get("high", 0),
                "medium_violations": severity_counts.get("medium", 0),
                "low_violations": severity_counts.get("low", 0),
            }
        }
    }

    return {
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": now_utc(),
        "total_skills": len(results),
        "total_targets": len(results),
        "target_type_counts": target_type_counts,
        "overall_status": overall_status,
        "status_counts": status_counts,
        "severity_counts": severity_counts,
        "rule_pack_counts": pack_counts,
        "top_issues": top_issues[:25],
        "high_risk_queue": [
            {
                "skill": result.skill,
                "target_type": result.target_type,
                "target": result.target or f"{result.target_type}s/{result.skill}",
                "risk_score": rs,
            } for rs, result in ranked_high_risk[:25]
        ],
        "deep_review_counts": deep_review_counts,
        "figure_data": figure_data,
    }


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def persist_results(results: list[AuditResult], summary: dict[str, Any]) -> None:
    """Write per-skill JSONL, run summary, and append to history."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    run_dir = RUNS_DIR / summary["run_id"]
    run_dir.mkdir(parents=True, exist_ok=True)

    result_lines = []
    for result in results:
        payload = {
            "run_id": summary["run_id"],
            "timestamp": summary["finished_at"],
            "skill": result.skill,
            "target_type": result.target_type,
            "target": result.target or f"{result.target_type}s/{result.skill}",
            "path": result.path,
            "status": result.status,
            "rule_packs": result.rule_packs,
            "works_well": result.works_well,
            "needs_fix": result.needs_fix,
            "aspirational_gaps": result.aspirational_gaps,
            "next_steps": result.next_steps,
            "errors": result.errors,
            "deep_review": result.deep_review or {"status": "skipped", "reason": "not requested"},
        }
        result_lines.append(json.dumps(payload, ensure_ascii=False))

    results_blob = "\n".join(result_lines) + ("\n" if result_lines else "")

    (run_dir / "results.jsonl").write_text(results_blob, encoding="utf-8")
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    LATEST_RESULTS_FILE.write_text(results_blob, encoding="utf-8")
    LATEST_SUMMARY_FILE.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # Save full report to user config directory
    report_file = Path.home() / ".pi" / "monitor-skill-health" / "report.json"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    full_payload = {
        "summary": summary,
        "results": [as_dict(result) for result in results],
    }
    report_file.write_text(json.dumps(full_payload, indent=2), encoding="utf-8")

    history_entry = {
        "run_id": summary["run_id"],
        "timestamp": summary["finished_at"],
        "overall_status": summary["overall_status"],
        "total_skills": summary["total_skills"],
        "total_targets": summary.get("total_targets", summary["total_skills"]),
        "target_type_counts": summary.get("target_type_counts", {}),
        "status_counts": summary["status_counts"],
        "severity_counts": summary["severity_counts"],
    }
    with HISTORY_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(history_entry, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Memory integration
# ---------------------------------------------------------------------------


def push_summary_to_memory(summary: dict[str, Any], no_memory: bool) -> None:
    """Optionally record the run summary in the memory skill."""
    if no_memory:
        logger.info("Skipping memory write (--no-memory)")
        return

    if not MEMORY_RUN.exists():
        logger.warning("memory skill not found at {}", MEMORY_RUN)
        return

    top = summary.get("top_issues", [])
    issue_preview = "; ".join(
        f"{item.get('skill')}:{item.get('rule')}@{item.get('file')}" for item in top[:5]
    ) or "no major issues"

    problem = (
        f"monitor-skill-health run {summary['run_id']} evaluated "
        f"{summary.get('total_targets', summary['total_skills'])} skills/agents with overall status "
        f"{summary['overall_status']}."
    )
    solution = (
        f"Status counts={summary['status_counts']}, "
        f"severity counts={summary['severity_counts']}, top issues={issue_preview}."
    )

    cmd = [
        str(MEMORY_RUN),
        "learn",
        "--problem",
        problem,
        "--solution",
        solution,
        "--scope",
        "operational",
        "--tag",
        "skill_audit",
        "--tag",
        "monitor-skill-health",
        "--tag",
        summary["overall_status"],
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=120)
    if proc.returncode != 0:
        logger.warning("memory learn failed: {}", proc.stderr.strip()[:200])


# ---------------------------------------------------------------------------
# Rich rendering
# ---------------------------------------------------------------------------


def render_table(results: list[AuditResult], summary: dict[str, Any]) -> None:
    """Print a Rich table summarising audit results to stderr."""
    color = {"healthy": "green", "warning": "yellow", "critical": "red"}.get(
        summary["overall_status"], "white"
    )
    console.print(
        Panel(
            f"[{color} bold]{summary['overall_status'].upper()}[/{color} bold]  "
            f"targets={summary.get('total_targets', summary['total_skills'])}  "
            f"status={summary['status_counts']}  "
            f"severity={summary['severity_counts']}",
            title="Monitor Skill Health",
            subtitle=summary["run_id"],
        )
    )

    table = Table(show_header=True, header_style="bold")
    table.add_column("Target", min_width=26)
    table.add_column("Status", width=10)
    table.add_column("Issues", justify="right", width=8)
    table.add_column("Aspirational", justify="right", width=12)
    table.add_column("Top Next Step")

    for result in results:
        style = {"healthy": "green", "warning": "yellow", "critical": "red bold"}.get(
            result.status,
            "white",
        )
        table.add_row(
            result.target or f"{result.target_type}s/{result.skill}",
            f"[{style}]{result.status}[/{style}]",
            str(len(result.needs_fix)),
            str(len(result.aspirational_gaps)),
            result.next_steps[0] if result.next_steps else "",
        )

    console.print(table)


def as_dict(result: AuditResult) -> dict[str, Any]:
    """Serialise an AuditResult to a plain dictionary."""
    return {
        "skill": result.skill,
        "target_type": result.target_type,
        "target": result.target or f"{result.target_type}s/{result.skill}",
        "path": result.path,
        "status": result.status,
        "rule_packs": result.rule_packs,
        "works_well": result.works_well,
        "needs_fix": result.needs_fix,
        "aspirational_gaps": result.aspirational_gaps,
        "next_steps": result.next_steps,
        "errors": result.errors,
        "deep_review": result.deep_review or {"status": "skipped"},
    }
