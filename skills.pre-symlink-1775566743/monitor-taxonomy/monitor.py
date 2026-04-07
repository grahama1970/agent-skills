"""monitor-taxonomy: Three-tier cascade taxonomy quality monitor.

Assesses correctness of Heart/Mind taxonomy tags (`mind` on sparta_qra,
`heart` on lessons) and collection_tags via T0 heuristic → T1.5 classifier
→ T2 Brandon teacher cascade.

Entry point: `uv run --directory . python monitor.py <command>`

Inputs: CLI arguments (tier, probe, autofix, json).
Outputs: Rich console output or JSON report to stdout.
"""
from __future__ import annotations

import sys
from typing import Optional

import typer
from loguru import logger

logger.remove()
logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level:<7} | {message}")

app = typer.Typer(no_args_is_help=True, help="Three-tier cascade taxonomy quality monitor")


@app.command()
def check(
    tier: int = typer.Option(0, help="Run specific tier (0=all, 15=tier1.5)"),
    probe: str = typer.Option("", help="Run specific probe by name"),
    autofix: bool = typer.Option(False, help="Auto-fix safe probes"),
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="LLM model override (sets CHUTES_TEXT_MODEL)"),
) -> None:
    """Run taxonomy quality probes and report results."""
    logger.info("Running probes tier={} probe={} autofix={}", tier, probe, autofix)
    if model:
        import os
        os.environ["CHUTES_TEXT_MODEL"] = model
    from probes import run_probes
    from reporter import report_results
    results = run_probes(tier=tier, probe_name=probe, autofix=autofix)
    report_results(results, json_output=json_output)
    from probes import ProbeStatus
    if any(r.status == ProbeStatus.FAIL for r in results):
        raise SystemExit(1)


@app.command()
def dashboard() -> None:
    """Rich TUI showing latest probe results from state files."""
    from reporter import show_dashboard
    show_dashboard()


@app.command()
def status() -> None:
    """Show cascade status: label count, shadow agreement, classifier availability."""
    from reporter import show_status
    show_status()


@app.command()
def fix(probe_name: str = typer.Argument(..., help="Probe name to fix")) -> None:
    """Manually trigger auto-fix for a specific probe."""
    from probes import run_probes
    from reporter import report_results
    results = run_probes(tier=0, probe_name=probe_name, autofix=True)
    report_results(results, json_output=False)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
