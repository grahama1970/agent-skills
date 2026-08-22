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
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlparse

import typer
from loguru import logger
from ticket_memory_plan import memory_plan_command


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
app.command("memory-plan")(memory_plan_command)


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


def _normalize_repo(repo: Optional[str]) -> Optional[str]:
    """Accept a local checkout path (e.g. ".") as well as OWNER/REPO.

    gh only accepts [HOST/]OWNER/REPO, so a path is resolved through the
    checkout's origin remote before being forwarded.
    """
    if not repo or not Path(repo).is_dir():
        return repo
    proc = _run(
        ["git", "-C", repo, "remote", "get-url", "origin"],
        capture=True,
        check=False,
    )
    if proc.returncode != 0:
        raise typer.BadParameter(
            f"--repo {repo!r} is a directory without an 'origin' remote; pass OWNER/REPO"
        )
    url = proc.stdout.strip()
    tail = url.split(":", 1)[-1] if url.startswith("git@") else urlparse(url).path
    parts = [p for p in tail.split("/") if p]
    if len(parts) < 2:
        raise typer.BadParameter(f"cannot derive OWNER/REPO from remote url {url!r}")
    return f"{parts[-2]}/{parts[-1].removesuffix('.git')}"


def _repo_args(repo: Optional[str]) -> list[str]:
    repo = _normalize_repo(repo)
    return ["--repo", repo] if repo else []


def _repo_hint(repo: Optional[str]) -> str:
    """Render the --repo suffix for a copy-pasteable remediation command."""
    return f" --repo {repo}" if repo else ""


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

#: Concurrency lanes. Two tickets in DIFFERENT lanes on one project can be
#: worked at the same time; two in the SAME lane cannot, because they edit the
#: same surface and the second stacks on the first's unmerged changes.
#:
#: project-watchdog uses `lane:<id>` to decide what is safe to dispatch in
#: parallel, so the lane is a scheduling fact, not documentation.
VALID_LANES = ("fe", "be", "data", "docs", "ops", "sec")

#: Emitted into every agent-routable ticket body. project-watchdog forwards the
#: body to a cron-dispatched agent that has no prior session, no memory of this
#: project, and no idea which skills exist. Without this it starts by grepping.
#:
#: Every command below is verified present in agent-skills. Order matters:
#: /memory's own contract is "query memory BEFORE scanning any codebase".
ORIENTATION_BLOCK = """You are running from cron with no prior context. Build context in this order
before changing anything. Do not start by grepping the repository.

1. **Recall first.** `skills/memory/run.sh recall --q "<target or symptom>"`
   Prior work on this exact problem may already exist. This is cheapest and
   most often decisive.
2. **Project state.** `skills/project-state/run.sh --json`
   Readiness, infrastructure health, doc-code drift, and known gaps in one
   command.
3. **Curated current state.** Read `PROJECT_KNOWLEDGE.md` in the target skill or
   repo when present. It records open blockers and decisions that the code does
   not.

Then use the narrowest tool for the actual question:

| Need | Use |
| --- | --- |
| Locate code by symbol or structure | `skills/treesitter/run.sh` |
| Find prior art in other repos | `skills/github-search/run.sh` |
| External research on a load-bearing claim | `skills/dogpile/run.sh "<claim>"`, else `skills/brave-search/run.sh web "<query>"` |
| Diagnose a failing test or traceback | load the `debugger` skill |
| Run the target's suites | `skills/test/run.sh` |

Load the skill's own `SKILL.md` before using it; do not infer its interface.
Record what you actually ran. A tool's success response is not proof — read
back the artifact it claims to have produced."""

#: Every route maps to exactly one lane, so existing tickets get a lane without
#: the filer having to think about it. `--lane` overrides when the route is a
#: poor fit.
ROUTE_LANE = {
    "frontend_code": "fe",
    "design_or_ux": "fe",
    "backend_python_or_skill_runtime": "be",
    "rust_or_binary": "be",
    "ops_or_scheduler": "ops",
    "documentation_or_report": "docs",
    "security_or_compliance": "sec",
    "unknown": "",
}


def _lane_for(route: str, lane: str) -> str:
    """Return the concurrency lane for a ticket, or empty when undecidable."""
    if lane:
        if lane not in VALID_LANES:
            _die(
                f"unknown --lane {lane!r}. Valid lanes: {', '.join(VALID_LANES)}. "
                "The lane decides what project-watchdog may dispatch concurrently: "
                "different lanes on one project run in parallel, the same lane does not."
            )
        return lane
    return ROUTE_LANE.get(route, "")

#: Commands that only ever exercise a deterministic gate. A proof made of these
#: alone is refused: a fixed expectation can be satisfied by a change that
#: targets the expectation rather than the behaviour.
#:
#: Observed 2026-07-27: a ticket proved by `pytest test_calc.py -q` was closed by
#: a patch that subclassed int and overrode __eq__ so the result compared equal
#: to two different numbers. The test passed, an independent reviewer re-ran it
#: and it passed there too. Nothing malfunctioned; the proof was just weaker than
#: the claim.
DETERMINISTIC_ONLY_MARKERS = (
    "pytest",
    "py_compile",
    "ruff",
    "mypy",
    "eslint",
    "npm test",
    "cargo test",
    "go test",
    "unittest",
    "jest",
    "vitest",
)

#: Signals that a proof actually runs the real path. At least one is required.
LIVE_PROOF_MARKERS = (
    "sanity-live",
    "sanity-e2e",
    "live_e2e",
    "--live",
    "--apply",
    "--allow-live",
    "e2e",
    "curl ",
    "gh ",
    "run.sh",
    "screenshot",
    "cdp",
    "browser",
    "readback",
    "read-back",
    "receipt",
)


def _is_deterministic_runner(command: str) -> bool:
    """Return whether the command's *executable* is a deterministic test runner.

    Matched against the leading words only. A substring search over the whole
    string is exploitable: `pytest tests/test_e2e.py` contains "e2e" and would
    otherwise satisfy a live-marker check on the strength of a filename.
    """
    head = " ".join(command.lower().split()[:3])
    return any(marker in head for marker in DETERMINISTIC_ONLY_MARKERS)


def _validate_live_proof(proof: str, ticket_type: str) -> None:
    """Refuse a ticket whose proof cannot distinguish a fix from a plausible fake.

    Enforces the Verification Contract in `best-practices-github-ticket`: every
    ticket names a live end-to-end proof that runs the real entrypoint against a
    surface the author does not control, and reads back the artifact it produced.

    Deterministic checks are welcome alongside it and are never sufficient alone.
    """
    if ticket_type in HUMAN_ONLY_TYPES:
        return
    text = proof.strip()
    if not text:
        _die("--proof is required")
    lowered = text.lower()
    # A proof may pair both tiers; require at least one live clause that is not
    # itself a deterministic runner.
    clauses = re.split(r"\band\b|;|\n|,", lowered)
    has_live = any(
        any(marker in clause for marker in LIVE_PROOF_MARKERS)
        and not _is_deterministic_runner(clause)
        for clause in clauses
    )
    has_det = any(marker in lowered for marker in DETERMINISTIC_ONLY_MARKERS)
    if has_live:
        return
    detail = (
        f"the proof names only deterministic checks ({text[:80]!r})"
        if has_det
        else f"the proof names no runnable live command ({text[:80]!r})"
    )
    _die(
        f"--proof must include a LIVE end-to-end command; {detail}.\n"
        "  A deterministic test states a fixed expectation, so it can be satisfied by a\n"
        "  change that targets the expectation instead of the behaviour. On 2026-07-27 a\n"
        "  ticket proved only by pytest was closed by a patch that overrode __eq__ so the\n"
        "  result compared equal to two different numbers. The test passed.\n"
        "  A live proof must run the real entrypoint against a service, model, browser,\n"
        "  repo, or filesystem you do not control, and read back the artifact it produced.\n"
        "  Examples:\n"
        "    'skills/x/sanity-live.sh, then read back the emitted receipt.json'\n"
        "    'uv run tau dag-run <spec> --apply; assert dag-receipt.json verdict=PASS'\n"
        "    'gh issue view <n> --json labels read back after the run'\n"
        "    'pytest tests/test_x.py -q AND ./run.sh e2e --allow-live with screenshot'\n"
        "  See best-practices-github-ticket, Verification Contract."
    )



def _is_agent_routable(ticket_type: str, route: str) -> bool:
    """Return whether a ticket is safe to hand to an automated repair loop.

    Requires a concrete maintainer route and a type that is actually actionable.
    Questions and triage tickets are human-first by definition, and a ticket with
    an unknown route has nowhere to be sent.
    """
    if ticket_type in HUMAN_ONLY_TYPES:
        return False
    return bool(route) and route != "unknown"


def _labels(ticket_type: str, target: str, route: str, agent: str, extra: list[str] | None = None, lane: str = "") -> list[str]:
    labels = [f"type:{ticket_type}"]
    routable = _is_agent_routable(ticket_type, route)
    if routable:
        labels.append(AGENT_WORK_LABEL)
    # A lane is what project-watchdog reads to decide whether this ticket may be
    # dispatched alongside another. It only means anything on a ticket the
    # watchdog can dispatch at all, so a human-first ticket carries none rather
    # than an inert label that reads like a scheduling commitment.
    resolved_lane = _lane_for(route, lane) if routable else ""
    if resolved_lane:
        labels.append(f"lane:{resolved_lane}")
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


def _require_agentic_eval_proof(proof: str, ticket_type: str, route: str) -> None:
    """An agent-routable ticket must prove its fix with an /agentic-evals run.

    project-watchdog's repair loop never authors a regression guard — the creator
    fixes and the reviewer verifies against the ticket's Required proof. So the
    ONLY thing that prevents the fix from silently regressing is the proof itself
    being an /agentic-evals run (a retained regression guard). Without it, the
    loop would fix the bug and leave nothing to stop it recurring. Human-first
    tickets (questions/triage) are exempt; they are not auto-dispatched.
    """
    if not _is_agent_routable(ticket_type, route):
        return
    norm = proof.lower().replace("_", "-")
    if "agentic-eval" not in norm:
        _die(
            "agent-routable tickets must prove the fix with an /agentic-evals run so it "
            "cannot silently regress.\n"
            "  project-watchdog's repair loop does NOT create a regression guard; the "
            "ticket's proof IS the guard.\n"
            "  Make --proof run the sanctioned runner against a committed guard case, e.g.:\n"
            "    'cd skills/agentic-evals && ./run.sh run ../<skill>/fixtures/agentic_eval.json "
            "--only-category <id> --map ../<skill>/fixtures/category_map.json shows READY'\n"
            "  Add the guard case to fixtures/agentic_eval.json first if it does not exist.\n"
            "  If no eval can exist yet, file as 'triage' (human-first, not auto-dispatched)."
        )


def _validate_common(ticket_type: str, target: str, proof: str, route: str) -> None:
    _validate_live_proof(proof, ticket_type)
    _require_agentic_eval_proof(proof, ticket_type, route)
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
    context_files: list[str] | None = None,
    required_skills: list[str] | None = None,
    depends_on: list[str] | None = None,
    memory_recipe: str = "",
    memory_symbols: list[str] | None = None,
    memory_identifiers: list[str] | None = None,
    memory_anchors: list[str] | None = None,
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
    # Bootstrap context for a stateless recurring agent. project-watchdog
    # forwards the whole issue body to the repair node, so the body is the only
    # project context a cron-dispatched agent gets. Naming the load-bearing
    # files and skills here beats making it rediscover them on every tick, and
    # only the VARIABLE part goes in the body: universal execution policy stays
    # in best-practices-github-ticket rather than being copied into every issue.
    # Always-on orientation. The per-ticket blocks below are the VARIABLE
    # context; this is the fixed part a cold agent needs to find anything at
    # all. It is a pointer, not policy: a cron-dispatched agent receives only
    # this issue body, so it cannot be told to "read best-practices-*" unless
    # the body says so and names how.
    if _is_agent_routable(ticket_type, route):
        lines.append(_section("Orientation for a stateless agent", ORIENTATION_BLOCK))
    if context_files:
        lines.append(
            _section(
                "Required repository context",
                "Read these before diagnosing or changing code:\n\n"
                + "\n".join(f"- `{item}`" for item in context_files),
            )
        )
    if required_skills:
        lines.append(
            _section(
                "Required skills",
                "Load these skills; do not rely on discovering them:\n\n"
                + "\n".join(f"- `{item}`" for item in required_skills),
            )
        )
    if depends_on:
        lines.append(
            _section(
                "Dependencies",
                "This ticket cannot close before these do:\n\n"
                + "\n".join(f"- blocked-by: {item}" for item in depends_on),
            )
        )
    lines.append(
        "<!-- ticket-skill\n"
        f"type: {ticket_type}\n"
        f"target: {target}\n"
        f"route: {route}\n"
        f"agent: {agent or 'unspecified'}\n"
        + (f"context_files: {','.join(context_files)}\n" if context_files else "")
        + (f"required_skills: {','.join(required_skills)}\n" if required_skills else "")
        + (f"depends_on: {','.join(depends_on)}\n" if depends_on else "")
        + (f"memory_recipe: {memory_recipe}\n" if memory_recipe else "")
        + (f"memory_symbols: {','.join(memory_symbols)}\n" if memory_symbols else "")
        + (f"memory_identifiers: {','.join(memory_identifiers)}\n" if memory_identifiers else "")
        + (f"memory_anchors: {','.join(memory_anchors)}\n" if memory_anchors else "")
        + "-->\n"
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
    context_files: list[str] | None = None,
    required_skills: list[str] | None = None,
    depends_on: list[str] | None = None,
    memory_recipe: str = "",
    memory_symbols: list[str] | None = None,
    memory_identifiers: list[str] | None = None,
    memory_anchors: list[str] | None = None,
    lane: str = "",
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
        context_files=context_files,
        required_skills=required_skills,
        depends_on=depends_on,
        memory_recipe=memory_recipe,
        memory_symbols=memory_symbols,
        memory_identifiers=memory_identifiers,
        memory_anchors=memory_anchors,
    )
    return TicketDraft(
        ticket_type=ticket_type,
        title=title,
        target=target,
        body=body,
        labels=_labels(ticket_type, target, route, agent, extra_labels, lane),
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


def _existing_repo_labels(repo: Optional[str]) -> Optional[set[str]]:
    """Return the set of label names that exist in the repo, or None on failure."""
    try:
        out = subprocess.run(
            ["gh", "label", "list", *_repo_args(repo), "--limit", "500", "--json", "name", "-q", ".[].name"],
            capture_output=True, text=True, check=True,
        )
        return {line.strip() for line in out.stdout.splitlines() if line.strip()}
    except Exception as exc:
        logger.warning("could not list repo labels (skipping label validation): {}", exc)
        return None


def _create_or_preview(draft: TicketDraft, *, repo: Optional[str], apply: bool, as_json: bool) -> None:
    if not apply:
        _emit_draft(draft, as_json=as_json)
        typer.echo("\nPreview only. Re-run with --apply to create the GitHub issue.", err=True)
        return
    # Drop labels that do not exist in the repo so one unknown label never aborts
    # the whole `gh issue create`. gh fails the entire call on a missing label.
    #
    # Scheduling labels are exempt from that leniency. `agent-work` is what makes
    # a ticket visible to project-watchdog at all, and `lane:<id>` is what decides
    # whether it may be dispatched alongside another in-flight ticket. Silently
    # dropping either produces a ticket that looks filed and never gets picked up,
    # so those fail closed with the command that fixes the repo.
    labels = list(draft.labels)
    existing = _existing_repo_labels(repo)
    if existing is not None:
        kept = [lbl for lbl in labels if lbl in existing]
        dropped = [lbl for lbl in labels if lbl not in existing]
        missing_scheduling = [
            lbl for lbl in dropped if lbl == AGENT_WORK_LABEL or lbl.startswith("lane:")
        ]
        if missing_scheduling:
            _die(
                f"scheduling labels missing from the repo: {', '.join(missing_scheduling)}. "
                "Without them project-watchdog cannot see or safely schedule this ticket. "
                f"Create them first: skills/ticket/run.sh ensure-labels{_repo_hint(repo)}"
            )
        if dropped:
            typer.echo(
                f"[ticket] skipping labels not present in repo (run ensure-labels to create them): {', '.join(dropped)}",
                err=True,
            )
        labels = kept
    cmd = ["gh", "issue", "create", *_repo_args(repo), "--title", draft.title]
    for label in labels:
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
    lane: str = typer.Option("", "--lane", help="Concurrency lane: fe, be, data, docs, ops, sec. Derived from --route when omitted."),
    agent: str = typer.Option("", "--agent"),
    non_goals: str = typer.Option("", "--non-goals"),
    label: list[str] = typer.Option([], "--label"),
    context_file: list[str] = typer.Option(
        [], "--context-file", help="Load-bearing file a stateless agent must read. Repeatable."
    ),
    required_skill: list[str] = typer.Option(
        [], "--required-skill", help="Skill the resolver must load. Repeatable."
    ),
    depends_on: list[str] = typer.Option(
        [], "--depends-on", help="owner/repo#N this ticket is blocked by. Repeatable."
    ),
    memory_recipe: str = typer.Option("", "--memory-recipe", help="Versioned Memory query recipe id."),
    memory_symbol: list[str] = typer.Option([], "--memory-symbol", help="Exact symbol anchor. Repeatable."),
    memory_identifier: list[str] = typer.Option([], "--memory-identifier", help="Exact identifier anchor. Repeatable."),
    memory_anchor: list[str] = typer.Option([], "--memory-anchor", help="Exact Memory search anchor. Repeatable."),
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
        lane=lane,
        non_goals=non_goals,
        details={
            "Observed failure": observed,
            "Expected behavior": expected,
            "Reproduction or artifact": repro,
        },
        extra_labels=label,
        context_files=list(context_file),
        required_skills=list(required_skill),
        depends_on=list(depends_on),
        memory_recipe=memory_recipe,
        memory_symbols=list(memory_symbol),
        memory_identifiers=list(memory_identifier),
        memory_anchors=list(memory_anchor),
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
    lane: str = typer.Option("", "--lane", help="Concurrency lane: fe, be, data, docs, ops, sec. Derived from --route when omitted."),
    agent: str = typer.Option("", "--agent"),
    non_goals: str = typer.Option("", "--non-goals"),
    label: list[str] = typer.Option([], "--label"),
    context_file: list[str] = typer.Option(
        [], "--context-file", help="Load-bearing file a stateless agent must read. Repeatable."
    ),
    required_skill: list[str] = typer.Option(
        [], "--required-skill", help="Skill the resolver must load. Repeatable."
    ),
    depends_on: list[str] = typer.Option(
        [], "--depends-on", help="owner/repo#N this ticket is blocked by. Repeatable."
    ),
    memory_recipe: str = typer.Option("", "--memory-recipe", help="Versioned Memory query recipe id."),
    memory_symbol: list[str] = typer.Option([], "--memory-symbol", help="Exact symbol anchor. Repeatable."),
    memory_identifier: list[str] = typer.Option([], "--memory-identifier", help="Exact identifier anchor. Repeatable."),
    memory_anchor: list[str] = typer.Option([], "--memory-anchor", help="Exact Memory search anchor. Repeatable."),
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
        lane=lane,
        non_goals=non_goals,
        details={
            "Current limitation": limitation,
            "Proposed capability": capability,
            "User workflow unlocked": workflow,
            "Acceptance criteria": acceptance,
        },
        extra_labels=label,
        context_files=list(context_file),
        required_skills=list(required_skill),
        depends_on=list(depends_on),
        memory_recipe=memory_recipe,
        memory_symbols=list(memory_symbol),
        memory_identifiers=list(memory_identifier),
        memory_anchors=list(memory_anchor),
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
    lane: str = typer.Option("", "--lane", help="Concurrency lane: fe, be, data, docs, ops, sec. Derived from --route when omitted."),
    agent: str = typer.Option("", "--agent"),
    non_goals: str = typer.Option("", "--non-goals"),
    repo: Optional[str] = typer.Option(None, "--repo", "-R"),
    context_file: list[str] = typer.Option(
        [], "--context-file", help="Load-bearing file a stateless agent must read. Repeatable."
    ),
    required_skill: list[str] = typer.Option(
        [], "--required-skill", help="Skill the resolver must load. Repeatable."
    ),
    depends_on: list[str] = typer.Option(
        [], "--depends-on", help="owner/repo#N this ticket is blocked by. Repeatable."
    ),
    memory_recipe: str = typer.Option("", "--memory-recipe", help="Versioned Memory query recipe id."),
    memory_symbol: list[str] = typer.Option([], "--memory-symbol", help="Exact symbol anchor. Repeatable."),
    memory_identifier: list[str] = typer.Option([], "--memory-identifier", help="Exact identifier anchor. Repeatable."),
    memory_anchor: list[str] = typer.Option([], "--memory-anchor", help="Exact Memory search anchor. Repeatable."),
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
        lane=lane,
        non_goals=non_goals,
        details={
            "Current cost or friction": friction,
            "Proposed improvement": improvement,
            "Measurable target": measurable_target,
        },
        context_files=list(context_file),
        required_skills=list(required_skill),
        depends_on=list(depends_on),
        memory_recipe=memory_recipe,
        memory_symbols=list(memory_symbol),
        memory_identifiers=list(memory_identifier),
        memory_anchors=list(memory_anchor),
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
    lane: str = typer.Option("", "--lane", help="Concurrency lane: fe, be, data, docs, ops, sec. Derived from --route when omitted."),
    agent: str = typer.Option("", "--agent"),
    non_goals: str = typer.Option("", "--non-goals"),
    label: list[str] = typer.Option([], "--label"),
    context_file: list[str] = typer.Option(
        [], "--context-file", help="Load-bearing file a stateless agent must read. Repeatable."
    ),
    required_skill: list[str] = typer.Option(
        [], "--required-skill", help="Skill the resolver must load. Repeatable."
    ),
    depends_on: list[str] = typer.Option(
        [], "--depends-on", help="owner/repo#N this ticket is blocked by. Repeatable."
    ),
    memory_recipe: str = typer.Option("", "--memory-recipe", help="Versioned Memory query recipe id."),
    memory_symbol: list[str] = typer.Option([], "--memory-symbol", help="Exact symbol anchor. Repeatable."),
    memory_identifier: list[str] = typer.Option([], "--memory-identifier", help="Exact identifier anchor. Repeatable."),
    memory_anchor: list[str] = typer.Option([], "--memory-anchor", help="Exact Memory search anchor. Repeatable."),
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
        lane=lane,
        non_goals=non_goals,
        details={
            "Invariant to preserve": invariant,
            "Cleanup target": cleanup,
            "Scoped files": scoped_files,
        },
        extra_labels=label,
        context_files=list(context_file),
        required_skills=list(required_skill),
        depends_on=list(depends_on),
        memory_recipe=memory_recipe,
        memory_symbols=list(memory_symbol),
        memory_identifiers=list(memory_identifier),
        memory_anchors=list(memory_anchor),
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
        # Question tickets are answered by a human, never dispatched to a repair
        # agent, so they carry no concurrency lane. The lane is a scheduling fact
        # for project-watchdog and would be meaningless here.
        lane="",
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
        # A triage ticket exists precisely because the route is not yet known,
        # and the lane is derived from the route. It gets a lane once triage
        # decides what it actually is.
        lane="",
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
def block(
    issue: int,
    reason: Path = typer.Option(..., "--reason"),
    release_lease: bool = typer.Option(False, "--release"),
    blocked_by: list[str] = typer.Option(
        [], "--blocked-by", help="owner/repo#N this issue is blocked by. Repeatable."
    ),
    repo: Optional[str] = typer.Option(None, "--repo", "-R"),
    dry_run: bool = False,
) -> None:
    """Mark an issue blocked, optionally recording cross-repo upstream blockers."""
    args = ["block", str(issue), "--reason", str(reason)]
    if release_lease:
        args.append("--release")
    for ref in blocked_by:
        args.extend(["--blocked-by", ref])
    _helper(args, repo=repo, dry_run=dry_run)


@app.command()
def unblock(issue: int, reason: Path = typer.Option(..., "--reason"), agent: Optional[str] = typer.Option(None, "--agent"), repo: Optional[str] = typer.Option(None, "--repo", "-R"), dry_run: bool = False) -> None:
    """Clear maintainer-blocked + needs-human so a resolved ticket can be closed.

    Pass --agent to re-lease (add maintainer-active) so you can close in one step.
    """
    args = ["unblock", str(issue), "--reason", str(reason)]
    if agent:
        args += ["--agent", agent]
    _helper(args, repo=repo, dry_run=dry_run)


@app.command()
def release(issue: int, agent: str = typer.Option(..., "--agent"), reason: Path = typer.Option(..., "--reason"), repo: Optional[str] = typer.Option(None, "--repo", "-R"), dry_run: bool = False) -> None:
    """Release a maintainer-active lease."""
    _helper(["release", str(issue), "--agent", agent, "--reason", str(reason)], repo=repo, dry_run=dry_run)


@app.command()
def close(
    issue: int,
    proof: Path = typer.Option(..., "--proof"),
    results: Path = typer.Option(
        ...,
        "--results",
        help="agent_skills.ticket_closure_evidence.v1 JSON with passing unit AND live e2e runs.",
    ),
    review: Optional[Path] = typer.Option(None, "--review"),
    reason: str = typer.Option("completed", "--reason"),
    repo: Optional[str] = typer.Option(None, "--repo", "-R"),
    dry_run: bool = False,
) -> None:
    """Close an issue. Requires a proof file AND machine-checkable test results."""
    if reason == "completed":
        _validate_closure_results(results)
        # Post the evidence, do not just check it. It was validated here and
        # then discarded, so nothing durable recorded what proved the closure:
        # project-watchdog's closure audit found zero artifact paths to read on
        # every ticket it reviewed, and had to judge "was the proof actually
        # run" from prose alone.
        proof = _proof_with_closure_evidence(proof, results)
    args = ["close", str(issue), "--proof", str(proof), "--reason", reason]
    if review:
        args.extend(["--review", str(review)])
    _helper(args, repo=repo, dry_run=dry_run)


def _proof_with_closure_evidence(proof: Path, results: Path) -> Path:
    """Append the closure-evidence JSON to the proof comment body.

    The reader is a later auditor with no access to this session: it needs the
    commands that ran and the artifact paths they wrote, in the ticket itself.
    """
    try:
        evidence = json.loads(results.read_text(encoding="utf-8"))
        body = proof.read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:
        logger.error("could not merge closure evidence into the proof: {}", exc)
        return proof

    merged = (
        f"{body.rstrip()}\n\n"
        f"## Closure evidence\n\n"
        f"Machine-checkable record of what proved this closure. The artifact "
        f"paths are what a later audit reads to confirm the proof actually ran.\n\n"
        f"```json\n{json.dumps(evidence, indent=2, sort_keys=True)}\n```\n"
    )
    merged_path = Path(tempfile.mkstemp(suffix=".md", prefix="ticket-proof-")[1])
    merged_path.write_text(merged, encoding="utf-8")
    return merged_path


CLOSURE_EVIDENCE_SCHEMA = "agent_skills.ticket_closure_evidence.v1"


def _validate_closure_results(path: Path) -> None:
    """Refuse closure unless both suites are present, passing, and live-backed.

    A prose proof file can assert anything. This is the machine-checkable half:
    the closer submits the actual runs, and each field is verified here rather
    than read as a claim.

    Requires, and fails on any of:

    - both a ``unit`` and an ``e2e`` block;
    - both reporting ``exit_code: 0``;
    - ``e2e.mocked: false`` and ``e2e.live: true`` — a mocked run is not an e2e run;
    - ``e2e.command`` naming something other than a deterministic test runner,
      because a deterministic expectation can be satisfied by a change that
      targets the expectation instead of the behaviour;
    - ``e2e.artifact`` existing and non-empty on disk. The artifact is read back
      here; a tool's own success response is not proof that it wrote anything.
    """
    if not path.is_file():
        _die(f"--results file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        _die(f"--results is not valid JSON: {exc}")
    if data.get("schema") != CLOSURE_EVIDENCE_SCHEMA:
        _die(f"--results must declare schema {CLOSURE_EVIDENCE_SCHEMA}; got {data.get('schema')!r}")

    problems: list[str] = []
    for tier in ("unit", "e2e"):
        block = data.get(tier)
        if not isinstance(block, dict):
            problems.append(f"missing '{tier}' block")
            continue
        if not str(block.get("command", "")).strip():
            problems.append(f"{tier}.command is empty")
        if block.get("exit_code") != 0:
            problems.append(f"{tier} did not pass: exit_code={block.get('exit_code')!r}")

    e2e = data.get("e2e") if isinstance(data.get("e2e"), dict) else {}
    if e2e:
        if e2e.get("mocked") is not False:
            problems.append("e2e.mocked must be false; a mocked run is not an end-to-end run")
        if e2e.get("live") is not True:
            problems.append("e2e.live must be true")
        command = str(e2e.get("command", "")).lower()
        if command and _is_deterministic_runner(command):
            problems.append(
                f"e2e.command {e2e.get('command')!r} is a deterministic test runner, "
                "not a live end-to-end run (a filename containing 'e2e' is not a live entrypoint)"
            )
        elif command and not any(m in command for m in LIVE_PROOF_MARKERS):
            problems.append(f"e2e.command {e2e.get('command')!r} names no live entrypoint")
        artifact = str(e2e.get("artifact", "")).strip()
        if not artifact:
            problems.append("e2e.artifact is required; the live run must produce a read-back artifact")
        else:
            candidate = Path(artifact).expanduser()
            if not candidate.is_file():
                problems.append(f"e2e.artifact does not exist: {artifact}")
            elif not candidate.read_text(encoding="utf-8", errors="replace").strip():
                problems.append(f"e2e.artifact is empty: {artifact}")

    if problems:
        _die(
            "closure refused; --results does not evidence a passing unit + live e2e run:\n"
            + "\n".join(f"  - {item}" for item in problems)
            + "\n\n  Required shape:\n"
            + json.dumps(
                {
                    "schema": CLOSURE_EVIDENCE_SCHEMA,
                    "issue": 123,
                    "unit": {"command": "uv run pytest -q", "exit_code": 0, "passed": 42},
                    "e2e": {
                        "command": "./run.sh sanity-live.sh --allow-live",
                        "exit_code": 0,
                        "mocked": False,
                        "live": True,
                        "artifact": "/abs/path/receipt.json",
                    },
                },
                indent=2,
            )
            + "\n  See best-practices-github-ticket, Verification Contract."
        )
    typer.echo(
        f"closure evidence accepted: unit exit 0, live e2e exit 0, "
        f"artifact read back from {e2e.get('artifact')}"
    )


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
