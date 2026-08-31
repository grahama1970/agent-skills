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
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loguru import logger

from . import config, github
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
        f"Add an entry to {config.projects_path()} to register a new project."
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
#: branch a worktree happens to hold is unattributable.
DEFAULT_BRANCHES = ("main", "master")

#: Branch prefix for per-ticket repair worktrees. The lane creates one from
#: origin/main per dispatch, so its branch is not a default branch and is still
#: a legitimate place to author.
REPAIR_BRANCH_PREFIX = "watchdog/issue-"


def remote_main_sha(repo_dir: Path) -> str:
    """The SHA ``origin/main`` currently points at, or "" if it cannot be read.

    Used to detect a repair seat pushing straight to main instead of leaving the
    decision to the reviewer.
    """
    result = run_cmd(["git", "-C", str(repo_dir), "ls-remote", "origin", "refs/heads/main"],
                     timeout_s=60)
    if result.get("exit_code") != 0:
        return ""
    out = str(result.get("stdout", "")).split()
    return out[0] if out else ""


def prepare_repair_worktree(repo_dir: Path, worktree: Path, issue_number: int) -> dict[str, Any]:
    """Create a clean worktree from ``origin/main`` to author one repair in.

    Isolation, not convenience. The registered checkout is a human's working
    tree; authoring there builds on whatever it happens to hold and risks
    clobbering uncommitted work. A fresh worktree off the fetched origin/main is
    clean by construction and current by construction.

    Returns the git commands run and the resolved branch, or an ``error``.
    """
    branch = f"{REPAIR_BRANCH_PREFIX}{issue_number}"
    steps: list[dict[str, Any]] = []

    def git(*args: str, cwd: Path) -> dict[str, Any]:
        result = run_cmd(["git", "-C", str(cwd), *args], timeout_s=120)
        steps.append({"argv": ["git", *args], "exit_code": result.get("exit_code")})
        return result

    # A leftover worktree from an earlier attempt may hold a finished repair
    # that nobody has merged yet. `worktree add -B` resets the branch to
    # origin/main, so removing and re-adding blindly DESTROYS that work --
    # observed on watchdog-probe#1: codex committed 9feb862, a later dispatch
    # reset the branch, and the commit was left unreferenced.
    if worktree.exists():
        result = run_cmd(
            ["git", "-C", str(worktree), "log", "--oneline", "origin/main..HEAD"],
            timeout_s=60,
        )
        unmerged = [ln for ln in str(result.get("stdout", "")).splitlines() if ln.strip()]
        if unmerged:
            return {
                "ok": False,
                "error": (
                    f"{worktree} already holds {len(unmerged)} unmerged commit(s) on "
                    f"{branch} ({unmerged[0]}). Refusing to reset it and lose that work: "
                    f"merge or delete the branch first."
                ),
                "unmerged": unmerged,
                "steps": steps,
            }
        git("worktree", "remove", "--force", str(worktree), cwd=repo_dir)
    git("worktree", "prune", cwd=repo_dir)

    fetched = git("fetch", "origin", "main", cwd=repo_dir)
    if fetched.get("exit_code") != 0:
        return {"ok": False, "error": f"fetch failed: {fetched.get('stderr')}", "steps": steps}

    worktree.parent.mkdir(parents=True, exist_ok=True)
    added = git("worktree", "add", "-B", branch, str(worktree), "origin/main", cwd=repo_dir)
    if added.get("returncode") == 0:
        # Register the lease at creation. The watchdog owns 58 of this repo's
        # worktrees and has never removed one; without an owner recorded here
        # the reaper can only report them, never reclaim them.
        _register_worktree_lease(worktree, purpose=f"watchdog:{branch}")
    if added.get("exit_code") != 0:
        return {"ok": False, "error": f"worktree add failed: {added.get('stderr')}", "steps": steps}
    return {"ok": True, "branch": branch, "worktree": str(worktree), "steps": steps}


def worktree_readiness(worktree: Path, targets: set[str] | None = None) -> dict[str, Any]:
    """Report whether a worktree is safe to author a repair in.

    Observed 2026-07-28: the registry pointed ``agent-skills`` at a worktree
    sitting on an unrelated feature branch, 686 commits behind main, with 543
    modified tracked files, while a cron lane wrote tracked files into it every
    few seconds. Dispatching there would author a repair on the wrong branch, on
    top of foreign uncommitted edits, and could corrupt a running job.

    Dirtiness is judged against ``targets`` when given, not the whole tree. In
    agent-skills 111 of 364 skills are dirty; requiring the repository to be
    clean withheld the 253 that are not. A repair confined to a clean skill is
    not endangered by unrelated edits elsewhere -- and a skill a cron lane is
    actively writing shows up dirty, so this still refuses exactly that case.

    The branch check stays global: a repair authored on a feature branch never
    reaches main regardless of which paths it touches.

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

    scope = sorted(t for t in (targets or set()) if t and t != UNKNOWN_TARGET)
    row["scope"] = scope or ["<whole worktree>"]

    # `git status -- <path>...` restricts the report to those paths. With no
    # scope this is the previous whole-tree behaviour.
    _, dirty_out = git("status", "--porcelain", "--untracked-files=no", "--", *scope)
    dirty = [line for line in dirty_out.splitlines() if line.strip()]
    row["dirty_tracked"] = len(dirty)
    # porcelain is "XY<space>PATH", but the status field width varies with
    # staged-vs-worktree combinations; a fixed slice truncated the filename.
    row["dirty_paths"] = [line[2:].strip() for line in dirty[:10]]

    _, untracked_out = git("status", "--porcelain", "--", *scope)
    row["untracked"] = len([ln for ln in untracked_out.splitlines() if ln.startswith("??")])

    reasons: list[str] = []
    if row["branch"] not in DEFAULT_BRANCHES and not row["branch"].startswith(
        REPAIR_BRANCH_PREFIX
    ):
        reasons.append(f"branch_is_not_default:{row['branch']}")
    if dirty:
        reasons.append(f"tracked_files_dirty:{len(dirty)}")
    row["reasons"] = reasons
    row["ready"] = not reasons
    return row


def list_routable_issues(
    run_id: str,
    project: dict[str, Any],
    busy: set[str] | None = None,
    *,
    skip_issue_numbers: set[int] | None = None,
    skip_issue_reasons: dict[int, str] | None = None,
    only_issue: int | None = None,
    apply: bool = False,
) -> list[dict[str, Any]]:
    """Return open issues this watchdog is permitted to route, in listing order.

    ``busy`` is the set of targets already in flight. A ticket against one of
    them is held back; a ticket against any other target is free to go.
    """
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
    dependency_unblocks: list[dict[str, Any]] = []
    # Every ticket the scan passes over is recorded with its reason, so a tick
    # that dispatches nothing names the tickets it declined and why.
    excluded: dict[str, list[int]] = {}
    has_lane = project_has_repair_lane(project)
    busy_now = set(busy or ())
    skip_now = set(skip_issue_numbers or ())
    skip_reasons = dict(skip_issue_reasons or {})
    for issue in issues:
        issue_number = int(issue["number"])
        if only_issue is not None and issue_number != int(only_issue):
            excluded.setdefault("not_targeted_issue", []).append(issue_number)
            continue
        if issue_number in skip_now:
            reason = skip_reasons.get(issue_number, "lease_reclaimed_this_tick")
            excluded.setdefault(reason, []).append(issue_number)
            continue
        targets = issue_targets(issue)
        if not issue_matches_project_scope(project, targets):
            excluded.setdefault("project_scope_mismatch", []).append(issue_number)
            continue
        dep = dependency_gate(run_id, repo, issue, apply=apply)
        if dep["status"] in {"open", "unreadable", "unblock_failed"}:
            excluded.setdefault(str(dep["reason"]), []).append(issue_number)
            issue["watchdog_dependencies"] = dep
            continue
        if dep["status"] == "unblocked":
            excluded.setdefault(str(dep["reason"]), []).append(issue_number)
            issue["watchdog_dependencies"] = dep
            dependency_unblocks.append({
                "issue_number": issue_number,
                "repo": repo,
                **dep,
            })
            continue
        if dep["status"] == "resolved":
            issue["watchdog_dependencies"] = dep
        action, reason = classify_issue_with_reason(issue)
        if action is None:
            excluded.setdefault(reason or "unknown", []).append(issue_number)
            continue
        if targets_are_blocked(targets, busy_now):
            excluded.setdefault("target_busy", []).append(issue_number)
            continue
        if action == "ticket_repair" and not has_lane:
            # The project exposes no Tau DAG repair lane, so this issue is not
            # routable HERE. Claiming it only to block it leases and blocks a
            # different ticket every tick and exits 1 every minute, which reads
            # as many broken tickets instead of one unconfigured project.
            unroutable_no_repair_lane += 1
            continue
        issue["watchdog_action"] = action
        issue["watchdog_targets"] = sorted(targets)
        # Claim them for the rest of this scan: with max_tickets > 1 two tickets
        # against the same target would otherwise both look free.
        busy_now |= targets
        routable.append(issue)
    if excluded:
        log_event(
            run_id,
            "issues_excluded_from_dispatch",
            project_id=project.get("project_id"),
            repo=repo,
            counts={reason: len(nums) for reason, nums in sorted(excluded.items())},
            issues={reason: nums for reason, nums in sorted(excluded.items())},
        )
    if unroutable_no_repair_lane:
        log_event(
            run_id,
            "issues_unroutable_no_repair_lane",
            project_id=project.get("project_id"),
            runner_kind=project.get("runner_kind"),
            count=unroutable_no_repair_lane,
        )
    LAST_SCAN["unroutable_no_repair_lane"] = unroutable_no_repair_lane
    LAST_SCAN["scanned"] = len(issues)
    LAST_SCAN["excluded"] = {reason: len(nums) for reason, nums in sorted(excluded.items())}
    LAST_SCAN["excluded_issues"] = {reason: nums for reason, nums in sorted(excluded.items())}
    LAST_SCAN["dependency_unblocks"] = dependency_unblocks
    return routable


_GITHUB_REF = re.compile(r"^[^/\s]+/[^#\s]+#[0-9]+$")
_BLOCKED_BY_LINE = re.compile(r"(?im)^\s*(?:[-*]\s*)?blocked-by:\s*(.+?)\s*$")
_DEPENDS_ON_LINE = re.compile(r"(?im)^\s*depends_on:\s*(.+?)\s*$")


def _dependency_refs_from_text(text: str) -> list[str]:
    refs: list[str] = []
    for match in _BLOCKED_BY_LINE.finditer(text or ""):
        refs.extend(part.strip() for part in match.group(1).split(",") if part.strip())
    for match in _DEPENDS_ON_LINE.finditer(text or ""):
        refs.extend(part.strip() for part in match.group(1).split(",") if part.strip())
    seen: set[str] = set()
    ordered: list[str] = []
    for ref in refs:
        if ref not in seen:
            seen.add(ref)
            ordered.append(ref)
    return ordered


def _comment_dependency_refs(run_id: str, repo: str, issue_number: int) -> list[str]:
    result = run_cmd(
        ["gh", "issue", "view", str(issue_number), "--repo", repo, "--json", "comments"],
        timeout_s=60,
    )
    log_event(
        run_id,
        "dependency_comment_scan",
        repo=repo,
        issue=issue_number,
        exit_code=result.get("exit_code"),
    )
    if result.get("exit_code") != 0:
        raise RuntimeError(f"dependency comment scan failed: {result.get('stderr')}")
    payload = json.loads(result.get("stdout") or "{}")
    refs: list[str] = []
    for comment in payload.get("comments", []):
        refs.extend(_dependency_refs_from_text(str(comment.get("body") or "")))
    return refs


def issue_dependency_refs(run_id: str, repo: str, issue: dict[str, Any]) -> list[str]:
    """Machine-readable upstream issue refs declared by ``$ticket``."""
    refs = _dependency_refs_from_text(str(issue.get("body") or ""))
    labels = {str(label.get("name")) for label in issue.get("labels", [])}
    if config.UPSTREAM_BLOCKED_LABEL in labels:
        refs.extend(_comment_dependency_refs(run_id, repo, int(issue["number"])))
    seen: set[str] = set()
    ordered: list[str] = []
    for ref in refs:
        if ref not in seen:
            seen.add(ref)
            ordered.append(ref)
    return ordered


def _upstream_issue_state(run_id: str, ref: str) -> dict[str, Any]:
    if not _GITHUB_REF.match(ref):
        raise RuntimeError(f"malformed dependency reference: {ref}")
    repo, raw_number = ref.split("#", 1)
    result = run_cmd(
        [
            "gh",
            "issue",
            "view",
            raw_number,
            "--repo",
            repo,
            "--json",
            "state,stateReason",
        ],
        timeout_s=60,
    )
    log_event(
        run_id,
        "dependency_issue_state",
        dependency=ref,
        exit_code=result.get("exit_code"),
    )
    if result.get("exit_code") != 0:
        raise RuntimeError(f"dependency state unreadable for {ref}: {result.get('stderr')}")
    payload = json.loads(result.get("stdout") or "{}")
    return {
        "ref": ref,
        "state": str(payload.get("state") or "").upper(),
        "stateReason": str(payload.get("stateReason") or "").upper(),
    }


def _dependency_resolved(row: dict[str, Any]) -> bool:
    if row["state"] != "CLOSED":
        return False
    return row["stateReason"] not in {"NOT_PLANNED", "DUPLICATE"}


def _remove_dependency_hold_labels(issue: dict[str, Any]) -> None:
    labels = [
        label for label in issue.get("labels", [])
        if str(label.get("name")) not in config.DEPENDENCY_HOLD_LABELS
    ]
    issue["labels"] = labels


def dependency_gate(
    run_id: str,
    repo: str,
    issue: dict[str, Any],
    *,
    apply: bool = False,
) -> dict[str, Any]:
    """Skip tickets whose upstream ``depends_on`` refs have not closed yet."""
    labels = {str(label.get("name")) for label in issue.get("labels", [])}
    try:
        refs = issue_dependency_refs(run_id, repo, issue)
    except RuntimeError as exc:
        if config.UPSTREAM_BLOCKED_LABEL in labels:
            return {"status": "unreadable", "reason": "dependency_unreadable", "error": str(exc)}
        return {"status": "none", "refs": []}
    if not refs:
        if config.UPSTREAM_BLOCKED_LABEL in labels:
            return {
                "status": "unreadable",
                "reason": "dependency_unreadable",
                "error": "blocked:upstream label is present but no blocked-by refs were found",
            }
        return {"status": "none", "refs": []}
    try:
        states = [_upstream_issue_state(run_id, ref) for ref in refs]
    except RuntimeError as exc:
        return {"status": "unreadable", "reason": "dependency_unreadable", "refs": refs, "error": str(exc)}
    unresolved = [row for row in states if not _dependency_resolved(row)]
    if unresolved:
        return {
            "status": "open",
            "reason": "dependency_open",
            "refs": refs,
            "unresolved": unresolved,
        }
    removed = sorted(config.DEPENDENCY_HOLD_LABELS & labels)
    result: dict[str, Any] = {
        "status": "resolved",
        "reason": "dependency_resolved",
        "refs": refs,
        "resolved": states,
        "removed_labels": removed,
        "applied": False,
    }
    if removed and apply:
        command = github.issue_edit(repo, int(issue["number"]), remove=removed)
        result["command"] = command
        if command.get("exit_code") != 0:
            result.update(
                {
                    "status": "unblock_failed",
                    "reason": "dependency_unblock_failed",
                    "error": command.get("stderr"),
                }
            )
            return result
        result["applied"] = True
        result["status"] = "unblocked"
        result["reason"] = "dependency_unblocked_this_tick"
    if removed:
        _remove_dependency_hold_labels(issue)
    return result


def _parse_github_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC)


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _lease_label_times(
    run_id: str,
    repo: str,
    issue_number: int,
    current_labels: set[str],
) -> dict[str, datetime]:
    """Return the latest active acquisition event for each current lease label."""
    result = run_cmd(
        [
            "gh",
            "api",
            "--paginate",
            "--slurp",
            f"repos/{repo}/issues/{issue_number}/events?per_page=100",
        ],
        timeout_s=60,
    )
    log_event(
        run_id,
        "github_lease_event_scan",
        repo=repo,
        issue=issue_number,
        exit_code=result.get("exit_code"),
    )
    if result.get("exit_code") != 0:
        raise RuntimeError(
            f"lease event scan failed for {repo}#{issue_number}: {result.get('stderr')}"
        )
    try:
        payload = json.loads(result.get("stdout") or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"lease event scan returned invalid JSON for {repo}#{issue_number}: {exc}"
        ) from exc
    if not isinstance(payload, list):
        raise RuntimeError(
            f"lease event scan returned a non-list for {repo}#{issue_number}"
        )
    pages = payload if payload and isinstance(payload[0], list) else [payload]
    acquired: dict[str, datetime] = {}
    for page in pages:
        if not isinstance(page, list):
            raise RuntimeError(
                f"lease event scan returned a malformed page for {repo}#{issue_number}"
            )
        for event in page:
            label = str((event.get("label") or {}).get("name", ""))
            if label not in current_labels:
                continue
            if event.get("event") == "unlabeled":
                acquired.pop(label, None)
                continue
            if event.get("event") != "labeled":
                continue
            moment = _parse_github_time(event.get("created_at"))
            if moment is not None:
                acquired[label] = moment
    return acquired


def list_closed_for_audit(
    run_id: str, project: dict[str, Any], *, now: float | None = None
) -> list[dict[str, Any]]:
    """Recently closed agent-work tickets whose closure has not been checked.

    Closing a ticket is a claim that the work is done. Nothing verified that
    claim: the repair lane's reviewer judges the diff, but a ticket can be
    closed by anything -- a person, a script, an agent that mis-read its own
    output -- and once closed it left the system entirely.

    Only closures GitHub records as COMPLETED. A ticket closed NOT_PLANNED --
    a duplicate, a won't-fix, an abandoned scope -- is not a claim that work was
    done, so auditing it for proof is a category error. tau#213 was closed as a
    duplicate of a lower-numbered ticket and the audit reopened it for having no
    proof of work it was never going to do.

    Excludes tickets already carrying ``closure-verified`` (checked and
    accepted) or ``needs-human`` (a person already owns it), and anything closed
    longer ago than the audit window, since an old closure is history rather
    than something to reopen.
    """
    repo = project_repo(project)
    result = run_cmd(
        [
            "gh", "issue", "list", "--repo", repo, "--state", "closed",
            "--label", config.READY_LABEL, "--limit", "50",
            "--json", "number,title,body,labels,url,closedAt,stateReason",
        ],
        timeout_s=60,
    )
    log_event(run_id, "closure_audit_scan", repo=repo, exit_code=result.get("exit_code"))
    if result.get("exit_code") != 0:
        raise RuntimeError(f"closed-issue scan failed for {repo}: {result.get('stderr')}")

    cutoff = (now if now is not None else time.time()) - config.CLOSURE_AUDIT_WINDOW_SECONDS
    pending: list[dict[str, Any]] = []
    for issue in json.loads(result.get("stdout") or "[]"):
        labels = {str(lbl.get("name")) for lbl in issue.get("labels", [])}
        if not issue_matches_project_scope(project, issue_targets(issue)):
            continue
        if (
            config.CLOSURE_VERIFIED_LABEL in labels
            or config.CLOSURE_UNVERIFIED_LABEL in labels
            or labels & config.HUMAN_HOLD_LABELS
        ):
            continue
        if str(issue.get("stateReason") or "").upper() != "COMPLETED":
            continue
        closed_at = _parse_iso(issue.get("closedAt"))
        if closed_at is None or closed_at < cutoff:
            continue
        pending.append(issue)
    return pending


def list_recently_closed(run_id: str, project: dict[str, Any]) -> list[dict[str, Any]]:
    """Closed agent-work tickets, newest first, for the completion attestation."""
    repo = project_repo(project)
    result = run_cmd(
        [
            "gh", "issue", "list", "--repo", repo, "--state", "closed",
            "--label", config.READY_LABEL, "--limit", "40",
            "--json", "number,title,body,labels,closedAt,stateReason",
        ],
        timeout_s=60,
    )
    if result.get("exit_code") != 0:
        raise RuntimeError(f"closed-issue scan failed for {repo}: {result.get('stderr')}")
    issues = json.loads(result.get("stdout") or "[]")
    scoped = [
        issue for issue in issues
        if issue_matches_project_scope(project, issue_targets(issue))
    ]
    return sorted(scoped, key=lambda i: str(i.get("closedAt") or ""), reverse=True)


def _parse_iso(value: Any) -> float | None:
    """Epoch seconds for a GitHub timestamp, or None when unreadable."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError as exc:
        logger.error("unreadable timestamp {!r}: {}", value, exc)
        return None


def lane_busy_issues(run_id: str, project: dict[str, Any]) -> list[dict[str, Any]]:
    """Issues already leased for this project, i.e. work in flight.

    A lease label is applied when a repair is leased and removed when it
    finishes or blocks, so its presence is the in-flight signal. Dispatching a
    second ticket while one is leased is working ahead: the second repair is
    authored against a tree the first is still changing.

    Scans every label in ``config.LEASE_LABELS``, which is the same vocabulary
    ``classify_issue`` refuses to dispatch on. Scanning only ``agent-active``
    missed ``maintainer-active`` -- the label ``skills/ticket/run.sh lease``
    applies -- so a ticket leased through the documented command read as idle
    and the watchdog dispatched alongside it.

    One scan per label rather than one call: ``gh issue list`` ANDs repeated
    ``--label``, so a single call with both would match only issues carrying
    both at once, which is never.
    """
    repo = str(project["repo"])
    by_number: dict[int, dict[str, Any]] = {}
    for label in sorted(config.LEASE_LABELS):
        result = run_cmd(
            [
                "gh", "issue", "list", "--repo", repo, "--state", "open",
                "--label", label, "--limit", "20",
                # body included: the target is read from it, and without it
                # every in-flight ticket reads as unknown-target.
                "--json", "number,title,body,labels,url,updatedAt",
            ],
            timeout_s=60,
        )
        if result.get("exit_code") != 0:
            # A failed scan must never read as "nothing in flight" -- that would
            # let the watchdog work ahead precisely when it cannot see the
            # current state.
            raise RuntimeError(
                f"lease scan failed for {repo} on label {label}: {result.get('stderr')}"
            )
        for issue in json.loads(result.get("stdout") or "[]"):
            number = int(issue["number"])
            existing = by_number.get(number, issue)
            scanned = set(existing.get("_watchdog_scanned_labels", []))
            scanned.add(label)
            existing["_watchdog_scanned_labels"] = sorted(scanned)
            by_number[number] = existing

    now = _now_utc()
    active: list[dict[str, Any]] = []
    stale_by_issue: list[dict[str, Any]] = []
    unknown: list[dict[str, Any]] = []
    for number in sorted(by_number):
        issue = by_number[number]
        current_labels = {
            str(label.get("name"))
            for label in issue.get("labels", [])
            if str(label.get("name")) in config.LEASE_LABELS
        }
        current_labels |= set(issue.get("_watchdog_scanned_labels", []))
        # ``updatedAt`` is requested by the live scan and acts only as a payload
        # completeness marker. The timestamp itself is never used as lease age:
        # comments can change it long after acquisition.
        label_times = (
            _lease_label_times(run_id, repo, number, current_labels)
            if issue.get("updatedAt")
            else {}
        )
        stale_labels: list[dict[str, Any]] = []
        fresh_labels: list[dict[str, Any]] = []
        for label in sorted(current_labels):
            acquired = label_times.get(label)
            if acquired is None:
                # Fail closed when GitHub cannot establish acquisition time. The
                # lease remains in flight and the receipt exposes the gap.
                fresh_labels.append(
                    {
                        "label": label,
                        "acquired_at": None,
                        "reason": "lease_acquisition_time_unknown",
                    }
                )
                unknown.append({"issue_number": number, "label": label})
                continue
            age_seconds = max(0, int((now - acquired).total_seconds()))
            lease = {
                "label": label,
                "acquired_at": acquired.isoformat().replace("+00:00", "Z"),
                "age_seconds": age_seconds,
                "stale_after_seconds": config.LEASE_STALE_SECONDS,
                "timestamp_source": "github_label_event",
            }
            if age_seconds >= config.LEASE_STALE_SECONDS:
                lease["reason"] = "lease_expired"
                stale_labels.append(lease)
            else:
                lease["reason"] = "lease_active"
                fresh_labels.append(lease)
        if stale_labels:
            stale_by_issue.append(
                {
                    "issue_number": number,
                    "issue_url": str(issue.get("url", "")),
                    "labels": [lease["label"] for lease in stale_labels],
                    "leases": stale_labels,
                    "reason": "lease_expired",
                }
            )
        if fresh_labels:
            issue["watchdog_leases"] = fresh_labels
            active.append(issue)

    LAST_LEASE_SCAN.clear()
    LAST_LEASE_SCAN.update(
        {
            "stale_after_seconds": config.LEASE_STALE_SECONDS,
            "stale": stale_by_issue,
            "active": [
                {
                    "issue_number": int(issue["number"]),
                    "leases": issue.get("watchdog_leases", []),
                }
                for issue in active
            ],
            "unknown_acquisition_time": unknown,
        }
    )
    return active


#: The machine-readable `target: skills/<name>` line `/ticket` writes into every
#: body. That line is the ticket's own statement of what it will change.
_TARGET_LINE = re.compile(r"^target:\s*(\S+)\s*$", re.MULTILINE)

#: Fallback for tickets filed before that line existed: every skill path the
#: body mentions. Coarser, but it resolves 7 of the 8 leases currently open on
#: agent-skills, where the `target:` line resolves 1.
_SKILL_PATH = re.compile(r"\bskills/[a-z0-9][a-z0-9._-]*")

_TARGET_PATHS_HEADING = re.compile(r"^##\s+Target paths\s*$", re.IGNORECASE | re.MULTILINE)

#: A ticket whose target cannot be read at all. Just another target value: it
#: collides with other unreadable tickets and with nothing else. Treating it as
#: colliding with everything sounds safer and is not -- one legacy ticket with
#: no target then holds the whole fleet, which is the stall being fixed.
UNKNOWN_TARGET = "?"


def _clean_target_path_fragment(raw: str) -> str | None:
    """Return a concrete target path from one declared Markdown fragment."""
    fragment = raw.strip().strip("`").strip().rstrip(".,;")
    if not fragment:
        return None
    token = fragment.split()[0].strip("`").rstrip(".,;")
    if not token or token.startswith(("/", "..")) or "/" not in token:
        return None
    if token != fragment and "." not in Path(token).name:
        return None
    return token.rstrip("/")


def _markdown_target_paths(body: str) -> set[str]:
    """Parse the ``## Target paths`` block written by modern ticket bodies."""
    match = _TARGET_PATHS_HEADING.search(body)
    if not match:
        return set()
    targets: set[str] = set()
    for line in body[match.end():].splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            break
        if not stripped.startswith(("-", "*")):
            continue
        item = stripped[1:].strip()
        for part in item.split(","):
            target = _clean_target_path_fragment(part)
            if target:
                targets.add(target)
    return targets


def issue_targets(issue: dict[str, Any]) -> set[str]:
    """The paths a ticket will change, e.g. ``{"skills/ticket"}``.

    A repository is not the unit of collision. agent-skills holds 364 skills;
    two tickets against different ones share no files and cannot cascade into
    each other, while two against the same one edit the same tree. Scheduling on
    the repo blocks 363 skills to protect 1.
    """
    body = issue.get("body") or ""
    match = _TARGET_LINE.search(body)
    if match and (declared := match.group(1).strip().rstrip("/")):
        return {declared}
    declared_paths = _markdown_target_paths(body)
    if declared_paths:
        return declared_paths
    mentioned = {path.rstrip("/") for path in _SKILL_PATH.findall(body)}
    return mentioned or {UNKNOWN_TARGET}


def _project_target_prefix_list(project: dict[str, Any], key: str) -> list[str]:
    raw = project.get(key) or []
    prefixes: list[str] = []
    if isinstance(raw, str):
        raw = [raw]
    for item in raw:
        prefix = str(item).strip().rstrip("/")
        if prefix and not prefix.startswith(("/", "..")):
            prefixes.append(prefix)
    return prefixes


def project_target_prefixes(project: dict[str, Any]) -> list[str]:
    """Target prefixes this project owns inside a shared repository.

    Most registered projects map one GitHub repo to one project. The
    agent-skills repo is different: it holds hundreds of skills. A skill-level
    project such as Battle must see only tickets scoped to ``skills/battle``;
    otherwise the shared repo queue can hand it unrelated Ask or Surf work.
    """
    return _project_target_prefix_list(project, "issue_target_prefixes")


def project_target_exclude_prefixes(project: dict[str, Any]) -> list[str]:
    """Target prefixes this broad project explicitly leaves to scoped projects."""
    return _project_target_prefix_list(project, "issue_target_exclude_prefixes")


def target_matches_prefix(target: str, prefix: str) -> bool:
    """Return whether ``target`` is exactly under ``prefix``."""
    target = target.rstrip("/")
    prefix = prefix.rstrip("/")
    return target == prefix or target.startswith(f"{prefix}/")


def issue_matches_project_scope(project: dict[str, Any], targets: set[str]) -> bool:
    """Whether the issue targets belong to this project's declared scope."""
    include_prefixes = project_target_prefixes(project)
    exclude_prefixes = project_target_exclude_prefixes(project)
    if not include_prefixes and not exclude_prefixes:
        return True
    concrete = {target for target in targets if target != UNKNOWN_TARGET}
    if any(
        target_matches_prefix(target, prefix)
        for target in concrete
        for prefix in exclude_prefixes
    ):
        return False
    if not include_prefixes:
        return True
    return any(
        target_matches_prefix(target, prefix)
        for target in concrete
        for prefix in include_prefixes
    )


def busy_targets(issues: list[dict[str, Any]]) -> set[str]:
    """Every target held by the given in-flight issues."""
    held: set[str] = set()
    for issue in issues:
        held |= issue_targets(issue)
    return held


def targets_are_blocked(targets: set[str], busy: set[str]) -> bool:
    """Whether dispatching ``targets`` would touch something already in flight."""
    return bool(targets & busy)


def rotation_order(
    projects: dict[str, Any], state: dict[str, Any], *, requested: str | None = None
) -> list[dict[str, Any]]:
    """Projects to try this tick, best candidate first.

    The requested project leads when it is active -- the crontab names one and
    that intent is honoured -- and the rest follow in round-robin order starting
    after the last one served, so service is fair rather than always restarting
    at the head of the registry.
    """
    entries = list(projects.get("projects", []))
    ids = [str(e.get("project_id")) for e in entries]
    last_served = state.get("last_served_project")
    start = ids.index(last_served) + 1 if last_served in ids else 0
    ordered = entries[start:] + entries[:start]
    if requested in ids:
        wanted = next(e for e in entries if str(e.get("project_id")) == requested)
        ordered = [wanted] + [e for e in ordered if e is not wanted]
    return ordered


def select_next_project(
    *,
    run_id: str,
    projects: dict[str, Any],
    state: dict[str, Any],
    last_served: str | None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Round-robin to the next ACTIVE project.

    The crontab is hardcoded to one project, and ``tick`` resolved exactly that
    one, so an idle project stalled the whole fleet and no other project was
    ever serviced. Rotation starts AFTER the last-served project so service is
    fair rather than always restarting at the head of the registry.

    A leased ticket does NOT take its project out of the rotation. Collision is
    a property of the target, not the repository, and is enforced per ticket in
    ``list_routable_issues``. Skipping the project instead meant one lease on
    agent-skills withheld the other 363 skills.

    Returns the chosen project (or None) and a per-project skip ledger, so a
    tick that dispatches nothing still says why for each candidate.
    """
    entries = list(projects.get("projects", []))
    ids = [str(e.get("project_id")) for e in entries]
    start = 0
    if last_served in ids:
        start = ids.index(last_served) + 1
    ordered = entries[start:] + entries[:start]

    skipped: list[dict[str, Any]] = []
    for entry in ordered:
        pid = str(entry.get("project_id"))
        project_state = state.get("projects", {}).get(pid, {}).get("state")
        if project_state != "active":
            skipped.append({"project_id": pid, "reason": f"project_state_{project_state}"})
            continue
        return entry, skipped
    return None, skipped


#: Side-channel for the last scan's non-routable tally, so ``tick`` can report
#: WHY nothing was routable without re-listing.
LAST_SCAN: dict[str, int] = {}

#: Side-channel for receipt construction, parallel to ``LAST_SCAN`` above.
#: ``lane_busy_issues`` stays backward-compatible as a list-returning function.
LAST_LEASE_SCAN: dict[str, Any] = {}


def project_has_repair_lane(project: dict[str, Any]) -> bool:
    """Whether this project can actually run a ticket repair.

    Every registered project can: $ask compiles the creator-reviewer DAG for any
    repo and Tau executes it. This used to require ``runner_kind`` to be
    ``tau-command-loop`` because the lane hand-authored a contract pointing at
    Tau's own command-spec tree, which only the tau checkout has -- so all five
    other registered projects were refused before dispatch. A project needs a
    worktree; readiness of that worktree is checked per target at dispatch.
    """
    return bool(project.get("worktree"))


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
    action, _ = classify_issue_with_reason(issue)
    return action


def classify_issue_with_reason(issue: dict[str, Any]) -> tuple[str | None, str | None]:
    """``classify_issue``, plus WHY an issue was excluded.

    A tick that dispatches nothing has to say which tickets it passed over and
    on what grounds. Without that, a fleet with no dispatchable work and a fleet
    whose every ticket is blocked produce the same silent tick -- which is how
    41,607 consecutive no-op ticks went unnoticed once already.

    Returns ``(action, None)`` when routable and ``(None, reason)`` when not.
    """
    labels = {label.get("name") for label in issue.get("labels", [])}

    # Never routable: already leased by any agent, human-blocked, or parked.
    # Reported separately because the remedies are different: a lease clears
    # itself, a blocked ticket needs its blocker resolved, and a human-held one
    # needs a person.
    if labels & config.LEASE_LABELS:
        return None, "leased"
    if config.BLOCKED_LABEL in labels:
        return None, "blocked"
    if config.DONE_LABEL in labels:
        return None, "awaiting_review"
    if labels & config.HUMAN_HOLD_LABELS:
        return None, "human_hold"
    if config.READY_LABEL not in labels:
        return None, "not_ready"

    body = issue.get("body") or ""
    if "next:coder" in labels and "executor:local" in labels and config.TAU_REPAIR_MARKER in body:
        return "add_tau_coder_command_spec", None
    if "executor:local" in labels and config.TAU_HANDOFF_DISPATCH_MARKER in body:
        return "tau_handoff_dispatch", None
    return "ticket_repair", None


def _register_worktree_lease(worktree, *, purpose: str) -> None:
    """Record a worktree lease; never fail the repair because logging did."""
    try:
        import sys as _sys
        from pathlib import Path as _Path

        cleanup = _Path(__file__).resolve().parents[3] / "ops-worktrees" / "scripts"
        if str(cleanup) not in _sys.path:
            _sys.path.insert(0, str(cleanup))
        from worktree_lease import register as _register

        _register(worktree, purpose=purpose)
    except Exception:
        pass
