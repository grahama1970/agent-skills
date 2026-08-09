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
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Annotated

import typer

from .herdr_target import HerdrPane, Resolution, list_panes, resolve, send

INTERVIEW_RUN = Path(__file__).resolve().parents[3] / "interview" / "run.sh"


def run_interview(resolution: Resolution) -> HerdrPane | None:
    """Ask the human which session, via /interview. None if unanswered.

    The project agent must not pick for the human when names collide, and it
    must not make the human go find the session list either -- the question
    carries the session, model, and directory for every candidate.
    """
    if not INTERVIEW_RUN.exists():
        return None
    with tempfile.TemporaryDirectory() as tmp:
        questions = Path(tmp) / "questions.json"
        answers = Path(tmp) / "answers.json"
        questions.write_text(
            json_lib.dumps(resolution.interview_payload(), indent=2), encoding="utf-8"
        )
        try:
            subprocess.run(
                [str(INTERVIEW_RUN), "--file", str(questions), "--output", str(answers)],
                check=False,
                timeout=600,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        try:
            chosen = json_lib.loads(answers.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    picked = ""
    if isinstance(chosen, dict):
        raw = chosen.get("herdr_session") or chosen.get("answers", {}).get("herdr_session")
        picked = str(raw[0] if isinstance(raw, list) and raw else raw or "")
    for pane in resolution.candidates:
        if pane.session_name == picked or pane.pane_id == picked:
            return pane
    return None

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
    no_interview: Annotated[bool, typer.Option("--no-interview", help="Fail on ambiguity instead of asking.")] = False,
) -> None:
    """Deliver MESSAGE to the Herdr session named NAME."""
    resolution = resolve(name, list_panes(), include_busy=busy)
    if resolution.needs_interview and not json_out and not no_interview:
        # Never guess -- but do not dead-end the human either. Ask which
        # session, showing name, model, and directory for each.
        picked = run_interview(resolution)
        if picked is not None:
            receipt = send(picked, message)
            typer.echo(
                f"delivered to {picked.describe()}"
                if receipt.get("submitted")
                else f"delivery failed: {receipt.get('error') or receipt.get('stderr')}"
            )
            raise typer.Exit(0 if receipt.get("submitted") else NOT_FOUND_EXIT)
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
