"""Goal-drift audit core: typed records, evidence gathering, verdicts.

Read-only by construction. Nothing here opens a file for writing in a project
tree, invokes git mutation, or shells out to anything that could. The audit is a
pure function of (goal record, observed evidence).

Ported concept: nicobailon/pi-subagents watchdog `scope-drift`, whose scope
artifact is built only from real user prompts. That exclusion is the load-bearing
rule — see GoalRecord.validate.
"""

from __future__ import annotations

import fnmatch
import json
import re
import subprocess
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

SCHEMA = "goal_drift.audit.v1"
INDIRECT_CAP = 0.30
"""Share of actions that may be SUPPORTS_INDIRECTLY before the run is DRIFTED.

'It was all necessary groundwork' is the story drift tells about itself, so the
allowance is bounded rather than unlimited.
"""


class Verdict(StrEnum):
    SERVES_GOAL = "SERVES_GOAL"
    SUPPORTS_INDIRECTLY = "SUPPORTS_INDIRECTLY"
    SCOPE_DRIFT = "SCOPE_DRIFT"
    MISSING_EXPECTED = "MISSING_EXPECTED"
    GOAL_UNREGISTERED = "GOAL_UNREGISTERED"
    UNTICKETED_WORK = "UNTICKETED_WORK"
    DECLARED_DRIFT = "DECLARED_DRIFT"


class RunVerdict(StrEnum):
    ON_GOAL = "ON_GOAL"
    DRIFTED = "DRIFTED"
    NOT_ESTABLISHED = "NOT_ESTABLISHED"
    DEGRADED = "DEGRADED"
    """An evidence source failed. Never report ON_GOAL on partial evidence."""


class GoalSource(StrEnum):
    HUMAN_PROMPT = "human_prompt"
    AGENT_INFERRED = "agent_inferred"


class GoalRegistrationError(Exception):
    """Raised when a goal cannot be registered. Fail closed."""


@dataclass(frozen=True)
class Criterion:
    """One acceptance criterion with the artifacts that prove it."""

    key: str
    text: str
    artifact_globs: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    min_instances: int = 1


@dataclass
class GoalRecord:
    project: str
    goal_text: str
    source: GoalSource
    criteria: tuple[Criterion, ...] = ()
    repos: tuple[str, ...] = ()
    registered_at: str = ""

    def validate(self) -> GoalRecord:
        """Refuse anything that would let an agent certify its own tangents."""
        if not self.project:
            raise GoalRegistrationError("project is required")
        if len(self.goal_text.strip()) < 20:
            raise GoalRegistrationError(
                "goal_text must be the human's own words, at least 20 characters"
            )
        if self.source is not GoalSource.HUMAN_PROMPT:
            raise GoalRegistrationError(
                "goal source must be human_prompt; agent_inferred goals are refused so an "
                "agent cannot invent a sub-goal, pursue it, and grade itself compliant"
            )
        if not self.criteria:
            raise GoalRegistrationError(
                "at least one acceptance criterion is required, or absence can never be detected"
            )
        keys = [c.key for c in self.criteria]
        if len(keys) != len(set(keys)):
            raise GoalRegistrationError("criterion keys must be unique")
        return self


@dataclass
class Action:
    """Something the project actually did."""

    kind: str  # commit | artifact | receipt
    ref: str
    summary: str
    paths: tuple[str, ...] = ()
    ticket: int | None = None
    """Ticket this action cites, if any. A commit with none is UNTICKETED_WORK."""


@dataclass
class Finding:
    verdict: Verdict
    subject: str
    reason: str
    criterion: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "subject": self.subject,
            "reason": self.reason,
            "criterion": self.criterion,
        }


@dataclass
class Audit:
    project: str
    window: str
    run_verdict: RunVerdict
    findings: list[Finding] = field(default_factory=list)
    indirect_share: float = 0.0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "project": self.project,
            "window": self.window,
            "verdict": self.run_verdict.value,
            "indirect_share": round(self.indirect_share, 3),
            "indirect_cap": INDIRECT_CAP,
            "findings": [f.to_dict() for f in self.findings],
            "notes": self.notes,
            "read_only": True,
        }

    def render(self) -> str:
        lines = [f"project: {self.project}   window: {self.window}   verdict: {self.run_verdict.value}"]
        order = {
            Verdict.MISSING_EXPECTED: 0,
            Verdict.DECLARED_DRIFT: 1,
            Verdict.UNTICKETED_WORK: 1,
            Verdict.SCOPE_DRIFT: 1,
            Verdict.SUPPORTS_INDIRECTLY: 2,
            Verdict.SERVES_GOAL: 3,
            Verdict.GOAL_UNREGISTERED: 4,
        }
        for f in sorted(self.findings, key=lambda x: order.get(x.verdict, 9)):
            arrow = f"  -> criterion: {f.criterion}" if f.criterion else ""
            lines.append(f"  {f.verdict.value:18} {f.subject[:46]:46} ({f.reason}){arrow}")
        if self.indirect_share > INDIRECT_CAP:
            lines.append(
                f"  indirect {self.indirect_share:.0%} exceeds cap {INDIRECT_CAP:.0%} -> DRIFTED"
            )
        lines.extend(f"  note: {n}" for n in self.notes)
        return "\n".join(lines)


def git_actions(repo: Path, since: str) -> list[Action]:
    """Read commits in a window. Read-only: log only, never a mutating verb."""
    if not (repo / ".git").exists():
        return []
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "log", f"--since={since}", "--pretty=%h%x1f%s", "--name-only"],
            capture_output=True, text=True, timeout=60, check=False,
        ).stdout
    except (subprocess.SubprocessError, OSError):
        return []
    actions: list[Action] = []
    sha = subject = ""
    paths: list[str] = []
    for line in out.splitlines():
        if "\x1f" in line:
            if sha:
                actions.append(Action("commit", sha, subject, tuple(paths)))
            sha, subject = line.split("\x1f", 1)
            paths = []
        elif line.strip():
            paths.append(line.strip())
    if sha:
        actions.append(Action("commit", sha, subject, tuple(paths)))
    return actions


def _matches(action: Action, crit: Criterion) -> bool:
    for pattern in crit.artifact_globs:
        for p in action.paths:
            if fnmatch.fnmatch(p, pattern):
                return True
    blob = f"{action.summary} {' '.join(action.paths)}".lower()
    return any(re.search(rf"\b{re.escape(k.lower())}", blob) for k in crit.keywords)


def audit(
    goal: GoalRecord | None,
    actions: list[Action],
    window: str,
    project: str = "",
    tickets: list[Any] | None = None,
    sources_ok: dict[str, bool] | None = None,
) -> Audit:
    """Audit declared intent (tickets) and produced work against the goal.

    Ticket-first: a ticket declares intent before work begins, so a ticket that
    maps to no criterion is DECLARED_DRIFT and catchable on the day it is filed —
    not weeks later in commit forensics. A commit with no ticket is
    UNTICKETED_WORK, which is a drift signal in its own right.
    """
    tickets = tickets or []
    sources_ok = sources_ok or {}

    if goal is None:
        return Audit(
            project=project, window=window, run_verdict=RunVerdict.NOT_ESTABLISHED,
            findings=[Finding(Verdict.GOAL_UNREGISTERED, project or "(unknown)",
                              "no immutable goal registered; on-track cannot be asserted")],
            notes=["register a goal from the human's own words before trusting any verdict"],
        )

    findings: list[Finding] = []
    satisfied: dict[str, int] = {c.key: 0 for c in goal.criteria}
    indirect = 0

    def match_text(blob: str) -> Criterion | None:
        low = blob.lower()
        for c in goal.criteria:
            if any(re.search(rf"\b{re.escape(k.lower())}", low) for k in c.keywords):
                return c
        return None

    # --- 1. Tickets: declared intent (authoritative) ---
    for t in tickets:
        hit = match_text(getattr(t, "text", ""))
        subject = t.to_action_summary() if hasattr(t, "to_action_summary") else str(t)
        if hit is None:
            findings.append(Finding(Verdict.DECLARED_DRIFT, subject,
                                    "ticket declares work matching no criterion"))
            continue
        # Proof on a closed ticket is real acceptance evidence.
        if getattr(t, "state", "") == "CLOSED" and getattr(t, "has_proof", False):
            satisfied[hit.key] += 1
            findings.append(Finding(Verdict.SERVES_GOAL, subject,
                                    "closed with attached proof", hit.key))
        else:
            # On-criterion but unproven. Counted toward the indirect cap so an
            # unbounded pile of "in progress" cannot read as on-goal.
            indirect += 1
            findings.append(Finding(Verdict.SUPPORTS_INDIRECTLY, subject,
                                    f"on-criterion ticket, state={getattr(t,'state','?')}"
                                    f", proof={getattr(t,'has_proof',False)}", hit.key))

    # --- 2. Artifacts and commits: produced work ---
    for a in actions:
        hit = next((c for c in goal.criteria if _matches(a, c)), None)
        if hit is not None:
            satisfied[hit.key] += 1
            findings.append(Finding(Verdict.SERVES_GOAL, a.summary or a.ref,
                                    f"{a.kind} matches criterion", hit.key))
            continue
        if a.kind == "commit" and not getattr(a, "ticket", None):
            findings.append(Finding(Verdict.UNTICKETED_WORK, a.summary or a.ref,
                                    "commit cites no ticket and matches no criterion"))
        elif a.paths:
            indirect += 1
            findings.append(Finding(Verdict.SUPPORTS_INDIRECTLY, a.summary or a.ref,
                                    f"{a.kind} touches the project but matches no criterion"))
        else:
            findings.append(Finding(Verdict.SCOPE_DRIFT, a.summary or a.ref,
                                    f"{a.kind} maps to no criterion"))

    # --- 3. Absence: what a what-happened-only checker cannot see ---
    for c in goal.criteria:
        if satisfied[c.key] < c.min_instances:
            findings.append(Finding(
                Verdict.MISSING_EXPECTED, c.text[:70],
                f"{satisfied[c.key]} produced, >={c.min_instances} required", c.key))

    total = max(len(actions) + len(tickets), 1)
    share = indirect / total
    drifted = (
        any(f.verdict in (Verdict.MISSING_EXPECTED, Verdict.SCOPE_DRIFT,
                          Verdict.DECLARED_DRIFT, Verdict.UNTICKETED_WORK)
            for f in findings)
        or share > INDIRECT_CAP
    )
    verdict = RunVerdict.DRIFTED if drifted else RunVerdict.ON_GOAL
    # A failed evidence source can never be reported as ON_GOAL.
    if sources_ok and not all(sources_ok.values()) and verdict is RunVerdict.ON_GOAL:
        verdict = RunVerdict.DEGRADED

    a = Audit(project=goal.project, window=window, run_verdict=verdict,
              findings=findings, indirect_share=share)
    if not actions and not tickets:
        a.notes.append("no tickets or actions observed in window")
    for src, ok in (sources_ok or {}).items():
        if not ok:
            a.notes.append(f"EVIDENCE SOURCE FAILED: {src} — absence of findings is not proof")
    return a


def goal_from_dict(d: dict[str, Any]) -> GoalRecord:
    return GoalRecord(
        project=d.get("project", ""),
        goal_text=d.get("goal_text", ""),
        source=GoalSource(d.get("source", "agent_inferred")),
        criteria=tuple(
            Criterion(
                key=c["key"], text=c.get("text", c["key"]),
                artifact_globs=tuple(c.get("artifact_globs", ())),
                keywords=tuple(c.get("keywords", ())),
                min_instances=int(c.get("min_instances", 1)),
            )
            for c in d.get("criteria", [])
        ),
        repos=tuple(d.get("repos", ())),
        registered_at=d.get("registered_at", ""),
    ).validate()


def goal_to_dict(g: GoalRecord) -> dict[str, Any]:
    return {
        "schema": "goal_drift.goal.v1",
        "project": g.project,
        "goal_text": g.goal_text,
        "source": g.source.value,
        "repos": list(g.repos),
        "registered_at": g.registered_at,
        "criteria": [
            {"key": c.key, "text": c.text, "artifact_globs": list(c.artifact_globs),
             "keywords": list(c.keywords), "min_instances": c.min_instances}
            for c in g.criteria
        ],
    }
