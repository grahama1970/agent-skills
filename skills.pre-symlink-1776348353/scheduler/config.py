"""
Scheduler configuration - constants, paths, and global state.

This module centralizes all configuration values and paths for the scheduler.
"""
import os
from pathlib import Path
from typing import TypedDict
from threading import Lock

# ============================================================================
# Paths
# ============================================================================

DATA_DIR = Path(os.getenv("SCHEDULER_DATA_DIR", Path.home() / ".pi" / "scheduler"))
JOBS_FILE = DATA_DIR / "jobs.json"
PID_FILE = Path(os.getenv("SCHEDULER_PID_FILE", DATA_DIR / "scheduler.pid"))
PORT_FILE = DATA_DIR / ".port"
LOG_DIR = DATA_DIR / "logs"

# ============================================================================
# Server Configuration
# ============================================================================

DEFAULT_METRICS_PORT = int(os.getenv("SCHEDULER_METRICS_PORT", "8610"))

# ============================================================================
# Global Runtime State
# ============================================================================

# Typed state structures

class RunningJob(TypedDict, total=False):
    started: float
    progress: str
    command: str

RunningJobs = dict[str, RunningJob]

class MetricsCounters(TypedDict):
    jobs_total: int
    jobs_success: int
    jobs_failed: int
    jobs_timeout: int

# Running jobs state (for progress tracking)
# Format: {job_name: {"started": timestamp, "progress": str, "command": str}}
RUNNING_JOBS: RunningJobs = {}
RUNNING_JOBS_LOCK = Lock()

# Metrics counters for prometheus-style metrics
METRICS_COUNTERS: MetricsCounters = {
    "jobs_total": 0,
    "jobs_success": 0,
    "jobs_failed": 0,
    "jobs_timeout": 0,
}
METRICS_LOCK = Lock()

# Daemon start time (set when daemon starts)
_start_time: float = 0.0


def set_start_time(t: float) -> None:
    """Set the daemon start time."""
    global _start_time
    _start_time = t


def get_start_time() -> float:
    """Get the daemon start time."""
    return _start_time
