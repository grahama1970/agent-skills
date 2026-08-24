"""Typer CLI for bounded LinkedIn operations and manual handoff receipts.

Most commands read and write local JSON only. The profile-sync planning path can
emit a Surf transport plan for Graham's own profile, but this CLI still does not
open LinkedIn, read browser state, perform HTTP requests, or submit social actions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer
from loguru import logger
from pydantic import ValidationError

from ops_linkedin.models import HandoffPacket, HandoffRequest, Readiness
from ops_linkedin.profile_sync import (
    DEFAULT_SURF_RUN,
    LinkedInProfileEntry,
    build_profile_entry,
    build_profile_sync_packet,
    build_profile_sync_packet_from_entry,
)
from ops_linkedin.service import (
    attest_human_completion,
    policy_report,
    prepare_handoff,
    status_report,
)

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Prepare local LinkedIn drafts and manual-execution handoff packets.",
)


def _read_json(path: Path) -> dict[str, Any]:
    """Read one UTF-8 JSON object from disk with boundary validation errors."""

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise typer.BadParameter(f"cannot read {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise typer.BadParameter(f"{path} must contain one JSON object")
    return data


def _write_json(payload: Any, output: Path | None) -> None:
    """Serialize a model or plain object to stdout or a caller-selected path."""

    if hasattr(payload, "model_dump"):
        data = payload.model_dump(mode="json", exclude_none=True)
    else:
        data = payload
    rendered = json.dumps(data, indent=2, sort_keys=True) + "\n"
    if output is None:
        typer.echo(rendered, nl=False)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    logger.info("wrote {}", output)
    typer.echo(str(output))


@app.command("policy")
def policy_command(
    output: Path | None = typer.Option(None, "--output", "-o", help="Optional JSON path."),
) -> None:
    """Print the dated no-automation policy used by this implementation."""

    _write_json(policy_report(), output)


@app.command("status")
def status_command(
    output: Path | None = typer.Option(None, "--output", "-o", help="Optional JSON path."),
) -> None:
    """Print feature readiness and explicit non-claims."""

    _write_json(status_report(), output)


@app.command("prepare")
def prepare_command(
    manifest: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    output: Path | None = typer.Option(None, "--output", "-o", help="Optional packet path."),
    allow_blocked: bool = typer.Option(
        False,
        "--allow-blocked",
        help="Return zero for a blocked packet; the packet remains non-executable.",
    ),
) -> None:
    """Validate a request manifest and emit a PREPARED local handoff packet."""

    try:
        request = HandoffRequest.model_validate(_read_json(manifest))
        packet = prepare_handoff(request)
    except ValidationError as exc:
        typer.echo(exc.json(indent=2), err=True)
        raise typer.Exit(code=2) from exc

    _write_json(packet, output)
    if packet.readiness is not Readiness.READY_FOR_HUMAN_REVIEW and not allow_blocked:
        raise typer.Exit(code=3)


@app.command("validate")
def validate_command(
    packet_path: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
) -> None:
    """Validate an existing handoff packet against the current schema."""

    try:
        packet = HandoffPacket.model_validate(_read_json(packet_path))
    except ValidationError as exc:
        typer.echo(exc.json(indent=2), err=True)
        raise typer.Exit(code=2) from exc
    _write_json(
        {
            "valid": True,
            "schema_version": packet.schema_version,
            "packet_id": str(packet.packet_id),
            "status": packet.status.value,
            "readiness": packet.readiness.value,
            "platform_verified": packet.proof.platform_verified,
        },
        None,
    )


@app.command("attest")
def attest_command(
    packet_path: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    actor: str = typer.Option(..., "--actor", help="Human who performed the action."),
    confirm_human_completed: bool = typer.Option(
        False,
        "--confirm-human-completed",
        help="Required explicit confirmation that the human performed the action manually.",
    ),
    output: Path | None = typer.Option(None, "--output", "-o", help="Optional receipt path."),
) -> None:
    """Record a human statement of completion without platform verification."""

    try:
        packet = HandoffPacket.model_validate(_read_json(packet_path))
        completed = attest_human_completion(
            packet,
            actor=actor,
            confirmed=confirm_human_completed,
        )
    except ValidationError as exc:
        typer.echo(exc.json(indent=2), err=True)
        raise typer.Exit(code=2) from exc
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=3) from exc

    _write_json(completed, output)


@app.command("profile-entry-export")
def profile_entry_export_command(
    resume_source: Annotated[
        Path,
        typer.Option(
            "--resume-source",
            exists=True,
            dir_okay=False,
            readable=True,
            help="Canonical resume Markdown source.",
        ),
    ],
    profile_url: Annotated[
        str,
        typer.Option("--profile-url", help="Graham-owned LinkedIn /in/ profile URL."),
    ],
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Optional JSON path.")] = None,
) -> None:
    """Export an editable JSON representation of Graham's LinkedIn profile."""

    _write_json(build_profile_entry(resume_path=resume_source, profile_url=profile_url), output)


@app.command("profile-sync-plan")
def profile_sync_plan_command(
    resume_source: Annotated[
        Path | None,
        typer.Option(
            "--resume-source",
            dir_okay=False,
            readable=True,
            help="Canonical resume Markdown source.",
        ),
    ] = None,
    entry_json: Annotated[
        Path | None,
        typer.Option(
            "--entry-json",
            exists=True,
            dir_okay=False,
            readable=True,
            help="Editable ops-linkedin.profile_entry.v1 JSON to sync.",
        ),
    ] = None,
    profile_url: Annotated[
        str | None,
        typer.Option("--profile-url", help="Graham-owned LinkedIn /in/ profile URL."),
    ] = None,
    accept_account_risk: Annotated[
        bool,
        typer.Option(
            "--accept-account-risk",
            help="Required acknowledgement for any LinkedIn own-profile automation plan.",
        ),
    ] = False,
    own_profile_only: Annotated[
        bool,
        typer.Option(
            "--own-profile-only",
            help="Required assertion that the target is Graham's own profile.",
        ),
    ] = False,
    surf_run: Annotated[
        Path,
        typer.Option("--surf-run", help="Surf skill run.sh path used in the emitted plan."),
    ] = DEFAULT_SURF_RUN,
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Optional packet path.")] = None,
) -> None:
    """Emit a RESUME.md-derived own-profile sync packet and Surf command plan."""

    if not accept_account_risk:
        typer.echo("--accept-account-risk is required for LinkedIn profile sync planning", err=True)
        raise typer.Exit(code=3)
    if not own_profile_only:
        typer.echo("--own-profile-only is required; this command cannot target other profiles", err=True)
        raise typer.Exit(code=3)
    if entry_json is not None:
        profile_entry = LinkedInProfileEntry.model_validate(_read_json(entry_json))
        packet = build_profile_sync_packet_from_entry(profile_entry=profile_entry, surf_run=surf_run)
    else:
        if resume_source is None or profile_url is None:
            typer.echo("either --entry-json or both --resume-source and --profile-url are required", err=True)
            raise typer.Exit(code=2)
        packet = build_profile_sync_packet(
            resume_path=resume_source,
            profile_url=profile_url,
            surf_run=surf_run,
        )
    _write_json(packet, output)


@app.command("resolve-leads")
def resolve_leads(
    name: Annotated[str, typer.Argument(help="Person's name as observed, e.g. from a Meetup attendee list.")],
    context: Annotated[str, typer.Option(help="Where they were observed: group, event title, topic.")] = "",
    location: Annotated[str, typer.Option(help="Geographic hint used in the public search.")] = "Buffalo",
    count: Annotated[int, typer.Option(help="Maximum candidates to return.")] = 5,
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Optional candidates path.")] = None,
) -> None:
    """Rank CANDIDATE LinkedIn profiles for a name. Never asserts an identity.

    Public web search only. Every row is a hypothesis the human confirms; a
    same-name mismatch would send a stranger a message that reads as though
    Graham knows them.
    """

    from .lead_resolver import resolve_candidates

    _write_json(resolve_candidates(name, context=context, location=location, count=count), output)


def main() -> None:
    """Console-script entrypoint."""

    app()


if __name__ == "__main__":
    main()
