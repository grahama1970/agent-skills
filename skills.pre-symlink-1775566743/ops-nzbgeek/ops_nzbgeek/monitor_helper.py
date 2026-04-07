"""Task-monitor skill integration helper for download progress tracking."""

import json
import time
from pathlib import Path
from typing import Optional

# Task-monitor paths (main registry, not skill code location)
TASK_MONITOR_DIR = Path.home() / ".pi" / "task-monitor"
REGISTRY_FILE = TASK_MONITOR_DIR / "registry.json"
STATE_DIR = TASK_MONITOR_DIR / "state"


def register_download(
    nzb_id: str,
    title: str,
    size: Optional[int] = None,
) -> bool:
    """
    Register download with task-monitor.

    Args:
        nzb_id: NZB ID from SABnzbd
        title: Download title/name
        size: Optional file size in bytes

    Returns:
        True if registered successfully, False otherwise
    """
    if not TASK_MONITOR_DIR.exists():
        return False  # Task-monitor not available

    # Create state directory if it doesn't exist
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    # Create initial state file
    state_file = STATE_DIR / f"{nzb_id}.json"
    state = {
        "task_id": nzb_id,
        "type": "download",
        "title": title,
        "status": "queued",
        "progress": 0,
        "size": size or 0,
        "downloaded": 0,
        "speed": "0 B/s",
        "eta": "Unknown",
        "started_at": time.time(),
        "updated_at": time.time(),
    }

    try:
        state_file.write_text(json.dumps(state, indent=2))

        # Update registry
        if REGISTRY_FILE.exists():
            registry = json.loads(REGISTRY_FILE.read_text())
        else:
            registry = {"tasks": []}

        # Add to registry if not already present
        task_ids = [t.get("task_id") for t in registry.get("tasks", [])]
        if nzb_id not in task_ids:
            registry["tasks"].append({
                "task_id": nzb_id,
                "type": "download",
                "title": title,
                "skill": "ops-nzbgeek",
                "status": "queued",
                "state_file": str(state_file),
            })
            REGISTRY_FILE.write_text(json.dumps(registry, indent=2))

        return True

    except Exception as e:
        print(f"Warning: Failed to register with task-monitor: {e}")
        return False


def update_progress(
    nzb_id: str,
    progress: int,
    speed: str,
    eta: str,
    downloaded: int,
    status: str = "downloading",
) -> bool:
    """
    Update download progress in task-monitor.

    Args:
        nzb_id: NZB ID from SABnzbd
        progress: Progress percentage (0-100)
        speed: Download speed string (e.g., "5.2 MB/s")
        eta: Estimated time remaining (e.g., "2m 15s")
        downloaded: Bytes downloaded so far
        status: Current status (queued, downloading, completed, failed)

    Returns:
        True if updated successfully, False otherwise
    """
    state_file = STATE_DIR / f"{nzb_id}.json"

    if not state_file.exists():
        return False  # Not registered

    try:
        state = json.loads(state_file.read_text())
        state.update({
            "status": status,
            "progress": progress,
            "speed": speed,
            "eta": eta,
            "downloaded": downloaded,
            "updated_at": time.time(),
        })

        if status in ["completed", "failed"]:
            state["completed_at"] = time.time()
            elapsed = state["completed_at"] - state["started_at"]
            state["elapsed_seconds"] = int(elapsed)

        state_file.write_text(json.dumps(state, indent=2))
        return True

    except Exception as e:
        print(f"Warning: Failed to update task-monitor: {e}")
        return False


def mark_complete(nzb_id: str, final_size: Optional[int] = None) -> bool:
    """
    Mark download as complete in task-monitor.

    Args:
        nzb_id: NZB ID from SABnzbd
        final_size: Optional final file size in bytes

    Returns:
        True if marked complete successfully, False otherwise
    """
    state_file = STATE_DIR / f"{nzb_id}.json"

    if not state_file.exists():
        return False  # Not registered

    try:
        state = json.loads(state_file.read_text())
        state.update({
            "status": "completed",
            "progress": 100,
            "speed": "0 B/s",
            "eta": "0s",
            "completed_at": time.time(),
            "updated_at": time.time(),
        })

        if final_size:
            state["size"] = final_size
            state["downloaded"] = final_size

        elapsed = state["completed_at"] - state["started_at"]
        state["elapsed_seconds"] = int(elapsed)

        state_file.write_text(json.dumps(state, indent=2))

        # Update registry
        if REGISTRY_FILE.exists():
            registry = json.loads(REGISTRY_FILE.read_text())
            for task in registry.get("tasks", []):
                if task.get("task_id") == nzb_id:
                    task["status"] = "completed"
                    break
            REGISTRY_FILE.write_text(json.dumps(registry, indent=2))

        return True

    except Exception as e:
        print(f"Warning: Failed to mark complete in task-monitor: {e}")
        return False


def mark_failed(nzb_id: str, error: str) -> bool:
    """
    Mark download as failed in task-monitor.

    Args:
        nzb_id: NZB ID from SABnzbd
        error: Error message

    Returns:
        True if marked failed successfully, False otherwise
    """
    state_file = STATE_DIR / f"{nzb_id}.json"

    if not state_file.exists():
        return False  # Not registered

    try:
        state = json.loads(state_file.read_text())
        state.update({
            "status": "failed",
            "error": error,
            "completed_at": time.time(),
            "updated_at": time.time(),
        })

        elapsed = state["completed_at"] - state["started_at"]
        state["elapsed_seconds"] = int(elapsed)

        state_file.write_text(json.dumps(state, indent=2))

        # Update registry
        if REGISTRY_FILE.exists():
            registry = json.loads(REGISTRY_FILE.read_text())
            for task in registry.get("tasks", []):
                if task.get("task_id") == nzb_id:
                    task["status"] = "failed"
                    break
            REGISTRY_FILE.write_text(json.dumps(registry, indent=2))

        return True

    except Exception as e:
        print(f"Warning: Failed to mark failed in task-monitor: {e}")
        return False
