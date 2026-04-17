"""monitor-memory: Nightly health orchestrator for memory, personas, and projects.

Composes existing skills (ops-arango, taxonomy, persona-journal, create-movie,
monitor-personas, assess, create-walkthrough) into 20 probes across 5 tiers.
Delegates all work -- never reimplements helper skill logic.

Entry point: `uv run --directory . python monitor.py <command>`

Inputs: CLI arguments (tier, probe, autofix, json).
Outputs: Rich console output or JSON report to stdout.
"""
from __future__ import annotations

import sys

import typer
from loguru import logger

logger.remove()
logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level:<7} | {message}")

app = typer.Typer(no_args_is_help=True, help="Nightly memory & system health orchestrator")


@app.command()
def check(
    tier: int = typer.Option(0, help="Run specific tier (0=all)"),
    probe: str = typer.Option("", help="Run specific probe by name"),
    autofix: bool = typer.Option(False, help="Auto-fix safe probes (Tier 1)"),
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Run health probes and report results."""
    logger.info("Running probes tier={} probe={} autofix={}", tier, probe, autofix)
    from probes import run_probes
    from reporter import report_results
    results = run_probes(tier=tier, probe_name=probe, autofix=autofix)
    report_results(results, json_output=json_output)
    # Log probe failures but always exit 0 — the monitor succeeded at running.
    # Scheduler cares about "did the monitor run?" not "did it find problems?"
    from probes import ProbeStatus
    fail_count = sum(1 for r in results if r.status == ProbeStatus.FAIL)
    if fail_count:
        logger.warning("{} probe(s) reported FAIL — see report for details", fail_count)


@app.command()
def dashboard() -> None:
    """Rich TUI showing latest probe results from state files."""
    from reporter import show_dashboard
    show_dashboard()


@app.command()
def report(
    output: str = typer.Option("", help="Custom output path for REPORT.md"),
) -> None:
    """Generate health report with mermaid charts and store in memory."""
    from reporter import generate_health_report
    from probes import run_probes, ProbeStatus
    logger.info("Running all probes for report generation...")
    results = run_probes(tier=0, probe_name="", autofix=False)
    counts = {s: 0 for s in ProbeStatus}
    for r in results:
        counts[r.status] += 1
    health = "healthy"
    if counts[ProbeStatus.FAIL] > 0:
        health = "critical"
    elif counts[ProbeStatus.WARN] > 0:
        health = "warning"
    report_path = generate_health_report(results, health, counts)
    if report_path:
        logger.info("Report: {}", report_path)
    else:
        logger.error("Report generation failed")


@app.command()
def fix(probe_name: str = typer.Argument(..., help="Probe name to fix")) -> None:
    """Manually trigger auto-fix for a specific probe."""
    from autofix import run_fix
    run_fix(probe_name)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
