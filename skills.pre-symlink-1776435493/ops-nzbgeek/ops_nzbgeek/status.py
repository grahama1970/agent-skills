"""SABnzbd status and queue management module."""

import os
from pathlib import Path
from typing import Optional
import httpx
from dotenv import load_dotenv

# Load environment variables from repo root
REPO_ROOT = Path.home() / "workspace" / "experiments" / "pi-mono"
ENV_FILE = REPO_ROOT / ".env"
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)
else:
    load_dotenv()  # Fallback to default search

# SABnzbd API configuration
SAB_API_KEY = os.getenv("SABNZBD_API_KEY")
SAB_BASE_URL = os.getenv("SABNZBD_BASE_URL", "http://localhost:8090")


def get_requests_session() -> httpx.Client:
    """Get an httpx client with retry logic."""
    transport = httpx.HTTPTransport(retries=3)
    client = httpx.Client(transport=transport, timeout=30.0)
    return client


def get_queue(nzb_id: Optional[str] = None) -> dict:
    """
    Get SABnzbd queue status.

    Args:
        nzb_id: Optional specific NZB ID to check

    Returns:
        Dict with queue status, active downloads, speed, disk space

    Raises:
        ValueError: If API key is missing
        httpx.HTTPError: If API request fails
    """
    if not SAB_API_KEY:
        raise ValueError("SABNZBD_API_KEY environment variable not set")

    params = {
        "mode": "queue",
        "apikey": SAB_API_KEY,
        "output": "json",
    }

    if nzb_id:
        params["nzo_ids"] = nzb_id

    url = f"{SAB_BASE_URL.rstrip('/')}/api"
    session = get_requests_session()

    try:
        resp = session.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as e:
        raise httpx.HTTPError(f"SABnzbd API request failed: {e}")

    queue = data.get("queue", {})

    # Extract key metrics
    return {
        "status": queue.get("status", "unknown"),
        "paused": queue.get("paused", False),
        "speed": queue.get("speed", "0 B/s"),
        "kbpersec": queue.get("kbpersec", 0.0),
        "size": queue.get("size", "0 B"),
        "sizeleft": queue.get("sizeleft", "0 B"),
        "noofslots": queue.get("noofslots", 0),
        "diskspace": queue.get("diskspace1", "Unknown"),
        "slots": queue.get("slots", []),
    }


def get_history(nzb_id: Optional[str] = None, limit: int = 20) -> dict:
    """
    Get SABnzbd history (completed/failed downloads).

    Args:
        nzb_id: Optional specific NZB ID to check
        limit: Maximum number of history items to return

    Returns:
        Dict with history status and slots

    Raises:
        ValueError: If API key is missing
        httpx.HTTPError: If API request fails
    """
    if not SAB_API_KEY:
        raise ValueError("SABNZBD_API_KEY environment variable not set")

    params = {
        "mode": "history",
        "apikey": SAB_API_KEY,
        "output": "json",
        "limit": limit,
    }

    url = f"{SAB_BASE_URL.rstrip('/')}/api"
    session = get_requests_session()

    try:
        resp = session.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as e:
        raise httpx.HTTPError(f"SABnzbd API request failed: {e}")

    history = data.get("history", {})

    # If looking for specific nzb_id, filter
    slots = history.get("slots", [])
    if nzb_id:
        slots = [s for s in slots if s.get("nzo_id") == nzb_id]

    return {
        "total_size": history.get("total_size", "0 B"),
        "noofslots": len(slots),
        "slots": slots,
    }


def control_download(action: str, nzb_id: str) -> dict:
    """
    Control a download (pause, resume, cancel).

    Args:
        action: Action to perform (pause, resume, delete)
        nzb_id: NZB ID to control

    Returns:
        Dict with status and response

    Raises:
        ValueError: If API key is missing or action is invalid
        httpx.HTTPError: If API request fails
    """
    if not SAB_API_KEY:
        raise ValueError("SABNZBD_API_KEY environment variable not set")

    valid_actions = ["pause", "resume", "delete"]
    if action not in valid_actions:
        raise ValueError(f"Invalid action: {action}. Must be one of: {', '.join(valid_actions)}")

    params = {
        "mode": "queue",
        "name": action,
        "value": nzb_id,
        "apikey": SAB_API_KEY,
        "output": "json",
    }

    url = f"{SAB_BASE_URL.rstrip('/')}/api"
    session = get_requests_session()

    try:
        resp = session.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as e:
        raise httpx.HTTPError(f"SABnzbd API request failed: {e}")

    if not data.get("status"):
        error = data.get("error", "Unknown error")
        raise ValueError(f"SABnzbd rejected {action} action: {error}")

    return {
        "status": "success",
        "action": action,
        "nzb_id": nzb_id,
        "response": data,
    }


def format_queue_status(queue_data: dict, json_output: bool = False) -> str:
    """
    Format queue status for display.

    Args:
        queue_data: Queue data dict
        json_output: If True, return JSON string

    Returns:
        Formatted string (human-readable or JSON)
    """
    if json_output:
        import json
        return json.dumps(queue_data, indent=2)

    status = queue_data.get("status", "unknown")
    paused = queue_data.get("paused", False)
    speed = queue_data.get("speed", "0 B/s")
    size = queue_data.get("size", "0 B")
    sizeleft = queue_data.get("sizeleft", "0 B")
    noofslots = queue_data.get("noofslots", 0)
    diskspace = queue_data.get("diskspace", "Unknown")

    lines = [
        "=== SABnzbd Queue Status ===",
        f"Status: {status} {'(PAUSED)' if paused else ''}",
        f"Speed: {speed}",
        f"Queue size: {noofslots} items",
        f"Total size: {size} ({sizeleft} remaining)",
        f"Disk space: {diskspace}",
    ]

    slots = queue_data.get("slots", [])
    if slots:
        lines.append("\nActive downloads:")
        for slot in slots[:5]:  # Show first 5
            filename = slot.get("filename", "Unknown")
            percentage = slot.get("percentage", 0)
            timeleft = slot.get("timeleft", "Unknown")
            lines.append(f"  - {filename} ({percentage}%, ETA: {timeleft})")

        if len(slots) > 5:
            lines.append(f"  ... and {len(slots) - 5} more")

    return "\n".join(lines)


def format_control_result(result: dict) -> str:
    """
    Format control action result for display.

    Args:
        result: Control result dict

    Returns:
        Formatted string
    """
    action = result.get("action", "unknown")
    nzb_id = result.get("nzb_id", "unknown")
    status = result.get("status", "unknown")

    action_names = {
        "pause": "paused",
        "resume": "resumed",
        "delete": "cancelled",
    }

    action_display = action_names.get(action, action)

    return f"Download {action_display} successfully\nNZB ID: {nzb_id}\nStatus: {status}"
