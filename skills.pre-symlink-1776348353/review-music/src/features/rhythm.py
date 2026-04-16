"""
Rhythm Feature Extraction using librosa.

Extracts: BPM, beat positions, tempo variance, time signature estimation.
"""
from typing import Dict, List, Optional, Tuple

import librosa
import numpy as np


def extract_rhythm_features(
    y: np.ndarray,
    sr: int,
) -> Dict:
    """
    Extract rhythm features from audio.

    Args:
        y: Audio time series (mono)
        sr: Sample rate

    Returns:
        Dictionary with:
        - bpm: Estimated tempo in beats per minute
        - beat_positions: List of beat times in seconds
        - tempo_variance: Variance in tempo (0 = steady, higher = more variation)
        - time_signature: Estimated time signature (e.g., "4/4", "3/4")
        - beat_strength: Average strength of detected beats
    """
    # Get tempo and beat frames
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)

    # Handle librosa returning array for tempo
    if hasattr(tempo, '__len__'):
        bpm = float(tempo[0]) if len(tempo) > 0 else 0.0
    else:
        bpm = float(tempo)

    # Convert beat frames to times
    beat_positions = librosa.frames_to_time(beat_frames, sr=sr).tolist()

    # Calculate tempo variance from beat intervals
    tempo_variance = calculate_tempo_variance(beat_positions)

    # Estimate time signature
    time_signature = estimate_time_signature(y, sr, beat_frames)

    # Calculate beat strength from onset envelope
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    beat_strength = float(np.mean(onset_env[beat_frames])) if len(beat_frames) > 0 else 0.0

    return {
        "bpm": bpm,
        "beat_positions": beat_positions,
        "tempo_variance": tempo_variance,
        "time_signature": time_signature,
        "beat_strength": beat_strength,
        "num_beats": len(beat_positions),
    }


def calculate_tempo_variance(beat_positions: List[float]) -> float:
    """
    Calculate tempo variance from beat positions.

    Lower values = more steady tempo.
    """
    if len(beat_positions) < 3:
        return 0.0

    # Calculate inter-beat intervals
    intervals = np.diff(beat_positions)

    if len(intervals) == 0:
        return 0.0

    # Calculate coefficient of variation (normalized variance)
    mean_interval = np.mean(intervals)
    if mean_interval == 0:
        return 0.0

    cv = np.std(intervals) / mean_interval
    return float(cv)


def estimate_time_signature(
    y: np.ndarray,
    sr: int,
    beat_frames: np.ndarray,
) -> str:
    """
    Estimate time signature from beat patterns.

    Uses onset strength to detect strong beats (downbeats).
    Returns common time signatures: "4/4", "3/4", "6/8", "2/4"
    """
    if len(beat_frames) < 8:
        return "4/4"  # Default for short audio

    # Get onset strength at beat positions
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    beat_strengths = onset_env[beat_frames]

    # Normalize beat strengths
    beat_strengths = (beat_strengths - np.min(beat_strengths))
    max_strength = np.max(beat_strengths)
    if max_strength > 0:
        beat_strengths = beat_strengths / max_strength

    # Find periodicity in beat strengths (looking for downbeat pattern)
    # Try different groupings and see which has strongest first-beat emphasis
    scores = {}

    for meter in [2, 3, 4, 6]:
        if len(beat_strengths) >= meter * 2:
            # Group beats and check if first beat of each group is strongest
            groups = []
            for i in range(0, len(beat_strengths) - meter, meter):
                group = beat_strengths[i:i + meter]
                if len(group) == meter:
                    groups.append(group)

            if groups:
                avg_group = np.mean(groups, axis=0)
                # Score: how much stronger is first beat compared to others
                first_beat_score = avg_group[0] - np.mean(avg_group[1:])
                scores[meter] = first_beat_score

    # Choose meter with strongest first-beat emphasis
    if scores:
        best_meter = max(scores, key=scores.get)
        if best_meter == 3:
            return "3/4"
        elif best_meter == 6:
            return "6/8"
        elif best_meter == 2:
            return "2/4"

    return "4/4"  # Default


def detect_downbeats(
    y: np.ndarray,
    sr: int,
    beat_frames: np.ndarray,
    beats_per_bar: int = 4,
) -> List[float]:
    """
    Detect downbeat (measure start) positions.

    Args:
        y: Audio time series
        sr: Sample rate
        beat_frames: Beat frame indices from beat_track
        beats_per_bar: Beats per measure (e.g., 4 for 4/4 time)

    Returns:
        List of downbeat times in seconds
    """
    if len(beat_frames) < beats_per_bar:
        return []

    # Get onset strength
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)

    # Find the strongest beat in each potential bar
    downbeat_frames = []

    for i in range(0, len(beat_frames), beats_per_bar):
        bar_beats = beat_frames[i:i + beats_per_bar]
        if len(bar_beats) == beats_per_bar:
            # Assume first beat of bar is downbeat
            downbeat_frames.append(bar_beats[0])

    # Convert to times
    downbeat_times = librosa.frames_to_time(np.array(downbeat_frames), sr=sr)
    return downbeat_times.tolist()
