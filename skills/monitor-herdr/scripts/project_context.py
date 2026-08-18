"""Resolve repo, branch, skill, and open tickets before the monitor nudges.

A stalled agent should not have to rediscover where it is. The monitor already
knows the pane's cwd, so it resolves the repo, branch, owning skill, and that
skill's open tickets up front and states them in the nudge. Everything here is
fail-soft: context is an aid to the prompt, never a gate on supervision, so any
failure degrades to less context rather than a skipped tick.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from loguru import logger

TICKET_CACHE_TTL_SECONDS = 15 * 60
DEFAULT_TICKET_LIMIT = 5
GIT_TIMEOUT_SECONDS = 5
GH_TIMEOUT_SECONDS = 20


def resolve_project_context(
    cwd: str,
    project_root: Path | None,
    *,
    cache_path: Path | None = None,
    ticket_limit: int = DEFAULT_TICKET_LIMIT,
    include_tickets: bool = True,
    now: float | None = None,
) -> dict[str, Any]:
    """Best-effort identity of the work in a pane, for use in the nudge prompt."""
    context: dict[str, Any] = {
        "project_root": str(project_root) if project_root else None,
        "repo": None,
        "branch": None,
        "skill": None,
        "open_tickets": [],
        "tickets_source": "not_requested",
    }
    if project_root is None:
        return context

    context["repo"] = git_repo_slug(project_root)
    context["branch"] = git_branch(project_root)
    context["skill"] = skill_for_cwd(cwd, project_root)

    if not include_tickets or not context["repo"]:
        context["tickets_source"] = "unavailable" if include_tickets else "not_requested"
        return context

    tickets, source = open_tickets(
        context["repo"],
        skill=context["skill"],
        cache_path=cache_path,
        limit=ticket_limit,
        now=now,
    )
    context["open_tickets"] = tickets
    context["tickets_source"] = source
    return context


def git_repo_slug(project_root: Path) -> str | None:
    """Return `owner/name` from the origin remote, or None."""
    url = run_git(["config", "--get", "remote.origin.url"], project_root)
    if not url:
        return None
    match = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?$", url.strip())
    return match.group(1) if match else None


def git_branch(project_root: Path) -> str | None:
    return run_git(["branch", "--show-current"], project_root) or None


def run_git(args: list[str], project_root: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.error("git {} failed in {}: {}", " ".join(args), project_root, exc)
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def skill_for_cwd(cwd: str, project_root: Path) -> str | None:
    """Return the skill name when the pane is working inside `skills/<name>/`."""
    if not cwd:
        return None
    try:
        current = Path(cwd).expanduser().resolve()
        root = project_root.resolve()
    except OSError:
        return None
    if not current.is_relative_to(root):
        return None
    parts = current.relative_to(root).parts
    for index, part in enumerate(parts):
        if part == "skills" and index + 1 < len(parts):
            return parts[index + 1]
    return None


def open_tickets(
    repo: str,
    *,
    skill: str | None,
    cache_path: Path | None,
    limit: int,
    now: float | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Open GitHub issues for this repo, narrowed to the skill when known."""
    now = time.time() if now is None else now
    cache_key = f"{repo}::{skill or '*'}::{limit}"
    cached = read_ticket_cache(cache_path, cache_key, now=now)
    if cached is not None:
        return cached, "cache"

    args = [
        "gh", "issue", "list",
        "--repo", repo,
        "--state", "open",
        "--limit", str(limit),
        "--json", "number,title,url",
    ]
    if skill:
        args += ["--search", skill]
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=GH_TIMEOUT_SECONDS, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        logger.error("gh issue list failed for {}: {}", repo, exc)
        return [], "unavailable"
    if proc.returncode != 0:
        logger.error("gh issue list returned {} for {}", proc.returncode, repo)
        return [], "unavailable"
    try:
        payload = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        logger.error("gh issue list emitted non-JSON for {}", repo)
        return [], "unavailable"

    tickets = [
        {"number": item.get("number"), "title": str(item.get("title") or "")[:120], "url": item.get("url")}
        for item in payload
        if isinstance(item, dict) and item.get("number")
    ][:limit]
    write_ticket_cache(cache_path, cache_key, tickets, now=now)
    return tickets, "gh"


def read_ticket_cache(cache_path: Path | None, key: str, *, now: float) -> list[dict[str, Any]] | None:
    if cache_path is None or not cache_path.exists():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    entry = payload.get(key) if isinstance(payload, dict) else None
    if not isinstance(entry, dict):
        return None
    if now - float(entry.get("fetched_at", 0) or 0) > TICKET_CACHE_TTL_SECONDS:
        return None
    tickets = entry.get("tickets")
    return tickets if isinstance(tickets, list) else None


def write_ticket_cache(cache_path: Path | None, key: str, tickets: list[dict[str, Any]], *, now: float) -> None:
    if cache_path is None:
        return
    payload: dict[str, Any] = {}
    if cache_path.exists():
        try:
            existing = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                payload = existing
        except (OSError, json.JSONDecodeError):
            payload = {}
    payload[key] = {"fetched_at": now, "tickets": tickets}
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    except OSError as exc:
        logger.error("Could not write ticket cache {}: {}", cache_path, exc)


def context_lines(context: dict[str, Any]) -> list[str]:
    """Render resolved context as prompt lines the stalled agent can act on."""
    lines: list[str] = []
    if context.get("repo"):
        branch = context.get("branch")
        lines.append(f"Repo: {context['repo']}" + (f" (branch {branch})" if branch else ""))
    if context.get("project_root"):
        lines.append(f"Project root: {context['project_root']}")
    if context.get("skill"):
        lines.append(f"Skill under work: {context['skill']} (skills/{context['skill']}/)")
    tickets = context.get("open_tickets") or []
    if tickets:
        rendered = "; ".join(f"#{item['number']} {item['title']}" for item in tickets if item.get("number"))
        lines.append(f"Open tickets already looked up for you: {rendered}")
    elif context.get("tickets_source") == "gh":
        lines.append("Open tickets already looked up for you: none open for this scope.")
    return lines
