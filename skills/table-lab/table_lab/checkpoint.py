"""Checkpoint/resume for batch table tuning.

Pattern: prompt-lab's batch_checkpoint.py.
Atomic saves ensure no data loss on interruption.
NDJSON results enable streaming analysis.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from .config import CHECKPOINT_DIR, RESULTS_DIR


@dataclass
class TuneCheckpoint:
    """Tracks batch tuning progress with resume capability."""

    task_name: str
    total_pdfs: int
    completed_pdfs: set[str] = field(default_factory=set)
    metrics_snapshot: dict[str, float] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def checkpoint_path(self) -> Path:
        return CHECKPOINT_DIR / f"{self.task_name}.json"

    @property
    def results_path(self) -> Path:
        return RESULTS_DIR / f"{self.task_name}.jsonl"

    def is_completed(self, pdf_name: str) -> bool:
        """Check if a PDF has already been tuned."""
        return pdf_name in self.completed_pdfs

    def mark_completed(
        self,
        pdf_name: str,
        result: dict | None = None,
        metrics: dict[str, float] | None = None,
    ) -> None:
        """Mark a PDF as completed and save atomically.

        Also appends the result to the NDJSON results file.
        """
        self.completed_pdfs.add(pdf_name)
        if metrics:
            self.metrics_snapshot.update(metrics)

        # Append result to NDJSON
        if result:
            result["_completed_at"] = datetime.now(timezone.utc).isoformat()
            RESULTS_DIR.mkdir(parents=True, exist_ok=True)
            with open(self.results_path, "a") as f:
                f.write(json.dumps(result) + "\n")

        # Save checkpoint atomically
        self._save()

    def _save(self) -> None:
        """Atomic save of checkpoint state."""
        CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "task_name": self.task_name,
            "total_pdfs": self.total_pdfs,
            "completed_pdfs": sorted(self.completed_pdfs),
            "completed_count": len(self.completed_pdfs),
            "metrics_snapshot": self.metrics_snapshot,
            "created_at": self.created_at,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        tmp = self.checkpoint_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.rename(self.checkpoint_path)

    @classmethod
    def load_or_create(cls, task_name: str, total_pdfs: int) -> TuneCheckpoint:
        """Load existing checkpoint or create new one (idempotent)."""
        path = CHECKPOINT_DIR / f"{task_name}.json"
        if path.exists():
            try:
                data = json.loads(path.read_text())
                cp = cls(
                    task_name=data["task_name"],
                    total_pdfs=total_pdfs,
                    completed_pdfs=set(data.get("completed_pdfs", [])),
                    metrics_snapshot=data.get("metrics_snapshot", {}),
                    created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
                )
                logger.info(
                    f"Resumed checkpoint '{task_name}': "
                    f"{len(cp.completed_pdfs)}/{total_pdfs} completed"
                )
                return cp
            except (json.JSONDecodeError, KeyError, OSError) as exc:
                logger.warning(f"Failed to load checkpoint, creating new: {exc}")

        cp = cls(task_name=task_name, total_pdfs=total_pdfs)
        logger.info(f"Created new checkpoint '{task_name}' for {total_pdfs} PDFs")
        return cp

    def finalize(self) -> dict:
        """Finalize the checkpoint and return summary."""
        summary = {
            "task_name": self.task_name,
            "total_pdfs": self.total_pdfs,
            "completed_count": len(self.completed_pdfs),
            "skipped_count": self.total_pdfs - len(self.completed_pdfs),
            "metrics_snapshot": self.metrics_snapshot,
            "results_file": str(self.results_path),
            "finalized_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save()
        logger.info(
            f"Finalized checkpoint '{self.task_name}': "
            f"{len(self.completed_pdfs)}/{self.total_pdfs} completed"
        )
        return summary
