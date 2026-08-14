"""`ask runs` — portable run inspection and control (#1402).

Purpose
    One command family over Tau identities:

        ./run.sh runs list|latest|show|watch|steer|cancel|resume

    Every read command supports ``--json``; ``watch`` also supports ``--jsonl``
    for SSH, pipes, cron and CI. ``show`` and ``watch`` render
    ``ask.run_projection.v1`` rather than reconstructing state.

Inputs
    A run id or run directory, plus per-command options.

Outputs
    Human lines, ``--json`` payloads, or newline-delimited events.

Failure modes
    Unknown run exits 2. An unsupported control operation exits 0 with an
    ``unsupported`` receipt: reporting truthfully that Ask cannot steer is a
    successful report, not a command failure.
"""

from __future__ import annotations

import json as json_lib
import sys
from pathlib import Path
from typing import Annotated

import typer

from .run_projection import project_run, render_text
from .runs_control import (
    cancel as cancel_run,
    list_runs,
    resolve_run,
    resume as resume_run,
    resume_plan,
    steer as steer_node,
    watch_events,
)

app = typer.Typer(help="Inspect and control Ask runs.", no_args_is_help=True)

NOT_FOUND_EXIT = 2


def _resolve_or_exit(run: str) -> Path:
    path = resolve_run(run)
    if path is None:
        typer.echo(f"no run found for {run!r}", err=True)
        raise typer.Exit(NOT_FOUND_EXIT)
    return path


@app.command("list")
def list_command(
    limit: Annotated[int, typer.Option("--limit", help="Maximum runs to list.")] = 20,
    json_out: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = False,
) -> None:
    """Recent runs, newest first."""
    rows = list_runs(limit=limit)
    if json_out:
        typer.echo(json_lib.dumps({"runs": rows}, indent=2, sort_keys=True))
        return
    for row in rows:
        typer.echo(
            f"{row['run_id'][:52]:<54}{row['lifecycle']:<16}"
            f"{row['unsettled']}/{row['nodes']} unsettled  {row['age_seconds']}s"
        )
    if not rows:
        typer.echo("(no runs)", err=True)


@app.command("latest")
def latest_command(
    json_out: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = False,
) -> None:
    """The most recent run."""
    rows = list_runs(limit=1)
    if not rows:
        typer.echo("(no runs)", err=True)
        raise typer.Exit(NOT_FOUND_EXIT)
    if json_out:
        typer.echo(json_lib.dumps(rows[0], indent=2, sort_keys=True))
        return
    for line in render_text(project_run(rows[0]["run_dir"])):
        typer.echo(line)


@app.command("show")
def show_command(
    run: Annotated[str, typer.Argument(help="Run id or directory.")],
    json_out: Annotated[bool, typer.Option("--json", help="Emit ask.run_projection.v1.")] = False,
) -> None:
    """Render the run projection."""
    projection = project_run(_resolve_or_exit(run))
    if json_out:
        typer.echo(json_lib.dumps(projection, indent=2, sort_keys=True))
        return
    for line in render_text(projection):
        typer.echo(line)


@app.command("watch")
def watch_command(
    run: Annotated[str, typer.Argument(help="Run id or directory.")],
    jsonl: Annotated[bool, typer.Option("--jsonl", help="Newline-delimited events.")] = False,
    poll_seconds: Annotated[float, typer.Option("--poll-seconds")] = 2.0,
    max_polls: Annotated[int, typer.Option("--max-polls", help="0 follows until settled.")] = 0,
) -> None:
    """Follow a run until it settles.

    Detaching (Ctrl-C) stops observation only. Watch performs no writes, so
    abandoning it cannot cancel or alter the run.
    """
    path = _resolve_or_exit(run)
    try:
        for event in watch_events(path, poll_seconds=poll_seconds, max_polls=max_polls):
            if jsonl:
                typer.echo(json_lib.dumps(event, sort_keys=True))
            else:
                typer.echo(
                    f"{event['event']:<22}{event.get('node_id') or '':<24}"
                    f"{event.get('from') or ''}->{event.get('to') or event.get('lifecycle') or ''}"
                )
            sys.stdout.flush()
    except KeyboardInterrupt:
        # Explicit: detach, and say so. Silence here is what would let an
        # operator believe Ctrl-C stopped the run.
        typer.echo("detached from watch; the run is still active", err=True)
        raise typer.Exit(0)


@app.command("steer")
def steer_command(
    run: Annotated[str, typer.Argument(help="Run id or directory.")],
    node: Annotated[str, typer.Option("--node", help="Node id to steer.")],
    message: Annotated[str, typer.Option("--message", help="Bounded guidance.")],
    json_out: Annotated[bool, typer.Option("--json", help="Emit the receipt.")] = False,
) -> None:
    """Send bounded guidance to one node, or report why it cannot be sent."""
    receipt = steer_node(_resolve_or_exit(run), node, message)
    if json_out:
        typer.echo(json_lib.dumps(receipt, indent=2, sort_keys=True))
        return
    typer.echo(f"steer {receipt['outcome']}: {receipt['reason_code']}")
    typer.echo(f"  {receipt['explanation']}")
    if receipt.get("violations"):
        typer.echo(f"  violations: {', '.join(receipt['violations'])}")


@app.command("cancel")
def cancel_command(
    run: Annotated[str, typer.Argument(help="Run id or directory.")],
    node: Annotated[str, typer.Option("--node", help="Optional node id.")] = "",
    json_out: Annotated[bool, typer.Option("--json", help="Emit the receipt.")] = False,
) -> None:
    """Record a cancellation request. This is not an acknowledgement."""
    receipt = cancel_run(_resolve_or_exit(run), node)
    if json_out:
        typer.echo(json_lib.dumps(receipt, indent=2, sort_keys=True))
        return
    typer.echo(f"cancel {receipt['outcome']} (acknowledged={receipt['acknowledged']})")
    typer.echo(f"  {receipt['explanation']}")


@app.command("resume")
def resume_command(
    run: Annotated[str, typer.Argument(help="Run id or directory.")],
    execute: Annotated[bool, typer.Option("--execute", help="Actually resume through Tau.")] = False,
    json_out: Annotated[bool, typer.Option("--json", help="Emit the receipt.")] = False,
) -> None:
    """Resume, skipping work whose evidence was already admitted."""
    path = _resolve_or_exit(run)
    receipt = resume_run(path, execute=execute) if execute else {
        **resume_plan(path), "outcome": "planned"
    }
    if json_out:
        typer.echo(json_lib.dumps(receipt, indent=2, sort_keys=True))
        return
    plan = receipt.get("plan") or receipt
    typer.echo(f"resume {receipt.get('outcome')}")
    typer.echo(f"  already accepted (never rerun): {', '.join(plan.get('already_accepted') or []) or '-'}")
    typer.echo(f"  would rerun: {', '.join(plan.get('would_rerun') or []) or '-'}")


def main() -> None:
    app()


if __name__ == "__main__":
    sys.exit(app())
