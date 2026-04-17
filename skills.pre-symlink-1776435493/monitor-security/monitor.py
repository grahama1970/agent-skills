"""CLI for monitor-security skill.

Typer-based CLI with check, dashboard, fix, and threat-intel commands.
"""
from __future__ import annotations

import sys

import typer
from loguru import logger

logger.remove()
logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level:<7} | {message}")

app = typer.Typer(no_args_is_help=True, help="Security monitoring and nightly self-hack orchestrator.")


@app.command()
def check(
    tier: int = typer.Option(0, help="Run probes for specific tier (0=all)"),
    probe: str = typer.Option("", help="Run a specific probe by name"),
    autofix: bool = typer.Option(False, help="Apply auto-fixes where safe"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON to stdout"),
) -> None:
    """Run security probes and report results."""
    logger.info("monitor-security check tier={} probe={} autofix={}", tier, probe, autofix)

    from probes import run_probes, ProbeStatus
    from reporter import report_results

    results = run_probes(tier=tier, probe_name=probe, autofix=autofix)
    report_results(results, json_output=json_output)

    if any(r.status == ProbeStatus.FAIL for r in results):
        raise SystemExit(1)


@app.command()
def dashboard() -> None:
    """Show latest security report dashboard."""
    from reporter import show_dashboard
    show_dashboard()


@app.command()
def fix(
    probe_name: str = typer.Argument(..., help="Probe name to auto-fix"),
) -> None:
    """Trigger auto-fix for a specific probe."""
    logger.info("Running fix for probe: {}", probe_name)

    from probes import run_probes, ProbeStatus

    results = run_probes(probe_name=probe_name, autofix=True)
    if not results:
        logger.error("Probe not found: {}", probe_name)
        raise SystemExit(1)

    for r in results:
        if r.fix_applied:
            logger.info("[{}] Fix applied: {}", r.probe_id, r.message)
        elif r.auto_fixable:
            logger.warning("[{}] Auto-fixable but fix not applied: {}", r.probe_id, r.message)
        else:
            logger.info("[{}] Not auto-fixable: {}", r.probe_id, r.message)


@app.command(name="threat-intel")
def threat_intel(
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate flow without executing"),
) -> None:
    """Run hourly threat intelligence loop."""
    logger.info("Running threat intelligence loop (dry_run={})", dry_run)

    from threat_intel import run_hourly_loop
    run_hourly_loop(dry_run=dry_run)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
