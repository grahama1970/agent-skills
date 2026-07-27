"""Ticket CLI.

Builds best-practices-github-ticket compliant issue bodies, delegates guarded
issue lifecycle operations to gh-ticket-tools.sh, and exposes explicit GitHub
Actions helpers. Failure modes are fail-closed: mutating GitHub operations
require explicit flags and proof files where applicable.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import typer
from loguru import logger


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
REPO_ROOT = SKILL_DIR.parent.parent
GH_HELPER = REPO_ROOT / "skills" / "best-practices-github-ticket" / "scripts" / "gh-ticket-tools.sh"

VALID_TYPES = {"bug", "feature", "optimization", "maintenance", "question", "triage"}
VALID_ROUTES = {
    "unknown",
    "backend_python_or_skill_runtime",
    "design_or_ux",
    "frontend_code",
    "rust_or_binary",
    "ops_or_scheduler",
    "documentation_or_report",
    "security_or_compliance",
}

app = typer.Typer(help="GitHub ticket filing and lifecycle CLI.")
ci_app = typer.Typer(help="GitHub Actions helpers for ticket verification.")
app.add_typer(ci_app, name="ci")


@dataclass(frozen=True)
class TicketDraft:
    ticket_type: str
    title: str
    target: str
    body: str
    labels: list[str]
    route: str
    agent: str


def _die(message: str, code: int = 2) -> None:
    typer.echo(f"ERROR: {message}", err=True)
    raise typer.Exit(code)


def _run(cmd: list[str], *, capture: bool = False, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        check=check,
    )


def _print_command(cmd: Iterable[str]) -> None:
    typer.echo(" ".join(shlex.quote(part) for part in cmd))


def _repo_args(repo: Optional[str]) -> list[str]:
    return ["--repo", repo] if repo else []


def _helper(args: list[str], *, repo: Optional[str] = None, dry_run: bool = False) -> None:
    cmd = [str(GH_HELPER), *args, *_repo_args(repo)]
    if dry_run:
        cmd.append("--dry-run")
    _run(cmd)


#: Ticket types that always need a human decision before an agent may act.
HUMAN_ONLY_TYPES = {"question", "triage"}

#: Label the project-watchdog router selects on. A ticket that does not carry it
#: is invisible to automated dispatch.
#:
#: Before 2026-07-27 nothing here emitted it: /ticket wrote type:* and route:*
#: while the watchdog routed on agent-work, so ordinary tickets were never
#: picked up and the cron logged 41,607 consecutive no-work ticks over roughly a
#: month. Stamping it at file time is what joins the two halves.
AGENT_WORK_LABEL = "agent-work"



def _is_agent_routable(ticket_type: str, route: str) -> bool:
    """Return whether a ticket is safe to hand to an automated repair loop.

    Requires a concrete maintainer route and a type that is actually actionable.
    Questions and triage tickets are human-first by definition, and a ticket with
    an unknown route has nowhere to be sent.
    """
    if ticket_type in HUMAN_ONLY_TYPES:
        return False
    return bool(route) and route != "unknown"


def _labels(ticket_type: str, target: str, route: str, agent: str, extra: list[str] | None = None) -> list[str]:
    labels = [f"type:{ticket_type}"]
    if _is_agent_routable(ticket_type, route):
        labels.append(AGENT_WORK_LABEL)
    if target.startswith("skills/"):
        if ticket_type == "bug":
            labels.append("skill-bug")
        elif ticket_type == "maintenance":
            labels.append("skill-maintenance")
        elif ticket_type == "optimization":
            labels.append("skill-optimization")
    if target.startswith("agents/"):
        if ticket_type == "bug":
            labels.append("agent-bug")
        elif ticket_type == "maintenance":
            labels.append("agent-maintenance")
        elif ticket_type == "optimization":
            labels.append("agent-optimization")
    if route and route != "unknown":
        labels.append(f"route:{route}")
    if agent:
        labels.append(f"agent:{agent}")
    for label in extra or []:
        if label and label not in labels:
            labels.append(label)
    return labels


def _validate_common(ticket_type: str, target: str, proof: str, route: str) -> None:
    if ticket_type not in VALID_TYPES:
        _die(f"unknown ticket type {ticket_type!r}")
    if not target.strip():
        _die("target path is required")
    if not proof.strip() and ticket_type != "triage":
        _die("required proof is required; use triage when proof is unknown")
    if route not in VALID_ROUTES:
        _die(f"unknown route {route!r}; use unknown if unsure")


def _section(title: str, value: str) -> str:
    value = value.strip() or "Not specified."
    return f"## {title}\n\n{value}\n"


def _body(
    *,
    ticket_type: str,
    target: str,
    current_state: str,
    requested_outcome: str,
    proof: str,
    route: str,
    agent: str,
    non_goals: str,
    details: dict[str, str],
) -> str:
    lines = [
        _section("Type", ticket_type),
        _section("Target", target),
        _section("Target paths", f"- {target}"),
        _section("Current state", current_state),
        _section("Requested outcome", requested_outcome),
        _section("Required proof", proof),
        _section("Route", route),
        _section("Maintainer route", route),
        _section("Requested repair agent", agent or "Not specified."),
        _section("Non-goals", non_goals or "No unrelated refactors or scope expansion."),
    ]
    if details:
        detail_text = "\n".join(f"- **{key}:** {value.strip() or 'Not specified.'}" for key, value in details.items())
        lines.append(_section("Ticket type details", detail_text))
    lines.append(
        "<!-- ticket-skill\n"
        f"type: {ticket_type}\n"
        f"target: {target}\n"
        f"route: {route}\n"
        f"agent: {agent or 'unspecified'}\n"
        "-->\n"
    )
    lines.append(
        "This ticket must be resolved under `best-practices-github-ticket`. "
        "Closure requires deterministic proof; WebGPT review or CI green alone is not closure proof.\n"
    )
    return "\n".join(lines)


def _draft(
    *,
    ticket_type: str,
    title: str,
    target: str,
    current_state: str,
    requested_outcome: str,
    proof: str,
    route: str,
    agent: str,
    non_goals: str = "",
    details: dict[str, str] | None = None,
    extra_labels: list[str] | None = None,
) -> TicketDraft:
    _validate_common(ticket_type, target, proof, route)
    body = _body(
        ticket_type=ticket_type,
        target=target,
        current_state=current_state,
        requested_outcome=requested_outcome,
        proof=proof,
        route=route,
        agent=agent,
        non_goals=non_goals,
        details=details or {},
    )
    return TicketDraft(
        ticket_type=ticket_type,
        title=title,
        target=target,
        body=body,
        labels=_labels(ticket_type, target, route, agent, extra_labels),
        route=route,
        agent=agent,
    )


def _emit_draft(draft: TicketDraft, *, as_json: bool = False) -> None:
    if as_json:
        typer.echo(json.dumps({
            "title": draft.title,
            "type": draft.ticket_type,
            "target": draft.target,
            "route": draft.route,
            "agent": draft.agent,
            "labels": draft.labels,
            "body": draft.body,
        }, indent=2))
        return
    typer.echo(f"# {draft.title}\n")
    typer.echo(draft.body)
    typer.echo("\nLabels: " + ", ".join(draft.labels))


def _create_or_preview(draft: TicketDraft, *, repo: Optional[str], apply: bool, as_json: bool) -> None:
    if not apply:
        _emit_draft(draft, as_json=as_json)
        typer.echo("\nPreview only. Re-run with --apply to create the GitHub issue.", err=True)
        return
    cmd = ["gh", "issue", "create", *_repo_args(repo), "--title", draft.title]
    for label in draft.labels:
        cmd.extend(["--label", label])
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as tmp:
        tmp.write(draft.body)
        body_path = tmp.name
    try:
        cmd.extend(["--body-file", body_path])
        _run(cmd)
    finally:
        try:
            os.unlink(body_path)
        except OSError as exc:
            logger.error("failed to remove temporary ticket body {}: {}", body_path, exc)


@app.command()
def bug(
    title: str,
    target: str = typer.Option(..., "--target"),
    observed: str = typer.Option(..., "--observed"),
    expected: str = typer.Option(..., "--expected"),
    repro: str = typer.Option(..., "--repro"),
    proof: str = typer.Option(..., "--proof"),
    route: str = typer.Option("unknown", "--route"),
    agent: str = typer.Option("", "--agent"),
    non_goals: str = typer.Option("", "--non-goals"),
    label: list[str] = typer.Option([], "--label"),
    repo: Optional[str] = typer.Option(None, "--repo", "-R"),
    apply: bool = typer.Option(False, "--apply"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Build or create a bug ticket."""
    draft = _draft(
        ticket_type="bug",
        title=title,
        target=target,
        current_state=observed,
        requested_outcome=expected,
        proof=proof,
        route=route,
        agent=agent,
        non_goals=non_goals,
        details={
            "Observed failure": observed,
            "Expected behavior": expected,
            "Reproduction or artifact": repro,
        },
        extra_labels=label,
    )
    _create_or_preview(draft, repo=repo, apply=apply, as_json=as_json)


@app.command()
def feature(
    title: str,
    target: str = typer.Option(..., "--target"),
    limitation: str = typer.Option(..., "--limitation"),
    capability: str = typer.Option(..., "--capability"),
    workflow: str = typer.Option(..., "--workflow"),
    acceptance: str = typer.Option(..., "--acceptance"),
    proof: str = typer.Option(..., "--proof"),
    route: str = typer.Option("unknown", "--route"),
    agent: str = typer.Option("", "--agent"),
    non_goals: str = typer.Option("", "--non-goals"),
    label: list[str] = typer.Option([], "--label"),
    repo: Optional[str] = typer.Option(None, "--repo", "-R"),
    apply: bool = typer.Option(False, "--apply"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Build or create a feature ticket."""
    draft = _draft(
        ticket_type="feature",
        title=title,
        target=target,
        current_state=limitation,
        requested_outcome=capability,
        proof=proof,
        route=route,
        agent=agent,
        non_goals=non_goals,
        details={
            "Current limitation": limitation,
            "Proposed capability": capability,
            "User workflow unlocked": workflow,
            "Acceptance criteria": acceptance,
        },
        extra_labels=label,
    )
    _create_or_preview(draft, repo=repo, apply=apply, as_json=as_json)


@app.command()
def optimization(
    title: str,
    target: str = typer.Option(..., "--target"),
    friction: str = typer.Option(..., "--friction"),
    improvement: str = typer.Option(..., "--improvement"),
    measurable_target: str = typer.Option(..., "--measurable-target"),
    proof: str = typer.Option(..., "--proof"),
    route: str = typer.Option("unknown", "--route"),
    agent: str = typer.Option("", "--agent"),
    non_goals: str = typer.Option("", "--non-goals"),
    repo: Optional[str] = typer.Option(None, "--repo", "-R"),
    apply: bool = typer.Option(False, "--apply"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Build or create an optimization ticket."""
    draft = _draft(
        ticket_type="optimization",
        title=title,
        target=target,
        current_state=friction,
        requested_outcome=improvement,
        proof=proof,
        route=route,
        agent=agent,
        non_goals=non_goals,
        details={
            "Current cost or friction": friction,
            "Proposed improvement": improvement,
            "Measurable target": measurable_target,
        },
    )
    _create_or_preview(draft, repo=repo, apply=apply, as_json=as_json)


@app.command()
def maintenance(
    title: str,
    target: str = typer.Option(..., "--target"),
    invariant: str = typer.Option(..., "--invariant"),
    cleanup: str = typer.Option(..., "--cleanup"),
    scoped_files: str = typer.Option(..., "--scoped-files"),
    proof: str = typer.Option(..., "--proof"),
    route: str = typer.Option("unknown", "--route"),
    agent: str = typer.Option("", "--agent"),
    non_goals: str = typer.Option("", "--non-goals"),
    label: list[str] = typer.Option([], "--label"),
    repo: Optional[str] = typer.Option(None, "--repo", "-R"),
    apply: bool = typer.Option(False, "--apply"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Build or create a maintenance ticket."""
    draft = _draft(
        ticket_type="maintenance",
        title=title,
        target=target,
        current_state=cleanup,
        requested_outcome=f"Preserve invariant: {invariant}",
        proof=proof,
        route=route,
        agent=agent,
        non_goals=non_goals,
        details={
            "Invariant to preserve": invariant,
            "Cleanup target": cleanup,
            "Scoped files": scoped_files,
        },
        extra_labels=label,
    )
    _create_or_preview(draft, repo=repo, apply=apply, as_json=as_json)


@app.command()
def question(
    title: str,
    target: str = typer.Option(..., "--target"),
    question_text: str = typer.Option(..., "--question"),
    source_scope: str = typer.Option(..., "--source-scope"),
    answer_format: str = typer.Option(..., "--answer-format"),
    proof: str = typer.Option("Sourced answer or documented reason it is not established.", "--proof"),
    route: str = typer.Option("documentation_or_report", "--route"),
    agent: str = typer.Option("reporter", "--agent"),
    non_goals: str = typer.Option("", "--non-goals"),
    repo: Optional[str] = typer.Option(None, "--repo", "-R"),
    apply: bool = typer.Option(False, "--apply"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Build or create a question ticket."""
    draft = _draft(
        ticket_type="question",
        title=title,
        target=target,
        current_state=question_text,
        requested_outcome=answer_format,
        proof=proof,
        route=route,
        agent=agent,
        non_goals=non_goals,
        details={
            "Concrete question": question_text,
            "Source scope": source_scope,
            "Expected answer format": answer_format,
        },
    )
    _create_or_preview(draft, repo=repo, apply=apply, as_json=as_json)


@app.command()
def triage(
    title: str,
    target: str = typer.Option(..., "--target"),
    clues: str = typer.Option(..., "--clues"),
    missing_data: str = typer.Option(..., "--missing-data"),
    route: str = typer.Option("unknown", "--route"),
    agent: str = typer.Option("", "--agent"),
    repo: Optional[str] = typer.Option(None, "--repo", "-R"),
    apply: bool = typer.Option(False, "--apply"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Build or create a triage ticket."""
    draft = _draft(
        ticket_type="triage",
        title=title,
        target=target,
        current_state=clues,
        requested_outcome="Classify ticket type, route, owner, and required proof.",
        proof="Route/type decision or needs-human with exact missing information.",
        route=route,
        agent=agent,
        details={
            "Available clues": clues,
            "Missing data": missing_data,
        },
        extra_labels=["needs-triage"],
    )
    _create_or_preview(draft, repo=repo, apply=apply, as_json=as_json)


def _fleet_items(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    items: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = re.match(r"^(?:[-*]|\d+[.)])\s+(.*)$", stripped)
        if match:
            item = match.group(1).strip()
            if item:
                items.append(item)
    if not items:
        paragraphs = [p.strip().replace("\n", " ") for p in re.split(r"\n\s*\n", text) if p.strip()]
        items.extend(paragraphs)
    return items


@app.command()
def fleet(
    file: Path,
    target: str = typer.Option(..., "--target"),
    ticket_type: str = typer.Option("feature", "--type"),
    route: str = typer.Option("unknown", "--route"),
    agent: str = typer.Option("", "--agent"),
    proof: str = typer.Option(..., "--proof"),
    non_goals: str = typer.Option("Do not bundle unrelated acceptance criteria into one ticket.", "--non-goals"),
    repo: Optional[str] = typer.Option(None, "--repo", "-R"),
    apply: bool = typer.Option(False, "--apply"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Split a change list into one ticket per independently verifiable item."""
    if ticket_type not in VALID_TYPES - {"triage"}:
        _die("fleet --type must be bug, feature, optimization, maintenance, or question")
    if not file.exists():
        _die(f"fleet file not found: {file}")
    items = _fleet_items(file)
    if not items:
        _die("fleet file did not contain bullet, numbered, or paragraph items")
    drafts = [
        _draft(
            ticket_type=ticket_type,
            title=item[:120],
            target=target,
            current_state=f"Batch request item from {file}: {item}",
            requested_outcome=item,
            proof=proof,
            route=route,
            agent=agent,
            non_goals=non_goals,
            details={"Fleet source": str(file), "Fleet item": item},
        )
        for item in items
    ]
    if as_json:
        typer.echo(json.dumps([{
            "title": d.title,
            "type": d.ticket_type,
            "target": d.target,
            "labels": d.labels,
            "body": d.body,
        } for d in drafts], indent=2))
    else:
        for index, draft in enumerate(drafts, start=1):
            typer.echo(f"\n--- Ticket {index}/{len(drafts)} ---")
            _emit_draft(draft)
    if not apply:
        typer.echo(f"\nPreview only. {len(drafts)} ticket(s) proposed. Re-run with --apply to create.", err=True)
        return
    for draft in drafts:
        _create_or_preview(draft, repo=repo, apply=True, as_json=False)


@app.command()
def lookup(
    issue: Optional[int] = typer.Option(None, "--issue"),
    next: bool = typer.Option(False, "--next"),
    label: str = typer.Option("", "--label"),
    search: str = typer.Option("", "--search"),
    limit: int = typer.Option(20, "--limit"),
    repo: Optional[str] = typer.Option(None, "--repo", "-R"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Show, search, or find the next unleased ticket."""
    if issue is not None:
        _helper(["show", str(issue)], repo=repo, dry_run=dry_run)
    elif next:
        args = ["next", "--limit", str(limit)]
        if label:
            args.extend(["--label", label])
        _helper(args, repo=repo, dry_run=dry_run)
    else:
        args = ["search", "--limit", str(limit)]
        if label:
            args.extend(["--label", label])
        if search:
            args.extend(["--search", search])
        _helper(args, repo=repo, dry_run=dry_run)


@app.command("ensure-labels")
def ensure_labels(repo: Optional[str] = typer.Option(None, "--repo", "-R"), dry_run: bool = False) -> None:
    """Ensure ticket workflow labels exist."""
    _helper(["ensure-labels"], repo=repo, dry_run=dry_run)


@app.command()
def doctor(repo: Optional[str] = typer.Option(None, "--repo", "-R")) -> None:
    """Check gh auth, issue access, and labels."""
    _helper(["doctor"], repo=repo)


@app.command()
def lease(issue: int, agent: str = typer.Option(..., "--agent"), assign_me: bool = False, repo: Optional[str] = typer.Option(None, "--repo", "-R"), dry_run: bool = False) -> None:
    """Lease exactly one issue through the guarded helper."""
    args = ["lease", str(issue), "--agent", agent]
    if assign_me:
        args.append("--assign-me")
    _helper(args, repo=repo, dry_run=dry_run)


@app.command()
def comment(issue: int, body: Path = typer.Option(..., "--body"), repo: Optional[str] = typer.Option(None, "--repo", "-R"), dry_run: bool = False) -> None:
    """Comment from a body file."""
    _helper(["comment", str(issue), "--body", str(body)], repo=repo, dry_run=dry_run)


@app.command()
def block(issue: int, reason: Path = typer.Option(..., "--reason"), release_lease: bool = typer.Option(False, "--release"), repo: Optional[str] = typer.Option(None, "--repo", "-R"), dry_run: bool = False) -> None:
    """Mark an issue blocked and optionally release the lease."""
    args = ["block", str(issue), "--reason", str(reason)]
    if release_lease:
        args.append("--release")
    _helper(args, repo=repo, dry_run=dry_run)


@app.command()
def release(issue: int, agent: str = typer.Option(..., "--agent"), reason: Path = typer.Option(..., "--reason"), repo: Optional[str] = typer.Option(None, "--repo", "-R"), dry_run: bool = False) -> None:
    """Release a maintainer-active lease."""
    _helper(["release", str(issue), "--agent", agent, "--reason", str(reason)], repo=repo, dry_run=dry_run)


@app.command()
def close(issue: int, proof: Path = typer.Option(..., "--proof"), review: Optional[Path] = typer.Option(None, "--review"), reason: str = typer.Option("completed", "--reason"), repo: Optional[str] = typer.Option(None, "--repo", "-R"), dry_run: bool = False) -> None:
    """Close an issue through proof-file gated helper."""
    args = ["close", str(issue), "--proof", str(proof), "--reason", reason]
    if review:
        args.extend(["--review", str(review)])
    _helper(args, repo=repo, dry_run=dry_run)


@app.command("close-duplicate")
def close_duplicate(issue: int, duplicate_of: int = typer.Option(..., "--duplicate-of"), proof: Path = typer.Option(..., "--proof"), review: Optional[Path] = typer.Option(None, "--review"), repo: Optional[str] = typer.Option(None, "--repo", "-R"), dry_run: bool = False) -> None:
    """Close a duplicate issue through proof-file gated helper."""
    args = ["close-duplicate", str(issue), "--duplicate-of", str(duplicate_of), "--proof", str(proof)]
    if review:
        args.extend(["--review", str(review)])
    _helper(args, repo=repo, dry_run=dry_run)


@app.command("attach-proof")
def attach_proof(issue: int, file: Path = typer.Option(..., "--file"), repo: Optional[str] = typer.Option(None, "--repo", "-R"), dry_run: bool = False) -> None:
    """Attach a proof file as an issue comment."""
    _helper(["comment", str(issue), "--body", str(file)], repo=repo, dry_run=dry_run)


@app.command()
def verify(
    issue: int,
    cmd: list[str] = typer.Option([], "--cmd", help="Deterministic command to run. Repeatable."),
    output: Optional[Path] = typer.Option(None, "--output"),
) -> None:
    """Run local proof commands and write a proof report."""
    if not cmd:
        _die("verify requires at least one --cmd")
    results = []
    failed = False
    for command in cmd:
        proc = subprocess.run(command, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        results.append({
            "cmd": command,
            "returncode": proc.returncode,
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-4000:],
        })
        if proc.returncode != 0:
            failed = True
    proof = [
        f"# Issue {issue} Verification Proof",
        "",
        "mocked: no",
        "live: no",
        "What was exercised: local deterministic commands supplied to `ticket verify`.",
        "What remains unverified: remote GitHub issue state and any live service not covered by commands.",
        "",
    ]
    for result in results:
        proof.extend([
            f"## Command: `{result['cmd']}`",
            "",
            f"Exit code: {result['returncode']}",
            "",
            "### stdout",
            "```text",
            result["stdout"].rstrip(),
            "```",
            "",
            "### stderr",
            "```text",
            result["stderr"].rstrip(),
            "```",
            "",
        ])
    text = "\n".join(proof)
    if output is None:
        output = Path(tempfile.gettempdir()) / f"issue-{issue}-proof.md"
    output.write_text(text, encoding="utf-8")
    typer.echo(str(output))
    if failed:
        raise typer.Exit(1)


@ci_app.command("status")
def ci_status(
    target: str = typer.Argument("", help="Optional branch, PR number, issue number, or run query label."),
    repo: Optional[str] = typer.Option(None, "--repo", "-R"),
    branch: str = typer.Option("", "--branch"),
    workflow: str = typer.Option("", "--workflow"),
    limit: int = typer.Option(10, "--limit"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Show GitHub Actions run status."""
    cmd = ["gh", "run", "list", *_repo_args(repo), "--limit", str(limit)]
    effective_branch = branch
    if not effective_branch and target and not target.isdigit():
        effective_branch = target
    if effective_branch:
        cmd.extend(["--branch", effective_branch])
    if workflow:
        cmd.extend(["--workflow", workflow])
    if dry_run:
        _print_command(cmd)
    else:
        _run(cmd)


@ci_app.command("rerun")
def ci_rerun(
    run_id: str,
    repo: Optional[str] = typer.Option(None, "--repo", "-R"),
    failed: bool = typer.Option(True, "--failed/--all"),
    yes: bool = typer.Option(False, "--yes"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Rerun a GitHub Actions workflow run. Requires --yes unless dry-run."""
    cmd = ["gh", "run", "rerun", run_id, *_repo_args(repo)]
    if failed:
        cmd.append("--failed")
    if dry_run:
        _print_command(cmd)
        return
    if not yes:
        _die("ci rerun requires --yes for live mutation")
    _run(cmd)


@ci_app.command("dispatch")
def ci_dispatch(
    workflow: str,
    repo: Optional[str] = typer.Option(None, "--repo", "-R"),
    ref: str = typer.Option("main", "--ref"),
    field: list[str] = typer.Option([], "--field", help="workflow_dispatch field as key=value. Repeatable."),
    apply: bool = typer.Option(False, "--apply"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Trigger a workflow_dispatch run. Requires --apply unless dry-run."""
    cmd = ["gh", "workflow", "run", workflow, *_repo_args(repo), "--ref", ref]
    for item in field:
        if "=" not in item:
            _die(f"--field must be key=value, got {item!r}")
        cmd.extend(["-f", item])
    if dry_run or not apply:
        _print_command(cmd)
        if not apply:
            typer.echo("Preview only. Re-run with --apply to dispatch.", err=True)
        return
    _run(cmd)


if __name__ == "__main__":
    try:
        app()
    except subprocess.CalledProcessError as exc:
        logger.error("command failed with exit code {}: {}", exc.returncode, exc.cmd)
        if exc.stdout:
            typer.echo(exc.stdout, err=False)
        if exc.stderr:
            typer.echo(exc.stderr, err=True)
        raise typer.Exit(exc.returncode) from exc
