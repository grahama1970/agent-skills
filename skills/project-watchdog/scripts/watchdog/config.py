"""Filesystem paths, routing markers, and environment resolution for project-watchdog.

Purpose
    Single source of truth for every path and constant the watchdog touches, so
    no other module hardcodes a location or re-derives one from ``$HOME``.

Inputs
    Environment variables, all optional:

    ``PROJECT_WATCHDOG_STATE_ROOT``
        Overrides the durable state root (default ``~/.local/state/project-watchdog``).
        Tests set this to a temporary directory to keep real receipts untouched.
    ``PROJECT_WATCHDOG_PROJECTS_PATH``
        Overrides the project registry file. Sanity checks point this at a
        fixture so a gate about idle behaviour is not rewritten every time a
        real project gains a ticket.
    ``PROJECT_WATCHDOG_REPAIR_CREATOR`` / ``PROJECT_WATCHDOG_REPAIR_REVIEWER``
        Override the two repair seats. Defaults are set so the reviewer is a
        different model family from the creator; a reviewer that shares the
        creator's blind spots is not a second opinion.
    ``PROJECT_WATCHDOG_WORKSPACE``
        Overrides the workspace root that holds project worktrees
        (default ``~/workspace/experiments``).
    ``UV_BIN``
        Overrides the ``uv`` executable path (default ``~/.local/bin/uv``,
        falling back to whatever ``uv`` resolves to on ``PATH``).

Outputs
    Module-level ``Path`` constants. Every path is absolute and fully expanded.

Failure modes
    ``resolve_uv_bin`` returns the bare string ``"uv"`` when no executable is
    found, deferring the failure to the subprocess call so the resulting receipt
    records a real exit code instead of raising during import.

History
    Until 2026-07-27 this module's constants were written as
    ``Path("${HOME}/workspace/...")``. Python does not expand ``${HOME}``, so
    every such path was a *relative* path literally named ``${HOME}/...`` and
    none of them existed. Any dispatch would have failed. Use ``expanduser()``
    or the helpers here, never a shell-style variable inside ``Path(...)``.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from loguru import logger

from .dotenv_helper import get as env_get
from .dotenv_helper import load_env

load_env()

SKILL_DIR = Path(__file__).resolve().parents[2]
REGISTRY_DIR = SKILL_DIR / "registry"
PROJECTS_PATH = REGISTRY_DIR / "projects.json"

#: $ask compiles the repair DAG and Tau executes it. Sibling skill, resolved
#: from this skill's own location so it follows the checkout it runs from.
ASK_RUN_SH = SKILL_DIR.parent / "ask" / "run.sh"


def ask_run_sh() -> Path:
    """Path to the $ask runner used by the ticket-repair lane."""
    return ASK_RUN_SH
#: Seed state, versioned with the skill. Runtime state is NOT written here.
STATE_SEED_PATH = REGISTRY_DIR / "state.json"


def _env_path(name: str, default: Path) -> Path:
    raw = env_get(name)
    if not raw:
        return default
    return Path(raw).expanduser().resolve()


def state_root() -> Path:
    """Return the durable state root, honouring ``PROJECT_WATCHDOG_STATE_ROOT``."""
    return _env_path(
        "PROJECT_WATCHDOG_STATE_ROOT",
        Path.home() / ".local" / "state" / "project-watchdog",
    )


def log_dir() -> Path:
    return state_root() / "logs"


def receipt_root() -> Path:
    return state_root() / "receipts"


def lock_dir() -> Path:
    return state_root() / "lock"


def state_path() -> Path:
    """Where mutable watchdog state actually lives.

    NOT inside the repository. ``registry/state.json`` is tracked, and the tick
    writes state on every run -- pausing a project, recording last_served -- so
    the watchdog dirtied its own skill directory continuously. With readiness
    judged per target that made every ticket against ``skills/project-watchdog``
    permanently unrepairable, and in any checkout it produced endless spurious
    diffs. Logs and receipts already live under the state root; state belongs
    with them.

    Seeded once from the versioned ``registry/state.json`` so a fresh install
    starts from the committed defaults.
    """
    live = state_root() / "state.json"
    if not live.exists() and STATE_SEED_PATH.is_file():
        live.parent.mkdir(parents=True, exist_ok=True)
        live.write_text(STATE_SEED_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    return live


def projects_path() -> Path:
    """Return the project registry, honouring ``PROJECT_WATCHDOG_PROJECTS_PATH``."""
    return _env_path("PROJECT_WATCHDOG_PROJECTS_PATH", PROJECTS_PATH)


#: The creator seat. Must be able to mutate a workspace and produce a real git
#: diff, which is the local Codex CLI lane -- an answer-only subagent cannot.
DEFAULT_REPAIR_CREATOR = "codex"

#: The reviewer seat. Deliberately a different model family from the creator:
#: `gpt-5.5-xhigh` resolves to `codex exec --model ...`, the same family the
#: creator runs, so it shared the creator's blind spots and was a second pass
#: rather than a second opinion.
DEFAULT_REPAIR_REVIEWER = "claude-opus-4-8"


def repair_creator(project: dict[str, Any] | None = None) -> str:
    """Handler that writes the fix, per project then env then default."""
    return _repair_seat(project, "repair_creator", "PROJECT_WATCHDOG_REPAIR_CREATOR",
                        DEFAULT_REPAIR_CREATOR)


def repair_reviewer(project: dict[str, Any] | None = None) -> str:
    """Handler that judges the fix, per project then env then default."""
    return _repair_seat(project, "repair_reviewer", "PROJECT_WATCHDOG_REPAIR_REVIEWER",
                        DEFAULT_REPAIR_REVIEWER)


def _repair_seat(project: dict[str, Any] | None, key: str, env: str, default: str) -> str:
    configured = str((project or {}).get(key) or "").strip()
    if configured:
        return configured
    return os.environ.get(env, "").strip() or default


def repair_worktrees_dir() -> Path:
    """Where per-ticket repair worktrees are created.

    A repair is authored in its own worktree, never in the registered checkout.
    That checkout is where a human works: agent-skills had 1,911 dirty entries
    and cron lanes writing tracked files mid-run, and it sat 60 commits behind
    origin/main, so a repair authored there would build on stale code and
    collide with uncommitted work that is not the watchdog's to touch.
    """
    return state_root() / "repair-worktrees"


def event_log_path() -> Path:
    return log_dir() / "project-watchdog.log"


def cron_log_path() -> Path:
    return log_dir() / "cron.log"


def workspace_root() -> Path:
    """Return the root directory that contains project worktrees."""
    return _env_path(
        "PROJECT_WATCHDOG_WORKSPACE",
        Path.home() / "workspace" / "experiments",
    )


def resolve_uv_bin() -> str:
    """Return the ``uv`` executable path, or the bare name if none is found."""
    override = env_get("UV_BIN")
    if override:
        candidate = Path(override).expanduser()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    default = Path.home() / ".local" / "bin" / "uv"
    if default.is_file() and os.access(default, os.X_OK):
        return str(default)
    found = shutil.which("uv")
    return found or "uv"


def agents_root() -> Path:
    return workspace_root() / "agent-skills" / "agents"


CRON_MARKER = "# project-watchdog global issue cron"
TAU_REPAIR_MARKER = "project-watchdog-action:add-tau-coder-command-spec"
TAU_HANDOFF_DISPATCH_MARKER = "project-watchdog-action:tau-handoff-dispatch"
TAU_ACTIVE_GOAL_HASH = "sha256:" + "1" * 64

LEASE_LABEL = "agent-active"
BLOCKED_LABEL = "agent-blocked"
DONE_LABEL = "agent-done"
READY_LABEL = "agent-work"

#: Labels that mean a human owns the next decision. Routable work must carry
#: none of these, so a maintainer parking a ticket is always honoured.
HUMAN_HOLD_LABELS = frozenset(
    {"needs-human", "maintainer-blocked", "next:human", "status:deferred"}
)

#: Labels that mean some agent already holds this ticket. Distinct from a human
#: hold: nobody is asking for a decision, the work is simply taken.
#:
#: ``agent-active`` is this watchdog's own lease. ``maintainer-active`` is what
#: ``ticket lease`` writes (gh-ticket-tools.sh), so it is the label any other
#: project agent holds a ticket with. Omitting it meant the watchdog would
#: dispatch a second agent onto a skill someone was already editing, and both
#: would write the same files.
LEASE_LABELS = frozenset({"agent-active", "maintainer-active"})

#: A lock older than this is treated as abandoned by a crashed or killed tick.
LOCK_STALE_SECONDS = 900


def _env_seconds(name: str, default: int) -> int:
    raw = env_get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.error("{} is not an integer: {!r}; using default {}", name, raw, default)
        return default
    return value if value > 0 else default


#: A lease older than this is abandoned. The acquisition timestamp comes from
#: GitHub's label event, not the issue's mutable ``updatedAt`` value, so later
#: comments do not keep a dead holder alive indefinitely.
LEASE_STALE_SECONDS = _env_seconds("PROJECT_WATCHDOG_LEASE_STALE_SECONDS", 86_400)

#: How long a project may report "nothing routable" before that stops counting
#: as a steady state. Silence is not success: before 2026-07-27 this skill
#: logged 41,607 consecutive idle ticks over roughly a month, every one of them
#: reported as ok, while a label mismatch made a match impossible.
NOOP_ESCALATION_SECONDS = _env_seconds("PROJECT_WATCHDOG_IDLE_ESCALATION_SECONDS", 86_400)

#: Applied to a closed ticket whose closure a reviewer checked and accepted.
#: Its presence keeps the audit from re-reading the same closure every minute.
CLOSURE_VERIFIED_LABEL = "closure-verified"

#: How far back the closure audit looks. A closure from months ago is history,
#: not something to reopen.
CLOSURE_AUDIT_WINDOW_SECONDS = _env_seconds("PROJECT_WATCHDOG_CLOSURE_AUDIT_WINDOW_SECONDS", 604_800)

#: How many times one ticket may be reopened by the audit before it stops being
#: reopened and asks for a person. Without a bound, a reviewer that always fails
#: reopens the same ticket forever.
CLOSURE_AUDIT_MAX_REOPENS = int(os.environ.get("PROJECT_WATCHDOG_CLOSURE_MAX_REOPENS", "2"))

#: Once escalated, how long before the watchdog persists another escalation
#: receipt. Without this, escalation would reintroduce one receipt directory per
#: minute — the exact disk churn the retention policy removed.
NOOP_RENOTIFY_SECONDS = _env_seconds("PROJECT_WATCHDOG_IDLE_RENOTIFY_SECONDS", 86_400)
