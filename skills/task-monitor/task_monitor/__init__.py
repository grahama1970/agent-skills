"""Task Monitor - Rich TUI + HTTP API for monitoring long-running tasks.

This package provides both a nvtop-style terminal UI and an HTTP API
for cross-agent monitoring of long-running tasks.

Modules:
    config - Constants and paths
    models - Pydantic data models
    stores - Data persistence (TaskRegistry, HistoryStore, etc.)
    utils - Common utility functions
    tui - Rich terminal UI components
    http_api - FastAPI HTTP server
    cli - Command-line interface
"""
from task_monitor.config import (
    DEFAULT_API_PORT,
    DEFAULT_REFRESH_INTERVAL,
    REGISTRY_DIR,
    REGISTRY_FILE,
)
from task_monitor.models import (
    HistoryEntry,
    QualityMetrics,
    SessionRecord,
    TaskConfig,
)
from task_monitor.stores import (
    HistoryStore,
    QualityStore,
    SessionTracker,
    TaskRegistry,
)
from task_monitor.utils import (
    get_task_status,
    read_task_state,
)

__all__ = [
    # Config
    "DEFAULT_API_PORT",
    "DEFAULT_REFRESH_INTERVAL",
    "REGISTRY_DIR",
    "REGISTRY_FILE",
    # Models
    "HistoryEntry",
    "QualityMetrics",
    "SessionRecord",
    "TaskConfig",
    # Stores
    "HistoryStore",
    "QualityStore",
    "SessionTracker",
    "TaskRegistry",
    # Utils
    "get_task_status",
    "read_task_state",
]

__version__ = "2.0.0"
