"""
Job executor - handles job execution with progress tracking and logging.

Provides both interactive (with Rich progress) and background execution modes.
"""
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from config import LOG_DIR, RUNNING_JOBS, METRICS_COUNTERS, RUNNING_JOBS_LOCK, METRICS_LOCK
from job_registry import load_jobs, update_job_run_status
from utils import (
    ensure_dirs,
    rprint,
    HAS_RICH,
    console,
)

# Conditional import of rich progress components
if HAS_RICH:
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn


def run_job(job: dict[str, Any], show_progress: bool = True) -> dict[str, Any]:
    """
    Execute a job and return result with optional progress display.

    Args:
        job: Job dictionary with 'name', 'command', and optional 'workdir', 'timeout'.
        show_progress: Whether to show Rich progress indicator.

    Returns:
        Result dictionary with 'status', 'exit_code', and 'duration'.
    """
    name = job["name"]
    command = job["command"]
    workdir = job.get("workdir", str(Path.cwd()))
    timeout = job.get("timeout", 3600)

    ensure_dirs()
    log_file = LOG_DIR / f"{name}.log"
    start_time = datetime.now()

    # Rich progress context
    if show_progress and HAS_RICH and console:
        result = _run_with_progress(name, command, workdir, timeout, log_file, start_time)
    else:
        result = _run_simple(name, command, workdir, timeout, log_file, start_time)

    return result


def _run_with_progress(
    name: str,
    command: str,
    workdir: str,
    timeout: int,
    log_file: Path,
    start_time: datetime,
) -> dict[str, Any]:
    """Run a job with Rich progress display."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(f"[cyan]Running {name}...", total=None)

        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        process: subprocess.Popen | None = None
        stdout_thread: threading.Thread | None = None
        stderr_thread: threading.Thread | None = None

        try:
            process = subprocess.Popen(
                command,
                shell=True,
                cwd=workdir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            def read_stream(stream, lines_list):
                for line in iter(stream.readline, ''):
                    lines_list.append(line)
                    progress.update(task, description=f"[cyan]{name}: {line.strip()[:50]}")

            stdout_thread = threading.Thread(target=read_stream, args=(process.stdout, stdout_lines))
            stderr_thread = threading.Thread(target=read_stream, args=(process.stderr, stderr_lines))
            stdout_thread.start()
            stderr_thread.start()

            process.wait(timeout=timeout)

            stdout = ''.join(stdout_lines)
            stderr = ''.join(stderr_lines)
            returncode = process.returncode

            status = "success" if returncode == 0 else "failed"
            color = "green" if status == "success" else "red"
            progress.update(task, description=f"[{color}]{name}: {status}")

        except subprocess.TimeoutExpired:
            if process:
                process.kill()
            progress.update(task, description=f"[red]{name}: TIMEOUT")
            status = "timeout"
            returncode = -1
            stdout = ''.join(stdout_lines)
            stderr = ''.join(stderr_lines)
        except Exception as e:
            status = "failed"
            returncode = -1
            stdout = ''.join(stdout_lines)
            stderr = (''.join(stderr_lines) + f"\n{e}") if stderr_lines else str(e)
            progress.update(task, description=f"[red]{name}: failed")
        finally:
            for t in (stdout_thread, stderr_thread):
                if t and t.is_alive():
                    t.join(timeout=1)

    _write_log(log_file, name, command, workdir, status, returncode, start_time, stdout, stderr)

    return {
        "status": status,
        "exit_code": returncode,
        "duration": (datetime.now() - start_time).total_seconds(),
    }


def _run_simple(
    name: str,
    command: str,
    workdir: str,
    timeout: int,
    log_file: Path,
    start_time: datetime,
) -> dict[str, Any]:
    """Run a job without progress display (for daemon mode)."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=timeout,
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
    except Exception as e:
        status = "failed"
        returncode = -1
        stdout = ""
        stderr = str(e)

    _write_log(log_file, name, command, workdir, status, returncode, start_time, stdout, stderr)

    return {
        "status": status,
        "exit_code": returncode,
        "duration": (datetime.now() - start_time).total_seconds(),
    }


def _write_log(
    log_file: Path,
    name: str,
    command: str,
    workdir: str,
    status: str,
    returncode: int,
    start_time: datetime,
    stdout: str,
    stderr: str,
) -> None:
    """Write execution log to file."""
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


def job_wrapper(job_name: str) -> None:
    """
    Wrapper function for APScheduler to execute a job.

    This is the callback invoked by APScheduler when a job triggers.
    It handles job tracking, metrics, and status updates.

    Args:
        job_name: Name of the job to execute.
    """
    jobs = load_jobs()
    if job_name not in jobs:
        rprint(f"[yellow][scheduler][/yellow] Job not found: {job_name}")
        return

    job = jobs[job_name]
    if not job.get("enabled", True):
        rprint(f"[yellow][scheduler][/yellow] Job disabled: {job_name}")
        return

    # Track running job
    with RUNNING_JOBS_LOCK:
        RUNNING_JOBS[job_name] = {
            "started": time.time(),
            "progress": "starting",
            "command": job["command"],
        }
    with METRICS_LOCK:
        METRICS_COUNTERS["jobs_total"] += 1

    rprint(f"[blue][scheduler][/blue] Running job: [bold]{job_name}[/bold]")
    result = run_job(job, show_progress=False)  # No progress in daemon mode

    # Update metrics
    with METRICS_LOCK:
        if result["status"] == "success":
            METRICS_COUNTERS["jobs_success"] += 1
        elif result["status"] == "timeout":
            METRICS_COUNTERS["jobs_timeout"] += 1
        else:
            METRICS_COUNTERS["jobs_failed"] += 1

    # Remove from running jobs
    with RUNNING_JOBS_LOCK:
        RUNNING_JOBS.pop(job_name, None)

    # Update job metadata
    update_job_run_status(job_name, result["status"], result.get("duration"))

    status_color = "green" if result["status"] == "success" else "red"
    rprint(f"[blue][scheduler][/blue] Job {job_name} completed: [{status_color}]{result['status']}[/{status_color}]")
