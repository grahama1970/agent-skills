"""
Scheduler utilities - common functions and optional dependency handling.

Handles rich console output, directory management, and daemon state queries.
"""
import os
from typing import Optional, Any, TYPE_CHECKING

from config import DATA_DIR, LOG_DIR, PID_FILE
if TYPE_CHECKING:
    from rich.console import Console as RichConsole


# ============================================================================
# Optional Dependencies
# ============================================================================

# Rich for TUI output
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
    from rich.live import Live
    from rich.text import Text
    from rich.style import Style
    HAS_RICH = True
    console: Optional["RichConsole"] = Console()
except ImportError:
    HAS_RICH = False
    console = None  # type: ignore[assignment]

# APScheduler for cron-like scheduling
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    HAS_APSCHEDULER = True
except ImportError:
    HAS_APSCHEDULER = False
    BackgroundScheduler = None  # type: ignore[assignment,misc]
    CronTrigger = None  # type: ignore[assignment,misc]
    IntervalTrigger = None  # type: ignore[assignment,misc]

# FastAPI for metrics server
try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import PlainTextResponse
    import uvicorn
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    FastAPI = None  # type: ignore[assignment,misc]
    HTTPException = None  # type: ignore[assignment,misc]
    PlainTextResponse = None  # type: ignore[assignment,misc]
    uvicorn = None  # type: ignore[assignment]

# YAML for service configuration
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False
    yaml = None  # type: ignore[assignment]


# ============================================================================
# Console Output
# ============================================================================

def rprint(*args: Any, **kwargs: Any) -> None:
    """Print with rich if available, else plain print."""
    if HAS_RICH and console:
        console.print(*args, **kwargs)
    else:
        print(*args, **kwargs)


# ============================================================================
# Directory Management
# ============================================================================

def ensure_dirs() -> None:
    """Ensure data directories exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================================
# Daemon State Queries
# ============================================================================

def is_daemon_running() -> bool:
    """Check if daemon is running."""
    if not PID_FILE.exists():
        return False
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def get_daemon_pid() -> Optional[int]:
    """Get daemon PID if running."""
    if not PID_FILE.exists():
        return None
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        return None
