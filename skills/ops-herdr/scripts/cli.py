#!/usr/bin/env python3
"""Typer CLI for Herdr workstation orchestration.

The CLI gives project agents a compact command surface for Herdr sessions:
create/remove workstations, start named provider panes, send live instructions,
read output, report semantic state, and run bounded creator/reviewer batches.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Annotated, Any, Optional

import typer
from loguru import logger

SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR))

from ops_herdr_core import (  # noqa: E402
    AGENT_KINDS,
    HerdrContractError,
    PaneMove,
    append_event,
    check_protocol,
    load_dotenv_once,
    move_pane,
    result_body,
    require_protocol,
    split_pane,
    create_tab,
    create_workspace,
    create_worktree_workspace,
    ensure_dir,
    manifest_path_from_run_dir,
    parse_env_options,
    run_herdr,
    save_manifest,
    slugify,
    status_object,
    utc_stamp,
    write_json,
    load_manifest,
)
from ops_herdr_loops import (  # noqa: E402
    LoopTask,
    build_creator_prompt,
    load_loop_tasks,
    run_one_loop,
)

# Idempotent: core loads .env on import; this keeps the entrypoint explicit for
# direct `python scripts/cli.py` invocations.
load_dotenv_once()

logger.remove()
logger.add(sys.stderr, format="{time:HH:mm:ss} | {level:<7} | {message}", level="INFO")

app = typer.Typer(help="Manage visible Herdr workstations for project-agent subagents.")
workstation_app = typer.Typer(help="Create, focus, inspect, and remove Herdr workstations.")
agent_app = typer.Typer(help="Start, message, read, wait, and report subagent panes.")
batch_app = typer.Typer(help="Run bounded creator/reviewer batches in Herdr workstations.")
app.add_typer(workstation_app, name="workstation")
app.add_typer(agent_app, name="agent")
app.add_typer(batch_app, name="batch")

StatusValue = Annotated[str, typer.Option(help="Agent state: idle, working, blocked, done, or unknown.")]


def print_json(value: Any) -> None:
    """Print deterministic JSON for scripts and receipts."""
    typer.echo(json.dumps(value, indent=2, sort_keys=True))


def optional_list(value: list[str] | None, fallback: list[str]) -> list[str]:
    """Return a copy of a Typer list option or its fallback."""
    return list(value) if value is not None else list(fallback)


@app.command()
def doctor(
    json_output: Annotated[bool, typer.Option("--json", help="Print JSON instead of human text.")] = False,
    herdr_bin: Annotated[str, typer.Option(help="Herdr binary path.")] = "herdr",
    session: Annotated[Optional[str], typer.Option(help="Named Herdr session.")] = None,
) -> None:
    """Check whether Herdr is installed and reachable."""
    binary = shutil.which(herdr_bin) or herdr_bin
    version = run_herdr(["--version"], herdr_bin=herdr_bin, session=session, check=False)
    status = run_herdr(["status"], herdr_bin=herdr_bin, session=session, check=False)
    protocol = check_protocol(herdr_bin=herdr_bin, session=session)
    payload = {
        "herdr_bin": binary,
        "version": status_object(version),
        "status": status_object(status),
        "protocol": protocol,
        "ok": version.returncode == 0 and status.returncode == 0 and protocol["ok"],
    }
    if json_output:
        print_json(payload)
    else:
        typer.echo("Herdr available" if payload["ok"] else "Herdr not fully reachable")
        typer.echo(f"binary: {binary}")
        typer.echo(version.stdout.strip() or version.stderr.strip())
        typer.echo(f"protocol: {protocol['protocol']} (need >= {protocol['minimum']}) {protocol['reason']}")


@app.command("install-integrations")
def install_integrations(
    agents: Annotated[list[str], typer.Argument(help="Agent integrations to install, e.g. codex opencode claude.")],
    herdr_bin: Annotated[str, typer.Option(help="Herdr binary path.")] = "herdr",
    session: Annotated[Optional[str], typer.Option(help="Named Herdr session.")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Print JSON response.")] = False,
) -> None:
    """Install Herdr integrations for provider-specific agent state."""
    results: list[dict[str, Any]] = []
    for agent_name in agents:
        result = run_herdr(["integration", "install", agent_name], herdr_bin=herdr_bin, session=session, check=False)
        results.append({"agent": agent_name, **status_object(result)})
    if json_output:
        print_json({"results": results})
    else:
        for item in results:
            typer.echo(f"{item['agent']}: exit={item['returncode']}")


@workstation_app.command("create")
def workstation_create(
    repo: Annotated[Path, typer.Option(help="Repository or project cwd for the workstation.")],
    label: Annotated[str, typer.Option(help="Herdr workspace label.")],
    run_root: Annotated[Path, typer.Option(help="Directory for manifests, events, and receipts.")] = Path(".herdr-workstations"),
    session: Annotated[Optional[str], typer.Option(help="Named Herdr session.")] = None,
    tabs: Annotated[Optional[list[str]], typer.Option("--tab", help="Tab labels to create.")] = None,
    env: Annotated[Optional[list[str]], typer.Option("--env", help="Workspace/tab KEY=VALUE env.")] = None,
    use_worktree: Annotated[bool, typer.Option("--worktree/--no-worktree", help="Create a Git worktree workspace.")] = False,
    branch: Annotated[Optional[str], typer.Option(help="Worktree branch name.")] = None,
    base: Annotated[Optional[str], typer.Option(help="Worktree base ref.")] = None,
    worktree_path: Annotated[Optional[Path], typer.Option(help="Explicit worktree checkout path.")] = None,
    herdr_bin: Annotated[str, typer.Option(help="Herdr binary path.")] = "herdr",
    dry_run: Annotated[bool, typer.Option(help="Print commands without running Herdr.")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Print JSON manifest.")] = True,
) -> None:
    """Create a dynamic Herdr workstation with tabs and a manifest."""
    repo = repo.expanduser().resolve()
    if not dry_run and not repo.exists():
        raise typer.BadParameter(f"repo does not exist: {repo}")
    env_values = parse_env_options(env)
    tab_labels = optional_list(tabs, ["agents", "logs", "receipts"])
    run_id = f"{utc_stamp()}-{slugify(label)}"
    run_dir = ensure_dir(run_root.expanduser().resolve() / run_id)
    actual_cwd = repo
    worktree_output: Any | None = None
    if not dry_run:
        require_protocol(herdr_bin=herdr_bin, session=session)
    root_pane_id: str | None = None
    root_tab_id: str | None = None
    if use_worktree:
        branch = branch or f"herdr/{slugify(label)}-{utc_stamp().lower()}"
        workspace_id, actual_worktree_path, worktree_output = create_worktree_workspace(
            label=label,
            repo=repo,
            branch=branch,
            base=base,
            path=worktree_path,
            session=session,
            herdr_bin=herdr_bin,
            dry_run=dry_run,
        )
        actual_cwd = actual_worktree_path or repo
    else:
        topology = create_workspace(label=label, cwd=repo, session=session, herdr_bin=herdr_bin, env_values=env_values, dry_run=dry_run)
        workspace_id = topology.workspace_id
        root_tab_id = topology.root_tab_id
        root_pane_id = topology.root_pane_id
    tabs: dict[str, dict[str, Any]] = {}
    for tab_label in tab_labels:
        tab = create_tab(
            workspace_id=workspace_id,
            label=tab_label,
            cwd=actual_cwd,
            session=session,
            herdr_bin=herdr_bin,
            env_values=env_values,
            dry_run=dry_run,
        )
        tabs[tab_label] = {"tab_id": tab.tab_id, "root_pane_id": tab.root_pane_id, "panes": [tab.root_pane_id]}
    manifest = {
        "schema_version": 2,
        "kind": "herdr-workstation",
        "run_id": run_id,
        "created_at": utc_stamp(),
        "updated_at": utc_stamp(),
        "label": label,
        "session": session or os.environ.get("HERDR_SESSION") or "default",
        "repo": str(repo),
        "cwd": str(actual_cwd),
        "run_dir": str(run_dir),
        "events_jsonl": str(run_dir / "events.jsonl"),
        "workspace_id": workspace_id,
        "root_tab_id": root_tab_id,
        "root_pane_id": root_pane_id,
        "tabs": tabs,
        "agents": {},
        "worktree": {"enabled": use_worktree, "branch": branch, "base": base, "path": str(actual_cwd) if use_worktree else None, "raw": worktree_output},
    }
    save_manifest(manifest_path_from_run_dir(run_dir), manifest)
    print_json(manifest) if json_output else typer.echo(str(run_dir))


@workstation_app.command("focus")
def workstation_focus(
    manifest: Annotated[Path, typer.Argument(help="Path to workstation.json or run dir.")],
    herdr_bin: Annotated[str, typer.Option(help="Herdr binary path.")] = "herdr",
    session: Annotated[Optional[str], typer.Option(help="Named Herdr session override.")] = None,
) -> None:
    """Focus an existing Herdr workstation workspace."""
    data = load_manifest(manifest)
    run_herdr(["workspace", "focus", data["workspace_id"]], herdr_bin=herdr_bin, session=session or data.get("session"))
    typer.echo(data["workspace_id"])


@workstation_app.command("inspect")
def workstation_inspect(
    manifest: Annotated[Path, typer.Argument(help="Path to workstation.json or run dir.")],
    herdr_bin: Annotated[str, typer.Option(help="Herdr binary path.")] = "herdr",
    session: Annotated[Optional[str], typer.Option(help="Named Herdr session override.")] = None,
) -> None:
    """Read Herdr workspace, tab, pane, and agent state for a workstation."""
    data = load_manifest(manifest)
    active_session = session or data.get("session")
    workspace_id = data["workspace_id"]
    payload = {
        "manifest": data,
        "workspace": status_object(run_herdr(["workspace", "get", workspace_id], herdr_bin=herdr_bin, session=active_session, check=False)),
        "tabs": status_object(run_herdr(["tab", "list", "--workspace", workspace_id], herdr_bin=herdr_bin, session=active_session, check=False)),
        "panes": status_object(run_herdr(["pane", "list", "--workspace", workspace_id], herdr_bin=herdr_bin, session=active_session, check=False)),
        "agents": status_object(run_herdr(["agent", "list"], herdr_bin=herdr_bin, session=active_session, check=False)),
    }
    print_json(payload)


@workstation_app.command("remove")
def workstation_remove(
    manifest: Annotated[Path, typer.Argument(help="Path to workstation.json or run dir.")],
    force_worktree: Annotated[bool, typer.Option("--force-worktree", help="Force git worktree removal.")] = False,
    close_only: Annotated[bool, typer.Option("--close-only/--remove-worktree", help="Close workspace without deleting worktree.")] = True,
    herdr_bin: Annotated[str, typer.Option(help="Herdr binary path.")] = "herdr",
    session: Annotated[Optional[str], typer.Option(help="Named Herdr session override.")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Print JSON response.")] = True,
) -> None:
    """Close a Herdr workstation and optionally remove its managed worktree."""
    manifest_path = manifest_path_from_run_dir(manifest) if manifest.is_dir() else manifest
    data = load_manifest(manifest_path)
    active_session = session or data.get("session")
    workspace_id = data["workspace_id"]
    if data.get("worktree", {}).get("enabled") and not close_only:
        args = ["worktree", "remove", "--workspace", workspace_id, "--json"]
        if force_worktree:
            args.append("--force")
        result = run_herdr(args, herdr_bin=herdr_bin, session=active_session, check=False)
    else:
        result = run_herdr(["workspace", "close", workspace_id], herdr_bin=herdr_bin, session=active_session, check=False)
    data["removed_at"] = utc_stamp()
    data["remove_result"] = status_object(result)
    save_manifest(manifest_path, data)
    print_json(data) if json_output else typer.echo(f"removed {workspace_id}")


def tab_entry(data: dict[str, Any], tab: str) -> dict[str, Any]:
    """Return a manifest tab record, upgrading schema v1 {label: tab_id} in place."""
    tabs = data.get("tabs", {})
    if tab not in tabs:
        raise typer.BadParameter(f"unknown tab {tab!r}; have {sorted(tabs)}")
    entry = tabs[tab]
    if isinstance(entry, str):  # schema v1 manifest: no root pane was recorded
        entry = {"tab_id": entry, "root_pane_id": None, "panes": []}
        tabs[tab] = entry
    return entry


def resolve_target_pane(
    entry: dict[str, Any],
    *,
    split: Optional[str],
    cwd: str,
    env_values: list[str],
    herdr_bin: str,
    session: str | None,
) -> str:
    """Return an idle pane for `agent start`, splitting when the tab is occupied.

    Herdr 0.8.0 attaches an agent to an EXISTING pane at a shell prompt, so the
    pane must be built before the agent is started, never after.
    """
    panes: list[str] = [p for p in entry.get("panes", []) if isinstance(p, str)]
    occupied: list[str] = [p for p in entry.get("occupied", []) if isinstance(p, str)]
    free = [p for p in panes if p not in occupied]
    if free and not split:
        return free[0]
    anchor = (panes[-1] if panes else entry.get("root_pane_id"))
    if not anchor:
        raise typer.BadParameter(
            "manifest has no pane to split from; recreate the workstation with this "
            "version so root pane ids are recorded (schema_version 2)"
        )
    pane = split_pane(
        pane_id=anchor,
        direction=split or "right",
        cwd=Path(cwd),
        env_values=env_values,
        session=session,
        herdr_bin=herdr_bin,
    )
    panes.append(pane)
    entry["panes"] = panes
    return pane


@agent_app.command("start")
def agent_start(
    manifest: Annotated[Path, typer.Argument(help="Path to workstation.json or run dir.")],
    name: Annotated[str, typer.Option(help="Unique Herdr agent name.")],
    role: Annotated[str, typer.Option(help="Semantic role, e.g. petey, qbert, creator.")],
    kind: Annotated[str, typer.Option(help=f"Herdr agent kind. One of: {', '.join(sorted(AGENT_KINDS))}.")],
    tab: Annotated[str, typer.Option(help="Target tab label from the manifest.")] = "agents",
    split: Annotated[Optional[str], typer.Option(help="Split direction for a new pane: right or down.")] = None,
    work_order: Annotated[Optional[Path], typer.Option(help="Durable work-order path for the agent.")] = None,
    env: Annotated[Optional[list[str]], typer.Option("--env", help="Additional KEY=VALUE env for the pane.")] = None,
    agent_arg: Annotated[Optional[list[str]], typer.Option("--agent-arg", help="Extra argument passed to the agent after `--`.")] = None,
    timeout_ms: Annotated[int, typer.Option(help="Interactive readiness timeout in ms (3000-300000).")] = 30000,
    herdr_bin: Annotated[str, typer.Option(help="Herdr binary path.")] = "herdr",
    session: Annotated[Optional[str], typer.Option(help="Named Herdr session override.")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Print JSON manifest.")] = True,
) -> None:
    """Start one named provider agent on a pane inside a workstation.

    Herdr 0.8.0 contract: `agent start <name> --kind KIND --pane PANE_ID`. The pane
    is created and carries the TAU_* environment; the agent then attaches to it.
    """
    if kind not in AGENT_KINDS:
        raise typer.BadParameter(f"unknown kind {kind!r}; Herdr accepts {', '.join(sorted(AGENT_KINDS))}")
    manifest_path = manifest_path_from_run_dir(manifest) if manifest.is_dir() else manifest
    data = load_manifest(manifest_path)
    active_session = session or data.get("session")
    require_protocol(herdr_bin=herdr_bin, session=active_session)
    entry = tab_entry(data, tab)
    run_dir = Path(data["run_dir"])
    pane_env = [f"TAU_ROLE={role}", f"TAU_AGENT_NAME={name}", f"TAU_RUN_DIR={run_dir}"]
    if work_order:
        pane_env.append(f"TAU_WORK_ORDER={work_order.expanduser().resolve()}")
    pane_env.extend(parse_env_options(env))
    pane_id = resolve_target_pane(
        entry,
        split=split,
        cwd=data["cwd"],
        env_values=pane_env,
        herdr_bin=herdr_bin,
        session=active_session,
    )
    args = ["agent", "start", name, "--kind", kind, "--pane", pane_id, "--timeout", str(timeout_ms)]
    if agent_arg:
        args.append("--")
        args.extend(agent_arg)
    result = run_herdr(args, herdr_bin=herdr_bin, session=active_session)
    entry.setdefault("occupied", []).append(pane_id)
    data.setdefault("agents", {})[name] = {
        "role": role,
        "kind": kind,
        "tab": tab,
        "pane_id": pane_id,
        "previous_pane_ids": [],
        "started_at": utc_stamp(),
        "work_order": str(work_order.expanduser().resolve()) if work_order else None,
        "last_start_result": status_object(result),
    }
    save_manifest(manifest_path, data)
    print_json(data) if json_output else typer.echo(name)


@agent_app.command("send")
def agent_send(
    target: Annotated[str, typer.Argument(help="Agent target name or pane id hosting an agent.")],
    text: Annotated[Optional[str], typer.Option(help="Text to send. Use --file for longer prompts.")] = None,
    file: Annotated[Optional[Path], typer.Option(help="Prompt file to send.")] = None,
    wait: Annotated[bool, typer.Option("--wait/--no-wait", help="Confirm submission by waiting for a settled state.")] = True,
    until: Annotated[Optional[list[str]], typer.Option("--until", help="State to match after --wait; repeatable.")] = None,
    timeout_ms: Annotated[int, typer.Option(help="Wait timeout in milliseconds.")] = 120000,
    events: Annotated[Optional[Path], typer.Option(help="Optional JSONL event path to append.")] = None,
    from_agent: Annotated[Optional[str], typer.Option(help="Optional sending role/name for event log.")] = None,
    herdr_bin: Annotated[str, typer.Option(help="Herdr binary path.")] = "herdr",
    session: Annotated[Optional[str], typer.Option(help="Named Herdr session.")] = None,
) -> None:
    """Submit a prompt to a Herdr agent and confirm it was actually submitted.

    Herdr 0.8.0 contract: `agent prompt <target> <text> [--wait] [--until STATUS]`.
    `--wait` is the default because a send that is pasted but never executed is
    the failure this skill exists to avoid; pass `--no-wait` only for fire-and-forget
    notifications.
    """
    if file:
        payload = file.expanduser().read_text(encoding="utf-8")
    elif text is not None:
        payload = text
    else:
        payload = sys.stdin.read()
    payload = payload.rstrip("\n")
    if not payload.strip():
        raise typer.BadParameter("refusing to submit an empty prompt")
    args = ["agent", "prompt", target, payload]
    if wait:
        args.append("--wait")
        for state in until or ["idle", "done", "blocked"]:
            args.extend(["--until", state])
        args.extend(["--timeout", str(timeout_ms)])
    result = run_herdr(args, herdr_bin=herdr_bin, session=session)
    record = {
        "ts": utc_stamp(),
        "from": from_agent,
        "target": target,
        "kind": "prompt",
        "chars": len(payload),
        "submit_confirmed": wait and result.returncode == 0,
        "waited_for": (until or ["idle", "done", "blocked"]) if wait else [],
    }
    if events:
        append_event(events.expanduser(), record)
    print_json(record)


@agent_app.command("read")
def agent_read(
    target: Annotated[str, typer.Argument(help="Agent target name, label, terminal id, or pane id.")],
    source: Annotated[str, typer.Option(help="Read source: visible, recent, recent-unwrapped, or detection.")] = "recent-unwrapped",
    lines: Annotated[int, typer.Option(help="Number of lines to read.")] = 120,
    ansi: Annotated[bool, typer.Option(help="Preserve ANSI output.")] = False,
    herdr_bin: Annotated[str, typer.Option(help="Herdr binary path.")] = "herdr",
    session: Annotated[Optional[str], typer.Option(help="Named Herdr session.")] = None,
) -> None:
    """Read recent output from a Herdr agent terminal stream."""
    args = ["agent", "read", target, "--source", source, "--lines", str(lines)]
    if ansi:
        args.append("--ansi")
    result = run_herdr(args, herdr_bin=herdr_bin, session=session)
    typer.echo(result.stdout.rstrip())


@agent_app.command("wait")
def agent_wait(
    target: Annotated[str, typer.Argument(help="Agent target name or pane id hosting an agent.")],
    until: Annotated[Optional[list[str]], typer.Option("--until", help="State to match; repeatable. Default: idle, done, blocked.")] = None,
    timeout_s: Annotated[int, typer.Option(help="Timeout in seconds.")] = 600,
    herdr_bin: Annotated[str, typer.Option(help="Herdr binary path.")] = "herdr",
    session: Annotated[Optional[str], typer.Option(help="Named Herdr session.")] = None,
) -> None:
    """Wait until a Herdr agent reaches one of the requested states.

    Herdr 0.8.0 uses `--until` (repeatable); the pre-0.8 `--status` flag is gone.
    """
    args = ["agent", "wait", target, "--timeout", str(timeout_s * 1000)]
    for state in until or []:
        args.extend(["--until", state])
    result = run_herdr(args, herdr_bin=herdr_bin, session=session)
    typer.echo(result.stdout.rstrip())


@agent_app.command("report")
def agent_report(
    agent: Annotated[str, typer.Option(help="Visible agent label, e.g. Petey or Qbert.")],
    state: StatusValue = "working",
    pane_id: Annotated[Optional[str], typer.Option(help="Pane id; defaults to HERDR_PANE_ID.")] = None,
    source: Annotated[str, typer.Option(help="Lifecycle authority source id.")] = "tau-herdr",
    message: Annotated[Optional[str], typer.Option(help="Detailed state message.")] = None,
    custom_status: Annotated[Optional[str], typer.Option(help="Short visible status label.")] = None,
    seq: Annotated[Optional[int], typer.Option(help="Monotonic sequence for stale-report protection.")] = None,
    herdr_bin: Annotated[str, typer.Option(help="Herdr binary path.")] = "herdr",
    session: Annotated[Optional[str], typer.Option(help="Named Herdr session.")] = None,
) -> None:
    """Report custom role/state metadata from inside a Herdr pane."""
    resolved_pane = pane_id or os.environ.get("HERDR_PANE_ID")
    if not resolved_pane:
        raise typer.BadParameter("pane id required; run inside Herdr or pass --pane-id")
    args = ["pane", "report-agent", resolved_pane, "--source", source, "--agent", agent, "--state", state]
    if message:
        args.extend(["--message", message])
    if custom_status:
        args.extend(["--custom-status", custom_status])
    if seq is not None:
        args.extend(["--seq", str(seq)])
    result = run_herdr(args, herdr_bin=herdr_bin, session=session)
    typer.echo(result.stdout.rstrip())


@agent_app.command("move")
def agent_move(
    manifest: Annotated[Path, typer.Argument(help="Path to workstation.json or run dir.")],
    name: Annotated[str, typer.Option(help="Agent name recorded in the manifest.")],
    new_space: Annotated[Optional[str], typer.Option(help="Move into a brand new workspace with this label.")] = None,
    workspace: Annotated[Optional[str], typer.Option(help="Move into a new tab in this existing workspace id.")] = None,
    tab: Annotated[Optional[str], typer.Option(help="Move into this existing tab id.")] = None,
    tab_label: Annotated[Optional[str], typer.Option(help="Label for the created tab.")] = None,
    split: Annotated[Optional[str], typer.Option(help="Split direction when landing in an existing tab: right or down.")] = None,
    target_pane: Annotated[Optional[str], typer.Option(help="Pane to split against in the destination tab.")] = None,
    focus: Annotated[bool, typer.Option("--focus/--no-focus", help="Focus the destination after moving.")] = False,
    herdr_bin: Annotated[str, typer.Option(help="Herdr binary path.")] = "herdr",
    session: Annotated[Optional[str], typer.Option(help="Named Herdr session override.")] = None,
) -> None:
    """Move a running agent's pane to another space and emit a reconciliation receipt.

    The terminal survives a cross-workspace move and Herdr keeps the old pane id as
    an alias, so the receipt records the old-to-new mapping that monitor-herdr needs
    to migrate cooldown and stopped-state instead of treating the agent as new.
    """
    manifest_path = manifest_path_from_run_dir(manifest) if manifest.is_dir() else manifest
    data = load_manifest(manifest_path)
    active_session = session or data.get("session")
    require_protocol(herdr_bin=herdr_bin, session=active_session)
    agent = data.get("agents", {}).get(name)
    if not agent:
        raise typer.BadParameter(f"unknown agent {name!r}; have {sorted(data.get('agents', {}))}")
    pane_id = agent.get("pane_id")
    if not pane_id:
        raise typer.BadParameter(f"agent {name!r} has no recorded pane_id; restart it with this version")
    before = {
        "workspace_id": data.get("workspace_id"),
        "tab_id": (tab_entry(data, agent["tab"]) or {}).get("tab_id"),
        "pane_id": pane_id,
        "agent_name": name,
    }
    move: PaneMove = move_pane(
        pane_id=pane_id,
        new_workspace=bool(new_space),
        new_tab=bool(workspace) and not tab,
        workspace_id=workspace,
        tab_id=tab,
        target_pane=target_pane,
        split=split,
        label=new_space or tab_label,
        tab_label=tab_label if new_space else None,
        focus=focus,
        session=active_session,
        herdr_bin=herdr_bin,
    )
    agent["previous_pane_ids"] = [*agent.get("previous_pane_ids", []), move.previous_pane_id]
    agent["pane_id"] = move.pane_id
    agent["terminal_id"] = move.terminal_id
    agent["workspace_id"] = move.workspace_id
    agent["tab_id"] = move.tab_id
    entry = tab_entry(data, agent["tab"])
    entry["panes"] = [move.pane_id if p == move.previous_pane_id else p for p in entry.get("panes", [])]
    entry["occupied"] = [move.pane_id if p == move.previous_pane_id else p for p in entry.get("occupied", [])]
    save_manifest(manifest_path, data)

    receipt = {
        "schema": "herdr.space_operation_receipt.v1",
        "operation": "move-pane",
        "created_at": utc_stamp(),
        "agent": name,
        "before": before,
        "after": {
            "workspace_id": move.workspace_id,
            "tab_id": move.tab_id,
            "pane_id": move.pane_id,
            "terminal_id": move.terminal_id,
            "agent_name": name,
        },
        "id_map": move.id_map(),
        "created_workspace_id": move.created_workspace_id,
        "created_tab_id": move.created_tab_id,
        "closed_workspace_id": move.closed_workspace_id,
        "closed_tab_id": move.closed_tab_id,
        "changed": move.changed,
        "status": "completed" if move.changed else "noop",
    }
    receipt_path = Path(data["run_dir"]) / "receipts" / f"move-{slugify(name)}-{utc_stamp()}.json"
    write_json(receipt_path, receipt)
    receipt["receipt_path"] = str(receipt_path)
    print_json(receipt)


@agent_app.command("notify")
def agent_notify(
    target: Annotated[str, typer.Argument(help="Target agent to notify.")],
    message: Annotated[str, typer.Argument(help="Short notification message.")],
    events: Annotated[Path, typer.Option(help="JSONL event path for durable coordination.")],
    from_agent: Annotated[str, typer.Option(help="Sender role/name.")] = "main-project-agent",
    kind: Annotated[str, typer.Option(help="Event kind, e.g. handoff_ready.")] = "notification",
    herdr_bin: Annotated[str, typer.Option(help="Herdr binary path.")] = "herdr",
    session: Annotated[Optional[str], typer.Option(help="Named Herdr session.")] = None,
) -> None:
    """Send a bounded notification and append a durable JSONL event."""
    event = {"ts": utc_stamp(), "from": from_agent, "target": target, "kind": kind, "message": message}
    append_event(events.expanduser(), event)
    run_herdr(["agent", "prompt", target, f"Notification from {from_agent}: {message}"], herdr_bin=herdr_bin, session=session)
    print_json(event)


@batch_app.command("creator-reviewer")
def batch_creator_reviewer(
    tasks: Annotated[Path, typer.Option(help="JSON array of LoopTask objects.")],
    repo: Annotated[Path, typer.Option(help="Repository cwd for all task workstations.")],
    creator_cmd: Annotated[str, typer.Option(help="Creator provider command, e.g. codex or opencode.")],
    reviewer_cmd: Annotated[str, typer.Option(help="Reviewer provider command, e.g. codex or opencode.")],
    run_root: Annotated[Path, typer.Option(help="Root directory for loop manifests and receipts.")] = Path(".herdr-workstations/loops"),
    concurrency: Annotated[int, typer.Option(help="Maximum tasks to run at once.")] = 1,
    receipt_timeout_s: Annotated[int, typer.Option(help="Timeout per receipt in seconds.")] = 3600,
    session: Annotated[Optional[str], typer.Option(help="Named Herdr session.")] = None,
    herdr_bin: Annotated[str, typer.Option(help="Herdr binary path.")] = "herdr",
) -> None:
    """Run a long-running batch of visible creator/reviewer loops."""
    repo = repo.expanduser().resolve()
    run_root = ensure_dir(run_root.expanduser().resolve())
    task_specs = load_loop_tasks(tasks.expanduser().resolve())

    async def runner() -> list[dict[str, Any]]:
        """Run task loops with a bounded asyncio semaphore."""
        semaphore = asyncio.Semaphore(concurrency)
        results: list[dict[str, Any]] = []

        async def guarded(task: LoopTask) -> None:
            """Run one task and convert controller exceptions into receipts."""
            async with semaphore:
                try:
                    result = await run_one_loop(task=task, repo=repo, run_root=run_root, creator_cmd=creator_cmd, reviewer_cmd=reviewer_cmd, session=session, herdr_bin=herdr_bin, receipt_timeout_s=receipt_timeout_s)
                except Exception as exc:  # noqa: BLE001 - controller must receipt failures.
                    result = {"task_id": task.task_id, "status": "CONTROLLER_ERROR", "error": repr(exc)}
                results.append(result)
                print_json(result)

        await asyncio.gather(*(guarded(task) for task in task_specs))
        return results

    results = asyncio.run(runner())
    summary = {"created_at": utc_stamp(), "repo": str(repo), "tasks": len(task_specs), "results": results}
    write_json(run_root / f"batch-{utc_stamp()}.json", summary)
    if any(item.get("status") != "PASS" for item in results):
        raise typer.Exit(code=1)


@app.command()
def verify() -> None:
    """Run local self-checks that do not require a live Herdr server."""
    sample = slugify("Monitor Sparta: Petey/Qbert Loop")
    if sample != "monitor-sparta-petey-qbert-loop":
        raise typer.Exit(code=2)
    task = LoopTask(task_id="demo", title="Demo", prompt="Do the thing")
    prompt = build_creator_prompt(task, 1, Path("work.md"), Path("receipt.json"), "none")
    if "TAU_CREATOR_RECEIPT_WRITTEN" not in prompt:
        raise typer.Exit(code=3)
    # A malformed Herdr reply must fail closed, never fall through to a recursive
    # id search that could return previous_pane_id as if it were the new pane.
    try:
        result_body({"id": "x"}, context="verify")
    except HerdrContractError:
        pass
    else:
        raise typer.Exit(code=4)
    if "codex" not in AGENT_KINDS or "definitely-not-a-kind" in AGENT_KINDS:
        raise typer.Exit(code=5)
    typer.echo("verify ok")


if __name__ == "__main__":
    app()
