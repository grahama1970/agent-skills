"""Thin wrapper around shared TaskClient for embedding skill.

Preserves the EmbeddingTaskClient interface and convenience functions.
Domain-specific tracking (batches, vectors, dimensions, failures) stored in
TaskClient.stats for task-monitor TUI display.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from common.task_monitor import TaskClient

SKILL_DIR = Path(__file__).parent
ERROR_LOG = SKILL_DIR / "embedding_errors.json"


@dataclass
class FailureRecord:
    """Record of an embedding failure."""
    batch_index: int
    error: str
    texts_affected: int
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "batch_index": self.batch_index,
            "error": self.error[:100],
            "texts_affected": self.texts_affected,
            "timestamp": self.timestamp,
        }


class EmbeddingTaskClient:
    """Task-monitor compatible progress tracker for embedding.

    Delegates core registration/state to shared TaskClient; adds
    embedding-specific metrics on top.
    """

    def __init__(
        self,
        task_name: str,
        total_texts: int,
        description: Optional[str] = None,
        register: bool = True,
    ):
        self.task_name = task_name
        self.total_texts = total_texts
        desc = description or f"Embedding: {task_name}"

        self._client = TaskClient(
            skill_name=f"embedding:{task_name}",
            total=total_texts,
            description=desc,
            state_dir=str(SKILL_DIR),
            register=register,
        )

        # Domain-specific metrics
        self.batches_processed = 0
        self.vectors_generated = 0
        self.total_dimensions = 0
        self.failures: List[FailureRecord] = []

    @property
    def completed(self) -> int:
        return self._client.completed

    def update(
        self,
        texts_processed: int,
        success: bool = True,
        dimensions: int = 0,
        error: Optional[str] = None,
    ):
        self.batches_processed += 1

        if success:
            self.vectors_generated += texts_processed
            if dimensions and not self.total_dimensions:
                self.total_dimensions = dimensions
        else:
            self.failures.append(FailureRecord(
                batch_index=self.batches_processed,
                error=error or "Unknown error",
                texts_affected=texts_processed,
            ))

        self._client.update(
            n=texts_processed,
            item=f"text {self._client.completed + texts_processed}/{self.total_texts}",
            batches_processed=self.batches_processed,
            vectors_generated=self.vectors_generated,
            failure_count=len(self.failures),
            dimensions=self.total_dimensions,
        )

    def finish(self, success: bool = True):
        self._client.finish(success=success)

        if self.failures:
            try:
                error_data = {
                    "task_name": self.task_name,
                    "completed_at": datetime.now().isoformat(),
                    "success": success,
                    "total_texts": self.total_texts,
                    "total_failures": len(self.failures),
                    "failures": [f.to_dict() for f in self.failures],
                }
                tmp = ERROR_LOG.with_suffix(".tmp")
                tmp.write_text(json.dumps(error_data, indent=2))
                os.replace(tmp, ERROR_LOG)
            except Exception:
                pass

    def get_summary(self) -> Dict[str, Any]:
        summary = self._client.get_summary()
        summary.update({
            "vectors_generated": self.vectors_generated,
            "failures": len(self.failures),
        })
        return summary


# Convenience functions
_current_client: Optional[EmbeddingTaskClient] = None


def start_monitoring(task_name: str, total_texts: int) -> EmbeddingTaskClient:
    global _current_client
    _current_client = EmbeddingTaskClient(task_name, total_texts)
    return _current_client


def get_monitor() -> Optional[EmbeddingTaskClient]:
    return _current_client


def end_monitoring(success: bool = True):
    global _current_client
    if _current_client:
        _current_client.finish(success)
        _current_client = None
