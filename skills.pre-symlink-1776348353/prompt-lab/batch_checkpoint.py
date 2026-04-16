"""Batch checkpoint/resume capability for prompt-lab.

Enables long-running QRA batch operations to:
1. Save progress after each case
2. Resume from last completed case on restart
3. Skip already-processed cases

Usage:
    checkpoint = BatchCheckpoint("test-sparta-100", total_cases=100)

    for case in cases:
        if checkpoint.is_completed(case.id):
            continue  # Skip already processed

        result = process(case)
        checkpoint.mark_completed(case.id, metrics)

    checkpoint.finalize()

Resume:
    checkpoint = BatchCheckpoint.load("test-sparta-100")
    completed_ids = checkpoint.completed_case_ids
"""
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Any


# Default checkpoint directory
CHECKPOINT_DIR = Path(__file__).parent / ".checkpoints"


from loguru import logger


@dataclass
class BatchCheckpoint:
    """Track batch progress for resume capability.

    Saves checkpoint after each completed case for crash recovery.
    """

    task_name: str
    total_cases: int
    checkpoint_dir: Path = field(default_factory=lambda: CHECKPOINT_DIR)

    # State tracking
    completed_case_ids: Set[str] = field(default_factory=set)
    metrics_snapshot: Dict[str, float] = field(default_factory=dict)
    results_buffer: List[Dict[str, Any]] = field(default_factory=list)

    # Timestamps
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_completed_at: Optional[str] = None

    # Internal
    _checkpoint_file: Path = field(init=False, repr=False)
    _results_file: Path = field(init=False, repr=False)

    def __post_init__(self):
        """Initialize paths and ensure directory exists."""
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self._checkpoint_file = self.checkpoint_dir / f"{self.task_name}.checkpoint.json"
        self._results_file = self.checkpoint_dir / f"{self.task_name}.results.jsonl"

        # Convert list to set if loaded from JSON
        if isinstance(self.completed_case_ids, list):
            self.completed_case_ids = set(self.completed_case_ids)

    def is_completed(self, case_id: str) -> bool:
        """Check if a case has already been processed."""
        return case_id in self.completed_case_ids

    def mark_completed(
        self,
        case_id: str,
        metrics: Optional[Dict[str, float]] = None,
        result: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Mark a case as completed and save checkpoint.

        Args:
            case_id: The completed case ID
            metrics: Optional metrics snapshot to store
            result: Optional result data to append to results file
        """
        self.completed_case_ids.add(case_id)
        self.last_completed_at = datetime.now().isoformat()

        if metrics:
            self.metrics_snapshot.update(metrics)

        if result:
            self.results_buffer.append(result)
            self._append_result(result)

        self._save_checkpoint()

    def _save_checkpoint(self) -> None:
        """Save checkpoint atomically."""
        data = {
            "task_name": self.task_name,
            "total_cases": self.total_cases,
            "completed_case_ids": list(self.completed_case_ids),
            "completed_count": len(self.completed_case_ids),
            "started_at": self.started_at,
            "last_completed_at": self.last_completed_at,
            "metrics_snapshot": self.metrics_snapshot,
        }

        # Atomic write
        tmp = self._checkpoint_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        os.replace(tmp, self._checkpoint_file)

    def _append_result(self, result: Dict[str, Any]) -> None:
        """Append a result to the JSONL file."""
        try:
            with open(self._results_file, "a") as f:
                f.write(json.dumps(result) + "\n")
        except Exception as e:
            logger.debug("batch checkpoint result append failed: {}", e)

    @classmethod
    def load(cls, task_name: str, checkpoint_dir: Optional[Path] = None) -> Optional["BatchCheckpoint"]:
        """Load an existing checkpoint if it exists.

        Args:
            task_name: The task name to load
            checkpoint_dir: Optional custom checkpoint directory

        Returns:
            BatchCheckpoint if found, None otherwise
        """
        checkpoint_dir = checkpoint_dir or CHECKPOINT_DIR
        checkpoint_file = checkpoint_dir / f"{task_name}.checkpoint.json"

        if not checkpoint_file.exists():
            return None

        try:
            data = json.loads(checkpoint_file.read_text())
            return cls(
                task_name=data["task_name"],
                total_cases=data["total_cases"],
                checkpoint_dir=checkpoint_dir,
                completed_case_ids=set(data.get("completed_case_ids", [])),
                metrics_snapshot=data.get("metrics_snapshot", {}),
                started_at=data.get("started_at", datetime.now().isoformat()),
                last_completed_at=data.get("last_completed_at"),
            )
        except Exception:
            return None

    @classmethod
    def load_or_create(
        cls,
        task_name: str,
        total_cases: int,
        checkpoint_dir: Optional[Path] = None,
    ) -> "BatchCheckpoint":
        """Load existing checkpoint or create new one.

        Args:
            task_name: The task name
            total_cases: Total number of cases (used only if creating new)
            checkpoint_dir: Optional custom checkpoint directory

        Returns:
            BatchCheckpoint (existing or new)
        """
        existing = cls.load(task_name, checkpoint_dir)
        if existing:
            return existing
        return cls(
            task_name=task_name,
            total_cases=total_cases,
            checkpoint_dir=checkpoint_dir or CHECKPOINT_DIR,
        )

    def clear(self) -> None:
        """Clear checkpoint (start fresh)."""
        self.completed_case_ids.clear()
        self.metrics_snapshot.clear()
        self.results_buffer.clear()
        self.last_completed_at = None
        self.started_at = datetime.now().isoformat()

        # Remove files
        if self._checkpoint_file.exists():
            self._checkpoint_file.unlink()
        if self._results_file.exists():
            self._results_file.unlink()

    def finalize(self, success: bool = True) -> Dict[str, Any]:
        """Finalize the checkpoint and return summary.

        Args:
            success: Whether the batch completed successfully

        Returns:
            Summary dict with completion info
        """
        summary = {
            "task_name": self.task_name,
            "total_cases": self.total_cases,
            "completed": len(self.completed_case_ids),
            "success": success,
            "started_at": self.started_at,
            "finished_at": datetime.now().isoformat(),
            "metrics": self.metrics_snapshot,
            "checkpoint_file": str(self._checkpoint_file),
            "results_file": str(self._results_file),
        }

        # Save final state
        self._save_checkpoint()

        return summary

    @property
    def progress_pct(self) -> float:
        """Get completion percentage."""
        if self.total_cases == 0:
            return 100.0
        return len(self.completed_case_ids) / self.total_cases * 100

    @property
    def remaining_count(self) -> int:
        """Get number of remaining cases."""
        return self.total_cases - len(self.completed_case_ids)


def get_checkpoint_file(task_name: str, checkpoint_dir: Optional[Path] = None) -> Path:
    """Get the checkpoint file path for a task."""
    checkpoint_dir = checkpoint_dir or CHECKPOINT_DIR
    return checkpoint_dir / f"{task_name}.checkpoint.json"


def list_checkpoints(checkpoint_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """List all available checkpoints.

    Returns:
        List of checkpoint summaries
    """
    checkpoint_dir = checkpoint_dir or CHECKPOINT_DIR
    if not checkpoint_dir.exists():
        return []

    checkpoints = []
    for f in checkpoint_dir.glob("*.checkpoint.json"):
        try:
            data = json.loads(f.read_text())
            checkpoints.append({
                "task_name": data["task_name"],
                "completed": data.get("completed_count", len(data.get("completed_case_ids", []))),
                "total": data["total_cases"],
                "last_updated": data.get("last_completed_at"),
                "file": str(f),
            })
        except Exception:
            continue

    return sorted(checkpoints, key=lambda x: x.get("last_updated") or "", reverse=True)
