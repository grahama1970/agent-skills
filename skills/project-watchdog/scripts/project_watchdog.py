#!/usr/bin/env python3
"""Project Watchdog CLI: one bounded cross-project GitHub issue tick per invocation.

Purpose
    Thin Typer entrypoint. Every command validates its arguments and delegates
    immediately to ``watchdog.commands``; no business logic lives here.

Inputs
    Command-line arguments. See ``./run.sh --help`` for the full surface.

Outputs
    A JSON receipt on stdout for every command, and a process exit code:
    ``0`` success or a deliberate refusal, ``1`` operational failure,
    ``2`` caller error such as an unknown project id or invalid state name.

Failure modes
    Unhandled exceptions are logged with a traceback to the durable event log
    and re-raised, so cron captures a real stack trace rather than a bare
    non-zero exit.

Usage
    ./run.sh tick --project all                 # dry-run fleet scan
    ./run.sh tick --apply --project all         # one bounded fleet dispatch
    ./run.sh tick --project tau                 # strict scan for tau only
    ./run.sh status
    ./run.sh set-state global paused --reason "maintenance"
    ./run.sh install-cron --apply
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent))

from watchdog import commands  # noqa: E402
from watchdog.core import (  # noqa: E402
    configure_logging,
    ensure_dirs,
    log_event,
    timestamp,
)

VALID_SCOPES = ("global", "project")
VALID_STATES = ("active", "paused", "stopped")

app = typer.Typer(add_completion=False, help="Run one bounded project watchdog tick.")


def _startup(verbose: bool = False) -> None:
    ensure_dirs()
    configure_logging(verbose=verbose)


@app.command("tick")
def tick_command(
    apply: bool = typer.Option(False, "--apply", help="Apply mutations instead of dry-run scan."),
    project: str = typer.Option(
        "all",
        "--project",
        help="Registered project id, or 'all' for explicit fleet rotation.",
    ),
    max_tickets: int = typer.Option(1, "--max-tickets", min=1, help="Maximum issues to handle."),
    verbose: bool = typer.Option(False, "--verbose", help="Log at DEBUG level to stderr."),
) -> None:
    """Scan and handle at most one bounded project ticket."""
    _startup(verbose)
    raise typer.Exit(commands.tick(apply=apply, project_id=project, max_tickets=max_tickets))


@app.command("install-cron")
def install_cron_command(
    apply: bool = typer.Option(False, "--apply", help="Install the crontab entry."),
    minute: str = typer.Option("*", "--minute", help="Cron minute field."),
) -> None:
    """Install or dry-run the project-watchdog cron line."""
    _startup()
    raise typer.Exit(commands.install_cron(apply=apply, minute=minute))


@app.command("set-state")
def set_state_command(
    scope: str = typer.Argument(..., help="global or project"),
    state: str = typer.Argument(..., help="active, paused, or stopped"),
    project: str = typer.Option("tau", "--project", help="Project id when scope=project."),
    reason: str = typer.Option("operator request", "--reason", help="State transition reason."),
) -> None:
    """Set global or per-project watchdog state."""
    if scope not in VALID_SCOPES:
        typer.echo(
            f"scope must be one of {', '.join(VALID_SCOPES)}; got {scope!r}. "
            f"Usage: set-state <{'|'.join(VALID_SCOPES)}> <{'|'.join(VALID_STATES)}>",
            err=True,
        )
        raise typer.Exit(2)
    if state not in VALID_STATES:
        typer.echo(
            f"state must be one of {', '.join(VALID_STATES)}; got {state!r}. "
            "'paused' allows observation but refuses dispatch; "
            "'stopped' ignores the project until a human resumes it.",
            err=True,
        )
        raise typer.Exit(2)
    _startup()
    raise typer.Exit(commands.set_state(scope, state, project_id=project, reason=reason))


@app.command("status")
def status_command() -> None:
    """Print watchdog registry, state, log, lock, and cron status."""
    _startup()
    print(commands.status_json())


def main() -> None:
    try:
        app()
    except Exception as exc:
        ensure_dirs()
        configure_logging()
        run_id = f"project-watchdog-error-{timestamp()}"
        logger.opt(exception=True).error("fatal watchdog error: {}", exc)
        log_event(run_id, "fatal_error", error=str(exc))
        print(f"project-watchdog error: {exc}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
