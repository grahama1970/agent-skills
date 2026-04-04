"""Shared task-monitor client for all skills.

Drop-in integration with the centralized task-monitor TUI/API.
Writes state to registry + state files. Never crashes the host skill.

Usage (3 lines to integrate):
    from common.task_monitor import TaskClient

    monitor = TaskClient("my-skill", total=100)
    for item in items:
        process(item)
        monitor.update(item=str(item))
    monitor.finish()

    # Or as context manager:
    with TaskClient("my-skill", total=100) as m:
        for item in items:
            process(item)
            m.update(item=str(item))

Replaces all per-skill task_monitor_client.py copies.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


__all__ = ["TaskClient"]

# Global registry for task-monitor TUI discovery
REGISTRY_PATH = Path.home() / ".pi" / "task-monitor" / "registry.json"


class TaskClient:
    """Generic task-monitor client. Gracefully degrades on all errors."""

    def __init__(
        self,
        skill_name: str,
        total: int = 1,
        description: str = "",
        state_dir: Optional[str] = None,
        min_interval_s: float = 1.0,
        register: bool = True,
    ):
        self.skill_name = skill_name
        self.total = total
        self.description = description or skill_name

        # Progress
        self.completed = 0
        self.failed = 0
        self.start_time = time.time()
        self.current_item = ""
        self.stats: Dict[str, Any] = {}

        # Throttling
        self._min_interval = min_interval_s
        self._last_write = 0.0

        # State file location
        if state_dir:
            self._state_dir = Path(state_dir)
        else:
            self._state_dir = Path.cwd()
        self._state_file = self._state_dir / f"{skill_name.replace('/', '_')}_task_state.json"
        self._batch_file = self._state_dir / ".batch_state.json"

        if register:
            self._register()
        self._write_state()

    # -- Context manager --
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.finish(success=exc_type is None)
        return False

    # -- Public API --
    def update(self, n: int = 1, item: str = "", **extra_stats):
        """Increment progress. Merges extra_stats into self.stats."""
        self.completed += n
        if item:
            self.current_item = str(item)[:80]
        if extra_stats:
            self.stats.update(extra_stats)

        now = time.time()
        if now - self._last_write >= self._min_interval:
            self._write_state()

    def fail(self, n: int = 1, item: str = ""):
        """Register N failures (also increments completed)."""
        self.failed += n
        self.completed += n
        if item:
            self.current_item = f"FAIL: {str(item)[:74]}"

        now = time.time()
        if now - self._last_write >= self._min_interval:
            self._write_state()

    def heartbeat(self, item: str = ""):
        """Force a state write (bypass throttle)."""
        if item:
            self.current_item = str(item)[:80]
        self._last_write = 0.0
        self._write_state()

    def finish(self, success: bool = True):
        """Mark task complete with final state write."""
        self._write_state(final=True, success=success)

    def set_total(self, total: int):
        """Update total (useful when total is discovered after init)."""
        self.total = total

    def get_summary(self) -> Dict[str, Any]:
        """Return summary dict for logging/reporting."""
        elapsed = time.time() - self.start_time
        rate = self.completed / elapsed if elapsed > 0 else 0
        return {
            "skill": self.skill_name,
            "completed": self.completed,
            "total": self.total,
            "failed": self.failed,
            "elapsed_seconds": round(elapsed, 1),
            "throughput_per_sec": round(rate, 2),
        }

    # -- Internal --
    def _register(self):
        """Register in ~/.pi/task-monitor/registry.json."""
        try:
            REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
            registry = {}
            if REGISTRY_PATH.exists():
                try:
                    registry = json.loads(REGISTRY_PATH.read_text())
                except Exception:
                    registry = {}

            registry[self.skill_name] = {
                "state_file": str(self._state_file),
                "batch_state_file": str(self._batch_file),
                "total": self.total,
                "description": self.description,
                "registered_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            tmp = REGISTRY_PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(registry, indent=2))
            os.replace(tmp, REGISTRY_PATH)
        except Exception:
            pass  # Never crash the host skill

    def _build_state(self, final: bool = False, success: bool = True) -> Dict[str, Any]:
        elapsed = time.time() - self.start_time
        pct = (self.completed / self.total * 100) if self.total > 0 else 0

        eta = None
        if self.completed > 0 and self.completed < self.total and elapsed > 0:
            rate = self.completed / elapsed
            eta = round((self.total - self.completed) / rate, 1) if rate > 0 else None

        throughput = round(self.completed / elapsed, 2) if elapsed > 0 else 0

        status = "completed" if final else "running"
        if final and not success:
            status = "error"

        return {
            "skill": self.skill_name,
            "completed": self.completed,
            "total": self.total,
            "description": self.description,
            "current_item": self.current_item,
            "progress_pct": round(pct, 1),
            "elapsed_seconds": round(elapsed, 1),
            "eta_seconds": eta,
            "throughput_per_sec": throughput,
            "stats": {
                "success": self.completed - self.failed,
                "failed": self.failed,
                **self.stats,
            },
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": status,
        }

    def _write_state(self, final: bool = False, success: bool = True):
        """Atomic write to both state files."""
        self._last_write = time.time()
        state = self._build_state(final=final, success=success)

        for path in (self._state_file, self._batch_file):
            try:
                tmp = path.with_suffix(".tmp")
                tmp.write_text(json.dumps(state, indent=2))
                os.replace(tmp, path)
            except Exception:
                pass  # Never crash the host skill
