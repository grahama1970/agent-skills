"""PipeWire audio recording with quality checks.

Record audio from PipeWire using pw-record with device selection,
real-time level monitoring, and post-processing (trim silence,
noise reduction).

Recording pattern from converse/surfaces.py KDESurface.
"""

from __future__ import annotations

import signal
import subprocess
import time
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf
from loguru import logger
from rich.console import Console
from rich.live import Live
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn

from devices import find_device, get_default_source

console = Console()


def _check_aec_module() -> bool:
    """Check if OpenClaw AEC module is active (causes XRUNs on USB devices)."""
    aec_conf = Path("/etc/pipewire/pipewire.conf.d/99-openclaw-aec.conf")
    if aec_conf.exists():
        content = aec_conf.read_text()
        # Check if it's actually enabled (not commented out)
        for line in content.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "echo-cancel" in stripped:
                return True
    return False


def _trim_silence(
    audio: np.ndarray,
    sr: int,
    threshold_db: float = -40.0,
    min_silence_ms: int = 200,
) -> np.ndarray:
    """Trim leading and trailing silence from audio."""
    frame_len = int(min_silence_ms * sr / 1000)
    threshold_linear = 10 ** (threshold_db / 20)

    # Find first non-silent frame
    start = 0
    for i in range(0, len(audio) - frame_len, frame_len):
        frame = audio[i : i + frame_len]
        if np.sqrt(np.mean(frame**2)) > threshold_linear:
            start = max(0, i - frame_len)  # Keep a small buffer
            break

    # Find last non-silent frame
    end = len(audio)
    for i in range(len(audio) - frame_len, 0, -frame_len):
        frame = audio[i : i + frame_len]
        if np.sqrt(np.mean(frame**2)) > threshold_linear:
            end = min(len(audio), i + 2 * frame_len)  # Keep a small buffer
            break

    return audio[start:end]


def _apply_denoise(audio: np.ndarray, sr: int) -> np.ndarray:
    """Apply noise reduction using noisereduce library."""
    try:
        import noisereduce as nr

        return nr.reduce_noise(y=audio, sr=sr, prop_decrease=0.8)
    except ImportError:
        logger.warning("noisereduce not installed, skipping denoising")
        return audio


def record_audio(
    device_name: Optional[str] = None,
    duration_s: int = 30,
    output_path: Path = Path("/tmp/voice-lab-recording.wav"),
    denoise: bool = False,
    sample_rate: int = 48000,
    trim: bool = True,
) -> Optional[Path]:
    """Record audio from a PipeWire device.

    Args:
        device_name: Device name substring (e.g. "Jabra"). Uses default if None.
        duration_s: Recording duration in seconds.
        output_path: Output WAV path.
        denoise: Apply noise reduction after recording.
        sample_rate: Sample rate (default 48000 for PipeWire).
        trim: Trim leading/trailing silence.

    Returns:
        Path to recorded file, or None on failure.
    """
    # Check AEC module
    if _check_aec_module():
        console.print(
            "[yellow]WARNING: OpenClaw AEC echo-cancel module is active.[/yellow]\n"
            "This may cause XRUN issues on USB devices like Jabra SPEAK 510.\n"
            "Consider disabling: sudo mv /etc/pipewire/pipewire.conf.d/99-openclaw-aec.conf{,.disabled}\n"
        )

    # Resolve device
    if device_name:
        device = find_device(device_name, device_type="source")
        if device is None:
            console.print(f"[red]Device not found: {device_name}[/red]")
            return None
        target_id = str(device.id)
        console.print(f"Recording from: [bold]{device.name}[/bold] (ID: {device.id})")
    else:
        device = get_default_source()
        if device is None:
            console.print("[red]No default audio source found[/red]")
            return None
        target_id = str(device.id)
        console.print(f"Recording from default: [bold]{device.name}[/bold]")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Build pw-record command
    cmd = [
        "pw-record",
        "--format", "s16",
        "--rate", str(sample_rate),
        "--channels", "1",
        "--target", target_id,
        str(output_path),
    ]

    console.print(f"Recording {duration_s}s at {sample_rate}Hz...")
    console.print("[dim]Press Ctrl+C to stop early[/dim]")

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait for duration or user interrupt
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}s"),
            console=console,
        ) as progress:
            task = progress.add_task("Recording", total=duration_s)
            for _ in range(duration_s):
                time.sleep(1)
                progress.update(task, advance=1)
                if proc.poll() is not None:
                    break

        # Stop recording
        proc.send_signal(signal.SIGINT)
        proc.wait(timeout=5)

    except KeyboardInterrupt:
        console.print("\n[yellow]Recording stopped by user[/yellow]")
        proc.send_signal(signal.SIGINT)
        proc.wait(timeout=5)
    except Exception as exc:
        logger.error(f"Recording failed: {exc}")
        if proc.poll() is None:
            proc.kill()
        return None

    if not output_path.exists():
        console.print("[red]Recording failed — no output file[/red]")
        return None

    # Post-processing
    try:
        audio, sr = sf.read(str(output_path), dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)

        original_duration = len(audio) / sr
        console.print(f"Recorded: {original_duration:.1f}s")

        # Trim silence
        if trim:
            audio = _trim_silence(audio, sr)
            trimmed_duration = len(audio) / sr
            if trimmed_duration < original_duration:
                console.print(f"Trimmed: {original_duration:.1f}s → {trimmed_duration:.1f}s")

        # Denoise
        if denoise:
            console.print("Applying noise reduction...")
            audio = _apply_denoise(audio, sr)

        # Save processed audio
        sf.write(str(output_path), audio, sr)

        # Show quality info
        rms = np.sqrt(np.mean(audio**2))
        peak = np.max(np.abs(audio))
        rms_db = 20 * np.log10(rms + 1e-10)
        peak_db = 20 * np.log10(peak + 1e-10)

        console.print(f"RMS: {rms_db:.1f} dB | Peak: {peak_db:.1f} dB")

        if peak >= 0.99:
            console.print("[red]WARNING: Clipping detected![/red]")
        if rms_db < -35:
            console.print("[yellow]WARNING: Recording is very quiet[/yellow]")

        console.print(f"[green]Saved: {output_path}[/green]")
        return output_path

    except Exception as exc:
        logger.error(f"Post-processing failed: {exc}")
        console.print(f"[yellow]Raw recording saved (post-processing failed): {output_path}[/yellow]")
        return output_path
