"""
Task-monitor integration for /ask learn sessions.

Provides the AskMonitor class for progress tracking, sub-step tracking,
ETA estimation, and task-monitor API integration.
"""

import json
import os
import time
from typing import Optional

from loguru import logger as log

# Task-monitor paths
from pathlib import Path

TASK_MONITOR_DIR = Path.home() / ".pi" / "task-monitor"
TASK_MONITOR_REGISTRY = TASK_MONITOR_DIR / "registry.json"
STATE_FILE = Path(__file__).parent / "ask_task_state.json"


# Estimated durations per step (in seconds) for each depth level
STEP_ESTIMATES = {
    "quick": {
        "memory_check": 5,
        "dogpile": 120,  # 2 min parallel searches
        "download_books": 5,  # Skip for quick
        "ingest_youtube": 60,  # 3 videos * 20s each
        "fetch_web": 30,  # 3 pages
        "extractor_qra": 60,  # Fast mode
        "store": 10,
    },
    "standard": {
        "memory_check": 5,
        "dogpile": 300,  # 5 min with deep dives
        "download_books": 60,  # Check existing, maybe 1 download
        "ingest_youtube": 150,  # 5 videos
        "fetch_web": 100,  # 5 pages
        "extractor_qra": 180,  # 3 min
        "store": 30,
    },
    "deep": {
        "memory_check": 10,
        "dogpile": 600,  # 10 min full research
        "download_books": 900,  # 15 min for 3-5 book downloads via SABnzbd
        "ingest_youtube": 600,  # 10+ videos, some with whisper fallback
        "fetch_web": 300,  # 10+ pages
        "extractor_qra": 600,  # 10 min heavy processing
        "store": 60,
    },
}


class AskMonitor:
    """Task-monitor compatible progress tracker for /ask learn sessions.

    Enhanced for multi-hour deep learning jobs:
    - Sub-step progress (items within each major step)
    - Heartbeat mechanism for long operations
    - Estimated time remaining based on depth
    - API push to task-monitor server
    - File-based state for resilience
    """

    STEPS = [
        "memory_check",
        "dogpile",
        "download_books",  # New: actual book download via ops-nzbgeek
        "ingest_youtube",
        "fetch_web",
        "extractor_qra",
        "store",
    ]

    def __init__(
        self,
        topic: str,
        scope: str,
        name: str = "ask-learn",
        api_url: Optional[str] = None,
        register: bool = True,
        depth: str = "quick",
    ):
        self.topic = topic
        self.scope = scope
        self.name = name
        self.api_url = api_url or os.environ.get("TASK_MONITOR_URL")
        self.state_file = STATE_FILE
        self.start_time = time.time()
        self.depth = depth

        # Progress tracking
        self.current_step = ""
        self.completed_steps = 0
        self.total_steps = len(self.STEPS)
        self.step_status: dict[str, str] = {s: "pending" for s in self.STEPS}
        self.step_times: dict[str, float] = {}
        self.errors: list[dict] = []
        self.stats: dict[str, int] = {
            "books_discovered": 0,
            "youtube_ingested": 0,
            "qra_extracted": 0,
            "items_stored": 0,
            "web_fetched": 0,
        }

        # Sub-step tracking (for items within a step)
        self.substep_current = 0
        self.substep_total = 0
        self.substep_label = ""
        self._last_heartbeat = time.time()
        self._heartbeat_interval = 10  # seconds

        # Estimated times based on depth
        self._step_estimates = STEP_ESTIMATES.get(depth, STEP_ESTIMATES["quick"])

        if register:
            self._register_task()
        self._update_state()

    def _register_task(self):
        """Register with ~/.pi/task-monitor/registry.json."""
        try:
            TASK_MONITOR_DIR.mkdir(parents=True, exist_ok=True)
            registry = {"tasks": {}}
            if TASK_MONITOR_REGISTRY.exists():
                try:
                    registry = json.loads(TASK_MONITOR_REGISTRY.read_text())
                except (json.JSONDecodeError, OSError):
                    pass

            # Calculate estimated total time
            total_estimate = sum(self._step_estimates.values())
            eta_display = f"~{total_estimate // 60} min" if total_estimate < 3600 else f"~{total_estimate / 3600:.1f} hours"

            # Depth indicator
            depth_label = {"quick": "\u26a1", "standard": "\U0001f4da", "deep": "\U0001f52c"}.get(self.depth, "")

            registry.setdefault("tasks", {})[self.name] = {
                "name": self.name,
                "state_file": str(self.state_file),
                "total": self.total_steps,
                "description": f"{depth_label} Ask Learn: {self.topic}",
                "project": "ask",
                "registered_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "depth": self.depth,
                "scope": self.scope,
                "estimated_seconds": total_estimate,
                "eta_display": eta_display,
            }

            # Atomic write
            tmp = TASK_MONITOR_REGISTRY.with_suffix(".tmp")
            tmp.write_text(json.dumps(registry, indent=2))
            os.replace(tmp, TASK_MONITOR_REGISTRY)
            log.debug("Registered task '%s' with task-monitor (depth=%s, eta=%s)",
                      self.name, self.depth, eta_display)
        except Exception as e:
            log.error("Could not register with task-monitor: %s", e)

    def start_step(self, step: str):
        """Mark a step as running."""
        self.current_step = step
        self.step_status[step] = "running"
        self._step_start = time.time()
        self._update_state()
        log.debug("Step started: %s", step)

    def complete_step(self, step: str, success: bool = True):
        """Mark a step as done."""
        self.step_status[step] = "done" if success else "error"
        elapsed = time.time() - getattr(self, "_step_start", time.time())
        self.step_times[step] = round(elapsed, 1)
        self.completed_steps += 1
        self._update_state()
        log.debug("Step completed: %s (%.1fs, success=%s)", step, elapsed, success)

    def log_error(self, step: str, message: str):
        """Log an error for a step."""
        self.errors.append({
            "step": step,
            "message": message[:200],
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        log.warning("Monitor error [%s]: %s", step, message[:100])

    def update_stats(self, **kwargs):
        """Update stats counters."""
        self.stats.update(kwargs)
        self._update_state()

    def finish(self, success: bool = True):
        """Mark the task as complete."""
        self._update_state(final=True, success=success)
        log.info("Task '%s' finished: success=%s, elapsed=%.1fs",
                 self.name, success, time.time() - self.start_time)

    # -------------------------------------------------------------------------
    # Sub-step tracking for long operations
    # -------------------------------------------------------------------------

    def start_substeps(self, total: int, label: str = ""):
        """Start tracking sub-steps within the current major step.

        Args:
            total: Total number of items to process
            label: Description (e.g., "Processing YouTube videos")
        """
        self.substep_current = 0
        self.substep_total = total
        self.substep_label = label
        self._last_heartbeat = time.time()
        self._update_state()
        log.debug("Substeps started: %s (%d items)", label, total)

    def advance_substep(self, label: str = ""):
        """Advance to the next sub-step item.

        Args:
            label: Current item label (e.g., video URL)
        """
        self.substep_current += 1
        if label:
            self.substep_label = label
        self._heartbeat()
        log.debug("Substep %d/%d: %s", self.substep_current, self.substep_total, label[:50])

    def _heartbeat(self, force: bool = False):
        """Emit a heartbeat update if enough time has passed.

        For long-running operations, this ensures task-monitor TUI
        shows progress even when individual items take a while.
        """
        now = time.time()
        if force or (now - self._last_heartbeat) >= self._heartbeat_interval:
            self._last_heartbeat = now
            self._update_state()

    def get_eta_seconds(self) -> float:
        """Estimate seconds remaining based on depth and progress.

        Returns:
            Estimated seconds remaining (0 if unknown)
        """
        # Sum remaining step estimates
        remaining = 0.0
        for step in self.STEPS:
            if self.step_status[step] == "pending":
                remaining += self._step_estimates.get(step, 60)
            elif self.step_status[step] == "running":
                # Partially complete - estimate based on substep progress
                step_estimate = self._step_estimates.get(step, 60)
                if self.substep_total > 0 and self.substep_current > 0:
                    # Pro-rate based on substep progress
                    fraction_done = self.substep_current / self.substep_total
                    remaining += step_estimate * (1 - fraction_done)
                else:
                    # Assume halfway through
                    remaining += step_estimate * 0.5

        return remaining

    def get_eta_display(self) -> str:
        """Get human-readable ETA string.

        Returns:
            String like "~5 min remaining" or "~2 hours remaining"
        """
        seconds = self.get_eta_seconds()
        if seconds < 60:
            return f"~{int(seconds)}s remaining"
        elif seconds < 3600:
            return f"~{int(seconds / 60)} min remaining"
        else:
            hours = seconds / 3600
            return f"~{hours:.1f} hours remaining"

    def _update_state(self, final: bool = False, success: bool = True):
        """Write state file atomically + optional API push."""
        elapsed = time.time() - self.start_time

        # Calculate fine-grained progress including substeps
        base_progress = (self.completed_steps / self.total_steps * 100) if self.total_steps else 0
        substep_bonus = 0.0
        if self.substep_total > 0 and self.current_step:
            # Add fractional progress within current step
            step_weight = 100.0 / self.total_steps
            substep_bonus = (self.substep_current / self.substep_total) * step_weight
        progress_pct = min(100.0, base_progress + substep_bonus)

        # Get ETA
        eta_seconds = self.get_eta_seconds()
        eta_display = self.get_eta_display() if not final else ""

        state = {
            "completed": self.completed_steps,
            "total": self.total_steps,
            "description": f"Ask Learn: {self.topic}",
            "current_item": self.current_step,
            "current_detail": self.substep_label,
            "stats": self.stats,
            "step_status": self.step_status,
            "step_times": self.step_times,
            "errors": self.errors[-10:],
            "elapsed_seconds": round(elapsed, 1),
            "progress_pct": round(progress_pct, 1),
            "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": ("completed" if success else "failed") if final else "running",
            "scope": self.scope,
            "topic": self.topic,
            "depth": self.depth,
            # Sub-step tracking
            "substep_current": self.substep_current,
            "substep_total": self.substep_total,
            # ETA
            "eta_seconds": round(eta_seconds, 1),
            "eta_display": eta_display,
        }

        # Atomic write to state file
        try:
            tmp = self.state_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(state, indent=2))
            os.replace(tmp, self.state_file)
        except Exception as e:
            log.error("Could not write state file: %s", e)

        # Optional API push
        if self.api_url:
            try:
                import httpx as _httpx
                _httpx.post(
                    f"{self.api_url}/tasks/{self.name}/state",
                    json=state,
                    timeout=0.5,
                )
            except Exception as e:
                log.error("ask monitor state push failed: {}", e)
