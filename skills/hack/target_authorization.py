"""Hack CLI helpers for target authorization manifest preflights."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import typer
from rich.console import Console

from common.security_authorization import validate_target_authorization

console = Console()


def create_authorization_preflight_command() -> Callable[..., None]:
    """Create the Hack authorization-preflight command."""

    def authorization_preflight(
        authorization_manifest: Path = typer.Option(..., "--authorization-manifest", help="security.target_authorization.v1 manifest."),
        target: str = typer.Option(..., "--target", help="Expected target identity, formatted canonical_id@immutable_ref."),
        action: str = typer.Option(..., "--action", help="Requested action class, such as session-audit."),
        receipt_out: Path | None = typer.Option(None, "--receipt-out", help="Persist security.target_authorization_validation_receipt.v1 JSON."),
        port: int | None = typer.Option(None, "--port", help="Requested target TCP port."),
        target_url: str | None = typer.Option(None, "--target-url", help="Requested target URL."),
        probe_class: str | None = typer.Option(None, "--probe-class", help="Requested scan/probe class."),
        runtime_mode: str | None = typer.Option(None, "--runtime-mode", help="Requested runtime mode."),
        expected_manifest_sha256: str | None = typer.Option(None, "--expected-manifest-sha256", help="Expected manifest file SHA-256."),
        json_output: bool = typer.Option(False, "--json", help="Print the full validation receipt."),
    ) -> None:
        receipt = validate_target_authorization(
            authorization_manifest,
            expected_target=target,
            requested_action=action,
            requested_port=port,
            requested_target_url=target_url,
            requested_probe_class=probe_class,
            requested_runtime_mode=runtime_mode,
            expected_manifest_sha256=expected_manifest_sha256,
            receipt_out=receipt_out,
        )
        if json_output:
            console.print(json.dumps(receipt, indent=2, sort_keys=True))
        elif receipt["status"] == "PASS":
            console.print("[green]Authorization preflight passed[/green]")
        else:
            console.print("[red]Authorization preflight failed[/red]")
            for error in receipt["errors"]:
                console.print(f"- {error}")
        if receipt["status"] != "PASS":
            raise typer.Exit(2)

    return authorization_preflight


__all__ = ["create_authorization_preflight_command"]
