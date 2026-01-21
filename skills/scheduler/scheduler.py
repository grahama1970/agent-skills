#!/usr/bin/env python3
"""
Scheduler daemon for Pi and Claude Code.

A lightweight background task scheduler using APScheduler.
Stores jobs in JSON, logs execution, supports cron and interval triggers.
Features rich TUI output with progress indicators.
"""
import argparse
import json
import os
import signal
import subprocess
import sys
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

# Rich for TUI output
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
    from rich.live import Live
    from rich.text import Text
    from rich.style import Style
    HAS_RICH = True
    console = Console()
except ImportError:
    HAS_RICH = False
    console = None

# APScheduler for cron-like scheduling
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    HAS_APSCHEDULER = True
except ImportError:
    HAS_APSCHEDULER = False

# FastAPI for metrics server
try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import PlainTextResponse
    import uvicorn
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False


def rprint(*args, **kwargs):
    """Print with rich if available, else plain print."""
    if HAS_RICH and console:
        console.print(*args, **kwargs)
    else:
        print(*args, **kwargs)

# Data directory
DATA_DIR = Path(os.getenv("SCHEDULER_DATA_DIR", Path.home() / ".pi" / "scheduler"))
JOBS_FILE = DATA_DIR / "jobs.json"
PID_FILE = Path(os.getenv("SCHEDULER_PID_FILE", DATA_DIR / "scheduler.pid"))
PORT_FILE = DATA_DIR / ".port"
LOG_DIR = DATA_DIR / "logs"

# Default metrics server port
DEFAULT_METRICS_PORT = int(os.getenv("SCHEDULER_METRICS_PORT", "8610"))

# Global state for running jobs (for progress tracking)
RUNNING_JOBS: dict = {}  # {job_name: {"started": timestamp, "progress": str, "pid": int}}
METRICS_COUNTERS: dict = {
    "jobs_total": 0,
    "jobs_success": 0,
    "jobs_failed": 0,
    "jobs_timeout": 0,
}


def ensure_dirs():
    """Ensure data directories exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def load_jobs() -> dict:
    """Load jobs from JSON file."""
    if JOBS_FILE.exists():
        return json.loads(JOBS_FILE.read_text())
    return {}


def save_jobs(jobs: dict):
    """Save jobs to JSON file."""
    ensure_dirs()
    JOBS_FILE.write_text(json.dumps(jobs, indent=2))


def parse_interval(interval_str: str) -> dict:
    """Parse interval string like '1h', '30m', '10s' to APScheduler kwargs."""
    import re
    match = re.match(r'^(\d+)([smhd])$', interval_str.lower())
    if not match:
        raise ValueError(f"Invalid interval format: {interval_str}")

    value = int(match.group(1))
    unit = match.group(2)

    unit_map = {'s': 'seconds', 'm': 'minutes', 'h': 'hours', 'd': 'days'}
    return {unit_map[unit]: value}


def run_job(job: dict, show_progress: bool = True) -> dict:
    """Execute a job and return result with optional progress display."""
    name = job["name"]
    command = job["command"]
    workdir = job.get("workdir", str(Path.cwd()))

    log_file = LOG_DIR / f"{name}.log"
    start_time = datetime.now()

    # Rich progress context
    if show_progress and HAS_RICH:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(f"[cyan]Running {name}...", total=None)

            try:
                # Run with real-time output capture
                process = subprocess.Popen(
                    command,
                    shell=True,
                    cwd=workdir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )

                stdout_lines = []
                stderr_lines = []

                # Read output in real-time
                def read_stream(stream, lines_list):
                    for line in iter(stream.readline, ''):
                        lines_list.append(line)
                        progress.update(task, description=f"[cyan]{name}: {line.strip()[:50]}")

                stdout_thread = threading.Thread(target=read_stream, args=(process.stdout, stdout_lines))
                stderr_thread = threading.Thread(target=read_stream, args=(process.stderr, stderr_lines))
                stdout_thread.start()
                stderr_thread.start()

                # Wait for completion with timeout
                timeout = job.get("timeout", 3600)
                process.wait(timeout=timeout)
                stdout_thread.join()
                stderr_thread.join()

                stdout = ''.join(stdout_lines)
                stderr = ''.join(stderr_lines)
                returncode = process.returncode

                status = "success" if returncode == 0 else "failed"
                progress.update(task, description=f"[green]{name}: {status}" if status == "success" else f"[red]{name}: {status}")

            except subprocess.TimeoutExpired:
                process.kill()
                progress.update(task, description=f"[red]{name}: TIMEOUT")
                status = "timeout"
                returncode = -1
                stdout = ''.join(stdout_lines)
                stderr = ''.join(stderr_lines)

    else:
        # Simple execution without progress
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=job.get("timeout", 3600),
            )
            status = "success" if result.returncode == 0 else "failed"
            returncode = result.returncode
            stdout = result.stdout
            stderr = result.stderr
        except subprocess.TimeoutExpired:
            status = "timeout"
            returncode = -1
            stdout = ""
            stderr = ""

    # Log execution
    with open(log_file, "a") as f:
        f.write(f"\n{'='*60}\n")
        f.write(f"[{start_time.isoformat()}] Job: {name}\n")
        f.write(f"Command: {command}\n")
        f.write(f"Workdir: {workdir}\n")
        f.write(f"Status: {status} (exit {returncode})\n")
        f.write(f"Duration: {(datetime.now() - start_time).total_seconds():.1f}s\n")
        if stdout:
            f.write(f"\n--- stdout ---\n{stdout}\n")
        if stderr:
            f.write(f"\n--- stderr ---\n{stderr}\n")

    return {
        "status": status,
        "exit_code": returncode,
        "duration": (datetime.now() - start_time).total_seconds(),
    }


def job_wrapper(job_name: str):
    """Wrapper function for APScheduler to execute a job."""
    jobs = load_jobs()
    if job_name not in jobs:
        rprint(f"[yellow][scheduler][/yellow] Job not found: {job_name}")
        return

    job = jobs[job_name]
    if not job.get("enabled", True):
        rprint(f"[yellow][scheduler][/yellow] Job disabled: {job_name}")
        return

    rprint(f"[blue][scheduler][/blue] Running job: [bold]{job_name}[/bold]")
    result = run_job(job, show_progress=False)  # No progress in daemon mode

    # Update job metadata
    jobs[job_name]["last_run"] = int(time.time())
    jobs[job_name]["last_status"] = result["status"]
    save_jobs(jobs)

    status_color = "green" if result["status"] == "success" else "red"
    rprint(f"[blue][scheduler][/blue] Job {job_name} completed: [{status_color}]{result['status']}[/{status_color}]")


class SchedulerDaemon:
    """Background scheduler daemon."""

    def __init__(self):
        self.scheduler = None
        self.running = False

    def start(self):
        """Start the scheduler daemon."""
        if not HAS_APSCHEDULER:
            print("ERROR: APScheduler not installed. Run: pip install apscheduler")
            sys.exit(1)

        ensure_dirs()

        # Check if already running
        if PID_FILE.exists():
            pid = int(PID_FILE.read_text().strip())
            try:
                os.kill(pid, 0)  # Check if process exists
                print(f"Scheduler already running (PID {pid})")
                sys.exit(1)
            except OSError:
                PID_FILE.unlink()  # Stale PID file

        # Write PID
        PID_FILE.write_text(str(os.getpid()))

        # Setup scheduler
        self.scheduler = BackgroundScheduler()

        # Load and schedule all enabled jobs
        jobs = load_jobs()
        for name, job in jobs.items():
            if job.get("enabled", True):
                self._add_job(job)

        self.scheduler.start()
        self.running = True

        print(f"[scheduler] Started with {len(jobs)} jobs")

        # Handle shutdown
        signal.signal(signal.SIGTERM, self._shutdown)
        signal.signal(signal.SIGINT, self._shutdown)

        # Keep running
        try:
            while self.running:
                time.sleep(1)
        finally:
            self._cleanup()

    def _add_job(self, job: dict):
        """Add a job to the scheduler."""
        name = job["name"]

        if job.get("cron"):
            trigger = CronTrigger.from_crontab(job["cron"])
        elif job.get("interval"):
            trigger = IntervalTrigger(**parse_interval(job["interval"]))
        else:
            print(f"[scheduler] Job {name} has no trigger (cron or interval)")
            return

        self.scheduler.add_job(
            job_wrapper,
            trigger=trigger,
            args=[name],
            id=name,
            replace_existing=True,
        )
        print(f"[scheduler] Scheduled: {name}")

    def _shutdown(self, signum, frame):
        """Handle shutdown signal."""
        print("\n[scheduler] Shutting down...")
        self.running = False

    def _cleanup(self):
        """Cleanup on exit."""
        if self.scheduler:
            self.scheduler.shutdown(wait=False)
        if PID_FILE.exists():
            PID_FILE.unlink()
        print("[scheduler] Stopped")


def cmd_start(args):
    """Start the scheduler daemon."""
    daemon = SchedulerDaemon()
    daemon.start()


def cmd_stop(args):
    """Stop the scheduler daemon."""
    if not PID_FILE.exists():
        print("Scheduler not running")
        return

    pid = int(PID_FILE.read_text().strip())
    try:
        os.kill(pid, signal.SIGTERM)
        print(f"Sent SIGTERM to PID {pid}")
        # Wait for process to exit
        for _ in range(10):
            time.sleep(0.5)
            try:
                os.kill(pid, 0)
            except OSError:
                print("Scheduler stopped")
                return
        print("Scheduler did not stop gracefully")
    except OSError as e:
        print(f"Error stopping scheduler: {e}")
        if PID_FILE.exists():
            PID_FILE.unlink()


def cmd_status(args):
    """Show scheduler status with rich output."""
    running = False
    pid = None

    if PID_FILE.exists():
        pid = int(PID_FILE.read_text().strip())
        try:
            os.kill(pid, 0)
            running = True
        except OSError:
            PID_FILE.unlink()

    jobs = load_jobs()
    enabled = sum(1 for j in jobs.values() if j.get("enabled", True))

    if args.json:
        print(json.dumps({"running": running, "pid": pid, "jobs": len(jobs), "enabled": enabled}))
        return

    if HAS_RICH:
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


def cmd_register(args):
    """Register a new job."""
    jobs = load_jobs()

    if not args.cron and not args.interval:
        print("ERROR: Must specify --cron or --interval")
        sys.exit(1)

    job = {
        "name": args.name,
        "command": args.command,
        "enabled": args.enabled,
        "created_at": int(time.time()),
    }

    if args.cron:
        job["cron"] = args.cron
    if args.interval:
        job["interval"] = args.interval
    if args.workdir:
        job["workdir"] = args.workdir
    if args.description:
        job["description"] = args.description

    jobs[args.name] = job
    save_jobs(jobs)

    print(f"Registered job: {args.name}")
    if args.json:
        print(json.dumps(job, indent=2))


def cmd_unregister(args):
    """Remove a job."""
    jobs = load_jobs()

    if args.name not in jobs:
        print(f"Job not found: {args.name}")
        sys.exit(1)

    del jobs[args.name]
    save_jobs(jobs)
    print(f"Removed job: {args.name}")


def cmd_list(args):
    """List all jobs with rich table output."""
    jobs = load_jobs()

    if args.json:
        print(json.dumps(jobs, indent=2))
        return

    if not jobs:
        rprint("[yellow]No jobs registered[/yellow]")
        return

    if HAS_RICH:
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


def cmd_run(args):
    """Run a job immediately."""
    jobs = load_jobs()

    if args.name not in jobs:
        print(f"Job not found: {args.name}")
        sys.exit(1)

    job = jobs[args.name]
    print(f"Running job: {args.name}")
    result = run_job(job)

    # Update metadata
    jobs[args.name]["last_run"] = int(time.time())
    jobs[args.name]["last_status"] = result["status"]
    save_jobs(jobs)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Result: {result['status']}")


def cmd_enable(args):
    """Enable a job."""
    jobs = load_jobs()
    if args.name not in jobs:
        print(f"Job not found: {args.name}")
        sys.exit(1)

    jobs[args.name]["enabled"] = True
    save_jobs(jobs)
    print(f"Enabled: {args.name}")


def cmd_disable(args):
    """Disable a job."""
    jobs = load_jobs()
    if args.name not in jobs:
        print(f"Job not found: {args.name}")
        sys.exit(1)

    jobs[args.name]["enabled"] = False
    save_jobs(jobs)
    print(f"Disabled: {args.name}")


def cmd_logs(args):
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


def cmd_systemd_unit(args):
    """Generate systemd unit file."""
    script_path = Path(__file__).resolve()
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


def main():
    parser = argparse.ArgumentParser(description="Background task scheduler")
    parser.add_argument("--json", action="store_true", help="JSON output")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # start
    subparsers.add_parser("start", help="Start scheduler daemon")

    # stop
    subparsers.add_parser("stop", help="Stop scheduler daemon")

    # status
    p = subparsers.add_parser("status", help="Show scheduler status")
    p.add_argument("--json", action="store_true")

    # register
    p = subparsers.add_parser("register", help="Register a job")
    p.add_argument("--name", required=True, help="Job name")
    p.add_argument("--command", required=True, help="Command to run")
    p.add_argument("--cron", help="Cron expression")
    p.add_argument("--interval", help="Interval (e.g., 1h, 30m)")
    p.add_argument("--workdir", help="Working directory")
    p.add_argument("--description", help="Job description")
    p.add_argument("--enabled", type=bool, default=True)
    p.add_argument("--json", action="store_true")

    # unregister
    p = subparsers.add_parser("unregister", help="Remove a job")
    p.add_argument("name", help="Job name")

    # list
    p = subparsers.add_parser("list", help="List jobs")
    p.add_argument("--json", action="store_true")

    # run
    p = subparsers.add_parser("run", help="Run a job now")
    p.add_argument("name", help="Job name")
    p.add_argument("--json", action="store_true")

    # enable/disable
    p = subparsers.add_parser("enable", help="Enable a job")
    p.add_argument("name", help="Job name")

    p = subparsers.add_parser("disable", help="Disable a job")
    p.add_argument("name", help="Job name")

    # logs
    p = subparsers.add_parser("logs", help="Show job logs")
    p.add_argument("name", nargs="?", help="Job name (or list all)")
    p.add_argument("--lines", "-n", type=int, default=50)

    # systemd-unit
    subparsers.add_parser("systemd-unit", help="Generate systemd unit file")

    args = parser.parse_args()

    cmd_map = {
        "start": cmd_start,
        "stop": cmd_stop,
        "status": cmd_status,
        "register": cmd_register,
        "unregister": cmd_unregister,
        "list": cmd_list,
        "run": cmd_run,
        "enable": cmd_enable,
        "disable": cmd_disable,
        "logs": cmd_logs,
        "systemd-unit": cmd_systemd_unit,
    }

    cmd_map[args.subcommand](args)


if __name__ == "__main__":
    main()
