#!/usr/bin/env python3
"""Task-Monitor Client for Agent-Inbox.

Thin wrapper around shared TaskClient for tracking bug-fix progress.
Preserves the original function-based API used by dispatch_agent.py,
dispatcher_agent.py, and inbox_core.py.
"""
import json
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any

from common.task_monitor import TaskClient

# Configuration
STATE_DIR = Path(os.environ.get("AGENT_INBOX_DIR", Path.home() / ".agent-inbox")) / "task_states"

# Status to progress mapping
STATUS_PROGRESS = {
    "pending": 0,
    "dispatched": 25,
    "in_progress": 50,
    "needs_verification": 75,
    "done": 100,
}

# Track active TaskClient instances by task name
_task_clients: Dict[str, TaskClient] = {}


def register_bug_fix_task(message: dict) -> Optional[str]:
    """Register a bug-fix task in task-monitor.

    Args:
        message: Message dict from agent-inbox with id, to, from, message, dispatch

    Returns:
        Task name if registered, None if task-monitor unavailable
    """
    msg_id = message.get("id", "unknown")
    from_project = message.get("from", "unknown")
    dispatch = message.get("dispatch", {})
    model = dispatch.get("model", "sonnet")

    task_name = f"bug-fix-{msg_id}"

    STATE_DIR.mkdir(parents=True, exist_ok=True)

    client = TaskClient(
        skill_name=task_name,
        total=4,  # 4 status stages
        description=f"[{model}] Bug fix from {from_project}",
        state_dir=str(STATE_DIR),
        register=True,
    )
    client.stats.update({
        "inbox_msg_id": msg_id,
        "from_project": from_project,
        "to_project": message.get("to", "unknown"),
        "model": model,
        "priority": message.get("priority", "normal"),
    })

    _task_clients[task_name] = client
    print(f"[task-monitor] Registered task: {task_name}")
    return task_name


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

    client = _task_clients.get(task_name)
    if client:
        # Set completed directly to the right stage
        delta = completed - client.completed
        if delta > 0:
            item = details.get("current_item", "") if details else ""
            extra = details.get("stats", {}) if details else {}
            client.update(n=delta, item=item, **extra)
        print(f"[task-monitor] Updated {task_name}: {status} ({progress}%)")
        return True
    else:
        # Fallback: write state file directly
        state = {
            "completed": completed,
            "total": 4,
            "status": status,
            "current_item": details.get("current_item", "") if details else "",
            "stats": details.get("stats", {}) if details else {},
        }
        _write_state_file(task_name, state)
        print(f"[task-monitor] Updated {task_name}: {status} ({progress}%)")
        return True


def complete_task(task_name: str, success: bool, note: str = "") -> bool:
    """Mark a task as complete.

    Args:
        task_name: Task name
        success: Whether the bug was fixed successfully
        note: Completion note (e.g., commit hash)

    Returns:
        True if completed successfully
    """
    client = _task_clients.pop(task_name, None)
    if client:
        # Ensure we're at the right completed count
        remaining = 4 - client.completed if success else 3 - client.completed
        if remaining > 0:
            client.update(n=remaining, item=note or ("Completed" if success else "Needs verification"))
        client.finish(success=success)
        print(f"[task-monitor] Completed {task_name}: {'success' if success else 'needs verification'}")
        return True
    else:
        state = {
            "completed": 4 if success else 3,
            "total": 4,
            "status": "done" if success else "needs_verification",
            "current_item": note or ("Completed" if success else "Needs verification"),
            "stats": {"success": success, "note": note},
        }
        _write_state_file(task_name, state)
        print(f"[task-monitor] Completed {task_name}: {'success' if success else 'needs verification'}")
        return True


def get_task_status(task_name: str) -> Optional[dict]:
    """Get current task status.

    Args:
        task_name: Task name

    Returns:
        Task state dict or None if not found
    """
    state_file = STATE_DIR / f"{task_name}.json"
    if state_file.exists():
        try:
            return json.loads(state_file.read_text())
        except Exception:
            pass
    return None


def is_task_monitor_available() -> bool:
    """Check if task-monitor is available (always True with file-based approach)."""
    return True


def _write_state_file(task_name: str, state: dict) -> Path:
    """Write state file for a task (fallback when no client exists)."""
    from datetime import datetime, timezone
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_file = STATE_DIR / f"{task_name}.json"
    state["last_updated"] = datetime.now(timezone.utc).isoformat()
    state_file.write_text(json.dumps(state, indent=2))
    return state_file


# CLI for testing
if __name__ == "__main__":
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
