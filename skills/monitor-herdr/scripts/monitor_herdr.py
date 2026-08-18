#!/usr/bin/env python3
"""Monitor Herdr workspaces and restart agents that stopped too early."""

from __future__ import annotations

import json
import os
import sys
import fcntl
from pathlib import Path
from typing import Any

from dotenv import find_dotenv, load_dotenv
from loguru import logger
import typer

from change_tracking import record_prompt_signature
from cron_support import install_cron, status_payload
from file_viewer import open_file_viewer
from herdr_socket import DEFAULT_SOCKET_PATH, HerdrClient
from monitor_common import (
    LOCK_PATH,
    LOG_DIR,
    RECEIPT_ROOT,
    STATE_PATH,
    append_jsonl,
    current_epoch,
    ensure_dirs,
    log_event,
    now_iso,
    timestamp,
    write_json,
)
from pane_classification import (
    apply_no_change_suppression,
    classify_pane,
    load_agent_index,
    prune_stopped_observations,
    resolve_workspace,
    update_stopped_observation,
)
from prompt_submission import (
    candidate_without_text,
    prompt_send_failed,
    send_prompt,
)
from prompt_builder import build_prompt
from workspace_sweep import DEFAULT_STALE_LABEL_PATTERNS, close_workspaces, sweep_workspaces

load_dotenv(find_dotenv(usecwd=True), override=False)

SKILL_DIR = Path(__file__).resolve().parents[1]
CRON_MARKER = "# monitor-herdr herdr cron"
DEFAULT_SPACE = "codex"
DEFAULT_CWD_PREFIX = str(Path.home() / "workspace" / "experiments")
DEFAULT_STOPPED_STATUSES = ("done", "idle", "blocked", "unknown")
DEFAULT_COOLDOWN_SECONDS = 60 * 60
DEFAULT_UNCONFIRMED_COOLDOWN_SECONDS = 10 * 60
DEFAULT_MIN_STOPPED_SECONDS = 0


app = typer.Typer(add_completion=False, help="Monitor Herdr spaces for stopped/confused agents.")
LOCK_HANDLE: Any | None = None






@app.command("tick")
def tick_command(
    apply: bool = typer.Option(False, "--apply", help="Send restart/intervention prompts to stopped panes."),
    space: str = typer.Option(DEFAULT_SPACE, "--space", help="Herdr workspace id, number, or label. Use '*' for all."),
    socket_path: Path = typer.Option(DEFAULT_SOCKET_PATH, "--socket-path", help="Herdr Unix socket path."),
    cwd_prefix: str = typer.Option(DEFAULT_CWD_PREFIX, "--cwd-prefix", help="Only monitor panes under this cwd prefix."),
    include_agent: list[str] = typer.Option(["codex", "claude"], "--include-agent", help="Agent labels to monitor."),
    stopped_status: list[str] = typer.Option(list(DEFAULT_STOPPED_STATUSES), "--stopped-status", help="Statuses treated as stopped."),
    cooldown_seconds: int = typer.Option(DEFAULT_COOLDOWN_SECONDS, "--cooldown-seconds", min=0, help="Per-pane prompt cooldown."),
    unconfirmed_cooldown_seconds: int = typer.Option(DEFAULT_UNCONFIRMED_COOLDOWN_SECONDS, "--unconfirmed-cooldown-seconds", min=0, help="Cooldown for prompt attempts that modified input but were not confirmed submitted."),
    min_stopped_seconds: int = typer.Option(DEFAULT_MIN_STOPPED_SECONDS, "--min-stopped-seconds", min=0, help="Minimum observed stopped/idle age before prompting."),
    max_prompts: int = typer.Option(20, "--max-prompts", min=1, help="Maximum prompts per tick."),
    only_obvious_early_stops: bool = typer.Option(False, "--only-obvious-early-stops", help="Prompt only stopped panes with early-stop transcript markers."),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Print JSON receipt."),
) -> None:
    """Run one bounded Herdr monitor tick."""
    ensure_dirs()
    exit_code, receipt = tick(
        apply=apply,
        space=space,
        socket_path=socket_path,
        cwd_prefix=cwd_prefix,
        include_agents={item for item in include_agent if item},
        stopped_statuses={item.lower() for item in stopped_status},
        cooldown_seconds=cooldown_seconds,
        unconfirmed_cooldown_seconds=unconfirmed_cooldown_seconds,
        min_stopped_seconds=min_stopped_seconds,
        max_prompts=max_prompts,
        only_obvious_early_stops=only_obvious_early_stops,
    )
    if json_output:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    raise typer.Exit(exit_code)


@app.command("sweep-workspaces")
def sweep_workspaces_command(
    apply: bool = typer.Option(False, "--apply", help="Close the stale workspaces instead of only reporting them."),
    socket_path: Path = typer.Option(DEFAULT_SOCKET_PATH, "--socket-path", help="Herdr Unix socket path."),
    stale_pattern: list[str] = typer.Option(list(DEFAULT_STALE_LABEL_PATTERNS), "--stale-pattern", help="Regex matched against the workspace label."),
    max_pane_count: int = typer.Option(8, "--max-pane-count", min=1, help="Refuse to close a workspace with more panes than this."),
    max_closes: int = typer.Option(25, "--max-closes", min=1, help="Maximum workspaces closed in one sweep."),
) -> None:
    """Report, and with --apply close, disposable leftover Herdr workspaces.

    Fail-closed: a workspace is closed only when its label matches a disposable
    pattern, it is not focused, it holds no live agent, and it is small enough to
    be eval debris. Everything else is reported and left alone.
    """
    ensure_dirs()
    client = HerdrClient(socket_path)
    try:
        result = client.call("workspace.list", {})
    except RuntimeError as exc:
        print(json.dumps({"schema": "agent_skills.monitor_herdr.sweep.v1", "ok": False, "status": "BLOCKED", "error": str(exc)}, indent=2))
        raise typer.Exit(2)

    payload = sweep_workspaces(
        result.get("workspaces", []),
        stale_patterns=tuple(stale_pattern),
        max_pane_count=max_pane_count,
        max_closes=max_closes,
    )
    payload["schema"] = "agent_skills.monitor_herdr.sweep.v1"
    payload["applied"] = apply
    if apply and payload["selected"]:
        payload["closed"] = close_workspaces(client, payload["selected"])
        payload["closed_total"] = sum(1 for item in payload["closed"] if item.get("closed"))
        payload["ok"] = payload["closed_total"] == len(payload["selected"])
        payload["status"] = "WORKSPACES_CLOSED" if payload["ok"] else "NEEDS_ATTENTION"
    else:
        payload["ok"] = True
        payload["status"] = "OBSERVED"
    print(json.dumps(payload, indent=2, sort_keys=True))
    raise typer.Exit(0 if payload["ok"] else 1)


@app.command("status")
def status_command() -> None:
    """Report installed cron, latest receipts, and monitor state."""
    ensure_dirs()
    print(json.dumps(status_payload(), indent=2, sort_keys=True))


@app.command("install-cron")
def install_cron_command(
    apply: bool = typer.Option(False, "--apply", help="Install the cron entry."),
    minute: str = typer.Option("*/10", "--minute", help="Cron minute field."),
    space: str = typer.Option(DEFAULT_SPACE, "--space", help="Herdr space/workspace to monitor."),
    apply_prompts: bool = typer.Option(True, "--apply-prompts/--dry-run-prompts", help="Cron should send restart prompts."),
    cwd_prefix: str = typer.Option(DEFAULT_CWD_PREFIX, "--cwd-prefix", help="Cron cwd-prefix scope."),
    min_stopped_seconds: int = typer.Option(600, "--min-stopped-seconds", min=0, help="Cron prompt threshold based on observed stopped age."),
) -> None:
    """Install or preview a 10 minute cron entry."""
    ensure_dirs()
    exit_code, payload = install_cron(
        apply=apply,
        minute=minute,
        space=space,
        apply_prompts=apply_prompts,
        cwd_prefix=cwd_prefix,
        min_stopped_seconds=min_stopped_seconds,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    raise typer.Exit(exit_code)


@app.command("probe-text")
def probe_text_command(
    pane_id: str = typer.Option(..., "--pane-id", help="Herdr pane id."),
    agent: str = typer.Option("agent", "--agent", help="Agent label."),
    reason: str = typer.Option("early_stop", "--reason", help="Selection reason."),
    action: str = typer.Option("restart_continue", "--action", help="restart_continue or needs_human"),
    cwd: str = typer.Option("", "--cwd", help="Pane cwd."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON instead of text."),
) -> None:
    """Render the exact prompt sent to a stopped agent."""
    text = build_prompt({
        "pane_id": pane_id,
        "agent": agent,
        "cwd": cwd,
        "selection_reasons": [reason],
        "action": action,
    })
    if json_output:
        print(json.dumps({
            "schema": "agent_skills.monitor_herdr.probe.v1",
            "pane_id": pane_id,
            "agent": agent,
            "action": action,
            "text": text,
        }, indent=2, sort_keys=True))
    else:
        print(text)


@app.command("open-file")
def open_file_command(
    target: str | None = typer.Argument(None, help="File path, path:line, or fuzzy query when --query is omitted."),
    query: str | None = typer.Option(None, "--query", "-q", help="Fuzzy file query to resolve before opening."),
    root: Path | None = typer.Option(None, "--root", help="Workspace/repo root for relative paths and fuzzy search."),
    focus: bool = typer.Option(True, "--focus/--no-focus", help="Focus the new Files pane."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Resolve and print the launch plan without opening Herdr."),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Print JSON receipt."),
) -> None:
    """Open an exact or fuzzy-resolved workspace file in herdr-file-viewer."""
    ensure_dirs()
    exit_code, receipt = open_file_viewer(
        target=target,
        query=query,
        root=root,
        focus=focus,
        dry_run=dry_run,
    )
    if json_output:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    raise typer.Exit(exit_code)
















































def cooldown_for_prompt_state(
    prompt_state: dict[str, Any],
    *,
    cooldown_seconds: int,
    unconfirmed_cooldown_seconds: int,
) -> int:
    if prompt_state.get("input_modified") and prompt_state.get("submit_confirmed") is False:
        return min(cooldown_seconds, unconfirmed_cooldown_seconds) if cooldown_seconds > 0 else unconfirmed_cooldown_seconds
    return cooldown_seconds


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"schema": "agent_skills.monitor_herdr.state.v1", "prompts": {}}
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.error("Monitor state JSON is corrupt: {}", STATE_PATH)
        return {"schema": "agent_skills.monitor_herdr.state.v1", "prompts": {}, "input_suppressed": True, "state_error": "corrupt_json"}
    if not isinstance(payload, dict):
        return {"schema": "agent_skills.monitor_herdr.state.v1", "prompts": {}, "input_suppressed": True, "state_error": "invalid_state_shape"}
    payload.setdefault("schema", "agent_skills.monitor_herdr.state.v1")
    payload.setdefault("prompts", {})
    return payload


def acquire_lock(run_id: str) -> bool:
    global LOCK_HANDLE
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCK_HANDLE = LOCK_PATH.open("a+", encoding="utf-8")
    try:
        fcntl.flock(LOCK_HANDLE.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        LOCK_HANDLE.close()
        LOCK_HANDLE = None
        return False
    LOCK_HANDLE.seek(0)
    LOCK_HANDLE.truncate()
    LOCK_HANDLE.write(json.dumps({"run_id": run_id, "pid": os.getpid(), "ts": now_iso()}) + "\n")
    LOCK_HANDLE.flush()
    return True


def release_lock() -> None:
    global LOCK_HANDLE
    if LOCK_HANDLE is None:
        return
    try:
        fcntl.flock(LOCK_HANDLE.fileno(), fcntl.LOCK_UN)
        LOCK_HANDLE.close()
    except OSError:
        logger.error("Could not release monitor lock at {}", LOCK_PATH)
    finally:
        LOCK_HANDLE = None


def tick(
    *,
    apply: bool,
    space: str,
    socket_path: Path,
    cwd_prefix: str,
    include_agents: set[str],
    stopped_statuses: set[str],
    cooldown_seconds: int,
    unconfirmed_cooldown_seconds: int,
    min_stopped_seconds: int,
    max_prompts: int,
    only_obvious_early_stops: bool,
) -> tuple[int, dict[str, Any]]:
    run_id = f"monitor-herdr-{timestamp()}"
    receipt_dir = RECEIPT_ROOT / run_id
    receipt_dir.mkdir(parents=True, exist_ok=True)
    events_path = receipt_dir / "events.jsonl"
    receipt: dict[str, Any] = {
        "schema": "agent_skills.monitor_herdr.tick_receipt.v1",
        "run_id": run_id,
        "mocked": False,
        "live": True,
        "api": "herdr_socket",
        "apply": apply,
        "invocation_source": os.environ.get("MONITOR_HERDR_INVOCATION_SOURCE", "cli"),
        "receipt_dir": str(receipt_dir),
        "events_path": str(events_path),
        "log_file": str(LOG_DIR / "monitor-herdr.log"),
        "state_path": str(STATE_PATH),
        "selection": {
            "space": space,
            "socket_path": str(socket_path),
            "cwd_prefix": cwd_prefix,
            "include_agents": sorted(include_agents),
            "stopped_statuses": sorted(stopped_statuses),
            "cooldown_seconds": cooldown_seconds,
            "unconfirmed_cooldown_seconds": unconfirmed_cooldown_seconds,
            "min_stopped_seconds": min_stopped_seconds,
            "max_prompts": max_prompts,
            "only_obvious_early_stops": only_obvious_early_stops,
        },
        "workspace": None,
        "api_trace": [],
        "observed_panes": 0,
        "stopped_panes": [],
        "selected_panes": [],
        "prompts": [],
        "errors": [],
    }
    append_jsonl(events_path, {"event": "tick_start", "ts": now_iso(), "apply": apply, "space": space})
    log_event(run_id, "tick_start", apply=apply, space=space)

    if not acquire_lock(run_id):
        receipt.update({"ok": False, "status": "BLOCKED", "errors": ["lock already held"]})
        return finish(receipt, 1)
    try:
        client = HerdrClient(socket_path)
        try:
            result: tuple[int, dict[str, Any]]
            try:
                client.call("ping", {})
            except RuntimeError as exc:
                receipt.update({"ok": False, "status": "BLOCKED", "errors": [f"Herdr ping failed: {exc}"]})
                result = finish(receipt, 2)
            else:
                result = tick_locked(
                    client=client,
                    receipt=receipt,
                    events_path=events_path,
                    apply=apply,
                    space=space,
                    cwd_prefix=cwd_prefix,
                    include_agents=include_agents,
                    stopped_statuses=stopped_statuses,
                    cooldown_seconds=cooldown_seconds,
                    unconfirmed_cooldown_seconds=unconfirmed_cooldown_seconds,
                    min_stopped_seconds=min_stopped_seconds,
                    max_prompts=max_prompts,
                    only_obvious_early_stops=only_obvious_early_stops,
                )
            receipt["api_trace"] = client.trace
            if receipt.get("receipt_path"):
                write_json(Path(str(receipt["receipt_path"])), receipt)
            return result
        finally:
            receipt["api_trace"] = client.trace
    finally:
        release_lock()


def tick_locked(
    *,
    client: HerdrClient,
    receipt: dict[str, Any],
    events_path: Path,
    apply: bool,
    space: str,
    cwd_prefix: str,
    include_agents: set[str],
    stopped_statuses: set[str],
    cooldown_seconds: int,
    unconfirmed_cooldown_seconds: int,
    min_stopped_seconds: int,
    max_prompts: int,
    only_obvious_early_stops: bool,
) -> tuple[int, dict[str, Any]]:
    try:
        workspace = resolve_workspace(client, space)
        workspace_ids = [item["workspace_id"] for item in workspace] if isinstance(workspace, list) else [workspace["workspace_id"]]
        receipt["workspace"] = workspace
        panes: list[dict[str, Any]] = []
        for workspace_id in workspace_ids:
            result = client.call("pane.list", {"workspace_id": workspace_id})
            panes.extend(result.get("panes", []))
    except RuntimeError as exc:
        receipt.update({"ok": False, "status": "BLOCKED", "errors": [str(exc)]})
        return finish(receipt, 2)

    agent_index = load_agent_index(client)
    receipt["observed_panes"] = len(panes)
    receipt["agent_index_size"] = len(agent_index)
    state = load_state()
    input_suppressed = bool(state.get("input_suppressed"))
    if input_suppressed:
        receipt["input_suppressed"] = True
        receipt["state_error"] = state.get("state_error")
    now_epoch = current_epoch()
    selected: list[dict[str, Any]] = []
    stopped_observations = state.setdefault("stopped_observations", {})
    observed_pane_ids = {str(pane.get("pane_id") or "") for pane in panes if pane.get("pane_id")}
    current_stopped_ids: set[str] = set()

    for pane in panes:
        candidate = classify_pane(
            client,
            pane,
            cwd_prefix=cwd_prefix,
            include_agents=include_agents,
            stopped_statuses=stopped_statuses,
            only_obvious_early_stops=only_obvious_early_stops,
            agent_index=agent_index,
        )
        if not candidate:
            continue
        pane_id = str(candidate["pane_id"])
        current_stopped_ids.add(pane_id)
        update_stopped_observation(stopped_observations, candidate, now_epoch=now_epoch)
        prompt_state = state.get("prompts", {}).get(pane_id, {})
        apply_no_change_suppression(candidate, prompt_state)
        last_prompt_at = int(prompt_state.get("last_prompt_epoch", 0) or 0)
        effective_cooldown_seconds = cooldown_for_prompt_state(
            prompt_state,
            cooldown_seconds=cooldown_seconds,
            unconfirmed_cooldown_seconds=unconfirmed_cooldown_seconds,
        )
        candidate["cooldown_active"] = effective_cooldown_seconds > 0 and (now_epoch - last_prompt_at) < effective_cooldown_seconds
        candidate["cooldown_seconds_effective"] = effective_cooldown_seconds
        candidate["last_prompt_epoch"] = last_prompt_at or None
        candidate["min_stopped_seconds"] = min_stopped_seconds
        candidate["stopped_age_satisfied"] = (
            candidate.get("stopped_age_seconds") is not None
            and int(candidate.get("stopped_age_seconds") or 0) >= min_stopped_seconds
        )
        receipt["stopped_panes"].append(candidate)
        append_jsonl(events_path, {"event": "stopped_pane", "ts": now_iso(), **candidate_without_text(candidate)})
        should_prompt = candidate.get("action") != "observe_only"
        candidate["select_for_prompt"] = should_prompt
        if (
            should_prompt
            and not input_suppressed
            and not candidate["cooldown_active"]
            and candidate["stopped_age_satisfied"]
            and len(selected) < max_prompts
        ):
            selected.append(candidate)
    prune_stopped_observations(
        stopped_observations,
        observed_pane_ids=observed_pane_ids,
        current_stopped_ids=current_stopped_ids,
    )

    receipt["selected_panes"] = [candidate_without_text(item) for item in selected]

    for candidate in selected:
        prompt = build_prompt(candidate)
        prompt_path = Path(receipt["receipt_dir"]) / f"prompt-{candidate['pane_id'].replace(':', '_')}.md"
        prompt_path.write_text(prompt, encoding="utf-8")
        prompt_record: dict[str, Any] = {
            "pane_id": candidate["pane_id"],
            "agent": candidate.get("agent"),
            "agent_status": candidate.get("agent_status"),
            "action": candidate.get("action"),
            "classification": candidate.get("classification"),
            "selection_reasons": candidate.get("selection_reasons", []),
            "prompt_path": str(prompt_path),
            "sent": False,
            "api_sent": False,
            "submit_confirmed": False,
            "send_api": [],
        }
        if apply:
            send_result = send_prompt(client, str(candidate["pane_id"]), prompt, project_root=candidate.get("project_root"))
            prompt_record.update(send_result)
            prompt_record["sent"] = bool(send_result.get("submit_confirmed"))
            if prompt_record["submit_confirmed"] or prompt_record.get("input_modified"):
                pane_key = str(candidate["pane_id"])
                previous_state = state.get("prompts", {}).get(pane_key, {})
                new_state = {
                    "last_prompt_epoch": now_epoch,
                    "last_prompt_at": now_iso(),
                    "agent": candidate.get("agent"),
                    "cwd": candidate.get("cwd"),
                    "classification": candidate.get("classification"),
                    "action": candidate.get("action"),
                    "submit_confirmed": bool(prompt_record["submit_confirmed"]),
                    "input_modified": bool(prompt_record.get("input_modified")),
                    "no_change_strikes": int(previous_state.get("no_change_strikes", 0) or 0),
                }
                # Snapshot what the agent looked like as we nudged it, so the next
                # tick can prove whether the nudge actually produced any work.
                record_prompt_signature(
                    new_state,
                    candidate.get("change_signature", {}),
                    unchanged_before=bool((candidate.get("change_verdict") or {}).get("unchanged")),
                )
                state.setdefault("prompts", {})[pane_key] = new_state
        receipt["prompts"].append(prompt_record)
        append_jsonl(events_path, {"event": "prompt", "ts": now_iso(), **prompt_record})

    if apply or min_stopped_seconds > 0:
        write_json(STATE_PATH, state)

    receipt["status"] = "RESTART_PROMPTS_SUBMITTED" if apply and receipt["prompts"] else "OBSERVED"
    if input_suppressed:
        receipt["status"] = "NEEDS_ATTENTION"
        receipt["ok"] = False
        return finish(receipt, 1)
    receipt["ok"] = all(not prompt_send_failed(item) for item in receipt["prompts"]) or not apply
    if apply and any(not item.get("sent") for item in receipt["prompts"]):
        receipt["status"] = "NEEDS_ATTENTION"
    return finish(receipt, 0 if receipt["ok"] else 1)
















































def finish(receipt: dict[str, Any], exit_code: int) -> tuple[int, dict[str, Any]]:
    receipt_path = Path(receipt["receipt_dir"]) / "receipt.json"
    receipt["receipt_path"] = str(receipt_path)
    append_jsonl(Path(receipt["events_path"]), {
        "event": "tick_finish",
        "ts": now_iso(),
        "status": receipt.get("status"),
        "ok": receipt.get("ok"),
        "receipt_path": str(receipt_path),
    })
    write_json(receipt_path, receipt)
    log_event(
        str(receipt["run_id"]),
        "tick_finish",
        status=receipt.get("status"),
        ok=receipt.get("ok"),
        receipt_path=str(receipt_path),
        exit_code=exit_code,
    )
    return exit_code, receipt


if __name__ == "__main__":
    try:
        app()
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        raise typer.Exit(130)
