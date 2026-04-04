#!/usr/bin/env python3
"""
Monitor PDFs - Tracking dashboard for harvesting and processing.

Usage:
    python monitor.py dashboard
    python monitor.py harvest
    python monitor.py batch
    python monitor.py images
"""

import os
import re
import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, BarColumn, TextColumn, TaskProgressColumn
from rich.live import Live
from rich.layout import Layout

from task_monitor_integration import PDFMonitorTracker
from loguru import logger

console = Console()
app = typer.Typer(help="Monitoring dashboard for PDF harvesting and processing")

# Paths (adjust to environment)
_SKILLS_DIR = Path(__file__).resolve().parent.parent
_EMBRY_STORAGE = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb"))
CORPUS_ROOT = Path(os.environ.get("EXTRACTOR_CORPUS", str(_EMBRY_STORAGE / "extractor_corpus")))
BATCH_RESULTS = CORPUS_ROOT / "results/s00_batch_full"
TRAINING_DATA_ROOT = _SKILLS_DIR / "create-classifier" / "data"
EXTRACTOR_DIR = _SKILLS_DIR.parent.parent.parent / "extractor"

# Logs
LOGS = {
    "batch": EXTRACTOR_DIR / "batch_full.log",
    "arxiv": EXTRACTOR_DIR / "arxiv_download.log",
    "archive": EXTRACTOR_DIR / "archive_download.log",
    "industry": EXTRACTOR_DIR / "industry_download.log",
    "dataset": EXTRACTOR_DIR / "dataset_inbox.log",
}

def get_file_count(path: Path, pattern: str = "*.pdf") -> int:
    """Count files in a directory matching pattern."""
    if not path.exists():
        return 0
    return len(list(path.glob(pattern)))

def parse_progress_from_log(log_path: Path, pattern: str) -> Dict:
    """Parse progress (X/Y) from the last line of a log file matching pattern."""
    if not log_path.exists():
        return {"current": 0, "total": 0, "percent": 0}
    
    try:
        content = log_path.read_text().splitlines()
        for line in reversed(content):
            match = re.search(pattern, line)
            if match:
                groups = match.groups()
                if len(groups) >= 2:
                    current = int(groups[0])
                    total = int(groups[1])
                    return {
                        "current": current,
                        "total": total,
                        "percent": (current / total * 100) if total > 0 else 0
                    }
    except Exception as e:
        logger.debug("value lookup failed: {}", e)
    return {"current": 0, "total": 0, "percent": 0}

def get_harvest_stats():
    """Get stats for different harvest sources."""
    sources = {
        "Arxiv": {
            "path": CORPUS_ROOT / "arxiv",
            "log": LOGS["arxiv"],
            "log_pattern": r"Progress: (\d+)/(\d+)",
        },
        "Archive.org": {
            "path": CORPUS_ROOT / "archive_org",
            "log": LOGS["archive"],
            "log_pattern": r"Collected (\d+) archive.org documents", # This log format varies
        },
        "Industry": {
            "path": CORPUS_ROOT / "industry",
            "log": LOGS["industry"],
            "log_pattern": r"Progress: (\d+)/(\d+)",
        },
        "DTIC/GPO": {
            "path": CORPUS_ROOT / "defense", # defense dir often used for DTIC
            "log": None,
        }
    }
    
    results = []
    for name, cfg in sources.items():
        count = get_file_count(cfg["path"])
        progress = {"current": 0, "total": 0}
        if cfg["log"]:
            progress = parse_progress_from_log(cfg["log"], cfg["log_pattern"])
        
        results.append({
            "name": name,
            "count": count,
            "target": progress.get("total", 0),
            "current": progress.get("current", 0),
        })
    return results

def get_batch_stats():
    """Get batch processing stats."""
    # Batch log progress: Progress: 400/11394
    progress = parse_progress_from_log(LOGS["batch"], r"Progress: (\d+)/(\d+)")
    
    # Also verify via filesystem
    result_count = 0
    if BATCH_RESULTS.exists():
        # Count profile.json files
        # find . -name "profile.json" | wc -l is faster, but let's try globbing
        # actually for 11k files, glob might be slow.
        pass
    
    return progress

def get_image_stats():
    """Get image extraction stats."""
    inbox_count = get_file_count(TRAINING_DATA_ROOT / "dataset_inbox", "**/*.jpg")
    corpus_count = get_file_count(TRAINING_DATA_ROOT / "dataset_corpus", "**/*.jpg")
    
    progress = parse_progress_from_log(LOGS["dataset"], r"Processed (\d+)/(\d+)")
    
    return {
        "inbox": inbox_count,
        "corpus": corpus_count,
        "total": inbox_count + corpus_count,
        "progress": progress
    }

@app.command()
def dashboard():
    """Show the full tracking dashboard."""
    harvest = get_harvest_stats()
    batch = get_batch_stats()
    images = get_image_stats()
    
    # Report to task-monitor
    tracker = PDFMonitorTracker()
    tracker.report_progress(harvest, batch, images)
    
    # 1. Harvest Table
    harvest_table = Table(title="PDF Harvesting Status", box=None)
    harvest_table.add_column("Source", style="cyan")
    harvest_table.add_column("Files", justify="right", style="green")
    harvest_table.add_column("Target Progress", justify="right", style="yellow")
    
    for h in harvest:
        prog_str = f"{h['current']}/{h['target']}" if h['target'] > 0 else "-"
        harvest_table.add_row(h["name"], str(h["count"]), prog_str)
    
    # 2. Batch Processing Panel
    batch_percent = batch["percent"]
    batch_panel = Panel(
        f"[bold blue]Full Corpus Batch S00 Classification[/]\n"
        f"Progress: [green]{batch['current']}[/] / [white]{batch['total']}[/]\n"
        f"Completion: [bold yellow]{batch_percent:.1f}%[/]",
        border_style="blue"
    )
    
    # 3. Vision Data Panel
    image_progress = images["progress"]
    image_panel = Panel(
        f"[bold magenta]Vision Training Data (Image Extraction)[/]\n"
        f"Inbox Images: [green]{images['inbox']}[/]\n"
        f"Corpus Images: [green]{images['corpus']}[/]\n"
        f"Extraction: [yellow]{image_progress['current']}[/] / [white]{image_progress['total']}[/]",
        border_style="magenta"
    )
    
    # Layout
    layout = Layout()
    layout.split_column(
        Layout(Panel(harvest_table, border_style="cyan"), name="harvest", ratio=2),
        Layout(batch_panel, name="batch", ratio=1),
        Layout(image_panel, name="images", ratio=1)
    )
    
    console.print(Panel(layout, title="[bold white]Extractor Pipeline Monitor[/]", border_style="white", height=25))

@app.command()
def harvest():
    """Monitor harvest sources only."""
    stats = get_harvest_stats()
    table = Table(title="PDF Harvesting Status")
    table.add_column("Source")
    table.add_column("Files")
    table.add_column("Progress")
    for s in stats:
        table.add_row(s["name"], str(s["count"]), f"{s['current']}/{s['target']}" if s['target'] > 0 else "-")
    console.print(table)

@app.command()
def batch():
    """Monitor batch processing only."""
    stats = get_batch_stats()
    console.print(f"Batch Progress: {stats['current']}/{stats['total']} ({stats['percent']:.1f}%)")

@app.command()
def images():
    """Monitor image extraction only."""
    stats = get_image_stats()
    console.print(f"Total Images: {stats['total']}")
    console.print(f"Inbox: {stats['inbox']}, Corpus: {stats['corpus']}")

@app.command()
def logs(
    name: str = typer.Argument("batch", help="Log name: batch, arxiv, archive, industry, dataset"),
    tail: int = typer.Option(10, "--tail", "-t", help="Number of lines to show")
):
    """View tail of specific logs."""
    log_path = LOGS.get(name)
    if not log_path or not log_path.exists():
        console.print(f"[red]Log not found: {name}[/]")
        return
    
    console.print(f"[bold cyan]--- Tail of {name} log ({log_path.name}) ---[/]")
    content = log_path.read_text().splitlines()
    for line in content[-tail:]:
        console.print(line)

@app.command()
def watchdog():
    """Start the watchdog loop (runs in background)."""
    import watchdog as wd
    wd.start()

if __name__ == "__main__":
    app()
