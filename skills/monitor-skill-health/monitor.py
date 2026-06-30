#!/usr/bin/env python3
"""Nightly monitor for skill quality and aspirational drift.

This is the CLI entry point. Business logic is split across:
- config.py    -- constants, paths, thresholds
- checkers.py  -- violation detectors, assess runner, risk scoring
- review.py    -- deep review orchestration for high-risk skills
- reporting.py -- summary building, persistence, rendering, memory

Inputs:
- CLI options selecting a skill/agent subset and output behavior.
- Existing skills under `skills/*/SKILL.md` and agents under `agents/*/AGENTS.md`.
- Structured output from composed skills (`assess`, `memory`, `scheduler`).

Outputs:
- Per-target findings (`latest_results.jsonl`).
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
from pathlib import Path
from typing import Any

import typer
from loguru import logger
from rich.panel import Panel
from rich.table import Table

# Re-export public API so that external callers importing from monitor still work.
from checkers import (  # noqa: F401 -- re-exports
    AuditResult,
    audit_agent,
    audit_skill,
    audit_target,
    collect_source_files,
    discover_agents,
    discover_skills,
    discover_targets,
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
    agent_violations,
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
    TICKET_DRAFTS_DIR,
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


TICKET_RUN = THIS_SKILL_DIR.parent / "ticket" / "run.sh"


def _load_latest_results() -> list[dict[str, Any]]:
    if not LATEST_RESULTS_FILE.exists():
        raise typer.BadParameter("No latest results exist yet. Run audit first.")

    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(LATEST_RESULTS_FILE.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise typer.BadParameter(f"Invalid JSON on {LATEST_RESULTS_FILE}:{line_number}: {exc}") from exc
    return rows


def _skill_target(row: dict[str, Any]) -> str:
    explicit = str(row.get("target") or "").strip()
    if explicit:
        return explicit
    raw_path = str(row.get("path") or "").strip()
    if raw_path:
        path = Path(raw_path)
        try:
            return path.resolve().relative_to(SKILLS_ROOT.parent).as_posix()
        except ValueError:
            return raw_path
    skill = str(row.get("skill") or "unknown").strip()
    return f"skills/{skill}" if skill else "skills/unknown"


def _finding_location(finding: dict[str, Any], target: str) -> str:
    for key in ("file", "path", "location"):
        value = str(finding.get(key) or "").strip()
        if value:
            return value
    return target


def _route_for_target(target: str) -> str:
    if target.startswith("agents/") or target.endswith(".md") or "/docs/" in target:
        return "documentation_or_report"
    if target.startswith("skills/"):
        return "backend_python_or_skill_runtime"
    return "unknown"


def _ticket_title(skill: str, finding: dict[str, Any], category: str, sequence: int) -> str:
    rule = str(finding.get("rule") or finding.get("message") or category or "finding").strip()
    rule = " ".join(rule.split())
    if len(rule) > 72:
        rule = rule[:69].rstrip() + "..."
    return f"[monitor-skill-health] {skill}: {rule} ({sequence})"


def _ticket_draft_for(
    *,
    row: dict[str, Any],
    finding: dict[str, Any],
    category: str,
    sequence: int,
    agent: str,
) -> dict[str, Any]:
    skill = str(row.get("skill") or "unknown")
    target_type = str(row.get("target_type") or "skill")
    target = _skill_target(row)
    location = _finding_location(finding, target)
    severity = str(finding.get("severity") or "medium")
    rule_pack = str(finding.get("rule_pack") or "monitor-skill-health")
    rule = str(finding.get("rule") or category)
    message = str(finding.get("message") or finding.get("reason") or finding.get("feature") or "monitor finding")
    title = _ticket_title(skill, finding, category, sequence)
    proof = (
        f"skills/monitor-skill-health/run.sh audit --{target_type} {skill} "
        "--no-memory --no-deep-review --json, plus any focused test required by the changed file."
    )
    invariant = (
        f"{target} must satisfy monitor-skill-health rule {rule_pack}/{rule} "
        f"without introducing unrelated skill or agent changes."
    )
    cleanup = (
        f"{severity} {category} finding at {location}: {message}"
    )
    route = _route_for_target(target)
    return {
        "schema": "agent_skills.monitor_skill_health.ticket_draft.v1",
        "title": title,
        "type": "maintenance",
        "target": target,
        "invariant": invariant,
        "cleanup": cleanup,
        "scoped_files": location,
        "proof": proof,
        "route": route,
        "agent": agent,
        "labels": ["monitor-skill-health"],
        "source": {
            "run_id": row.get("run_id"),
            "skill": skill,
            "target_type": target_type,
            "target": target,
            "status": row.get("status"),
            "category": category,
            "finding": finding,
        },
        "tau_handoff": {
            "schema": "tau.agent_handoff.v1",
            "requested_agent": agent,
            "lease_policy": "one_ticket_at_a_time",
            "objective": f"Repair one monitor-skill-health finding for {skill}",
            "target": target,
            "proof_required": proof,
            "closure_rule": "Attach deterministic proof before ticket closure; WebGPT review alone is insufficient.",
        },
    }


def _build_ticket_drafts(
    rows: list[dict[str, Any]],
    *,
    include_aspirational: bool,
    agent: str,
    max_tickets: int,
) -> list[dict[str, Any]]:
    drafts: list[dict[str, Any]] = []
    sequence = 0
    for row in rows:
        findings: list[tuple[str, dict[str, Any]]] = []
        findings.extend(("needs_fix", item) for item in row.get("needs_fix", []) if isinstance(item, dict))
        if include_aspirational:
            findings.extend(
                ("aspirational_gap", item)
                for item in row.get("aspirational_gaps", [])
                if isinstance(item, dict)
            )
        for category, finding in findings:
            sequence += 1
            drafts.append(
                _ticket_draft_for(
                    row=row,
                    finding=finding,
                    category=category,
                    sequence=sequence,
                    agent=agent,
                )
            )
            if max_tickets and len(drafts) >= max_tickets:
                return drafts
    return drafts


def _ticket_command(draft: dict[str, Any], *, repo: str, apply: bool) -> list[str]:
    cmd = [
        str(TICKET_RUN),
        "maintenance",
        draft["title"],
        "--target",
        draft["target"],
        "--invariant",
        draft["invariant"],
        "--cleanup",
        draft["cleanup"],
        "--scoped-files",
        draft["scoped_files"],
        "--proof",
        draft["proof"],
        "--route",
        draft["route"],
        "--agent",
        draft["agent"],
        "--non-goals",
        "Do not bundle unrelated monitor findings or broad cleanup into this ticket.",
    ]
    for label in draft.get("labels", []):
        cmd.extend(["--label", str(label)])
    if repo:
        cmd.extend(["--repo", repo])
    if apply:
        cmd.append("--apply")
    return cmd


def _write_ticket_drafts(drafts: list[dict[str, Any]], run_id: str) -> Path:
    TICKET_DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    path = TICKET_DRAFTS_DIR / f"{run_id}.json"
    payload = {
        "schema": "agent_skills.monitor_skill_health.ticket_drafts.v1",
        "run_id": run_id,
        "created_at": now_utc(),
        "draft_count": len(drafts),
        "drafts": drafts,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


@app.command()
def audit(
    skill: str = typer.Option("", help="Run only one skill by exact directory name"),
    agent: str = typer.Option("", help="Run only one agent by exact directory name"),
    include_agents: bool = typer.Option(True, "--agents/--no-agents", help="Include agents/*/AGENTS.md targets"),
    limit: int = typer.Option(0, min=0, help="Limit number of targets for dry runs"),
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
    repo_report: bool = typer.Option(
        False,
        "--repo-report",
        help="Compatibility flag for agent-maintainer scheduled reports; audit artifacts are already persisted.",
    ),
) -> None:
    """Run audit over registered skills and agents and write aggregate reports."""
    start = now_utc()
    run_id = f"msh-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    if skill and agent:
        raise typer.BadParameter("Use either --skill or --agent, not both.")

    targets = discover_targets(include_agents=include_agents)
    if skill:
        targets = [entry for entry in targets if entry[0] == "skill" and entry[1].name == skill]
    if agent:
        targets = [entry for entry in targets if entry[0] == "agent" and entry[1].name == agent]
    if limit > 0:
        targets = targets[:limit]

    if not targets:
        raise typer.BadParameter("No matching skills or agents found")

    logger.info("Auditing {} targets", len(targets))
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    results: list[AuditResult] = []
    stats = {"healthy": 0, "warning": 0, "critical": 0}
    update_task_state(current_item="starting", completed=0, total=len(targets), status="running", stats=stats)

    for idx, (target_type, target_dir) in enumerate(targets, start=1):
        logger.info("[{}/{}] {}:{}", idx, len(targets), target_type, target_dir.name)
        result = audit_target(target_dir, target_type=target_type)
        results.append(result)
        stats[result.status] = stats.get(result.status, 0) + 1
        update_task_state(
            current_item=f"{target_type}:{target_dir.name}",
            completed=idx,
            total=len(targets),
            status="running",
            stats=stats,
        )

    if deep_review:
        ranked_high_risk_list = [
            item for item in rank_high_risk(results) if item[1].target_type == "skill"
        ]
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
                completed=len(targets),
                total=len(targets),
                status="running",
                stats=stats,
            )
            logger.info(
                "[deep {}/{}] {} provider={} model={}",
                idx,
                len(selected),
                f"{result.target_type}:{result.skill}",
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
    if repo_report:
        summary["repo_report"] = {
            "status": "persisted",
            "latest_results": str(LATEST_RESULTS_FILE),
            "latest_summary": str(LATEST_SUMMARY_FILE),
        }
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
        completed=len(targets),
        total=len(targets),
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


@app.command("tickets")
def tickets(
    include_aspirational: bool = typer.Option(
        False,
        "--include-aspirational",
        help="Also draft tickets for aspirational gaps; default is concrete violations only.",
    ),
    max_tickets: int = typer.Option(0, "--max", min=0, help="Limit number of ticket drafts, 0 means all."),
    agent: str = typer.Option("agent-skill-maintainer", "--agent", help="Requested repair agent label."),
    repo: str = typer.Option("", "--repo", "-R", help="GitHub repo for --apply, for example owner/name."),
    apply: bool = typer.Option(False, "--apply", help="Create GitHub issues instead of previewing drafts."),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON"),
) -> None:
    """Draft or create one normalized maintenance ticket per current monitor finding."""
    rows = _load_latest_results()
    run_id = str((rows[0].get("run_id") if rows else None) or f"msh-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    drafts = _build_ticket_drafts(
        rows,
        include_aspirational=include_aspirational,
        agent=agent,
        max_tickets=max_tickets,
    )
    path = _write_ticket_drafts(drafts, run_id)

    payload = {
        "schema": "agent_skills.monitor_skill_health.ticket_preview.v1",
        "run_id": run_id,
        "draft_count": len(drafts),
        "draft_file": str(path),
        "apply": apply,
        "commands": [_ticket_command(draft, repo=repo, apply=apply) for draft in drafts],
    }

    if apply:
        if not TICKET_RUN.exists():
            raise typer.BadParameter(f"ticket skill runner not found: {TICKET_RUN}")
        for draft in drafts:
            subprocess.run(_ticket_command(draft, repo=repo, apply=True), check=True)

    if json_output:
        typer.echo(json.dumps(payload, indent=2))
        return

    console.print(
        Panel(
            f"Draft file: {path}\n"
            f"Tickets: {len(drafts)}\n"
            f"Mode: {'apply' if apply else 'preview'}",
            title="Monitor Skill Health Ticket Handoff",
        )
    )
    for draft in drafts[:25]:
        typer.echo(f"- {draft['title']} -> {draft['target']}")
    if len(drafts) > 25:
        typer.echo(f"... {len(drafts) - 25} more")


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
