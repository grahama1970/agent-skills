"""Evidence gathering for the goal-drift audit.

Evidence hierarchy, strongest first — a rework after the first version relied on
`git log` alone, which cannot tell a commit that serves the goal from a commit
that merely touches the tree:

  1. TICKETS   declared intent + lease state + attached proof (authoritative)
  2. ARTIFACTS files matching a criterion's globs (did the thing get produced?)
  3. COMMITS   secondary; a commit with NO ticket is itself a drift signal

Tickets are the primary source because they declare intent BEFORE work starts, so
drift is visible at declaration time rather than only as post-hoc forensics. A
lease says what is being worked on right now; attached proof is real acceptance
evidence rather than a filename guess.

Read-only: `gh issue list` and `git log` only. Nothing here mutates.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

TICKET_SKILL = Path("skills/ticket/run.sh")


@dataclass
class Ticket:
    """A declared unit of intent."""

    number: int
    title: str
    state: str  # OPEN | CLOSED
    labels: tuple[str, ...] = ()
    body: str = ""
    leased: bool = False
    has_proof: bool = False
    closed_at: str = ""

    @property
    def text(self) -> str:
        return f"{self.title} {self.body} {' '.join(self.labels)}"

    def to_action_summary(self) -> str:
        flags = []
        if self.leased:
            flags.append("leased")
        if self.has_proof:
            flags.append("proof")
        suffix = f" [{','.join(flags)}]" if flags else ""
        return f"#{self.number} {self.title}{suffix}"


@dataclass
class EvidenceBundle:
    tickets: list[Ticket] = field(default_factory=list)
    commits: list[tuple[str, str, tuple[str, ...]]] = field(default_factory=list)
    sources_ok: dict[str, bool] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def degraded(self) -> bool:
        """True when a source failed. A dead source must never read as 'no drift'."""
        return not all(self.sources_ok.values())


def _gh(args: list[str], repo: str | None = None, timeout: int = 60) -> str:
    cmd = ["gh", *args]
    if repo:
        cmd += ["--repo", repo]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return r.stdout if r.returncode == 0 else ""
    except (subprocess.SubprocessError, OSError):
        return ""


def gather_tickets(repo: str, since_iso: str, limit: int = 100) -> tuple[list[Ticket], bool]:
    """Read tickets via gh. Returns (tickets, source_ok).

    source_ok distinguishes 'no tickets' from 'could not read tickets' — the same
    loud-degradation rule the opportunity feeds use.
    """
    raw = _gh([
        "issue", "list", "--state", "all", "--limit", str(limit),
        "--json", "number,title,state,labels,body,assignees,closedAt,comments",
    ], repo=repo)
    if not raw.strip():
        return [], False
    try:
        items: list[dict[str, Any]] = json.loads(raw)
    except json.JSONDecodeError:
        return [], False

    out: list[Ticket] = []
    for it in items:
        closed_at = it.get("closedAt") or ""
        if closed_at and closed_at < since_iso:
            continue
        labels = tuple(l.get("name", "") for l in (it.get("labels") or []))
        comments = it.get("comments") or []
        body = it.get("body") or ""
        # /ticket attaches proof as a body section or comment; either counts.
        proof_blob = body + " ".join(
            c.get("body", "") if isinstance(c, dict) else str(c) for c in comments
        )
        out.append(Ticket(
            number=int(it.get("number", 0)),
            title=it.get("title", ""),
            state=(it.get("state") or "").upper(),
            labels=labels,
            body=body,
            leased=bool(it.get("assignees")),
            has_proof=("proof" in proof_blob.lower() or "acceptance" in proof_blob.lower()),
            closed_at=closed_at,
        ))
    return out, True


def gather_commits(repo_path: Path, since: str) -> tuple[list[tuple[str, str, tuple[str, ...]]], bool]:
    """Secondary evidence. git log only — never a mutating verb."""
    if not (repo_path / ".git").exists():
        return [], False
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_path), "log", f"--since={since}",
             "--pretty=%h%x1f%s", "--name-only"],
            capture_output=True, text=True, timeout=60, check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return [], False
    if out.returncode != 0:
        return [], False

    commits: list[tuple[str, str, tuple[str, ...]]] = []
    sha = subject = ""
    paths: list[str] = []
    for line in out.stdout.splitlines():
        if "\x1f" in line:
            if sha:
                commits.append((sha, subject, tuple(paths)))
            sha, subject = line.split("\x1f", 1)
            paths = []
        elif line.strip():
            paths.append(line.strip())
    if sha:
        commits.append((sha, subject, tuple(paths)))
    return commits, True


def commit_references_ticket(subject: str, tickets: list[Ticket]) -> Ticket | None:
    """A commit citing #N inherits that ticket's declared intent."""
    import re
    for m in re.finditer(r"#(\d+)", subject):
        n = int(m.group(1))
        for t in tickets:
            if t.number == n:
                return t
    return None
