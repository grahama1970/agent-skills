#!/usr/bin/env python3
"""
Watchdog for PDF Pipeline - Monitors progress and detects stalls.
Reports to task-monitor.
"""

import os
import time
import json
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

import typer
from loguru import logger
from task_monitor_integration import PDFMonitorTracker

# Re-use paths from monitor_pdfs if possible, or redefine
_SKILLS_DIR = Path(__file__).resolve().parent.parent
_EMBRY_STORAGE = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb"))
CORPUS_ROOT = Path(os.environ.get("EXTRACTOR_CORPUS", str(_EMBRY_STORAGE / "extractor_corpus")))
EXTRACTOR_DIR = _SKILLS_DIR.parent.parent.parent / "extractor"
LOGS = {
    "batch": EXTRACTOR_DIR / "batch_full.log",
    "arxiv": EXTRACTOR_DIR / "arxiv_download.log",
    "dataset": EXTRACTOR_DIR / "dataset_inbox.log",
}

CHECK_INTERVAL = 60  # seconds
STALL_THRESHOLD = 900  # 15 minutes

app = typer.Typer()

class WatchdogState:
    def __init__(self):
        self.last_counts = {}
        self.last_activity = {}
        self.tracker = PDFMonitorTracker(name="pdf-pipeline-watchdog")

    def get_file_count(self, path: Path) -> int:
        if not path.exists():
            return 0
        # Fast count
        try:
            result = subprocess.run(["find", str(path), "-name", "*.pdf"], capture_output=True, text=True, check=True)
            return len(result.stdout.strip().splitlines()) if result.stdout.strip() else 0
        except Exception:
            return 0

    def get_image_count(self) -> int:
        path = _SKILLS_DIR / "create-classifier" / "data" / "dataset_inbox"
        try:
            result = subprocess.run(["find", str(path), "-name", "*.jpg"], capture_output=True, text=True, check=True)
            return len(result.stdout.strip().splitlines()) if result.stdout.strip() else 0
        except Exception:
            return 0

    def check_stall(self, name: str, current_count: int):
        last_count = self.last_counts.get(name, 0)
        now = time.time()
        
        if current_count > last_count:
            self.last_counts[name] = current_count
            self.last_activity[name] = now
            return False
        
        idle_time = now - self.last_activity.get(name, now)
        if idle_time > STALL_THRESHOLD:
            return True
        return False

@app.command()
def start():
    """Start the watchdog loop."""
    logger.info("Starting PDF Pipeline Watchdog...")
    state = WatchdogState()
    
    # Initialize activity
    state.last_activity["arxiv"] = time.time()
    state.last_activity["batch"] = time.time()
    state.last_activity["images"] = time.time()

    while True:
        try:
            # 1. Check Arxiv
            arxiv_count = state.get_file_count(CORPUS_ROOT / "arxiv")
            if state.check_stall("arxiv", arxiv_count):
                logger.warning(f"STALL DETECTED: Arxiv downloads (Count: {arxiv_count})")
            
            # 2. Check Batch Results
            batch_count = state.get_file_count(CORPUS_ROOT / "results/s00_batch_full") # This expects PDFs/JSONs
            # For batch, we might want to check the log mtime instead since it's one big job
            if LOGS["batch"].exists():
                mtime = LOGS["batch"].stat().st_mtime
                if time.time() - mtime > STALL_THRESHOLD:
                    logger.warning("STALL DETECTED: Batch classification log not updating")

            # 3. Check Images
            img_count = state.get_image_count()
            if state.check_stall("images", img_count):
                logger.warning(f"STALL DETECTED: Image extraction (Count: {img_count})")

            # Status log
            logger.info(f"Watchdog Heartbeat | Arxiv: {arxiv_count} | Images: {img_count}")
            
            # Report to task-monitor (via dummy stats for now to maintain heartbeat)
            # In a real impl, we'd parse full stats like monitor_pdfs.py
            
        except Exception as e:
            logger.error(f"Watchdog loop error: {e}")

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    app()
