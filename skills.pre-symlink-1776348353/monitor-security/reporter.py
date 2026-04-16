"""Rich console output and JSON report generation for monitor-security.

Renders probe results as a Rich table for terminal output, or as structured
JSON for machine consumption and state persistence.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from probes import ProbeResult, ProbeStatus

import config

console = Console(stderr=True)

_STATUS_STYLE = {
    ProbeStatus.PASS: "green",
    ProbeStatus.WARN: "yellow",
    ProbeStatus.FAIL: "red bold",
    ProbeStatus.SKIP: "dim",
    ProbeStatus.FIXED: "cyan",
}


def report_results(results: list[ProbeResult], json_output: bool = False) -> None:
    """Render probe results to console and optionally as JSON."""
    if not results:
        logger.warning("No probe results to report")
        return

    counts = {s: 0 for s in ProbeStatus}
    for r in results:
        counts[r.status] += 1

    total = len(results)
    health = "healthy"
    if counts[ProbeStatus.FAIL] > 0:
        health = "critical"
    elif counts[ProbeStatus.WARN] > 0:
        health = "warning"

    if not json_output:
        _render_table(results, health, counts, total)
    else:
        _render_json(results, health, counts, total)

    _save_state(results, health, counts, total)


def _render_table(
    results: list[ProbeResult],
    health: str,
    counts: dict,
    total: int,
) -> None:
    health_color = {"healthy": "green", "warning": "yellow", "critical": "red"}[health]

    console.print(Panel(
        f"[{health_color} bold]{health.upper()}[/{health_color} bold]  "
        f"({counts[ProbeStatus.PASS]} pass, {counts[ProbeStatus.WARN]} warn, "
        f"{counts[ProbeStatus.FAIL]} fail, {counts[ProbeStatus.SKIP]} skip, "
        f"{counts[ProbeStatus.FIXED]} fixed)",
        title="Monitor Security",
        subtitle=time.strftime("%Y-%m-%d %H:%M"),
    ))

    table = Table(show_header=True, header_style="bold")
    table.add_column("ID", style="dim", width=4)
    table.add_column("Probe", min_width=26)
    table.add_column("Tier", justify="center", width=4)
    table.add_column("Status", justify="center", width=8)
    table.add_column("Message")

    for r in results:
        style = _STATUS_STYLE.get(r.status, "")
        table.add_row(
            r.probe_id,
            r.name,
            str(r.tier),
            f"[{style}]{r.status.value.upper()}[/{style}]",
            r.message,
        )

    console.print(table)


def _render_json(
    results: list[ProbeResult],
    health: str,
    counts: dict,
    total: int,
) -> None:
    out_console = Console()
    payload = {
        "health": health,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "summary": {s.value: c for s, c in counts.items()},
        "total": total,
        "probes": [
            {
                "probe_id": r.probe_id,
                "name": r.name,
                "tier": r.tier,
                "status": r.status.value,
                "message": r.message,
                "details": r.details,
                "auto_fixable": r.auto_fixable,
                "fix_applied": r.fix_applied,
            }
            for r in results
        ],
    }
    out_console.print_json(json.dumps(payload))


def _save_state(
    results: list[ProbeResult],
    health: str,
    counts: dict,
    total: int,
) -> None:
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_file = config.STATE_DIR / "latest_report.json"
    payload = {
        "health": health,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "summary": {s.value: c for s, c in counts.items()},
        "total": total,
        "probes": [
            {
                "probe_id": r.probe_id,
                "name": r.name,
                "tier": r.tier,
                "status": r.status.value,
                "message": r.message,
                "auto_fixable": r.auto_fixable,
                "fix_applied": r.fix_applied,
            }
            for r in results
        ],
    }
    try:
        tmp = state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2))
        os.replace(tmp, state_file)
    except OSError as e:
        logger.error("Failed to save state: {}", e)


def show_dashboard() -> None:
    """Load latest report from state and render dashboard."""
    state_file = config.STATE_DIR / "latest_report.json"
    if not state_file.exists():
        console.print("[yellow]No report found. Run 'check' first.[/yellow]")
        return

    try:
        data = json.loads(state_file.read_text())
    except (json.JSONDecodeError, OSError) as e:
        console.print(f"[red]Failed to load report: {e}[/red]")
        return

    health = data.get("health", "unknown")
    health_color = {"healthy": "green", "warning": "yellow", "critical": "red"}.get(
        health, "white",
    )

    console.print(Panel(
        f"[{health_color} bold]{health.upper()}[/{health_color} bold]",
        title="Monitor Security Dashboard",
        subtitle=data.get("timestamp", ""),
    ))

    summary = data.get("summary", {})
    summary_table = Table(title="Summary", show_header=True)
    summary_table.add_column("Status", style="cyan")
    summary_table.add_column("Count", justify="right")
    for status, count in summary.items():
        summary_table.add_row(status, str(count))
    console.print(summary_table)

    probes = data.get("probes", [])
    if probes:
        probe_table = Table(title="Probes", show_header=True, header_style="bold")
        probe_table.add_column("ID", style="dim", width=4)
        probe_table.add_column("Probe", min_width=26)
        probe_table.add_column("Tier", justify="center", width=4)
        probe_table.add_column("Status", justify="center", width=8)
        probe_table.add_column("Message")

        for p in probes:
            status = p.get("status", "unknown")
            style = {
                "pass": "green", "warn": "yellow", "fail": "red bold",
                "skip": "dim", "fixed": "cyan",
            }.get(status, "")
            probe_table.add_row(
                p.get("probe_id", ""),
                p.get("name", ""),
                str(p.get("tier", "")),
                f"[{style}]{status.upper()}[/{style}]",
                p.get("message", ""),
            )
        console.print(probe_table)
