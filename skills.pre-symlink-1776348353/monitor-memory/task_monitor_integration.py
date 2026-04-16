"""Task Monitor Integration for monitor-memory.

Thin wrapper around shared TaskClient. Preserves the MemoryMonitorTracker
interface with per-probe tracking.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from common.task_monitor import TaskClient

STATE_DIR = Path.home() / ".pi" / "monitor-memory"


class MemoryMonitorTracker:
    """Task-monitor compatible tracker for memory health probes."""

    def __init__(
        self,
        job_type: str = "check",
        name: str = "memory-monitor",
        register: bool = True,
    ):
        self.job_type = job_type
        self.name = f"{name}-{job_type}"
        STATE_DIR.mkdir(parents=True, exist_ok=True)

        self._client = TaskClient(
            skill_name=self.name,
            total=1,
            description=f"Memory Monitor: {job_type}",
            state_dir=str(STATE_DIR),
            register=register,
        )

        self.probes: List[str] = []
        self.current_probe: str = ""
        self.completed_probes: List[str] = []
        self.probe_status: Dict[str, str] = {}
        self.probe_stats: Dict[str, Dict[str, Any]] = {}
        self.errors: List[Dict[str, Any]] = []

    def set_probes(self, probe_ids: List[str]):
        self.probes = probe_ids
        self.probe_status = {p: "pending" for p in probe_ids}
        self._client.set_total(len(probe_ids))
        self._client.heartbeat(item=f"0/{len(probe_ids)} probes")

    def start_probe(self, probe_id: str):
        self.current_probe = probe_id
        self.probe_status[probe_id] = "running"
        self._client.heartbeat(item=probe_id)

    def complete_probe(
        self,
        probe_id: str,
        success: bool = True,
        stats: Optional[Dict[str, Any]] = None,
        error_msg: Optional[str] = None,
    ):
        self.probe_status[probe_id] = "success" if success else "failed"
        self.completed_probes.append(probe_id)

        if stats:
            self.probe_stats[probe_id] = stats

        if not success and error_msg:
            self.errors.append({
                "probe": probe_id,
                "message": error_msg,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            })

        if success:
            self._client.update(item=probe_id)
        else:
            self._client.fail(item=probe_id)

    def skip_probe(self, probe_id: str, reason: str = "not applicable"):
        self.probe_status[probe_id] = "skipped"
        self.completed_probes.append(probe_id)
        self.probe_stats[probe_id] = {"skipped_reason": reason}
        self._client.update(item=f"{probe_id} (skipped)")

    def finish(self, success: bool = True):
        self._client.finish(success=success)

    def get_summary(self) -> Dict[str, Any]:
        summary = self._client.get_summary()
        summary.update({
            "job_type": self.job_type,
            "probes": {
                "total": len(self.probes),
                "success": sum(1 for s in self.probe_status.values() if s == "success"),
                "failed": sum(1 for s in self.probe_status.values() if s == "failed"),
                "skipped": sum(1 for s in self.probe_status.values() if s == "skipped"),
            },
            "errors": len(self.errors),
        })
        return summary


# Global tracker instances
_trackers: Dict[str, MemoryMonitorTracker] = {}


def start_job(job_type: str) -> MemoryMonitorTracker:
    tracker = MemoryMonitorTracker(job_type=job_type)
    _trackers[job_type] = tracker
    return tracker


def get_tracker(job_type: str) -> Optional[MemoryMonitorTracker]:
    return _trackers.get(job_type)


def end_job(job_type: str, success: bool = True):
    if job_type in _trackers:
        _trackers[job_type].finish(success)
        del _trackers[job_type]
