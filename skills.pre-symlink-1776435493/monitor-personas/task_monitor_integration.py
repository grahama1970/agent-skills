#!/usr/bin/env python3
"""Task Monitor Integration for Monitor-Personas.

Thin wrapper around shared TaskClient. Preserves PersonaMonitorTracker interface.
"""
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from common.task_monitor import TaskClient

STATE_DIR = Path.home() / ".pi" / "monitor-personas"


class PersonaMonitorTracker:
    """Task-monitor compatible tracker for persona monitoring jobs."""

    def __init__(
        self,
        job_type: str = "check",
        name: str = "persona-monitor",
        register: bool = True,
    ):
        self.job_type = job_type
        self.name = f"{name}-{job_type}"
        STATE_DIR.mkdir(parents=True, exist_ok=True)

        self._client = TaskClient(
            skill_name=self.name,
            total=1,
            description=f"Persona Monitor: {job_type}",
            state_dir=str(STATE_DIR),
            register=register,
        )

        self.personas: List[str] = []
        self.current_persona: str = ""
        self.completed_personas: List[str] = []
        self.persona_status: Dict[str, str] = {}
        self.persona_stats: Dict[str, Dict[str, Any]] = {}
        self.errors: List[Dict[str, Any]] = []

    def set_personas(self, personas: List[str]):
        self.personas = personas
        self.persona_status = {p: "pending" for p in personas}
        self._client.set_total(len(personas))
        self._client.heartbeat(item=f"0/{len(personas)} personas")

    def start_persona(self, persona_id: str):
        self.current_persona = persona_id
        self.persona_status[persona_id] = "running"
        self._client.heartbeat(item=persona_id)

    def complete_persona(
        self,
        persona_id: str,
        success: bool = True,
        stats: Optional[Dict[str, Any]] = None,
        error_msg: Optional[str] = None,
    ):
        self.persona_status[persona_id] = "success" if success else "failed"
        self.completed_personas.append(persona_id)

        if stats:
            self.persona_stats[persona_id] = stats

        if not success and error_msg:
            self.errors.append({
                "persona": persona_id,
                "message": error_msg,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            })

        if success:
            self._client.update(item=persona_id)
        else:
            self._client.fail(item=persona_id)

    def skip_persona(self, persona_id: str, reason: str = "no new content"):
        self.persona_status[persona_id] = "skipped"
        self.completed_personas.append(persona_id)
        self.persona_stats[persona_id] = {"skipped_reason": reason}
        self._client.update(item=f"{persona_id} (skipped)")

    def log_error(self, persona_id: str, error_msg: str):
        self.errors.append({
            "persona": persona_id,
            "message": error_msg,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        self._client.heartbeat(item=f"{persona_id} (error)")

    def finish(self, success: bool = True):
        self._client.finish(success=success)

    def get_summary(self) -> Dict[str, Any]:
        summary = self._client.get_summary()
        summary.update({
            "job_type": self.job_type,
            "personas": {
                "total": len(self.personas),
                "success": sum(1 for s in self.persona_status.values() if s == "success"),
                "failed": sum(1 for s in self.persona_status.values() if s == "failed"),
                "skipped": sum(1 for s in self.persona_status.values() if s == "skipped"),
            },
            "errors": len(self.errors),
        })
        return summary


# Global tracker instances
_trackers: Dict[str, PersonaMonitorTracker] = {}


def start_job(job_type: str) -> PersonaMonitorTracker:
    tracker = PersonaMonitorTracker(job_type=job_type)
    _trackers[job_type] = tracker
    return tracker


def get_tracker(job_type: str) -> Optional[PersonaMonitorTracker]:
    return _trackers.get(job_type)


def end_job(job_type: str, success: bool = True):
    if job_type in _trackers:
        _trackers[job_type].finish(success)
        del _trackers[job_type]
