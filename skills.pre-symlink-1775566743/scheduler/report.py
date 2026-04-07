"""
Report generation - comprehensive status reports with metrics and failures.

Provides both Rich TUI and plain text report output.
"""
import json
from datetime import datetime
from typing import Any

from config import LOG_DIR, METRICS_COUNTERS
from job_registry import load_jobs
from utils import rprint, is_daemon_running, get_daemon_pid, HAS_RICH, console

# Conditional imports for rich components
if HAS_RICH:
    from rich.table import Table
    from rich.panel import Panel


def generate_report_data() -> dict[str, Any]:
    """
    Generate comprehensive report data.

    Returns:
        Dictionary containing all report metrics and job statistics.
    """
    jobs = load_jobs()

    # Aggregate metrics
    total_jobs = len(jobs)
    enabled_jobs = sum(1 for j in jobs.values() if j.get("enabled", True))
    jobs_run = sum(1 for j in jobs.values() if j.get("last_run"))

    # Calculate success/failure counts from job history
    successes = sum(1 for j in jobs.values() if j.get("last_status") == "success")
    failures = sum(1 for j in jobs.values() if j.get("last_status") == "failed")
    timeouts = sum(1 for j in jobs.values() if j.get("last_status") == "timeout")

    # Per-job stats
    job_stats = []
    recent_failures = []

    for name, job in sorted(jobs.items(), key=lambda x: x[1].get("last_run") or 0, reverse=True):
        stat = {
            "name": name,
            "enabled": job.get("enabled", True),
            "schedule": job.get("cron") or job.get("interval", "hook"),
            "last_run": job.get("last_run"),
            "last_status": job.get("last_status"),
            "last_duration": job.get("last_duration", 0),
            "description": job.get("description", ""),
        }
        job_stats.append(stat)

        # Collect recent failures
        if stat["last_status"] in ("failed", "timeout"):
            log_file = LOG_DIR / f"{name}.log"
            log_excerpt = ""
            if log_file.exists():
                with open(log_file) as f:
                    lines = f.readlines()
                    # Get last execution block
                    last_block = []
                    for line in reversed(lines):
                        last_block.insert(0, line)
                        if line.startswith("====="):
                            break
                        if len(last_block) > 20:
                            break
                    log_excerpt = "".join(last_block[-15:])

            recent_failures.append({
                "name": name,
                "status": stat["last_status"],
                "last_run": stat["last_run"],
                "duration": stat["last_duration"],
                "log_excerpt": log_excerpt.strip(),
            })

    # Calculate aggregate metrics
    total_duration = sum(j.get("last_duration", 0) for j in jobs.values() if j.get("last_run"))
    avg_duration = total_duration / jobs_run if jobs_run > 0 else 0
    success_rate = (successes / jobs_run * 100) if jobs_run > 0 else 0

    return {
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "total_jobs": total_jobs,
            "enabled_jobs": enabled_jobs,
            "jobs_with_runs": jobs_run,
            "successes": successes,
            "failures": failures,
            "timeouts": timeouts,
            "success_rate": round(success_rate, 1),
            "avg_duration_seconds": round(avg_duration, 2),
            "total_runtime_seconds": round(total_duration, 2),
        },
        "daemon": {
            "running": is_daemon_running(),
            "pid": get_daemon_pid(),
            "metrics_counters": METRICS_COUNTERS,
        },
        "jobs": job_stats,
        "recent_failures": recent_failures[:5],  # Top 5 recent failures
    }


def print_report_json(report_data: dict[str, Any]) -> None:
    """Print report as JSON."""
    print(json.dumps(report_data, indent=2, default=str))


def print_report_rich(report_data: dict[str, Any]) -> None:
    """Print report using Rich TUI."""
    if not HAS_RICH or not console:
        print_report_plain(report_data)
        return

    summary = report_data["summary"]
    job_stats = report_data["jobs"]
    recent_failures = report_data["recent_failures"]

    # Header
    console.print()
    console.print(Panel.fit(
        f"[bold]Scheduler Report[/bold]\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        border_style="blue"
    ))

    # Summary stats
    console.print("\n[bold cyan]Summary[/bold cyan]")
    summary_table = Table(show_header=False, box=None, padding=(0, 2))
    summary_table.add_column("Metric", style="dim")
    summary_table.add_column("Value", style="bold")

    summary_table.add_row("Total Jobs", str(summary["total_jobs"]))
    summary_table.add_row("Enabled", f"[green]{summary['enabled_jobs']}[/green]")
    summary_table.add_row("Jobs Run", str(summary["jobs_with_runs"]))

    success_rate = summary["success_rate"]
    success_style = "green" if success_rate >= 90 else "yellow" if success_rate >= 70 else "red"
    summary_table.add_row("Success Rate", f"[{success_style}]{success_rate:.1f}%[/{success_style}]")
    summary_table.add_row("Avg Duration", f"{summary['avg_duration_seconds']:.1f}s")

    if summary["failures"] > 0:
        summary_table.add_row("Failures", f"[red]{summary['failures']}[/red]")
    if summary["timeouts"] > 0:
        summary_table.add_row("Timeouts", f"[yellow]{summary['timeouts']}[/yellow]")

    console.print(summary_table)

    # Daemon status
    daemon_running = report_data["daemon"]["running"]
    daemon_status = "[green]RUNNING[/green]" if daemon_running else "[red]STOPPED[/red]"
    pid = report_data["daemon"]["pid"]
    console.print(f"\n[bold cyan]Daemon[/bold cyan]: {daemon_status}" + (f" (PID {pid})" if pid else ""))

    # Per-job table
    console.print("\n[bold cyan]Job Status[/bold cyan]")
    job_table = Table(show_header=True, header_style="bold")
    job_table.add_column("Job", style="cyan")
    job_table.add_column("Schedule")
    job_table.add_column("Last Run")
    job_table.add_column("Duration")
    job_table.add_column("Status")

    for stat in job_stats[:15]:  # Top 15
        last_run_str = datetime.fromtimestamp(stat["last_run"]).strftime("%m-%d %H:%M") if stat["last_run"] else "[dim]never[/dim]"
        duration_str = f"{stat['last_duration']:.1f}s" if stat["last_duration"] else "-"

        status = stat["last_status"]
        if status == "success":
            status_str = "[green]success[/green]"
        elif status == "failed":
            status_str = "[red]failed[/red]"
        elif status == "timeout":
            status_str = "[yellow]timeout[/yellow]"
        else:
            status_str = f"[dim]{status or '-'}[/dim]"

        enabled_marker = "" if stat["enabled"] else " [dim](disabled)[/dim]"

        job_table.add_row(
            stat["name"] + enabled_marker,
            stat["schedule"],
            last_run_str,
            duration_str,
            status_str
        )

    console.print(job_table)

    # Recent failures
    if recent_failures:
        console.print("\n[bold red]Recent Failures[/bold red]")
        for failure in recent_failures[:3]:
            when = datetime.fromtimestamp(failure["last_run"]).strftime("%Y-%m-%d %H:%M") if failure["last_run"] else "unknown"
            console.print(f"\n[bold]{failure['name']}[/bold] - {failure['status']} at {when}")
            if failure["log_excerpt"]:
                console.print(Panel(
                    failure["log_excerpt"][:500],
                    title="Log excerpt",
                    border_style="red",
                    expand=False
                ))

    # Recommendations
    recommendations = []
    if summary["failures"] > 0:
        recommendations.append(f"Review {summary['failures']} failed job(s) with: scheduler logs <job-name>")
    if summary["timeouts"] > 0:
        recommendations.append(f"Consider increasing timeout for {summary['timeouts']} timed out job(s)")
    if summary["enabled_jobs"] < summary["total_jobs"]:
        recommendations.append(f"{summary['total_jobs'] - summary['enabled_jobs']} job(s) are disabled")
    if not daemon_running:
        recommendations.append("Scheduler daemon is not running. Start with: scheduler start")

    if recommendations:
        console.print("\n[bold yellow]Recommendations[/bold yellow]")
        for rec in recommendations:
            console.print(f"  - {rec}")

    console.print()


def print_report_plain(report_data: dict[str, Any]) -> None:
    """Print report in plain text."""
    summary = report_data["summary"]
    job_stats = report_data["jobs"]
    recent_failures = report_data["recent_failures"]

    print(f"\n=== Scheduler Report ({datetime.now().strftime('%Y-%m-%d %H:%M')}) ===\n")
    print(f"Jobs: {summary['total_jobs']} total, {summary['enabled_jobs']} enabled, {summary['jobs_with_runs']} have run")
    print(f"Success rate: {summary['success_rate']:.1f}%")
    print(f"Failures: {summary['failures']}, Timeouts: {summary['timeouts']}")
    print(f"Avg duration: {summary['avg_duration_seconds']:.1f}s")

    print("\n--- Jobs ---")
    for stat in job_stats[:10]:
        status = stat["last_status"] or "never-run"
        last_run = datetime.fromtimestamp(stat["last_run"]).strftime("%m-%d %H:%M") if stat["last_run"] else "never"
        print(f"  {stat['name']}: {status} (last: {last_run})")

    if recent_failures:
        print("\n--- Recent Failures ---")
        for f in recent_failures[:3]:
            print(f"  {f['name']}: {f['status']}")
