"""CLI entrypoint for the zero-network Stage 0 kernel."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import NoReturn

import typer
from loguru import logger

from . import __version__
from .contracts import CONTRACT_VERSION, IMMUTABLE_GOAL, STAGE, ContractError
from .report import load_manifest, render_report
from .verification import run_verification

app = typer.Typer(
    name="monitor-opportunities",
    help="Zero-network Stage 0 status, report, and verification kernel.",
    no_args_is_help=True,
)

IMPLEMENTED = ["status", "report", "verify"]
NOT_IMPLEMENTED = [
    "run",
    "resume",
    "sweep",
    "rank",
    "tailor",
    "serve",
    "decision",
    "replay",
    "apply",
    "schedule",
]


def _configure_logging() -> None:
    logger.remove()
    logger.add(sys.stderr, level="INFO", colorize=False)


def _fail(exc: ContractError) -> NoReturn:
    typer.echo(json.dumps({"status": "ERROR", **exc.as_dict()}, sort_keys=True), err=True)
    raise typer.Exit(code=2)


def status_payload() -> dict[str, object]:
    return {
        "schema": "monitor_opportunities.status.v1",
        "runtime_version": __version__,
        "contract_version": CONTRACT_VERSION,
        "immutable_goal": IMMUTABLE_GOAL,
        "stage": STAGE,
        "operational_readiness": "NOT_ESTABLISHED",
        "network_access": False,
        "external_effects": False,
        "implemented_commands": IMPLEMENTED,
        "not_implemented_commands": NOT_IMPLEMENTED,
        "capabilities": {
            "local_report": "IMPLEMENTED",
            "verification_receipt": "IMPLEMENTED",
            "live_discovery": "NOT_IMPLEMENTED",
            "eligibility_and_ranking": "NOT_IMPLEMENTED",
            "claim_bound_tailoring": "NOT_IMPLEMENTED",
            "decision_ledger": "NOT_IMPLEMENTED",
            "scheduler_registration": "NOT_IMPLEMENTED",
            "gmail_mailbox_draft": "BLOCKED_STAGE_0",
            "gmail_send": "PERMANENTLY_FORBIDDEN",
            "linkedin_handoff": "BLOCKED_STAGE_0",
            "linkedin_automation": "PERMANENTLY_FORBIDDEN",
            "ats_inspect": "BLOCKED_STAGE_0",
            "ats_prefill": "BLOCKED_STAGE_0",
            "ats_submit": "BLOCKED_STAGE_0",
        },
        "non_claims": [
            "The nightly opportunity pipeline is not implemented or reliable.",
            "Fixture rendering does not prove live sources, ranking, tailoring, scheduling, or effects.",
        ],
    }


@app.command()
def status(
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Report exact Stage 0 implementation and authority state."""
    _configure_logging()
    payload = status_payload()
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    typer.echo(f"monitor-opportunities {payload['runtime_version']}")
    typer.echo(f"stage: {payload['stage']}")
    typer.echo(f"operational readiness: {payload['operational_readiness']}")
    typer.echo("implemented: " + ", ".join(IMPLEMENTED))
    typer.echo("external effects: blocked")


@app.command()
def report(
    input_path: Path = typer.Option(..., "--input", exists=True, dir_okay=False, readable=True),
    out: Path = typer.Option(..., "--out", file_okay=False),
) -> None:
    """Validate and render one self-contained Stage 0 report."""
    _configure_logging()
    try:
        manifest = load_manifest(input_path)
        artifacts = render_report(manifest, out)
    except ContractError as exc:
        _fail(exc)
    typer.echo(json.dumps({"status": "PASS", **artifacts}, indent=2, sort_keys=True))


@app.command()
def verify(
    out: Path = typer.Option(..., "--out", file_okay=False),
    fixture: Path | None = typer.Option(
        None,
        "--fixture",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Optional contract fixture; built-in fixture is used when omitted.",
    ),
) -> None:
    """Run positive and adversarial local verification and write a receipt."""
    _configure_logging()
    try:
        receipt = run_verification(out, fixture)
    except ContractError as exc:
        _fail(exc)
    typer.echo(json.dumps(receipt, indent=2, sort_keys=True))
    if receipt["overall"] != "PASS":
        raise typer.Exit(code=1)


def _not_implemented(command: str) -> None:
    typer.echo(
        json.dumps(
            {
                "status": "NOT_IMPLEMENTED",
                "command": command,
                "stage": STAGE,
                "external_effects": False,
            },
            sort_keys=True,
        ),
        err=True,
    )
    raise typer.Exit(code=3)


def _register_not_implemented(command_name: str) -> None:
    def command(ctx: typer.Context) -> None:
        del ctx
        _not_implemented(command_name)

    command.__name__ = command_name.replace("-", "_")
    app.command(
        name=command_name,
        help="Not implemented; fails closed.",
        context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    )(command)


for _command_name in NOT_IMPLEMENTED:
    _register_not_implemented(_command_name)


if __name__ == "__main__":  # pragma: no cover
    app()
