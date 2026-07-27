"""Project registry lookup, worktree resolution, and routable-issue selection.

Purpose
    Answer two questions and nothing else: *which project am I acting for* and
    *which of its open issues may I route*. Dispatch lives in ``handlers``.

Inputs
    ``registry/projects.json`` and ``registry/state.json``, plus live GitHub
    issue listings fetched through the ``gh`` CLI.

Outputs
    Project dictionaries and lists of issue dictionaries carrying an added
    ``watchdog_action`` key naming the handler that claims them.

Failure modes
    - ``find_project`` raises ``ValueError`` naming every registered project id,
      so a typo produces a usable error instead of ``unknown project_id: x``.
    - ``list_routable_issues`` raises ``RuntimeError`` when ``gh`` fails. A
      failed scan must never be reported as "no work to do".
    - Issues labelled ``agent-active`` or ``agent-blocked`` are skipped so a cron
      firing every minute cannot retry a failed ticket without a human decision.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import config
from .core import log_event, run_cmd


def find_project(projects: dict[str, Any], project_id: str) -> dict[str, Any]:
    """Return the registered project entry, or raise listing the valid ids."""
    entries = projects.get("projects", [])
    for project in entries:
        if project.get("project_id") == project_id:
            return project
    known = sorted(str(entry.get("project_id")) for entry in entries)
    raise ValueError(
        f"unknown project_id: {project_id!r}. "
        f"Registered ids: {', '.join(known) or '(none)'}. "
        f"Add an entry to {config.PROJECTS_PATH} to register a new project."
    )


def project_repo(project: dict[str, Any]) -> str:
    """Return the ``owner/name`` GitHub slug for a registered project."""
    repo = project.get("repo")
    if not repo:
        raise ValueError(
            f"project {project.get('project_id')!r} has no 'repo' field; "
            "the watchdog cannot address GitHub without one"
        )
    return str(repo)


def project_worktree(project: dict[str, Any]) -> Path:
    """Return the absolute worktree path for a registered project."""
    raw = project.get("worktree")
    if not raw:
        return config.workspace_root() / str(project.get("project_id"))
    return Path(str(raw)).expanduser()


def list_routable_issues(run_id: str, project: dict[str, Any]) -> list[dict[str, Any]]:
    """Return open issues this watchdog is permitted to route, in listing order."""
    repo = project_repo(project)
    command = [
        "gh",
        "issue",
        "list",
        "--repo",
        repo,
        "--state",
        "open",
        "--label",
        config.READY_LABEL,
        "--limit",
        "50",
        "--json",
        "number,title,body,labels,url",
    ]
    result = run_cmd(command, timeout_s=60)
    log_event(run_id, "github_issue_scan", repo=repo, exit_code=result["exit_code"])
    if result["exit_code"] != 0:
        raise RuntimeError(f"gh issue list failed for {repo}: {result['stderr']}")
    issues = json.loads(result["stdout"] or "[]")
    routable: list[dict[str, Any]] = []
    for issue in issues:
        action = classify_issue(issue)
        if action is None:
            continue
        issue["watchdog_action"] = action
        routable.append(issue)
    return routable


def classify_issue(issue: dict[str, Any]) -> str | None:
    """Return the handler name that claims this issue, or ``None`` to skip it."""
    labels = {label.get("name") for label in issue.get("labels", [])}
    if config.LEASE_LABEL in labels or config.BLOCKED_LABEL in labels:
        return None
    body = issue.get("body") or ""
    if "next:coder" in labels and "executor:local" in labels and config.TAU_REPAIR_MARKER in body:
        return "add_tau_coder_command_spec"
    if "executor:local" in labels and config.TAU_HANDOFF_DISPATCH_MARKER in body:
        return "tau_handoff_dispatch"
    return None
