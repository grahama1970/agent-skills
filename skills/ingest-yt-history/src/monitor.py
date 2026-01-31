"""
Progress tracking utilities for task-monitor integration.

Provides BatchProgress class that writes .batch_state.json for task-monitor visibility.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class BatchProgress:
    """
    Tracks batch operation progress and writes to .batch_state.json.

    The state file is written atomically (temp file + rename) to prevent
    partial reads by task-monitor.

    State format matches task-monitor expectations:
    {
        "completed": 150,
        "total": 1000,
        "current_item": "processing video dQw4w9WgXcQ",
        "stats": {"success": 145, "failed": 3, "skipped": 2},
        "elapsed_seconds": 45.2,
        "progress_pct": 15.0,
        "status": "running"
    }
    """

    output_dir: Path
    total: int
    completed: int = 0
    stats: dict[str, int] = field(default_factory=lambda: {"success": 0, "failed": 0, "skipped": 0})
    current_item: str = ""
    status: str = "running"
    _start_time: float = field(default_factory=time.time)

    def __post_init__(self):
        """Ensure output_dir is a Path and initialize start time."""
        self.output_dir = Path(self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        # Write initial state
        self._write_state()

    @property
    def state_file(self) -> Path:
        """Path to the batch state file."""
        return self.output_dir / ".batch_state.json"

    @property
    def elapsed_seconds(self) -> float:
        """Elapsed time since batch started."""
        return time.time() - self._start_time

    @property
    def progress_pct(self) -> float:
        """Progress percentage (0.0 to 100.0)."""
        if self.total <= 0:
            return 0.0
        return (self.completed / self.total) * 100.0

    def to_dict(self) -> dict[str, Any]:
        """Convert current state to dict for JSON serialization."""
        return {
            "completed": self.completed,
            "total": self.total,
            "current_item": self.current_item,
            "stats": self.stats.copy(),
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "progress_pct": round(self.progress_pct, 2),
            "status": self.status,
        }

    def _write_state(self) -> None:
        """Write state to file atomically (temp + rename)."""
        state = self.to_dict()

        # Write to temp file in same directory for atomic rename
        fd, temp_path = tempfile.mkstemp(
            suffix=".tmp",
            prefix=".batch_state_",
            dir=self.output_dir,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            # Atomic rename
            os.replace(temp_path, self.state_file)
        except Exception:
            # Clean up temp file on error
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

    def update(
        self,
        current_item: Optional[str] = None,
        increment_completed: bool = False,
        result: Optional[str] = None,
    ) -> None:
        """
        Update progress state and write to file.

        Args:
            current_item: Description of current item being processed
            increment_completed: Whether to increment completed count
            result: Result type to increment in stats ("success", "failed", "skipped")
        """
        if current_item is not None:
            self.current_item = current_item

        if increment_completed:
            self.completed += 1

        if result is not None and result in self.stats:
            self.stats[result] += 1

        self._write_state()

    def record_success(self, item: Optional[str] = None) -> None:
        """Record a successful item."""
        self.update(current_item=item, increment_completed=True, result="success")

    def record_failure(self, item: Optional[str] = None) -> None:
        """Record a failed item."""
        self.update(current_item=item, increment_completed=True, result="failed")

    def record_skip(self, item: Optional[str] = None) -> None:
        """Record a skipped item."""
        self.update(current_item=item, increment_completed=True, result="skipped")

    def set_processing(self, item: str) -> None:
        """Set the current item being processed (without incrementing counts)."""
        self.update(current_item=f"processing {item}")

    def complete(self, status: str = "completed") -> None:
        """Mark the batch as complete."""
        self.status = status
        self.current_item = ""
        self._write_state()

    def fail(self, error: str = "") -> None:
        """Mark the batch as failed."""
        self.status = "failed"
        self.current_item = error or "batch failed"
        self._write_state()

    @classmethod
    def from_state_file(cls, state_file: Path) -> Optional["BatchProgress"]:
        """
        Load existing progress from a state file.

        Args:
            state_file: Path to .batch_state.json

        Returns:
            BatchProgress instance if file exists and is valid, None otherwise
        """
        if not state_file.exists():
            return None

        try:
            with open(state_file, encoding="utf-8") as f:
                data = json.load(f)

            progress = cls(
                output_dir=state_file.parent,
                total=data.get("total", 0),
                completed=data.get("completed", 0),
                stats=data.get("stats", {"success": 0, "failed": 0, "skipped": 0}),
                current_item=data.get("current_item", ""),
                status=data.get("status", "running"),
            )
            return progress
        except (OSError, json.JSONDecodeError, KeyError):
            return None
