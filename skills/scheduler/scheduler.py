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

# YAML for service configuration
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


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
    global RUNNING_JOBS, METRICS_COUNTERS

    jobs = load_jobs()
    if job_name not in jobs:
        rprint(f"[yellow][scheduler][/yellow] Job not found: {job_name}")
        return

    job = jobs[job_name]
    if not job.get("enabled", True):
        rprint(f"[yellow][scheduler][/yellow] Job disabled: {job_name}")
        return

    # Track running job
    RUNNING_JOBS[job_name] = {
        "started": time.time(),
        "progress": "starting",
        "command": job["command"],
    }
    METRICS_COUNTERS["jobs_total"] += 1

    rprint(f"[blue][scheduler][/blue] Running job: [bold]{job_name}[/bold]")
    result = run_job(job, show_progress=False)  # No progress in daemon mode

    # Update metrics
    if result["status"] == "success":
        METRICS_COUNTERS["jobs_success"] += 1
    elif result["status"] == "timeout":
        METRICS_COUNTERS["jobs_timeout"] += 1
    else:
        METRICS_COUNTERS["jobs_failed"] += 1

    # Remove from running jobs
    RUNNING_JOBS.pop(job_name, None)

    # Update job metadata
    jobs[job_name]["last_run"] = int(time.time())
    jobs[job_name]["last_status"] = result["status"]
    jobs[job_name]["last_duration"] = result.get("duration", 0)
    save_jobs(jobs)

    status_color = "green" if result["status"] == "success" else "red"
    rprint(f"[blue][scheduler][/blue] Job {job_name} completed: [{status_color}]{result['status']}[/{status_color}]")


# ============================================================================
# Metrics Server (FastAPI)
# ============================================================================

def create_metrics_app():
    """Create FastAPI app for metrics endpoint."""
    if not HAS_FASTAPI:
        return None

    app = FastAPI(
        title="Pi Scheduler Metrics",
        description="Metrics and status endpoint for the Pi scheduler daemon",
        version="1.0.0",
    )

    @app.get("/")
    def root():
        """Root endpoint with links."""
        return {
            "service": "pi-scheduler",
            "endpoints": ["/status", "/jobs", "/jobs/{name}", "/jobs/{name}/logs", "/metrics"],
        }

    @app.get("/status")
    def status():
        """Scheduler daemon status."""
        jobs = load_jobs()
        enabled = sum(1 for j in jobs.values() if j.get("enabled", True))
        return {
            "running": True,  # If this endpoint responds, daemon is running
            "pid": os.getpid(),
            "uptime": time.time() - _start_time if "_start_time" in dir() else 0,
            "jobs_total": len(jobs),
            "jobs_enabled": enabled,
            "jobs_running": len(RUNNING_JOBS),
            "metrics": METRICS_COUNTERS,
        }

    @app.get("/jobs")
    def list_jobs():
        """List all jobs with status."""
        jobs = load_jobs()
        result = []
        for name, job in jobs.items():
            is_running = name in RUNNING_JOBS
            result.append({
                "name": name,
                "schedule": job.get("cron") or job.get("interval"),
                "enabled": job.get("enabled", True),
                "running": is_running,
                "last_run": job.get("last_run"),
                "last_status": job.get("last_status"),
                "last_duration": job.get("last_duration"),
                "command": job.get("command"),
                "workdir": job.get("workdir"),
            })
        return {"jobs": result, "count": len(result)}

    @app.get("/jobs/{name}")
    def get_job(name: str):
        """Get details for a specific job."""
        jobs = load_jobs()
        if name not in jobs:
            raise HTTPException(status_code=404, detail=f"Job not found: {name}")

        job = jobs[name]
        is_running = name in RUNNING_JOBS
        running_info = RUNNING_JOBS.get(name, {})

        return {
            **job,
            "running": is_running,
            "running_since": running_info.get("started"),
            "progress": running_info.get("progress"),
        }

    @app.get("/jobs/{name}/logs")
    def get_job_logs(name: str, lines: int = 100):
        """Get recent logs for a job."""
        log_file = LOG_DIR / f"{name}.log"
        if not log_file.exists():
            raise HTTPException(status_code=404, detail=f"No logs for job: {name}")

        with open(log_file) as f:
            all_lines = f.readlines()
            return {
                "job": name,
                "lines": lines,
                "total_lines": len(all_lines),
                "logs": "".join(all_lines[-lines:]),
            }

    @app.get("/metrics", response_class=PlainTextResponse)
    def prometheus_metrics():
        """Prometheus-compatible metrics endpoint."""
        jobs = load_jobs()
        enabled = sum(1 for j in jobs.values() if j.get("enabled", True))

        lines = [
            "# HELP scheduler_jobs_total Total number of registered jobs",
            "# TYPE scheduler_jobs_total gauge",
            f"scheduler_jobs_total {len(jobs)}",
            "",
            "# HELP scheduler_jobs_enabled Number of enabled jobs",
            "# TYPE scheduler_jobs_enabled gauge",
            f"scheduler_jobs_enabled {enabled}",
            "",
            "# HELP scheduler_jobs_running Number of currently running jobs",
            "# TYPE scheduler_jobs_running gauge",
            f"scheduler_jobs_running {len(RUNNING_JOBS)}",
            "",
            "# HELP scheduler_executions_total Total job executions",
            "# TYPE scheduler_executions_total counter",
            f"scheduler_executions_total {METRICS_COUNTERS['jobs_total']}",
            "",
            "# HELP scheduler_executions_success Successful job executions",
            "# TYPE scheduler_executions_success counter",
            f"scheduler_executions_success {METRICS_COUNTERS['jobs_success']}",
            "",
            "# HELP scheduler_executions_failed Failed job executions",
            "# TYPE scheduler_executions_failed counter",
            f"scheduler_executions_failed {METRICS_COUNTERS['jobs_failed']}",
            "",
            "# HELP scheduler_executions_timeout Timed out job executions",
            "# TYPE scheduler_executions_timeout counter",
            f"scheduler_executions_timeout {METRICS_COUNTERS['jobs_timeout']}",
        ]

        # Per-job metrics
        for name, job in jobs.items():
            last_run = job.get("last_run", 0)
            last_duration = job.get("last_duration", 0)
            last_success = 1 if job.get("last_status") == "success" else 0

            lines.extend([
                "",
                f"# HELP scheduler_job_last_run_timestamp Last run timestamp for {name}",
                f"# TYPE scheduler_job_last_run_timestamp gauge",
                f'scheduler_job_last_run_timestamp{{job="{name}"}} {last_run}',
                f'scheduler_job_last_duration_seconds{{job="{name}"}} {last_duration}',
                f'scheduler_job_last_success{{job="{name}"}} {last_success}',
            ])

        return "\n".join(lines) + "\n"

    @app.post("/jobs/{name}/run")
    def trigger_job(name: str):
        """Trigger a job to run immediately (async)."""
        jobs = load_jobs()
        if name not in jobs:
            raise HTTPException(status_code=404, detail=f"Job not found: {name}")

        # Run in background thread
        thread = threading.Thread(target=job_wrapper, args=(name,))
        thread.start()

        return {"status": "triggered", "job": name}

    return app


def start_metrics_server(port: int = DEFAULT_METRICS_PORT):
    """Start the metrics server in a background thread."""
    if not HAS_FASTAPI:
        rprint("[yellow][scheduler][/yellow] FastAPI not available, metrics server disabled")
        return None

    app = create_metrics_app()

    # Write port file for discovery
    ensure_dirs()
    PORT_FILE.write_text(str(port))

    # Run uvicorn in background thread
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    rprint(f"[green][scheduler][/green] Metrics server started on port {port}")
    return server


_start_time = time.time()  # Track daemon start time


class SchedulerDaemon:
    """Background scheduler daemon."""

    def __init__(self):
        self.scheduler = None
        self.running = False
        self.metrics_server = None

    def start(self, metrics_port: int = DEFAULT_METRICS_PORT):
        """Start the scheduler daemon with metrics server."""
        global _start_time
        _start_time = time.time()

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

        # Start metrics server
        self.metrics_server = start_metrics_server(metrics_port)

        # Setup scheduler
        self.scheduler = BackgroundScheduler()

        # Load and schedule all enabled jobs
        jobs = load_jobs()
        for name, job in jobs.items():
            if job.get("enabled", True):
                self._add_job(job)

        self.scheduler.start()
        self.running = True

        rprint(f"[green][scheduler][/green] Started with {len(jobs)} jobs")
        if self.metrics_server:
            rprint(f"[green][scheduler][/green] Metrics: http://localhost:{metrics_port}/")

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
    daemon.start(metrics_port=args.port)


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


def load_services_yaml(yaml_path: Path) -> dict:
    """Load services configuration from YAML file."""
    if not HAS_YAML:
        raise RuntimeError("PyYAML not installed. Run: pip install pyyaml")

    if not yaml_path.exists():
        raise FileNotFoundError(f"Services file not found: {yaml_path}")

    with open(yaml_path) as f:
        config = yaml.safe_load(f)

    return config


def cmd_load(args):
    """Load jobs from a services.yaml file."""
    yaml_path = Path(args.file)

    try:
        config = load_services_yaml(yaml_path)
    except Exception as e:
        rprint(f"[red]Error loading {yaml_path}:[/red] {e}")
        sys.exit(1)

    workdir = config.get("workdir", str(yaml_path.parent))
    jobs = load_jobs()
    loaded = 0
    skipped = 0

    # Process scheduled jobs
    scheduled = config.get("scheduled", {})
    for name, job_config in scheduled.items():
        if not job_config.get("enabled", True) and not args.include_disabled:
            rprint(f"[yellow]Skipping disabled job:[/yellow] {name}")
            skipped += 1
            continue

        job = {
            "name": name,
            "command": job_config["command"],
            "workdir": job_config.get("workdir", workdir),
            "enabled": job_config.get("enabled", True),
            "description": job_config.get("description", ""),
            "created_at": int(time.time()),
            "source": str(yaml_path),
        }

        # Schedule (cron or interval)
        if "schedule" in job_config:
            schedule = job_config["schedule"]
            # Detect if it's cron or interval
            if any(c in schedule for c in ["*", "/"]) or len(schedule.split()) >= 5:
                job["cron"] = schedule
            else:
                job["interval"] = schedule

        if "timeout" in job_config:
            job["timeout"] = job_config["timeout"]

        # Environment variables
        if "env" in job_config:
            job["env"] = job_config["env"]

        # Dependencies (informational)
        if "depends_on" in job_config:
            job["depends_on"] = job_config["depends_on"]

        jobs[name] = job
        loaded += 1
        rprint(f"[green]Loaded:[/green] {name} ({job.get('cron') or job.get('interval', 'no schedule')})")

    # Process hook-triggered jobs (store but don't schedule)
    hooks = config.get("hooks", {})
    for name, hook_config in hooks.items():
        if not hook_config.get("enabled", True) and not args.include_disabled:
            rprint(f"[yellow]Skipping disabled hook:[/yellow] {name}")
            skipped += 1
            continue

        job = {
            "name": name,
            "command": hook_config["command"],
            "workdir": hook_config.get("workdir", workdir),
            "enabled": hook_config.get("enabled", True),
            "description": hook_config.get("description", ""),
            "trigger": hook_config.get("trigger", "on-demand"),
            "created_at": int(time.time()),
            "source": str(yaml_path),
            "is_hook": True,  # Mark as hook, not scheduled
        }

        if "timeout" in hook_config:
            job["timeout"] = hook_config["timeout"]

        if "depends_on" in hook_config:
            job["depends_on"] = hook_config["depends_on"]

        jobs[name] = job
        loaded += 1
        rprint(f"[green]Loaded hook:[/green] {name} (trigger: {job.get('trigger')})")

    save_jobs(jobs)

    if HAS_RICH:
        from rich.panel import Panel
        summary = f"[bold]Loaded:[/bold] {loaded} jobs\n[bold]Skipped:[/bold] {skipped} disabled\n[bold]Source:[/bold] {yaml_path}"
        console.print(Panel(summary, title="Services Loaded", border_style="green"))
    else:
        print(f"\nLoaded {loaded} jobs, skipped {skipped} disabled")
        print(f"Source: {yaml_path}")


def main():
    parser = argparse.ArgumentParser(description="Background task scheduler")
    parser.add_argument("--json", action="store_true", help="JSON output")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # start
    p = subparsers.add_parser("start", help="Start scheduler daemon")
    p.add_argument("--port", type=int, default=DEFAULT_METRICS_PORT, help=f"Metrics server port (default: {DEFAULT_METRICS_PORT})")

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

    # load (from YAML)
    p = subparsers.add_parser("load", help="Load jobs from services.yaml")
    p.add_argument("file", help="Path to services.yaml file")
    p.add_argument("--include-disabled", action="store_true", help="Also load disabled jobs")

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
        "load": cmd_load,
    }

    cmd_map[args.subcommand](args)


if __name__ == "__main__":
    main()
