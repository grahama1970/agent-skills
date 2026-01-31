"""
Harmony Feature Extraction using librosa.

Extracts: Key, mode, scale, chroma features.
"""
from typing import Dict, List, Optional, Tuple

import librosa
import numpy as np


# Pitch class names
PITCH_CLASSES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

# Major and minor scale profiles (Krumhansl-Schmuckler)
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def extract_harmony_features(
    y: np.ndarray,
    sr: int,
) -> Dict:
    """
    Extract harmony features from audio.

    Args:
        y: Audio time series (mono)
        sr: Sample rate

    Returns:
        Dictionary with:
        - key: Detected key (e.g., "C", "F#")
        - mode: "major" or "minor"
        - scale: Full scale name (e.g., "C major", "A minor")
        - key_confidence: Confidence score (0-1)
        - chroma_mean: Mean chroma vector (12 values)
    """
    # Extract chroma features
    chroma = librosa.feature.chroma_stft(y=y, sr=sr)

    # Get mean chroma (pitch class distribution)
    chroma_mean = np.mean(chroma, axis=1)

    # Detect key using Krumhansl-Schmuckler algorithm
    key, mode, confidence = detect_key(chroma_mean)

    scale = f"{key} {mode}"

    return {
        "key": key,
        "mode": mode,
        "scale": scale,
        "key_confidence": confidence,
        "chroma_mean": chroma_mean.tolist(),
    }


def detect_key(chroma: np.ndarray) -> Tuple[str, str, float]:
    """
    Detect musical key using Krumhansl-Schmuckler algorithm.

    Correlates the chroma distribution with major/minor profiles
    for all 12 possible keys.

    Args:
        chroma: 12-element chroma vector (mean across time)

    Returns:
        Tuple of (key_name, mode, confidence)
    """
    # Normalize chroma
    chroma_norm = chroma / (np.sum(chroma) + 1e-8)

    best_score = -1
    best_key = 0
    best_mode = "major"

    for shift in range(12):
        # Shift chroma to align with key
        shifted = np.roll(chroma_norm, -shift)

        # Correlate with major profile
        major_score = np.corrcoef(shifted, MAJOR_PROFILE)[0, 1]

        # Correlate with minor profile
        minor_score = np.corrcoef(shifted, MINOR_PROFILE)[0, 1]

        if major_score > best_score:
            best_score = major_score
            best_key = shift
            best_mode = "major"

        if minor_score > best_score:
            best_score = minor_score
            best_key = shift
            best_mode = "minor"

    # Convert to key name
    key_name = PITCH_CLASSES[best_key]

    # Normalize confidence to 0-1 range (correlation is -1 to 1)
    confidence = (best_score + 1) / 2

    return key_name, best_mode, float(confidence)


def extract_chord_features(
    y: np.ndarray,
    sr: int,
    hop_length: int = 512,
) -> Dict:
    """
    Extract chord-related features (simplified - full chord detection requires more complex models).

    Args:
        y: Audio time series
        sr: Sample rate
        hop_length: Hop length for analysis

    Returns:
        Dictionary with chord-related features
    """
    # Get chroma with time resolution
    chroma = librosa.feature.chroma_stft(y=y, sr=sr, hop_length=hop_length)

    # Harmonic complexity: variance in chroma over time
    chroma_variance = np.var(chroma, axis=1)
    harmonic_complexity = float(np.mean(chroma_variance))

    # Chord changes: detect when chroma changes significantly
    chroma_diff = np.diff(chroma, axis=1)
    chord_change_strength = np.sum(np.abs(chroma_diff), axis=0)

    # Count chord changes (peaks in change strength)
    threshold = np.mean(chord_change_strength) + np.std(chord_change_strength)
    chord_changes = np.sum(chord_change_strength > threshold)

    # Duration in seconds
    duration = len(y) / sr

    # Chord changes per minute
    chord_changes_per_minute = (chord_changes / duration) * 60 if duration > 0 else 0

    return {
        "harmonic_complexity": harmonic_complexity,
        "chord_changes_per_minute": float(chord_changes_per_minute),
        "num_chord_changes": int(chord_changes),
    }


def get_dominant_pitches(
    chroma: np.ndarray,
    top_n: int = 3,
) -> List[str]:
    """
    Get the top N most prominent pitch classes.

    Args:
        chroma: Mean chroma vector (12 values)
        top_n: Number of top pitches to return

    Returns:
        List of pitch class names in order of prominence
    """
    # Get indices of top pitches
    top_indices = np.argsort(chroma)[-top_n:][::-1]

    return [PITCH_CLASSES[i] for i in top_indices]
