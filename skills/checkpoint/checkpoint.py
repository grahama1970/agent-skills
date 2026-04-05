"""Session checkpoint — 50% deterministic (git), 50% human/agent.

v5: Git provides the WHAT (files changed, commits, test results, branch state).
Human provides the WHY (grade, resume instruction). Agent provides topic + failures.
No more agent-authored summaries or self-reported file lists.

Workflow:
  End of session:  /checkpoint save -t "topic" --grade clean --resume "read X, do Y"
  Next session:    /clear → /checkpoint resume
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from typing import Optional

import typer
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from helpers import (
    CHECKPOINT_PREFIX,
    default_workspace_scope,
    detect_project_root,
    detect_scope,
    detect_transcript_paths,
    git,
    git_context,
    git_commit_and_push,
    git_exec,
    memory_post,
    store_skill_chain,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_GRADES = ("unresolved", "workaround", "solved", "clean", "reusable")
CHECKPOINT_TAG_PREFIX = "checkpoint/"

# Grade → outcome mapping (deterministic, no self-reporting)
GRADE_TO_OUTCOME = {
    "unresolved": "failed",
    "workaround": "partial",
    "solved": "success",
    "clean": "success",
    "reusable": "success",
}

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

console = Console(stderr=True)
app = typer.Typer(
    name="checkpoint",
    help="Git-grounded session checkpoints. Git provides the WHAT, human provides the WHY.",
    no_args_is_help=True,
)

logger.remove()
logger.add(sys.stderr, level=os.environ.get("LOG_LEVEL", "WARNING"))


# ---------------------------------------------------------------------------
# Git-derived state (deterministic — can't lie)
# ---------------------------------------------------------------------------


def _last_checkpoint_tag(root: str) -> str:
    """Find the most recent checkpoint/* tag."""
    tags = git(["tag", "--list", f"{CHECKPOINT_TAG_PREFIX}*", "--sort=-creatordate"], cwd=root)
    if tags:
        return tags.splitlines()[0].strip()
    return ""


def _git_since_tag(root: str, tag: str) -> dict:
    """Get deterministic git state since a checkpoint tag."""
    if tag:
        log = git(["log", "--oneline", f"{tag}..HEAD"], cwd=root)
        diff_stat = git(["diff", "--stat", tag], cwd=root)
        diff_files = git(["diff", "--name-only", tag], cwd=root)
        commit_count = len(log.splitlines()) if log else 0
    else:
        log = git(["log", "--oneline", "-20"], cwd=root)
        diff_stat = ""
        diff_files = ""
        commit_count = -1  # unknown, no baseline

    return {
        "since_tag": tag,
        "commits_since": log.splitlines() if log else [],
        "commit_count": commit_count,
        "diff_stat": diff_stat,
        "files_changed": diff_files.splitlines() if diff_files else [],
    }


def _git_preflight(root: str) -> dict:
    """Current git state — branch, dirty, ahead/behind."""
    branch = git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=root)
    commit = git(["rev-parse", "--short", "HEAD"], cwd=root)
    commit_msg = git(["log", "-1", "--format=%s"], cwd=root)

    # Dirty state
    status = git(["status", "--porcelain"], cwd=root)
    dirty_files = [l[3:] for l in status.splitlines() if l.strip()] if status else []

    # Ahead/behind
    ahead_behind = ""
    tracking = git(["rev-parse", "--abbrev-ref", "@{upstream}"], cwd=root)
    if tracking:
        ab = git(["rev-list", "--left-right", "--count", f"HEAD...@{{upstream}}"], cwd=root)
        if ab:
            parts = ab.split()
            if len(parts) == 2:
                ahead, behind = int(parts[0]), int(parts[1])
                if ahead or behind:
                    ahead_behind = f"ahead {ahead}, behind {behind}"

    return {
        "branch": branch,
        "commit": commit,
        "commit_message": commit_msg,
        "dirty_files": dirty_files[:20],
        "dirty_count": len(dirty_files),
        "ahead_behind": ahead_behind,
    }


def _run_tests(root: str) -> dict:
    """Run tests and return pass/fail + summary. Non-blocking — skips if no test runner found."""
    # Try common test runners
    for cmd, label in [
        (["make", "test"], "make test"),
        ([".venv/bin/pytest", "--tb=no", "-q", "--no-header"], "pytest"),
        (["cargo", "test", "--", "--quiet"], "cargo test"),
    ]:
        full_path = os.path.join(root, cmd[0]) if not cmd[0].startswith("/") else cmd[0]
        # Check if the command exists
        if cmd[0] == "make":
            makefile = os.path.join(root, "Makefile")
            if not os.path.isfile(makefile):
                continue
        elif cmd[0] == ".venv/bin/pytest":
            if not os.path.isfile(os.path.join(root, cmd[0])):
                continue
        elif cmd[0] == "cargo":
            if not os.path.isfile(os.path.join(root, "Cargo.toml")):
                continue

        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120, cwd=root,
                env={**os.environ, "VIRTUAL_ENV": ""},
            )
            # Extract last line as summary
            output = r.stdout.strip() or r.stderr.strip()
            last_lines = output.splitlines()[-3:] if output else []
            return {
                "runner": label,
                "passed": r.returncode == 0,
                "exit_code": r.returncode,
                "summary": "\n".join(last_lines),
            }
        except subprocess.TimeoutExpired:
            return {"runner": label, "passed": False, "exit_code": -1, "summary": "TIMEOUT after 120s"}
        except FileNotFoundError:
            continue

    return {"runner": "none", "passed": None, "exit_code": None, "summary": "no test runner found"}


# ---------------------------------------------------------------------------
# Temporal queries (for recall/last)
# ---------------------------------------------------------------------------


def _query_checkpoints_by_time(limit: int = 1, scope: str = "", extra_tags: list[str] | None = None) -> list[dict]:
    tags = ["checkpoint"] + (extra_tags or [])
    payload: dict = {
        "q": CHECKPOINT_PREFIX, "k": limit, "tags": tags,
        "sort": "created_at", "prefix": CHECKPOINT_PREFIX,
        "collections": ["checkpoints", "lessons"],
    }
    if scope:
        payload["scope"] = scope
    result = memory_post("/recall", payload, console=console)
    return result.get("items", [])


def _recall_with_scope_fallback(query: str, scope: str, limit: int, extra_tags: list[str] | None = None) -> list[dict]:
    tags = ["checkpoint"] + (extra_tags or [])
    result = memory_post("/recall", {
        "q": query, "scope": scope, "k": limit, "tags": tags,
        "prefix": CHECKPOINT_PREFIX, "collections": ["checkpoints", "lessons"],
    }, console=console)
    items = result.get("items", [])
    if items:
        return _parse_checkpoint_items(items)

    result_all = memory_post("/recall", {
        "q": query, "k": limit, "tags": tags,
        "prefix": CHECKPOINT_PREFIX, "collections": ["checkpoints", "lessons"],
    }, console=console)
    return _parse_checkpoint_items(result_all.get("items", []))


def _query_checkpoints_by_time_with_fallback(limit: int = 1, scope: str = "", extra_tags: list[str] | None = None) -> list[dict]:
    items = _query_checkpoints_by_time(limit=limit, scope=scope, extra_tags=extra_tags)
    if items:
        return items
    if scope:
        return _query_checkpoints_by_time(limit=limit, scope="", extra_tags=extra_tags)
    return []


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def save(
    topic: str = typer.Option(..., "--topic", "-t", help="What was attempted this session"),
    grade: str = typer.Option(..., "--grade", "-g", help="Human grade: unresolved|workaround|solved|clean|reusable"),
    resume_instruction: str = typer.Option(..., "--resume", "-r", help="Literal instruction for next session (REQUIRED)"),
    session_name: Optional[str] = typer.Option(None, "--session", help="Terminal session name (default: $CLAUDE_SESSION env var)"),
    failures: Optional[list[str]] = typer.Option(None, "--failures", help="What failed and why (repeatable)"),
    skills: Optional[list[str]] = typer.Option(None, "--skills", help="Skills used (repeatable)"),
    run_tests: bool = typer.Option(False, "--test", is_flag=True, help="Run tests and include results"),
    project_root: Optional[str] = typer.Option(None, "--project-root", help="Project root (auto-detected)"),
    scope: Optional[str] = typer.Option(None, "--scope", help="Memory scope (default: project name)"),
    session_id: Optional[str] = typer.Option(None, "--session-id", help="Conversation session identifier"),
    episode_key: Optional[str] = typer.Option(None, "--episode-key", help="ArangoDB _key of episodic archive"),
    output_json: bool = typer.Option(False, "--json", is_flag=True, help="Output as JSON"),
) -> None:
    """Save a checkpoint. Git provides the WHAT, you provide the WHY."""
    if grade not in VALID_GRADES:
        console.print(f"[red]Invalid grade '{grade}'. Valid: {VALID_GRADES}[/red]")
        raise typer.Exit(1)

    # Auto-detect session name from env if not provided
    if not session_name:
        session_name = os.environ.get("CLAUDE_SESSION", "") or None

    # Require --failures for non-success grades
    outcome = GRADE_TO_OUTCOME[grade]
    if outcome in ("failed", "partial") and not failures:
        console.print("[red]--failures is required when grade is unresolved or workaround[/red]")
        console.print("[dim]What went wrong? The next session needs to know.[/dim]")
        raise typer.Exit(1)

    root = project_root or detect_project_root()
    scope_val = scope or detect_scope(root)

    # === DETERMINISTIC: git state ===
    preflight = _git_preflight(root)
    last_tag = _last_checkpoint_tag(root)
    since = _git_since_tag(root, last_tag)

    # === DETERMINISTIC: tests (optional) ===
    test_result = _run_tests(root) if run_tests else None

    # === GIT: commit + push + tag ===
    commit_info = git_commit_and_push(root, topic, [], console=console,
                                      skills=skills, grade=grade)

    # Create checkpoint tag
    timestamp = datetime.now(timezone.utc)
    tag_name = f"{CHECKPOINT_TAG_PREFIX}{timestamp.strftime('%Y-%m-%d-%H%M%S')}"
    git_exec(["tag", "-a", tag_name, "-m", f"checkpoint: {topic[:60]}"], cwd=root)
    git_exec(["push", "origin", tag_name], cwd=root, timeout=30)

    # === BUILD DOC: 50/50 deterministic + human ===
    ts_iso = timestamp.isoformat()
    solution_doc: dict = {
        "checkpoint_version": 5,
        "timestamp": ts_iso,
        # Human/agent authored (the WHY)
        "topic": topic,
        "grade": grade,
        "outcome": outcome,
        "resume": resume_instruction,
        "failures": failures or [],
        "skills_used": [s.lstrip("/") for s in skills] if skills else [],
        "session": session_name or "",
        # Deterministic (the WHAT — from git)
        "tag": tag_name,
        "git": {
            "branch": preflight["branch"],
            "commit": preflight["commit"],
            "commit_message": preflight["commit_message"],
            "dirty_count": preflight["dirty_count"],
            "ahead_behind": preflight["ahead_behind"],
        },
        "since_last_checkpoint": {
            "previous_tag": last_tag,
            "commit_count": since["commit_count"],
            "commits": since["commits_since"][:20],
            "files_changed": since["files_changed"][:50],
            "diff_stat": since["diff_stat"],
        },
    }
    if test_result:
        solution_doc["tests"] = test_result
    if commit_info.get("commit_hash"):
        solution_doc["checkpoint_commit"] = commit_info["commit_hash"]
    if session_id:
        solution_doc["session_id"] = session_id
    if episode_key:
        solution_doc["episode_key"] = episode_key

    # Auto-detect transcript paths for this session
    transcript_paths = detect_transcript_paths(root)
    if transcript_paths:
        solution_doc["transcript_paths"] = transcript_paths

    # Tags for filtering
    date_str = ts_iso[:10]
    tags = [
        "checkpoint", "session-state",
        f"outcome:{outcome}", f"grade:{grade}",
        f"project:{scope_val}", f"date:{date_str}",
        f"branch:{preflight['branch']}",
    ]
    if test_result and test_result.get("passed") is not None:
        tags.append(f"tests:{'pass' if test_result['passed'] else 'fail'}")
    if session_name:
        tags.append(f"session:{session_name}")

    # Store to dedicated checkpoints collection via /store
    # Fields mapped to lessons_v2_search schema: title, problem, playbook
    # so the existing BM25 pipeline finds checkpoints without bespoke AQL
    checkpoint_doc = {
        **solution_doc,
        "title": f"{CHECKPOINT_PREFIX} {date_str} [{scope_val}] {topic}",
        "problem": f"Grade: {grade} | Outcome: {outcome}\nResume: {resume_instruction}",
        "playbook": f"- {resume_instruction}",
        "tags": tags,
        "scope": scope_val,
    }
    result = memory_post("/store", {
        "document": checkpoint_doc,
        "collection": "checkpoints",
    }, console=console)
    checkpoint_key = result.get("_key", "") if isinstance(result, dict) else ""

    # Skill chain storage — links checkpoint → skill_chain via edge
    if skills:
        store_skill_chain(
            topic=topic, summary=resume_instruction, decisions=[],
            scope=scope_val, outcome=outcome,
            explicit_skills=skills, console=console,
            checkpoint_key=checkpoint_key,
        )

    if output_json:
        print(json.dumps({"status": "saved", "tag": tag_name, **solution_doc}, indent=2))
        return

    # Rich output
    gc = {"unresolved": "red", "workaround": "yellow", "solved": "bright_yellow",
          "clean": "green", "reusable": "blue"}.get(grade, "white")
    test_str = ""
    if test_result:
        tp = "[green]PASS[/green]" if test_result["passed"] else "[red]FAIL[/red]"
        test_str = f"\n[bold]Tests:[/bold] {tp} ({test_result['runner']})"

    console.print(Panel(
        f"[bold]Topic:[/bold] {topic}\n"
        f"[bold]Grade:[/bold] [{gc}]{grade.upper()}[/{gc}]\n"
        f"[bold]Tag:[/bold] {tag_name}\n"
        f"[bold]Branch:[/bold] {preflight['branch']} @ {preflight['commit']}\n"
        f"[bold]Changes:[/bold] {since['commit_count']} commits, {len(since['files_changed'])} files"
        f"{test_str}\n"
        f"[bold]Resume:[/bold] {resume_instruction}\n"
        f"{'[bold red]Failures:[/bold red] ' + '; '.join(failures) if failures else ''}",
        title="CHECKPOINT SAVED",
        border_style=gc,
    ))


@app.command()
def resume(
    session_name: Optional[str] = typer.Option(None, "--session", help="Terminal session (default: $CLAUDE_SESSION)"),
    topic: Optional[str] = typer.Option(None, "--topic", "-t", help="Search by topic (default: latest)"),
    scope: Optional[str] = typer.Option(None, "--scope", help="Memory scope filter"),
    output_json: bool = typer.Option(False, "--json", is_flag=True, help="Output as JSON"),
) -> None:
    """Resume after /clear. Shows git-derived state + human's resume instruction.

    Deterministic: branch, dirty files, commits since checkpoint, test results.
    Human-authored: resume instruction, failures to avoid.

    Session auto-detected from $CLAUDE_SESSION env var, or use --session.
    """
    # Auto-detect session from env
    if not session_name:
        session_name = os.environ.get("CLAUDE_SESSION", "") or None

    scope_val = scope or default_workspace_scope()
    root = detect_project_root()

    # Build query with optional session filter
    extra_tags = [f"session:{session_name}"] if session_name else []

    # Fetch last checkpoint from ArangoDB
    if topic:
        query = f"{CHECKPOINT_PREFIX} {topic}"
        checkpoints = _recall_with_scope_fallback(query, scope_val, 1, extra_tags=extra_tags)
    else:
        items = _query_checkpoints_by_time_with_fallback(limit=1, scope=scope_val, extra_tags=extra_tags)
        checkpoints = _parse_checkpoint_items(items) if items else []

    # Live git state (deterministic — current truth)
    preflight = _git_preflight(root)
    last_tag = _last_checkpoint_tag(root)
    since = _git_since_tag(root, last_tag)

    # === RECALL: prior solutions + recommended skill chains ===
    prior_solutions: list[dict] = []
    recommended_chains: list[dict] = []
    if checkpoints:
        cp = checkpoints[0]
        recall_query = cp.get("resume", "") or cp.get("topic", "")
        if recall_query:
            try:
                recall_result = memory_post("/recall", {
                    "q": recall_query,
                    "k": 3,
                    "collections": ["lessons_v2", "skill_chains"],
                }, console=None)
                for item in recall_result.get("items", []):
                    source = item.get("_source", "")
                    if source == "skill_chains":
                        chain = item.get("skills", [])
                        if not chain:
                            sol = item.get("solution", "")
                            if isinstance(sol, str) and sol.startswith("{"):
                                try:
                                    chain = json.loads(sol).get("chain", [])
                                except (json.JSONDecodeError, TypeError):
                                    pass
                        if chain:
                            recommended_chains.append({
                                "chain": chain,
                                "task": item.get("problem", "")[:80],
                                "score": item.get("scores", {}).get("bm25", 0),
                            })
                    else:
                        problem = item.get("problem", "")
                        solution = item.get("solution", "")
                        if problem and solution:
                            prior_solutions.append({
                                "problem": problem[:100],
                                "solution": solution[:150],
                            })
            except (TypeError, KeyError):
                pass  # recall unavailable, non-fatal

    if output_json:
        slim = {
            "checkpoint": checkpoints[0] if checkpoints else None,
            "live_git": {
                "branch": preflight["branch"],
                "commit": preflight["commit"],
                "dirty_count": preflight["dirty_count"],
                "ahead_behind": preflight["ahead_behind"],
                "since_tag": last_tag,
                "commits_since": since["commit_count"],
                "files_changed": since["files_changed"][:20],
            },
            "prior_solutions": prior_solutions,
            "recommended_chains": recommended_chains,
        }
        print(json.dumps(slim, indent=2))
        return

    # === RENDER ===
    lines = []

    # Section 1: Git preflight (deterministic, current)
    lines.append("[bold]GIT STATE (live):[/bold]")
    lines.append(f"  Branch: [cyan]{preflight['branch']}[/cyan] @ {preflight['commit']}")
    if preflight["dirty_count"] > 0:
        lines.append(f"  [yellow]Dirty: {preflight['dirty_count']} uncommitted files[/yellow]")
        for f in preflight["dirty_files"][:5]:
            lines.append(f"    - {f}")
    else:
        lines.append("  [green]Clean working tree[/green]")
    if preflight["ahead_behind"]:
        lines.append(f"  Remote: {preflight['ahead_behind']}")
    lines.append("")

    # Section 2: What changed since last checkpoint (deterministic)
    if last_tag:
        lines.append(f"[bold]SINCE {last_tag}:[/bold]")
        lines.append(f"  {since['commit_count']} commits, {len(since['files_changed'])} files changed")
        if since["commits_since"]:
            lines.append("  [dim]Recent commits:[/dim]")
            for c in since["commits_since"][:10]:
                lines.append(f"    {c}")
        lines.append("")

    # Section 3: Human-authored context from checkpoint
    if checkpoints:
        cp = checkpoints[0]
        grade = cp.get("grade", "")
        gc = {"unresolved": "red", "workaround": "yellow", "solved": "bright_yellow",
              "clean": "green", "reusable": "blue"}.get(grade, "white")

        lines.append(f"[bold]LAST SESSION:[/bold] {cp.get('topic', '?')} [{gc}]{grade.upper()}[/{gc}]")

        resume_text = cp.get("resume", "")
        if resume_text:
            lines.append(f"\n[bold green]>>> DO THIS:[/bold green]")
            lines.append(f"  {resume_text}")

        cp_failures = cp.get("failures", [])
        if cp_failures:
            lines.append(f"\n[bold red]>>> DON'T REPEAT:[/bold red]")
            for f in cp_failures:
                lines.append(f"  - {f}")

        lines.append(f"\n[dim]Saved: {cp.get('timestamp', '?')}[/dim]")
    else:
        lines.append("[yellow]No previous checkpoint found.[/yellow]")

    # Section 4: Prior solutions from /memory recall
    if prior_solutions:
        lines.append("")
        lines.append("[bold]PRIOR SOLUTIONS:[/bold]")
        for ps in prior_solutions[:3]:
            lines.append(f"  [dim]{ps['problem']}[/dim]")
            lines.append(f"    → {ps['solution']}")

    # Section 5: Recommended skill chains
    if recommended_chains:
        lines.append("")
        lines.append("[bold]RECOMMENDED SKILL CHAINS:[/bold]")
        for rc in recommended_chains[:3]:
            chain_str = " → ".join(f"/{s}" for s in rc["chain"])
            lines.append(f"  [cyan]{chain_str}[/cyan]")
            if rc.get("task"):
                lines.append(f"    [dim]{rc['task']}[/dim]")

    console.print(Panel("\n".join(lines), title="RESUME", border_style="cyan"))


@app.command()
def recall(
    topic: Optional[str] = typer.Option(None, "--topic", "-t", help="Topic to search for"),
    scope: Optional[str] = typer.Option(None, "--scope", help="Memory scope filter"),
    limit: int = typer.Option(3, "--limit", "-k", help="Max results"),
    output_json: bool = typer.Option(False, "--json", is_flag=True, help="Output as JSON"),
) -> None:
    """Search checkpoints by topic."""
    query = f"{CHECKPOINT_PREFIX} {topic}" if topic else CHECKPOINT_PREFIX
    scope_val = scope or default_workspace_scope()
    checkpoints = _recall_with_scope_fallback(query, scope_val, limit)

    if output_json:
        print(json.dumps(checkpoints, indent=2))
        return

    if not checkpoints:
        console.print(f"[yellow]No checkpoints found (scope={scope_val}).[/yellow]")
        return

    for i, cp in enumerate(checkpoints):
        _render_checkpoint_compact(cp, index=i + 1)


@app.command()
def last(
    scope: Optional[str] = typer.Option(None, "--scope", help="Memory scope filter"),
    output_json: bool = typer.Option(False, "--json", is_flag=True, help="Output as JSON"),
) -> None:
    """Show the most recent checkpoint."""
    scope_val = scope or default_workspace_scope()
    items = _query_checkpoints_by_time_with_fallback(limit=1, scope=scope_val)
    if not items:
        console.print("[yellow]No checkpoints found.[/yellow]")
        return
    checkpoints = _parse_checkpoint_items(items)
    if output_json:
        print(json.dumps(checkpoints[0] if checkpoints else {}, indent=2))
        return
    if checkpoints:
        _render_checkpoint_compact(checkpoints[0], index=1)


@app.command("list")
def list_cmd(
    limit: int = typer.Option(5, "--limit", "-k", help="Max results"),
    scope: Optional[str] = typer.Option(None, "--scope", help="Memory scope filter"),
    output_json: bool = typer.Option(False, "--json", is_flag=True, help="Output as JSON"),
) -> None:
    """List recent checkpoints."""
    scope_val = scope or default_workspace_scope()
    items = _query_checkpoints_by_time_with_fallback(limit=limit, scope=scope_val)
    checkpoints = _parse_checkpoint_items(items)

    if output_json:
        print(json.dumps(checkpoints, indent=2))
        return

    if not checkpoints:
        console.print("[yellow]No checkpoints found.[/yellow]")
        return

    table = Table(title="Checkpoints", show_lines=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Topic", style="bold", max_width=30)
    table.add_column("Grade", width=12)
    table.add_column("Branch", style="cyan", width=15)
    table.add_column("Tag", style="dim", width=28)
    table.add_column("Time", style="green", width=19)

    for i, cp in enumerate(checkpoints, 1):
        grade = cp.get("grade", "?")
        gc = {"unresolved": "red", "workaround": "yellow", "solved": "bright_yellow",
              "clean": "green", "reusable": "blue"}.get(grade, "white")
        table.add_row(
            str(i),
            _truncate(cp.get("topic", "?"), 30),
            f"[{gc}]{grade}[/{gc}]",
            cp.get("git", {}).get("branch", "?"),
            cp.get("tag", ""),
            cp.get("timestamp", "?")[:19],
        )
    console.print(table)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_checkpoint_items(items: list[dict]) -> list[dict]:
    """Parse ArangoDB recall items into checkpoint dicts.

    Handles two sources:
    - checkpoints collection: fields stored directly on the document
    - lessons_v2 (legacy): checkpoint data JSON-encoded in 'solution' field
    """
    checkpoints = []
    for item in items:
        source = item.get("_source", "")

        # New format: checkpoints collection — fields are directly on the document
        if source == "checkpoints":
            # solution_doc was stored as a nested dict; parse if JSON string
            sol = item.get("solution", "")
            if isinstance(sol, str) and sol.startswith("{"):
                try:
                    sol = json.loads(sol)
                except (json.JSONDecodeError, TypeError):
                    sol = {}
            elif not isinstance(sol, dict):
                sol = {}

            parsed = {**item, **sol} if isinstance(sol, dict) else item
            checkpoint = {
                "topic": parsed.get("topic", ""),
                "grade": parsed.get("grade", ""),
                "outcome": parsed.get("outcome", ""),
                "resume": parsed.get("resume", ""),
                "failures": parsed.get("failures", []),
                "tag": parsed.get("tag", ""),
                "git": parsed.get("git", {}),
                "since_last_checkpoint": parsed.get("since_last_checkpoint", {}),
                "tests": parsed.get("tests", {}),
                "skills_used": parsed.get("skills_used", []),
                "timestamp": parsed.get("timestamp", _epoch_to_iso(item.get("updated_at")) or ""),
                "scope": item.get("scope", ""),
                "_key": item.get("_key", ""),
                "summary": parsed.get("summary", ""),
                "next_steps": parsed.get("next_steps", []),
                "files": parsed.get("files", []),
            }
            checkpoints.append(checkpoint)
            continue

        # Legacy format: lessons_v2 — checkpoint data in JSON 'solution' field
        solution = item.get("solution", "")
        parsed = {}
        if solution:
            try:
                parsed = json.loads(solution)
            except (json.JSONDecodeError, TypeError):
                parsed = {"raw_solution": solution}

        topic = parsed.get("topic", "")
        if not topic:
            problem = item.get("problem", "")
            if problem.startswith(CHECKPOINT_PREFIX):
                raw = problem[len(CHECKPOINT_PREFIX):].strip()
                m = re.match(r"^\d{4}-\d{2}-\d{2}\s+\[([^\]]+)\]\s+(.+)$", raw.split("\n")[0])
                topic = m.group(2).strip() if m else raw.split("\n")[0]

        checkpoint = {
            "topic": topic,
            "grade": parsed.get("grade", ""),
            "outcome": parsed.get("outcome", ""),
            "resume": parsed.get("resume", ""),
            "failures": parsed.get("failures", []),
            "tag": parsed.get("tag", ""),
            "git": parsed.get("git", {}),
            "since_last_checkpoint": parsed.get("since_last_checkpoint", {}),
            "tests": parsed.get("tests", {}),
            "skills_used": parsed.get("skills_used", []),
            "timestamp": parsed.get("timestamp", _epoch_to_iso(item.get("updated_at")) or ""),
            "scope": item.get("scope", ""),
            "_key": item.get("_key", ""),
            "summary": parsed.get("summary", ""),
            "next_steps": parsed.get("next_steps", []),
            "files": parsed.get("files", []),
        }
        checkpoints.append(checkpoint)
    return checkpoints


def _render_checkpoint_compact(cp: dict, index: int = 1) -> None:
    """Compact single-checkpoint view."""
    grade = cp.get("grade", "")
    gc = {"unresolved": "red", "workaround": "yellow", "solved": "bright_yellow",
          "clean": "green", "reusable": "blue"}.get(grade, "white")

    lines = [
        f"[bold]Topic:[/bold] {cp.get('topic', '?')}",
        f"[bold]Grade:[/bold] [{gc}]{grade.upper() or '?'}[/{gc}]",
    ]

    if cp.get("tag"):
        lines.append(f"[bold]Tag:[/bold] {cp['tag']}")

    git_info = cp.get("git", {})
    if git_info:
        lines.append(f"[bold]Branch:[/bold] {git_info.get('branch', '?')} @ {git_info.get('commit', '?')}")

    since = cp.get("since_last_checkpoint", {})
    if since:
        lines.append(f"[bold]Changes:[/bold] {since.get('commit_count', '?')} commits, {len(since.get('files_changed', []))} files")

    tests = cp.get("tests", {})
    if tests and tests.get("passed") is not None:
        tp = "[green]PASS[/green]" if tests["passed"] else "[red]FAIL[/red]"
        lines.append(f"[bold]Tests:[/bold] {tp}")

    if cp.get("resume"):
        lines.append(f"\n[bold green]Resume:[/bold green] {cp['resume']}")

    if cp.get("failures"):
        lines.append(f"\n[bold red]Failures:[/bold red]")
        for f in cp["failures"]:
            lines.append(f"  - {f}")

    # v3/v4 compat: show summary/next_steps if no resume
    if not cp.get("resume") and cp.get("summary"):
        lines.append(f"\n[bold]Summary:[/bold] {cp['summary']}")
    if not cp.get("resume") and cp.get("next_steps"):
        lines.append(f"\n[bold]Next Steps:[/bold]")
        for ns in cp["next_steps"]:
            lines.append(f"  - {ns}")

    lines.append(f"\n[dim]{cp.get('timestamp', '?')[:19]}[/dim]")

    console.print(Panel("\n".join(lines), title=f"Checkpoint #{index}", border_style=gc or "blue"))


def _epoch_to_iso(epoch: int | float | None) -> str:
    if not epoch:
        return ""
    try:
        return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()
    except (OSError, ValueError):
        return ""


def _truncate(text: str, max_len: int) -> str:
    text = text.replace("\n", " ").strip()
    return text if len(text) <= max_len else text[:max_len - 3] + "..."


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()
