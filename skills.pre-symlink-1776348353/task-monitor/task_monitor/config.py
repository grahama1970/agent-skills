"""Task Monitor Configuration - Constants, paths, and shared state.

This module centralizes all configuration settings and paths used across
the task-monitor skill modules.
"""
from __future__ import annotations

from pathlib import Path

# =============================================================================
# Registry Paths
# =============================================================================

# Global location to share across all agents
REGISTRY_DIR = Path.home() / ".pi" / "task-monitor"
REGISTRY_DIR.mkdir(parents=True, exist_ok=True)

REGISTRY_FILE = REGISTRY_DIR / "registry.json"
HISTORY_FILE = REGISTRY_DIR / "history.json"
SESSIONS_FILE = REGISTRY_DIR / "sessions.json"
QUALITY_DIR = REGISTRY_DIR / "quality"

# =============================================================================
# Scheduler Integration
# =============================================================================

SCHEDULER_DIR = Path.home() / ".pi" / "scheduler"
SCHEDULER_JOBS_FILE = SCHEDULER_DIR / "jobs.json"

# =============================================================================
# Batch Report Integration
# =============================================================================

# Locations to search for batch-report skill
BATCH_REPORT_PATHS = [
    Path.home() / ".pi" / "skills" / "batch-report" / "report.py",
    Path.home() / ".agent" / "skills" / "batch-report" / "report.py",
]

# =============================================================================
# Default Settings
# =============================================================================

# History settings
MAX_HISTORY_ENTRIES = 10000

# Session settings
MAX_SESSION_ENTRIES = 100

# Quality metrics settings
MAX_QUALITY_ENTRIES = 1000

# TUI settings
DEFAULT_REFRESH_INTERVAL = 2  # seconds
RATE_HISTORY_WINDOW = 600  # 10 minutes in seconds

# API settings
DEFAULT_API_PORT = 8765
API_HOST = "0.0.0.0"

# Hook polling interval
HOOK_POLL_INTERVAL = 5  # seconds
