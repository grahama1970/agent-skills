#!/usr/bin/env python3
"""Task-monitor integration for security-scan.

Thin wrapper around shared TaskClient. Preserves SecurityScanMonitor interface.
"""
import time
from typing import Any, Dict, List, Optional

from common.task_monitor import TaskClient


class SecurityScanMonitor:
    """Monitor for security scan progress.

    Delegates core state tracking to shared TaskClient.
    """

    def __init__(self, name: str = "security-scan"):
        self.name = name
        self.current_phase = ""
        self.errors: List[str] = []

        self._client = TaskClient(
            skill_name=name,
            total=1,
            description="Security scan",
            register=True,
        )

    def start(self, phases: Optional[List[str]] = None) -> None:
        default_phases = ["sast", "deps", "secrets", "finalize"]
        phases = phases or default_phases
        self.errors = []
        self._client.set_total(len(phases))
        self._client.heartbeat(item=f"Starting scan: {', '.join(phases)}")

    def phase_start(self, phase: str) -> None:
        self.current_phase = phase
        self._client.heartbeat(item=f"Running {phase}")

    def phase_complete(self, phase: str, findings: int = 0) -> None:
        self._client.update(
            item=f"Completed {phase}: {findings} findings",
            findings=findings,
        )

    def phase_error(self, phase: str, error: str) -> None:
        self.errors.append(f"{phase}: {error}")
        self._client.heartbeat(item=f"Error in {phase}: {error}")

    def complete(self, total_findings: int = 0) -> None:
        self._client.update(
            n=0,
            item=f"Scan complete: {total_findings} findings",
            total_findings=total_findings,
        )
        self._client.finish(success=True)

    def fail(self, error: str) -> None:
        self._client.update(n=0, item=f"Scan failed: {error}")
        self._client.finish(success=False)


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
