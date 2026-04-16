"""Thin wrapper around shared TaskClient for debug-pdf skill.

Preserves the DebugPdfTaskClient interface and convenience functions.
Domain-specific tracking (patterns, downloads, fixtures) stored in TaskClient.stats.
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
ERROR_LOG = SKILL_DIR / "debug_pdf_errors.json"


@dataclass
class PatternMetrics:
    detected: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {"detected": self.detected}


@dataclass
class FailureRecord:
    url: str
    error: str
    patterns_detected: List[str]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url[:100],
            "error": self.error[:100],
            "patterns": self.patterns_detected[:5],
            "timestamp": self.timestamp,
        }


class DebugPdfTaskClient:
    """Task-monitor compatible progress tracker for debug-pdf.

    Delegates core registration/state to shared TaskClient; adds
    PDF-specific metrics on top.
    """

    def __init__(
        self,
        task_name: str,
        total_pdfs: int,
        description: Optional[str] = None,
        register: bool = True,
    ):
        self.task_name = task_name
        self.total_pdfs = total_pdfs
        desc = description or f"Debug-PDF: {task_name}"

        self._client = TaskClient(
            skill_name=f"debug-pdf:{task_name}",
            total=total_pdfs,
            description=desc,
            state_dir=str(SKILL_DIR),
            register=register,
        )

        self.patterns: Dict[str, PatternMetrics] = {}
        self.download_success = 0
        self.download_failed = 0
        self.fixtures_generated = 0
        self.total_pages_analyzed = 0
        self.failures: List[FailureRecord] = []

    @property
    def completed(self) -> int:
        return self._client.completed

    def update(
        self,
        url: str,
        download_success: bool,
        patterns_detected: List[str],
        pages: int = 0,
        fixture_generated: bool = False,
        error: Optional[str] = None,
    ):
        if download_success:
            self.download_success += 1
        else:
            self.download_failed += 1

        if fixture_generated:
            self.fixtures_generated += 1

        self.total_pages_analyzed += pages

        for pattern in patterns_detected:
            if pattern not in self.patterns:
                self.patterns[pattern] = PatternMetrics()
            self.patterns[pattern].detected += 1

        if not download_success or error:
            self.failures.append(FailureRecord(
                url=url, error=error or "Download failed",
                patterns_detected=patterns_detected,
            ))

        total_downloads = self.download_success + self.download_failed
        download_rate = self.download_success / total_downloads if total_downloads > 0 else 0.0

        self._client.update(
            item=url[:80],
            download_success=self.download_success,
            download_failed=self.download_failed,
            download_rate=round(download_rate, 4),
            fixtures_generated=self.fixtures_generated,
            total_pages=self.total_pages_analyzed,
            unique_patterns=len(self.patterns),
        )

    def finish(self, success: bool = True):
        self._client.finish(success=success)

        if self.failures:
            try:
                error_data = {
                    "task_name": self.task_name,
                    "completed_at": datetime.now().isoformat(),
                    "success": success,
                    "total_pdfs": self.total_pdfs,
                    "total_failures": len(self.failures),
                    "patterns": {n: m.to_dict() for n, m in self.patterns.items()},
                    "failures": [f.to_dict() for f in self.failures],
                }
                tmp = ERROR_LOG.with_suffix(".tmp")
                tmp.write_text(json.dumps(error_data, indent=2))
                os.replace(tmp, ERROR_LOG)
            except Exception:
                pass

    def get_summary(self) -> Dict[str, Any]:
        summary = self._client.get_summary()
        total_downloads = self.download_success + self.download_failed
        summary.update({
            "download_rate": self.download_success / total_downloads if total_downloads > 0 else 0,
            "fixtures_generated": self.fixtures_generated,
            "unique_patterns": len(self.patterns),
        })
        return summary


# Convenience functions
_current_client: Optional[DebugPdfTaskClient] = None


def start_monitoring(task_name: str, total_pdfs: int) -> DebugPdfTaskClient:
    global _current_client
    _current_client = DebugPdfTaskClient(task_name, total_pdfs)
    return _current_client


def get_monitor() -> Optional[DebugPdfTaskClient]:
    return _current_client


def end_monitoring(success: bool = True):
    global _current_client
    if _current_client:
        _current_client.finish(success)
        _current_client = None
