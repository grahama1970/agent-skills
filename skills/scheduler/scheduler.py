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
import argparse
import sys

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


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Background task scheduler")
    parser.add_argument("--json", action="store_true", help="JSON output")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # start
    p = subparsers.add_parser("start", help="Start scheduler daemon")
    p.add_argument(
        "--port",
        type=int,
        default=DEFAULT_METRICS_PORT,
        help=f"Metrics server port (default: {DEFAULT_METRICS_PORT})"
    )

    # stop
    subparsers.add_parser("stop", help="Stop scheduler daemon")

    # status
    p = subparsers.add_parser("status", help="Show scheduler status")
    p.add_argument("--json", action="store_true")

    # register
    p = subparsers.add_parser("register", help="Register a job")
    p.add_argument("--name", required=True, help="Job name")
    p.add_argument("--command", required=True, help="Command to run")
    p.add_argument("--cron", help="Cron expression")
    p.add_argument("--interval", help="Interval (e.g., 1h, 30m)")
    p.add_argument("--workdir", help="Working directory")
    p.add_argument("--description", help="Job description")
    p.add_argument("--enabled", type=bool, default=True)
    p.add_argument("--json", action="store_true")

    # unregister
    p = subparsers.add_parser("unregister", help="Remove a job")
    p.add_argument("name", help="Job name")

    # list
    p = subparsers.add_parser("list", help="List jobs")
    p.add_argument("--json", action="store_true")

    # run
    p = subparsers.add_parser("run", help="Run a job now")
    p.add_argument("name", help="Job name")
    p.add_argument("--json", action="store_true")

    # enable/disable
    p = subparsers.add_parser("enable", help="Enable a job")
    p.add_argument("name", help="Job name")

    p = subparsers.add_parser("disable", help="Disable a job")
    p.add_argument("name", help="Job name")

    # logs
    p = subparsers.add_parser("logs", help="Show job logs")
    p.add_argument("name", nargs="?", help="Job name (or list all)")
    p.add_argument("--lines", "-n", type=int, default=50)

    # systemd-unit
    subparsers.add_parser("systemd-unit", help="Generate systemd unit file")

    # load (from YAML)
    p = subparsers.add_parser("load", help="Load jobs from services.yaml")
    p.add_argument("file", help="Path to services.yaml file")
    p.add_argument("--include-disabled", action="store_true", help="Also load disabled jobs")

    # report
    p = subparsers.add_parser("report", help="Generate comprehensive status report")
    p.add_argument("--json", action="store_true", help="JSON output")

    args = parser.parse_args()

    cmd_map = {
        "start": cmd_start,
        "stop": cmd_stop,
        "status": cmd_status,
        "register": cmd_register,
        "unregister": cmd_unregister,
        "list": cmd_list,
        "run": cmd_run,
        "enable": cmd_enable,
        "disable": cmd_disable,
        "logs": cmd_logs,
        "systemd-unit": cmd_systemd_unit,
        "load": cmd_load,
        "report": cmd_report,
    }

    cmd_map[args.subcommand](args)


if __name__ == "__main__":
    main()
