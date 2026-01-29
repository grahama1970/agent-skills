"""
CLI command handlers for the scheduler.

Each function implements a subcommand of the scheduler CLI.
"""
import json
import sys
from argparse import Namespace
from datetime import datetime
from pathlib import Path

from config import LOG_DIR
from daemon import SchedulerDaemon, stop_daemon
from executor import run_job
from job_registry import (
    load_jobs,
    register_job,
    unregister_job,
    set_job_enabled,
    update_job_run_status,
    import_from_yaml,
)
from report import generate_report_data, print_report_json, print_report_rich, print_report_plain
from utils import (
    rprint,
    is_daemon_running,
    get_daemon_pid,
    HAS_RICH,
    console,
)

# Conditional imports for rich components
if HAS_RICH:
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text


def cmd_start(args: Namespace) -> None:
    """Start the scheduler daemon."""
    daemon = SchedulerDaemon()
    daemon.start(metrics_port=args.port)


def cmd_stop(args: Namespace) -> None:
    """Stop the scheduler daemon."""
    stop_daemon()


def cmd_status(args: Namespace) -> None:
    """Show scheduler status with rich output."""
    running = is_daemon_running()
    pid = get_daemon_pid()

    jobs = load_jobs()
    enabled = sum(1 for j in jobs.values() if j.get("enabled", True))

    if args.json:
        print(json.dumps({"running": running, "pid": pid, "jobs": len(jobs), "enabled": enabled}))
        return

    if HAS_RICH and console:
        # Status panel
        if running:
            status_text = Text()
            status_text.append("RUNNING", style="bold green")
            status_text.append(f" (PID {pid})", style="dim")
        else:
            status_text = Text("STOPPED", style="bold red")

        panel = Panel(
            status_text,
            title="Scheduler Status",
            border_style="green" if running else "red"
        )
        console.print(panel)

        # Jobs summary
        rprint(f"\n[bold]Jobs:[/bold] {len(jobs)} total, [green]{enabled}[/green] enabled")

        # Show next scheduled runs if jobs exist
        if jobs and running:
            rprint("\n[bold]Upcoming runs:[/bold]")
            for name, job in list(jobs.items())[:5]:
                if job.get("enabled", True):
                    schedule = job.get("cron") or job.get("interval", "?")
                    rprint(f"  [cyan]{name}[/cyan]: {schedule}")
    else:
        if running:
            print(f"Scheduler running (PID {pid})")
        else:
            print("Scheduler not running")
        print(f"\nJobs: {len(jobs)} total, {enabled} enabled")


def cmd_register(args: Namespace) -> None:
    """Register a new job."""
    if not args.cron and not args.interval:
        print("ERROR: Must specify --cron or --interval")
        sys.exit(1)

    try:
        job = register_job(
            name=args.name,
            command=args.command,
            cron=args.cron,
            interval=args.interval,
            workdir=args.workdir,
            description=args.description,
            enabled=args.enabled,
        )
        print(f"Registered job: {args.name}")
        if args.json:
            print(json.dumps(job, indent=2))
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)


def cmd_unregister(args: Namespace) -> None:
    """Remove a job."""
    if not unregister_job(args.name):
        print(f"Job not found: {args.name}")
        sys.exit(1)
    print(f"Removed job: {args.name}")


def cmd_list(args: Namespace) -> None:
    """List all jobs with rich table output."""
    jobs = load_jobs()

    if args.json:
        print(json.dumps(jobs, indent=2))
        return

    if not jobs:
        rprint("[yellow]No jobs registered[/yellow]")
        return

    if HAS_RICH and console:
        table = Table(title="Scheduled Jobs", show_header=True, header_style="bold cyan")
        table.add_column("Name", style="bold")
        table.add_column("Schedule")
        table.add_column("Status")
        table.add_column("Last Run")
        table.add_column("Last Status")
        table.add_column("Command", max_width=40)

        for name, job in jobs.items():
            enabled = job.get("enabled", True)
            status_str = "[green]enabled[/green]" if enabled else "[red]DISABLED[/red]"
            schedule = job.get("cron") or job.get("interval", "?")
            last_run = job.get("last_run")
            last_status = job.get("last_status", "-")

            if last_run:
                last_run_str = datetime.fromtimestamp(last_run).strftime("%m-%d %H:%M")
            else:
                last_run_str = "[dim]never[/dim]"

            # Color last status
            if last_status == "success":
                last_status_str = "[green]success[/green]"
            elif last_status == "failed":
                last_status_str = "[red]failed[/red]"
            elif last_status == "timeout":
                last_status_str = "[yellow]timeout[/yellow]"
            else:
                last_status_str = f"[dim]{last_status}[/dim]"

            cmd_short = job['command'][:37] + "..." if len(job['command']) > 40 else job['command']

            table.add_row(name, schedule, status_str, last_run_str, last_status_str, cmd_short)

        console.print(table)
    else:
        # Fallback plain text
        for name, job in jobs.items():
            status = "enabled" if job.get("enabled", True) else "DISABLED"
            schedule = job.get("cron") or job.get("interval", "?")
            last_run = job.get("last_run")
            last_status = job.get("last_status", "-")

            if last_run:
                last_run_str = datetime.fromtimestamp(last_run).strftime("%Y-%m-%d %H:%M")
            else:
                last_run_str = "never"

            print(f"{name}")
            print(f"  Schedule: {schedule}")
            print(f"  Status: {status}")
            print(f"  Last run: {last_run_str} ({last_status})")
            print(f"  Command: {job['command'][:60]}...")
            print()


def cmd_run(args: Namespace) -> None:
    """Run a job immediately."""
    jobs = load_jobs()

    if args.name not in jobs:
        print(f"Job not found: {args.name}")
        sys.exit(1)

    job = jobs[args.name]
    print(f"Running job: {args.name}")
    result = run_job(job)

    # Update metadata
    update_job_run_status(args.name, result["status"], result.get("duration"))

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Result: {result['status']}")


def cmd_enable(args: Namespace) -> None:
    """Enable a job."""
    if not set_job_enabled(args.name, True):
        print(f"Job not found: {args.name}")
        sys.exit(1)
    print(f"Enabled: {args.name}")


def cmd_disable(args: Namespace) -> None:
    """Disable a job."""
    if not set_job_enabled(args.name, False):
        print(f"Job not found: {args.name}")
        sys.exit(1)
    print(f"Disabled: {args.name}")


def cmd_logs(args: Namespace) -> None:
    """Show job logs."""
    if args.name:
        log_file = LOG_DIR / f"{args.name}.log"
        if not log_file.exists():
            print(f"No logs for: {args.name}")
            return

        lines = args.lines or 50
        # Read last N lines
        with open(log_file) as f:
            all_lines = f.readlines()
            for line in all_lines[-lines:]:
                print(line, end="")
    else:
        # List all log files
        for log_file in sorted(LOG_DIR.glob("*.log")):
            size = log_file.stat().st_size
            mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
            print(f"{log_file.stem}: {size} bytes, modified {mtime}")


def cmd_systemd_unit(args: Namespace) -> None:
    """Generate systemd unit file."""
    script_path = Path(__file__).resolve().parent / "scheduler.py"
    python_path = sys.executable

    unit = f"""[Unit]
Description=Pi Scheduler Daemon
After=network.target

[Service]
Type=simple
ExecStart={python_path} {script_path} start
ExecStop={python_path} {script_path} stop
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
"""
    print(unit)


def cmd_load(args: Namespace) -> None:
    """Load jobs from a services.yaml file."""
    yaml_path = Path(args.file)

    try:
        loaded, skipped = import_from_yaml(yaml_path, args.include_disabled)
    except Exception as e:
        rprint(f"[red]Error loading {yaml_path}:[/red] {e}")
        sys.exit(1)

    if HAS_RICH and console:
        summary = f"[bold]Loaded:[/bold] {loaded} jobs\n[bold]Skipped:[/bold] {skipped} disabled\n[bold]Source:[/bold] {yaml_path}"
        console.print(Panel(summary, title="Services Loaded", border_style="green"))
    else:
        print(f"\nLoaded {loaded} jobs, skipped {skipped} disabled")
        print(f"Source: {yaml_path}")


def cmd_report(args: Namespace) -> None:
    """Generate comprehensive status report with metrics and failures."""
    report_data = generate_report_data()

    if args.json:
        print_report_json(report_data)
    elif HAS_RICH and console:
        print_report_rich(report_data)
    else:
        print_report_plain(report_data)
