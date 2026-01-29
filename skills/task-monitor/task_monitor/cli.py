"""Task Monitor CLI - Command-line interface commands.

This module provides all CLI commands for the task-monitor skill.
"""
from __future__ import annotations

from datetime import datetime

import typer
from rich.console import Console
from rich.table import Table

from task_monitor.config import DEFAULT_API_PORT, DEFAULT_REFRESH_INTERVAL
from task_monitor.models import HistoryEntry, TaskConfig
from task_monitor.stores import HistoryStore, SessionTracker, TaskRegistry
from task_monitor.tui import TaskMonitorTUI
from task_monitor.utils import get_task_status


console = Console()

# =============================================================================
# Main CLI Application
# =============================================================================

app_cli = typer.Typer(help="Task Monitor - TUI + API for long-running tasks")


@app_cli.command()
def tui(
    refresh: int = typer.Option(DEFAULT_REFRESH_INTERVAL, "--refresh", "-r", help="Refresh interval in seconds"),
    filter_term: str = typer.Option(None, "--filter", "-f", help="Filter tasks by name"),
):
    """Start the Rich TUI monitor."""
    monitor = TaskMonitorTUI(filter_term=filter_term)

    if not monitor.registry.tasks:
        console.print("[yellow]No tasks registered. Use 'register' command first.[/]")
        return

    monitor.run(refresh_interval=refresh)


@app_cli.command()
def serve(port: int = typer.Option(DEFAULT_API_PORT, "--port", "-p", help="Port to run on")):
    """Start the HTTP API server."""
    from task_monitor.http_api import run_server
    run_server(port)


@app_cli.command()
def register(
    name: str = typer.Option(..., "--name", "-n", help="Task name"),
    state: str = typer.Option(..., "--state", "-s", help="Path to state file"),
    total: int = typer.Option(None, "--total", "-t", help="Total items to process"),
    description: str = typer.Option(None, "--desc", "-d", help="Task description"),
    on_complete: str = typer.Option(None, "--on-complete", help="Command to run on completion (or 'batch-report')"),
    batch_type: str = typer.Option(None, "--batch-type", "-b", help="Batch type for reporting"),
    project: str = typer.Option(None, "--project", "-p", help="Project name for grouping"),
):
    """Register a task to monitor."""
    config = TaskConfig(
        name=name,
        state_file=state,
        total=total,
        description=description,
        on_complete=on_complete,
        batch_type=batch_type,
        project=project,
    )
    registry = TaskRegistry()
    registry.register(config)

    # Record in history
    history = HistoryStore()
    history.record(HistoryEntry(
        task_name=name,
        project=project,
        action="started",
        timestamp=datetime.now().isoformat(),
        details={"total": total, "description": description},
    ))

    # Add to active session if exists
    sessions = SessionTracker()
    active = sessions.get_active_session()
    if active:
        sessions.add_task(active["session_id"], name)

    console.print(f"[green]Registered task: {name}[/]")
    console.print(f"  State file: {state}")
    if total:
        console.print(f"  Total items: {total}")
    if project:
        console.print(f"  Project: {project}")


@app_cli.command()
def unregister(name: str = typer.Argument(..., help="Task name to unregister")):
    """Unregister a task."""
    registry = TaskRegistry()
    if name not in registry.tasks:
        console.print(f"[red]Task not found: {name}[/]")
        return
    registry.unregister(name)
    console.print(f"[green]Unregistered task: {name}[/]")


@app_cli.command()
def status():
    """Show quick status of all tasks."""
    registry = TaskRegistry()

    if not registry.tasks:
        console.print("[yellow]No tasks registered.[/]")
        return

    for name, task in registry.tasks.items():
        task_status = get_task_status(task)
        completed = task_status.get("completed", 0) or 0
        total = task.total or "?"
        pct = task_status.get("progress_pct")
        pct_str = f"({pct:.1f}%)" if pct else ""

        console.print(f"[cyan]{name}[/]: {completed}/{total} {pct_str}")


@app_cli.command("list")
def list_tasks():
    """List all registered tasks."""
    registry = TaskRegistry()

    if not registry.tasks:
        console.print("[yellow]No tasks registered.[/]")
        return

    for name, task in registry.tasks.items():
        console.print(f"[cyan]{name}[/]: {task.state_file}")


# =============================================================================
# History CLI Subcommands
# =============================================================================

history_app = typer.Typer(help="Search task history and session context")
app_cli.add_typer(history_app, name="history")


@history_app.command("search")
def history_search(
    term: str = typer.Argument(..., help="Search term (task name or project)"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
):
    """Search history by task name or project."""
    store = HistoryStore()
    results = store.search(term, limit=limit)

    if not results:
        console.print(f"[yellow]No history found for '{term}'[/]")
        return

    table = Table(title=f"History: {term}")
    table.add_column("Timestamp", style="dim")
    table.add_column("Task", style="cyan")
    table.add_column("Action")
    table.add_column("Project")
    table.add_column("Details")

    for entry in results:
        ts = entry.get("timestamp", "")[:19]
        action = entry.get("action", "")
        action_style = {
            "started": "[green]started[/]",
            "completed": "[bold green]completed[/]",
            "failed": "[red]failed[/]",
            "paused": "[yellow]paused[/]",
            "progress": "[blue]progress[/]",
        }.get(action, action)

        details = entry.get("details", {})
        detail_str = ""
        if details:
            if "completed" in details:
                detail_str = f"{details['completed']}/{details.get('total', '?')}"
            elif "reason" in details:
                detail_str = details["reason"][:30]

        table.add_row(
            ts,
            entry.get("task_name", "")[:20],
            action_style,
            entry.get("project", "")[:15] or "-",
            detail_str,
        )

    console.print(table)


@history_app.command("recent")
def history_recent(
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
):
    """Show recent history entries."""
    store = HistoryStore()
    results = store.get_recent(limit=limit)

    if not results:
        console.print("[yellow]No history found[/]")
        return

    table = Table(title="Recent History")
    table.add_column("Timestamp", style="dim")
    table.add_column("Task", style="cyan")
    table.add_column("Action")
    table.add_column("Project")

    for entry in results:
        ts = entry.get("timestamp", "")[:19]
        action = entry.get("action", "")
        action_style = {
            "started": "[green]started[/]",
            "completed": "[bold green]completed[/]",
            "failed": "[red]failed[/]",
            "paused": "[yellow]paused[/]",
            "progress": "[blue]progress[/]",
        }.get(action, action)

        table.add_row(
            ts,
            entry.get("task_name", "")[:25],
            action_style,
            entry.get("project", "")[:15] or "-",
        )

    console.print(table)


@history_app.command("project")
def history_project(
    project: str = typer.Argument(..., help="Project name"),
    limit: int = typer.Option(50, "--limit", "-n", help="Max results"),
):
    """Show history for a specific project."""
    store = HistoryStore()
    results = store.get_by_project(project, limit=limit)

    if not results:
        console.print(f"[yellow]No history found for project '{project}'[/]")
        return

    table = Table(title=f"Project History: {project}")
    table.add_column("Timestamp", style="dim")
    table.add_column("Task", style="cyan")
    table.add_column("Action")
    table.add_column("Details")

    for entry in results:
        ts = entry.get("timestamp", "")[:19]
        action = entry.get("action", "")
        details = entry.get("details", {})
        detail_str = ""
        if details and "completed" in details:
            detail_str = f"{details['completed']}/{details.get('total', '?')}"

        table.add_row(ts, entry.get("task_name", "")[:25], action, detail_str)

    console.print(table)


@history_app.command("resume")
def history_resume():
    """Show 'where was I?' context - incomplete tasks and last session."""
    store = HistoryStore()
    sessions = SessionTracker()

    context = store.get_last_session_context()
    last_session = sessions.get_last_session()

    console.print("\n[bold cyan]=== Where Was I? ===[/]\n")

    # Show last session info
    if last_session:
        console.print("[bold]Last Session:[/]")
        console.print(f"  Started: {last_session.get('started_at', '')[:19]}")
        if last_session.get("ended_at"):
            console.print(f"  Ended: {last_session.get('ended_at', '')[:19]}")
        else:
            console.print("  [yellow]Status: Still active (or interrupted)[/]")

        if last_session.get("project"):
            console.print(f"  Project: [cyan]{last_session['project']}[/]")

        if last_session.get("tasks"):
            console.print(f"  Tasks: {', '.join(last_session['tasks'][:5])}")

        if last_session.get("accomplishments"):
            console.print("  [green]Accomplishments:[/]")
            for acc in last_session["accomplishments"][:5]:
                console.print(f"    - {acc}")

        console.print()

    # Show incomplete tasks
    incomplete = context.get("incomplete_tasks", [])
    if incomplete:
        console.print("[bold yellow]Incomplete Tasks:[/]")
        for task in incomplete[:5]:
            console.print(f"  [cyan]{task['task_name']}[/]")
            console.print(f"    Last action: {task['last_action']} at {task['last_timestamp'][:19]}")
            if task.get("project"):
                console.print(f"    Project: {task['project']}")
            if task.get("details"):
                details = task["details"]
                if "completed" in details:
                    console.print(f"    Progress: {details['completed']}/{details.get('total', '?')}")
        console.print()

    # Show suggestion
    suggestion = context.get("suggestion")
    if suggestion:
        console.print("[bold green]Suggested Resume Point:[/]")
        console.print(f"  -> [bold]{suggestion['task_name']}[/]")
        if suggestion.get("details"):
            details = suggestion["details"]
            if "completed" in details:
                console.print(f"    Resume at: {details['completed']}/{details.get('total', '?')}")
    elif not incomplete:
        console.print("[green]All tasks completed! Start a new session.[/]")

    console.print()


@history_app.command("sessions")
def history_sessions(
    project: str = typer.Option(None, "--project", "-p", help="Filter by project"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max sessions"),
):
    """List recent work sessions."""
    tracker = SessionTracker()
    sessions = tracker.get_sessions(project=project, limit=limit)

    if not sessions:
        console.print("[yellow]No sessions found[/]")
        return

    table = Table(title="Work Sessions")
    table.add_column("Session ID", style="cyan")
    table.add_column("Project")
    table.add_column("Started", style="dim")
    table.add_column("Status")
    table.add_column("Tasks")
    table.add_column("Accomplishments")

    for session in sessions:
        status = session.get("status", "unknown")
        status_style = {
            "active": "[green]active[/]",
            "completed": "[dim]completed[/]",
            "interrupted": "[yellow]interrupted[/]",
        }.get(status, status)

        tasks = session.get("tasks", [])
        task_str = f"{len(tasks)} tasks" if tasks else "-"

        accs = session.get("accomplishments", [])
        acc_str = f"{len(accs)} items" if accs else "-"

        table.add_row(
            session.get("session_id", "")[:8],
            session.get("project", "")[:15] or "-",
            session.get("started_at", "")[:16],
            status_style,
            task_str,
            acc_str,
        )

    console.print(table)


# =============================================================================
# Session Management Commands
# =============================================================================

@app_cli.command("start-session")
def start_session(
    project: str = typer.Option(None, "--project", "-p", help="Project name"),
):
    """Start a new work session."""
    tracker = SessionTracker()

    # Check for existing active session
    active = tracker.get_active_session()
    if active:
        console.print(f"[yellow]Active session exists: {active['session_id']}[/]")
        console.print("End it with 'end-session' first, or continue working.")
        return

    session_id = tracker.start_session(project=project)
    console.print(f"[green]Started session: {session_id}[/]")
    if project:
        console.print(f"  Project: {project}")
    console.print("Use 'end-session' when done, or 'add-accomplishment' to track progress.")


@app_cli.command("end-session")
def end_session(
    notes: str = typer.Option(None, "--notes", "-n", help="Session notes"),
):
    """End the current work session."""
    tracker = SessionTracker()

    active = tracker.get_active_session()
    if not active:
        console.print("[yellow]No active session found[/]")
        return

    tracker.end_session(active["session_id"], notes=notes)
    console.print(f"[green]Ended session: {active['session_id']}[/]")

    if active.get("accomplishments"):
        console.print("Accomplishments:")
        for acc in active["accomplishments"]:
            console.print(f"  - {acc}")


@app_cli.command("add-accomplishment")
def add_accomplishment(
    text: str = typer.Argument(..., help="What you accomplished"),
):
    """Add an accomplishment to the current session."""
    tracker = SessionTracker()

    active = tracker.get_active_session()
    if not active:
        console.print("[yellow]No active session. Use 'start-session' first.[/]")
        return

    tracker.add_accomplishment(active["session_id"], text)
    console.print(f"[green]Added: {text}[/]")
