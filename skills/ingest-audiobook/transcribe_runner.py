#!/usr/bin/env python3
"""
GPU-accelerated audiobook transcription with rich progress display.

Features:
- Rich progress bars with ETA
- State persistence for resume capability
- Structured JSON logging for agent parsing
- Status command for progress queries
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

# Lazy imports for faster --status queries
def get_rich():
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn, TimeRemainingColumn, TaskProgressColumn
    from rich.table import Table
    from rich.panel import Panel
    from rich.live import Live
    return Console, Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn, TimeRemainingColumn, TaskProgressColumn, Table, Panel, Live


# Configuration
LIBRARY_DIR = Path.home() / "clawd" / "library" / "books"
STATE_FILE = Path(__file__).parent / "progress.json"
LOG_FILE = Path(__file__).parent / "transcribe.jsonl"
COMPLETION_MARKER = "<!-- TRANSCRIPTION_COMPLETE -->"

# Minimum words per hour of audio (sanity check for partial transcripts)
MIN_WORDS_PER_HOUR = 7000  # Conservative: actual is ~9300


@dataclass
class BookState:
    name: str
    m4b_path: str
    status: Literal["pending", "in_progress", "completed", "failed", "skipped"] = "pending"
    duration_seconds: float | None = None
    transcribe_seconds: float | None = None
    error: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


@dataclass
class PipelineState:
    books: dict[str, BookState] = field(default_factory=dict)
    started_at: str | None = None
    updated_at: str | None = None

    def save(self):
        """Save state to JSON file."""
        self.updated_at = datetime.now().isoformat()
        data = {
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "books": {k: asdict(v) for k, v in self.books.items()}
        }
        STATE_FILE.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls) -> "PipelineState":
        """Load state from JSON file or create new."""
        if STATE_FILE.exists():
            try:
                data = json.loads(STATE_FILE.read_text())
                state = cls(
                    started_at=data.get("started_at"),
                    updated_at=data.get("updated_at"),
                )
                for name, book_data in data.get("books", {}).items():
                    state.books[name] = BookState(**book_data)
                return state
            except (json.JSONDecodeError, TypeError):
                pass
        return cls()

    def get_summary(self) -> dict:
        """Get summary statistics."""
        total = len(self.books)
        by_status = {"pending": 0, "in_progress": 0, "completed": 0, "failed": 0, "skipped": 0}
        total_duration = 0
        total_transcribe_time = 0

        for book in self.books.values():
            by_status[book.status] = by_status.get(book.status, 0) + 1
            if book.duration_seconds:
                total_duration += book.duration_seconds
            if book.transcribe_seconds:
                total_transcribe_time += book.transcribe_seconds

        # Estimate remaining time based on completed transcriptions
        completed = by_status["completed"]
        remaining = by_status["pending"] + by_status["in_progress"]

        avg_ratio = 0
        if completed > 0 and total_transcribe_time > 0:
            completed_duration = sum(
                b.duration_seconds for b in self.books.values()
                if b.status == "completed" and b.duration_seconds
            )
            if completed_duration > 0:
                avg_ratio = total_transcribe_time / completed_duration

        remaining_duration = sum(
            b.duration_seconds for b in self.books.values()
            if b.status in ("pending", "in_progress") and b.duration_seconds
        )

        eta_seconds = remaining_duration * avg_ratio if avg_ratio > 0 else None

        return {
            "total": total,
            "completed": completed,
            "pending": by_status["pending"],
            "in_progress": by_status["in_progress"],
            "failed": by_status["failed"],
            "skipped": by_status["skipped"],
            "total_audio_hours": total_duration / 3600 if total_duration else 0,
            "total_transcribe_hours": total_transcribe_time / 3600 if total_transcribe_time else 0,
            "eta_hours": eta_seconds / 3600 if eta_seconds else None,
            "avg_speed_ratio": avg_ratio,
        }


def log_event(event_type: str, book: str | None = None, **data):
    """Append structured log entry."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "event": event_type,
        "book": book,
        **data
    }
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")


def is_transcript_complete(transcript_path: Path, audio_duration: float | None = None) -> bool:
    """Check if a transcript file is complete (not partial from crashed transcription).

    Checks for:
    1. Completion marker at end of file
    2. Minimum word count based on audio duration (fallback)
    """
    if not transcript_path.exists():
        return False

    try:
        content = transcript_path.read_text(encoding="utf-8")

        # Primary check: completion marker
        if COMPLETION_MARKER in content:
            return True

        # Fallback: validate word count if we know audio duration
        if audio_duration and audio_duration > 0:
            word_count = len(content.split())
            hours = audio_duration / 3600
            expected_min = int(hours * MIN_WORDS_PER_HOUR)

            # If less than 70% of expected minimum, likely incomplete
            if word_count < expected_min * 0.7:
                return False

        # If no marker but reasonable content, assume legacy complete transcript
        # (for backwards compatibility with transcripts made before this fix)
        word_count = len(content.split())
        return word_count > 1000  # At least 1000 words for a valid transcript

    except Exception:
        return False


def get_audio_duration(m4b_path: Path) -> float | None:
    """Get audio duration in seconds using ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(m4b_path)],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            return float(result.stdout.strip())
    except Exception:
        pass
    return None


def discover_books(state: PipelineState) -> list[BookState]:
    """Discover M4B files and update state."""
    m4b_files = list(LIBRARY_DIR.glob("*/audio.m4b"))

    for m4b_path in m4b_files:
        book_name = m4b_path.parent.name
        transcript = m4b_path.parent / "text.md"

        if book_name not in state.books:
            # New book - check if already transcribed
            duration = get_audio_duration(m4b_path)

            if transcript.exists() and is_transcript_complete(transcript, duration):
                state.books[book_name] = BookState(
                    name=book_name,
                    m4b_path=str(m4b_path),
                    status="completed",
                    duration_seconds=duration,
                    completed_at=datetime.now().isoformat(),
                )
            else:
                # Either no transcript or transcript is incomplete
                state.books[book_name] = BookState(
                    name=book_name,
                    m4b_path=str(m4b_path),
                    status="pending",
                    duration_seconds=duration,
                )
        else:
            # Existing book in state
            book = state.books[book_name]
            duration = book.duration_seconds or get_audio_duration(m4b_path)
            book.duration_seconds = duration

            # Check if transcript is complete
            if book.status == "pending" and transcript.exists():
                if is_transcript_complete(transcript, duration):
                    book.status = "completed"
                    book.completed_at = datetime.now().isoformat()
                # else: leave as pending - transcript exists but is incomplete

            # Check if "completed" book actually has incomplete transcript
            elif book.status == "completed" and transcript.exists():
                if not is_transcript_complete(transcript, duration):
                    book.status = "pending"  # Re-queue for transcription
                    book.completed_at = None
                    log_event("requeue_incomplete", book.name,
                              reason="transcript incomplete or missing marker")

            # Reset stuck in_progress to pending on restart
            elif book.status == "in_progress":
                book.status = "pending"

    state.save()
    return [b for b in state.books.values() if b.status == "pending"]


def convert_to_wav(m4b_path: Path, console) -> Path | None:
    """Convert M4B to WAV using ffmpeg CLI to avoid PyAV issues."""
    wav_path = m4b_path.parent / "audio.wav"

    # Skip if already converted
    if wav_path.exists():
        console.print(f"  [dim]Using existing WAV file[/dim]")
        return wav_path

    console.print(f"  [dim]Converting M4B to WAV (fixes PyAV issues)...[/dim]")

    try:
        result = subprocess.run(
            ["ffmpeg", "-i", str(m4b_path), "-acodec", "pcm_s16le",
             "-ar", "16000", "-ac", "1", str(wav_path), "-y"],
            capture_output=True, text=True, timeout=7200  # 2 hour timeout
        )
        if result.returncode == 0:
            console.print(f"  [dim]Converted to WAV successfully[/dim]")
            return wav_path
        else:
            console.print(f"  [red]FFmpeg error: {result.stderr[:200]}[/red]")
    except subprocess.TimeoutExpired:
        console.print(f"  [red]FFmpeg conversion timed out[/red]")
    except Exception as e:
        console.print(f"  [red]Conversion error: {e}[/red]")

    return None


def transcribe_book(book: BookState, state: PipelineState, console) -> bool:
    """Transcribe a single book with progress display."""
    from faster_whisper import WhisperModel

    book.status = "in_progress"
    book.started_at = datetime.now().isoformat()
    state.save()
    log_event("transcribe_start", book.name)

    m4b_path = Path(book.m4b_path)
    output_path = m4b_path.parent / "text.md"

    try:
        start_time = time.time()

        # Convert M4B to WAV first (workaround for PyAV issues with M4B)
        audio_path = convert_to_wav(m4b_path, console)
        if not audio_path:
            raise RuntimeError("Failed to convert audio to WAV")

        # Load model (cached after first load)
        console.print(f"  [dim]Loading whisper model...[/dim]")
        model = WhisperModel("turbo", device="cuda", compute_type="float16")

        # Transcribe the WAV file (more reliable than M4B)
        console.print(f"  [dim]Transcribing audio...[/dim]")
        segments, info = model.transcribe(
            str(audio_path),
            language="en",
            beam_size=5,
            vad_filter=True,
        )

        book.duration_seconds = info.duration
        console.print(f"  [dim]Duration: {info.duration/3600:.1f}h, Language: {info.language}[/dim]")

        # Write transcript with completion marker
        with open(output_path, "w", encoding="utf-8") as f:
            for segment in segments:
                f.write(f"{segment.text}\n")
            # Write completion marker at end - this proves transcription finished
            f.write(f"\n{COMPLETION_MARKER}\n")

        elapsed = time.time() - start_time
        book.transcribe_seconds = elapsed

        # Quality gate: verify transcript before marking complete
        word_count = len(output_path.read_text().split())
        expected_min = int((book.duration_seconds / 3600) * MIN_WORDS_PER_HOUR * 0.7) if book.duration_seconds else 1000
        completion_pct = int(word_count * 100 / max(1, int((book.duration_seconds / 3600) * 9300))) if book.duration_seconds else 100

        if word_count < expected_min:
            # Quality gate FAILED - transcript too short
            book.status = "failed"
            book.error = f"Quality gate failed: {word_count} words ({completion_pct}% of expected)"
            book.completed_at = datetime.now().isoformat()
            state.save()
            log_event("quality_gate_failed", book.name,
                      word_count=word_count, expected_min=expected_min,
                      completion_pct=completion_pct)
            console.print(f"  [red]Quality gate FAILED: {word_count} words ({completion_pct}% of expected)[/red]")
            # Remove partial transcript so it can be retried
            output_path.unlink(missing_ok=True)
            return False

        book.status = "completed"
        book.completed_at = datetime.now().isoformat()
        state.save()

        speed_ratio = book.duration_seconds / elapsed if elapsed > 0 else 0
        log_event("transcribe_complete", book.name,
                  duration_seconds=book.duration_seconds,
                  transcribe_seconds=elapsed,
                  speed_ratio=speed_ratio,
                  word_count=word_count,
                  completion_pct=completion_pct)

        console.print(f"  [green]Completed in {elapsed/60:.1f}min ({speed_ratio:.1f}x realtime) - {word_count} words ({completion_pct}%)[/green]")
        return True

    except Exception as e:
        book.status = "failed"
        book.error = str(e)
        book.completed_at = datetime.now().isoformat()
        state.save()
        log_event("transcribe_error", book.name, error=str(e))
        console.print(f"  [red]Error: {e}[/red]")
        return False


def cmd_run(args):
    """Run transcription pipeline."""
    Console, Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn, TimeRemainingColumn, TaskProgressColumn, Table, Panel, Live = get_rich()
    console = Console()

    state = PipelineState.load()
    if not state.started_at:
        state.started_at = datetime.now().isoformat()

    # Discover books
    console.print(Panel.fit("[bold]Audiobook Transcription Pipeline[/bold]", border_style="blue"))
    pending_books = discover_books(state)

    summary = state.get_summary()
    console.print(f"Total: {summary['total']} books, {summary['total_audio_hours']:.1f}h audio")
    console.print(f"Status: {summary['completed']} completed, {summary['pending']} pending, {summary['skipped']} skipped, {summary['failed']} failed")

    if not pending_books:
        console.print("[green]All books already processed![/green]")
        return 0

    console.print(f"\n[bold]Processing {len(pending_books)} books...[/bold]\n")
    log_event("pipeline_start", pending=len(pending_books))

    # Process with progress bar
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        refresh_per_second=1,
    ) as progress:

        task = progress.add_task("Transcribing", total=len(pending_books))

        for i, book in enumerate(pending_books):
            progress.update(task, description=f"[cyan]{book.name[:50]}...")
            console.print(f"\n[bold][{i+1}/{len(pending_books)}] {book.name}[/bold]")

            success = transcribe_book(book, state, console)
            progress.advance(task)

            if not success and not args.continue_on_error:
                console.print("[red]Stopping due to error. Use --continue-on-error to skip failures.[/red]")
                break

    # Final summary
    summary = state.get_summary()
    console.print(f"\n[bold]Pipeline Complete[/bold]")
    console.print(f"Completed: {summary['completed']}, Failed: {summary['failed']}, Pending: {summary['pending']}")

    log_event("pipeline_complete", **summary)
    return 0 if summary['failed'] == 0 else 1


def cmd_status(args):
    """Show current status."""
    state = PipelineState.load()

    if not state.books:
        # Discover books first
        discover_books(state)

    summary = state.get_summary()

    if args.json:
        # Machine-readable output for agents
        output = {
            "summary": summary,
            "books": {k: asdict(v) for k, v in state.books.items()},
            "state_file": str(STATE_FILE),
            "log_file": str(LOG_FILE),
        }
        print(json.dumps(output, indent=2))
        return 0

    # Human-readable output
    Console, Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn, TimeRemainingColumn, TaskProgressColumn, Table, Panel, Live = get_rich()
    console = Console()

    # Summary panel
    eta_str = f"{summary['eta_hours']:.1f}h" if summary['eta_hours'] else "unknown"
    speed_str = f"{summary['avg_speed_ratio']:.1f}x" if summary['avg_speed_ratio'] else "N/A"

    console.print(Panel.fit(
        f"[bold]Transcription Progress[/bold]\n\n"
        f"Total: {summary['total']} books ({summary['total_audio_hours']:.1f}h audio)\n"
        f"Completed: [green]{summary['completed']}[/green] | "
        f"Pending: [yellow]{summary['pending']}[/yellow] | "
        f"Failed: [red]{summary['failed']}[/red] | "
        f"Skipped: [dim]{summary['skipped']}[/dim]\n\n"
        f"Avg Speed: {speed_str} realtime | ETA: {eta_str}",
        border_style="blue"
    ))

    # Book table
    if args.verbose:
        table = Table(title="Books")
        table.add_column("Book", style="cyan", max_width=50)
        table.add_column("Status", justify="center")
        table.add_column("Duration", justify="right")
        table.add_column("Time", justify="right")

        status_colors = {
            "completed": "green",
            "pending": "yellow",
            "in_progress": "blue",
            "failed": "red",
            "skipped": "dim",
        }

        for book in sorted(state.books.values(), key=lambda b: b.name):
            color = status_colors.get(book.status, "white")
            duration = f"{book.duration_seconds/3600:.1f}h" if book.duration_seconds else "-"
            trans_time = f"{book.transcribe_seconds/60:.0f}m" if book.transcribe_seconds else "-"
            table.add_row(
                book.name[:50],
                f"[{color}]{book.status}[/{color}]",
                duration,
                trans_time,
            )

        console.print(table)

    return 0


def cmd_reset(args):
    """Reset state file."""
    if STATE_FILE.exists():
        STATE_FILE.unlink()
        print(f"Removed {STATE_FILE}")
    if args.logs and LOG_FILE.exists():
        LOG_FILE.unlink()
        print(f"Removed {LOG_FILE}")
    return 0


def cmd_revalidate(args):
    """Revalidate all transcriptions and re-queue incomplete ones."""
    Console, *_ = get_rich()
    console = Console()

    state = PipelineState.load()
    requeued = []

    console.print("[bold]Revalidating transcriptions...[/bold]\n")

    for book_name, book in state.books.items():
        m4b_path = Path(book.m4b_path)
        transcript = m4b_path.parent / "text.md"
        duration = book.duration_seconds or get_audio_duration(m4b_path)
        book.duration_seconds = duration

        if book.status == "completed":
            if not transcript.exists():
                book.status = "pending"
                book.completed_at = None
                requeued.append((book_name, "transcript missing"))
            elif not is_transcript_complete(transcript, duration):
                # Calculate completion percentage
                if transcript.exists() and duration:
                    words = len(transcript.read_text().split())
                    expected = int((duration / 3600) * 9300)
                    pct = int(words * 100 / max(1, expected))
                    reason = f"incomplete ({pct}% of expected)"
                else:
                    reason = "incomplete or missing marker"
                book.status = "pending"
                book.completed_at = None
                requeued.append((book_name, reason))
            else:
                console.print(f"[green]✓[/green] {book_name[:50]}")

    state.save()

    if requeued:
        console.print(f"\n[yellow]Re-queued {len(requeued)} incomplete transcriptions:[/yellow]")
        for name, reason in requeued:
            console.print(f"  [yellow]→[/yellow] {name[:50]} ({reason})")
        log_event("revalidate_complete", requeued=len(requeued),
                  books=[name for name, _ in requeued])
    else:
        console.print("\n[green]All transcriptions validated![/green]")

    return 0


def main():
    parser = argparse.ArgumentParser(description="Audiobook transcription pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run command
    run_parser = subparsers.add_parser("run", help="Run transcription pipeline")
    run_parser.add_argument("--continue-on-error", action="store_true", help="Continue on transcription errors")
    run_parser.set_defaults(func=cmd_run)

    # status command
    status_parser = subparsers.add_parser("status", help="Show current status")
    status_parser.add_argument("--json", action="store_true", help="Output JSON for agent parsing")
    status_parser.add_argument("--verbose", "-v", action="store_true", help="Show all books")
    status_parser.set_defaults(func=cmd_status)

    # reset command
    reset_parser = subparsers.add_parser("reset", help="Reset state file")
    reset_parser.add_argument("--logs", action="store_true", help="Also remove log file")
    reset_parser.set_defaults(func=cmd_reset)

    # revalidate command
    revalidate_parser = subparsers.add_parser("revalidate",
        help="Check all transcriptions and re-queue incomplete ones")
    revalidate_parser.set_defaults(func=cmd_revalidate)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
