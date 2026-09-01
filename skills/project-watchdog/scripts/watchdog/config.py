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


def execution_lock_root() -> Path:
    return state_root() / "execution-locks"


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
#: diff or commit through the Tau repair DAG. Browser/web seats are advisory
#: strategy and ticket-planning lanes; they cannot author local repairs. Bare
#: ``codex`` is the local Codex CLI lane and is refused by the dispatch guard;
#: model seats such as ``gpt-5.5-high`` are valid when routed through
#: ``$ask tau-dag`` with a handler workspace.
DEFAULT_REPAIR_CREATOR = "gpt-5.5-high"

#: The reviewer seat. It must be a different provider family from the creator
#: and must be locally executing so it can run the ticket's proof command.
#: Browser seats such as ``webclaude`` are not acceptable repair reviewers.
DEFAULT_REPAIR_REVIEWER = "claude-fable-low"


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


class SeatIndependenceError(ValueError):
    """Creator and reviewer resolve to the same provider — no second opinion."""


#: Provider of each repair seat. The reviewer exists to be an INDEPENDENT second
#: opinion; a reviewer that shares the creator's provider reviews its own family's
#: work (observed: gpt-5.5-high == `codex exec --model gpt-5.5`, both OpenAI; and
#: webgpt is browser ChatGPT, also OpenAI). A reviewer must also be able to RUN
#: the ticket's live proof — a browser seat cannot execute code in the worktree.
_SEAT_PROVIDER = {
    "codex": "openai",
    "webgpt": "openai",
    "webgrok": "xai",
    "webclaude": "anthropic",
}
_BROWSER_SEATS = {"webgpt", "webclaude", "webgrok"}


#: OpenCode Go chat seat (`oc-<family>`) -> provider family. These are useful
#: model/review lanes, but they are not workspace-authoring repair creators.
#: Repo-changing OpenCode work needs the explicit OpenCode serve/transport
#: surface, not an `oc-*` chat handler with a Codex workspace bolted on.
_OC_FAMILY_PROVIDER = {
    "deepseek": "deepseek", "ds": "deepseek",
    "glm": "zhipu", "kimi": "moonshot", "minimax": "minimax",
    "qwen": "alibaba", "mimo": "xiaomi",
}
#: Seats that route through `codex exec` (the hobbled Codex CLI) regardless of
#: the model they name -- rejected as a creator/reviewer here (2026-08-22).
_CODEX_EXEC_SEATS_PREFIXES = ("gpt-", "codex-", "o1", "o3")


def seat_provider(seat: str) -> str:
    s = seat.strip().lower()
    if s in _SEAT_PROVIDER:
        return _SEAT_PROVIDER[s]
    if s.startswith("oc-"):
        return _OC_FAMILY_PROVIDER.get(s[3:].split("-")[0], "opencode")
    # `Codex-<model>` is a SciLLM route prefix, NOT the OpenAI Codex CLI: the
    # provider is the MODEL family after it (Codex-opus-5 -> anthropic).
    m = s[len("codex-"):] if s.startswith("codex-") else s
    if m.startswith(("opus", "sonnet", "haiku", "claude", "fable")):
        return "anthropic"
    if m.startswith(("gpt", "o1", "o3")) or m == "codex":
        return "openai"
    if m.startswith("grok"):
        return "xai"
    if m.startswith("gemini"):
        return "google"
    if m.startswith("deepseek"):
        return "deepseek"
    return "unknown"


def seat_uses_codex_exec(seat: str) -> bool:
    """True ONLY for the bare local Codex CLI coder lane (`codex`). SciLLM model
    handlers such as `Codex-opus-5-high` or `gpt-5.5-high` are Tau/SciLLM nodes,
    not the local codex subprocess, and are allowed."""
    return seat.strip().lower() == "codex"


def seat_can_run_code(seat: str) -> bool:
    """A reviewer must execute the ticket's live proof; a browser chat cannot.
    OpenCode Go chat (`oc-*`) and browser seats do not run shell commands."""
    s = seat.strip().lower()
    return not (s in _BROWSER_SEATS or s.startswith("web") or s.startswith("oc-"))


def seat_can_author_repair(seat: str) -> bool:
    """A creator must be able to author through the Tau repair workspace route."""
    s = seat.strip().lower()
    if s.startswith("gpt-") or s.startswith("codex-"):
        return True
    if s == "claude" or s.startswith("claude-"):
        return True
    return False


def assert_cross_provider_seats(creator: str, reviewer: str) -> None:
    """Fail loudly if the seats are codex, same-provider, or a non-code reviewer."""
    for role, seat in (("creator", creator), ("reviewer", reviewer)):
        if seat_uses_codex_exec(seat):
            raise SeatIndependenceError(
                f"repair {role} {seat!r} runs through the Codex CLI (codex exec); the Codex "
                "harness is not used. Use a workspace-capable model seat such as `gpt-5.5-high` "
                "or the local `claude` lane."
            )
    if not seat_can_author_repair(creator):
        raise SeatIndependenceError(
            f"repair creator {creator!r} is not a Tau repair authoring lane; "
            "use a workspace-capable model seat such as `gpt-5.5-high` or the local `claude` "
            "lane. `oc-*` is a chat/review route unless a separate OpenCode serve/transport "
            "authoring lane is configured."
        )
    cp, rp = seat_provider(creator), seat_provider(reviewer)
    if cp == rp:
        raise SeatIndependenceError(
            f"repair creator {creator!r} and reviewer {reviewer!r} are both provider {cp!r}; "
            "the reviewer must be a DIFFERENT provider to be an independent second opinion."
        )
    if not seat_can_run_code(reviewer):
        raise SeatIndependenceError(
            f"repair reviewer {reviewer!r} is a browser seat and cannot run the ticket's live "
            "proof in the worktree; the reviewer must be a locally-executing handler."
        )


def auto_land_main(project: dict[str, Any] | None = None) -> bool:
    """Whether a reviewer-passed repair lands directly on main for this project.

    Operator rule: while a project is alpha / pre-stable, `main` is the single
    branch and stays directly pushable — the branch-and-await-human-review dance
    is the stable-project workflow, not the alpha one. When true, a repair that
    the reviewer passed is rebased onto origin/main and pushed to main, and the
    ticket is closed, instead of being left as a branch awaiting a human. The
    reviewer verdict (which checked the ticket's live proof) is the gate."""
    if project and project.get("auto_land_main") is not None:
        return bool(project["auto_land_main"])
    return os.environ.get("PROJECT_WATCHDOG_AUTO_LAND_MAIN", "").strip().lower() in ("1", "true", "yes")


def repair_seats(project: dict[str, Any] | None = None) -> tuple[str, str]:
    """Resolve (creator, reviewer), enforcing cross-provider + code-running review."""
    creator = repair_creator(project)
    reviewer = repair_reviewer(project)
    assert_cross_provider_seats(creator, reviewer)
    return creator, reviewer


def login_shell() -> str:
    """The shell cron runs the tick through."""
    configured = os.environ.get("PROJECT_WATCHDOG_LOGIN_SHELL", "").strip()
    if configured:
        return configured
    shell = os.environ.get("SHELL", "").strip()
    return shell if shell and Path(shell).exists() else "/bin/bash"


def shell_init_file() -> Path | None:
    """The rc file holding the environment cron needs, if there is one.

    cron starts with a nearly empty environment and does not read the user's
    profile, so provider credentials exported from a shell rc are missing --
    every audit seat under cron failed `scillm_auth_invalid_api_key` while the
    same handler answered from an interactive shell.

    `-lc` does not help for zsh: a non-interactive login shell reads `.zprofile`
    and `.zlogin` but NOT `.zshrc`, which is where the key is. `-ic` does work,
    but an interactive shell under cron has no TTY and can emit control noise
    into the log. Sourcing the rc explicitly is the predictable option.
    """
    override = os.environ.get("PROJECT_WATCHDOG_SHELL_INIT", "").strip()
    if override:
        path = Path(override).expanduser()
        return path if path.is_file() else None
    shell = Path(login_shell()).name
    candidates = {"zsh": [".zshrc", ".zshenv"], "bash": [".bashrc", ".bash_profile"]}
    for name in candidates.get(shell, [".profile"]):
        path = Path.home() / name
        if path.is_file():
            return path
    return None


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

#: A downstream ticket is parked until every machine-readable upstream
#: ``blocked-by`` / ``depends_on`` reference has closed. ``ticket block
#: --blocked-by`` writes this label plus human-hold labels; watchdog may clear
#: only this dependency hold after it proves the upstream issue state.
UPSTREAM_BLOCKED_LABEL = "blocked:upstream"
DEPENDENCY_HOLD_LABELS = frozenset({UPSTREAM_BLOCKED_LABEL, "maintainer-blocked", "needs-human"})

#: Applied when a repair finished and left a branch for review. The ticket stays
#: open -- the work has not landed -- but it must stop being routable, or cron
#: re-dispatches it every tick and each dispatch resets the branch over the last
#: repair. Observed on watchdog-probe#1.
DONE_LABEL = "agent-done"
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

#: The closure-audit panel. Two seats, different model families, judging the
#: same closure independently.
#:
#: One seat is not enough and it is not the same problem as the repair reviewer:
#: a single model that systematically over-accepts would both pass bad repairs
#: and uphold bad closures, and nothing downstream would catch it. Two seats
#: make that require two models to fail the same way at once.
#:
#: ``webclaude`` is a browser transport test seat, not a better closure auditor:
#: it has no Ask-controlled reasoning effort and consumes Chrome/SURF capacity.
#: Use the local Claude Ask/Tau lane for Anthropic-family closure review.
DEFAULT_CLOSURE_AUDITORS = ("claude-opus-5-low", "gpt-5.5-xhigh")


def closure_auditors(project: dict[str, Any] | None = None) -> list[str]:
    """Handlers that judge a closure, per project then env then default."""
    configured = (project or {}).get("closure_auditors")
    if isinstance(configured, list) and configured:
        seats = [str(s).strip() for s in configured if str(s).strip()]
    else:
        raw = os.environ.get("PROJECT_WATCHDOG_CLOSURE_AUDITORS", "").strip()
        seats = [s.strip() for s in raw.split(",") if s.strip()] or list(DEFAULT_CLOSURE_AUDITORS)
    return seats


#: Independent seat for the completion attestation. Deliberately a browser
#: handler: when every ticket is closed and every closure has been upheld, the
#: whole judgement so far has come from the same API-routed models that did and
#: reviewed the work. WebGPT is a different transport and a different vantage
#: point, so "everything is done" is not self-certified.
DEFAULT_COMPLETION_ATTESTOR = "webgpt"

#: How often a project may be attested. Every ticket being closed is a durable
#: state, so without this the cron would re-ask the same question every minute.
COMPLETION_ATTEST_INTERVAL_SECONDS = _env_seconds(
    "PROJECT_WATCHDOG_COMPLETION_ATTEST_INTERVAL_SECONDS", 86_400
)


#: Retry window after an attestation that produced no verdict. Shorter than the
#: success interval: a crashed or unanswered run has told us nothing, so waiting
#: a full day before asking again wastes a day.
COMPLETION_ATTEST_RETRY_SECONDS = _env_seconds(
    "PROJECT_WATCHDOG_COMPLETION_ATTEST_RETRY_SECONDS", 3_600
)


def completion_attestor(project: dict[str, Any] | None = None) -> str:
    """Handler that attests a project is genuinely finished."""
    configured = str((project or {}).get("completion_attestor") or "").strip()
    if configured:
        return configured
    return os.environ.get("PROJECT_WATCHDOG_COMPLETION_ATTESTOR", "").strip() or (
        DEFAULT_COMPLETION_ATTESTOR
    )


#: How long to leave a closure alone after an audit that produced no verdict.
#: Observed 2026-07-28: a SciLLM auth failure made every audit inconclusive, and
#: the cron re-audited the SAME closure ten times in ten minutes because nothing
#: recorded the attempt. A provider outage should cost one attempt per hour, not
#: one per minute, and it must not starve the other 36 pending closures.
CLOSURE_AUDIT_RETRY_COOLDOWN_SECONDS = _env_seconds(
    "PROJECT_WATCHDOG_CLOSURE_RETRY_COOLDOWN_SECONDS", 3_600
)


#: Applied to a closed ticket whose closure a reviewer checked and accepted.
#: Its presence keeps the audit from re-reading the same closure every minute.
CLOSURE_VERIFIED_LABEL = "closure-verified"

#: Applied when the audit panel returned NEEDS_ATTENTION: the closure could not
#: be judged from the thread and stays closed-unverified. Durable for the same
#: reason as closure-verified — without it the panel re-answers the identical
#: question every tick (observed: one-minute window flash loop, 2026-07-31).
CLOSURE_UNVERIFIED_LABEL = "closure-unverified"

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

#: Hours (local, 24h) when heavy overnight batch work owns the machine. The
#: installed crontab runs nightly corpus, security, memory and sparta jobs
#: between 02:00 and 06:00 -- nightly corpus 02:00, security 03:00, memory
#: 03:45, sparta 04:17 and 06:00 -- so the window runs to 07:00 to cover the
#: last one. A repair dispatch landing inside it competes
#: for the same CPU, disk and provider quota as jobs that cannot be restarted
#: cheaply. The watchdog defers instead -- the issues are still there at 06:00.
#: Set PROJECT_WATCHDOG_QUIET_HOURS="" to disable, or "22-07" to widen.
QUIET_HOURS = os.environ.get("PROJECT_WATCHDOG_QUIET_HOURS", "2-7")


def quiet_window() -> tuple[int, int] | None:
    """Parsed quiet window, or None when disabled or malformed."""
    raw = (QUIET_HOURS or "").strip()
    if not raw:
        return None
    try:
        start, end = (int(part) for part in raw.split("-", 1))
    except (ValueError, TypeError):
        return None
    if not (0 <= start <= 23 and 0 <= end <= 23):
        return None
    return start, end


def tick_would_enter_quiet_hours(now=None, projected_seconds: int = 600) -> bool:
    """True when a tick starting now could still be running inside the window.

    A start-time-only check lets work begun at 01:59:59 run straight into the
    02:00 batch window -- the exact invasion the quiet hours exist to prevent.
    Adversarial review caught this; the gate now considers where the tick ends,
    not only where it starts.
    """
    import datetime as _dt

    if quiet_window() is None:
        return False
    start = now or _dt.datetime.now()
    return in_quiet_hours(start) or in_quiet_hours(start + _dt.timedelta(seconds=projected_seconds))


def in_quiet_hours(now=None) -> bool:
    """True inside the overnight window, wrapping past midnight correctly."""
    import datetime as _dt

    window = quiet_window()
    if window is None:
        return False
    start, end = window
    hour = (now or _dt.datetime.now()).hour
    # A window like 22-07 crosses midnight, so a plain start <= h < end is wrong.
    return start <= hour < end if start < end else (hour >= start or hour < end)
