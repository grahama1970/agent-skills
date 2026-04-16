"""Thin wrapper around shared TaskClient for debug-fetcher skill.

Preserves the DebugFetcherTaskClient interface and convenience functions.
Domain-specific tracking (strategies, learned count) stored in TaskClient.stats.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from common.task_monitor import TaskClient

SKILL_DIR = Path(__file__).parent.parent
ERROR_LOG = SKILL_DIR / "debug_fetcher_errors.json"


@dataclass
class StrategyMetrics:
    attempts: int = 0
    successes: int = 0

    @property
    def rate(self) -> float:
        return self.successes / self.attempts if self.attempts > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {"attempts": self.attempts, "successes": self.successes, "rate": round(self.rate, 4)}


@dataclass
class FailureRecord:
    url: str
    strategy: str
    error: str
    attempts: int
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url[:100],
            "strategy": self.strategy,
            "error": self.error[:100],
            "attempts": self.attempts,
            "timestamp": self.timestamp,
        }


class DebugFetcherTaskClient:
    """Task-monitor compatible progress tracker for debug-fetcher.

    Delegates core registration/state to shared TaskClient; adds
    fetcher-specific metrics on top.
    """

    def __init__(
        self,
        task_name: str,
        total_urls: int,
        description: Optional[str] = None,
        register: bool = True,
    ):
        self.task_name = task_name
        self.total_urls = total_urls
        desc = description or f"Debug-Fetcher: {task_name}"

        self._client = TaskClient(
            skill_name=f"debug-fetcher:{task_name}",
            total=total_urls,
            description=desc,
            state_dir=str(SKILL_DIR),
            register=register,
        )

        self.strategies: Dict[str, StrategyMetrics] = {}
        self.failures: List[FailureRecord] = []
        self.success_count = 0
        self.learned_count = 0

    @property
    def completed(self) -> int:
        return self._client.completed

    def update(
        self,
        url: str,
        success: bool,
        winning_strategy: str,
        attempts: int,
        error: Optional[str] = None,
        used_learned: bool = False,
    ):
        if success:
            self.success_count += 1
        if used_learned:
            self.learned_count += 1

        if winning_strategy not in self.strategies:
            self.strategies[winning_strategy] = StrategyMetrics()
        self.strategies[winning_strategy].attempts += 1
        if success:
            self.strategies[winning_strategy].successes += 1

        if not success:
            self.failures.append(FailureRecord(
                url=url, strategy=winning_strategy,
                error=error or "Unknown error", attempts=attempts,
            ))

        success_rate = self.success_count / (self._client.completed + 1)
        self._client.update(
            item=url[:80],
            success_count=self.success_count,
            failure_count=len(self.failures),
            success_rate=round(success_rate, 4),
            learned_count=self.learned_count,
        )

    def finish(self, success: bool = True):
        self._client.finish(success=success)

        if self.failures:
            try:
                error_data = {
                    "task_name": self.task_name,
                    "completed_at": datetime.now().isoformat(),
                    "success": success,
                    "total_urls": self.total_urls,
                    "total_failures": len(self.failures),
                    "strategies": {n: m.to_dict() for n, m in self.strategies.items()},
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
            "learned_count": self.learned_count,
        })
        return summary


# Convenience functions
_current_client: Optional[DebugFetcherTaskClient] = None


def start_monitoring(task_name: str, total_urls: int) -> DebugFetcherTaskClient:
    global _current_client
    _current_client = DebugFetcherTaskClient(task_name, total_urls)
    return _current_client


def get_monitor() -> Optional[DebugFetcherTaskClient]:
    return _current_client


def end_monitoring(success: bool = True):
    global _current_client
    if _current_client:
        _current_client.finish(success)
        _current_client = None
