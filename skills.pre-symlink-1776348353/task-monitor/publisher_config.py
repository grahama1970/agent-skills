"""Configuration, constants, and utilities for Discord publisher."""

from __future__ import annotations

import os
import time
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

# Load environment - check multiple locations
load_dotenv(find_dotenv(usecwd=True))
_clawd_env = Path(__file__).resolve().parent.parent.parent.parent / "clawd" / ".env"
if _clawd_env.exists():
    load_dotenv(str(_clawd_env))

# Configuration
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEB_HOOK_URL", "") or os.environ.get("TASK_MONITOR_DISCORD_WEBHOOK", "")
EVENTS_DIR = Path.home() / ".pi" / "task-monitor" / "events"
REGISTRY_FILE = Path.home() / ".pi" / "task-monitor" / "registry.json"
DASHBOARD_CACHE = Path.home() / ".pi" / "task-monitor" / "dashboard_cache.png"

# Rate limiting
_last_post_time = 0.0
_min_post_interval = 2.0  # seconds between posts


def _rate_limit():
    """Ensure minimum interval between webhook posts."""
    global _last_post_time
    elapsed = time.time() - _last_post_time
    if elapsed < _min_post_interval:
        time.sleep(_min_post_interval - elapsed)
    _last_post_time = time.time()


def progress_bar(pct: float, width: int = 10) -> str:
    """Generate Unicode progress bar."""
    if pct < 0:
        pct = 0
    if pct > 100:
        pct = 100
    filled = int(pct / 100 * width)
    return "\u25b0" * filled + "\u25b1" * (width - filled)


def progress_bar_modern(pct: float, width: int = 12) -> str:
    """Generate modern progress bar with better Unicode chars."""
    if pct < 0:
        pct = 0
    if pct > 100:
        pct = 100
    filled = int(pct / 100 * width)
    # Use block characters for cleaner look
    return "\u2588" * filled + "\u2591" * (width - filled)


# Discord Components V2 Type IDs
COMPONENT_ACTION_ROW = 1
COMPONENT_SECTION = 9
COMPONENT_TEXT_DISPLAY = 10
COMPONENT_THUMBNAIL = 11
COMPONENT_SEPARATOR = 14
COMPONENT_CONTAINER = 17

# Message flags
FLAG_IS_COMPONENTS_V2 = 1 << 15  # 32768
