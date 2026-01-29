#!/usr/bin/env python3
"""
Tenacious watchdog for audiobook transcription pipeline.
Monitors progress, auto-restarts on hangs, validates completions.

Key features:
- No restart limit - keeps trying until all books complete
- Periodic revalidation to catch incomplete transcripts
- Self-healing: detects and recovers from all failure modes
"""

import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

STATE_FILE = Path(__file__).parent / "progress.json"
SCRIPT_DIR = Path(__file__).parent
LOG_FILE = SCRIPT_DIR / "watchdog.log"

# Timing configuration
HANG_TIMEOUT = 1800  # 30 minutes without progress = hung (transcription can take time)
CHECK_INTERVAL = 60  # Check every minute
REVALIDATE_INTERVAL = 3600  # Revalidate completed transcripts every hour


def log(msg: str, console: Console | None = None):
    """Log to file and optionally console."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_msg = f"[{timestamp}] {msg}"
    with open(LOG_FILE, "a") as f:
        f.write(log_msg + "\n")
    if console:
        console.print(msg)


def get_state_mtime() -> float:
    """Get state file modification time."""
    if STATE_FILE.exists():
        return STATE_FILE.stat().st_mtime
    return 0


def get_progress() -> dict:
    """Get current progress from state file."""
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text())
            completed = sum(1 for b in data.get("books", {}).values() if b.get("status") == "completed")
            in_progress = sum(1 for b in data.get("books", {}).values() if b.get("status") == "in_progress")
            pending = sum(1 for b in data.get("books", {}).values() if b.get("status") == "pending")
            failed = sum(1 for b in data.get("books", {}).values() if b.get("status") == "failed")
            total = len(data.get("books", {}))

            # Get current book name if in progress
            current = None
            for name, book in data.get("books", {}).items():
                if book.get("status") == "in_progress":
                    current = name
                    break

            return {
                "completed": completed,
                "in_progress": in_progress,
                "pending": pending,
                "failed": failed,
                "total": total,
                "current": current,
                "updated_at": data.get("updated_at"),
            }
        except Exception as e:
            log(f"Error reading state: {e}")
    return {"completed": 0, "in_progress": 0, "pending": 0, "failed": 0, "total": 0, "current": None, "updated_at": None}


def find_transcribe_process() -> int | None:
    """Find running transcribe_runner process."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "transcribe_runner.py.*run"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            pids = result.stdout.strip().split("\n")
            return int(pids[0]) if pids[0] else None
    except Exception:
        pass
    return None


def kill_process(pid: int, console: Console) -> bool:
    """Kill a process with escalating force."""
    try:
        log(f"Sending SIGTERM to {pid}", console)
        os.kill(pid, signal.SIGTERM)
        time.sleep(5)

        # Check if still running
        try:
            os.kill(pid, 0)  # Check if process exists
            log(f"Process {pid} still running, sending SIGKILL", console)
            os.kill(pid, signal.SIGKILL)
            time.sleep(2)
        except ProcessLookupError:
            pass  # Already dead

        return True
    except Exception as e:
        log(f"Error killing process: {e}", console)
        return False


def reset_stuck_books(console: Console):
    """Reset any in_progress books to pending."""
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text())
            changed = False
            for name, book in data.get("books", {}).items():
                if book.get("status") == "in_progress":
                    book["status"] = "pending"
                    log(f"Reset stuck book: {name}", console)
                    changed = True
            if changed:
                data["updated_at"] = datetime.now().isoformat()
                STATE_FILE.write_text(json.dumps(data, indent=2))
        except Exception as e:
            log(f"Error resetting stuck books: {e}", console)


def run_revalidate(console: Console) -> int:
    """Run revalidate command to check for incomplete transcripts."""
    log("Running revalidate to check for incomplete transcripts...", console)
    try:
        result = subprocess.run(
            [str(SCRIPT_DIR / ".venv/bin/python3"), str(SCRIPT_DIR / "transcribe_runner.py"), "revalidate"],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode == 0:
            # Count re-queued from output
            requeued = result.stdout.count("→")
            if requeued > 0:
                log(f"[yellow]Revalidate found {requeued} incomplete transcripts[/yellow]", console)
            else:
                log("[green]All transcripts validated[/green]", console)
            return requeued
    except Exception as e:
        log(f"Error running revalidate: {e}", console)
    return 0


def start_transcription(console: Console) -> subprocess.Popen:
    """Start transcription process."""
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    log_file = open(SCRIPT_DIR / "watchdog_transcribe.log", "a")

    log("Starting transcription process...", console)

    process = subprocess.Popen(
        [str(SCRIPT_DIR / ".venv/bin/python3"), str(SCRIPT_DIR / "transcribe_runner.py"),
         "run", "--continue-on-error"],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        cwd=str(SCRIPT_DIR),
        env=env,
    )
    return process


def main():
    console = Console()

    console.print(Panel.fit(
        "[bold blue]Tenacious Transcription Watchdog[/bold blue]\n"
        f"Hang timeout: {HANG_TIMEOUT}s | Check interval: {CHECK_INTERVAL}s\n"
        "[dim]Will keep trying until all books complete. No restart limit.[/dim]",
        border_style="blue"
    ))

    log("Watchdog started", console)

    restarts = 0
    last_state_mtime = 0
    last_progress_time = time.time()
    last_revalidate_time = time.time()
    last_completed_count = 0
    process = None

    try:
        while True:
            progress = get_progress()
            current_mtime = get_state_mtime()

            # Check if all done
            if progress["completed"] == progress["total"] and progress["total"] > 0 and progress["pending"] == 0:
                log(f"[green]All {progress['total']} books completed![/green]", console)
                # Final revalidate to make sure
                requeued = run_revalidate(console)
                if requeued == 0:
                    log("[green]Pipeline complete! All transcripts validated.[/green]", console)
                    break
                else:
                    log(f"[yellow]Found {requeued} incomplete transcripts, continuing...[/yellow]", console)

            # Periodic revalidation
            if time.time() - last_revalidate_time > REVALIDATE_INTERVAL:
                requeued = run_revalidate(console)
                last_revalidate_time = time.time()
                if requeued > 0:
                    # Reset progress tracking since we found issues
                    last_progress_time = time.time()

            # Track actual progress (completed count increasing)
            if progress["completed"] > last_completed_count:
                last_completed_count = progress["completed"]
                last_progress_time = time.time()
                restarts = 0  # Reset restart counter on successful completion
                log(f"[green]Book completed! {progress['completed']}/{progress['total']}[/green]", console)

            # Find or start process
            pid = find_transcribe_process()

            if pid is None and (progress["pending"] > 0 or progress["in_progress"] > 0):
                log(f"[yellow]No transcription process found. Starting...[/yellow]", console)
                reset_stuck_books(console)
                process = start_transcription(console)
                restarts += 1
                last_progress_time = time.time()
                log(f"[green]Started transcription (restart #{restarts})[/green]", console)
                time.sleep(15)  # Give it time to start
                continue

            # Check for state file updates (transcription is making progress)
            if current_mtime > last_state_mtime:
                last_state_mtime = current_mtime
                last_progress_time = time.time()

            time_since_progress = time.time() - last_progress_time

            # Build status message
            current_book = progress.get("current", "")[:40] + "..." if progress.get("current") else "none"
            status = (
                f"[{datetime.now().strftime('%H:%M:%S')}] "
                f"Done: {progress['completed']}/{progress['total']} | "
                f"Pending: {progress['pending']} | "
                f"Current: {current_book} | "
                f"PID: {pid or 'none'} | "
                f"Idle: {time_since_progress:.0f}s"
            )

            if pid and time_since_progress > HANG_TIMEOUT:
                log(f"[red]{status} - HUNG![/red]", console)
                log(f"[yellow]Killing hung process {pid}...[/yellow]", console)
                kill_process(pid, console)
                reset_stuck_books(console)
                time.sleep(5)

                log(f"[yellow]Restarting transcription...[/yellow]", console)
                process = start_transcription(console)
                restarts += 1
                last_progress_time = time.time()
                log(f"[green]Restarted (attempt #{restarts})[/green]", console)
            elif pid:
                console.print(status)
            elif progress["pending"] == 0 and progress["in_progress"] == 0:
                # No process and nothing pending - we might be done
                console.print(f"[dim]{status} - checking completion...[/dim]")

            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        log("\n[dim]Watchdog stopped by user[/dim]", console)

    finally:
        log("Watchdog exiting", console)
        console.print("[dim]Watchdog exiting. Use 'nohup python watchdog.py &' to run in background.[/dim]")


if __name__ == "__main__":
    main()
