"""
Dynamics Feature Extraction using librosa and scipy.

Extracts: Loudness (LUFS estimate), dynamic range, loudness variation.
"""
from typing import Dict, List, Tuple

import librosa
import numpy as np
from scipy import signal


def extract_dynamics_features(
    y: np.ndarray,
    sr: int,
) -> Dict:
    """
    Extract dynamics features from audio.

    Args:
        y: Audio time series (mono)
        sr: Sample rate

    Returns:
        Dictionary with:
        - loudness_integrated: Estimated integrated loudness (LUFS-like)
        - dynamic_range: Peak-to-RMS ratio in dB
        - loudness_range: Variation in loudness (LU)
        - peak_db: Peak level in dB
        - rms_db: RMS level in dB
        - crest_factor: Peak to RMS ratio
    """
    # RMS energy over time
    rms = librosa.feature.rms(y=y)
    rms_mean = float(np.mean(rms))

    # Peak amplitude
    peak = float(np.max(np.abs(y)))

    # Convert to dB (with small offset to avoid log(0))
    peak_db = 20 * np.log10(peak + 1e-10)
    rms_db = 20 * np.log10(rms_mean + 1e-10)

    # Crest factor (peak to RMS ratio)
    crest_factor = peak / rms_mean if rms_mean > 0 else 0

    # Dynamic range (peak to RMS in dB)
    dynamic_range = peak_db - rms_db

    # Loudness range (variation in loudness over time)
    # Use windowed RMS converted to dB
    rms_db_series = 20 * np.log10(rms[0] + 1e-10)
    loudness_range = float(np.percentile(rms_db_series, 95) - np.percentile(rms_db_series, 10))

    # Estimated integrated loudness (simplified LUFS-like measure)
    # True LUFS requires K-weighting filter, this is an approximation
    loudness_integrated = estimate_lufs(y, sr)

    return {
        "loudness_integrated": loudness_integrated,
        "dynamic_range": float(dynamic_range),
        "loudness_range": loudness_range,
        "peak_db": float(peak_db),
        "rms_db": float(rms_db),
        "crest_factor": float(crest_factor),
    }


def estimate_lufs(
    y: np.ndarray,
    sr: int,
) -> float:
    """
    Estimate integrated loudness in LUFS.

    This is a simplified approximation. For accurate LUFS measurement,
    use pyloudnorm or essentia.

    The approximation:
    1. Apply K-weighting filter (simplified high-shelf)
    2. Calculate mean square
    3. Convert to LUFS scale
    """
    # Apply simplified K-weighting (high-shelf boost)
    # True K-weighting has two stages: high-shelf and high-pass
    # This is a simplified version

    # High-shelf filter to boost high frequencies
    b, a = signal.butter(2, 1500 / (sr / 2), btype='high')
    y_filtered = signal.filtfilt(b, a, y)

    # Combine with original (approximation of K-weighting)
    y_k = 0.5 * y + 0.5 * y_filtered

    # Calculate mean square
    mean_square = np.mean(y_k ** 2)

    # Convert to LUFS (LKFS)
    # LUFS = -0.691 + 10 * log10(mean_square)
    if mean_square > 0:
        lufs = -0.691 + 10 * np.log10(mean_square)
    else:
        lufs = -70  # Very quiet

    return float(lufs)


def analyze_loudness_contour(
    y: np.ndarray,
    sr: int,
    frame_length: int = 2048,
    hop_length: int = 512,
) -> Dict:
    """
    Analyze loudness contour over time.

    Returns:
        Dictionary with:
        - loudness_times: Time points in seconds
        - loudness_values: Loudness values in dB
        - trend: "building", "fading", "steady", or "dynamic"
    """
    # Calculate RMS over time
    rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]

    # Convert to dB
    rms_db = 20 * np.log10(rms + 1e-10)

    # Time points
    times = librosa.frames_to_time(np.arange(len(rms_db)), sr=sr, hop_length=hop_length)

    # Analyze trend
    trend = analyze_loudness_trend(rms_db)

    return {
        "loudness_times": times.tolist(),
        "loudness_values": rms_db.tolist(),
        "trend": trend,
    }


def analyze_loudness_trend(loudness_db: np.ndarray) -> str:
    """
    Analyze overall loudness trend.

    Returns: "building", "fading", "steady", or "dynamic"
    """
    if len(loudness_db) < 10:
        return "steady"

    # Split into segments
    n_segments = 4
    segment_len = len(loudness_db) // n_segments
    segment_means = []

    for i in range(n_segments):
        start = i * segment_len
        end = start + segment_len
        segment_means.append(np.mean(loudness_db[start:end]))

    # Calculate trend
    diffs = np.diff(segment_means)

    # Overall variance
    variance = np.var(loudness_db)

    # Determine trend
    if np.all(diffs > 1):  # Consistently increasing
        return "building"
    elif np.all(diffs < -1):  # Consistently decreasing
        return "fading"
    elif variance < 5:  # Low variance
        return "steady"
    else:
        return "dynamic"


def detect_crescendos(
    y: np.ndarray,
    sr: int,
    min_duration: float = 2.0,
    min_gain_db: float = 6.0,
) -> List[Tuple[float, float, float]]:
    """
    Detect crescendos (gradual increases in loudness).

    Args:
        y: Audio time series
        sr: Sample rate
        min_duration: Minimum crescendo duration in seconds
        min_gain_db: Minimum loudness increase in dB

    Returns:
        List of (start_time, end_time, gain_db) tuples
    """
    # Calculate RMS over time
    hop_length = 512
    rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    rms_db = 20 * np.log10(rms + 1e-10)

    crescendos = []

    # Sliding window to find increasing segments
    window_frames = int(min_duration * sr / hop_length)

    for i in range(len(rms_db) - window_frames):
        segment = rms_db[i:i + window_frames]

        # Check if segment is consistently increasing
        diffs = np.diff(segment)
        if np.mean(diffs > 0) > 0.6:  # 60% of steps are increasing
            gain = segment[-1] - segment[0]
            if gain >= min_gain_db:
                start_time = librosa.frames_to_time(i, sr=sr, hop_length=hop_length)
                end_time = librosa.frames_to_time(i + window_frames, sr=sr, hop_length=hop_length)
                crescendos.append((float(start_time), float(end_time), float(gain)))

    # Merge overlapping crescendos
    return merge_overlapping(crescendos)


def merge_overlapping(
    segments: List[Tuple[float, float, float]],
) -> List[Tuple[float, float, float]]:
    """Merge overlapping segments."""
    if not segments:
        return []

    # Sort by start time
    sorted_segments = sorted(segments, key=lambda x: x[0])

    merged = [sorted_segments[0]]

    for start, end, gain in sorted_segments[1:]:
        prev_start, prev_end, prev_gain = merged[-1]

        if start <= prev_end:
            # Overlapping - merge
            merged[-1] = (prev_start, max(end, prev_end), max(gain, prev_gain))
        else:
            merged.append((start, end, gain))

    return merged
