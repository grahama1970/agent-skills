"""Task Monitor Integration for create-score.

Provides:
- ScoreMonitor: Task-monitor compatible progress tracker
- Auto-registration with task-monitor registry
- Progress updates during generation
- Error state reporting

Integrates with ~/.pi/task-monitor/ for centralized monitoring.

Usage:
    from create_score.task_monitor import ScoreMonitor, start_generation, get_monitor

    # Automatic (recommended)
    monitor = start_generation(prompt="epic battle theme", duration_s=30)
    # ... do generation ...
    monitor.update_progress(state="running", progress_pct=50)
    monitor.finish(success=True, output_path=Path("output.wav"))

    # Or use context manager
    with ScoreMonitor(prompt="battle", duration_s=30) as monitor:
        # ... generation happens here ...
        monitor.update_progress(state="generating")
"""

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

# Task monitor paths
TASK_MONITOR_REGISTRY = Path.home() / ".pi" / "task-monitor" / "registry.json"
TASK_MONITOR_API_URL = os.environ.get("TASK_MONITOR_API", "http://localhost:8765")


@dataclass
class GenerationJob:
    """Represents a single generation job for tracking."""

    job_id: str
    prompt: str
    duration_s: float
    seed: int
    state: str = "queued"  # queued, generating, done, error
    progress_pct: float = 0.0
    error_msg: Optional[str] = None
    output_path: Optional[Path] = None
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None


class ScoreMonitor:
    """Task-monitor compatible progress tracker for create-score generations.

    Tracks:
    - Generation jobs (queued, generating, done, error)
    - Progress percentage during inference
    - Timing information
    - Error states

    Pushes updates to task-monitor state file or API.
    """

    def __init__(
        self,
        prompt: str,
        duration_s: float,
        name: str = "create-score",
        state_file: Optional[str] = None,
        api_url: Optional[str] = None,
        register: bool = True,
    ):
        self.prompt = prompt[:60]
        self.duration_s = duration_s
        self.name = name
        self.api_url = api_url or (
            TASK_MONITOR_API_URL if os.environ.get("TASK_MONITOR_API") else None
        )

        # State file path
        if state_file:
            self.state_file = Path(state_file).resolve()
        else:
            # Default to skill directory
            self.state_file = Path(__file__).parent.parent / "score_task_state.json"

        # Job tracking
        self.jobs: Dict[str, GenerationJob] = {}
        self.current_job_id: Optional[str] = None

        # Aggregate stats
        self.total_jobs = 0
        self.completed_jobs = 0
        self.failed_jobs = 0

        # Timing
        self.start_time = time.time()
        self.last_update = 0.0

        # Errors
        self.errors: List[Dict[str, Any]] = []

        # Auto-register with task-monitor
        if register:
            self._register_task()

        # Initial state write
        self._update_state()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - finish monitoring."""
        if exc_type is not None:
            self.finish(success=False)
        else:
            self.finish(success=True)
        return False

    def _register_task(self):
        """Register this task with task-monitor registry."""
        try:
            TASK_MONITOR_REGISTRY.parent.mkdir(parents=True, exist_ok=True)

            # Load existing registry
            registry = {}
            if TASK_MONITOR_REGISTRY.exists():
                try:
                    registry = json.loads(TASK_MONITOR_REGISTRY.read_text())
                except Exception:
                    registry = {}

            # Add/update our task
            registry[self.name] = {
                "state_file": str(self.state_file),
                "total": 1,  # Will be updated per-job
                "description": f"Score: {self.prompt}",
                "project": "create-score",
                "registered_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }

            # Write atomically
            tmp = TASK_MONITOR_REGISTRY.with_suffix(".tmp")
            tmp.write_text(json.dumps(registry, indent=2))
            os.replace(tmp, TASK_MONITOR_REGISTRY)
            logger.debug("Registered with task-monitor")
        except Exception as e:
            logger.debug("Failed to register with task-monitor: {}", e)

    def _update_state(self, final: bool = False):
        """Update task-monitor state file."""
        now = time.time()

        # Throttle updates (max every 0.5s unless final)
        if not final and (now - self.last_update) < 0.5:
            return
        self.last_update = now

        elapsed = now - self.start_time

        # Current job info
        current_job = self.jobs.get(self.current_job_id) if self.current_job_id else None

        state = {
            "completed": self.completed_jobs,
            "total": self.total_jobs or 1,
            "description": f"Score: {self.prompt}",
            "current_item": current_job.state if current_job else "idle",
            "stats": {
                "completed": self.completed_jobs,
                "failed": self.failed_jobs,
                "queued": self.total_jobs - self.completed_jobs - self.failed_jobs,
            },
            "current_job": {
                "job_id": current_job.job_id if current_job else None,
                "state": current_job.state if current_job else None,
                "progress_pct": current_job.progress_pct if current_job else 0,
                "prompt": current_job.prompt[:40] if current_job else None,
                "duration_s": current_job.duration_s if current_job else None,
            }
            if current_job
            else None,
            "errors": self.errors[-5:],  # Last 5 errors
            "elapsed_seconds": round(elapsed, 1),
            "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": "completed" if final else "running",
        }

        # Write to file
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(state, indent=2))
            os.replace(tmp, self.state_file)
        except Exception as e:
            logger.debug("Failed to write state file: {}", e)

        # Push to API if configured
        if self.api_url:
            try:
                import httpx

                with httpx.Client(timeout=1.0) as client:
                    client.post(
                        f"{self.api_url}/tasks/{self.name}/state",
                        json=state,
                    )
            except Exception as e:
                logger.debug("create-score task monitor publish failed: {}", e)

    def start_job(self, job_id: str, seed: int = -1) -> GenerationJob:
        """Start tracking a new generation job."""
        job = GenerationJob(
            job_id=job_id,
            prompt=self.prompt,
            duration_s=self.duration_s,
            seed=seed,
            state="queued",
        )
        self.jobs[job_id] = job
        self.current_job_id = job_id
        self.total_jobs += 1
        self._update_state()
        logger.debug("Started job tracking: {}", job_id)
        return job

    def update_progress(
        self,
        job_id: Optional[str] = None,
        state: Optional[str] = None,
        progress_pct: Optional[float] = None,
    ):
        """Update progress for a job."""
        jid = job_id or self.current_job_id
        if not jid or jid not in self.jobs:
            return

        job = self.jobs[jid]
        if state:
            job.state = state
        if progress_pct is not None:
            job.progress_pct = progress_pct

        self._update_state()

    def complete_job(
        self,
        job_id: Optional[str] = None,
        output_path: Optional[Path] = None,
    ):
        """Mark a job as complete."""
        jid = job_id or self.current_job_id
        if not jid or jid not in self.jobs:
            return

        job = self.jobs[jid]
        job.state = "done"
        job.progress_pct = 100.0
        job.end_time = time.time()
        job.output_path = output_path

        self.completed_jobs += 1
        self._update_state()
        logger.debug("Job completed: {}", jid)

    def fail_job(
        self,
        job_id: Optional[str] = None,
        error_msg: str = "Unknown error",
    ):
        """Mark a job as failed."""
        jid = job_id or self.current_job_id
        if not jid or jid not in self.jobs:
            return

        job = self.jobs[jid]
        job.state = "error"
        job.end_time = time.time()
        job.error_msg = error_msg

        self.failed_jobs += 1
        self.errors.append(
            {
                "job_id": jid,
                "message": error_msg,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        self._update_state()
        logger.debug("Job failed: {} - {}", jid, error_msg)

    def finish(self, success: bool = True):
        """Mark monitoring as complete."""
        self._update_state(final=True)

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary for logging/reporting."""
        elapsed = time.time() - self.start_time
        return {
            "prompt": self.prompt,
            "duration_s": self.duration_s,
            "elapsed_seconds": round(elapsed, 1),
            "jobs": {
                "total": self.total_jobs,
                "completed": self.completed_jobs,
                "failed": self.failed_jobs,
            },
            "errors": len(self.errors),
        }


# Global monitor instance for current generation
_current_monitor: Optional[ScoreMonitor] = None


def start_generation(
    prompt: str,
    duration_s: float,
    name: str = "create-score",
) -> ScoreMonitor:
    """Start monitoring a new score generation."""
    global _current_monitor
    _current_monitor = ScoreMonitor(prompt=prompt, duration_s=duration_s, name=name)
    return _current_monitor


def get_monitor() -> Optional[ScoreMonitor]:
    """Get the current generation monitor."""
    return _current_monitor


def end_generation(success: bool = True):
    """End the current generation monitoring."""
    global _current_monitor
    if _current_monitor:
        _current_monitor.finish(success)
        _current_monitor = None
