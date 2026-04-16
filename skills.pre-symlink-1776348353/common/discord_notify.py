#!/usr/bin/env python3
"""Shared Discord notification utility for all skills.

Any skill can import this to post notifications to Discord.
Notifications are written to an event file that task-monitor's
daemon picks up and posts to Discord.

Usage:
    from common.discord_notify import notify, SkillEvent

    # Simple notification
    notify("ops-workstation", "warning", "Memory at 85%")

    # Structured event
    notify(
        skill="batch-report",
        status="complete",
        title="Batch analysis complete",
        message="Processed 1,234 items with 3 failures",
        data={"total": 1234, "failures": 3, "duration_s": 3600}
    )

Event Types:
    - health: System health alerts (ops-workstation, ops-arango)
    - progress: Long-running task progress
    - complete: Task/batch completion
    - error: Errors requiring attention
    - info: Informational updates
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Optional

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(usecwd=True), override=False)

# Event storage directory
EVENTS_DIR = Path.home() / ".pi" / "task-monitor" / "events"

EventType = Literal["health", "progress", "complete", "error", "info"]
StatusLevel = Literal["ok", "warning", "critical", "info"]


def notify(
    skill: str,
    status: StatusLevel,
    message: str,
    *,
    title: Optional[str] = None,
    event_type: EventType = "info",
    data: Optional[dict[str, Any]] = None,
    priority: Literal["low", "normal", "high"] = "normal",
) -> Path:
    """Post a notification event for Discord.

    Args:
        skill: Name of the skill posting the event
        status: Status level (ok, warning, critical, info)
        message: Human-readable message
        title: Optional title (defaults to skill name)
        event_type: Type of event (health, progress, complete, error, info)
        data: Optional structured data
        priority: Priority level for ordering

    Returns:
        Path to the created event file
    """
    EVENTS_DIR.mkdir(parents=True, exist_ok=True)

    event = {
        "timestamp": datetime.now().isoformat(),
        "skill": skill,
        "status": status,
        "event_type": event_type,
        "title": title or skill,
        "message": message,
        "priority": priority,
        "data": data or {},
    }

    # Use timestamp + skill for unique filename
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    event_file = EVENTS_DIR / f"{ts}_{skill}.json"
    event_file.write_text(json.dumps(event, indent=2))

    return event_file


def notify_health(
    skill: str,
    status: StatusLevel,
    message: str,
    **kwargs,
) -> Path:
    """Convenience wrapper for health events."""
    return notify(skill, status, message, event_type="health", **kwargs)


def notify_complete(
    skill: str,
    message: str,
    *,
    success: bool = True,
    **kwargs,
) -> Path:
    """Convenience wrapper for completion events."""
    status: StatusLevel = "ok" if success else "critical"
    return notify(skill, status, message, event_type="complete", **kwargs)


def notify_error(
    skill: str,
    message: str,
    **kwargs,
) -> Path:
    """Convenience wrapper for error events."""
    return notify(skill, "critical", message, event_type="error", priority="high", **kwargs)


def notify_progress(
    skill: str,
    message: str,
    *,
    percent: Optional[float] = None,
    **kwargs,
) -> Path:
    """Convenience wrapper for progress events."""
    data = kwargs.pop("data", {})
    if percent is not None:
        data["percent"] = percent
    return notify(skill, "info", message, event_type="progress", data=data, **kwargs)


# =============================================================================
# Direct Discord posting (for skills that need immediate posting)
# =============================================================================

def post_directly(
    message: str,
    *,
    title: Optional[str] = None,
    color: int = 0x5865F2,  # Discord blurple
    webhook_url: Optional[str] = None,
) -> bool:
    """Post directly to Discord webhook (bypasses event system).

    Use sparingly - prefer notify() for most cases.
    """
    import httpx

    url = webhook_url or os.environ.get("DISCORD_WEB_HOOK_URL", "")
    if not url:
        print("WARNING: No Discord webhook URL configured")
        return False

    embed = {
        "title": title or "Skill Notification",
        "description": message,
        "color": color,
        "timestamp": datetime.now().isoformat(),
    }

    try:
        with httpx.Client(timeout=10) as client:
            r = client.post(url, json={"embeds": [embed]})
            return r.status_code in (200, 204)
    except Exception as e:
        print(f"Discord post failed: {e}")
        return False


# Color constants for direct posting
COLOR_OK = 0x57F287      # Green
COLOR_WARNING = 0xFEE75C  # Yellow
COLOR_CRITICAL = 0xED4245 # Red
COLOR_INFO = 0x5865F2     # Blurple
