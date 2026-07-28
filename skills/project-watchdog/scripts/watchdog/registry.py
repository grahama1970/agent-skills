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


#: Branches a repair may be authored on. A repair committed onto whatever
#: branch a worktree happens to hold is unattributable, and on a feature branch
#: it never reaches main.
DEFAULT_BRANCHES = ("main", "master")


def worktree_readiness(worktree: Path) -> dict[str, Any]:
    """Report whether a worktree is safe to author a repair in.

    Observed 2026-07-28: the registry pointed ``agent-skills`` at a worktree
    sitting on an unrelated feature branch, 686 commits behind main, with 543
    modified tracked files, while a cron lane wrote tracked files into it every
    few seconds. Dispatching there would author a repair on the wrong branch, on
    top of foreign uncommitted edits, and could corrupt a running job.

    Read-only. Returns the facts; the caller decides.
    """
    row: dict[str, Any] = {"worktree": str(worktree), "exists": worktree.is_dir()}
    if not row["exists"]:
        row["reasons"] = ["worktree_missing"]
        row["ready"] = False
        return row

    def git(*args: str) -> tuple[int, str]:
        result = run_cmd(["git", "-C", str(worktree), *args], timeout_s=30)
        return int(result.get("exit_code", 1)), str(result.get("stdout", "")).strip()

    code, branch = git("branch", "--show-current")
    row["branch"] = branch or "(detached HEAD)"
    if code != 0:
        row["reasons"] = ["not_a_git_worktree"]
        row["ready"] = False
        return row

    _, dirty_out = git("status", "--porcelain", "--untracked-files=no")
    dirty = [line for line in dirty_out.splitlines() if line.strip()]
    row["dirty_tracked"] = len(dirty)
    # porcelain is "XY<space>PATH", but the status field width varies with
    # staged-vs-worktree combinations; a fixed slice truncated the filename.
    row["dirty_paths"] = [line[2:].strip() for line in dirty[:10]]

    _, untracked_out = git("status", "--porcelain")
    row["untracked"] = len([l for l in untracked_out.splitlines() if l.startswith("??")])

    reasons: list[str] = []
    if row["branch"] not in DEFAULT_BRANCHES:
        reasons.append(f"branch_is_not_default:{row['branch']}")
    if dirty:
        reasons.append(f"tracked_files_dirty:{len(dirty)}")
    row["reasons"] = reasons
    row["ready"] = not reasons
    return row


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
    unroutable_no_repair_lane = 0
    has_lane = project_has_repair_lane(project)
    for issue in issues:
        action = classify_issue(issue)
        if action is None:
            continue
        if action == "ticket_repair" and not has_lane:
            # The project exposes no Tau DAG repair lane, so this issue is not
            # routable HERE. Claiming it only to block it leases and blocks a
            # different ticket every tick and exits 1 every minute, which reads
            # as many broken tickets instead of one unconfigured project.
            unroutable_no_repair_lane += 1
            continue
        issue["watchdog_action"] = action
        routable.append(issue)
    if unroutable_no_repair_lane:
        log_event(
            run_id,
            "issues_unroutable_no_repair_lane",
            project_id=project.get("project_id"),
            runner_kind=project.get("runner_kind"),
            count=unroutable_no_repair_lane,
        )
    LAST_SCAN["unroutable_no_repair_lane"] = unroutable_no_repair_lane
    return routable


#: Side-channel for the last scan's non-routable tally, so ``tick`` can report
#: WHY nothing was routable without re-listing.
LAST_SCAN: dict[str, int] = {}


def project_has_repair_lane(project: dict[str, Any]) -> bool:
    """Whether this project can actually run a Tau DAG ticket repair.

    Imported lazily: ``handlers`` imports this module, so a module-level import
    of ``handlers`` here would be circular.
    """
    from .handlers import TICKET_REPAIR_RUNNERS  # noqa: PLC0415

    return str(project.get("runner_kind", "")) in TICKET_REPAIR_RUNNERS


def classify_issue(issue: dict[str, Any]) -> str | None:
    """Return the handler name that claims this issue, or ``None`` to skip it.

    Three routes, checked most-specific first:

    1. ``add_tau_coder_command_spec`` — legacy, needs an explicit body marker.
    2. ``tau_handoff_dispatch`` — legacy, needs an explicit body marker.
    3. ``ticket_repair`` — any ``agent-work`` issue with no marker. This is the
       route ordinary ``/ticket``-filed tickets take.

    Before route 3 existed, an issue had to be hand-authored with a
    ``project-watchdog-action:`` body marker to be routable at all, while
    ``/ticket`` emitted only ``type:*`` and ``route:*``. The two halves of the
    system shared no vocabulary, and the cron logged 41,607 consecutive
    ``no_routable_issues`` ticks over roughly a month as a result.
    """
    labels = {label.get("name") for label in issue.get("labels", [])}

    # Never routable: already leased by any agent, human-blocked, or parked.
    if labels & {config.BLOCKED_LABEL, *config.LEASE_LABELS, *config.HUMAN_HOLD_LABELS}:
        return None
    if config.READY_LABEL not in labels:
        return None

    body = issue.get("body") or ""
    if "next:coder" in labels and "executor:local" in labels and config.TAU_REPAIR_MARKER in body:
        return "add_tau_coder_command_spec"
    if "executor:local" in labels and config.TAU_HANDOFF_DISPATCH_MARKER in body:
        return "tau_handoff_dispatch"
    return "ticket_repair"
