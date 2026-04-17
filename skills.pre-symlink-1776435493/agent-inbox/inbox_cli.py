"""
Agent-Inbox CLI - Command-line interface and main() entry point.

Contains the typer-based CLI with all subcommands.
"""

import json
import sys
from pathlib import Path
from typing import Optional, List

import typer

from inbox_core import (
    register_project,
    unregister_project,
    list_projects,
    send,
    list_messages,
    read_message,
    ack_message,
    check_inbox,
    update_status,
    list_thread,
    scan_projects,
    _detect_project,
    _load_registry,
    _get_triage_module,
    INBOX_DIR,
)

app = typer.Typer(help="Inter-agent message inbox")


@app.command()
def register(
    name: str = typer.Argument(..., help="Project name"),
    path: str = typer.Argument(..., help="Project path"),
):
    register_project(name, path)


@app.command()
def unregister(
    name: str = typer.Argument(..., help="Project name"),
):
    unregister_project(name)


@app.command()
def projects(
    output_json: bool = typer.Option(False, "--json", help="Output JSON"),
):
    proj = list_projects()
    if output_json:
        print(json.dumps(proj, indent=2))
    else:
        if not proj:
            print("No projects registered.")
            print("Use: agent-inbox register <name> <path>")
        else:
            print("Registered projects:")
            for name, path in sorted(proj.items()):
                print(f"  {name}: {path}")


@app.command("send")
def send_cmd(
    to: str = typer.Option(..., help="Target project"),
    msg_type: str = typer.Option("info", "--type", help="Message type: bug, request, info, question"),
    priority: str = typer.Option("normal", help="Priority: low, normal, high, critical"),
    from_project: Optional[str] = typer.Option(None, "--from", help="Source project (auto-detected)"),
    model: Optional[str] = typer.Option(None, help="Model for headless agent dispatch (e.g. sonnet, codex-5.2)"),
    timeout: int = typer.Option(30, help="Timeout in minutes for headless agent (default: 30)"),
    test_command: Optional[str] = typer.Option(None, "--test", help="Command to verify fix before auto-ack"),
    no_dispatch: bool = typer.Option(False, help="Disable auto-spawn for this message"),
    reply_to: Optional[str] = typer.Option(None, help="Message ID to reply to (for threading)"),
    dry_run: bool = typer.Option(False, help="Print message JSON without writing file"),
    register_path: Optional[str] = typer.Option(None, help="Auto-register target project with this path before sending"),
    context_files: Optional[List[str]] = typer.Option(None, "--context-file", help="File to include as context (can be used multiple times)"),
    no_triage: bool = typer.Option(False, help="Skip AI triage for this message"),
    priority_override: bool = typer.Option(False, help="Keep user's priority even if AI suggests different"),
    message: Optional[str] = typer.Argument(None, help="Message (or read from stdin)"),
):
    msg = message
    if not msg:
        msg = sys.stdin.read().strip()
    if not msg:
        print("Error: No message provided")
        raise typer.Exit(code=1)

    if register_path:
        register_project(to, register_path)

    send(
        to,
        msg,
        msg_type=msg_type,
        priority=priority,
        from_project=from_project,
        model=model,
        auto_spawn=not no_dispatch,
        timeout_minutes=timeout,
        test_command=test_command,
        reply_to=reply_to,
        dry_run=dry_run,
        context_files=context_files,
        use_triage=not no_triage,
        priority_override=priority_override,
    )


@app.command("list")
def list_cmd(
    project: Optional[str] = typer.Option(None, help="Filter by project (auto-detected if omitted)"),
    show_all: bool = typer.Option(False, "--all", help="Show all projects"),
    status: str = typer.Option("pending", help="Status filter: pending, done"),
    output_json: bool = typer.Option(False, "--json", help="Output JSON"),
):
    proj = None if show_all else (project or _detect_project())
    messages = list_messages(project=proj, status=status)
    if output_json:
        print(json.dumps(messages, indent=2))
    else:
        if not messages:
            print(f"No {status} messages." + (f" (project: {proj})" if proj else ""))
        else:
            for m in messages:
                status_icon = "+" if m.get("status") == "pending" else "v"
                priority_icon = {"critical": "!", "high": "*", "normal": "-", "low": "."}.get(m.get("priority", "normal"), "-")
                print(f"{status_icon} {priority_icon} [{m['id']}] {m.get('type', 'info')}: {m.get('from', '?')} -> {m.get('to', '?')}")
                first_line = m.get("message", "").split("\n")[0][:50]
                print(f"      {first_line}...")


@app.command("read")
def read_cmd(
    msg_id: str = typer.Argument(..., help="Message ID"),
    output_json: bool = typer.Option(False, "--json", help="Output JSON"),
):
    msg = read_message(msg_id)
    if not msg:
        print(f"Message not found: {msg_id}")
        raise typer.Exit(code=1)
    if output_json:
        print(json.dumps(msg, indent=2))
    else:
        print(f"ID: {msg['id']}")
        print(f"From: {msg.get('from', '?')} -> To: {msg.get('to', '?')}")
        print(f"Type: {msg.get('type', 'info')} | Priority: {msg.get('priority', 'normal')}")
        print(f"Status: {msg.get('status', '?')}")
        print(f"Created: {msg.get('created_at', '?')}")
        if msg.get("acked_at"):
            print(f"Acked: {msg.get('acked_at')}")
        if msg.get("ack_note"):
            print(f"Note: {msg.get('ack_note')}")
        print()
        print("--- Message ---")
        print(msg.get("message", ""))


@app.command()
def ack(
    msg_id: str = typer.Argument(..., help="Message ID"),
    note: Optional[str] = typer.Option(None, help="Acknowledgment note"),
):
    ack_message(msg_id, note=note)


@app.command()
def check(
    project: Optional[str] = typer.Option(None, help="Project name (auto-detected if omitted)"),
    show_all: bool = typer.Option(False, "--all", help="Check all registered projects"),
    quiet: bool = typer.Option(False, "-q", "--quiet", help="Only return count"),
):
    count = check_inbox(project=project, quiet=quiet, all_projects=show_all)
    if quiet:
        print(count)
    raise typer.Exit(code=0 if count == 0 else 1)


@app.command()
def whoami():
    project = _detect_project()
    registry = _load_registry()
    if project in registry:
        print(f"Project: {project}")
        print(f"Path: {registry[project]}")
    else:
        print(f"Project: {project} (not registered)")
        print(f"Current dir: {Path.cwd()}")
        print()
        print("To register: agent-inbox register {project} {Path.cwd()}")


@app.command()
def tui():
    try:
        from . import tui as tui_mod
    except ImportError:
        import tui as tui_mod

    tui_app = tui_mod.InboxTUI()
    tui_app.run()


@app.command()
def scan(
    path: str = typer.Argument(".", help="Root path to scan"),
    depth: int = typer.Option(2, help="Max depth to scan"),
):
    scan_projects(Path(path), max_depth=depth)


@app.command("update-status")
def update_status_cmd(
    msg_id: str = typer.Argument(..., help="Message ID"),
    status: str = typer.Argument(..., help="Status: pending, dispatched, in_progress, needs_verification, done"),
    note: Optional[str] = typer.Option(None, help="Status note"),
):
    update_status(msg_id, status, note=note)


@app.command()
def reply(
    msg_id: str = typer.Argument(..., help="Message ID to reply to"),
    message: Optional[str] = typer.Argument(None, help="Reply message (or read from stdin)"),
    msg_type: str = typer.Option("info", "--type", help="Message type: bug, request, info, question"),
    priority: str = typer.Option("normal", help="Priority: low, normal, high, critical"),
    model: Optional[str] = typer.Option(None, help="Model: sonnet, opus-4.5, codex-5.2, codex-5.2-high"),
):
    parent = read_message(msg_id)
    if not parent:
        print(f"Parent message not found: {msg_id}")
        raise typer.Exit(code=1)

    msg = message
    if not msg:
        msg = sys.stdin.read().strip()
    if not msg:
        print("Error: No message provided")
        raise typer.Exit(code=1)

    # Reply to sender; if I am the sender, reply to recipient
    to_project = parent.get("from")
    current_project = _detect_project() or "unknown"
    if to_project == current_project:
        to_project = parent.get("to")

    send(
        to_project=to_project,
        message=msg,
        msg_type=msg_type,
        priority=priority,
        model=model,
        reply_to=msg_id,
        from_project=current_project,
    )


@app.command()
def thread(
    thread_id: str = typer.Argument(..., help="Thread ID (usually first message ID)"),
    output_json: bool = typer.Option(False, "--json", help="Output JSON"),
):
    messages = list_thread(thread_id)
    if output_json:
        print(json.dumps(messages, indent=2))
    else:
        if not messages:
            print(f"No messages found in thread: {thread_id}")
        else:
            print(f"=== Thread: {thread_id} ({len(messages)} messages) ===")
            print()
            for i, m in enumerate(messages):
                indent = "  " if m.get("parent_id") else ""
                arrow = "-> " if m.get("parent_id") else ""
                print(f"{indent}{arrow}[{m['id']}] {m.get('from', '?')} -> {m.get('to', '?')}")
                print(f"{indent}  {m.get('type', 'info')} | {m.get('priority', 'normal')} | {m.get('status', '?')}")
                print(f"{indent}  {m.get('created_at', '?')}")
                first_line = m.get("message", "").split("\n")[0][:60]
                print(f"{indent}  {first_line}...")
                print()


@app.command("triage")
def triage_cmd(
    action: str = typer.Argument(..., help="Action: classify, route, webhook-add, webhook-remove, webhook-list, log"),
    triage_message_text: Optional[str] = typer.Option(None, "--message", help="Message to triage"),
    msg_id: Optional[str] = typer.Option(None, "--msg-id", help="Message ID for log retrieval"),
    url: Optional[str] = typer.Option(None, help="Webhook URL"),
    events: Optional[str] = typer.Option(None, help="Comma-separated webhook events"),
    project: Optional[str] = typer.Option(None, help="Project filter for webhook"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Use heuristics only"),
    output_json: bool = typer.Option(False, "--json", help="Output JSON"),
):
    triage_mod = _get_triage_module()
    if not triage_mod:
        print("Error: Triage module not available")
        raise typer.Exit(code=1)

    if action == "classify":
        if not triage_message_text:
            print("Error: --message required for classify")
            raise typer.Exit(code=1)
        result = triage_mod.triage_message(triage_message_text, use_llm=not no_llm)
        if output_json:
            print(json.dumps(result, indent=2))
        else:
            cls = result.get("classification", {})
            print(f"Severity: {cls.get('severity', 'unknown')}")
            print(f"Priority: {result.get('suggested_priority', 'normal')}")
            print(f"Model: {result.get('suggested_model', 'sonnet')}")
            print(f"Reasoning: {cls.get('reasoning', 'N/A')}")
            if result.get("suggested_project"):
                print(f"Suggested Project: {result['suggested_project']}")

    elif action == "route":
        if not triage_message_text:
            print("Error: --message required for route")
            raise typer.Exit(code=1)
        proj = triage_mod.auto_route(triage_message_text)
        if proj:
            print(f"Suggested project: {proj}")
        else:
            print("Could not auto-detect project from message")

    elif action == "webhook-add":
        if not url:
            print("Error: --url required")
            raise typer.Exit(code=1)
        events_list = events.split(",") if events else None
        triage_mod.register_webhook(url, events_list, project)
        print(f"Webhook registered: {url}")

    elif action == "webhook-remove":
        if not url:
            print("Error: --url required")
            raise typer.Exit(code=1)
        if triage_mod.unregister_webhook(url):
            print(f"Webhook removed: {url}")
        else:
            print("Webhook not found")

    elif action == "webhook-list":
        webhooks = triage_mod._load_webhooks()
        if webhooks:
            for wh in webhooks:
                print(f"  {wh['url']}")
                print(f"    Events: {wh.get('events', ['all'])}")
                if wh.get('project'):
                    print(f"    Project: {wh['project']}")
        else:
            print("No webhooks registered")

    elif action == "log":
        if not msg_id:
            print("Error: --msg-id required for log")
            raise typer.Exit(code=1)
        log = triage_mod.get_triage_log(msg_id)
        if log:
            if output_json:
                print(json.dumps(log, indent=2))
            else:
                print(f"Message ID: {log.get('msg_id')}")
                print(f"Timestamp: {log.get('timestamp')}")
                cls = log.get("classification", {})
                print(f"Severity: {cls.get('severity')}")
                print(f"Reasoning: {cls.get('reasoning')}")
                routing = log.get("routing", {})
                print(f"Routed to: {routing.get('target_project')} ({routing.get('method')})")
        else:
            print(f"No triage log found for: {msg_id}")


def main():
    app()


if __name__ == "__main__":
    main()
