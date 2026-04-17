"""Thin wrapper around shared TaskClient for ingest-youtube skill.

Preserves the IngestYoutubeTaskClient interface and convenience functions.
Domain-specific tracking (methods, rate limits) stored in TaskClient.stats.
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
ERROR_LOG = SKILL_DIR / "ingest_youtube_errors.json"


@dataclass
class MethodMetrics:
    attempts: int = 0
    successes: int = 0

    @property
    def rate(self) -> float:
        return self.successes / self.attempts if self.attempts > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {"attempts": self.attempts, "successes": self.successes, "rate": round(self.rate, 4)}


@dataclass
class FailureRecord:
    video_id: str
    error: str
    method_tried: str
    is_rate_limit: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "video_id": self.video_id,
            "error": self.error[:100],
            "method_tried": self.method_tried,
            "is_rate_limit": self.is_rate_limit,
            "timestamp": self.timestamp,
        }


class IngestYoutubeTaskClient:
    """Task-monitor compatible progress tracker for ingest-youtube.

    Delegates core registration/state to shared TaskClient; adds
    YouTube-specific metrics on top.
    """

    def __init__(
        self,
        task_name: str,
        total_videos: int,
        description: Optional[str] = None,
        register: bool = True,
    ):
        self.task_name = task_name
        self.total_videos = total_videos
        desc = description or f"Ingest-YouTube: {task_name}"

        self._client = TaskClient(
            skill_name=f"ingest-youtube:{task_name}",
            total=total_videos,
            description=desc,
            state_dir=str(SKILL_DIR),
            register=register,
        )

        self.methods: Dict[str, MethodMetrics] = {}
        self.failures: List[FailureRecord] = []
        self.success_count = 0
        self.skipped_count = 0
        self.rate_limit_count = 0

    @property
    def completed(self) -> int:
        return self._client.completed

    def update(
        self,
        video_id: str,
        success: bool,
        method: Optional[str] = None,
        error: Optional[str] = None,
        is_rate_limit: bool = False,
        skipped: bool = False,
    ):
        if skipped:
            self.skipped_count += 1
        elif success:
            self.success_count += 1
            if method:
                if method not in self.methods:
                    self.methods[method] = MethodMetrics()
                self.methods[method].attempts += 1
                self.methods[method].successes += 1
        else:
            if is_rate_limit:
                self.rate_limit_count += 1
            if method:
                if method not in self.methods:
                    self.methods[method] = MethodMetrics()
                self.methods[method].attempts += 1
            self.failures.append(FailureRecord(
                video_id=video_id,
                error=error or "Unknown error",
                method_tried=method or "unknown",
                is_rate_limit=is_rate_limit,
            ))

        success_rate = self.success_count / (self._client.completed + 1) if (self._client.completed + 1) > 0 else 0
        self._client.update(
            item=video_id,
            success_count=self.success_count,
            failure_count=len(self.failures),
            skipped_count=self.skipped_count,
            rate_limit_count=self.rate_limit_count,
            success_rate=round(success_rate, 4),
        )

    def finish(self, success: bool = True):
        self._client.finish(success=success)

        if self.failures:
            try:
                error_data = {
                    "task_name": self.task_name,
                    "completed_at": datetime.now().isoformat(),
                    "success": success,
                    "total_videos": self.total_videos,
                    "total_failures": len(self.failures),
                    "methods": {n: m.to_dict() for n, m in self.methods.items()},
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
            "success_rate": self.success_count / self._client.completed if self._client.completed > 0 else 0,
            "failures": len(self.failures),
            "rate_limits": self.rate_limit_count,
        })
        return summary


# Convenience functions
_current_client: Optional[IngestYoutubeTaskClient] = None


def start_monitoring(task_name: str, total_videos: int) -> IngestYoutubeTaskClient:
    global _current_client
    _current_client = IngestYoutubeTaskClient(task_name, total_videos)
    return _current_client


def get_monitor() -> Optional[IngestYoutubeTaskClient]:
    return _current_client


def end_monitoring(success: bool = True):
    global _current_client
    if _current_client:
        _current_client.finish(success)
        _current_client = None
