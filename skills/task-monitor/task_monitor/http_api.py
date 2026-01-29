"""Task Monitor HTTP API - FastAPI server for remote monitoring.

This module provides the HTTP API for task monitoring and management.
"""
from __future__ import annotations

import asyncio
import subprocess
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from rich.console import Console

from task_monitor.config import BATCH_REPORT_PATHS, HOOK_POLL_INTERVAL
from task_monitor.models import HistoryEntry, QualityMetrics, TaskConfig
from task_monitor.stores import HistoryStore, QualityStore, SessionTracker, TaskRegistry
from task_monitor.utils import get_task_status


# =============================================================================
# FastAPI Application
# =============================================================================

app_api = FastAPI(
    title="Task Monitor API",
    description="Monitor long-running tasks across projects",
    version="1.0.0",
)

console = Console()

# Global registry and quality store instances
registry = TaskRegistry()
quality_store = QualityStore()


# =============================================================================
# Root and Info Endpoints
# =============================================================================

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


# =============================================================================
# Task CRUD Endpoints
# =============================================================================

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
        import json
        with open(path, 'w', encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write state file: {e}")

    return {"status": "updated", "name": name}


# =============================================================================
# Quality Metrics Endpoints
# =============================================================================

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


# =============================================================================
# Pause/Resume Endpoints
# =============================================================================

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


# =============================================================================
# History Endpoints
# =============================================================================

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


# =============================================================================
# Background Tasks
# =============================================================================

@app_api.on_event("startup")
async def start_hook_poller():
    """Start background poller for task completion hooks."""
    asyncio.create_task(monitor_hooks())


async def monitor_hooks():
    """Poll tasks and execute on_complete hooks."""
    while True:
        try:
            # Reload registry to get latest state
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
                            batch_report_script = None

                            for script_path in BATCH_REPORT_PATHS:
                                if script_path.exists():
                                    batch_report_script = script_path
                                    break

                            if batch_report_script:
                                cmd = f"uv run {batch_report_script} analyze {path}"
                            else:
                                console.print("[red][Hook] Error: batch-report script not found[/]")
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
                        current_registry.register(task)  # Save updates to file

        except Exception as e:
            console.print(f"[red][Hook] Error: {e}[/]")

        await asyncio.sleep(HOOK_POLL_INTERVAL)


def run_server(port: int):
    """Run the HTTP API server.

    Args:
        port: Port number to listen on
    """
    import uvicorn
    from task_monitor.config import API_HOST

    console.print(f"[green]Starting Task Monitor API on port {port}[/]")
    console.print(f"  GET http://localhost:{port}/all - All task status")
    console.print(f"  GET http://localhost:{port}/tasks/{{name}} - Specific task")
    console.print(f"  POST http://localhost:{port}/tasks - Register task")
    uvicorn.run(app_api, host=API_HOST, port=port, log_level="warning")
