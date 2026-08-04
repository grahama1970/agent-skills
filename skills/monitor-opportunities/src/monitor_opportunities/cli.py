"""CLI entrypoint for the read-only Stage 0 opportunity monitor."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import NoReturn

import typer
from loguru import logger

from . import __version__
from .buzz_review import BuzzAgentReviewConfig, create_buzz_agent_review
from .contracts import CONTRACT_VERSION, IMMUTABLE_GOAL, STAGE, ContractError
from .decisions import append_decision, replay as replay_decisions
from .discovery import sweep as sweep_sources
from .pipeline import run_stage0, status_for_run
from .ranking import rank as rank_candidates
from .report import load_manifest, render_report
from .service import serve as serve_report
from .tailoring import tailor as tailor_resume
from .verification import run_verification

app = typer.Typer(
    name="monitor-opportunities",
    help="Zero-network Stage 0 status, report, and verification kernel.",
    no_args_is_help=True,
)

IMPLEMENTED = [
    "status",
    "report",
    "verify",
    "sweep",
    "rank",
    "tailor",
    "decision",
    "replay",
    "run",
    "resume",
    "schedule",
    "serve",
    "buzz-review",
]
NOT_IMPLEMENTED = [
    "apply",
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
        "network_access": True,
        "external_effects": False,
        "implemented_commands": IMPLEMENTED,
        "not_implemented_commands": NOT_IMPLEMENTED,
        "capabilities": {
            "local_report": "IMPLEMENTED",
            "verification_receipt": "IMPLEMENTED",
            "live_discovery": "IMPLEMENTED_READ_ONLY",
            "eligibility_and_ranking": "IMPLEMENTED_LOCAL",
            "claim_bound_tailoring": "IMPLEMENTED_LOCAL",
            "decision_ledger": "IMPLEMENTED_LOCAL",
            "loopback_decision_service": "IMPLEMENTED_LOCAL",
            "scheduler_registration": "IMPLEMENTED_LOCAL_READBACK",
            "gmail_mailbox_draft": "BLOCKED_STAGE_0",
            "gmail_send": "PERMANENTLY_FORBIDDEN",
            "linkedin_handoff": "BLOCKED_STAGE_0",
            "linkedin_automation": "PERMANENTLY_FORBIDDEN",
            "ats_inspect": "BLOCKED_STAGE_0",
            "ats_prefill": "BLOCKED_STAGE_0",
            "ats_submit": "BLOCKED_STAGE_0",
        },
        "non_claims": [
            "Stage 0 does not prove long-run nightly reliability.",
            "No Gmail, LinkedIn, ATS, Memory, or scheduler effect is hidden behind report rendering.",
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


@app.command()
def sweep(
    lane: str = typer.Option("A,B,C", "--lane", help="Comma-separated lanes to attempt."),
    out: Path = typer.Option(..., "--out", file_okay=False),
    fixture_dir: Path | None = typer.Option(None, "--fixture-dir", file_okay=False),
) -> None:
    """Run read-only source discovery and write local receipts."""
    _configure_logging()
    lanes = {item.strip().upper() for item in lane.split(",") if item.strip()}
    skill_dir = Path(__file__).resolve().parents[2]
    receipt = sweep_sources(skill_dir=skill_dir, lanes=lanes, out_dir=out, fixture_dir=fixture_dir)
    typer.echo(json.dumps({"status": "PASS", **receipt}, indent=2, sort_keys=True))


@app.command()
def rank(
    input_dir: Path = typer.Option(..., "--input", exists=True, readable=True),
    limit: int = typer.Option(8, "--limit", min=0, max=8),
    out: Path = typer.Option(..., "--out", file_okay=False),
) -> None:
    """Hard-gate eligibility before deterministic ranking."""
    _configure_logging()
    receipt = rank_candidates(input_dir, limit, out)
    typer.echo(json.dumps({"status": "PASS", **receipt}, indent=2, sort_keys=True))


@app.command()
def tailor(
    posting: str = typer.Option(..., "--posting"),
    claims: Path = typer.Option(..., "--claims", exists=True, dir_okay=False, readable=True),
    out: Path = typer.Option(..., "--out", file_okay=False),
) -> None:
    """Compile a local claim-bound resume variant."""
    _configure_logging()
    try:
        receipt = tailor_resume(posting, claims, out)
    except ValueError as exc:
        _fail(ContractError("TAILORING_FAILED", str(exc)))
    typer.echo(json.dumps({"status": "PASS", **receipt}, indent=2, sort_keys=True))


@app.command()
def decision(
    run: Path = typer.Option(..., "--run", file_okay=False),
    item: str = typer.Option(..., "--item"),
    action: str = typer.Option(..., "--action"),
    actor: str = typer.Option("candidate", "--actor"),
    idempotency_key: str = typer.Option(..., "--idempotency-key"),
    reason: str | None = typer.Option(None, "--reason"),
) -> None:
    """Append one local decision event; external effects are impossible."""
    _configure_logging()
    try:
        event = append_decision(
            run_dir=run,
            item_id=item,
            action=action,
            actor=actor,
            idempotency_key=idempotency_key,
            reason=reason,
        )
    except ValueError as exc:
        _fail(ContractError("DECISION_REJECTED", str(exc)))
    typer.echo(json.dumps({"status": "PASS", **event}, indent=2, sort_keys=True))


@app.command()
def replay(
    run: Path = typer.Option(..., "--run", exists=True, file_okay=False, readable=True),
) -> None:
    """Replay the local decision ledger into the current projection."""
    _configure_logging()
    projection = replay_decisions(run)
    typer.echo(json.dumps({"status": "PASS", **projection}, indent=2, sort_keys=True))


@app.command()
def serve(
    report: Path = typer.Option(..., "--report", exists=True, file_okay=False, readable=True),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port", min=1, max=65535),
    allow_remote: bool = typer.Option(
        False,
        "--allow-remote",
        help="Allow non-loopback bind for Tailscale/LAN review.",
    ),
) -> None:
    """Serve one token-gated morning report and decision loop."""
    _configure_logging()
    try:
        serve_report(report, host, port, allow_remote=allow_remote)
    except ValueError as exc:
        _fail(ContractError("SERVE_REJECTED", str(exc)))


@app.command("run")
def run_command(
    out: Path | None = typer.Option(None, "--out", file_okay=False),
    fixture_dir: Path | None = typer.Option(None, "--fixture-dir", file_okay=False),
) -> None:
    """Run one resumable Stage 0 transaction with no external effects."""
    _configure_logging()
    skill_dir = Path(__file__).resolve().parents[2]
    if out is None:
        out = skill_dir / "local" / "nightly" / "latest"
    receipt = run_stage0(skill_dir, out, fixture_dir)
    typer.echo(json.dumps({"status": "PASS", **receipt}, indent=2, sort_keys=True))


@app.command()
def resume(
    run: Path = typer.Option(..., "--run", exists=True, file_okay=False, readable=True),
) -> None:
    """Read back a prior Stage 0 run status."""
    _configure_logging()
    typer.echo(json.dumps(status_for_run(run), indent=2, sort_keys=True))


@app.command("buzz-review")
def buzz_review(
    run: Path = typer.Option(..., "--run", exists=True, file_okay=False, readable=True),
    channel: str = typer.Option(..., "--channel", help="Buzz channel UUID or configured channel id."),
    target_agent: str = typer.Option(..., "--target-agent", help="Buzz agent name to address."),
    report_url: str = typer.Option(..., "--report-url", help="Human-accessible report URL."),
    out: Path | None = typer.Option(None, "--out", file_okay=False),
    mention_pubkey: str | None = typer.Option(None, "--mention-pubkey"),
    ops_buzz_run: Path | None = typer.Option(None, "--ops-buzz-run", dir_okay=False),
    timeout_seconds: int = typer.Option(0, "--timeout-seconds", min=0, max=600),
    poll_interval_seconds: int = typer.Option(5, "--poll-interval-seconds", min=1, max=60),
    readback_limit: int = typer.Option(20, "--readback-limit", min=1, max=100),
) -> None:
    """Create a no-network Buzz agent-review request for one completed report run."""
    _configure_logging()
    if out is None:
        out = run / "buzz-review"
    try:
        receipt = create_buzz_agent_review(
            BuzzAgentReviewConfig(
                run_dir=run,
                out_dir=out,
                channel=channel,
                target_agent=target_agent,
                report_url=report_url,
                mention_pubkey=mention_pubkey,
                ops_buzz_run=ops_buzz_run,
                timeout_seconds=timeout_seconds,
                poll_interval_seconds=poll_interval_seconds,
                readback_limit=readback_limit,
            )
        )
    except ContractError as exc:
        _fail(exc)
    typer.echo(json.dumps(receipt, indent=2, sort_keys=True))


@app.command()
def schedule(
    cron: str = typer.Option("0 2 * * *", "--cron"),
) -> None:
    """Register the single full-run transaction with the scheduler and read it back."""
    _configure_logging()
    import subprocess

    repo_root = Path(__file__).resolve().parents[4]
    scheduler = repo_root / "skills" / "scheduler" / "run.sh"
    command = str(repo_root / "skills" / "monitor-opportunities" / "run.sh") + " run"
    register = subprocess.run(
        [
            str(scheduler),
            "register",
            "--name",
            "monitor-opportunities-nightly",
            "--cron",
            cron,
            "--command",
            command,
            "--workdir",
            str(repo_root),
            "--description",
            "Nightly Stage 0 opportunity report",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    listing = subprocess.run(
        [str(scheduler), "list", "--json"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    jobs = json.loads(listing.stdout)
    job = jobs.get("monitor-opportunities-nightly")
    if not job or job.get("cron") != cron or job.get("command") != command:
        _fail(ContractError("SCHEDULER_READBACK_FAILED", "Registered job did not read back"))
    typer.echo(
        json.dumps(
            {
                "status": "PASS",
                "schema": "monitor_opportunities.scheduler_receipt.v1",
                "external_effects": False,
                "name": "monitor-opportunities-nightly",
                "cron": cron,
                "command": command,
                "workdir": str(repo_root),
                "register_stdout": register.stdout,
                "readback": job,
            },
            indent=2,
            sort_keys=True,
        )
    )


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
