"""`ask herdr` — talk to another agent's Herdr session by name.

Purpose
    Cross-session messaging has to be one short command or nobody uses it.
    The whole surface is three verbs:

        ./run.sh herdr list [NAME]
        ./run.sh herdr send NAME "message"
        ./run.sh herdr who NAME

    NAME is whatever the human already knows: a project directory
    (``memory``), a GitHub repo (``graph-memory-operator``), or an exact pane
    id (``w11:p13``). The resolver reconciles the first two, which disagree on
    this machine.

Inputs
    A name plus, for ``send``, the message text.

Outputs
    Human-readable lines by default, ``--json`` for machine callers. Exit 0 on
    delivery, 2 when the name is ambiguous, 1 when nothing addressable matched.

Failure modes
    Ambiguity is the expected case, not an error path: ``memory`` currently
    matches six panes. ``send`` refuses rather than guessing, and prints the
    candidates plus the exact disambiguating command, so the fix is a copy and
    paste rather than a research task.
"""

from __future__ import annotations

import json as json_lib
import sys
from typing import Annotated

import typer

from .herdr_target import list_panes, resolve, send

app = typer.Typer(help="Send work to another agent's Herdr session by name.", no_args_is_help=True)

AMBIGUOUS_EXIT = 2
NOT_FOUND_EXIT = 1


def _print_candidates(resolution) -> None:
    typer.echo(f"'{resolution.query}' matches {len(resolution.candidates)} live panes:", err=True)
    for pane in resolution.candidates:
        typer.echo(f"  {pane.describe()}", err=True)
    typer.echo("", err=True)
    typer.echo("Pick one by pane id:", err=True)
    typer.echo(f"  ./run.sh herdr send {resolution.candidates[0].pane_id} \"<message>\"", err=True)


@app.command("list")
def list_command(
    name: Annotated[str, typer.Argument(help="Optional project/repo filter.")] = "",
    json_out: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = False,
    all_panes: Annotated[bool, typer.Option("--all", help="Include panes that cannot be typed into.")] = False,
) -> None:
    """List addressable Herdr sessions, optionally filtered by name."""
    panes = list_panes()
    if name:
        resolution = resolve(name, panes)
        shown = list(resolution.candidates)
        if not shown and not all_panes:
            typer.echo(resolution.reason or "no match", err=True)
            raise typer.Exit(NOT_FOUND_EXIT)
    else:
        shown = [p for p in panes if all_panes or p.is_addressable]
    if json_out:
        typer.echo(json_lib.dumps([p.__dict__ for p in shown], indent=2, sort_keys=True))
        return
    for pane in shown:
        typer.echo(pane.describe())
    if not shown:
        typer.echo("(no addressable panes)", err=True)


@app.command("who")
def who_command(
    name: Annotated[str, typer.Argument(help="Project, repo, or pane id.")],
    json_out: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = False,
) -> None:
    """Show what NAME resolves to, without sending anything."""
    resolution = resolve(name, list_panes())
    if json_out:
        typer.echo(
            json_lib.dumps(
                {
                    "query": resolution.query,
                    "needs_interview": resolution.needs_interview,
                    "reason": resolution.reason,
                    "candidates": resolution.interview_options(),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return
    if resolution.resolved:
        typer.echo(resolution.resolved.describe())
        return
    if resolution.needs_interview:
        _print_candidates(resolution)
        raise typer.Exit(AMBIGUOUS_EXIT)
    typer.echo(resolution.reason or "no match", err=True)
    raise typer.Exit(NOT_FOUND_EXIT)


@app.command("send")
def send_command(
    name: Annotated[str, typer.Argument(help="Project, repo, or pane id.")],
    message: Annotated[str, typer.Argument(help="Message to deliver.")],
    json_out: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = False,
    busy: Annotated[bool, typer.Option("--busy", help="Allow panes mid-task.")] = False,
) -> None:
    """Deliver MESSAGE to the Herdr session named NAME."""
    resolution = resolve(name, list_panes(), include_busy=busy)
    if resolution.needs_interview:
        # Never guess. Picking wrong sends another agent's work to a stranger.
        if json_out:
            typer.echo(
                json_lib.dumps(
                    {
                        "submitted": False,
                        "needs_interview": True,
                        "query": resolution.query,
                        "candidates": resolution.interview_options(),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            _print_candidates(resolution)
        raise typer.Exit(AMBIGUOUS_EXIT)

    pane = resolution.resolved
    if pane is None:
        message_text = resolution.reason or "no match"
        if json_out:
            typer.echo(json_lib.dumps({"submitted": False, "reason": message_text}, indent=2))
        else:
            typer.echo(message_text, err=True)
        raise typer.Exit(NOT_FOUND_EXIT)

    receipt = send(pane, message)
    if json_out:
        typer.echo(json_lib.dumps(receipt, indent=2, sort_keys=True))
    elif receipt.get("submitted"):
        typer.echo(f"delivered to {pane.describe()}")
    else:
        typer.echo(f"delivery failed: {receipt.get('error') or receipt.get('stderr')}", err=True)
    if not receipt.get("submitted"):
        raise typer.Exit(NOT_FOUND_EXIT)


def main() -> None:
    app()


if __name__ == "__main__":
    sys.exit(app())
