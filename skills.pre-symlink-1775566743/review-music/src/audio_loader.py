"""
Audio Loader Module for review-music skill.

Loads audio from local files or YouTube URLs, normalizes to consistent format.
"""
import tempfile
from pathlib import Path
from typing import Optional, Tuple, Union

import librosa
import numpy as np


# Standard sample rate for all processing
STANDARD_SR = 44100


def load_audio(
    source: Union[str, Path],
    sr: Optional[int] = None,
    mono: bool = True,
    duration: Optional[float] = None,
) -> Tuple[np.ndarray, int]:
    """
    Load audio from file or YouTube URL.

    Args:
        source: File path or YouTube URL
        sr: Target sample rate (None = keep original, default uses STANDARD_SR)
        mono: Convert to mono if True
        duration: Only load first N seconds (None = full file)

    Returns:
        Tuple of (audio_array, sample_rate)
    """
    source_str = str(source)

    # Check if it's a YouTube URL
    if is_youtube_url(source_str):
        return load_from_youtube(source_str, sr=sr, mono=mono, duration=duration)

    # Load from local file
    return load_from_file(source_str, sr=sr, mono=mono, duration=duration)


def load_from_file(
    file_path: Union[str, Path],
    sr: Optional[int] = None,
    mono: bool = True,
    duration: Optional[float] = None,
) -> Tuple[np.ndarray, int]:
    """
    Load audio from local file.

    Supports: mp3, wav, flac, ogg, m4a, and other formats via soundfile/audioread.
    """
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    # Use librosa to load with optional resampling
    y, loaded_sr = librosa.load(
        str(file_path),
        sr=sr if sr is not None else STANDARD_SR,
        mono=mono,
        duration=duration,
    )

    return y, loaded_sr


def load_from_youtube(
    url: str,
    sr: Optional[int] = None,
    mono: bool = True,
    duration: Optional[float] = None,
) -> Tuple[np.ndarray, int]:
    """
    Download audio from YouTube URL and load.

    Uses ingest-youtube skill to download audio, then loads with librosa.
    """
    import re
    import sys

    SKILLS_DIR = Path(__file__).resolve().parent.parent.parent
    _iy_dir = str(SKILLS_DIR / "ingest-youtube")
    if _iy_dir not in sys.path:
        sys.path.insert(0, _iy_dir)

    from youtube_transcripts.downloader import download_audio

    # Extract video ID from URL
    vid = None
    for pat in [
        r"youtube\.com/watch\?v=([a-zA-Z0-9_-]+)",
        r"youtu\.be/([a-zA-Z0-9_-]+)",
        r"youtube\.com/embed/([a-zA-Z0-9_-]+)",
        r"music\.youtube\.com/watch\?v=([a-zA-Z0-9_-]+)",
    ]:
        m = re.search(pat, url)
        if m:
            vid = m.group(1)
            break

    if not vid:
        raise ValueError(f"Could not extract video ID from: {url}")

    # Download to temporary directory
    with tempfile.TemporaryDirectory() as tmp_dir:
        audio_path, error = download_audio(vid, Path(tmp_dir))

        if error or audio_path is None:
            raise RuntimeError(f"Failed to download audio from: {url} — {error}")

        # Load the downloaded audio
        return load_from_file(
            audio_path,
            sr=sr,
            mono=mono,
            duration=duration,
        )


def is_youtube_url(url: str) -> bool:
    """Check if the URL is a YouTube URL."""
    youtube_patterns = [
        "youtube.com/watch",
        "youtu.be/",
        "youtube.com/v/",
        "youtube.com/embed/",
        "music.youtube.com/watch",
    ]
    return any(pattern in url.lower() for pattern in youtube_patterns)


def normalize_audio(
    y: np.ndarray,
    target_lufs: float = -14.0,
) -> np.ndarray:
    """
    Normalize audio to target loudness (LUFS).

    Uses simple RMS-based normalization as approximation.
    For accurate LUFS, use essentia or pyloudnorm.
    """
    # Calculate current RMS
    rms = np.sqrt(np.mean(y ** 2))

    if rms == 0:
        return y

    # Target RMS based on LUFS approximation
    # LUFS ≈ 20 * log10(RMS) - 0.691
    target_rms = 10 ** ((target_lufs + 0.691) / 20)

    # Apply gain
    gain = target_rms / rms
    return y * gain


def get_audio_info(source: Union[str, Path]) -> dict:
    """
    Get audio file information without loading full audio.

    Returns:
        Dictionary with duration, sample_rate, channels, format
    """
    import soundfile as sf

    source_str = str(source)

    if is_youtube_url(source_str):
        # For YouTube, we'd need to download to get info
        return {"source": source_str, "type": "youtube", "duration": None}

    info = sf.info(source_str)
    return {
        "source": source_str,
        "type": "file",
        "duration": info.duration,
        "sample_rate": info.samplerate,
        "channels": info.channels,
        "format": info.format,
        "subtype": info.subtype,
    }
