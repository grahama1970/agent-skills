"""`ask targets` — readiness for every target kind (#1405).

Purpose
    One command family over ``ask.capability_report.v1``:

        ./run.sh targets list --readiness [--json] [--live]
        ./run.sh targets doctor browser:webgpt [--json] [--live]

    ``doctor <kind>:<selector>`` narrows the same report rather than running a
    different check, so a single target's verdict can never disagree with the
    matrix it came from.

Inputs
    An optional ``kind:selector`` filter and the ``--live`` opt-in.

Outputs
    Human lines, or the report JSON with ``--json``.

Failure modes
    An unknown selector exits 2 and lists what is addressable. A target whose
    probe failed is reported with its reason code; the command still exits 0
    because reporting a blocked target is a successful report.
"""

from __future__ import annotations

import json as json_lib
import sys
from typing import Annotated

import typer

from .capability_report import build_report, render_text

app = typer.Typer(help="Readiness for Ask targets.", no_args_is_help=True)

NOT_FOUND_EXIT = 2


@app.command("list")
def list_targets(
    readiness: Annotated[bool, typer.Option("--readiness", help="Include readiness state.")] = False,
    live: Annotated[bool, typer.Option("--live", help="Run probes that touch owning subsystems.")] = False,
    json_out: Annotated[bool, typer.Option("--json", help="Emit ask.capability_report.v1.")] = False,
) -> None:
    """List every target kind with its readiness."""
    report = build_report(live=live)
    if json_out:
        typer.echo(json_lib.dumps(report, indent=2, sort_keys=True))
        return
    if not readiness:
        for entry in report["capabilities"]:
            typer.echo(f"{entry['kind']:<14} {entry['capability_id']}")
        return
    for line in render_text(report):
        typer.echo(line)


@app.command("doctor")
def doctor_target(
    selector: Annotated[str, typer.Argument(help="kind:selector, e.g. browser:webgpt")] = "",
    live: Annotated[bool, typer.Option("--live", help="Run probes that touch owning subsystems.")] = False,
    json_out: Annotated[bool, typer.Option("--json", help="Emit the narrowed report.")] = False,
) -> None:
    """Readiness for one target, narrowed from the same report."""
    report = build_report(live=live)
    if not selector:
        if json_out:
            typer.echo(json_lib.dumps(report, indent=2, sort_keys=True))
            return
        for line in render_text(report):
            typer.echo(line)
        return

    wanted = selector.strip().lower()
    matches = [
        entry
        for entry in report["capabilities"]
        if entry["capability_id"].lower() == wanted
        or entry["capability_id"].lower().replace(".", ":") == wanted
        or entry["selector"].lower() == wanted.split(":")[-1]
    ]
    if not matches:
        addressable = ", ".join(e["capability_id"] for e in report["capabilities"])
        typer.echo(f"no target matches {selector!r}; addressable: {addressable}", err=True)
        raise typer.Exit(NOT_FOUND_EXIT)

    narrowed = {**report, "capabilities": matches}
    if json_out:
        typer.echo(json_lib.dumps(narrowed, indent=2, sort_keys=True))
        return
    for line in render_text(narrowed):
        typer.echo(line)


def main() -> None:
    app()


if __name__ == "__main__":
    sys.exit(app())
