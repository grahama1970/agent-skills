"""Skill event processing for Discord publisher."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from publisher_config import EVENTS_DIR

# Status colors and icons for skill events
STATUS_COLORS = {
    "ok": 0x57F287,       # Green
    "warning": 0xFEE75C,  # Yellow
    "critical": 0xED4245, # Red
    "info": 0x5865F2,     # Blurple
}

STATUS_ICONS = {
    "ok": "\U0001f7e2",
    "warning": "\U0001f7e1",
    "critical": "\U0001f534",
    "info": "\U0001f535",
}


def process_skill_events(post_webhook_fn) -> int:
    """Process pending skill events from the events directory.

    Args:
        post_webhook_fn: Callable that posts a webhook embed. Signature: post_webhook(embed=dict) -> bool

    Returns the number of events processed.
    """
    if not EVENTS_DIR.exists():
        return 0

    processed = 0
    event_files = sorted(EVENTS_DIR.glob("*.json"))

    for event_file in event_files:
        try:
            event = json.loads(event_file.read_text())

            # Build embed from event
            status = event.get("status", "info")
            icon = STATUS_ICONS.get(status, "\U0001f535")
            color = STATUS_COLORS.get(status, 0x5865F2)

            skill = event.get("skill", "unknown")
            title = event.get("title", skill)
            message = event.get("message", "")
            event_type = event.get("event_type", "info")

            # Format based on event type
            if event_type == "health":
                embed_title = f"{icon} {title}"
            elif event_type == "complete":
                embed_title = f"Completed: {title}"
            elif event_type == "error":
                embed_title = f"Error: {title}"
            elif event_type == "progress":
                pct = event.get("data", {}).get("percent", "")
                embed_title = f"{title} \u2014 {pct}%" if pct else title
            else:
                embed_title = f"{icon} {title}"

            embed = {
                "title": embed_title,
                "description": message,
                "color": color,
                "footer": {"text": f"skill: {skill}"},
                "timestamp": event.get("timestamp", datetime.now().isoformat()),
            }

            # Add data fields if present
            data = event.get("data", {})
            if data and len(data) <= 3:
                embed["fields"] = [
                    {"name": k, "value": str(v), "inline": True}
                    for k, v in list(data.items())[:3]
                ]

            post_webhook_fn(embed=embed)
            processed += 1

            # Remove processed event
            event_file.unlink()

        except Exception as e:
            print(f"Error processing event {event_file}: {e}")
            # Move to failed directory
            failed_dir = EVENTS_DIR / "failed"
            failed_dir.mkdir(exist_ok=True)
            event_file.rename(failed_dir / event_file.name)

    return processed
