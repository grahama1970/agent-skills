"""Rich progress reporting engine for YouTube transcript batch processing.

Provides real-time progress bars, stats, and status updates using the rich library.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich.text import Text


class VideoStatus(Enum):
    PENDING = "pending"
    FETCHING = "fetching"
    DOWNLOADING = "downloading"
    TRANSCRIBING = "transcribing"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class BatchStats:
    """Track batch processing statistics."""
    total: int = 0
    completed: int = 0
    success_direct: int = 0
    success_proxy: int = 0
    success_whisper: int = 0
    failed: int = 0
    skipped: int = 0
    rate_limited: int = 0
    start_time: float = field(default_factory=time.time)

    @property
    def success_total(self) -> int:
        return self.success_direct + self.success_proxy + self.success_whisper

    @property
    def elapsed(self) -> float:
        return time.time() - self.start_time

    @property
    def rate_per_hour(self) -> float:
        if self.elapsed < 1:
            return 0
        return (self.completed / self.elapsed) * 3600

    @property
    def eta_seconds(self) -> float:
        remaining = self.total - self.completed
        if self.completed == 0 or self.elapsed < 1:
            return 0
        return (remaining / self.completed) * self.elapsed


class ProgressReporter:
    """Rich progress reporting for YouTube transcript batch processing."""

    def __init__(self, total_videos: int, title: str = "YouTube Transcript Batch"):
        self.console = Console()
        self.stats = BatchStats(total=total_videos)
        self.title = title
        self.current_video: Optional[str] = None
        self.current_status: VideoStatus = VideoStatus.PENDING
        self.current_detail: str = ""

        # Main batch progress bar
        self.batch_progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=40),
            MofNCompleteColumn(),
            TextColumn("[cyan]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            TextColumn("ETA:"),
            TimeRemainingColumn(),
            console=self.console,
        )

        # Current video progress
        self.video_progress = Progress(
            SpinnerColumn(),
            TextColumn("[yellow]{task.description}"),
            BarColumn(bar_width=30),
            TextColumn("{task.fields[detail]}"),
            console=self.console,
        )

        self.batch_task: Optional[TaskID] = None
        self.video_task: Optional[TaskID] = None
        self.live: Optional[Live] = None

    def _create_stats_table(self) -> Table:
        """Create a table showing current statistics."""
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Label", style="dim")
        table.add_column("Value", style="bold")
        table.add_column("Label2", style="dim")
        table.add_column("Value2", style="bold")

        table.add_row(
            "Direct:", f"[green]{self.stats.success_direct}[/]",
            "Proxy:", f"[blue]{self.stats.success_proxy}[/]",
        )
        table.add_row(
            "Whisper:", f"[magenta]{self.stats.success_whisper}[/]",
            "Failed:", f"[red]{self.stats.failed}[/]",
        )
        table.add_row(
            "Skipped:", f"[dim]{self.stats.skipped}[/]",
            "Rate Limited:", f"[yellow]{self.stats.rate_limited}[/]",
        )
        table.add_row(
            "Rate:", f"[cyan]{self.stats.rate_per_hour:.1f}/hr[/]",
            "", "",
        )

        return table

    def _create_display(self) -> Group:
        """Create the full display layout."""
        # Current video status
        status_colors = {
            VideoStatus.PENDING: "dim",
            VideoStatus.FETCHING: "blue",
            VideoStatus.DOWNLOADING: "yellow",
            VideoStatus.TRANSCRIBING: "magenta",
            VideoStatus.SUCCESS: "green",
            VideoStatus.FAILED: "red",
        }
        color = status_colors.get(self.current_status, "white")

        current_text = Text()
        if self.current_video:
            current_text.append("Current: ", style="dim")
            current_text.append(self.current_video, style="bold")
            current_text.append(" → ", style="dim")
            current_text.append(self.current_status.value, style=color)
            if self.current_detail:
                current_text.append(f" ({self.current_detail})", style="dim")

        return Group(
            self.batch_progress,
            Text(""),
            current_text,
            self.video_progress,
            Text(""),
            self._create_stats_table(),
        )

    def start(self):
        """Start the progress display."""
        self.batch_task = self.batch_progress.add_task(
            self.title,
            total=self.stats.total,
        )
        self.video_task = self.video_progress.add_task(
            "Waiting...",
            total=100,
            detail="",
        )

        panel = Panel(
            self._create_display(),
            title="[bold]YouTube Transcript Batch[/]",
            border_style="blue",
        )

        self.live = Live(
            panel,
            console=self.console,
            refresh_per_second=4,
            transient=False,
        )
        self.live.start()

    def stop(self):
        """Stop the progress display."""
        if self.live:
            self.live.stop()

    def _update_display(self):
        """Update the live display."""
        if self.live:
            panel = Panel(
                self._create_display(),
                title="[bold]YouTube Transcript Batch[/]",
                border_style="blue",
            )
            self.live.update(panel)

    def set_video(self, video_id: str):
        """Set the current video being processed."""
        self.current_video = video_id
        self.current_status = VideoStatus.FETCHING
        self.current_detail = ""
        if self.video_task is not None:
            self.video_progress.update(
                self.video_task,
                description=f"[yellow]{video_id}[/]",
                completed=0,
                detail="fetching transcript...",
            )
        self._update_display()

    def set_status(self, status: VideoStatus, detail: str = ""):
        """Update the current video status."""
        self.current_status = status
        self.current_detail = detail

        if self.video_task is not None:
            progress_map = {
                VideoStatus.FETCHING: 25,
                VideoStatus.DOWNLOADING: 50,
                VideoStatus.TRANSCRIBING: 75,
                VideoStatus.SUCCESS: 100,
                VideoStatus.FAILED: 100,
            }
            self.video_progress.update(
                self.video_task,
                completed=progress_map.get(status, 0),
                detail=detail,
            )
        self._update_display()

    def video_success(self, method: str):
        """Mark current video as successful."""
        self.stats.completed += 1

        if method == "direct":
            self.stats.success_direct += 1
        elif method == "proxy":
            self.stats.success_proxy += 1
        elif method in ("whisper-local", "whisper-api", "whisper"):
            self.stats.success_whisper += 1

        self.current_status = VideoStatus.SUCCESS
        self.current_detail = method

        if self.batch_task is not None:
            self.batch_progress.update(self.batch_task, advance=1)
        self._update_display()

    def video_failed(self, error: str, rate_limited: bool = False):
        """Mark current video as failed."""
        self.stats.completed += 1
        self.stats.failed += 1
        if rate_limited:
            self.stats.rate_limited += 1

        self.current_status = VideoStatus.FAILED
        self.current_detail = error[:50]

        if self.batch_task is not None:
            self.batch_progress.update(self.batch_task, advance=1)
        self._update_display()

    def video_skipped(self):
        """Mark current video as skipped (already exists)."""
        self.stats.completed += 1
        self.stats.skipped += 1

        if self.batch_task is not None:
            self.batch_progress.update(self.batch_task, advance=1)
        self._update_display()

    def log(self, message: str, style: str = ""):
        """Log a message below the progress display."""
        if self.live:
            self.console.print(message, style=style)


def create_reporter(total: int, title: str = "YouTube Transcript Batch") -> ProgressReporter:
    """Factory function to create a progress reporter."""
    return ProgressReporter(total, title)


# Standalone test
if __name__ == "__main__":
    import random

    reporter = ProgressReporter(total_videos=20, title="Test Batch")
    reporter.start()

    try:
        for i in range(20):
            vid = f"test_video_{i:03d}"
            reporter.set_video(vid)
            time.sleep(0.3)

            reporter.set_status(VideoStatus.FETCHING, "trying direct...")
            time.sleep(0.2)

            # Simulate different outcomes
            outcome = random.choice(["direct", "proxy", "whisper", "failed", "skipped"])

            if outcome == "whisper":
                reporter.set_status(VideoStatus.DOWNLOADING, "downloading audio...")
                time.sleep(0.3)
                reporter.set_status(VideoStatus.TRANSCRIBING, "transcribing...")
                time.sleep(0.5)
                reporter.video_success("whisper-local")
            elif outcome == "failed":
                reporter.video_failed("Transcripts disabled", rate_limited=random.choice([True, False]))
            elif outcome == "skipped":
                reporter.video_skipped()
            else:
                reporter.video_success(outcome)

            time.sleep(0.2)
    finally:
        reporter.stop()

    print("\nBatch complete!")
    print(f"Success: {reporter.stats.success_total}")
    print(f"Failed: {reporter.stats.failed}")
