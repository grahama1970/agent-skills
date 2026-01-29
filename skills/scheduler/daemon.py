"""
Scheduler daemon - background task scheduler using APScheduler.

Manages the scheduler lifecycle, job scheduling, and signal handling.
"""
import os
import signal
import sys
import time
from typing import Any, Optional, TYPE_CHECKING

from config import PID_FILE, DEFAULT_METRICS_PORT, set_start_time
from cron_parser import parse_interval
from executor import job_wrapper
from job_registry import load_jobs
from metrics_server import start_metrics_server
from utils import ensure_dirs, rprint, HAS_APSCHEDULER

if HAS_APSCHEDULER:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

if TYPE_CHECKING:
    from uvicorn import Server as UvicornServer


class SchedulerDaemon:
    """Background scheduler daemon with APScheduler integration."""

    def __init__(self) -> None:
        """Initialize the daemon."""
        self.scheduler: Optional[Any] = None
        self.running = False
        self.metrics_server: Optional["UvicornServer"] = None

    def start(self, metrics_port: int = DEFAULT_METRICS_PORT) -> None:
        """
        Start the scheduler daemon with metrics server.

        Args:
            metrics_port: Port for the metrics HTTP server.
        """
        set_start_time(time.time())

        if not HAS_APSCHEDULER:
            print("ERROR: APScheduler not installed. Run: pip install apscheduler")
            sys.exit(1)

        ensure_dirs()

        # Check if already running
        if PID_FILE.exists():
            try:
                pid = int(PID_FILE.read_text().strip())
            except ValueError:
                # Corrupt/stale PID file
                PID_FILE.unlink()
            else:
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
                try:
                    self._add_job(job)
                except Exception as e:
                    print(f"[scheduler] Failed to schedule {name}: {e}")

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

    def _add_job(self, job: dict[str, Any]) -> None:
        """
        Add a job to the scheduler.

        Args:
            job: Job dictionary with scheduling configuration.
        """
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

    def _shutdown(self, signum: int, frame: Any) -> None:
        """
        Handle shutdown signal.

        Args:
            signum: Signal number.
            frame: Current stack frame.
        """
        print("\n[scheduler] Shutting down...")
        self.running = False

    def _cleanup(self) -> None:
        """Cleanup on exit."""
        if self.scheduler:
            self.scheduler.shutdown(wait=False)
        if PID_FILE.exists():
            PID_FILE.unlink()
        print("[scheduler] Stopped")


def stop_daemon() -> bool:
    """
    Stop a running scheduler daemon.

    Returns:
        True if daemon was stopped, False otherwise.
    """
    if not PID_FILE.exists():
        print("Scheduler not running")
        return False

    try:
        pid = int(PID_FILE.read_text().strip())
    except ValueError:
        print("Invalid PID file, removing")
        PID_FILE.unlink()
        return False
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
                return True
        print("Scheduler did not stop gracefully")
        return False
    except OSError as e:
        print(f"Error stopping scheduler: {e}")
        if PID_FILE.exists():
            PID_FILE.unlink()
        return False
