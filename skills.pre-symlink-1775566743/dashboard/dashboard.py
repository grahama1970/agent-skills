"""Dashboard CLI — Typer entry point.

Commands:
  tui   Live terminal dashboard (default)
  json  JSON output for piping to /create-figure
  text  Plain-text summary

Inputs: reads from 8 data sources (see collectors.py).
Outputs: Rich TUI, JSON blob, or plain-text summary.
Failure modes: individual collectors fail gracefully (return error dicts).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import typer
from loguru import logger
from rich.console import Console

# Load .env before any os.getenv usage
from dotenv import find_dotenv, load_dotenv
load_dotenv(find_dotenv(usecwd=True), override=False)

app = typer.Typer(help="Embry OS Dev Dashboard")
console = Console()

# Task-monitor integration (MANDATORY per best-practices-skills)
_SKILLS_DIR = Path(__file__).resolve().parent.parent
_TM_RUN = _SKILLS_DIR / "task-monitor" / "run.sh"


def _tm(args: list[str]) -> bool:
    """Report to task-monitor. Returns True on success."""
    if not _TM_RUN.exists():
        return False
    try:
        return subprocess.run(
            [str(_TM_RUN), *args],
            capture_output=True, text=True, timeout=30,
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        ).returncode == 0
    except Exception:
        return False


@app.command()
def tui():
    """Launch the live Rich TUI dashboard."""
    from tui import DashboardTUI

    _tm(["start-session", "--project", "dashboard"])
    logger.info("Starting dashboard TUI")
    try:
        DashboardTUI().run()
    finally:
        _tm(["end-session", "--notes", "Dashboard TUI closed"])


@app.command("json")
def json_output():
    """Collect all data and print as JSON."""
    from collectors import collect_all
    from renderer import render_json

    _tm(["start-session", "--project", "dashboard"])
    logger.info("Collecting dashboard data (JSON mode)")
    data = collect_all()
    print(render_json(data))
    _tm(["add-accomplishment", "--text", f"JSON: {len(data)} sections collected"])
    _tm(["end-session", "--notes", "JSON output complete"])


@app.command()
def text():
    """Collect all data and print as plain text."""
    from collectors import collect_all
    from renderer import render_text

    _tm(["start-session", "--project", "dashboard"])
    logger.info("Collecting dashboard data (text mode)")
    data = collect_all()
    print(render_text(data))
    _tm(["add-accomplishment", "--text", f"Text: {len(data)} sections collected"])
    _tm(["end-session", "--notes", "Text output complete"])


@app.command()
def monitor(
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Aggregated view of all monitor-* skill reports."""
    from collectors import collect_monitor_reports
    from renderer import render_json

    _tm(["start-session", "--project", "dashboard"])
    logger.info("Collecting monitor reports")
    data = collect_monitor_reports()

    if json_output:
        import json as _json
        print(_json.dumps(data, indent=2))
    else:
        # Rich table of monitor health
        from rich.table import Table
        from rich.panel import Panel

        overall = data.get("overall_health", "unknown")
        color = {"healthy": "green", "warning": "yellow", "critical": "red"}.get(overall, "white")
        console.print(Panel(
            f"[{color} bold]{overall.upper()}[/{color} bold]  "
            f"({data.get('monitors_reporting', 0)}/{data.get('monitors_total', 0)} reporting)",
            title="Monitor Aggregation",
        ))

        table = Table(show_header=True, header_style="bold")
        table.add_column("Monitor", min_width=25)
        table.add_column("Health", justify="center", width=10)
        table.add_column("Probes", justify="center", width=8)
        table.add_column("Last Run", width=18)

        monitors = data.get("monitors", {})
        for name, m in sorted(monitors.items()):
            if not isinstance(m, dict) or "error" in m:
                table.add_row(name, "[dim]ERROR[/dim]", "", str(m.get("error", ""))[:30])
                continue
            h = m.get("health", "?")
            hc = {"healthy": "green", "warning": "yellow", "critical": "red"}.get(h, "white")
            table.add_row(
                name,
                f"[{hc}]{h.upper()}[/{hc}]",
                str(m.get("total_probes", "")),
                m.get("timestamp", "")[:16],
            )
        console.print(table)

    _tm(["end-session", "--notes", f"Monitor: {data.get('overall_health', '?')}"])


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """Default to TUI mode if no command given."""
    if ctx.invoked_subcommand is None:
        tui()


if __name__ == "__main__":
    app()
