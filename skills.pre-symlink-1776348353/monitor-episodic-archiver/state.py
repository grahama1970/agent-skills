"""State management for monitor-episodic-archiver nightly pipeline."""

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional


DEFAULT_STATE_DIR = Path.home() / ".pi" / "monitor-episodic-archiver"


class StateManager:
    """Manages nightly pipeline state with atomic JSON writes."""

    def __init__(self, state_dir: Path = DEFAULT_STATE_DIR):
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.nightly_file = state_dir / "nightly_state.json"
        self.report_file = state_dir / "nightly_report.json"

    def _load_json(self, path: Path, default: Any = None) -> Any:
        if path.exists():
            try:
                return json.loads(path.read_text())
            except json.JSONDecodeError:
                pass
        return default if default is not None else {}

    def _save_json(self, path: Path, data: Any):
        """Atomic write: write to .tmp then rename."""
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, default=str))
        os.replace(str(tmp), str(path))

    def load_nightly_state(self) -> dict:
        return self._load_json(self.nightly_file, {
            "last_run": None,
            "last_success": None,
            "sessions_processed": 0,
            "total_runs": 0,
            "consecutive_failures": 0,
        })

    def save_nightly_state(self, state: dict):
        self._save_json(self.nightly_file, state)

    def record_nightly_run(self, success: bool, stats: dict):
        """Record a nightly run result."""
        state = self.load_nightly_state()
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        state["last_run"] = now
        state["total_runs"] = state.get("total_runs", 0) + 1
        state["sessions_processed"] = state.get("sessions_processed", 0) + stats.get("archived", 0)

        if success:
            state["last_success"] = now
            state["consecutive_failures"] = 0
        else:
            state["consecutive_failures"] = state.get("consecutive_failures", 0) + 1

        state["last_stats"] = stats
        self.save_nightly_state(state)

    def save_report(self, report: dict):
        """Save nightly report JSON."""
        self._save_json(self.report_file, report)

    def load_report(self) -> dict:
        return self._load_json(self.report_file, {})


# Singleton
_state_manager: Optional[StateManager] = None


def get_state_manager(state_dir: Optional[Path] = None) -> StateManager:
    global _state_manager
    if _state_manager is None or state_dir is not None:
        _state_manager = StateManager(state_dir or DEFAULT_STATE_DIR)
    return _state_manager
