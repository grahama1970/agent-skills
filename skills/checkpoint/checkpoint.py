"""Session checkpoint — 50% deterministic (git), 50% human/agent.

v6: Git provides the WHAT (files changed, commits, test results, branch state).
Human provides the WHY (grade, resume instruction). Agent provides topic + failures.
No more agent-authored summaries or self-reported file lists.

Resume outputs a structured plain-text briefing to stdout that survives /clear.
Rich panel goes to stderr for human display. The stdout briefing is what the
agent actually sees when the user runs `! .pi/skills/checkpoint/run.sh resume`
after /clear — it contains everything the agent needs to continue work.

Workflow:
  End of session:  /checkpoint save -t "topic" --grade clean --resume "read X, do Y"
  Free context:    /clear
  Resume:          ! .pi/skills/checkpoint/run.sh resume
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
    """Query checkpoints by recency using /list with scope filter.

    /recall uses BM25 ranking (not time-sorted), so we use /list with
    filters for recency-based queries like 'last' and 'list'.
    /list sort order is unreliable, so we fetch all and sort client-side
    by updated_at descending. Checkpoint counts per scope are small (<100).
    """
    filters: dict = {}
    if scope:
        filters["scope"] = scope

    payload: dict = {
        "collection": "checkpoints",
        "limit": 200,  # fetch all, sort client-side
    }
    if filters:
        payload["filters"] = filters
    result = memory_post("/list", payload, console=console)
    docs = result.get("documents", [])
    # Filter to actual checkpoint docs (have checkpoint_version field)
    docs = [d for d in docs if d.get("checkpoint_version")]
    # Sort by updated_at descending (newest first)
    docs.sort(key=lambda d: d.get("updated_at", 0), reverse=True)
    return docs[:limit]


def _recall_with_scope_fallback(query: str, scope: str, limit: int, extra_tags: list[str] | None = None) -> list[dict]:
    tags = ["checkpoint"] + (extra_tags or [])
    # Try BM25 recall with scope
    result = memory_post("/recall", {
        "q": query, "scope": scope, "k": limit, "tags": tags,
        "prefix": CHECKPOINT_PREFIX, "collections": ["checkpoints"],
    }, console=console)
    items = result.get("items", [])
    if items:
        return _parse_checkpoint_items(items)

    # Try BM25 recall without scope
    result_all = memory_post("/recall", {
        "q": query, "k": limit, "tags": tags,
        "prefix": CHECKPOINT_PREFIX, "collections": ["checkpoints"],
    }, console=console)
    items_all = result_all.get("items", [])
    if items_all:
        return _parse_checkpoint_items(items_all)

    # BM25 index may lag after fresh save — fall back to /list with client-side
    # topic filter. This ensures resume works immediately after save.
    logger.warning("BM25 recall returned 0 items, falling back to /list scan")
    all_docs = _query_checkpoints_by_time(limit=50, scope=scope)
    if not all_docs:
        all_docs = _query_checkpoints_by_time(limit=50, scope="")
    # Client-side topic filter: check if query terms appear in topic/resume
    query_lower = query.lower().replace(CHECKPOINT_PREFIX.lower(), "").strip()
    matched = []
    for doc in all_docs:
        haystack = f"{doc.get('topic', '')} {doc.get('resume', '')}".lower()
        if any(term in haystack for term in query_lower.split() if len(term) > 2):
            matched.append(doc)
    return _parse_checkpoint_items(matched[:limit]) if matched else _parse_checkpoint_items(all_docs[:limit])


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
    session_name: Optional[str] = typer.Option(None, "--session", "-s", help="Session name (e.g., sparta, bugs). Used for multi-terminal resume."),
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

    # Session name is optional but enables multi-terminal resume.
    # User says: /checkpoint save -s sparta ...
    # Later:     /checkpoint resume -s sparta (or: "resume sparta" after /clear)

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
    }, console=console, retries=2)
    checkpoint_key = result.get("_key", "") if isinstance(result, dict) else ""
    actual_id = result.get("_id", "") if isinstance(result, dict) else ""

    # Write verification — confirm the doc landed in checkpoints, not lessons_v2
    if actual_id and not actual_id.startswith("checkpoints/"):
        logger.error("Checkpoint stored in WRONG collection: _id={}", actual_id)
        if console:
            console.print(f"[red bold]BUG: checkpoint landed in {actual_id.split('/')[0]} instead of checkpoints[/red bold]")
    elif checkpoint_key:
        # Read-back verification
        verify = memory_post("/recall/by-keys", {
            "keys": [checkpoint_key],
            "collection": "checkpoints",
        }, console=None)
        verify_docs = verify.get("documents", [])
        if not verify_docs:
            logger.error("Checkpoint write verification FAILED: _key={} not found in checkpoints collection", checkpoint_key)
            if console:
                console.print(f"[red bold]BUG: checkpoint _key={checkpoint_key} written but not found on read-back[/red bold]")
        else:
            logger.info("Checkpoint verified in checkpoints collection: _key={}", checkpoint_key)

    # Skill chain storage — links checkpoint → skill_chain via edge
    # Also store the chain directly in the checkpoint doc for resume display
    if skills:
        chain = [s.lstrip("/") for s in skills if s.strip()]
        store_skill_chain(
            topic=topic, summary=resume_instruction, decisions=[],
            scope=scope_val, outcome=outcome,
            explicit_skills=skills, console=console,
            checkpoint_key=checkpoint_key,
        )
        # Write skill_chain into the checkpoint document itself
        if chain and checkpoint_key:
            memory_post("/store", {
                "document": {
                    "_key": checkpoint_key,
                    "skill_chain": chain,
                },
                "collection": "checkpoints",
            }, console=None, retries=2)

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

    # Emit deterministic resume command — user pastes this after /clear
    resume_args = f" -s {session_name}" if session_name else ""
    console.print()
    console.print("[bold yellow]To free context:[/bold yellow]")
    console.print(f"  1. [bold]/clear[/bold]")
    console.print(f"  2. [bold cyan]/checkpoint resume{resume_args}[/bold cyan]")
    # Also print to stdout so the agent sees it
    print(f"\nRESUME_CMD: /checkpoint resume{resume_args}")


def _find_plan_context(root: str) -> dict | None:
    """Find the most recent plan file and return its contents.

    Checks session-specific plans first (plan-{session_id}.json),
    then falls back to the shared plan.json.
    """
    plans_dir = os.path.join(root, ".claude", "plans")
    if os.path.isdir(plans_dir):
        # Find the most recently modified plan file
        plan_files = []
        for f in os.listdir(plans_dir):
            if f.startswith("plan-") and f.endswith(".json"):
                full = os.path.join(plans_dir, f)
                plan_files.append((os.path.getmtime(full), full))
        if plan_files:
            plan_files.sort(reverse=True)
            plan_path = plan_files[0][1]
            try:
                data = json.loads(open(plan_path).read())
                data["_plan_file"] = plan_path
                return data
            except (json.JSONDecodeError, OSError):
                pass

    # Fallback: shared plan.json
    shared = os.path.join(root, ".claude", "plan.json")
    if os.path.isfile(shared):
        try:
            data = json.loads(open(shared).read())
            data["_plan_file"] = shared
            return data
        except (json.JSONDecodeError, OSError):
            pass
    return None


def _recent_commit_details(root: str, since_tag: str, limit: int = 5) -> list[dict]:
    """Get detailed commit info (hash, subject, files) for recent commits.

    More useful than one-line summaries — the agent needs to see what files
    each commit touched to understand the work done.
    """
    if since_tag:
        log_range = f"{since_tag}..HEAD"
    else:
        log_range = f"-{limit}"

    # Get commits with files changed
    raw = git(["log", log_range, f"--max-count={limit}",
               "--format=%h|%s", "--name-only"], cwd=root)
    if not raw:
        return []

    results = []
    current: dict | None = None
    for line in raw.splitlines():
        if "|" in line and not line.startswith(" "):
            # Commit line: hash|subject
            if current:
                results.append(current)
            parts = line.split("|", 1)
            current = {"hash": parts[0], "subject": parts[1], "files": []}
        elif line.strip() and current is not None:
            current["files"].append(line.strip())
    if current:
        results.append(current)

    return results


@app.command()
def resume(
    session_name: Optional[str] = typer.Option(None, "--session", "-s", help="Session name (e.g., sparta, bugs)"),
    topic: Optional[str] = typer.Option(None, "--topic", "-t", help="Search by topic (default: latest)"),
    scope: Optional[str] = typer.Option(None, "--scope", help="Memory scope filter"),
    output_json: bool = typer.Option(False, "--json", is_flag=True, help="Output as JSON"),
) -> None:
    """Resume after /clear. Provides full working context for the next agent.

    Deterministic: branch, dirty files, commits since checkpoint, file diffs, plan.
    Human-authored: resume instruction, failures to avoid.

    With -s/--session, resumes that specific session. Without, resumes latest.
    """
    scope_val = scope or default_workspace_scope()
    root = detect_project_root()

    extra_tags = [f"session:{session_name}"] if session_name else []

    # Fetch last checkpoint from ArangoDB
    # Always use /list (reliable, no BM25 index lag) with client-side topic filter
    all_items = _query_checkpoints_by_time_with_fallback(limit=200, scope=scope_val, extra_tags=extra_tags)
    if topic:
        topic_lower = topic.lower()
        terms = [t for t in topic_lower.split() if len(t) > 2]
        matched = [d for d in all_items if any(
            t in f"{d.get('topic', '')} {d.get('resume', '')}".lower() for t in terms
        )]
        checkpoints = _parse_checkpoint_items(matched[:1]) if matched else _parse_checkpoint_items(all_items[:1])
    else:
        checkpoints = _parse_checkpoint_items(all_items[:1]) if all_items else []

    # Live git state (deterministic — current truth)
    preflight = _git_preflight(root)
    last_tag = _last_checkpoint_tag(root)
    since = _git_since_tag(root, last_tag)

    # === PLAN FILE: session-specific working context ===
    plan_context = _find_plan_context(root)

    # === DETAILED DIFFS: what actually changed in recent commits ===
    recent_diffs = _recent_commit_details(root, last_tag, limit=5)

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
            "plan": plan_context,
            "recent_diffs": recent_diffs,
            "prior_solutions": prior_solutions,
            "recommended_chains": recommended_chains,
        }
        print(json.dumps(slim, indent=2))
        return

    # === RENDER ===
    lines = []

    # Section 1: Human-authored context (THE MOST IMPORTANT PART — show first)
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

        if cp.get("skill_chain"):
            chain_str = " → ".join(f"/{s}" for s in cp["skill_chain"])
            lines.append(f"\n[bold cyan]>>> USE THIS CHAIN:[/bold cyan] {chain_str}")
        elif cp.get("skills_used"):
            lines.append(f"\n[bold]Skills used:[/bold] {', '.join('/' + s for s in cp['skills_used'])}")

        # Show files from the STORED checkpoint (frozen at save time)
        cp_since = cp.get("since_last_checkpoint", {})
        cp_files = cp_since.get("files_changed", [])
        cp_commits = cp_since.get("commits", [])
        if cp_files:
            lines.append(f"\n[bold]FILES TOUCHED IN THAT SESSION ({len(cp_files)}):[/bold]")
            for f in cp_files[:15]:
                lines.append(f"  - {f}")
            if len(cp_files) > 15:
                lines.append(f"  [dim]... and {len(cp_files) - 15} more[/dim]")
        if cp_commits:
            lines.append(f"\n[bold]COMMITS IN THAT SESSION ({len(cp_commits)}):[/bold]")
            for c in cp_commits[:10]:
                lines.append(f"  [dim]{c}[/dim]")

        lines.append(f"\n[dim]Saved: {cp.get('timestamp', '?')}[/dim]")
    else:
        lines.append("[yellow]No previous checkpoint found.[/yellow]")

    # Section 2: Plan file (working context from last session)
    if plan_context:
        lines.append("")
        lines.append("[bold]ACTIVE PLAN:[/bold]")
        lines.append(f"  [bold]Task:[/bold] {plan_context.get('task', '?')}")
        target_files = plan_context.get("target_files", [])
        if target_files:
            lines.append(f"  [bold]Target files:[/bold]")
            for tf in target_files[:10]:
                lines.append(f"    - {tf}")
        skills_sel = plan_context.get("skills_selected", [])
        if skills_sel:
            lines.append(f"  [bold]Skills:[/bold] {', '.join('/' + s for s in skills_sel)}")
        plan_file = plan_context.get("_plan_file", "")
        if plan_file:
            lines.append(f"  [dim]Plan file: {plan_file}[/dim]")

    # Section 3: Git state (deterministic)
    lines.append("")
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

    # Section 4: What changed since last checkpoint — with details
    if last_tag:
        lines.append("")
        lines.append(f"[bold]SINCE {last_tag}:[/bold]")
        lines.append(f"  {since['commit_count']} commits, {len(since['files_changed'])} files changed")

    if recent_diffs:
        lines.append("")
        lines.append("[bold]RECENT COMMITS (read these to understand prior work):[/bold]")
        for rd in recent_diffs:
            lines.append(f"  [cyan]{rd['hash']}[/cyan] {rd['subject']}")
            if rd.get("files"):
                for f in rd["files"][:5]:
                    lines.append(f"    {f}")

    # Section 5: Files changed — the agent should READ these
    if since.get("files_changed"):
        lines.append("")
        lines.append("[bold]FILES TO READ (changed since last checkpoint):[/bold]")
        for f in since["files_changed"][:20]:
            lines.append(f"  - {f}")

    # Section 6: Prior solutions
    if prior_solutions:
        lines.append("")
        lines.append("[bold]PRIOR SOLUTIONS:[/bold]")
        for ps in prior_solutions[:3]:
            lines.append(f"  [dim]{ps['problem']}[/dim]")
            lines.append(f"    → {ps['solution']}")

    # Section 7: Recommended skill chains
    if recommended_chains:
        lines.append("")
        lines.append("[bold]RECOMMENDED SKILL CHAINS:[/bold]")
        for rc in recommended_chains[:3]:
            chain_str = " → ".join(f"/{s}" for s in rc["chain"])
            lines.append(f"  [cyan]{chain_str}[/cyan]")
            if rc.get("task"):
                lines.append(f"    [dim]{rc['task']}[/dim]")

    console.print(Panel("\n".join(lines), title="RESUME", border_style="cyan"))

    # === STDOUT BRIEFING: agent-readable plain text for post-/clear resume ===
    # After /clear all Rich output is gone. This stdout block is what the agent
    # actually sees when the user pastes `! .pi/skills/checkpoint/run.sh resume`.
    briefing_parts: list[str] = ["--- CHECKPOINT RESUME BRIEFING ---"]
    briefing_parts.append(f"BRANCH: {preflight['branch']}")
    if checkpoints:
        cp = checkpoints[0]
        briefing_parts.append(f"TOPIC: {cp.get('topic', '?')}")
        briefing_parts.append(f"GRADE: {cp.get('grade', '?').upper()}")
        resume_text = cp.get("resume", "")
        if resume_text:
            briefing_parts.append(f"\nDO THIS NEXT:\n  {resume_text}")
        cp_failures = cp.get("failures", [])
        if cp_failures:
            briefing_parts.append("\nDON'T REPEAT:")
            for f in cp_failures:
                briefing_parts.append(f"  - {f}")
        if cp.get("skills_used"):
            briefing_parts.append(f"\nSKILLS USED: {', '.join('/' + s for s in cp['skills_used'])}")
    else:
        briefing_parts.append("No previous checkpoint found.")

    briefing_parts.append(f"\nGIT: {preflight['branch']} @ {preflight['commit']}")
    if preflight["dirty_count"] > 0:
        briefing_parts.append(f"DIRTY: {preflight['dirty_count']} uncommitted files")
    if last_tag and since.get("files_changed"):
        briefing_parts.append(f"CHANGED SINCE {last_tag}: {len(since['files_changed'])} files")
        for f in since["files_changed"][:10]:
            briefing_parts.append(f"  - {f}")

    if plan_context:
        briefing_parts.append(f"\nACTIVE PLAN: {plan_context.get('task', '?')}")
        target_files = plan_context.get("target_files", [])
        if target_files:
            for tf in target_files[:5]:
                briefing_parts.append(f"  - {tf}")

    briefing_parts.append("--- END BRIEFING ---")
    print("\n".join(briefing_parts))


@app.command()
def recall(
    topic: Optional[str] = typer.Option(None, "--topic", "-t", help="Topic to search for"),
    scope: Optional[str] = typer.Option(None, "--scope", help="Memory scope filter"),
    limit: int = typer.Option(3, "--limit", "-k", help="Max results"),
    output_json: bool = typer.Option(False, "--json", is_flag=True, help="Output as JSON"),
) -> None:
    """Search checkpoints by topic."""
    scope_val = scope or default_workspace_scope()
    # Primary: /list + client-side filter (reliable, no BM25 index lag)
    all_docs = _query_checkpoints_by_time(limit=200, scope=scope_val)
    if not all_docs:
        all_docs = _query_checkpoints_by_time(limit=200, scope="")
    if topic:
        topic_lower = topic.lower()
        terms = [t for t in topic_lower.split() if len(t) > 2]
        matched = [d for d in all_docs if any(
            t in f"{d.get('topic', '')} {d.get('resume', '')}".lower() for t in terms
        )]
        checkpoints = _parse_checkpoint_items(matched[:limit]) if matched else _parse_checkpoint_items(all_docs[:limit])
    else:
        checkpoints = _parse_checkpoint_items(all_docs[:limit])

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
    table.add_column("Session", style="magenta", width=10)
    table.add_column("Topic", style="bold", max_width=30)
    table.add_column("Grade", width=12)
    table.add_column("Branch", style="cyan", width=15)
    table.add_column("Time", style="green", width=19)

    for i, cp in enumerate(checkpoints, 1):
        grade = cp.get("grade", "?")
        gc = {"unresolved": "red", "workaround": "yellow", "solved": "bright_yellow",
              "clean": "green", "reusable": "blue"}.get(grade, "white")
        # Extract session from tags
        session = ""
        for tag in (cp.get("tags") or []):
            if isinstance(tag, str) and tag.startswith("session:"):
                session = tag[8:]
                break
        if not session:
            session = cp.get("session", "")
        table.add_row(
            str(i),
            session or "-",
            _truncate(cp.get("topic", "?"), 30),
            f"[{gc}]{grade}[/{gc}]",
            cp.get("git", {}).get("branch", "?"),
            cp.get("timestamp", "?")[:19],
        )
    console.print(table)


@app.command()
def rewind(
    key: Optional[str] = typer.Option(None, "--key", "-k", help="Checkpoint _key to rewind to"),
    limit: int = typer.Option(10, "--limit", "-n", help="Number of checkpoints to show"),
    scope: Optional[str] = typer.Option(None, "--scope", help="Memory scope filter"),
    output_json: bool = typer.Option(False, "--json", is_flag=True, help="Output as JSON"),
) -> None:
    """Rewind git state to a saved checkpoint.

    Without --key: list recent checkpoints with index numbers.
    With --key: stash current changes, checkout that commit, print resume.
    """
    scope_val = scope or default_workspace_scope()
    root = detect_project_root()

    if not key:
        # List mode — show checkpoints with _key so user can pick
        items = _query_checkpoints_by_time_with_fallback(limit=limit, scope=scope_val)
        checkpoints = _parse_checkpoint_items(items)

        if output_json:
            print(json.dumps(checkpoints, indent=2))
            return

        if not checkpoints:
            console.print("[yellow]No checkpoints found.[/yellow]")
            return

        table = Table(title="Rewind — pick a checkpoint", show_lines=True)
        table.add_column("#", style="dim", width=3)
        table.add_column("Topic", style="bold", max_width=40)
        table.add_column("Grade", width=12)
        table.add_column("Date", style="green", width=19)
        table.add_column("Key", style="dim cyan", width=14)

        for i, cp in enumerate(checkpoints, 1):
            grade = cp.get("grade", "?")
            gc = {"unresolved": "red", "workaround": "yellow", "solved": "bright_yellow",
                  "clean": "green", "reusable": "blue"}.get(grade, "white")
            table.add_row(
                str(i),
                _truncate(cp.get("topic", "?"), 40),
                f"[{gc}]{grade}[/{gc}]",
                cp.get("timestamp", "?")[:19],
                cp.get("_key", "?"),
            )
        console.print(table)
        console.print("\n[dim]Usage: ./run.sh rewind --key <key>[/dim]")
        return

    # Rewind mode — checkout the checkpoint's commit
    # Fetch the checkpoint doc
    result = memory_post("/recall/by-keys", {
        "collection": "checkpoints",
        "keys": [key],
    }, console=console)
    docs = result.get("documents", [])
    if not docs:
        console.print(f"[red]Checkpoint {key} not found.[/red]")
        raise typer.Exit(1)

    cp = docs[0]
    commit = cp.get("git", {}).get("commit", "")
    if not commit:
        console.print(f"[red]Checkpoint {key} has no commit hash stored.[/red]")
        raise typer.Exit(1)

    # Verify commit exists in this repo
    check = git(["cat-file", "-t", commit], cwd=root)
    if not check or "commit" not in check:
        console.print(f"[red]Commit {commit} not found in this repo.[/red]")
        raise typer.Exit(1)

    # Stash if dirty
    status = git(["status", "--porcelain"], cwd=root)
    stashed = False
    if status and status.strip():
        console.print("[yellow]Stashing uncommitted changes...[/yellow]")
        git_exec(["stash", "push", "-m", f"rewind-to-{key}"], cwd=root)
        stashed = True

    # Checkout the commit (detached HEAD)
    git_exec(["checkout", commit], cwd=root)

    topic = cp.get("topic", "?")
    console.print(f"\n[bold green]Rewound to checkpoint {key}[/bold green]")
    console.print(f"  Topic:  {topic}")
    console.print(f"  Commit: {commit}")
    console.print(f"  Date:   {cp.get('timestamp', '?')[:19]}")
    if stashed:
        console.print("[yellow]  Previous changes stashed (git stash pop to restore)[/yellow]")

    # Print resume context
    resume_text = cp.get("resume", "")
    if resume_text:
        console.print(f"\n[bold]Resume:[/bold] {resume_text}")

    skill_chain = cp.get("skill_chain")
    if skill_chain and isinstance(skill_chain, list):
        chain_str = " → ".join(f"/{s}" for s in skill_chain)
        console.print(f"[bold cyan]Chain:[/bold cyan] {chain_str}")

    console.print(f"\n[dim]HEAD is detached. Create a branch: git checkout -b rewind/{key}[/dim]")


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
        # Detect by _source field (from /recall) or checkpoint_version (from /list)
        if source == "checkpoints" or item.get("checkpoint_version"):
            # solution_doc was stored as a nested dict; parse if JSON string
            # Legacy lessons_v2 items returned via /recall with _source=checkpoints
            # store checkpoint data in 'playbook', not 'solution'
            sol = item.get("solution", "") or item.get("playbook", "")
            if isinstance(sol, str):
                # Strip YAML list prefix "- " that /store adds to playbook
                stripped = sol.lstrip("- ").strip()
                if stripped.startswith("{"):
                    try:
                        sol = json.loads(stripped)
                    except (json.JSONDecodeError, TypeError):
                        sol = {}
                else:
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

        # Legacy format: lessons_v2 — checkpoint data in JSON 'solution' or 'playbook' field
        solution = item.get("solution", "") or item.get("playbook", "")
        parsed = {}
        if solution:
            # Strip YAML list prefix "- " that /store adds to playbook
            stripped = solution.lstrip("- ").strip() if isinstance(solution, str) else solution
            try:
                parsed = json.loads(stripped)
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
