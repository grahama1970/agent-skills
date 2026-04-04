#!/usr/bin/env python3
"""Task-monitor integration for ops-compliance.

Thin wrapper around shared TaskClient. Preserves ComplianceMonitor interface.
"""
import os
import time
from typing import Any, Dict

from common.task_monitor import TaskClient


class ComplianceMonitor:
    """Monitor for compliance scan progress.

    Delegates core state tracking to shared TaskClient.
    """

    def __init__(self, name: str = "ops-compliance"):
        self.name = name
        self.current_framework = ""
        self.results: Dict[str, int] = {"passed": 0, "failed": 0, "warnings": 0}

        self._client = TaskClient(
            skill_name=name,
            total=1,
            description="Compliance scan",
            register=True,
        )

    def start(self, framework: str, estimated_checks: int = 10) -> None:
        self.current_framework = framework
        self.results = {"passed": 0, "failed": 0, "warnings": 0}
        self._client.set_total(estimated_checks)
        self._client.heartbeat(item=f"Starting {framework.upper()} compliance check")

    def check_complete(self, check_id: str, status: str) -> None:
        if status == "pass":
            self.results["passed"] += 1
        elif status == "fail":
            self.results["failed"] += 1
        elif status == "warning":
            self.results["warnings"] += 1

        self._client.update(
            item=f"Check {check_id}: {status}",
            passed=self.results["passed"],
            failed=self.results["failed"],
            warnings=self.results["warnings"],
            framework=self.current_framework,
        )

    def complete(self) -> None:
        status = "compliant" if self.results["failed"] == 0 else "non-compliant"
        self._client.update(
            n=0,
            item=f"{self.current_framework.upper()} scan complete: {status}",
        )
        self._client.finish(success=True)

    def fail(self, error: str) -> None:
        self._client.update(n=0, item=f"Compliance scan failed: {error}")
        self._client.finish(success=False)


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
