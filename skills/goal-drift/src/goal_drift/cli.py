"""goal-drift CLI (Typer, per best-practices-skills — never argparse/click)."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Optional

import typer

from goal_drift.contracts import AuditContract, SeamViolation, enforce
from goal_drift.evidence import commit_references_ticket, gather_commits, gather_tickets
from goal_drift.core import (
    Action,
    Criterion,
    GoalRecord,
    GoalRegistrationError,
    GoalSource,
    RunVerdict,
    audit,
    git_actions,
    goal_from_dict,
    goal_to_dict,
)

app = typer.Typer(add_completion=False, help="Read-only goal-drift auditor.")

REGISTRY = Path.home() / ".local/state/agent-skills/goal-drift/goals"


def _path(project: str) -> Path:
    return REGISTRY / f"{project}.json"


def _since_iso(since: str) -> str:
    """Best-effort ISO floor for ticket filtering. Relative strings widen the window."""
    import re as _re
    from datetime import timedelta
    m = _re.match(r"^\s*(\d+)\s*(h|hour|hours|d|day|days)\b", since)
    if m:
        n = int(m.group(1))
        delta = timedelta(hours=n) if m.group(2).startswith("h") else timedelta(days=n)
        return (datetime.now(UTC) - delta).isoformat()
    return (datetime.now(UTC) - timedelta(days=1)).isoformat()


def _repo_slug(repo_path: Path) -> str:
    """owner/name from the git remote, or '' when there is none. Read-only."""
    import subprocess as _sp
    try:
        out = _sp.run(["git", "-C", str(repo_path), "remote", "get-url", "origin"],
                      capture_output=True, text=True, timeout=20, check=False).stdout.strip()
    except (_sp.SubprocessError, OSError):
        return ""
    m = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?$", out)
    return m.group(1) if m else ""


@app.command()
def register(
    project: str = typer.Option(..., "--project"),
    goal_file: Path = typer.Option(..., "--goal-file", help="File containing the HUMAN's own words"),
    criteria_file: Optional[Path] = typer.Option(None, "--criteria-file"),
    repo: list[str] = typer.Option([], "--repo", help="Repo path to inspect (repeatable)"),
    source: str = typer.Option("human_prompt", "--source"),
) -> None:
    """Register an immutable goal. agent_inferred sources are refused."""
    crits = json.loads(criteria_file.read_text()) if criteria_file else []
    rec = GoalRecord(
        project=project,
        goal_text=goal_file.read_text().strip(),
        source=GoalSource(source),
        criteria=tuple(
            Criterion(
                key=c["key"], text=c.get("text", c["key"]),
                artifact_globs=tuple(c.get("artifact_globs", ())),
                keywords=tuple(c.get("keywords", ())),
                min_instances=int(c.get("min_instances", 1)),
            ) for c in crits
        ),
        repos=tuple(repo),
        registered_at=datetime.now(UTC).isoformat(),
    )
    try:
        rec.validate()
    except GoalRegistrationError as exc:
        typer.echo(json.dumps({"status": "REFUSED", "reason": str(exc)}, indent=2), err=True)
        raise typer.Exit(2) from exc
    REGISTRY.mkdir(parents=True, exist_ok=True)
    _path(project).write_text(json.dumps(goal_to_dict(rec), indent=2) + "\n")
    typer.echo(json.dumps({"status": "REGISTERED", "project": project,
                           "criteria": len(rec.criteria), "path": str(_path(project))}, indent=2))


@app.command()
def goal(project: str = typer.Option(..., "--project")) -> None:
    """Read a registered goal back. Verbatim, never paraphrased."""
    p = _path(project)
    if not p.exists():
        typer.echo(json.dumps({"status": "NOT_ESTABLISHED", "project": project,
                               "reason": "no immutable goal registered"}, indent=2))
        raise typer.Exit(1)
    typer.echo(p.read_text())


@app.command()
def check(
    project: str = typer.Option(..., "--project"),
    since: str = typer.Option("24h", "--since"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Audit actions against the goal. Exits 1 on DRIFTED so a cron notices."""
    p = _path(project)
    rec = goal_from_dict(json.loads(p.read_text())) if p.exists() else None
    actions: list = []
    tickets: list = []
    sources_ok: dict[str, bool] = {}
    since_iso = _since_iso(since)

    if rec:
        for r in rec.repos:
            repo_path = Path(r).expanduser()
            # 1. Tickets: declared intent, the authoritative source.
            slug = _repo_slug(repo_path)
            if slug:
                got, ok = gather_tickets(slug, since_iso)
                tickets.extend(got)
                sources_ok[f"tickets:{slug}"] = ok
            # 3. Commits: secondary. A commit citing no ticket is itself a signal.
            commits, ok = gather_commits(repo_path, since)
            sources_ok[f"commits:{repo_path.name}"] = ok
            for sha, subject, paths in commits:
                linked = commit_references_ticket(subject, tickets)
                actions.append(Action("commit", sha, subject, paths,
                                      ticket=linked.number if linked else None))

    result = audit(rec, actions, since, project=project, tickets=tickets,
                   sources_ok=sources_ok)
    payload = result.to_dict()
    try:
        enforce(AuditContract(payload))       # producer-side seam validation
    except SeamViolation as exc:
        typer.echo(json.dumps({"status": "SEAM_VIOLATION", "reason": str(exc)}, indent=2), err=True)
        raise typer.Exit(3) from exc

    typer.echo(json.dumps(payload, indent=2) if json_out else result.render())
    if result.run_verdict is not RunVerdict.ON_GOAL:
        raise typer.Exit(1)


@app.command()
def schedule() -> None:
    """Print the nightly registration command. Deliberately does not self-install."""
    typer.echo('/scheduler add goal-drift --cron "0 6 * * *" --budget 5')
    typer.echo("# 06:00: after nightly producers finish, so it grades a completed night")


if __name__ == "__main__":
    app()
