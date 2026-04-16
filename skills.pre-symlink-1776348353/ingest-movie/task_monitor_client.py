"""Thin wrapper around shared TaskClient for ingest-movie skill.

Preserves the IngestMovieTaskClient interface and convenience functions.
Domain-specific tracking (emotions, per-movie status) stored in TaskClient.stats.
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
ERROR_LOG = SKILL_DIR / "ingest_movie_errors.json"


@dataclass
class EmotionMetrics:
    processed: int = 0
    skipped: int = 0
    failed: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {"processed": self.processed, "skipped": self.skipped, "failed": self.failed}


@dataclass
class FailureRecord:
    movie_title: str
    emotion: str
    error: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "movie_title": self.movie_title[:50],
            "emotion": self.emotion,
            "error": self.error[:100],
            "timestamp": self.timestamp,
        }


class IngestMovieTaskClient:
    """Task-monitor compatible progress tracker for ingest-movie.

    Delegates core registration/state to shared TaskClient; adds
    movie/emotion-specific metrics on top.
    """

    def __init__(
        self,
        task_name: str,
        total_tasks: int,
        description: Optional[str] = None,
        register: bool = True,
    ):
        self.task_name = task_name
        self.total_tasks = total_tasks
        desc = description or f"Ingest-Movie: {task_name}"

        self._client = TaskClient(
            skill_name=f"ingest-movie:{task_name}",
            total=total_tasks,
            description=desc,
            state_dir=str(SKILL_DIR),
            register=register,
        )

        self.emotions: Dict[str, EmotionMetrics] = {}
        self.failures: List[FailureRecord] = []
        self.processed_count = 0
        self.skipped_count = 0

    @property
    def completed(self) -> int:
        return self._client.completed

    def update(
        self,
        movie_title: str,
        emotion: str,
        processed: bool = False,
        skipped: bool = False,
        error: Optional[str] = None,
    ):
        if emotion not in self.emotions:
            self.emotions[emotion] = EmotionMetrics()

        if processed:
            self.processed_count += 1
            self.emotions[emotion].processed += 1
        elif skipped:
            self.skipped_count += 1
            self.emotions[emotion].skipped += 1
        else:
            self.emotions[emotion].failed += 1
            self.failures.append(FailureRecord(
                movie_title=movie_title, emotion=emotion,
                error=error or "Unknown error",
            ))

        self._client.update(
            item=f"{movie_title[:40]} ({emotion})",
            processed_count=self.processed_count,
            skipped_count=self.skipped_count,
            failure_count=len(self.failures),
        )

    def finish(self, success: bool = True):
        self._client.finish(success=success)

        if self.failures:
            try:
                error_data = {
                    "task_name": self.task_name,
                    "completed_at": datetime.now().isoformat(),
                    "success": success,
                    "total_tasks": self.total_tasks,
                    "total_failures": len(self.failures),
                    "emotions": {n: m.to_dict() for n, m in self.emotions.items()},
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
            "processed": self.processed_count,
            "skipped": self.skipped_count,
            "failures": len(self.failures),
        })
        return summary


# Convenience functions
_current_client: Optional[IngestMovieTaskClient] = None


def start_monitoring(task_name: str, total_tasks: int) -> IngestMovieTaskClient:
    global _current_client
    _current_client = IngestMovieTaskClient(task_name, total_tasks)
    return _current_client


def get_monitor() -> Optional[IngestMovieTaskClient]:
    return _current_client


def end_monitoring(success: bool = True):
    global _current_client
    if _current_client:
        _current_client.finish(success)
        _current_client = None
