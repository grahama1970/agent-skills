"""Run bounded watchdog dispatches inside a visible Herdr pane.

Purpose
    A dispatch executed as a captured subprocess is invisible: if it hangs, the
    only evidence is a receipt that never appears. Running it as a named agent
    pane in a dedicated Herdr space makes the work watchable, and — because
    ``$monitor-herdr`` already scans spaces for stopped or confused panes — a
    stalled dispatch is detected by existing machinery with no new code.

    This module owns only the pane lifecycle. Issue selection stays in
    ``registry``, and what to run stays in ``handlers``.

Inputs
    A space label (default ``autoupdate``), a project id, an agent name, and the
    argv to run. The workstation manifest is created on first use and cached at
    ``config.state_root()/herdr-spaces/<label>.json``.

Outputs
    A ``PaneDispatch`` recording the agent name, manifest path, workspace id,
    every ``herdr-workstation`` invocation, and the terminal wait result.

Failure modes
    - Fails closed and returns ``ok=False`` when ``herdr-workstation`` is
      missing, when Herdr is unreachable, or when workstation creation fails.
      The caller records that in the receipt rather than crashing the tick.
    - ``wait`` is bounded. A pane that never reaches a terminal state returns
      ``timed_out=True`` and is left running and visible on purpose: the pane is
      the evidence, and ``$monitor-herdr`` is what probes it.
    - Never steals focus (``--no-focus``). A cron job must not grab the desktop.

Non-goals
    Asynchronous dispatch. The tick still blocks on a bounded wait so the
    existing lease/close semantics are unchanged. Making dispatch fire-and-forget
    needs a reconciliation path for leased-but-unfinished issues, which does not
    exist yet.
"""

from __future__ import annotations

import json
import shlex
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from . import config
from .core import run_cmd

#: Default space label for projects that update themselves.
DEFAULT_SPACE_LABEL = "autoupdate"

#: Tab created inside the space; matches herdr-workstation's default.
AGENT_TAB = "agents"

#: Stable Herdr agent label reported by every dispatch pane. It must not vary
#: per issue: $monitor-herdr selects panes with --include-agent, so a
#: per-issue label could never be filtered on. Probe stalled dispatches with:
#:   skills/monitor-herdr/run.sh tick --space autoupdate \
#:     --include-agent watchdog-dispatch
PANE_AGENT_LABEL = "watchdog-dispatch"

#: Terminal state to wait for. Herdr rejects ``done`` here with
#: "done is a UI attention state; use idle for CLI agent completion waits",
#: so completion waits must target ``idle``.
COMPLETION_STATE = "idle"

#: How long a failed dispatch pane stays alive after reporting ``blocked``.
#: A pane that exits immediately vanishes before $monitor-herdr's next tick,
#: so the failure would be invisible in the very space built to show it.
HOLD_SECONDS = 900


@dataclass
class PaneDispatch:
    """Result of running one bounded command inside a Herdr pane."""

    ok: bool = False
    agent_name: str = ""
    space_label: str = DEFAULT_SPACE_LABEL
    workspace_id: str | None = None
    manifest_path: str | None = None
    timed_out: bool = False
    exit_code: int | None = None
    sentinel_path: str | None = None
    error: str | None = None
    commands: list[dict[str, Any]] = field(default_factory=list)

    def as_receipt_block(self) -> dict[str, Any]:
        return {
            "backend": "herdr_pane",
            "ok": self.ok,
            "agent_name": self.agent_name,
            "space_label": self.space_label,
            "workspace_id": self.workspace_id,
            "manifest_path": self.manifest_path,
            "timed_out": self.timed_out,
            "exit_code": self.exit_code,
            "sentinel_path": self.sentinel_path,
            "error": self.error,
            "pane_agent_label": PANE_AGENT_LABEL,
            "observable_via": (
                "skills/monitor-herdr/run.sh tick "
                f"--space {self.space_label} --include-agent {PANE_AGENT_LABEL}"
                if self.workspace_id
                else None
            ),
        }


def workstation_cli() -> Path:
    """Return the path to the herdr-workstation skill entrypoint."""
    return config.workspace_root() / "agent-skills" / "skills" / "herdr-workstation" / "run.sh"


def manifest_cache_path(space_label: str) -> Path:
    return config.state_root() / "herdr-spaces" / f"{space_label}.json"


def available() -> bool:
    """Return whether the herdr-workstation entrypoint exists and is runnable."""
    cli = workstation_cli()
    return cli.is_file() and cli.stat().st_mode & 0o111 != 0


def _run_workstation(args: list[str], *, timeout_s: int = 120) -> dict[str, Any]:
    return run_cmd([str(workstation_cli()), *args], timeout_s=timeout_s)


def ensure_space(space_label: str = DEFAULT_SPACE_LABEL) -> tuple[Path | None, dict[str, Any]]:
    """Return the workstation manifest path for ``space_label``, creating it once.

    The manifest path is cached under the watchdog state root so repeated ticks
    reuse one space instead of opening a workspace per dispatch.
    """
    cache = manifest_cache_path(space_label)
    if cache.is_file():
        try:
            cached = json.loads(cache.read_text(encoding="utf-8"))
            manifest = Path(cached["manifest_path"])
            if manifest.is_file():
                return manifest, cached
        except (OSError, ValueError, KeyError) as exc:
            logger.error("unusable cached space manifest {}: {}", cache, exc)

    run_root = config.state_root() / "herdr-spaces" / space_label
    result = _run_workstation(
        [
            "workstation",
            "create",
            "--repo",
            str(config.workspace_root() / "agent-skills"),
            "--label",
            space_label,
            "--run-root",
            str(run_root),
            "--tab",
            AGENT_TAB,
            "--json",
        ]
    )
    if result["exit_code"] != 0:
        logger.error("herdr workstation create failed for {}: {}", space_label, result["stderr"])
        return None, {"create_result": result}

    try:
        payload = json.loads(result["stdout"])
        manifest = Path(payload["run_dir"]) / "workstation.json"
    except (ValueError, KeyError) as exc:
        logger.error("unparseable workstation manifest for {}: {}", space_label, exc)
        return None, {"create_result": result}

    cached = {
        "space_label": space_label,
        "manifest_path": str(manifest),
        "workspace_id": payload.get("workspace_id"),
        "run_dir": payload.get("run_dir"),
    }
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(cached, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest, cached


def build_pane_script(
    command: list[str], *, agent_name: str, sentinel: Path, timeout_s: int = 600
) -> str:
    """Wrap ``command`` so the pane reports its state and records a terminal exit code.

    Herdr's agent status is populated by provider integrations. An arbitrary
    command such as ``uv run tau handoff-command-loop`` has no such reporter, so
    ``herdr agent wait --status idle`` on a raw command times out even after the
    command succeeds — observed 2026-07-27: "timed out waiting for agent status
    change" against a pane that had already finished.

    The wrapper fixes both halves: it reports ``working``/``idle``/``blocked`` so
    the Herdr UI and ``$monitor-herdr`` see a truthful state, and it writes a
    sentinel JSON file so completion detection is a deterministic file read
    rather than an inference from a UI state.

    It also self-limits with ``timeout``. ``$monitor-herdr`` treats ``done``,
    ``idle``, ``blocked``, and ``unknown`` as stopped — ``working`` is *not* in
    that set. A hung command left reporting ``working`` would therefore never be
    flagged by the monitor. Bounding the command converts a hang into a
    ``blocked`` pane, which the monitor does select.
    """
    cli = shlex.quote(str(workstation_cli()))
    name = shlex.quote(agent_name)
    label = shlex.quote(PANE_AGENT_LABEL)
    sentinel_q = shlex.quote(str(sentinel))
    inner = shlex.join(command)
    # SIGTERM at the deadline, SIGKILL 30s later if the child ignores it.
    bounded = f"timeout --kill-after=30s {int(timeout_s)}s {inner}"
    return (
        f"{cli} agent report --agent {label} --state working "
        f"--custom-status watchdog-dispatch >/dev/null 2>&1 || true; "
        f"{bounded}; "
        "__rc=$?; "
        f'printf \'{{"exit_code": %d, "agent": "%s"}}\\n\' "$__rc" {name} > {sentinel_q}; '
        f'if [ "$__rc" -eq 0 ]; then __state=idle; else __state=blocked; fi; '
        f'{cli} agent report --agent {label} --state "$__state" >/dev/null 2>&1 || true; '
        f'if [ "$__rc" -ne 0 ]; then '
        f'echo "watchdog dispatch failed rc=$__rc; pane held for inspection"; sleep {HOLD_SECONDS}; '
        "fi; "
        'exit "$__rc"'
    )


def _await_sentinel(
    sentinel: Path, *, timeout_s: int, poll_s: float = 1.0
) -> dict[str, Any] | None:
    """Poll for the wrapper's sentinel file. Returns ``None`` on timeout."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if sentinel.is_file():
            try:
                return json.loads(sentinel.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                logger.error("unreadable dispatch sentinel {}: {}", sentinel, exc)
                return None
        time.sleep(poll_s)
    return None


def dispatch_in_pane(
    *,
    agent_name: str,
    command: list[str],
    role: str = "watchdog-dispatch",
    space_label: str = DEFAULT_SPACE_LABEL,
    timeout_s: int = 600,
    sentinel_dir: Path | None = None,
) -> PaneDispatch:
    """Start ``command`` as a named agent pane and wait, bounded, for it to finish."""
    dispatch = PaneDispatch(agent_name=agent_name, space_label=space_label)

    if not available():
        dispatch.error = (
            f"herdr-workstation entrypoint not found at {workstation_cli()}; "
            "install it or set dispatch_backend to 'local'"
        )
        logger.error("{}", dispatch.error)
        return dispatch

    manifest, meta = ensure_space(space_label)
    if manifest is None:
        dispatch.error = f"could not open Herdr space {space_label!r}"
        if "create_result" in meta:
            dispatch.commands.append(meta["create_result"])
        return dispatch
    dispatch.manifest_path = str(manifest)
    dispatch.workspace_id = meta.get("workspace_id")

    sentinel_root = sentinel_dir or (config.state_root() / "herdr-spaces" / "sentinels")
    sentinel_root.mkdir(parents=True, exist_ok=True)
    sentinel = sentinel_root / f"{agent_name}.json"
    sentinel.unlink(missing_ok=True)
    dispatch.sentinel_path = str(sentinel)

    start = _run_workstation(
        [
            "agent",
            "start",
            str(manifest),
            "--name",
            agent_name,
            "--role",
            role,
            "--command",
            f"bash -lc {shlex.quote(build_pane_script(command, agent_name=agent_name, sentinel=sentinel, timeout_s=timeout_s))}",
            "--tab",
            AGENT_TAB,
            "--no-focus",
            "--json",
        ]
    )
    dispatch.commands.append(start)
    if start["exit_code"] != 0:
        dispatch.error = f"herdr agent start failed: {start['stderr'].strip()[:400]}"
        logger.error("{}", dispatch.error)
        return dispatch

    outcome = _await_sentinel(sentinel, timeout_s=timeout_s + 45)
    if outcome is None:
        dispatch.timed_out = True
        dispatch.error = (
            f"pane {agent_name} produced no completion sentinel within {timeout_s}s; "
            f"left running and visible in space {space_label!r} for monitor-herdr to probe"
        )
        logger.warning("{}", dispatch.error)
        return dispatch

    dispatch.exit_code = int(outcome.get("exit_code", 1))
    dispatch.ok = dispatch.exit_code == 0
    if not dispatch.ok:
        dispatch.error = f"pane command exited {dispatch.exit_code}"
    return dispatch
