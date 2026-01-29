#!/usr/bin/env python3
"""
Task-monitor integration for security-scan.

Follows the dogpile pattern (DogpileMonitor) for progress tracking.
"""
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
import urllib.request
import urllib.error


@dataclass
class SecurityScanMonitor:
    """
    Monitor for security scan progress.

    Integrates with task-monitor API for real-time progress tracking.
    """

    name: str = "security-scan"
    api_url: str = field(default_factory=lambda: os.environ.get(
        "TASK_MONITOR_API_URL", "http://localhost:8765"
    ))
    enabled: bool = field(default_factory=lambda: os.environ.get(
        "TASK_MONITOR_ENABLED", "true"
    ).lower() != "false")

    # State tracking
    total_steps: int = 0
    completed_steps: int = 0
    current_phase: str = ""
    start_time: float = field(default_factory=time.time)
    errors: list[str] = field(default_factory=list)

    # Local state file for offline operation
    state_file: Path = field(default_factory=lambda: Path.home() / ".pi" / "task-monitor" / "security-scan-state.json")

    def __post_init__(self) -> None:
        """Initialize state file directory."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

    def start(self, phases: list[str] | None = None) -> None:
        """Start monitoring a scan."""
        default_phases = ["sast", "deps", "secrets", "finalize"]
        phases = phases or default_phases
        self.total_steps = len(phases)
        self.completed_steps = 0
        self.start_time = time.time()
        self.errors = []
        self._update_state("running", f"Starting scan: {', '.join(phases)}")

    def phase_start(self, phase: str) -> None:
        """Mark the start of a phase."""
        self.current_phase = phase
        self._update_state("running", f"Running {phase}")

    def phase_complete(self, phase: str, findings: int = 0) -> None:
        """Mark a phase as complete."""
        self.completed_steps += 1
        self._update_state(
            "running",
            f"Completed {phase}: {findings} findings"
        )

    def phase_error(self, phase: str, error: str) -> None:
        """Record a phase error."""
        self.errors.append(f"{phase}: {error}")
        self._update_state("running", f"Error in {phase}: {error}")

    def complete(self, total_findings: int = 0) -> None:
        """Mark the scan as complete."""
        elapsed = time.time() - self.start_time
        self._update_state(
            "completed",
            f"Scan complete: {total_findings} findings in {elapsed:.1f}s"
        )

    def fail(self, error: str) -> None:
        """Mark the scan as failed."""
        self._update_state("failed", f"Scan failed: {error}")

    def _update_state(self, status: str, message: str) -> None:
        """Update state locally and push to API."""
        state = {
            "name": self.name,
            "status": status,
            "message": message,
            "progress": self.completed_steps,
            "total": self.total_steps,
            "current_phase": self.current_phase,
            "errors": self.errors,
            "elapsed_seconds": time.time() - self.start_time,
            "updated_at": datetime.now().isoformat(),
        }

        # Always write local state
        try:
            self.state_file.write_text(json.dumps(state, indent=2))
        except Exception:
            pass

        # Push to API if enabled
        if self.enabled:
            self._push_to_api(state)

    def _push_to_api(self, state: dict[str, Any]) -> None:
        """Push state to task-monitor API."""
        try:
            url = f"{self.api_url}/tasks/{self.name}/state"
            data = json.dumps(state).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                resp.read()
        except urllib.error.URLError:
            pass  # API not available, that's OK
        except Exception:
            pass


def create_monitor(name: str = "security-scan") -> SecurityScanMonitor:
    """Factory function to create a monitor instance."""
    return SecurityScanMonitor(name=name)


if __name__ == "__main__":
    # Demo usage
    monitor = SecurityScanMonitor()
    monitor.start()
    monitor.phase_start("sast")
    time.sleep(0.1)
    monitor.phase_complete("sast", findings=5)
    monitor.phase_start("deps")
    time.sleep(0.1)
    monitor.phase_complete("deps", findings=2)
    monitor.complete(total_findings=7)
    print("Monitor test complete")
