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
import shlex
import shutil
import sys
from pathlib import Path
from typing import Annotated, Any, Optional

import typer
from loguru import logger

SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR))

from ops_herdr_core import (  # noqa: E402
    append_event,
    load_dotenv_once,
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
    payload = {
        "herdr_bin": binary,
        "version": status_object(version),
        "status": status_object(status),
        "ok": version.returncode == 0 and status.returncode == 0,
    }
    if json_output:
        print_json(payload)
    else:
        typer.echo("Herdr available" if payload["ok"] else "Herdr not fully reachable")
        typer.echo(f"binary: {binary}")
        typer.echo(version.stdout.strip() or version.stderr.strip())


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
        workspace_id = create_workspace(label=label, cwd=repo, session=session, herdr_bin=herdr_bin, env_values=env_values, dry_run=dry_run)
    tab_ids = {
        tab_label: create_tab(
            workspace_id=workspace_id,
            label=tab_label,
            cwd=actual_cwd,
            session=session,
            herdr_bin=herdr_bin,
            env_values=env_values,
            dry_run=dry_run,
        )
        for tab_label in tab_labels
    }
    manifest = {
        "schema_version": 1,
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
        "tabs": tab_ids,
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


@agent_app.command("start")
def agent_start(
    manifest: Annotated[Path, typer.Argument(help="Path to workstation.json or run dir.")],
    name: Annotated[str, typer.Option(help="Unique Herdr agent name.")],
    role: Annotated[str, typer.Option(help="Semantic role, e.g. petey, qbert, creator.")],
    command: Annotated[str, typer.Option(help="Provider command, e.g. 'codex' or 'opencode'.")],
    tab: Annotated[str, typer.Option(help="Target tab label from the manifest.")] = "agents",
    split: Annotated[Optional[str], typer.Option(help="Optional split direction: right or down.")] = None,
    work_order: Annotated[Optional[Path], typer.Option(help="Durable work-order path for the agent.")] = None,
    env: Annotated[Optional[list[str]], typer.Option("--env", help="Additional KEY=VALUE env.")] = None,
    no_focus: Annotated[bool, typer.Option("--no-focus/--focus", help="Do not steal focus.")] = True,
    herdr_bin: Annotated[str, typer.Option(help="Herdr binary path.")] = "herdr",
    session: Annotated[Optional[str], typer.Option(help="Named Herdr session override.")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Print JSON manifest.")] = True,
) -> None:
    """Start one named provider agent inside a workstation pane."""
    manifest_path = manifest_path_from_run_dir(manifest) if manifest.is_dir() else manifest
    data = load_manifest(manifest_path)
    active_session = session or data.get("session")
    tab_id = data.get("tabs", {}).get(tab)
    if not tab_id:
        raise typer.BadParameter(f"unknown tab {tab!r}; have {sorted(data.get('tabs', {}))}")
    run_dir = Path(data["run_dir"])
    args = [
        "agent", "start", name, "--cwd", data["cwd"], "--workspace", data["workspace_id"], "--tab", tab_id,
        "--env", f"TAU_ROLE={role}", "--env", f"TAU_AGENT_NAME={name}", "--env", f"TAU_RUN_DIR={run_dir}",
    ]
    if work_order:
        args.extend(["--env", f"TAU_WORK_ORDER={work_order.expanduser().resolve()}"])
    for env_value in parse_env_options(env):
        args.extend(["--env", env_value])
    args.append("--no-focus" if no_focus else "--focus")
    if split:
        args.extend(["--split", split])
    args.append("--")
    args.extend(shlex.split(command))
    result = run_herdr(args, herdr_bin=herdr_bin, session=active_session)
    data.setdefault("agents", {})[name] = {
        "role": role,
        "command": command,
        "tab": tab,
        "started_at": utc_stamp(),
        "work_order": str(work_order.expanduser().resolve()) if work_order else None,
        "last_start_result": status_object(result),
    }
    save_manifest(manifest_path, data)
    print_json(data) if json_output else typer.echo(name)


@agent_app.command("send")
def agent_send(
    target: Annotated[str, typer.Argument(help="Agent target name, label, terminal id, or pane id.")],
    text: Annotated[Optional[str], typer.Option(help="Text to send. Use --file for longer prompts.")] = None,
    file: Annotated[Optional[Path], typer.Option(help="Prompt file to send.")] = None,
    newline: Annotated[bool, typer.Option("--newline/--no-newline", help="Append newline to submit the prompt.")] = True,
    events: Annotated[Optional[Path], typer.Option(help="Optional JSONL event path to append.")] = None,
    from_agent: Annotated[Optional[str], typer.Option(help="Optional sending role/name for event log.")] = None,
    herdr_bin: Annotated[str, typer.Option(help="Herdr binary path.")] = "herdr",
    session: Annotated[Optional[str], typer.Option(help="Named Herdr session.")] = None,
) -> None:
    """Send a live instruction to a Herdr agent terminal stream."""
    if file:
        payload = file.expanduser().read_text(encoding="utf-8")
    elif text is not None:
        payload = text
    else:
        payload = sys.stdin.read()
    if newline and not payload.endswith("\n"):
        payload += "\n"
    run_herdr(["agent", "send", target, payload], herdr_bin=herdr_bin, session=session)
    if events:
        append_event(events.expanduser(), {"ts": utc_stamp(), "from": from_agent, "target": target, "kind": "send", "chars": len(payload)})


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
    target: Annotated[str, typer.Argument(help="Agent target name, label, terminal id, or pane id.")],
    status: StatusValue = "blocked",
    timeout_s: Annotated[int, typer.Option(help="Timeout in seconds.")] = 600,
    herdr_bin: Annotated[str, typer.Option(help="Herdr binary path.")] = "herdr",
    session: Annotated[Optional[str], typer.Option(help="Named Herdr session.")] = None,
) -> None:
    """Wait until a Herdr agent reaches the requested state."""
    result = run_herdr(["agent", "wait", target, "--status", status, "--timeout", str(timeout_s * 1000)], herdr_bin=herdr_bin, session=session)
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
    run_herdr(["agent", "send", target, f"Notification from {from_agent}: {message}\n"], herdr_bin=herdr_bin, session=session)
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
    typer.echo("verify ok")


if __name__ == "__main__":
    app()
