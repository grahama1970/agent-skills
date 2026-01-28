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

import asyncio
import json
import subprocess
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
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# Registry file for known tasks - Global location to share across all agents
REGISTRY_DIR = Path.home() / ".pi" / "task-monitor"
REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
REGISTRY_FILE = REGISTRY_DIR / "registry.json"
HISTORY_FILE = REGISTRY_DIR / "history.json"
SESSIONS_FILE = REGISTRY_DIR / "sessions.json"

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
    on_complete: Optional[str] = None  # Command or "batch-report" to auto-run
    batch_type: Optional[str] = None  # For batch-report integration
    completed_at: Optional[str] = None  # Timestamp when task reached 100%
    hook_executed: bool = False  # Track if on_complete was already run
    quality_thresholds: Optional[dict] = None  # Quality thresholds for early termination
    paused: bool = False  # Whether task is paused
    project: Optional[str] = None  # Project name for grouping


class SessionRecord(BaseModel):
    """Record of a work session."""
    session_id: str
    project: Optional[str] = None
    tasks: list[str] = []
    started_at: str
    ended_at: Optional[str] = None
    accomplishments: list[str] = []
    notes: Optional[str] = None
    status: str = "active"  # active, completed, interrupted


class HistoryEntry(BaseModel):
    """Entry in task history."""
    task_name: str
    project: Optional[str] = None
    action: str  # started, progress, completed, failed, paused, resumed
    timestamp: str
    details: Optional[dict] = None


class HistoryStore:
    """Store for task history - enables 'where was I?' queries."""

    def __init__(self, history_file: Path = HISTORY_FILE):
        self.history_file = history_file
        self._history: list[dict] = []
        self._load()

    def _load(self):
        """Load history from file."""
        if self.history_file.exists():
            try:
                with open(self.history_file) as f:
                    self._history = json.load(f)
            except Exception:
                self._history = []

    def _save(self):
        """Save history to file."""
        # Keep last 10000 entries
        if len(self._history) > 10000:
            self._history = self._history[-10000:]
        with open(self.history_file, 'w') as f:
            json.dump(self._history, f, indent=2)

    def record(self, entry: HistoryEntry):
        """Record a history entry."""
        self._history.append(entry.model_dump())
        self._save()

    def search(self, term: str, limit: int = 50) -> list[dict]:
        """Search history by task name or project."""
        term_lower = term.lower()
        results = []
        for entry in reversed(self._history):
            if (term_lower in entry.get("task_name", "").lower() or
                term_lower in (entry.get("project") or "").lower()):
                results.append(entry)
                if len(results) >= limit:
                    break
        return results

    def get_recent(self, limit: int = 20) -> list[dict]:
        """Get recent history entries."""
        return list(reversed(self._history[-limit:]))

    def get_by_project(self, project: str, limit: int = 100) -> list[dict]:
        """Get history for a specific project."""
        results = []
        for entry in reversed(self._history):
            if entry.get("project") == project:
                results.append(entry)
                if len(results) >= limit:
                    break
        return results

    def get_last_session_context(self) -> dict:
        """Get context about the last work session for 'where was I?'"""
        if not self._history:
            return {"message": "No history found"}

        # Find the most recent entries
        recent = self._history[-50:]

        # Group by task
        tasks_worked = {}
        for entry in recent:
            task = entry.get("task_name")
            if task not in tasks_worked:
                tasks_worked[task] = {
                    "task_name": task,
                    "project": entry.get("project"),
                    "last_action": entry.get("action"),
                    "last_timestamp": entry.get("timestamp"),
                    "details": entry.get("details"),
                }
            else:
                # Update with most recent
                tasks_worked[task]["last_action"] = entry.get("action")
                tasks_worked[task]["last_timestamp"] = entry.get("timestamp")
                tasks_worked[task]["details"] = entry.get("details")

        # Find incomplete tasks (started but not completed)
        incomplete = []
        completed = []
        for task_info in tasks_worked.values():
            if task_info["last_action"] in ["started", "progress", "paused"]:
                incomplete.append(task_info)
            elif task_info["last_action"] == "completed":
                completed.append(task_info)

        return {
            "incomplete_tasks": incomplete,
            "completed_tasks": completed,
            "last_activity": self._history[-1] if self._history else None,
            "suggestion": incomplete[0] if incomplete else None,
        }


class SessionTracker:
    """Track work sessions for resume context."""

    def __init__(self, sessions_file: Path = SESSIONS_FILE):
        self.sessions_file = sessions_file
        self._sessions: list[dict] = []
        self._load()

    def _load(self):
        """Load sessions from file."""
        if self.sessions_file.exists():
            try:
                with open(self.sessions_file) as f:
                    self._sessions = json.load(f)
            except Exception:
                self._sessions = []

    def _save(self):
        """Save sessions to file."""
        # Keep last 100 sessions
        if len(self._sessions) > 100:
            self._sessions = self._sessions[-100:]
        with open(self.sessions_file, 'w') as f:
            json.dump(self._sessions, f, indent=2)

    def start_session(self, project: str = None) -> str:
        """Start a new work session."""
        import uuid
        session_id = str(uuid.uuid4())[:8]
        session = SessionRecord(
            session_id=session_id,
            project=project,
            started_at=datetime.now().isoformat(),
            status="active",
        )
        self._sessions.append(session.model_dump())
        self._save()
        return session_id

    def end_session(self, session_id: str, notes: str = None):
        """End a work session."""
        for session in self._sessions:
            if session.get("session_id") == session_id:
                session["ended_at"] = datetime.now().isoformat()
                session["status"] = "completed"
                if notes:
                    session["notes"] = notes
                self._save()
                return

    def add_accomplishment(self, session_id: str, accomplishment: str):
        """Add an accomplishment to the current session."""
        for session in self._sessions:
            if session.get("session_id") == session_id:
                if "accomplishments" not in session:
                    session["accomplishments"] = []
                session["accomplishments"].append(accomplishment)
                self._save()
                return

    def add_task(self, session_id: str, task_name: str):
        """Add a task to the current session."""
        for session in self._sessions:
            if session.get("session_id") == session_id:
                if "tasks" not in session:
                    session["tasks"] = []
                if task_name not in session["tasks"]:
                    session["tasks"].append(task_name)
                    self._save()
                return

    def get_active_session(self) -> Optional[dict]:
        """Get the currently active session."""
        for session in reversed(self._sessions):
            if session.get("status") == "active":
                return session
        return None

    def get_last_session(self) -> Optional[dict]:
        """Get the most recent session (active or completed)."""
        return self._sessions[-1] if self._sessions else None

    def get_sessions(self, project: str = None, limit: int = 10) -> list[dict]:
        """Get recent sessions, optionally filtered by project."""
        results = []
        for session in reversed(self._sessions):
            if project and session.get("project") != project:
                continue
            results.append(session)
            if len(results) >= limit:
                break
        return results


class QualityMetrics(BaseModel):
    """Quality metrics for a task."""
    metrics: dict  # Current rolling metrics
    recent_failures: Optional[list] = None  # Recent failures for debugging
    timestamp: Optional[str] = None


class QualityStore:
    """Store for quality metrics history."""

    def __init__(self, store_dir: Path = REGISTRY_DIR):
        self.store_dir = store_dir / "quality"
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def push(self, task_name: str, metrics: QualityMetrics) -> None:
        """Push quality metrics for a task."""
        file_path = self.store_dir / f"{task_name}.json"

        # Load existing history
        history = []
        if file_path.exists():
            try:
                with open(file_path) as f:
                    history = json.load(f)
            except Exception:
                history = []

        # Add new metrics with timestamp
        entry = metrics.model_dump()
        entry["timestamp"] = datetime.now().isoformat()
        history.append(entry)

        # Keep last 1000 entries
        if len(history) > 1000:
            history = history[-1000:]

        # Save
        with open(file_path, 'w') as f:
            json.dump(history, f, indent=2)

    def get(self, task_name: str, limit: int = 100) -> list:
        """Get quality metrics history for a task."""
        file_path = self.store_dir / f"{task_name}.json"

        if not file_path.exists():
            return []

        try:
            with open(file_path) as f:
                history = json.load(f)
            return history[-limit:]
        except Exception:
            return []

    def get_latest(self, task_name: str) -> Optional[dict]:
        """Get latest quality metrics for a task."""
        history = self.get(task_name, limit=1)
        return history[-1] if history else None


class QualityPanel:
    """Standalone quality panel for testing and embedding."""

    def __init__(self, task_name: Optional[str] = None):
        self.task_name = task_name
        self.store = QualityStore()
        self.console = Console()

    def render_test(self) -> None:
        """Render panel with mock data for testing."""
        # Create mock data
        mock_metrics = {
            "schema_valid_rate": 0.98,
            "grounding_rate": 0.85,
            "taxonomy_rate": 0.92,
            "should_stop": False,
            "window_size": 100,
        }

        table = Table(show_header=True, header_style="bold", box=None)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")
        table.add_column("Status")

        for metric, value in mock_metrics.items():
            if metric.endswith("_rate"):
                status = "[green]OK[/]" if value >= 0.8 else "[red]LOW[/]"
                table.add_row(metric, f"{value:.1%}", status)
            elif metric == "should_stop":
                status = "[red]STOPPED[/]" if value else "[green]RUNNING[/]"
                table.add_row(metric, str(value), status)
            else:
                table.add_row(metric, str(value), "")

        panel = Panel(table, title="[bold]Quality Panel Test[/]", border_style="magenta")
        self.console.print(panel)

    def render(self) -> Panel:
        """Render panel with real data."""
        if not self.task_name:
            return Panel("[dim]No task specified[/]", title="Quality")

        latest = self.store.get_latest(self.task_name)
        if not latest:
            return Panel("[dim]No quality data[/]", title=f"Quality: {self.task_name}")

        metrics = latest.get("metrics", {})

        table = Table(show_header=True, header_style="bold", box=None)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")
        table.add_column("Status")

        for key in ["schema_valid_rate", "grounding_rate", "taxonomy_rate"]:
            if key in metrics:
                value = metrics[key]
                threshold = 0.9 if "schema" in key else 0.8
                status = "[green]OK[/]" if value >= threshold else "[red]LOW[/]"
                table.add_row(key, f"{value:.1%}", status)

        if metrics.get("should_stop"):
            table.add_row("status", "[red]STOPPED[/]", metrics.get("stop_reason", ""))

        return Panel(table, title=f"[bold]Quality: {self.task_name}[/]", border_style="magenta")


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

def get_scheduled_jobs() -> list[dict]:
    """Get list of scheduled jobs."""
    path = Path.home() / ".pi" / "scheduler" / "jobs.json"
    if not path.exists():
        return []
    try:
        with open(path) as f:
            data = json.load(f)
            return list(data.values())
    except Exception:
        return []

# =============================================================================

# =============================================================================
# FastAPI Endpoints
# =============================================================================

registry = TaskRegistry()
quality_store = QualityStore()


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
            "update_state": "POST /tasks/{name}/state",
            "push_quality": "POST /tasks/{name}/quality",
            "get_quality": "GET /tasks/{name}/quality",
            "pause_task": "POST /tasks/{name}/pause",
            "resume_task": "POST /tasks/{name}/resume",
            "check_paused": "GET /tasks/{name}/paused",
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


@app_api.post("/tasks/{name}/state")
async def update_task_state(name: str, state: dict):
    """Update task state via API (Push mode)."""
    if name not in registry.tasks:
        raise HTTPException(status_code=404, detail=f"Task '{name}' not found")

    task = registry.tasks[name]
    path = Path(task.state_file)

    # Ensure directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write state to file
    try:
        with open(path, 'w') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write state file: {e}")

    return {"status": "updated", "name": name}


@app_api.post("/tasks/{name}/quality")
async def push_quality_metrics(name: str, metrics: QualityMetrics):
    """Push quality metrics for a task."""
    # Note: Task doesn't need to be registered to push quality
    # This allows standalone quality monitoring
    quality_store.push(name, metrics)
    return {"status": "recorded", "name": name}


@app_api.get("/tasks/{name}/quality")
async def get_quality_metrics(name: str, limit: int = 100):
    """Get quality metrics history for a task."""
    history = quality_store.get(name, limit=limit)
    latest = quality_store.get_latest(name)

    # Calculate trends if we have enough data
    trends = {}
    if len(history) >= 2:
        first = history[0].get("metrics", {})
        last = history[-1].get("metrics", {})
        for key in ["schema_valid_rate", "grounding_rate", "taxonomy_rate"]:
            if key in first and key in last:
                trends[key] = last[key] - first[key]

    return {
        "task_name": name,
        "history_count": len(history),
        "latest": latest,
        "trends": trends,
        "history": history,
    }


@app_api.post("/tasks/{name}/pause")
async def pause_task(name: str):
    """Pause a task (for early termination)."""
    if name not in registry.tasks:
        raise HTTPException(status_code=404, detail=f"Task '{name}' not found")

    task = registry.tasks[name]
    task.paused = True
    registry.register(task)  # Save update
    return {"status": "paused", "name": name}


@app_api.post("/tasks/{name}/resume")
async def resume_task(name: str):
    """Resume a paused task."""
    if name not in registry.tasks:
        raise HTTPException(status_code=404, detail=f"Task '{name}' not found")

    task = registry.tasks[name]
    task.paused = False
    registry.register(task)  # Save update
    return {"status": "running", "name": name}


@app_api.get("/tasks/{name}/paused")
async def check_paused(name: str):
    """Check if a task is paused."""
    if name not in registry.tasks:
        return {"paused": False}  # Unknown tasks default to not paused

    task = registry.tasks[name]
    return {"paused": task.paused, "name": name}


@app_api.post("/history")
async def record_history(entry: HistoryEntry):
    """Record a history entry."""
    store = HistoryStore()
    store.record(entry)
    return {"status": "recorded", "task_name": entry.task_name}


@app_api.get("/history/search")
async def search_history(term: str, limit: int = 50):
    """Search history by task name or project."""
    store = HistoryStore()
    return {"results": store.search(term, limit=limit)}


@app_api.get("/history/recent")
async def get_recent_history(limit: int = 20):
    """Get recent history entries."""
    store = HistoryStore()
    return {"results": store.get_recent(limit=limit)}


@app_api.get("/history/resume")
async def get_resume_context():
    """Get 'where was I?' context."""
    store = HistoryStore()
    sessions = SessionTracker()
    return {
        "context": store.get_last_session_context(),
        "last_session": sessions.get_last_session(),
    }


@app_api.on_event("startup")
async def start_hook_poller():
    """Start background poller for task completion hooks."""
    asyncio.create_task(monitor_hooks())


async def monitor_hooks():
    """Poll tasks and execute on_complete hooks."""
    while True:
        try:
            # Reload registry to get latest state
            # (In a real app, maybe optimize this, but for now file read is fine)
            # Actually registry is loaded once globaly. But register() saves it.
            # If creating a new registry() object, it reloads.
            # Let's use the global registry but maybe reload it occasionally?
            # Actually the global registry variable 'registry' is what we use.
            # But if other processes update registry.json, we might miss it if we don't reload.
            # Let's reload.
            current_registry = TaskRegistry()
            
            for name, task in current_registry.tasks.items():
                if task.on_complete and not task.hook_executed:
                    status = get_task_status(task)
                    completed = status.get("completed", 0) or 0
                    total = task.total
                    
                    if total and completed >= total:
                        # Task complete! Run hook.
                        cmd = task.on_complete
                        
                        # Helper: "batch-report" shortcut
                        if cmd == "batch-report":
                             path = Path(task.state_file).parent
                             # Assume report.py is in same skill group or path
                             # We'll use 'uv run report.py' assuming we are in correct dir?
                             # No, safer to use absolute path to report.py if known.
                             # But we don't know where report.py is easily here.
                             # We'll assume 'batch-report' skill is installed.
                             # Better: simple shell command.
                             
                             batch_report_script = Path.home() / ".pi" / "skills" / "batch-report" / "report.py"
                             if not batch_report_script.exists():
                                 # Try alternate locations
                                 batch_report_script = Path.home() / ".agent" / "skills" / "batch-report" / "report.py"

                             if batch_report_script.exists():
                                 cmd = f"uv run {batch_report_script} analyze {path}"
                                 # We can't auto-send because we don't know where to send.

                             else:
                                 print(f"[Hook] Error: batch-report script not found")
                                 continue

                        # Replace placeholders
                        if "{output_dir}" in cmd:
                            cmd = cmd.format(output_dir=Path(task.state_file).parent)

                        console.print(f"[green][Hook] Executing: {cmd}[/]")
                        
                        # Execute in background (detached)
                        subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        
                        # Mark executed
                        task.hook_executed = True
                        task.completed_at = datetime.now().isoformat()
                        current_registry.register(task) # Save updates to file

        except Exception as e:
            console.print(f"[red][Hook] Error: {e}[/]")
            
        await asyncio.sleep(5)


# =============================================================================
# Rich TUI
# =============================================================================

class TaskMonitorTUI:
    """nvtop-style TUI for task monitoring."""

    def __init__(self, filter_term: Optional[str] = None):
        self.registry = TaskRegistry()
        self.filter_term = filter_term.lower() if filter_term else None
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
        table.add_column("Errors", justify="right", width=8, style="red")
        table.add_column("Current", width=20)

        for name, task in self.registry.tasks.items():
            if self.filter_term and self.filter_term not in name.lower():
                continue

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

            # Errors
            stats_dict = status.get("stats", {})
            errors = stats_dict.get("failed", 0) + stats_dict.get("errors", 0)
            err_str = f"{errors}" if errors > 0 else "-"

            table.add_row(name[:18], progress_str, rate_str, eta_str, err_str, current_str)

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

    def create_schedule_panel(self) -> Panel:
        """Create scheduled jobs panel."""
        jobs = get_scheduled_jobs()
        if not jobs:
             return Panel("No scheduled jobs found", title="[bold]Schedule[/]", border_style="yellow")

        table = Table(show_header=True, header_style="bold", box=None, expand=True)
        table.add_column("Job Name", style="cyan")
        table.add_column("Schedule", style="yellow")
        table.add_column("Next Run", style="green", justify="right")
        table.add_column("Status", style="bold")

        # Sort by next run time (if parseable?) 
        # Actually jobs.json 'next_run' might be string or absent.
        # Just list them.
        
        # Filter scheduler jobs too? Maybe.
        
        for job in jobs:
            name = job.get("name", "unknown")
            if self.filter_term and self.filter_term not in name.lower():
                continue
                
            cron = job.get("cron", "")
            # next_run is usually ISO string or timestamp? 
            # Scheduler saves it as isoformat usually? Or int?
            # jobs.json has "created_at": 1769101872
            # Let's assume it has human readable or we just show it.
            
            # Since I don't know exact format (I didn't inspect jobs.json deeply for next_run format),
            # I will just display what is there.
            
            # If enabled is False, show disabled
            enabled = job.get("enabled", True)
            status_str = "[green]Active[/]" if enabled else "[dim]Disabled[/]"
            
            table.add_row(name, cron, str(job.get("next_run", "-")), status_str)

        return Panel(table, title="[bold]Upcoming Schedule[/]", border_style="yellow")

    def create_quality_panel(self) -> Panel:
        """Create quality metrics panel for batch jobs."""
        # Get quality data for all registered tasks
        store = QualityStore()
        table = Table(show_header=True, header_style="bold", box=None, expand=True)
        table.add_column("Task", style="cyan", width=20)
        table.add_column("Schema", justify="right", width=10)
        table.add_column("Ground", justify="right", width=10)
        table.add_column("Taxonomy", justify="right", width=10)
        table.add_column("Status", width=12)
        table.add_column("Recent Failures", width=25)

        has_quality_data = False

        for name in self.registry.tasks:
            if self.filter_term and self.filter_term not in name.lower():
                continue

            latest = store.get_latest(name)
            if not latest:
                continue

            has_quality_data = True
            metrics = latest.get("metrics", {})

            # Format rates with color coding
            schema_rate = metrics.get("schema_valid_rate", 0)
            ground_rate = metrics.get("grounding_rate", 0)
            taxonomy_rate = metrics.get("taxonomy_rate", 0)

            def rate_style(rate: float, threshold: float = 0.9) -> str:
                if rate >= threshold:
                    return f"[green]{rate:.1%}[/]"
                elif rate >= threshold - 0.1:
                    return f"[yellow]{rate:.1%}[/]"
                else:
                    return f"[red]{rate:.1%}[/]"

            # Status
            should_stop = metrics.get("should_stop", False)
            if should_stop:
                status = "[red]STOPPED[/]"
            else:
                status = "[green]OK[/]"

            # Recent failures
            failures = latest.get("recent_failures", [])
            if failures:
                last_fail = failures[-1] if failures else {}
                fail_str = f"{last_fail.get('metric', '?')}: {last_fail.get('value', '?')}"
            else:
                fail_str = "[dim]-[/]"

            table.add_row(
                name[:20],
                rate_style(schema_rate, 0.95),
                rate_style(ground_rate, 0.80),
                rate_style(taxonomy_rate, 0.90),
                status,
                fail_str[:25],
            )

        if not has_quality_data:
            return Panel("[dim]No quality data available[/]", title="[bold]Quality[/]", border_style="magenta")

        return Panel(table, title="[bold]Quality Metrics[/]", border_style="magenta")

    def create_display(self) -> Layout:
        """Create the full layout."""
        layout = Layout()

        layout.split_column(
            Layout(self.create_header(), size=3),
            Layout(self.create_tasks_panel(), name="tasks"),
            Layout(self.create_quality_panel(), size=8),
            Layout(self.create_schedule_panel(), size=10),
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
def tui(
    refresh: int = typer.Option(2, "--refresh", "-r", help="Refresh interval in seconds"),
    filter_term: str = typer.Option(None, "--filter", "-f", help="Filter tasks by name"),
):
    """Start the Rich TUI monitor."""
    monitor = TaskMonitorTUI(filter_term=filter_term)

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


# =============================================================================
# History CLI Commands
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

    console.print("\n[bold cyan]═══ Where Was I? ═══[/]\n")

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
        console.print(f"  → [bold]{suggestion['task_name']}[/]")
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


if __name__ == "__main__":
    app_cli()
