#!/usr/bin/env python3
"""Typer CLI entrypoint for agent-status."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from update_status import (  # noqa: E402
    VALID_STATES,
    cmd_artifact_add,
    cmd_blocked,
    cmd_event,
    cmd_gate_passed,
    cmd_init,
    cmd_needs_human,
    cmd_render,
    cmd_update,
    cmd_validate,
)

app = typer.Typer(
    help="Artifact-backed status for long-running project-agent campaigns.",
    no_args_is_help=True,
)


def _ns(**kwargs: object) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


@app.command("init")
def init_cmd(
    goal: Annotated[str, typer.Option("--goal", help="Campaign goal in plain language")],
    campaign: Annotated[str, typer.Option("--campaign")] = "agent-status",
    status_dir: Annotated[Optional[Path], typer.Option("--status-dir")] = None,
    state: Annotated[str, typer.Option("--state")] = "not_started",
    not_proven: Annotated[Optional[list[str]], typer.Option("--not-proven")] = None,
    do_not_do_next: Annotated[Optional[list[str]], typer.Option("--do-not-do-next")] = None,
) -> None:
    cmd_init(
        _ns(
            campaign=campaign,
            status_dir=str(status_dir) if status_dir else None,
            goal=goal,
            state=state,
            not_proven=not_proven,
            do_not_do_next=do_not_do_next,
        )
    )


@app.command("update")
def update_cmd(
    campaign: Annotated[str, typer.Option("--campaign")] = "agent-status",
    status_dir: Annotated[Optional[Path], typer.Option("--status-dir")] = None,
    state: Annotated[Optional[str], typer.Option("--state", case_sensitive=False)] = None,
    current_step: Annotated[Optional[str], typer.Option("--current-step")] = None,
    step_status: Annotated[Optional[str], typer.Option("--step-status")] = None,
    next_action: Annotated[Optional[str], typer.Option("--next-action")] = None,
    next_owner: Annotated[str, typer.Option("--next-owner")] = "agent",
    next_why: Annotated[Optional[str], typer.Option("--next-why")] = None,
    blocker: Annotated[Optional[list[str]], typer.Option("--blocker")] = None,
    not_proven: Annotated[Optional[list[str]], typer.Option("--not-proven")] = None,
    do_not_do_next: Annotated[Optional[list[str]], typer.Option("--do-not-do-next")] = None,
) -> None:
    if state is not None and state not in VALID_STATES:
        raise typer.BadParameter(f"state must be one of: {', '.join(sorted(VALID_STATES))}")
    cmd_update(
        _ns(
            campaign=campaign,
            status_dir=str(status_dir) if status_dir else None,
            state=state,
            current_step=current_step,
            step_status=step_status,
            next_action=next_action,
            next_owner=next_owner,
            next_why=next_why,
            blocker=blocker,
            not_proven=not_proven,
            do_not_do_next=do_not_do_next,
        )
    )


@app.command("gate-passed")
def gate_passed_cmd(
    label: Annotated[str, typer.Option("--label")],
    verdict: Annotated[str, typer.Option("--verdict")],
    proof: Annotated[str, typer.Option("--proof", help="Path to proof JSON or log")],
    campaign: Annotated[str, typer.Option("--campaign")] = "agent-status",
    status_dir: Annotated[Optional[Path], typer.Option("--status-dir")] = None,
    state: Annotated[str, typer.Option("--state")] = "passed_scoped_gate",
    next_action: Annotated[Optional[str], typer.Option("--next-action")] = None,
    next_owner: Annotated[str, typer.Option("--next-owner")] = "agent",
    next_why: Annotated[Optional[str], typer.Option("--next-why")] = None,
    not_proven: Annotated[Optional[list[str]], typer.Option("--not-proven")] = None,
    do_not_do_next: Annotated[Optional[list[str]], typer.Option("--do-not-do-next")] = None,
) -> None:
    cmd_gate_passed(
        _ns(
            campaign=campaign,
            status_dir=str(status_dir) if status_dir else None,
            label=label,
            verdict=verdict,
            proof=proof,
            state=state,
            next_action=next_action,
            next_owner=next_owner,
            next_why=next_why,
            not_proven=not_proven,
            do_not_do_next=do_not_do_next,
        )
    )


@app.command("needs-human")
def needs_human_cmd(
    question: Annotated[str, typer.Option("--question")],
    campaign: Annotated[str, typer.Option("--campaign")] = "agent-status",
    status_dir: Annotated[Optional[Path], typer.Option("--status-dir")] = None,
    why: Annotated[Optional[str], typer.Option("--why")] = None,
    option: Annotated[Optional[list[str]], typer.Option("--option")] = None,
) -> None:
    cmd_needs_human(
        _ns(
            campaign=campaign,
            status_dir=str(status_dir) if status_dir else None,
            question=question,
            why=why,
            option=option,
        )
    )


@app.command("blocked")
def blocked_cmd(
    reason: Annotated[str, typer.Option("--reason")],
    campaign: Annotated[str, typer.Option("--campaign")] = "agent-status",
    status_dir: Annotated[Optional[Path], typer.Option("--status-dir")] = None,
    blocker: Annotated[Optional[list[str]], typer.Option("--blocker")] = None,
    next_action: Annotated[Optional[str], typer.Option("--next-action")] = None,
    next_owner: Annotated[str, typer.Option("--next-owner")] = "agent",
) -> None:
    cmd_blocked(
        _ns(
            campaign=campaign,
            status_dir=str(status_dir) if status_dir else None,
            reason=reason,
            blocker=blocker,
            next_action=next_action,
            next_owner=next_owner,
        )
    )


@app.command("artifact-add")
def artifact_add_cmd(
    path: Annotated[str, typer.Option("--path", help="Relative or absolute artifact path")],
    kind: Annotated[str, typer.Option("--kind", help="mockup, image, table, report, log, proof, other")],
    label: Annotated[str, typer.Option("--label", help="Human-readable label")],
    campaign: Annotated[str, typer.Option("--campaign")] = "agent-status",
    status_dir: Annotated[Optional[Path], typer.Option("--status-dir")] = None,
    caption: Annotated[Optional[str], typer.Option("--caption")] = None,
) -> None:
    cmd_artifact_add(
        _ns(
            campaign=campaign,
            status_dir=str(status_dir) if status_dir else None,
            path=path,
            kind=kind,
            label=label,
            caption=caption,
        )
    )


@app.command("event")
def event_cmd(
    event: Annotated[str, typer.Option("--event")],
    message: Annotated[str, typer.Option("--message")],
    campaign: Annotated[str, typer.Option("--campaign")] = "agent-status",
    status_dir: Annotated[Optional[Path], typer.Option("--status-dir")] = None,
    data: Annotated[Optional[str], typer.Option("--data", help="JSON object string")] = None,
) -> None:
    cmd_event(
        _ns(
            campaign=campaign,
            status_dir=str(status_dir) if status_dir else None,
            event=event,
            message=message,
            data=data,
        )
    )


@app.command("render")
def render_cmd(
    campaign: Annotated[str, typer.Option("--campaign")] = "agent-status",
    status_dir: Annotated[Optional[Path], typer.Option("--status-dir")] = None,
) -> None:
    cmd_render(_ns(campaign=campaign, status_dir=str(status_dir) if status_dir else None))


@app.command("validate")
def validate_cmd(
    campaign: Annotated[str, typer.Option("--campaign")] = "agent-status",
    status_dir: Annotated[Optional[Path], typer.Option("--status-dir")] = None,
) -> None:
    cmd_validate(_ns(campaign=campaign, status_dir=str(status_dir) if status_dir else None))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
