"""Cross-repo dependency edges: parse ``blocked-by`` refs and clear them when resolved.

Purpose
    Make "this ticket is waiting on another project" a machine-readable fact
    that a cron can act on, instead of prose in an issue body that only a human
    can join up.

    The failure this removes was observed directly: ``graph-memory-operator#61``
    blocked ``tau#140`` and ``tau#149``; #61 closed on 2026-07-27 and both Tau
    tickets closed the same day — but nothing in either repo linked them. A
    human had to notice. Three greps across project-watchdog, ticket, and
    best-practices-github-ticket for ``blocked.by|upstream|unblock`` returned
    nothing before this module existed.

Inputs
    Issues carrying the ``blocked:upstream`` label and one or more
    ``blocked-by: owner/repo#N`` lines in the body or in a watchdog comment.

Outputs
    ``UnblockOutcome`` per issue: which upstreams were checked, which are still
    open, and whether the downstream issue was released back into the routable
    pool.

Failure modes
    Fail-closed in every ambiguous case. An upstream that cannot be read — bad
    ref, deleted repo, ``gh`` failure — counts as *still blocking*. Releasing a
    ticket because its dependency could not be checked is strictly worse than
    leaving it blocked, so unreadable never means resolved.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from . import github
from .core import log_event, run_cmd

#: Label marking a downstream issue as waiting on another repository.
BLOCKED_LABEL = "blocked:upstream"

#: ``blocked-by: owner/repo#123``. Case-insensitive, tolerant of surrounding
#: markdown, and anchored so prose mentioning an issue does not create an edge.
BLOCKED_BY_PATTERN = re.compile(
    r"blocked-by:\s*([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(\d+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class UpstreamRef:
    """One ``owner/repo#number`` dependency."""

    repo: str
    number: int

    def __str__(self) -> str:
        return f"{self.repo}#{self.number}"


@dataclass
class UpstreamState:
    ref: UpstreamRef
    state: str = "UNKNOWN"
    title: str = ""
    readable: bool = False

    @property
    def resolved(self) -> bool:
        """Only a confirmed CLOSED upstream stops blocking."""
        return self.readable and self.state == "CLOSED"


@dataclass
class UnblockOutcome:
    issue_number: int
    repo: str
    refs: list[UpstreamState] = field(default_factory=list)
    released: bool = False
    error: str | None = None
    commands: list[dict[str, Any]] = field(default_factory=list)

    def as_receipt_block(self) -> dict[str, Any]:
        return {
            "issue": f"issue#{self.issue_number}",
            "repo": self.repo,
            "released": self.released,
            "error": self.error,
            "upstreams": [
                {
                    "ref": str(item.ref),
                    "state": item.state,
                    "readable": item.readable,
                    "resolved": item.resolved,
                    "title": item.title,
                }
                for item in self.refs
            ],
            "still_blocking": [str(i.ref) for i in self.refs if not i.resolved],
        }


def parse_blocked_by(text: str) -> list[UpstreamRef]:
    """Extract every ``blocked-by: owner/repo#N`` ref, de-duplicated, in order."""
    seen: dict[str, UpstreamRef] = {}
    for repo, number in BLOCKED_BY_PATTERN.findall(text or ""):
        ref = UpstreamRef(repo=repo, number=int(number))
        seen.setdefault(str(ref), ref)
    return list(seen.values())


def read_upstream(ref: UpstreamRef) -> UpstreamState:
    """Read one upstream issue. Anything unreadable is treated as still blocking."""
    result = run_cmd(
        ["gh", "issue", "view", str(ref.number), "--repo", ref.repo, "--json", "state,title"],
        timeout_s=45,
    )
    if result["exit_code"] != 0:
        logger.error("cannot read upstream {}: {}", ref, result["stderr"].strip()[:200])
        return UpstreamState(ref=ref, state="UNREADABLE", readable=False)
    try:
        payload = json.loads(result["stdout"] or "{}")
    except ValueError as exc:
        logger.error("unparseable upstream payload for {}: {}", ref, exc)
        return UpstreamState(ref=ref, state="UNREADABLE", readable=False)
    return UpstreamState(
        ref=ref,
        state=str(payload.get("state", "UNKNOWN")).upper(),
        title=str(payload.get("title", "")),
        readable=True,
    )


def list_blocked_issues(run_id: str, repo: str) -> list[dict[str, Any]]:
    """Return open issues in ``repo`` carrying the blocked-upstream label."""
    result = run_cmd(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            repo,
            "--state",
            "open",
            "--label",
            BLOCKED_LABEL,
            "--limit",
            "50",
            "--json",
            "number,title,body,labels,url",
        ],
        timeout_s=60,
    )
    log_event(run_id, "blocked_issue_scan", repo=repo, exit_code=result["exit_code"])
    if result["exit_code"] != 0:
        raise RuntimeError(
            f"gh issue list --label {BLOCKED_LABEL} failed for {repo}: {result['stderr']}"
        )
    return json.loads(result["stdout"] or "[]")


def issue_dependency_text(issue: dict[str, Any], *, repo: str) -> str:
    """Return body plus comment text, so an edge added by comment is honoured."""
    text = issue.get("body") or ""
    result = run_cmd(
        ["gh", "issue", "view", str(issue["number"]), "--repo", repo, "--json", "comments"],
        timeout_s=45,
    )
    if result["exit_code"] != 0:
        logger.error("cannot read comments for {}#{}", repo, issue.get("number"))
        return text
    try:
        payload = json.loads(result["stdout"] or "{}")
    except ValueError:
        return text
    for comment in payload.get("comments", []):
        text += "\n" + (comment.get("body") or "")
    return text


def resolve_issue(
    run_id: str,
    issue: dict[str, Any],
    *,
    repo: str,
    apply: bool,
) -> UnblockOutcome:
    """Check one blocked issue's upstreams and release it when all are closed."""
    number = int(issue["number"])
    outcome = UnblockOutcome(issue_number=number, repo=repo)

    refs = parse_blocked_by(issue_dependency_text(issue, repo=repo))
    if not refs:
        outcome.error = (
            f"{repo}#{number} carries the {BLOCKED_LABEL} label but declares no "
            "'blocked-by: owner/repo#N' reference; it can never be released "
            "automatically. Add the reference or remove the label."
        )
        logger.warning("{}", outcome.error)
        return outcome

    outcome.refs = [read_upstream(ref) for ref in refs]
    unresolved = [item for item in outcome.refs if not item.resolved]
    if unresolved:
        log_event(
            run_id,
            "still_blocked",
            issue=number,
            repo=repo,
            still_blocking=[str(i.ref) for i in unresolved],
        )
        return outcome

    if not apply:
        outcome.released = False
        outcome.error = "all upstreams resolved; would release (dry run)"
        return outcome

    resolved_list = "\n".join(f"- `{i.ref}` — {i.state} — {i.title}" for i in outcome.refs)
    outcome.commands.append(
        github.issue_comment(
            repo,
            number,
            github.watchdog_comment(
                "Upstream dependency resolved",
                {
                    "schema": "agent_skills.project_watchdog.unblock_receipt.v1",
                    "run_id": run_id,
                    "issue": f"issue#{number}",
                    "repo": repo,
                    "upstreams": [
                        {"ref": str(i.ref), "state": i.state, "title": i.title}
                        for i in outcome.refs
                    ],
                    "action": f"removed {BLOCKED_LABEL}; issue returns to the routable pool",
                },
            )
            + f"\nEvery declared upstream is closed:\n\n{resolved_list}\n",
        )
    )
    edit = github.issue_edit(repo, number, remove=[BLOCKED_LABEL])
    outcome.commands.append(edit)
    outcome.released = edit["exit_code"] == 0
    if not outcome.released:
        outcome.error = f"failed to remove {BLOCKED_LABEL}: {edit['stderr'].strip()[:200]}"
        logger.error("{}", outcome.error)
    else:
        log_event(run_id, "issue_unblocked", issue=number, repo=repo)
    return outcome


def poll(run_id: str, project: dict[str, Any], *, apply: bool) -> list[dict[str, Any]]:
    """Check every blocked issue in a project and release the resolved ones.

    Runs before routing so an issue unblocked this tick becomes eligible on the
    next one, rather than being dispatched in the same pass it was released.
    """
    repo = str(project["repo"])
    outcomes = [
        resolve_issue(run_id, issue, repo=repo, apply=apply).as_receipt_block()
        for issue in list_blocked_issues(run_id, repo)
    ]
    if outcomes:
        log_event(
            run_id,
            "unblock_poll_complete",
            repo=repo,
            checked=len(outcomes),
            released=sum(1 for o in outcomes if o["released"]),
        )
    return outcomes


__all__ = [
    "BLOCKED_LABEL",
    "UnblockOutcome",
    "UpstreamRef",
    "UpstreamState",
    "list_blocked_issues",
    "parse_blocked_by",
    "poll",
    "read_upstream",
    "resolve_issue",
]
