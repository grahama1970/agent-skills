"""monitor-workstation: Nightly workstation health monitor.

Enforces "no artifacts on NVMe" rule, detects cache bloat, checks drive
health, and alerts on threshold breaches.  Composes existing ops-* skills
— never reimplements their logic.

Entry point: `uv run --directory . python monitor.py <command>`

Inputs: CLI arguments (autofix, json, report).
Outputs: Rich console table or JSON report to stdout.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import typer
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from probes import ALL_PROBES, ProbeResult, ProbeStatus

logger.remove()
logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level:<7} | {message}")

app = typer.Typer(no_args_is_help=True, help="Nightly workstation health monitor")

STATE_DIR = Path.home() / ".pi" / "monitor-workstation"
SKILLS_DIR = Path(__file__).resolve().parent.parent

console = Console(stderr=True)


# ---------------------------------------------------------------------------
# Probe orchestrator
# ---------------------------------------------------------------------------

def run_all_probes(autofix: bool = False) -> list[ProbeResult]:
    """Execute all probes and collect results."""
    results: list[ProbeResult] = []
    for probe_id, name, fn in ALL_PROBES:
        try:
            logger.info("[{}] Running {}", probe_id, name)
            result = fn(autofix=autofix)
            results.append(result)
            logger.info("[{}] {} → {}", probe_id, name, result.status.value)
        except Exception as e:
            logger.error("[{}] {} crashed: {}", probe_id, name, e)
            results.append(ProbeResult(
                probe_id=probe_id, name=name,
                status=ProbeStatus.FAIL,
                message=f"Probe crashed: {e}",
            ))
    return results


# ---------------------------------------------------------------------------
# Reporter
# ---------------------------------------------------------------------------

_STATUS_STYLE = {
    ProbeStatus.PASS: "green",
    ProbeStatus.WARN: "yellow",
    ProbeStatus.FAIL: "red bold",
    ProbeStatus.SKIP: "dim",
    ProbeStatus.FIXED: "cyan",
}


def _compute_health(results: list[ProbeResult]) -> str:
    if any(r.status == ProbeStatus.FAIL for r in results):
        return "critical"
    if any(r.status == ProbeStatus.WARN for r in results):
        return "warning"
    return "healthy"


def _render_table(results: list[ProbeResult]) -> None:
    health = _compute_health(results)
    health_color = {"healthy": "green", "warning": "yellow", "critical": "red"}[health]
    counts = {s: sum(1 for r in results if r.status == s) for s in ProbeStatus}

    console.print(Panel(
        f"[{health_color} bold]{health.upper()}[/{health_color} bold]  "
        f"({counts[ProbeStatus.PASS]} pass, {counts[ProbeStatus.WARN]} warn, "
        f"{counts[ProbeStatus.FAIL]} fail, {counts[ProbeStatus.SKIP]} skip, "
        f"{counts[ProbeStatus.FIXED]} fixed)",
        title="Monitor Workstation",
        subtitle=time.strftime("%Y-%m-%d %H:%M"),
    ))

    table = Table(show_header=True, header_style="bold")
    table.add_column("ID", style="dim", width=4)
    table.add_column("Probe", min_width=20)
    table.add_column("Status", justify="center", width=8)
    table.add_column("Value", justify="right", width=10)
    table.add_column("Message")

    for r in results:
        style = _STATUS_STYLE.get(r.status, "")
        table.add_row(
            r.probe_id, r.name,
            f"[{style}]{r.status.value.upper()}[/{style}]",
            str(r.value) if r.value else "",
            r.message,
        )

    console.print(table)


def _build_json_payload(results: list[ProbeResult]) -> dict:
    health = _compute_health(results)
    counts = {s.value: sum(1 for r in results if r.status == s) for s in ProbeStatus}

    # Build figure_data for /dashboard consumption
    figure_metrics: dict[str, float] = {}
    for r in results:
        if r.probe_id == "W01":
            figure_metrics["NVMe Used %"] = r.value
        elif r.probe_id == "W03":
            figure_metrics["Cache GB"] = r.value
        elif r.probe_id == "W04":
            figure_metrics["Experiments GB"] = r.value
        elif r.probe_id == "W06":
            figure_metrics["Docker Reclaimable GB"] = r.value

    return {
        "health": health,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "summary": counts,
        "total": len(results),
        "probes": [
            {
                "probe_id": r.probe_id,
                "name": r.name,
                "status": r.status.value,
                "message": r.message,
                "value": r.value,
                "details": r.details,
                "auto_fixable": r.auto_fixable,
                "fix_applied": r.fix_applied,
            }
            for r in results
        ],
        "figure_data": {
            "bar": {"metrics": figure_metrics},
        },
    }


def _save_state(payload: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    # Save latest report
    report_file = STATE_DIR / "report.json"
    try:
        tmp = report_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2))
        os.replace(tmp, report_file)
    except OSError as e:
        logger.error("Failed to save report: {}", e)

    # Append to history
    history_file = STATE_DIR / "history.jsonl"
    try:
        with open(history_file, "a") as f:
            f.write(json.dumps({
                "timestamp": payload["timestamp"],
                "health": payload["health"],
                "summary": payload["summary"],
                "probes": [
                    {"id": p["probe_id"], "name": p["name"],
                     "status": p["status"], "value": p["value"]}
                    for p in payload["probes"]
                ],
            }) + "\n")
    except OSError as e:
        logger.error("Failed to append history: {}", e)


def _send_discord_alerts(results: list[ProbeResult]) -> None:
    """Send Discord alerts for WARN/FAIL probes via common/discord_notify."""
    alerts = [r for r in results if r.status in (ProbeStatus.WARN, ProbeStatus.FAIL)]
    if not alerts:
        return

    try:
        skills_dir = Path(__file__).resolve().parent.parent
        if str(skills_dir) not in sys.path:
            sys.path.insert(0, str(skills_dir))
        from common.discord_notify import notify_health

        health = _compute_health(results)
        status = "critical" if health == "critical" else "warning"
        lines = [f"- [{r.probe_id}] {r.name}: {r.message}" for r in alerts]
        notify_health(
            skill="monitor-workstation",
            status=status,
            message="\n".join(lines),
            title=f"Workstation Health: {health.upper()}",
        )
        logger.info("Discord alert sent for {} probe(s)", len(alerts))
    except Exception as e:
        logger.warning("Discord notification failed: {}", e)


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

@app.command()
def check(
    autofix: bool = typer.Option(False, help="Auto-fix safe probes (cache pruning)"),
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
    report: bool = typer.Option(False, "--report", help="Generate visual report via /analytics"),
) -> None:
    """Run all 8 health probes and report results."""
    logger.info("Running probes autofix={}", autofix)
    results = run_all_probes(autofix=autofix)

    if not results:
        logger.warning("No probe results")
        return

    payload = _build_json_payload(results)

    if json_output:
        out = Console()
        out.print_json(json.dumps(payload))
    else:
        _render_table(results)

    _save_state(payload)
    _send_discord_alerts(results)

    if report:
        _generate_visual_report(payload)

    fail_count = sum(1 for r in results if r.status == ProbeStatus.FAIL)
    if fail_count:
        logger.warning("{} probe(s) reported FAIL — see report for details", fail_count)


def _generate_visual_report(payload: dict) -> None:
    """Generate visual report by composing /analytics -> /create-figure."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    # Write probe data as JSONL for /analytics
    probe_data_file = STATE_DIR / "probe_data.jsonl"
    with open(probe_data_file, "w") as f:
        for p in payload["probes"]:
            f.write(json.dumps({"name": p["name"], "value": p["value"],
                                "status": p["status"]}) + "\n")

    metrics_file = STATE_DIR / "metrics.json"
    report_png = STATE_DIR / "report.png"

    # Step 1: analytics group-by
    analytics = SKILLS_DIR / "analytics" / "run.sh"
    if analytics.exists():
        try:
            subprocess.run(
                [str(analytics), "group-by", str(probe_data_file),
                 "--by", "name", "--agg", "value", "--func", "last",
                 "--for-figure", "-o", str(metrics_file)],
                capture_output=True, timeout=30,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
        except (subprocess.TimeoutExpired, OSError) as e:
            logger.warning("analytics group-by failed: {}", e)
            return

    # Step 2: create-figure
    create_figure = SKILLS_DIR / "create-figure" / "run.sh"
    if create_figure.exists() and metrics_file.exists():
        try:
            subprocess.run(
                [str(create_figure), "metrics", "-i", str(metrics_file),
                 "--type", "hbar", "-o", str(report_png)],
                capture_output=True, timeout=30,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            logger.info("Visual report: {}", report_png)
        except (subprocess.TimeoutExpired, OSError) as e:
            logger.warning("create-figure failed: {}", e)

    # Step 3: historical trend
    history_file = STATE_DIR / "history.jsonl"
    if history_file.exists() and create_figure.exists() and analytics.exists():
        trend_json = STATE_DIR / "trend.json"
        trend_png = STATE_DIR / "trend.png"
        try:
            subprocess.run(
                [str(analytics), "chart", str(history_file),
                 "--name", "trend_nvme_usage", "-o", str(trend_json)],
                capture_output=True, timeout=30,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            if trend_json.exists():
                subprocess.run(
                    [str(create_figure), "training-curves", "-i", str(trend_json),
                     "-o", str(trend_png)],
                    capture_output=True, timeout=30,
                    env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
                )
                logger.info("Trend report: {}", trend_png)
        except (subprocess.TimeoutExpired, OSError) as e:
            logger.warning("Trend generation failed: {}", e)


@app.command()
def dashboard() -> None:
    """Rich TUI showing latest probe results from state files."""
    report_file = STATE_DIR / "report.json"
    if not report_file.exists():
        console.print("[yellow]No report found. Run 'check' first.[/yellow]")
        return

    try:
        data = json.loads(report_file.read_text())
    except (json.JSONDecodeError, OSError) as e:
        console.print(f"[red]Failed to load report: {e}[/red]")
        return

    health = data.get("health", "unknown")
    health_color = {"healthy": "green", "warning": "yellow", "critical": "red"}.get(
        health, "white")

    console.print(Panel(
        f"[{health_color} bold]{health.upper()}[/{health_color} bold]",
        title="Workstation Dashboard",
        subtitle=data.get("timestamp", ""),
    ))

    table = Table(show_header=True, header_style="bold")
    table.add_column("ID", style="dim", width=4)
    table.add_column("Probe", min_width=20)
    table.add_column("Status", justify="center", width=8)
    table.add_column("Value", justify="right", width=10)
    table.add_column("Message")

    for p in data.get("probes", []):
        status = p.get("status", "unknown")
        style = {"pass": "green", "warn": "yellow", "fail": "red bold",
                 "skip": "dim", "fixed": "cyan"}.get(status, "")
        table.add_row(
            p.get("probe_id", ""), p.get("name", ""),
            f"[{style}]{status.upper()}[/{style}]",
            str(p.get("value", "")),
            p.get("message", ""),
        )
    console.print(table)


@app.command()
def fix(probe_name: str = typer.Argument(..., help="Probe name to fix")) -> None:
    """Manually trigger auto-fix for a specific probe."""
    logger.info("Manual fix requested for probe: {}", probe_name)

    probe_map = {name: fn for _, name, fn in ALL_PROBES}
    if probe_name not in probe_map:
        logger.error("Probe '{}' not found. Available: {}",
                     probe_name, list(probe_map.keys()))
        raise SystemExit(1)

    result = probe_map[probe_name](autofix=True)
    _render_table([result])

    if not result.auto_fixable:
        logger.warning("Probe '{}' is not auto-fixable", probe_name)
    elif result.fix_applied:
        logger.info("Fix applied successfully for '{}'", probe_name)
    elif result.status == ProbeStatus.PASS:
        logger.info("Probe '{}' is already passing", probe_name)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
