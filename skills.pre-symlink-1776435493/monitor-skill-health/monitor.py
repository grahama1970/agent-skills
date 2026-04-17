#!/usr/bin/env python3
"""Nightly monitor for skill quality and aspirational drift.

This is the CLI entry point. Business logic is split across:
- config.py    -- constants, paths, thresholds
- checkers.py  -- violation detectors, assess runner, risk scoring
- review.py    -- deep review orchestration for high-risk skills
- reporting.py -- summary building, persistence, rendering, memory

Inputs:
- CLI options selecting a skill subset and output behavior.
- Existing skills under `.pi/skills/*/SKILL.md`.
- Structured output from composed skills (`assess`, `memory`, `scheduler`).

Outputs:
- Per-skill findings (`latest_results.jsonl`).
- Aggregate summary (`latest_summary.json`) for longitudinal tracking.
- Optional memory records for high-value run summaries.
- Task-monitor style state file for live progress visibility.

Failure modes:
- Downstream skill commands may fail (assess/memory/scheduler unavailable).
- Individual skill scans may partially fail; monitor continues and marks errors.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from typing import Any

import typer
from loguru import logger
from rich.panel import Panel
from rich.table import Table

# Re-export public API so that external callers importing from monitor still work.
from checkers import (  # noqa: F401 -- re-exports
    AuditResult,
    audit_skill,
    collect_source_files,
    discover_skills,
    is_high_risk,
    kde_violations,
    normalize_assess_gaps,
    python_violations,
    rank_high_risk,
    react_violations,
    risk_score,
    rule_packs_for,
    run_assess,
    safe_read_lines,
    skills_violations,
    status_for,
    storage_policy_violations,
)
from config import (
    HISTORY_FILE,
    LATEST_RESULTS_FILE,
    LATEST_SUMMARY_FILE,
    MAX_DEEP_REVIEW_DEFAULT,
    RUNS_DIR,
    SCHEDULER_RUN,
    SKILLS_ROOT,
    STATE_DIR,
    THIS_SKILL_DIR,
    app,
    console,
)
from reporting import (  # noqa: F401 -- re-exports
    as_dict,
    build_summary,
    now_utc,
    persist_results,
    push_summary_to_memory,
    render_table,
    update_task_state,
)
from review import run_high_risk_review  # noqa: F401 -- re-export


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------


@app.command()
def audit(
    skill: str = typer.Option("", help="Run only one skill by exact directory name"),
    limit: int = typer.Option(0, min=0, help="Limit number of skills for dry runs"),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON"),
    no_memory: bool = typer.Option(False, "--no-memory", help="Skip memory.learn summary write"),
    deep_review: bool = typer.Option(
        True,
        "--deep-review/--no-deep-review",
        help="Run deep review-code checks for high-risk skills",
    ),
    review_provider: str = typer.Option("openai", "--review-provider", help="review-code provider"),
    review_model: str = typer.Option("gpt-5.2-codex", "--review-model", help="review-code model"),
    review_rounds: int = typer.Option(2, "--review-rounds", min=1, help="review-code rounds"),
    review_reasoning: str = typer.Option("high", "--review-reasoning", help="OpenAI reasoning effort"),
    deep_review_max: int = typer.Option(
        MAX_DEEP_REVIEW_DEFAULT,
        "--deep-review-max",
        min=0,
        help="Max high-risk skills to deep-review (0 means all high-risk skills)",
    ),
) -> None:
    """Run audit over registered skills and write aggregate reports."""
    start = now_utc()
    run_id = f"msh-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    skills = discover_skills()
    if skill:
        skills = [entry for entry in skills if entry.name == skill]
    if limit > 0:
        skills = skills[:limit]

    if not skills:
        raise typer.BadParameter("No matching skills found")

    logger.info("Auditing {} skills", len(skills))
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    results: list[AuditResult] = []
    stats = {"healthy": 0, "warning": 0, "critical": 0}
    update_task_state(current_item="starting", completed=0, total=len(skills), status="running", stats=stats)

    for idx, skill_dir in enumerate(skills, start=1):
        logger.info("[{}/{}] {}", idx, len(skills), skill_dir.name)
        result = audit_skill(skill_dir)
        results.append(result)
        stats[result.status] = stats.get(result.status, 0) + 1
        update_task_state(
            current_item=skill_dir.name,
            completed=idx,
            total=len(skills),
            status="running",
            stats=stats,
        )

    if deep_review:
        ranked_high_risk_list = rank_high_risk(results)
        selected = ranked_high_risk_list if deep_review_max == 0 else ranked_high_risk_list[:deep_review_max]
        deferred = ranked_high_risk_list[len(selected):]
        selected_by_skill = {result.skill: rs for rs, result in selected}
        deferred_by_skill = {result.skill: rs for rs, result in deferred}

        logger.info(
            "Running deep review for {} high-risk skills ({} candidates total)",
            len(selected),
            len(ranked_high_risk_list),
        )
        if deferred:
            logger.info(
                "Deferred {} high-risk skills due to --deep-review-max={}",
                len(deferred),
                deep_review_max,
            )

        for result in results:
            if result.skill in deferred_by_skill:
                result.deep_review = {
                    "status": "skipped",
                    "reason": f"deferred by deep-review-max={deep_review_max}",
                    "risk_score": deferred_by_skill[result.skill],
                }
            elif result.skill not in selected_by_skill:
                result.deep_review = {"status": "skipped", "reason": "not high-risk", "risk_score": risk_score(result)}

        for idx, (rs, result) in enumerate(selected, start=1):
            update_task_state(
                current_item=f"deep-review:{result.skill}",
                completed=len(skills),
                total=len(skills),
                status="running",
                stats=stats,
            )
            logger.info(
                "[deep {}/{}] {} provider={} model={}",
                idx,
                len(selected),
                result.skill,
                review_provider,
                review_model,
            )
            result.deep_review = run_high_risk_review(
                run_dir=run_dir,
                result=result,
                provider=review_provider,
                model=review_model,
                rounds=review_rounds,
                reasoning=review_reasoning,
            )
            result.deep_review["risk_score"] = rs
    else:
        for result in results:
            result.deep_review = {"status": "skipped", "reason": "disabled"}

    summary = build_summary(results, run_id=run_id, started_at=start)
    persist_results(results, summary)
    push_summary_to_memory(summary, no_memory=no_memory)

    # Post-hook: full skill registry refresh in /memory after nightly audit
    if not no_memory:
        try:
            import subprocess as _sp
            _sp.run(
                ["memory-agent", "ingest-skills", str(SKILLS_ROOT)],
                check=False, timeout=300, capture_output=True,
            )
        except Exception:
            pass  # Best-effort — don't block nightly on memory failures

    update_task_state(
        current_item="complete",
        completed=len(skills),
        total=len(skills),
        status="completed",
        stats=stats,
    )

    if json_output:
        payload = {
            "summary": summary,
            "results": [as_dict(result) for result in results],
            "state_dir": str(STATE_DIR),
        }
        typer.echo(json.dumps(payload, indent=2))
    else:
        render_table(results, summary)
        console.print(
            f"Aggregate summary written: {LATEST_SUMMARY_FILE}\n"
            f"Per-skill results written: {LATEST_RESULTS_FILE}"
        )


@app.command()
def status(json_output: bool = typer.Option(False, "--json", help="Print JSON summary")) -> None:
    """Show latest aggregate summary."""
    if not LATEST_SUMMARY_FILE.exists():
        raise typer.BadParameter("No summary exists yet. Run audit first.")

    summary = json.loads(LATEST_SUMMARY_FILE.read_text(encoding="utf-8"))
    if json_output:
        typer.echo(json.dumps(summary, indent=2))
        return

    color = {"healthy": "green", "warning": "yellow", "critical": "red"}.get(
        summary.get("overall_status", "healthy"),
        "white",
    )
    console.print(
        Panel(
            f"[{color} bold]{summary.get('overall_status', 'unknown').upper()}[/{color} bold]"
            f"\nrun: {summary.get('run_id')}"
            f"\nskills: {summary.get('total_skills')}"
            f"\nstatus counts: {summary.get('status_counts')}"
            f"\nseverity counts: {summary.get('severity_counts')}",
            title="Monitor Skill Health Status",
            subtitle=summary.get("finished_at", ""),
        )
    )


@app.command()
def history(
    limit: int = typer.Option(20, min=1, help="Number of history entries to print"),
    json_output: bool = typer.Option(False, "--json", help="Print as JSON array"),
) -> None:
    """Show run history for trend tracking."""
    if not HISTORY_FILE.exists():
        typer.echo("No history yet")
        return

    lines = [line for line in HISTORY_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    recent = lines[-limit:]
    entries = [json.loads(line) for line in recent]

    if json_output:
        typer.echo(json.dumps(entries, indent=2))
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Timestamp", min_width=24)
    table.add_column("Run ID", min_width=20)
    table.add_column("Status", width=10)
    table.add_column("Skills", justify="right", width=8)

    for entry in entries:
        entry_status = entry.get("overall_status", "unknown")
        style = {"healthy": "green", "warning": "yellow", "critical": "red bold"}.get(entry_status, "white")
        table.add_row(
            entry.get("timestamp", ""),
            entry.get("run_id", ""),
            f"[{style}]{entry_status}[/{style}]",
            str(entry.get("total_skills", 0)),
        )

    console.print(table)


@app.command()
def register(
    cron: str = typer.Option("0 2 * * *", help="Cron expression for nightly schedule"),
    job_name: str = typer.Option("monitor-skill-health-nightly", help="Scheduler job name"),
) -> None:
    """Register nightly monitor job in scheduler."""
    if not SCHEDULER_RUN.exists():
        raise typer.BadParameter(f"scheduler skill not found at {SCHEDULER_RUN}")

    command = f"{THIS_SKILL_DIR}/run.sh audit --json > {STATE_DIR}/last_run.json"
    cmd = [
        str(SCHEDULER_RUN),
        "register",
        "--name",
        job_name,
        "--cron",
        cron,
        "--command",
        command,
        "--workdir",
        str(SKILLS_ROOT.parents[1]),
        "--description",
        "Nightly best-practice + aspirational monitoring for skills",
    ]

    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=60, env=env)
    if proc.returncode != 0:
        raise typer.BadParameter(f"scheduler register failed: {proc.stderr.strip()}")

    typer.echo(f"Registered {job_name} with cron '{cron}'")


if __name__ == "__main__":
    app()
