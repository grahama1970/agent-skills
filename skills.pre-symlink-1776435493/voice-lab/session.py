"""Follow-along session orchestration.

Play clip audio while recording Graham, synchronized with SRT display.
Coordinates PipeWire playback + recording simultaneously using asyncio,
with real-time karaoke-style subtitle prompts.
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Optional

from loguru import logger
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from alignment import align_recordings, parse_srt, print_alignment, save_alignment
from devices import find_device, get_default_source

console = Console()


async def _run_recording(
    device_id: str,
    output_path: Path,
    duration_s: float,
    sample_rate: int = 48000,
) -> asyncio.subprocess.Process:
    """Start pw-record as an async subprocess."""
    proc = await asyncio.create_subprocess_exec(
        "pw-record",
        "--format", "s16",
        "--rate", str(sample_rate),
        "--channels", "1",
        "--target", device_id,
        str(output_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    return proc


async def _run_playback(
    audio_path: Path,
    sink_id: Optional[str] = None,
) -> asyncio.subprocess.Process:
    """Start pw-play as an async subprocess."""
    cmd = ["pw-play", str(audio_path)]
    if sink_id:
        cmd.extend(["--target", sink_id])

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    return proc


async def _run_session(
    clip_path: Path,
    srt_path: Path,
    recording_path: Path,
    mic_device_id: str,
    speaker_sink_id: Optional[str] = None,
    duration_s: float = 0,
) -> bool:
    """Run the follow-along session with simultaneous play + record.

    Returns True if session completed successfully.
    """
    segments = parse_srt(srt_path)
    if not segments:
        console.print("[red]No segments found in SRT file[/red]")
        return False

    # Calculate duration from SRT if not specified
    if duration_s <= 0:
        last_seg = max(segments, key=lambda s: s.end_ms)
        duration_s = (last_seg.end_ms / 1000) + 2  # Add 2s buffer

    console.print(Panel(
        f"Clip: {clip_path.name}\n"
        f"Duration: {duration_s:.0f}s\n"
        f"Segments: {len(segments)}\n"
        f"Recording to: {recording_path}",
        title="Follow-Along Session",
    ))
    console.print("[yellow]Starting in 3 seconds... Get ready![/yellow]")
    await asyncio.sleep(3)

    recording_path.parent.mkdir(parents=True, exist_ok=True)

    # Start recording first (slightly before playback)
    rec_proc = await _run_recording(mic_device_id, recording_path, duration_s)

    # Brief delay then start playback
    await asyncio.sleep(0.1)
    play_proc = await _run_playback(clip_path, speaker_sink_id)

    # Show karaoke display
    start_time = time.monotonic()

    try:
        with Live(console=console, refresh_per_second=4) as live:
            while True:
                elapsed_ms = int((time.monotonic() - start_time) * 1000)

                # Find current and upcoming segments
                current = None
                upcoming = None
                for seg in segments:
                    if seg.start_ms <= elapsed_ms <= seg.end_ms:
                        current = seg
                    elif seg.start_ms > elapsed_ms and upcoming is None:
                        upcoming = seg

                # Build display
                display = Text()
                elapsed_s = elapsed_ms / 1000

                display.append(f"Time: {elapsed_s:.1f}s / {duration_s:.0f}s\n\n", style="dim")

                if current:
                    display.append("NOW: ", style="bold cyan")
                    display.append(f"{current.text}\n", style="bold white")
                else:
                    display.append("...\n", style="dim")

                if upcoming:
                    time_until = (upcoming.start_ms - elapsed_ms) / 1000
                    display.append(f"\nNEXT ({time_until:.1f}s): ", style="dim yellow")
                    display.append(f"{upcoming.text}", style="dim")

                live.update(Panel(display, title="Follow Along"))

                # Check if playback finished
                if play_proc.returncode is not None:
                    break

                # Check timeout
                if elapsed_ms > (duration_s * 1000) + 1000:
                    break

                await asyncio.sleep(0.25)

    except KeyboardInterrupt:
        console.print("\n[yellow]Session stopped by user[/yellow]")
    finally:
        # Stop recording
        try:
            rec_proc.send_signal(signal.SIGINT)
            await asyncio.wait_for(rec_proc.wait(), timeout=5)
        except (ProcessLookupError, asyncio.TimeoutError):
            rec_proc.kill()

        # Stop playback if still running
        if play_proc.returncode is None:
            try:
                play_proc.terminate()
                await asyncio.wait_for(play_proc.wait(), timeout=3)
            except (ProcessLookupError, asyncio.TimeoutError):
                play_proc.kill()

    if recording_path.exists():
        console.print(f"[green]Recording saved: {recording_path}[/green]")
        return True

    console.print("[red]Recording failed — no output file[/red]")
    return False


def run_follow_along(
    clip_path: Path,
    srt_path: Path,
    stem_path: Optional[Path] = None,
    persona: str = "embry",
    device: Optional[str] = None,
    headphones: Optional[str] = None,
    output_dir: Optional[Path] = None,
) -> Optional[Path]:
    """Run a follow-along session and produce alignment results.

    Args:
        clip_path: Audio clip to play back.
        srt_path: SRT subtitle file for karaoke display.
        stem_path: Original vocals stem for comparison.
        persona: Persona name for storage.
        device: Mic device name substring.
        headphones: Headphone sink name (to avoid feedback).
        output_dir: Output directory for recording + alignment.

    Returns:
        Path to output directory, or None on failure.
    """
    if not clip_path.exists():
        console.print(f"[red]Clip not found: {clip_path}[/red]")
        return None
    if not srt_path.exists():
        console.print(f"[red]SRT not found: {srt_path}[/red]")
        return None

    # Resolve devices
    if device:
        mic = find_device(device, device_type="source")
        if mic is None:
            console.print(f"[red]Mic device not found: {device}[/red]")
            return None
        mic_id = str(mic.id)
    else:
        mic = get_default_source()
        if mic is None:
            console.print("[red]No default audio source[/red]")
            return None
        mic_id = str(mic.id)

    speaker_sink_id = None
    if headphones:
        sink = find_device(headphones, device_type="sink")
        if sink:
            speaker_sink_id = str(sink.id)
            console.print(f"Playback through: [bold]{sink.name}[/bold]")
        else:
            console.print(f"[yellow]Headphone sink not found: {headphones}[/yellow]")

    # Setup output
    if output_dir is None:
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        _storage = os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb")
        output_dir = Path(f"{_storage}/media/personas/{persona}/voice-lessons/session_{ts}")

    output_dir.mkdir(parents=True, exist_ok=True)
    recording_path = output_dir / "graham.wav"

    # Run session
    success = asyncio.run(_run_session(
        clip_path=clip_path,
        srt_path=srt_path,
        recording_path=recording_path,
        mic_device_id=mic_id,
        speaker_sink_id=speaker_sink_id,
    ))

    if not success:
        return None

    # Run alignment if stem is available
    if stem_path and stem_path.exists():
        console.print("\n[cyan]Running alignment analysis...[/cyan]")
        results = align_recordings(
            graham_path=recording_path,
            original_path=stem_path,
            srt_path=srt_path,
            output_dir=output_dir,
        )
        save_alignment(results, output_dir / "alignment.json")
        print_alignment(results)
    else:
        console.print("[dim]No stem provided — skipping alignment[/dim]")

    return output_dir
