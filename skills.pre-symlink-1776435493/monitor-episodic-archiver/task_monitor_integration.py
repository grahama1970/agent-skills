"""Task-monitor integration for episodic nightly pipeline.

Thin wrapper around shared TaskClient. Preserves the EpisodicMonitorTracker
interface with per-session tracking.
"""
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from common.task_monitor import TaskClient

STATE_DIR = Path.home() / ".pi" / "monitor-episodic-archiver"


class EpisodicMonitorTracker:
    """Track nightly episodic pipeline progress for task-monitor."""

    def __init__(
        self,
        job_type: str = "nightly",
        name: str = "episodic-monitor",
        register: bool = True,
    ):
        self.job_type = job_type
        self.name = f"{name}-{job_type}"
        STATE_DIR.mkdir(parents=True, exist_ok=True)

        self._client = TaskClient(
            skill_name=self.name,
            total=1,
            description=f"Episodic Monitor: {job_type}",
            state_dir=str(STATE_DIR),
            register=register,
        )

        self.sessions: List[str] = []
        self.current_session: str = ""
        self.completed_sessions: List[str] = []
        self.session_status: Dict[str, str] = {}
        self.session_stats: Dict[str, Dict[str, Any]] = {}
        self.errors: List[Dict[str, Any]] = []

    def set_sessions(self, session_ids: List[str]):
        self.sessions = session_ids
        self.session_status = {s: "pending" for s in session_ids}
        self._client.set_total(len(session_ids))
        self._client.heartbeat(item=f"0/{len(session_ids)} sessions")

    def start_session(self, session_id: str):
        self.current_session = session_id
        self.session_status[session_id] = "running"
        self._client.heartbeat(item=session_id)

    def complete_session(
        self, session_id: str, success: bool = True,
        stats: dict = None, error_msg: str = None,
    ):
        self.session_status[session_id] = "success" if success else "failed"
        self.completed_sessions.append(session_id)
        if stats:
            self.session_stats[session_id] = stats
        if error_msg:
            self.errors.append({
                "session_id": session_id,
                "error": error_msg,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            })

        success_count = sum(1 for s in self.session_status.values() if s == "success")
        failed_count = sum(1 for s in self.session_status.values() if s == "failed")
        skipped_count = sum(1 for s in self.session_status.values() if s == "skipped")

        if success:
            self._client.update(item=session_id, success=success_count, failed=failed_count, skipped=skipped_count)
        else:
            self._client.fail(item=session_id)

    def skip_session(self, session_id: str, reason: str = ""):
        self.session_status[session_id] = "skipped"
        self.completed_sessions.append(session_id)
        self._client.update(item=f"{session_id} (skipped)")

    def finish(self, success: bool = True):
        self.current_session = ""
        self._client.finish(success=success)

    def get_summary(self) -> dict:
        summary = self._client.get_summary()
        summary.update({
            "total": len(self.sessions),
            "completed": len(self.completed_sessions),
            "success": sum(1 for s in self.session_status.values() if s == "success"),
            "failed": sum(1 for s in self.session_status.values() if s == "failed"),
            "skipped": sum(1 for s in self.session_status.values() if s == "skipped"),
            "errors": len(self.errors),
        })
        return summary


# Global tracker management
_trackers: Dict[str, EpisodicMonitorTracker] = {}


def start_job(job_type: str = "nightly") -> EpisodicMonitorTracker:
    tracker = EpisodicMonitorTracker(job_type=job_type)
    _trackers[job_type] = tracker
    return tracker


def end_job(job_type: str = "nightly", success: bool = True):
    if job_type in _trackers:
        _trackers[job_type].finish(success)
        del _trackers[job_type]
