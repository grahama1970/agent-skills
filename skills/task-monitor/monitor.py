#!/usr/bin/env python3
"""Task Monitor - Rich TUI + HTTP API for monitoring long-running tasks.

This is the thin entry point that delegates to the modular task_monitor package.

Provides both a nvtop-style terminal UI and an HTTP API for cross-agent monitoring.

Usage:
    # Start TUI (interactive)
    uv run python monitor.py tui

    # Start API server
    uv run python monitor.py serve --port 8765

    # Register a task
    uv run python monitor.py register --name "my-task" --state /path/to/state.json --total 1000

    # Quick status check
    uv run python monitor.py status

    # Where was I?
    uv run python monitor.py history resume
"""
from __future__ import annotations

from task_monitor.cli import app_cli

if __name__ == "__main__":
    app_cli()
