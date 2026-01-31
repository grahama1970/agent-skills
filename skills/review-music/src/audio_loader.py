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

    Uses yt-dlp to download audio, then loads with librosa.
    """
    import yt_dlp

    # Create temporary file for download
    with tempfile.TemporaryDirectory() as tmp_dir:
        output_template = f"{tmp_dir}/audio.%(ext)s"

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
                "preferredquality": "192",
            }],
            "quiet": True,
            "no_warnings": True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # Find the downloaded file
        audio_files = list(Path(tmp_dir).glob("audio.*"))
        if not audio_files:
            raise RuntimeError(f"Failed to download audio from: {url}")

        # Load the downloaded audio
        return load_from_file(
            audio_files[0],
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
