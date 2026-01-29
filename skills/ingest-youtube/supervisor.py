#!/usr/bin/env python3
"""Batch supervisor with auto-restart and nvtop-style progress display.

Monitors batch jobs and automatically restarts them if they fail.
Provides real-time GPU monitoring and detailed progress metrics.

Usage:
    python supervisor.py run --input videos.txt --output ./transcripts
    python supervisor.py status --output ./transcripts
    python supervisor.py multi --config batches.json
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


def _load_dotenv():
    """Load .env file from script directory."""
    script_dir = Path(__file__).parent
    env_file = script_dir / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, value = line.split('=', 1)
                    value = value.strip().strip('"').strip("'")
                    os.environ[key] = value


_load_dotenv()

import typer
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.text import Text

app = typer.Typer(help="YouTube Transcript Batch Supervisor")
console = Console()


# GPU monitoring
def get_gpu_info() -> list[dict]:
    """Get GPU utilization info using nvidia-smi."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return []

        gpus = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 6:
                gpus.append({
                    "index": int(parts[0]),
                    "name": parts[1],
                    "util": int(parts[2]) if parts[2].isdigit() else 0,
                    "mem_used": int(parts[3]) if parts[3].isdigit() else 0,
                    "mem_total": int(parts[4]) if parts[4].isdigit() else 0,
                    "temp": int(parts[5]) if parts[5].isdigit() else 0,
                })
        return gpus
    except Exception:
        return []


def get_gpu_processes() -> dict[int, dict]:
    """Get GPU processes and their memory usage."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return {}

        procs = {}
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 2:
                try:
                    pid = int(parts[0])
                    mem = int(parts[1]) if parts[1].isdigit() else 0
                    procs[pid] = {"mem": mem}
                except ValueError:
                    pass
        return procs
    except Exception:
        return {}


@dataclass
class BatchJob:
    """Represents a batch job to supervise."""
    name: str
    input_file: Path
    output_dir: Path
    delay_min: int = 30
    delay_max: int = 60
    process: Optional[subprocess.Popen] = None
    restarts: int = 0
    max_restarts: int = 10
    last_restart: float = 0
    hung_timeout: int = 1800  # 30 min default - consider hung if no progress
    _completed_history: list = field(default_factory=list)  # (timestamp, count) for rate calc
    _last_progress_time: float = field(default_factory=time.time)
    _last_completed_count: int = 0

    @property
    def state_file(self) -> Path:
        return self.output_dir / ".batch_state.json"

    @property
    def total_videos(self) -> int:
        if not self.input_file.exists():
            return 0
        with open(self.input_file) as f:
            return sum(1 for line in f if line.strip() and not line.startswith('#'))

    def _read_state(self) -> dict:
        if not self.state_file.exists():
            return {}
        try:
            with open(self.state_file) as f:
                return json.load(f)
        except Exception:
            return {}

    @property
    def completed_videos(self) -> int:
        state = self._read_state()
        return len(state.get("completed", []))

    @property
    def stats(self) -> dict:
        return self._read_state().get("stats", {})

    @property
    def current_video(self) -> str:
        """Get currently processing video ID."""
        state = self._read_state()
        return state.get("current_video", "")

    @property
    def current_method(self) -> str:
        """Get current processing method (direct/proxy/whisper)."""
        state = self._read_state()
        return state.get("current_method", "")

    @property
    def last_updated(self) -> str:
        state = self._read_state()
        return state.get("last_updated", "")

    @property
    def is_running(self) -> bool:
        if self.process is None:
            return False
        return self.process.poll() is None

    @property
    def is_complete(self) -> bool:
        return self.completed_videos >= self.total_videos

    @property
    def pid(self) -> Optional[int]:
        if self.process:
            return self.process.pid
        return None

    @property
    def is_hung(self) -> bool:
        """Check if process is hung (running but no progress for hung_timeout seconds)."""
        if not self.is_running:
            return False

        current_completed = self.completed_videos
        now = time.time()

        # If progress was made, update tracking
        if current_completed > self._last_completed_count:
            self._last_completed_count = current_completed
            self._last_progress_time = now
            return False

        # Check if we've exceeded the timeout
        time_since_progress = now - self._last_progress_time
        return time_since_progress > self.hung_timeout

    @property
    def time_since_progress(self) -> float:
        """Seconds since last progress was made."""
        return time.time() - self._last_progress_time

    def force_restart(self) -> bool:
        """Force kill and restart the process."""
        if self.process:
            try:
                self.process.kill()
                self.process.wait(timeout=5)
            except Exception:
                pass
            self.process = None

        # Reset progress tracking
        self._last_progress_time = time.time()
        self._last_completed_count = self.completed_videos

        return self.start()

    def get_rate(self) -> float:
        """Calculate videos per hour based on recent history."""
        now = time.time()
        completed = self.completed_videos

        # Add current data point
        self._completed_history.append((now, completed))

        # Keep only last 10 minutes of history
        cutoff = now - 600
        self._completed_history = [(t, c) for t, c in self._completed_history if t > cutoff]

        if len(self._completed_history) < 2:
            return 0.0

        oldest_time, oldest_count = self._completed_history[0]
        newest_time, newest_count = self._completed_history[-1]

        time_diff = newest_time - oldest_time
        count_diff = newest_count - oldest_count

        if time_diff < 60:  # Need at least 1 minute of data
            return 0.0

        return (count_diff / time_diff) * 3600  # videos per hour

    def start(self) -> bool:
        """Start the batch process."""
        if self.is_running:
            return True

        if self.restarts >= self.max_restarts:
            return False

        if time.time() - self.last_restart < 60:
            return False

        script_dir = Path(__file__).parent
        cmd = [
            sys.executable,
            str(script_dir / "youtube_transcript.py"),
            "batch",
            "--input", str(self.input_file),
            "--output", str(self.output_dir),
            "--delay-min", str(self.delay_min),
            "--delay-max", str(self.delay_max),
            "--backoff-base", "60",
            "--backoff-max", "900",
            "--whisper",
            "--resume",
        ]

        try:
            env = os.environ.copy()
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                cwd=script_dir,
                env=env,
            )
            self.restarts += 1
            self.last_restart = time.time()
            return True
        except Exception:
            return False

    def stop(self):
        """Stop the batch process."""
        if self.process and self.is_running:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()


class Supervisor:
    """Supervises batch jobs with nvtop-style display."""

    def __init__(self, jobs: list[BatchJob]):
        self.jobs = jobs
        self.running = False
        self.start_time = time.time()
        self.initial_completed = {j.name: j.completed_videos for j in jobs}

    def create_gpu_panel(self) -> Panel:
        """Create GPU status panel like nvtop."""
        gpus = get_gpu_info()
        gpu_procs = get_gpu_processes()

        if not gpus:
            return Panel("[dim]No GPU detected[/]", title="GPU", border_style="dim")

        # Check if any of our jobs are using GPU
        job_pids = {j.pid for j in self.jobs if j.pid}
        our_gpu_mem = sum(gpu_procs.get(pid, {}).get("mem", 0) for pid in job_pids if pid in gpu_procs)

        content = []
        for gpu in gpus:
            # GPU utilization bar
            util = gpu["util"]
            util_bar_width = 20
            util_filled = int(util_bar_width * util / 100)
            util_bar = "█" * util_filled + "░" * (util_bar_width - util_filled)

            # Color based on utilization
            if util > 80:
                util_color = "green"
            elif util > 40:
                util_color = "yellow"
            else:
                util_color = "cyan"

            # Memory bar
            mem_pct = (gpu["mem_used"] / gpu["mem_total"] * 100) if gpu["mem_total"] > 0 else 0
            mem_bar_width = 20
            mem_filled = int(mem_bar_width * mem_pct / 100)
            mem_bar = "█" * mem_filled + "░" * (mem_bar_width - mem_filled)

            # Temperature color
            temp = gpu["temp"]
            if temp > 80:
                temp_color = "red"
            elif temp > 60:
                temp_color = "yellow"
            else:
                temp_color = "green"

            line = Text()
            line.append(f"GPU{gpu['index']} ", style="bold")
            line.append(f"{gpu['name'][:20]:<20} ", style="dim")
            line.append(f"[{util_color}]{util_bar}[/] {util:3d}% ", style=util_color)
            line.append(f"MEM [{util_color}]{mem_bar}[/] {gpu['mem_used']:5d}/{gpu['mem_total']:5d}MB ", style=util_color)
            line.append(f"[{temp_color}]{temp}°C[/]", style=temp_color)
            content.append(line)

        if our_gpu_mem > 0:
            content.append(Text(f"  Whisper using: {our_gpu_mem} MiB", style="magenta"))

        return Panel(Group(*content), title="[bold]GPU[/]", border_style="green")

    def create_jobs_panel(self) -> Panel:
        """Create jobs status panel."""
        table = Table(show_header=True, header_style="bold", box=None, expand=True)
        table.add_column("Job", style="cyan", width=14)
        table.add_column("Progress", width=32)
        table.add_column("Rate", justify="right", width=10)
        table.add_column("ETA", justify="right", width=10)
        table.add_column("Status", width=10)
        table.add_column("Current", width=16)

        for job in self.jobs:
            total = job.total_videos
            done = job.completed_videos
            pct = (done / total * 100) if total > 0 else 0

            # Progress bar
            bar_width = 20
            filled = int(bar_width * pct / 100)
            bar = "█" * filled + "░" * (bar_width - filled)

            # Rate and ETA
            rate = job.get_rate()
            if rate > 0:
                remaining = total - done
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

            # Status with color
            if job.is_complete:
                status = "[green]✓ Done[/]"
            elif job.is_hung:
                mins = int(job.time_since_progress / 60)
                status = f"[red]⚠ Hung {mins}m[/]"
            elif job.is_running:
                status = "[blue]● Run[/]"
            else:
                status = "[yellow]○ Stop[/]"

            # Current video/method
            current = job.current_video
            method = job.current_method
            if current:
                if method == "whisper":
                    current_str = f"[magenta]🎤 {current[:11]}[/]"
                elif method == "proxy":
                    current_str = f"[yellow]🔄 {current[:11]}[/]"
                else:
                    current_str = f"[cyan]{current[:14]}[/]"
            else:
                current_str = "[dim]waiting...[/]"

            progress_str = f"[cyan]{bar}[/] {done:4d}/{total:4d} ({pct:4.1f}%)"

            table.add_row(
                job.name[:14],
                progress_str,
                rate_str,
                eta_str,
                status,
                current_str,
            )

        return Panel(table, title="[bold]Batch Jobs[/]", border_style="blue")

    def create_stats_panel(self) -> Panel:
        """Create aggregate stats panel."""
        total_all = sum(j.total_videos for j in self.jobs)
        done_all = sum(j.completed_videos for j in self.jobs)
        session_done = done_all - sum(self.initial_completed.values())

        # Aggregate stats
        success = sum(j.stats.get("success", 0) for j in self.jobs)
        failed = sum(j.stats.get("failed", 0) for j in self.jobs)
        whisper = sum(j.stats.get("whisper", 0) for j in self.jobs)
        rate_limited = sum(j.stats.get("rate_limited", 0) for j in self.jobs)

        elapsed = time.time() - self.start_time
        elapsed_str = f"{int(elapsed // 3600):02d}:{int((elapsed % 3600) // 60):02d}:{int(elapsed % 60):02d}"

        # Overall rate
        if elapsed > 120:
            overall_rate = session_done / (elapsed / 3600)
            remaining = total_all - done_all
            if overall_rate > 0:
                eta_hours = remaining / overall_rate
                if eta_hours < 1:
                    eta_str = f"{int(eta_hours * 60)} min"
                elif eta_hours < 24:
                    eta_str = f"{eta_hours:.1f} hours"
                else:
                    eta_str = f"{eta_hours / 24:.1f} days"
            else:
                eta_str = "calculating..."
            rate_str = f"{overall_rate:.1f}/h"
        else:
            eta_str = "calculating..."
            rate_str = "--"

        # Overall progress bar
        pct = (done_all / total_all * 100) if total_all > 0 else 0
        bar_width = 40
        filled = int(bar_width * pct / 100)
        bar = "█" * filled + "░" * (bar_width - filled)

        content = Text()
        content.append(f"Overall: [{bar}] {done_all}/{total_all} ({pct:.1f}%)\n", style="bold cyan")
        content.append(f"Session: ", style="dim")
        content.append(f"+{session_done} videos  ", style="green")
        content.append(f"Rate: {rate_str}  ", style="cyan")
        content.append(f"ETA: {eta_str}\n", style="yellow")
        content.append(f"Elapsed: {elapsed_str}  ", style="dim")
        content.append(f"Success: ", style="dim")
        content.append(f"{success} ", style="green")
        content.append(f"Failed: ", style="dim")
        content.append(f"{failed} ", style="red")
        content.append(f"Whisper: ", style="dim")
        content.append(f"{whisper} ", style="magenta")
        content.append(f"RateLim: ", style="dim")
        content.append(f"{rate_limited}", style="yellow")

        return Panel(content, title="[bold]Statistics[/]", border_style="cyan")

    def create_display(self) -> Layout:
        """Create the full nvtop-style layout."""
        layout = Layout()

        # Header
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        header = Text()
        header.append("YouTube Transcript Supervisor", style="bold white on blue")
        header.append(f"  {now}", style="dim")

        layout.split_column(
            Layout(Panel(header, style="bold"), size=3),
            Layout(name="gpu", size=5),
            Layout(name="jobs", size=10),
            Layout(name="stats", size=7),
        )

        layout["gpu"].update(self.create_gpu_panel())
        layout["jobs"].update(self.create_jobs_panel())
        layout["stats"].update(self.create_stats_panel())

        return layout

    def run(self, check_interval: int = 5):
        """Run the supervisor loop with live display."""
        self.running = True
        self.start_time = time.time()

        def signal_handler(sig, frame):
            self.running = False

        signal.signal(signal.SIGINT, signal_handler)

        # Start all jobs
        for job in self.jobs:
            if not job.is_complete:
                job.start()

        with Live(self.create_display(), console=console, refresh_per_second=2, screen=True) as live:
            while self.running:
                all_complete = True
                for job in self.jobs:
                    if job.is_complete:
                        continue
                    all_complete = False

                    # Check for hung process (no progress for hung_timeout)
                    if job.is_hung:
                        mins = int(job.time_since_progress / 60)
                        console.print(f"[yellow]Job {job.name} hung ({mins}m no progress), restarting...[/]")
                        job.force_restart()
                    elif not job.is_running:
                        job.start()

                if all_complete:
                    self.running = False
                    break

                live.update(self.create_display())
                time.sleep(check_interval)

        # Stop all jobs
        for job in self.jobs:
            job.stop()

        console.print("\n[green]Supervisor stopped.[/]")


@app.command()
def run(
    input_file: str = typer.Option(..., "--input", "-f", help="File with video IDs"),
    output_dir: str = typer.Option(..., "--output", "-o", help="Output directory"),
    delay_min: int = typer.Option(30, "--delay-min", help="Min delay between requests"),
    delay_max: int = typer.Option(60, "--delay-max", help="Max delay between requests"),
    max_restarts: int = typer.Option(10, "--max-restarts", help="Max automatic restarts"),
):
    """Run a single batch job with supervision and auto-restart."""
    job = BatchJob(
        name=Path(input_file).stem,
        input_file=Path(input_file),
        output_dir=Path(output_dir),
        delay_min=delay_min,
        delay_max=delay_max,
        max_restarts=max_restarts,
    )

    supervisor = Supervisor([job])
    supervisor.run()


@app.command()
def multi(
    config: str = typer.Option(..., "--config", "-c", help="JSON config file with batch jobs"),
):
    """Run multiple batch jobs with unified supervision."""
    config_path = Path(config)
    if not config_path.exists():
        console.print(f"[red]Config file not found: {config}[/]")
        raise typer.Exit(1)

    with open(config_path) as f:
        cfg = json.load(f)

    jobs = []
    for job_cfg in cfg.get("jobs", []):
        jobs.append(BatchJob(
            name=job_cfg.get("name", Path(job_cfg["input"]).stem),
            input_file=Path(job_cfg["input"]),
            output_dir=Path(job_cfg["output"]),
            delay_min=job_cfg.get("delay_min", 30),
            delay_max=job_cfg.get("delay_max", 60),
            max_restarts=job_cfg.get("max_restarts", 10),
            hung_timeout=job_cfg.get("hung_timeout", 1800),  # 30 min default
        ))

    supervisor = Supervisor(jobs)
    supervisor.run()


@app.command()
def status(
    output_dir: str = typer.Option(..., "--output", "-o", help="Output directory to check"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON for agent parsing"),
):
    """Check status of a batch job (useful for agents)."""
    output_path = Path(output_dir)
    state_file = output_path / ".batch_state.json"

    if not state_file.exists():
        result = {"error": "No batch state found", "output_dir": str(output_dir)}
        if json_output:
            print(json.dumps(result))
        else:
            console.print(f"[red]No batch state found in {output_dir}[/]")
        return

    with open(state_file) as f:
        state = json.load(f)

    json_files = list(output_path.glob("*.json"))
    completed = len([f for f in json_files if f.name != ".batch_state.json"])

    stats = state.get("stats", {})
    result = {
        "output_dir": str(output_dir),
        "completed": completed,
        "stats": stats,
        "current_video": state.get("current_video", ""),
        "current_method": state.get("current_method", ""),
        "last_updated": state.get("last_updated", "unknown"),
        "consecutive_failures": state.get("consecutive_failures", 0),
    }

    if json_output:
        print(json.dumps(result, indent=2))
    else:
        current = state.get("current_video", "")
        method = state.get("current_method", "")
        current_str = f"{current} ({method})" if current else "idle"

        console.print(Panel(
            f"""[bold]Batch Status: {output_dir}[/]

Completed: [cyan]{completed}[/]
Current:   [yellow]{current_str}[/]
Success:   [green]{stats.get('success', 0)}[/]
Failed:    [red]{stats.get('failed', 0)}[/]
Whisper:   [magenta]{stats.get('whisper', 0)}[/]
Rate Lim:  [yellow]{stats.get('rate_limited', 0)}[/]

Last Updated: {state.get('last_updated', 'unknown')}
""",
            border_style="blue",
        ))


if __name__ == "__main__":
    app()
