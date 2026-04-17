#!/usr/bin/env python3
"""
Scheduler CLI - Background task scheduler for Pi and Claude Code.

A lightweight background task scheduler using APScheduler.
Stores jobs in JSON, logs execution, supports cron and interval triggers.
Features rich TUI output with progress indicators.

This is a thin CLI entry point that delegates to modular components:
- config.py: Constants, paths, global state
- utils.py: Common utilities, optional dependency handling
- cron_parser.py: Cron and interval parsing
- job_registry.py: Job storage and management
- executor.py: Job execution logic
- metrics_server.py: FastAPI metrics endpoints
- daemon.py: Scheduler daemon class
- commands.py: CLI command handlers
"""
import sys
from typing import Optional

import typer

from config import DEFAULT_METRICS_PORT
from commands import (
    cmd_start,
    cmd_stop,
    cmd_status,
    cmd_register,
    cmd_unregister,
    cmd_list,
    cmd_run,
    cmd_enable,
    cmd_disable,
    cmd_logs,
    cmd_systemd_unit,
    cmd_load,
    cmd_report,
)

app = typer.Typer(help="Background task scheduler")


@app.command()
def start(
    port: int = typer.Option(DEFAULT_METRICS_PORT, help=f"Metrics server port (default: {DEFAULT_METRICS_PORT})"),
):
    """Start scheduler daemon."""
    cmd_start(port=port)


@app.command()
def stop():
    """Stop scheduler daemon."""
    cmd_stop()


@app.command()
def status(
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Show scheduler status."""
    cmd_status(as_json=as_json)


@app.command()
def register(
    name: str = typer.Option(..., help="Job name"),
    command: str = typer.Option(..., help="Command to run"),
    cron: Optional[str] = typer.Option(None, help="Cron expression"),
    interval: Optional[str] = typer.Option(None, help="Interval (e.g., 1h, 30m)"),
    workdir: Optional[str] = typer.Option(None, help="Working directory"),
    description: Optional[str] = typer.Option(None, help="Job description"),
    enabled: bool = typer.Option(True, help="Whether job is enabled"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Register a job."""
    cmd_register(
        name=name, command=command, cron=cron, interval=interval,
        workdir=workdir, description=description, enabled=enabled, as_json=as_json,
    )


@app.command()
def unregister(
    name: str = typer.Argument(..., help="Job name"),
):
    """Remove a job."""
    cmd_unregister(name=name)


@app.command("list")
def list_cmd(
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """List jobs."""
    cmd_list(as_json=as_json)


@app.command()
def run(
    name: str = typer.Argument(..., help="Job name"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Run a job now."""
    cmd_run(name=name, as_json=as_json)


@app.command()
def enable(
    name: str = typer.Argument(..., help="Job name"),
):
    """Enable a job."""
    cmd_enable(name=name)


@app.command()
def disable(
    name: str = typer.Argument(..., help="Job name"),
):
    """Disable a job."""
    cmd_disable(name=name)


@app.command()
def logs(
    name: Optional[str] = typer.Argument(None, help="Job name (or list all)"),
    lines: int = typer.Option(50, "-n", "--lines", help="Number of log lines"),
):
    """Show job logs."""
    cmd_logs(name=name, lines=lines)


@app.command("systemd-unit")
def systemd_unit():
    """Generate systemd unit file."""
    cmd_systemd_unit()


@app.command()
def load(
    file: str = typer.Argument(..., help="Path to services.yaml file"),
    include_disabled: bool = typer.Option(False, "--include-disabled", help="Also load disabled jobs"),
):
    """Load jobs from services.yaml."""
    cmd_load(file=file, include_disabled=include_disabled)


@app.command()
def report(
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Generate comprehensive status report."""
    cmd_report(as_json=as_json)


if __name__ == "__main__":
    app()
