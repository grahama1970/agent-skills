#!/usr/bin/env python3
"""
Task-Monitor Client for Agent-Inbox.

Provides integration with task-monitor for tracking bug-fix progress.
Degrades gracefully when task-monitor is unavailable.
"""
import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any

# Configuration
API_URL = os.environ.get("TASK_MONITOR_API_URL", "http://localhost:8765")
STATE_DIR = Path(os.environ.get("AGENT_INBOX_DIR", Path.home() / ".agent-inbox")) / "task_states"

# Status to progress percentage mapping
STATUS_PROGRESS = {
    "pending": 0,
    "dispatched": 25,
    "in_progress": 50,
    "needs_verification": 75,
    "done": 100,
}


def _ensure_state_dir():
    """Ensure state directory exists."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def _api_request(endpoint: str, method: str = "GET", data: Optional[dict] = None) -> tuple[bool, Any]:
    """Make HTTP request to task-monitor API.

    Args:
        endpoint: API endpoint (e.g., "/tasks")
        method: HTTP method
        data: Optional JSON body

    Returns:
        (success, response_data_or_error)
    """
    try:
        url = f"{API_URL}{endpoint}"
        req = urllib.request.Request(
            url,
            method=method,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
        )
        if data:
            req.data = json.dumps(data).encode()

        with urllib.request.urlopen(req, timeout=5) as resp:
            return True, json.loads(resp.read().decode())

    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return False, f"Connection error: {e.reason}"
    except Exception as e:
        return False, str(e)


def _write_state_file(task_name: str, state: dict) -> Path:
    """Write state file for a task.

    Args:
        task_name: Task name
        state: State dict with completed, total, status, etc.

    Returns:
        Path to state file
    """
    _ensure_state_dir()
    state_file = STATE_DIR / f"{task_name}.json"
    state["last_updated"] = datetime.now(timezone.utc).isoformat()
    state_file.write_text(json.dumps(state, indent=2))
    return state_file


def register_bug_fix_task(message: dict) -> Optional[str]:
    """Register a bug-fix task in task-monitor.

    Args:
        message: Message dict from agent-inbox with id, to, from, message, dispatch

    Returns:
        Task name if registered, None if task-monitor unavailable
    """
    msg_id = message.get("id", "unknown")
    to_project = message.get("to", "unknown")
    from_project = message.get("from", "unknown")
    dispatch = message.get("dispatch", {})
    model = dispatch.get("model", "sonnet")
    priority = message.get("priority", "normal")

    # Generate task name
    task_name = f"bug-fix-{msg_id}"

    # Create initial state file
    # Bug fixes have 4 stages: pending(0) → dispatched(25) → in_progress(50) → done(100)
    state = {
        "completed": 0,
        "total": 4,  # 4 status stages
        "status": "pending",
        "description": f"[{model}] Bug fix from {from_project}",
        "current_item": message.get("message", "")[:100],
        "stats": {
            "inbox_msg_id": msg_id,
            "from_project": from_project,
            "to_project": to_project,
            "model": model,
            "priority": priority,
        }
    }
    state_file = _write_state_file(task_name, state)

    # Build on_complete command for auto-ack
    on_complete = f"agent-inbox ack {msg_id} --note 'Completed via task-monitor'"

    # Register with task-monitor API
    task_config = {
        "name": task_name,
        "state_file": str(state_file),
        "total": 4,
        "description": f"[{model}] Bug fix from {from_project}",
        "on_complete": on_complete,
        "project": to_project,
    }

    success, result = _api_request("/tasks", method="POST", data=task_config)

    if success:
        print(f"[task-monitor] Registered task: {task_name}")
        return task_name
    else:
        print(f"[task-monitor] Warning: Could not register task ({result})")
        print(f"[task-monitor] Bug-fix will proceed without live monitoring")
        return task_name  # Return name anyway so we can track locally


def update_task_progress(task_name: str, status: str, details: Optional[dict] = None) -> bool:
    """Update task progress in task-monitor.

    Args:
        task_name: Task name (from register_bug_fix_task)
        status: New status (pending, dispatched, in_progress, needs_verification, done)
        details: Optional additional details to record

    Returns:
        True if updated successfully
    """
    progress = STATUS_PROGRESS.get(status, 0)
    completed = progress // 25  # 0, 1, 2, 3, or 4

    # Update state file
    state = {
        "completed": completed,
        "total": 4,
        "status": status,
        "current_item": details.get("current_item", "") if details else "",
        "stats": details.get("stats", {}) if details else {},
    }
    state_file = _write_state_file(task_name, state)

    # Also push to API
    success, result = _api_request(f"/tasks/{task_name}/state", method="POST", data=state)

    if success:
        print(f"[task-monitor] Updated {task_name}: {status} ({progress}%)")
    else:
        print(f"[task-monitor] Warning: Could not push state ({result})")

    return success


def complete_task(task_name: str, success: bool, note: str = "") -> bool:
    """Mark a task as complete.

    Args:
        task_name: Task name
        success: Whether the bug was fixed successfully
        note: Completion note (e.g., commit hash)

    Returns:
        True if completed successfully
    """
    status = "done" if success else "needs_verification"

    state = {
        "completed": 4 if success else 3,
        "total": 4,
        "status": status,
        "current_item": note or ("Completed" if success else "Needs verification"),
        "stats": {
            "success": success,
            "note": note,
        }
    }
    state_file = _write_state_file(task_name, state)

    # Push to API
    api_success, result = _api_request(f"/tasks/{task_name}/state", method="POST", data=state)

    if api_success:
        print(f"[task-monitor] Completed {task_name}: {'success' if success else 'needs verification'}")
    else:
        print(f"[task-monitor] Warning: Could not push completion ({result})")

    return api_success


def get_task_status(task_name: str) -> Optional[dict]:
    """Get current task status.

    Args:
        task_name: Task name

    Returns:
        Task state dict or None if not found
    """
    # Try state file first
    state_file = STATE_DIR / f"{task_name}.json"
    if state_file.exists():
        try:
            return json.loads(state_file.read_text())
        except Exception:
            pass

    # Try API
    success, result = _api_request(f"/tasks/{task_name}")
    if success:
        return result

    return None


def is_task_monitor_available() -> bool:
    """Check if task-monitor API is available.

    Returns:
        True if API is reachable
    """
    success, _ = _api_request("/")
    return success


# CLI for testing
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: task_monitor_client.py <command> [args]")
        print("Commands:")
        print("  check           - Check if task-monitor is available")
        print("  register <json> - Register task from message JSON")
        print("  update <name> <status> - Update task status")
        print("  complete <name> [note] - Mark task complete")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "check":
        available = is_task_monitor_available()
        print(f"Task-monitor available: {available}")
        sys.exit(0 if available else 1)

    elif cmd == "register":
        if len(sys.argv) < 3:
            print("Usage: register <message_json>")
            sys.exit(1)
        message = json.loads(sys.argv[2])
        task_name = register_bug_fix_task(message)
        print(f"Task name: {task_name}")

    elif cmd == "update":
        if len(sys.argv) < 4:
            print("Usage: update <task_name> <status>")
            sys.exit(1)
        update_task_progress(sys.argv[2], sys.argv[3])

    elif cmd == "complete":
        if len(sys.argv) < 3:
            print("Usage: complete <task_name> [note]")
            sys.exit(1)
        note = sys.argv[3] if len(sys.argv) > 3 else ""
        complete_task(sys.argv[2], success=True, note=note)

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
