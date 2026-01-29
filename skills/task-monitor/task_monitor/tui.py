"""Task Monitor TUI - Rich terminal user interface components.

This module provides the nvtop-style terminal UI for monitoring tasks.
"""
from __future__ import annotations

import signal
import time
from datetime import datetime
from typing import Optional

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from task_monitor.config import DEFAULT_REFRESH_INTERVAL, RATE_HISTORY_WINDOW
from task_monitor.stores import QualityStore, TaskRegistry
from task_monitor.utils import get_scheduled_jobs, get_task_status


console = Console()


class QualityPanel:
    """Standalone quality panel for testing and embedding."""

    def __init__(self, task_name: Optional[str] = None):
        self.task_name = task_name
        self.store = QualityStore()
        self.console = Console()

    def render_test(self) -> None:
        """Render panel with mock data for testing."""
        # Create mock data
        mock_metrics = {
            "schema_valid_rate": 0.98,
            "grounding_rate": 0.85,
            "taxonomy_rate": 0.92,
            "should_stop": False,
            "window_size": 100,
        }

        table = Table(show_header=True, header_style="bold", box=None)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")
        table.add_column("Status")

        for metric, value in mock_metrics.items():
            if metric.endswith("_rate"):
                status = "[green]OK[/]" if value >= 0.8 else "[red]LOW[/]"
                table.add_row(metric, f"{value:.1%}", status)
            elif metric == "should_stop":
                status = "[red]STOPPED[/]" if value else "[green]RUNNING[/]"
                table.add_row(metric, str(value), status)
            else:
                table.add_row(metric, str(value), "")

        panel = Panel(table, title="[bold]Quality Panel Test[/]", border_style="magenta")
        self.console.print(panel)

    def render(self) -> Panel:
        """Render panel with real data."""
        if not self.task_name:
            return Panel("[dim]No task specified[/]", title="Quality")

        latest = self.store.get_latest(self.task_name)
        if not latest:
            return Panel("[dim]No quality data[/]", title=f"Quality: {self.task_name}")

        metrics = latest.get("metrics", {})

        table = Table(show_header=True, header_style="bold", box=None)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")
        table.add_column("Status")

        for key in ["schema_valid_rate", "grounding_rate", "taxonomy_rate"]:
            if key in metrics:
                value = metrics[key]
                threshold = 0.9 if "schema" in key else 0.8
                status = "[green]OK[/]" if value >= threshold else "[red]LOW[/]"
                table.add_row(key, f"{value:.1%}", status)

        if metrics.get("should_stop"):
            table.add_row("status", "[red]STOPPED[/]", metrics.get("stop_reason", ""))

        return Panel(table, title=f"[bold]Quality: {self.task_name}[/]", border_style="magenta")


class TaskMonitorTUI:
    """nvtop-style TUI for task monitoring."""

    def __init__(self, filter_term: Optional[str] = None):
        self.registry = TaskRegistry()
        self.filter_term = filter_term.lower() if filter_term else None
        self.running = False
        self.start_time = time.time()
        self._history: dict[str, list[tuple[float, int]]] = {}

    def _get_rate(self, name: str, completed: int) -> float:
        """Calculate rate from history."""
        now = time.time()

        if name not in self._history:
            self._history[name] = []

        self._history[name].append((now, completed))

        # Keep last N seconds of data
        cutoff = now - RATE_HISTORY_WINDOW
        self._history[name] = [(t, c) for t, c in self._history[name] if t > cutoff]

        if len(self._history[name]) < 2:
            return 0.0

        oldest_time, oldest_count = self._history[name][0]
        newest_time, newest_count = self._history[name][-1]

        time_diff = newest_time - oldest_time
        count_diff = newest_count - oldest_count

        if time_diff < 60:
            return 0.0

        return (count_diff / time_diff) * 3600

    def create_header(self) -> Panel:
        """Create header panel."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        elapsed = time.time() - self.start_time
        elapsed_str = f"{int(elapsed // 3600):02d}:{int((elapsed % 3600) // 60):02d}:{int(elapsed % 60):02d}"

        header = Text()
        header.append("Task Monitor", style="bold white on blue")
        header.append(f"  {now}  ", style="dim")
        header.append(f"Elapsed: {elapsed_str}", style="cyan")

        return Panel(header, style="bold")

    def create_tasks_panel(self) -> Panel:
        """Create tasks status panel."""
        table = Table(show_header=True, header_style="bold", box=None, expand=True)
        table.add_column("Task", style="cyan", width=18)
        table.add_column("Progress", width=35)
        table.add_column("Rate", justify="right", width=10)
        table.add_column("ETA", justify="right", width=10)
        table.add_column("Errors", justify="right", width=8, style="red")
        table.add_column("Current", width=20)

        for name, task in self.registry.tasks.items():
            if self.filter_term and self.filter_term not in name.lower():
                continue

            status = get_task_status(task)

            completed = status.get("completed", 0) or 0
            total = task.total or 0
            pct = status.get("progress_pct", 0) or 0

            # Progress bar
            bar_width = 20
            filled = int(bar_width * pct / 100) if pct else 0
            bar = "\u2588" * filled + "\u2591" * (bar_width - filled)

            # Rate and ETA
            rate = self._get_rate(name, completed)
            if rate > 0 and total > completed:
                remaining = total - completed
                eta_hours = remaining / rate
                if eta_hours < 1:
                    eta_str = f"{int(eta_hours * 60)}m"
                elif eta_hours < 24:
                    eta_str = f"{eta_hours:.1f}h"
                else:
                    eta_str = f"{eta_hours / 24:.1f}d"
                rate_str = f"{rate:.1f}/h"
            else:
                eta_str = "--"
                rate_str = "--"

            # Current item
            current = status.get("current_item", "")
            method = status.get("current_method", "")
            if current:
                if method == "whisper":
                    current_str = f"[magenta]mic {current[:14]}[/]"
                elif method == "fetching":
                    current_str = f"[cyan]... {current[:14]}[/]"
                else:
                    current_str = f"{current[:17]}"
            else:
                current_str = "[dim]idle[/]"

            if total:
                progress_str = f"[cyan]{bar}[/] {completed:5d}/{total:5d} ({pct:5.1f}%)"
            else:
                progress_str = f"[cyan]{bar}[/] {completed:5d}/??? "

            # Errors
            stats_dict = status.get("stats", {})
            errors = stats_dict.get("failed", 0) + stats_dict.get("errors", 0)
            err_str = f"{errors}" if errors > 0 else "-"

            table.add_row(name[:18], progress_str, rate_str, eta_str, err_str, current_str)

        return Panel(table, title="[bold]Tasks[/]", border_style="blue")

    def create_totals_panel(self) -> Panel:
        """Create totals panel."""
        total_completed = 0
        total_items = 0

        for name, task in self.registry.tasks.items():
            status = get_task_status(task)
            completed = status.get("completed", 0) or 0
            total_completed += completed
            if task.total:
                total_items += task.total

        pct = (total_completed / total_items * 100) if total_items else 0
        bar_width = 50
        filled = int(bar_width * pct / 100)
        bar = "\u2588" * filled + "\u2591" * (bar_width - filled)

        content = Text()
        content.append(f"Overall Progress: [{bar}] ", style="bold")
        content.append(f"{total_completed}/{total_items} ({pct:.1f}%)", style="cyan")

        return Panel(content, title="[bold]Totals[/]", border_style="green")

    def create_schedule_panel(self) -> Panel:
        """Create scheduled jobs panel."""
        jobs = get_scheduled_jobs()
        if not jobs:
            return Panel("No scheduled jobs found", title="[bold]Schedule[/]", border_style="yellow")

        table = Table(show_header=True, header_style="bold", box=None, expand=True)
        table.add_column("Job Name", style="cyan")
        table.add_column("Schedule", style="yellow")
        table.add_column("Next Run", style="green", justify="right")
        table.add_column("Status", style="bold")

        for job in jobs:
            name = job.get("name", "unknown")
            if self.filter_term and self.filter_term not in name.lower():
                continue

            cron = job.get("cron", "")
            enabled = job.get("enabled", True)
            status_str = "[green]Active[/]" if enabled else "[dim]Disabled[/]"

            table.add_row(name, cron, str(job.get("next_run", "-")), status_str)

        return Panel(table, title="[bold]Upcoming Schedule[/]", border_style="yellow")

    def create_quality_panel(self) -> Panel:
        """Create quality metrics panel for batch jobs."""
        store = QualityStore()
        table = Table(show_header=True, header_style="bold", box=None, expand=True)
        table.add_column("Task", style="cyan", width=20)
        table.add_column("Schema", justify="right", width=10)
        table.add_column("Ground", justify="right", width=10)
        table.add_column("Taxonomy", justify="right", width=10)
        table.add_column("Status", width=12)
        table.add_column("Recent Failures", width=25)

        has_quality_data = False

        for name in self.registry.tasks:
            if self.filter_term and self.filter_term not in name.lower():
                continue

            latest = store.get_latest(name)
            if not latest:
                continue

            has_quality_data = True
            metrics = latest.get("metrics", {})

            # Format rates with color coding
            schema_rate = metrics.get("schema_valid_rate", 0)
            ground_rate = metrics.get("grounding_rate", 0)
            taxonomy_rate = metrics.get("taxonomy_rate", 0)

            def rate_style(rate: float, threshold: float = 0.9) -> str:
                if rate >= threshold:
                    return f"[green]{rate:.1%}[/]"
                elif rate >= threshold - 0.1:
                    return f"[yellow]{rate:.1%}[/]"
                else:
                    return f"[red]{rate:.1%}[/]"

            # Status
            should_stop = metrics.get("should_stop", False)
            if should_stop:
                status = "[red]STOPPED[/]"
            else:
                status = "[green]OK[/]"

            # Recent failures
            failures = latest.get("recent_failures", [])
            if failures:
                last_fail = failures[-1] if failures else {}
                fail_str = f"{last_fail.get('metric', '?')}: {last_fail.get('value', '?')}"
            else:
                fail_str = "[dim]-[/]"

            table.add_row(
                name[:20],
                rate_style(schema_rate, 0.95),
                rate_style(ground_rate, 0.80),
                rate_style(taxonomy_rate, 0.90),
                status,
                fail_str[:25],
            )

        if not has_quality_data:
            return Panel("[dim]No quality data available[/]", title="[bold]Quality[/]", border_style="magenta")

        return Panel(table, title="[bold]Quality Metrics[/]", border_style="magenta")

    def create_display(self) -> Layout:
        """Create the full layout."""
        layout = Layout()

        layout.split_column(
            Layout(self.create_header(), size=3),
            Layout(self.create_tasks_panel(), name="tasks"),
            Layout(self.create_quality_panel(), size=8),
            Layout(self.create_schedule_panel(), size=10),
            Layout(self.create_totals_panel(), size=3),
        )

        return layout

    def run(self, refresh_interval: int = DEFAULT_REFRESH_INTERVAL):
        """Run the TUI."""
        self.running = True
        self.start_time = time.time()

        def signal_handler(sig, frame):
            self.running = False

        signal.signal(signal.SIGINT, signal_handler)

        with Live(self.create_display(), console=console, refresh_per_second=1, screen=True) as live:
            while self.running:
                live.update(self.create_display())
                time.sleep(refresh_interval)

        console.print("\n[green]Monitor stopped.[/]")
