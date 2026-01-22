#!/usr/bin/env python3
"""
Live TUI monitor for audiobook transcription pipeline.
Similar to nvtop/htop - shows real-time progress and system stats.
"""

from __future__ import annotations

import subprocess
import time
from datetime import datetime
from pathlib import Path

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich.layout import Layout
from rich.text import Text

# Import state from main runner
from transcribe_runner import PipelineState, STATE_FILE, LOG_FILE, LIBRARY_DIR


def get_gpu_stats() -> dict:
    """Get NVIDIA GPU stats via nvidia-smi."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(", ")
            return {
                "gpu_util": int(parts[0]),
                "mem_used": int(parts[1]),
                "mem_total": int(parts[2]),
                "temp": int(parts[3]),
                "power": float(parts[4]) if parts[4] != "[N/A]" else 0,
            }
    except:
        pass
    return {"gpu_util": 0, "mem_used": 0, "mem_total": 1, "temp": 0, "power": 0}


def get_cpu_stats() -> dict:
    """Get CPU and memory stats."""
    try:
        # CPU usage
        with open("/proc/stat") as f:
            cpu_line = f.readline()
            parts = cpu_line.split()[1:]
            idle = int(parts[3])
            total = sum(int(p) for p in parts)

        # Memory
        with open("/proc/meminfo") as f:
            lines = f.readlines()
            mem_total = int(lines[0].split()[1]) // 1024  # MB
            mem_free = int(lines[1].split()[1]) // 1024
            mem_available = int(lines[2].split()[1]) // 1024

        return {
            "cpu_idle": idle,
            "cpu_total": total,
            "mem_used": mem_total - mem_available,
            "mem_total": mem_total,
        }
    except:
        return {"cpu_idle": 0, "cpu_total": 1, "mem_used": 0, "mem_total": 1}


def get_recent_logs(n: int = 5) -> list[str]:
    """Get recent log entries."""
    if not LOG_FILE.exists():
        return []

    import json
    lines = []
    try:
        with open(LOG_FILE) as f:
            all_lines = f.readlines()[-n:]
            for line in all_lines:
                entry = json.loads(line)
                ts = entry.get("timestamp", "")[:19]
                event = entry.get("event", "")
                book = entry.get("book", "")
                if book:
                    book = book[:40] + "..." if len(book) > 40 else book
                lines.append(f"[dim]{ts}[/dim] {event}: {book}")
    except:
        pass
    return lines


def make_bar(value: float, max_value: float, width: int = 20, color: str = "green") -> str:
    """Create a text-based progress bar."""
    if max_value == 0:
        return "[dim]" + "─" * width + "[/dim]"

    pct = min(value / max_value, 1.0)
    filled = int(pct * width)
    empty = width - filled

    bar = f"[{color}]{'█' * filled}[/{color}][dim]{'░' * empty}[/dim]"
    return bar


def create_layout() -> Layout:
    """Create the TUI layout."""
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="main", ratio=1),
        Layout(name="footer", size=5),
    )
    layout["main"].split_row(
        Layout(name="left", ratio=2),
        Layout(name="right", ratio=1),
    )
    layout["left"].split_column(
        Layout(name="progress", ratio=2),
        Layout(name="books", ratio=3),
    )
    layout["right"].split_column(
        Layout(name="gpu", size=8),
        Layout(name="cpu", size=6),
        Layout(name="logs", ratio=1),
    )
    return layout


def render_header(state: PipelineState) -> Panel:
    """Render header with title and summary."""
    summary = state.get_summary()

    text = Text()
    text.append("AUDIOBOOK TRANSCRIPTION MONITOR", style="bold blue")
    text.append(f"  │  ", style="dim")
    text.append(f"{summary['completed']}", style="green bold")
    text.append(f"/{summary['total']} complete  ", style="dim")
    text.append(f"ETA: ", style="dim")
    if summary['eta_hours']:
        text.append(f"{summary['eta_hours']:.1f}h", style="yellow")
    else:
        text.append("calculating...", style="dim")

    return Panel(text, style="blue", padding=(0, 1))


def render_progress(state: PipelineState) -> Panel:
    """Render overall progress."""
    summary = state.get_summary()

    # Progress bar
    completed = summary['completed']
    total = summary['total']
    pct = completed / total if total > 0 else 0

    content = []
    content.append(f"[bold]Overall Progress[/bold]")
    content.append("")
    content.append(f"  {make_bar(completed, total, 40, 'green')}  {completed}/{total} ({pct*100:.0f}%)")
    content.append("")
    content.append(f"  [dim]Audio:[/dim] {summary['total_audio_hours']:.1f}h total")
    content.append(f"  [dim]Transcribed:[/dim] {summary['total_transcribe_hours']:.1f}h processing time")
    if summary['avg_speed_ratio'] > 0:
        content.append(f"  [dim]Speed:[/dim] {summary['avg_speed_ratio']:.1f}x realtime")

    return Panel("\n".join(content), title="Progress", border_style="green")


def render_books(state: PipelineState) -> Panel:
    """Render book status table."""
    table = Table(show_header=True, header_style="bold", expand=True, box=None)
    table.add_column("Book", style="cyan", max_width=45)
    table.add_column("Status", justify="center", width=12)
    table.add_column("Duration", justify="right", width=8)
    table.add_column("Time", justify="right", width=8)

    status_styles = {
        "completed": "[green]✓ done[/green]",
        "in_progress": "[yellow bold]► running[/yellow bold]",
        "pending": "[dim]○ pending[/dim]",
        "failed": "[red]✗ failed[/red]",
        "skipped": "[dim]- skip[/dim]",
    }

    # Sort: in_progress first, then pending, then completed
    priority = {"in_progress": 0, "pending": 1, "failed": 2, "completed": 3, "skipped": 4}
    sorted_books = sorted(state.books.values(), key=lambda b: (priority.get(b.status, 5), b.name))

    for book in sorted_books[:12]:  # Show top 12
        name = book.name[:45]
        if len(book.name) > 45:
            name = name[:42] + "..."

        status = status_styles.get(book.status, book.status)
        duration = f"{book.duration_seconds/3600:.1f}h" if book.duration_seconds else "-"
        trans_time = f"{book.transcribe_seconds/60:.0f}m" if book.transcribe_seconds else "-"

        table.add_row(name, status, duration, trans_time)

    remaining = len(state.books) - 12
    if remaining > 0:
        table.add_row(f"[dim]... and {remaining} more[/dim]", "", "", "")

    return Panel(table, title="Books", border_style="cyan")


def render_gpu(gpu_stats: dict) -> Panel:
    """Render GPU stats."""
    util = gpu_stats['gpu_util']
    mem_used = gpu_stats['mem_used']
    mem_total = gpu_stats['mem_total']
    temp = gpu_stats['temp']
    power = gpu_stats['power']

    util_color = "green" if util < 70 else "yellow" if util < 90 else "red"
    temp_color = "green" if temp < 70 else "yellow" if temp < 85 else "red"

    content = []
    content.append(f"[bold]GPU Utilization[/bold]")
    content.append(f"  {make_bar(util, 100, 15, util_color)}  [{util_color}]{util:3d}%[/{util_color}]")
    content.append("")
    content.append(f"[bold]VRAM[/bold]")
    content.append(f"  {make_bar(mem_used, mem_total, 15, 'blue')}  {mem_used//1024:.0f}/{mem_total//1024:.0f}GB")
    content.append("")
    content.append(f"  [dim]Temp:[/dim] [{temp_color}]{temp}°C[/{temp_color}]  [dim]Power:[/dim] {power:.0f}W")

    return Panel("\n".join(content), title="GPU", border_style="magenta")


def render_cpu(cpu_stats: dict, prev_cpu: dict) -> Panel:
    """Render CPU/Memory stats."""
    # Calculate CPU usage
    idle_delta = cpu_stats['cpu_idle'] - prev_cpu.get('cpu_idle', 0)
    total_delta = cpu_stats['cpu_total'] - prev_cpu.get('cpu_total', 1)
    cpu_pct = 100 * (1 - idle_delta / total_delta) if total_delta > 0 else 0

    mem_used = cpu_stats['mem_used']
    mem_total = cpu_stats['mem_total']

    cpu_color = "green" if cpu_pct < 70 else "yellow" if cpu_pct < 90 else "red"

    content = []
    content.append(f"[bold]CPU[/bold]  {make_bar(cpu_pct, 100, 12, cpu_color)}  [{cpu_color}]{cpu_pct:4.0f}%[/{cpu_color}]")
    content.append(f"[bold]RAM[/bold]  {make_bar(mem_used, mem_total, 12, 'blue')}  {mem_used//1024:.0f}/{mem_total//1024:.0f}GB")

    return Panel("\n".join(content), title="System", border_style="blue")


def render_logs() -> Panel:
    """Render recent log entries."""
    logs = get_recent_logs(6)
    content = "\n".join(logs) if logs else "[dim]No recent activity[/dim]"
    return Panel(content, title="Activity Log", border_style="dim")


def render_footer() -> Panel:
    """Render footer with help."""
    return Panel(
        "[dim]Press [bold]Ctrl+C[/bold] to exit  │  "
        "State: progress.json  │  "
        "Logs: transcribe.jsonl  │  "
        f"Updated: {datetime.now().strftime('%H:%M:%S')}[/dim]",
        style="dim"
    )


def main():
    console = Console()
    layout = create_layout()

    prev_cpu = get_cpu_stats()

    console.print("[bold]Starting monitor...[/bold] Press Ctrl+C to exit\n")

    try:
        with Live(layout, console=console, refresh_per_second=2, screen=True) as live:
            while True:
                # Reload state
                state = PipelineState.load()
                if not state.books:
                    from transcribe_runner import discover_books
                    discover_books(state)

                # Get system stats
                gpu_stats = get_gpu_stats()
                cpu_stats = get_cpu_stats()

                # Update layout
                layout["header"].update(render_header(state))
                layout["progress"].update(render_progress(state))
                layout["books"].update(render_books(state))
                layout["gpu"].update(render_gpu(gpu_stats))
                layout["cpu"].update(render_cpu(cpu_stats, prev_cpu))
                layout["logs"].update(render_logs())
                layout["footer"].update(render_footer())

                prev_cpu = cpu_stats
                time.sleep(1)

    except KeyboardInterrupt:
        console.print("\n[dim]Monitor stopped.[/dim]")


if __name__ == "__main__":
    main()
