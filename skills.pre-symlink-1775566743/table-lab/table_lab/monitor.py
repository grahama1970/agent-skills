"""Task-monitor integration for batch table tuning.

Registers with ~/.pi/task-monitor/registry.json so other skills
(like corpus-report) can observe table-lab batch progress.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

TASK_MONITOR_DIR = Path.home() / ".pi" / "task-monitor"
REGISTRY_PATH = TASK_MONITOR_DIR / "registry.json"


class DebugTableTaskClient:
    """Lightweight task-monitor client for table-lab batch operations."""

    def __init__(self, task_name: str, total_pdfs: int) -> None:
        self.task_name = task_name
        self.total_pdfs = total_pdfs
        self.completed = 0
        self.failed = 0
        self.state_path = TASK_MONITOR_DIR / f"{task_name}.batch_state.json"
        self._register()

    def _register(self) -> None:
        """Register this task in the task-monitor registry.

        Registry format: {"tasks": {"task_name": {...}, ...}}
        """
        TASK_MONITOR_DIR.mkdir(parents=True, exist_ok=True)

        registry: dict = {"tasks": {}}
        if REGISTRY_PATH.exists():
            try:
                raw = json.loads(REGISTRY_PATH.read_text())
                if isinstance(raw, dict) and "tasks" in raw:
                    registry = raw
                elif isinstance(raw, dict):
                    registry = {"tasks": raw}
            except (json.JSONDecodeError, OSError):
                pass

        registry["tasks"][self.task_name] = {
            "name": self.task_name,
            "skill": "table-lab",
            "batch_type": "table_tune",
            "total": self.total_pdfs,
            "state_file": str(self.state_path),
            "description": f"Batch table tuning ({self.total_pdfs} PDFs)",
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }

        tmp = REGISTRY_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(registry, indent=2))
        tmp.rename(REGISTRY_PATH)
        logger.debug(f"Registered task '{self.task_name}' in task-monitor")

    def update(self, pdf_name: str, success: bool) -> None:
        """Update batch state after processing a PDF."""
        if success:
            self.completed += 1
        else:
            self.failed += 1

        state = {
            "task_name": self.task_name,
            "skill": "table-lab",
            "total": self.total_pdfs,
            "completed": self.completed,
            "failed": self.failed,
            "remaining": self.total_pdfs - self.completed - self.failed,
            "progress_pct": round(100 * (self.completed + self.failed) / max(1, self.total_pdfs), 1),
            "last_pdf": pdf_name,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2))
        tmp.rename(self.state_path)

    def finish(self) -> None:
        """Mark task as finished in state file."""
        state = {
            "task_name": self.task_name,
            "skill": "table-lab",
            "total": self.total_pdfs,
            "completed": self.completed,
            "failed": self.failed,
            "status": "finished",
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }

        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2))
        tmp.rename(self.state_path)
        logger.info(
            f"Task '{self.task_name}' finished: "
            f"{self.completed} completed, {self.failed} failed"
        )
