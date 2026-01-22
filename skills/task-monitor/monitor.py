#!/usr/bin/env python3
"""Task Monitor - Rich TUI + HTTP API for monitoring long-running tasks.

Provides both a nvtop-style terminal UI and an HTTP API for cross-agent monitoring.

Usage:
    # Start TUI (interactive)
    uv run python monitor.py tui

    # Start API server
    uv run python monitor.py serve --port 8765

    # Register a task
    uv run python monitor.py register --name "my-task" --state /path/to/state.json --total 1000

    # Quick status check
    uv run python monitor.py status
"""
from __future__ import annotations

import json
import os
import signal
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# Registry file for known tasks
REGISTRY_FILE = Path(__file__).parent / ".task_registry.json"

app_cli = typer.Typer(help="Task Monitor - TUI + API for long-running tasks")
app_api = FastAPI(
    title="Task Monitor API",
    description="Monitor long-running tasks across projects",
    version="1.0.0",
)
console = Console()


class TaskConfig(BaseModel):
    """Configuration for a monitored task."""
    name: str
    state_file: str
    total: Optional[int] = None
    description: Optional[str] = None


class TaskRegistry:
    """Registry of monitored tasks."""

    def __init__(self, registry_file: Path = REGISTRY_FILE):
        self.registry_file = registry_file
        self.tasks: dict[str, TaskConfig] = {}
        self._load()

    def _load(self):
        """Load registry from file."""
        if self.registry_file.exists():
            try:
                with open(self.registry_file) as f:
                    data = json.load(f)
                    self.tasks = {k: TaskConfig(**v) for k, v in data.get("tasks", {}).items()}
            except Exception:
                self.tasks = {}

    def _save(self):
        """Save registry to file."""
        data = {"tasks": {k: v.model_dump() for k, v in self.tasks.items()}}
        with open(self.registry_file, 'w') as f:
            json.dump(data, f, indent=2)

    def register(self, config: TaskConfig):
        """Register a new task."""
        self.tasks[config.name] = config
        self._save()

    def unregister(self, name: str):
        """Unregister a task."""
        if name in self.tasks:
            del self.tasks[name]
            self._save()

    def get_all(self) -> dict[str, TaskConfig]:
        """Get all registered tasks."""
        return self.tasks.copy()


def read_task_state(state_file: str) -> dict:
    """Read state from a task's state file."""
    path = Path(state_file)

    if not path.exists():
        return {"error": "State file not found", "state_file": state_file}

    try:
        with open(path) as f:
            state = json.load(f)
    except Exception as e:
        return {"error": f"Failed to read state: {e}", "state_file": state_file}

    # Standard fields we look for
    return {
        "state_file": state_file,
        "completed": len(state.get("completed", [])) if isinstance(state.get("completed"), list) else state.get("completed", 0),
        "stats": state.get("stats", {}),
        "current_item": state.get("current_video", state.get("current_item", state.get("current", ""))),
        "current_method": state.get("current_method", ""),
        "last_updated": state.get("last_updated", ""),
        "consecutive_failures": state.get("consecutive_failures", 0),
        "raw": state,  # Include raw state for debugging
    }


def get_task_status(task: TaskConfig) -> dict:
    """Get full status for a task."""
    state = read_task_state(task.state_file)

    # Add task config info
    state["name"] = task.name
    state["total"] = task.total
    state["description"] = task.description

    # Calculate progress percentage
    if task.total and "completed" in state and state["completed"]:
        state["progress_pct"] = (state["completed"] / task.total) * 100
    else:
        state["progress_pct"] = None

    # Remove raw state from API responses (too verbose)
    if "raw" in state:
        del state["raw"]

    return state


# =============================================================================
# FastAPI Endpoints
# =============================================================================

registry = TaskRegistry()


@app_api.get("/")
async def list_endpoints():
    """List available endpoints."""
    return {
        "endpoints": {
            "list_tasks": "GET /tasks",
            "get_task": "GET /tasks/{name}",
            "all_status": "GET /all",
            "register": "POST /tasks",
            "unregister": "DELETE /tasks/{name}",
        },
        "task_count": len(registry.tasks),
    }


@app_api.get("/tasks")
async def list_tasks():
    """List all registered tasks."""
    return {"tasks": list(registry.tasks.keys())}


@app_api.get("/tasks/{name}")
async def get_task(name: str):
    """Get status of a specific task."""
    if name not in registry.tasks:
        raise HTTPException(status_code=404, detail=f"Task '{name}' not found")
    return get_task_status(registry.tasks[name])


@app_api.get("/all")
async def get_all_status():
    """Get status of all registered tasks."""
    results = {}
    totals = {"completed": 0, "total": 0}

    for name, task in registry.tasks.items():
        status = get_task_status(task)
        results[name] = status

        if "completed" in status and status["completed"]:
            totals["completed"] += status["completed"]
        if task.total:
            totals["total"] += task.total

    if totals["total"] > 0:
        totals["progress_pct"] = (totals["completed"] / totals["total"]) * 100

    return {"tasks": results, "totals": totals}


@app_api.post("/tasks")
async def register_task(config: TaskConfig):
    """Register a new task to monitor."""
    registry.register(config)
    return {"status": "registered", "name": config.name}


@app_api.delete("/tasks/{name}")
async def unregister_task(name: str):
    """Unregister a task."""
    if name not in registry.tasks:
        raise HTTPException(status_code=404, detail=f"Task '{name}' not found")
    registry.unregister(name)
    return {"status": "unregistered", "name": name}


# =============================================================================
# Rich TUI
# =============================================================================

class TaskMonitorTUI:
    """nvtop-style TUI for task monitoring."""

    def __init__(self):
        self.registry = TaskRegistry()
        self.running = False
        self.start_time = time.time()
        self._history: dict[str, list[tuple[float, int]]] = {}

    def _get_rate(self, name: str, completed: int) -> float:
        """Calculate rate from history."""
        now = time.time()

        if name not in self._history:
            self._history[name] = []

        self._history[name].append((now, completed))

        # Keep last 10 minutes
        cutoff = now - 600
        self._history[name] = [(t, c) for t, c in self._history[name] if t > cutoff]

        if len(self._history[name]) < 2:
            return 0.0

        oldest_time, oldest_count = self._history[name][0]
        newest_time, newest_count = self._history[name][-1]

        time_diff = newest_time - oldest_time
        count_diff = newest_count - oldest_count

        if time_diff < 60:
            return 0.0

        return (count_diff / time_diff) * 3600

    def create_header(self) -> Panel:
        """Create header panel."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        elapsed = time.time() - self.start_time
        elapsed_str = f"{int(elapsed // 3600):02d}:{int((elapsed % 3600) // 60):02d}:{int(elapsed % 60):02d}"

        header = Text()
        header.append("Task Monitor", style="bold white on blue")
        header.append(f"  {now}  ", style="dim")
        header.append(f"Elapsed: {elapsed_str}", style="cyan")

        return Panel(header, style="bold")

    def create_tasks_panel(self) -> Panel:
        """Create tasks status panel."""
        table = Table(show_header=True, header_style="bold", box=None, expand=True)
        table.add_column("Task", style="cyan", width=18)
        table.add_column("Progress", width=35)
        table.add_column("Rate", justify="right", width=10)
        table.add_column("ETA", justify="right", width=10)
        table.add_column("Current", width=20)

        for name, task in self.registry.tasks.items():
            status = get_task_status(task)

            completed = status.get("completed", 0) or 0
            total = task.total or 0
            pct = status.get("progress_pct", 0) or 0

            # Progress bar
            bar_width = 20
            filled = int(bar_width * pct / 100) if pct else 0
            bar = "█" * filled + "░" * (bar_width - filled)

            # Rate and ETA
            rate = self._get_rate(name, completed)
            if rate > 0 and total > completed:
                remaining = total - completed
                eta_hours = remaining / rate
                if eta_hours < 1:
                    eta_str = f"{int(eta_hours * 60)}m"
                elif eta_hours < 24:
                    eta_str = f"{eta_hours:.1f}h"
                else:
                    eta_str = f"{eta_hours / 24:.1f}d"
                rate_str = f"{rate:.1f}/h"
            else:
                eta_str = "--"
                rate_str = "--"

            # Current item
            current = status.get("current_item", "")
            method = status.get("current_method", "")
            if current:
                if method == "whisper":
                    current_str = f"[magenta]🎤 {current[:14]}[/]"
                elif method == "fetching":
                    current_str = f"[cyan]⏳ {current[:14]}[/]"
                else:
                    current_str = f"{current[:17]}"
            else:
                current_str = "[dim]idle[/]"

            if total:
                progress_str = f"[cyan]{bar}[/] {completed:5d}/{total:5d} ({pct:5.1f}%)"
            else:
                progress_str = f"[cyan]{bar}[/] {completed:5d}/??? "

            table.add_row(name[:18], progress_str, rate_str, eta_str, current_str)

        return Panel(table, title="[bold]Tasks[/]", border_style="blue")

    def create_totals_panel(self) -> Panel:
        """Create totals panel."""
        total_completed = 0
        total_items = 0

        for name, task in self.registry.tasks.items():
            status = get_task_status(task)
            completed = status.get("completed", 0) or 0
            total_completed += completed
            if task.total:
                total_items += task.total

        pct = (total_completed / total_items * 100) if total_items else 0
        bar_width = 50
        filled = int(bar_width * pct / 100)
        bar = "█" * filled + "░" * (bar_width - filled)

        content = Text()
        content.append(f"Overall Progress: [{bar}] ", style="bold")
        content.append(f"{total_completed}/{total_items} ({pct:.1f}%)", style="cyan")

        return Panel(content, title="[bold]Totals[/]", border_style="green")

    def create_display(self) -> Layout:
        """Create the full layout."""
        layout = Layout()

        layout.split_column(
            Layout(self.create_header(), size=3),
            Layout(self.create_tasks_panel(), name="tasks"),
            Layout(self.create_totals_panel(), size=3),
        )

        return layout

    def run(self, refresh_interval: int = 2):
        """Run the TUI."""
        self.running = True
        self.start_time = time.time()

        def signal_handler(sig, frame):
            self.running = False

        signal.signal(signal.SIGINT, signal_handler)

        with Live(self.create_display(), console=console, refresh_per_second=1, screen=True) as live:
            while self.running:
                live.update(self.create_display())
                time.sleep(refresh_interval)

        console.print("\n[green]Monitor stopped.[/]")


# =============================================================================
# CLI Commands
# =============================================================================

@app_cli.command()
def tui(refresh: int = typer.Option(2, "--refresh", "-r", help="Refresh interval in seconds")):
    """Start the Rich TUI monitor."""
    monitor = TaskMonitorTUI()

    if not monitor.registry.tasks:
        console.print("[yellow]No tasks registered. Use 'register' command first.[/]")
        return

    monitor.run(refresh_interval=refresh)


@app_cli.command()
def serve(port: int = typer.Option(8765, "--port", "-p", help="Port to run on")):
    """Start the HTTP API server."""
    console.print(f"[green]Starting Task Monitor API on port {port}[/]")
    console.print(f"  GET http://localhost:{port}/all - All task status")
    console.print(f"  GET http://localhost:{port}/tasks/{{name}} - Specific task")
    console.print(f"  POST http://localhost:{port}/tasks - Register task")
    uvicorn.run(app_api, host="0.0.0.0", port=port, log_level="warning")


@app_cli.command()
def register(
    name: str = typer.Option(..., "--name", "-n", help="Task name"),
    state: str = typer.Option(..., "--state", "-s", help="Path to state file"),
    total: int = typer.Option(None, "--total", "-t", help="Total items to process"),
    description: str = typer.Option(None, "--desc", "-d", help="Task description"),
):
    """Register a task to monitor."""
    config = TaskConfig(name=name, state_file=state, total=total, description=description)
    registry = TaskRegistry()
    registry.register(config)
    console.print(f"[green]Registered task: {name}[/]")
    console.print(f"  State file: {state}")
    if total:
        console.print(f"  Total items: {total}")


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
        status = get_task_status(task)
        completed = status.get("completed", 0) or 0
        total = task.total or "?"
        pct = status.get("progress_pct")
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


if __name__ == "__main__":
    app_cli()
