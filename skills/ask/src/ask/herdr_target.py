"""Resolve a human-typed name to exactly one addressable Herdr pane.

Purpose
    ``/ask`` had no notion of Herdr panes at all, so there was no way to say
    "give this to the memory session". Naming alone cannot do it: on this
    workstation ``herdr pane list`` returns 122 panes, of which 6 have cwd
    ``memory`` and 44 have cwd ``agent-skills``. A resolver that guessed would
    pick the wrong agent most of the time, so ambiguity is a first-class
    result here rather than an error -- the caller is expected to hand the
    candidates to ``/interview``.

    Two filters do the real work before any disambiguation:

    - Addressability. A pane with no agent, or one Herdr reports as ``blocked``
      or ``unknown``, must never be typed into. That rule is monitor-herdr's,
      reused verbatim rather than reinvented, because it already encodes which
      panes have a real human or a wedged agent in them. Of the 6 ``memory``
      panes, one is ``unknown`` and drops out here.
    - Repo aliasing. The checkout directory and the GitHub repo disagree on
      this machine: ``~/workspace/experiments/memory`` is
      ``grahama1970/graph-memory-operator``. Someone routing issue #105 will
      type the repo name, and nothing on disk is called that.

Inputs
    The output of ``herdr pane list`` (JSON), plus a query that may be a pane
    id, a repo slug, or a directory name.

Outputs
    ``Resolution`` carrying the addressable candidates and whether the caller
    must interview.

Failure modes
    Herdr absent, not running, or emitting unparseable output yields an empty
    pane list and a resolution with ``reason`` set, never an exception.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

DEFAULT_HERDR_BIN = Path.home() / ".local" / "share" / "mise" / "installs" / "herdr" / "latest" / "herdr"

# monitor-herdr's rule: these two mean a human or a wedged agent owns the pane.
# Typing into them is the one action that is never safe.
OBSERVE_ONLY_STATUSES = frozenset({"blocked", "unknown"})
# `working` is a live agent mid-task. Addressable in principle, but never
# chosen implicitly -- interrupting running work needs an explicit decision.
BUSY_STATUSES = frozenset({"working"})


def herdr_bin() -> str:
    if DEFAULT_HERDR_BIN.exists():
        return str(DEFAULT_HERDR_BIN)
    return shutil.which("herdr") or "herdr"


@dataclass(frozen=True)
class HerdrPane:
    pane_id: str
    agent: str
    status: str
    cwd: str
    workspace_id: str = ""

    @property
    def project(self) -> str:
        """Directory basename, which is how a human names a pane."""
        return Path(self.cwd).name if self.cwd else ""

    @property
    def is_addressable(self) -> bool:
        """True when a prompt may be submitted to this pane at all."""
        if not self.agent:
            return False
        return self.status not in OBSERVE_ONLY_STATUSES

    @property
    def is_idle(self) -> bool:
        return self.is_addressable and self.status not in BUSY_STATUSES

    @property
    def session_name(self) -> str:
        """How a human refers to this session: workspace plus pane."""
        return self.pane_id

    def describe(self) -> str:
        return f"{self.pane_id} [{self.agent}/{self.status}] {self.cwd}"


@dataclass(frozen=True)
class Resolution:
    query: str
    candidates: tuple[HerdrPane, ...] = ()
    reason: str = ""

    @property
    def needs_interview(self) -> bool:
        """More than one live pane matched; a guess would be a coin flip."""
        return len(self.candidates) > 1

    @property
    def resolved(self) -> HerdrPane | None:
        return self.candidates[0] if len(self.candidates) == 1 else None

    def interview_options(self) -> list[dict[str, str]]:
        """Candidates shaped for /interview.

        The three facts a human needs to tell identical names apart are the
        session, the model driving it, and the directory it is working in.
        Anything less and the choice is still a guess, just the human's.
        """
        return [
            {
                "label": pane.session_name,
                "description": f"model: {pane.agent or 'unknown'} ({pane.status}) | dir: {pane.cwd}",
                "pane_id": pane.pane_id,
                "model": pane.agent,
                "directory": pane.cwd,
            }
            for pane in self.candidates
        ]

    def interview_payload(self, *, question: str = "") -> dict[str, object]:
        """A ready-to-run /interview question document."""
        return {
            "version": 2,
            "title": "Which session did you want to target?",
            "context": (
                f"{len(self.candidates)} Herdr sessions answer to "
                f"'{self.query}'. Pick the one to receive this work."
            ),
            "questions": [
                {
                    "id": "herdr_session",
                    "header": "Session",
                    "text": question or f"Which '{self.query}' session should receive this?",
                    "multi_select": False,
                    "options": [
                        {"label": o["label"], "description": o["description"]}
                        for o in self.interview_options()
                    ],
                }
            ],
        }


def list_panes(*, bin_path: str | None = None, timeout: float = 20.0) -> list[HerdrPane]:
    """Return every pane Herdr reports, or an empty list if it cannot be asked."""
    command = [bin_path or herdr_bin(), "pane", "list"]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if completed.returncode != 0:
        return []
    return parse_panes(completed.stdout)


def parse_panes(stdout: str) -> list[HerdrPane]:
    """Parse `herdr pane list` output; unrecognized shapes yield no panes."""
    try:
        payload = json.loads(stdout)
    except (ValueError, TypeError):
        return []
    raw = payload.get("result", {}).get("panes") if isinstance(payload, dict) else None
    if not isinstance(raw, list):
        return []
    panes: list[HerdrPane] = []
    for entry in raw:
        if not isinstance(entry, dict) or not entry.get("pane_id"):
            continue
        panes.append(
            HerdrPane(
                pane_id=str(entry.get("pane_id")),
                agent=str(entry.get("agent") or ""),
                status=str(entry.get("agent_status") or "unknown").lower(),
                cwd=str(entry.get("cwd") or ""),
                workspace_id=str(entry.get("workspace_id") or ""),
            )
        )
    return panes


def _repo_aliases(panes: list[HerdrPane], repo_map: dict[str, str] | None) -> dict[str, str]:
    """Map a GitHub repo slug to the directory name it is checked out as.

    Callers may pass an explicit map; otherwise the remote is read per unique
    cwd. The mismatch is real and load-bearing here: nothing on disk is named
    ``graph-memory-operator``.
    """
    if repo_map is not None:
        return {k.lower(): v for k, v in repo_map.items()}
    aliases: dict[str, str] = {}
    for cwd in {p.cwd for p in panes if p.cwd}:
        try:
            completed = subprocess.run(
                ["git", "-C", cwd, "remote", "get-url", "origin"],
                capture_output=True, text=True, timeout=10, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if completed.returncode != 0:
            continue
        url = completed.stdout.strip()
        if not url:
            continue
        slug = url.rsplit("/", 1)[-1].removesuffix(".git")
        if slug:
            aliases[slug.lower()] = Path(cwd).name
    return aliases


def resolve(
    query: str,
    panes: list[HerdrPane],
    *,
    repo_map: dict[str, str] | None = None,
    include_busy: bool = False,
) -> Resolution:
    """Resolve a pane id, repo slug, or project name to addressable panes.

    An exact pane id short-circuits everything: the caller already knows which
    pane it means, and a name-based search could only muddy that.
    """
    wanted = query.strip()
    if not wanted:
        return Resolution(query=query, reason="empty query")
    if not panes:
        return Resolution(query=query, reason="herdr reported no panes")

    exact = [p for p in panes if p.pane_id == wanted]
    if exact:
        pane = exact[0]
        if not pane.is_addressable:
            return Resolution(query=query, reason=f"{pane.pane_id} is {pane.status}; not addressable")
        return Resolution(query=query, candidates=(pane,))

    needle = wanted.lower()
    # A repo slug resolves to its checkout directory before matching, so
    # "graph-memory-operator" and "memory" reach the same panes.
    aliases = _repo_aliases(panes, repo_map)
    needle = aliases.get(needle, needle)

    matched = [p for p in panes if p.project.lower() == needle]
    if not matched:
        return Resolution(query=query, reason=f"no pane has cwd named {needle!r}")

    live = [p for p in matched if p.is_addressable]
    if not live:
        return Resolution(
            query=query,
            reason=f"{len(matched)} pane(s) named {needle!r} but none addressable",
        )
    if not include_busy:
        idle = [p for p in live if p.is_idle]
        if not idle:
            # Every match is mid-task. Offering them would let `send` interrupt
            # running work without anyone deciding to; name the situation and
            # the flag that overrides it instead.
            return Resolution(
                query=query,
                reason=(
                    f"{len(live)} pane(s) named {needle!r} are busy; "
                    "pass include_busy to interrupt them"
                ),
            )
        live = idle
    return Resolution(query=query, candidates=tuple(sorted(live, key=lambda p: p.pane_id)))


def send(
    pane: HerdrPane,
    prompt: str,
    *,
    bin_path: str | None = None,
    timeout: float = 30.0,
) -> dict[str, object]:
    """Submit a prompt to one pane via `herdr pane run`, which appends Enter.

    Deliberately the same transport monitor-herdr uses. Submission is reported
    from herdr's own exit status; this is delivery proof, not proof the agent
    understood or acted on the prompt.
    """
    command = [bin_path or herdr_bin(), "pane", "run", pane.pane_id, prompt]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"submitted": False, "pane_id": pane.pane_id, "error": str(exc)}
    return {
        "submitted": completed.returncode == 0,
        "pane_id": pane.pane_id,
        "agent": pane.agent,
        "cwd": pane.cwd,
        "returncode": completed.returncode,
        "stderr": (completed.stderr or "")[-300:],
        "transport": "herdr_pane_run",
    }
