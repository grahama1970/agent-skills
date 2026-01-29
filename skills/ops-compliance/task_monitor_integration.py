#!/usr/bin/env python3
"""
Task-monitor integration for ops-compliance.

Follows the dogpile pattern for progress tracking.
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
class ComplianceMonitor:
    """
    Monitor for compliance scan progress.

    Integrates with task-monitor API for real-time progress tracking.
    """

    name: str = "ops-compliance"
    api_url: str = field(default_factory=lambda: os.environ.get(
        "TASK_MONITOR_API_URL", "http://localhost:8765"
    ))
    enabled: bool = field(default_factory=lambda: os.environ.get(
        "TASK_MONITOR_ENABLED", "true"
    ).lower() != "false")

    # State tracking
    total_checks: int = 0
    completed_checks: int = 0
    current_framework: str = ""
    start_time: float = field(default_factory=time.time)
    results: dict[str, Any] = field(default_factory=dict)

    # Local state file
    state_file: Path = field(default_factory=lambda: Path.home() / ".pi" / "task-monitor" / "ops-compliance-state.json")

    def __post_init__(self) -> None:
        """Initialize state file directory."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.results = {"passed": 0, "failed": 0, "warnings": 0}

    def start(self, framework: str, estimated_checks: int = 10) -> None:
        """Start monitoring a compliance scan."""
        self.current_framework = framework
        self.total_checks = estimated_checks
        self.completed_checks = 0
        self.start_time = time.time()
        self.results = {"passed": 0, "failed": 0, "warnings": 0}
        self._update_state("running", f"Starting {framework.upper()} compliance check")

    def check_complete(self, check_id: str, status: str) -> None:
        """Record a completed check."""
        self.completed_checks += 1
        if status == "pass":
            self.results["passed"] += 1
        elif status == "fail":
            self.results["failed"] += 1
        elif status == "warning":
            self.results["warnings"] += 1

        self._update_state(
            "running",
            f"Check {check_id}: {status} ({self.completed_checks}/{self.total_checks})"
        )

    def complete(self) -> None:
        """Mark the scan as complete."""
        elapsed = time.time() - self.start_time
        status = "compliant" if self.results["failed"] == 0 else "non-compliant"
        self._update_state(
            "completed",
            f"{self.current_framework.upper()} scan complete: {status} "
            f"(P:{self.results['passed']} F:{self.results['failed']} W:{self.results['warnings']}) "
            f"in {elapsed:.1f}s"
        )

    def fail(self, error: str) -> None:
        """Mark the scan as failed."""
        self._update_state("failed", f"Compliance scan failed: {error}")

    def _update_state(self, status: str, message: str) -> None:
        """Update state locally and push to API."""
        state = {
            "name": self.name,
            "status": status,
            "message": message,
            "progress": self.completed_checks,
            "total": self.total_checks,
            "framework": self.current_framework,
            "results": self.results,
            "elapsed_seconds": time.time() - self.start_time,
            "updated_at": datetime.now().isoformat(),
        }

        # Write local state
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
            pass
        except Exception:
            pass


def create_monitor(name: str = "ops-compliance") -> ComplianceMonitor:
    """Factory function to create a monitor instance."""
    return ComplianceMonitor(name=name)


if __name__ == "__main__":
    # Demo usage
    monitor = ComplianceMonitor()
    monitor.start("soc2", estimated_checks=5)
    for i in range(5):
        monitor.check_complete(f"CC{i+1}.1", "pass" if i < 3 else "warning")
        time.sleep(0.1)
    monitor.complete()
    print("Monitor test complete")
