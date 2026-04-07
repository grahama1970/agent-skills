"""
Movie Ingest Skill - Extraction Module
Video/audio extraction using ffmpeg.
"""
from pathlib import Path
from typing import Optional

from rich.console import Console

from utils import get_ffmpeg_bin, run_subprocess, format_hms

console = Console()


def extract_audio(
    input_file: Path,
    output_file: Path,
    sample_rate: int = 16000,
    channels: int = 1,
    timeout_sec: int = 300,
) -> bool:
    """
    Extract audio from video file as mono WAV.

    Args:
        input_file: Source video file
        output_file: Destination WAV file
        sample_rate: Audio sample rate (default 16kHz for Whisper)
        channels: Number of audio channels (default 1 for mono)
        timeout_sec: Command timeout

    Returns:
        True on success
    """
    output_file.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        get_ffmpeg_bin(), "-y",
        "-i", str(input_file),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", str(sample_rate),
        "-ac", str(channels),
        str(output_file)
    ]

    console.print(f"[cyan]Extracting audio to {output_file}...[/cyan]")
    run_subprocess(cmd, timeout_sec=timeout_sec)
    return True


def extract_video_clip(
    input_file: Path,
    output_file: Path,
    start_sec: float,
    end_sec: float,
    codec: str = "copy",
    timeout_sec: int = 120,
) -> bool:
    """
    Extract a clip from a video file.

    Args:
        input_file: Source video file
        output_file: Destination clip file
        start_sec: Start time in seconds
        end_sec: End time in seconds
        codec: Video codec (default "copy" for no re-encoding)
        timeout_sec: Command timeout

    Returns:
        True on success
    """
    output_file.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        get_ffmpeg_bin(), "-y",
        "-ss", format_hms(start_sec),
        "-to", format_hms(end_sec),
        "-i", str(input_file),
        "-c", codec,
        str(output_file)
    ]

    console.print(f"[cyan]Extracting clip {format_hms(start_sec)} → {format_hms(end_sec)}...[/cyan]")
    run_subprocess(cmd, timeout_sec=timeout_sec)
    return True


def get_video_duration(input_file: Path) -> Optional[float]:
    """
    Get the duration of a video file in seconds.

    Returns:
        Duration in seconds, or None on error
    """
    import subprocess

    cmd = [
        get_ffmpeg_bin(),
        "-i", str(input_file),
        "-f", "null", "-"
    ]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
        # Parse duration from ffmpeg stderr output
        import re
        stderr = result.stderr.decode(errors='ignore')
        match = re.search(r'Duration: (\d+):(\d+):(\d+\.?\d*)', stderr)
        if match:
            h, m, s = match.groups()
            return int(h) * 3600 + int(m) * 60 + float(s)
    except Exception as e:
        console.print(f"[yellow]Could not get video duration: {e}[/yellow]")

    return None


def probe_media_info(input_file: Path) -> dict:
    """
    Get detailed media information using ffprobe.

    Returns:
        Dict with streams, format info, etc.
    """
    import json
    import subprocess

    # Try ffprobe first
    ffprobe = "ffprobe"
    ffmpeg_bin = get_ffmpeg_bin()
    if ffmpeg_bin and "/" in ffmpeg_bin:
        ffprobe = str(Path(ffmpeg_bin).parent / "ffprobe")

    cmd = [
        ffprobe,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(input_file)
    ]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception as e:
        console.print(f"[yellow]ffprobe failed: {e}[/yellow]")

    return {}
