#!/usr/bin/env python3
"""Task Monitor Integration for Monitor-PDFs.

Thin wrapper around shared TaskClient. Preserves PDFMonitorTracker interface.
"""
from pathlib import Path
from typing import Dict, List

from common.task_monitor import TaskClient

STATE_DIR = Path.home() / ".pi" / "monitor-pdfs"


class PDFMonitorTracker:
    """Task-monitor compatible tracker for PDF harvesting and processing."""

    def __init__(self, name: str = "pdf-monitor"):
        self.name = name
        STATE_DIR.mkdir(parents=True, exist_ok=True)

        self._client = TaskClient(
            skill_name=name,
            total=1,
            description="PDF Harvesting & Processing Dashboard",
            state_dir=str(STATE_DIR),
            register=True,
        )

    def report_progress(self, harvest_stats: List[Dict], batch_stats: Dict, image_stats: Dict):
        """Update task-monitor state file with current metrics."""
        total_pdfs = batch_stats.get("total", 11394)
        processed_pdfs = batch_stats.get("current", 0)
        harvest_count = sum(h["count"] for h in harvest_stats)

        self._client.set_total(total_pdfs)

        # Set completed directly
        delta = processed_pdfs - self._client.completed
        if delta > 0:
            self._client.update(
                n=delta,
                item=f"batch {processed_pdfs}/{total_pdfs}",
                harvested_pdfs=harvest_count,
                batch_processed=processed_pdfs,
                extracted_images=image_stats.get("total", 0),
                arxiv_progress=next(
                    (f"{h['current']}/{h['target']}" for h in harvest_stats if h["name"] == "Arxiv"),
                    "0/0",
                ),
            )
        else:
            self._client.heartbeat(item=f"batch {processed_pdfs}/{total_pdfs}")
