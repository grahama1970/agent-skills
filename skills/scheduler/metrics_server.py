"""
Metrics server - FastAPI-based metrics and status endpoints.

Provides Prometheus-compatible metrics and REST API for job management.
"""
import os
import threading
import time
from typing import Any, Optional, TYPE_CHECKING

from config import (
    LOG_DIR,
    PORT_FILE,
    DEFAULT_METRICS_PORT,
    RUNNING_JOBS,
    METRICS_COUNTERS,
    get_start_time,
)
from job_registry import load_jobs
from utils import ensure_dirs, rprint, HAS_FASTAPI

if HAS_FASTAPI:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import PlainTextResponse
    import uvicorn

if TYPE_CHECKING:
    from fastapi import FastAPI as FastAPIApp
    from uvicorn import Server as UvicornServer


def create_metrics_app() -> Optional["FastAPIApp"]:
    """
    Create FastAPI app for metrics endpoint.

    Returns:
        FastAPI application instance, or None if FastAPI is unavailable.
    """
    if not HAS_FASTAPI:
        return None

    app = FastAPI(
        title="Pi Scheduler Metrics",
        description="Metrics and status endpoint for the Pi scheduler daemon",
        version="1.0.0",
    )

    @app.get("/")
    def root() -> dict:
        """Root endpoint with links."""
        return {
            "service": "pi-scheduler",
            "endpoints": ["/status", "/jobs", "/jobs/{name}", "/jobs/{name}/logs", "/metrics"],
        }

    @app.get("/status")
    def status() -> dict:
        """Scheduler daemon status."""
        jobs = load_jobs()
        enabled = sum(1 for j in jobs.values() if j.get("enabled", True))
        start_time = get_start_time()
        return {
            "running": True,  # If this endpoint responds, daemon is running
            "pid": os.getpid(),
            "uptime": time.time() - start_time if start_time else 0,
            "jobs_total": len(jobs),
            "jobs_enabled": enabled,
            "jobs_running": len(RUNNING_JOBS),
            "metrics": METRICS_COUNTERS,
        }

    @app.get("/jobs")
    def list_jobs() -> dict:
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
    def get_job(name: str) -> dict:
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
    def get_job_logs(name: str, lines: int = 100) -> dict:
        """Get recent logs for a job."""
        lines = max(1, min(int(lines), 1000))
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
    def prometheus_metrics() -> str:
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
    def trigger_job(name: str) -> dict:
        """Trigger a job to run immediately (async)."""
        from executor import job_wrapper

        jobs = load_jobs()
        if name not in jobs:
            raise HTTPException(status_code=404, detail=f"Job not found: {name}")

        # Run in background thread
        thread = threading.Thread(target=job_wrapper, args=(name,))
        thread.start()

        return {"status": "triggered", "job": name}

    return app


def start_metrics_server(port: int = DEFAULT_METRICS_PORT) -> Optional["UvicornServer"]:
    """
    Start the metrics server in a background thread.

    Args:
        port: Port number to listen on.

    Returns:
        Uvicorn Server instance, or None if FastAPI is unavailable.
    """
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

    try:
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        rprint(f"[green][scheduler][/green] Metrics server started on port {port}")
        return server
    except Exception as e:
        rprint(f"[yellow][scheduler][/yellow] Failed to start metrics server: {e}")
        return None
