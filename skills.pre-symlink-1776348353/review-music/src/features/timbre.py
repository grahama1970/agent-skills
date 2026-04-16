"""
Timbre Feature Extraction using librosa.

Extracts: MFCC, spectral features (centroid, bandwidth, rolloff, flatness), zero crossing rate.
"""
from typing import Dict, List

import librosa
import numpy as np


def extract_timbre_features(
    y: np.ndarray,
    sr: int,
    n_mfcc: int = 13,
) -> Dict:
    """
    Extract timbre features from audio.

    Args:
        y: Audio time series (mono)
        sr: Sample rate
        n_mfcc: Number of MFCC coefficients

    Returns:
        Dictionary with:
        - mfcc_mean: Mean MFCC coefficients
        - spectral_centroid: Mean spectral centroid (brightness)
        - spectral_bandwidth: Mean spectral bandwidth (frequency spread)
        - spectral_rolloff: Mean spectral rolloff (high-frequency content)
        - spectral_flatness: Mean spectral flatness (noise vs tone)
        - zero_crossing_rate: Mean zero crossing rate (noisiness)
        - brightness_category: "dark", "neutral", or "bright"
        - texture: "sparse", "layered", or "dense"
    """
    # MFCC (timbre fingerprint)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=n_mfcc)
    mfcc_mean = np.mean(mfcc, axis=1).tolist()

    # Spectral centroid (brightness)
    spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
    centroid_mean = float(np.mean(spectral_centroid))

    # Spectral bandwidth (frequency spread)
    spectral_bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr)
    bandwidth_mean = float(np.mean(spectral_bandwidth))

    # Spectral rolloff (high-frequency content boundary)
    spectral_rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)
    rolloff_mean = float(np.mean(spectral_rolloff))

    # Spectral flatness (noise vs tone)
    spectral_flatness = librosa.feature.spectral_flatness(y=y)
    flatness_mean = float(np.mean(spectral_flatness))

    # Zero crossing rate (correlates with noisiness/percussiveness)
    zcr = librosa.feature.zero_crossing_rate(y)
    zcr_mean = float(np.mean(zcr))

    # Spectral contrast (difference between peaks and valleys)
    spectral_contrast = librosa.feature.spectral_contrast(y=y, sr=sr)
    contrast_mean = float(np.mean(spectral_contrast))

    # Categorize brightness
    brightness_category = categorize_brightness(centroid_mean)

    # Categorize texture based on spectral features
    texture = categorize_texture(bandwidth_mean, flatness_mean, contrast_mean)

    return {
        "mfcc_mean": mfcc_mean,
        "spectral_centroid": centroid_mean,
        "spectral_bandwidth": bandwidth_mean,
        "spectral_rolloff": rolloff_mean,
        "spectral_flatness": flatness_mean,
        "spectral_contrast": contrast_mean,
        "zero_crossing_rate": zcr_mean,
        "brightness": brightness_category,
        "texture": texture,
    }


def categorize_brightness(centroid: float) -> str:
    """
    Categorize brightness based on spectral centroid.

    Dark: < 1500 Hz (bass-heavy, low frequencies)
    Neutral: 1500-3000 Hz (balanced)
    Bright: > 3000 Hz (high frequencies, crisp)
    """
    if centroid < 1500:
        return "dark"
    elif centroid < 3000:
        return "neutral"
    else:
        return "bright"


def categorize_texture(
    bandwidth: float,
    flatness: float,
    contrast: float,
) -> str:
    """
    Categorize texture based on spectral features.

    Sparse: Low bandwidth, high contrast (solo instruments, minimal)
    Layered: Medium bandwidth, low flatness (multiple distinct elements)
    Dense: High bandwidth, high flatness (full mix, noise-like)
    """
    # Normalize features (approximate ranges)
    bandwidth_norm = min(bandwidth / 3000, 1.0)
    flatness_norm = min(flatness, 1.0)
    contrast_norm = min(contrast / 100, 1.0)

    if bandwidth_norm < 0.3 and contrast_norm > 0.5:
        return "sparse"
    elif flatness_norm > 0.3 or bandwidth_norm > 0.6:
        return "dense"
    else:
        return "layered"


def extract_mfcc_delta(
    y: np.ndarray,
    sr: int,
    n_mfcc: int = 13,
) -> Dict:
    """
    Extract MFCC with delta and delta-delta features.

    Useful for capturing temporal dynamics of timbre.
    """
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=n_mfcc)

    # Delta (first derivative)
    mfcc_delta = librosa.feature.delta(mfcc)

    # Delta-delta (second derivative)
    mfcc_delta2 = librosa.feature.delta(mfcc, order=2)

    return {
        "mfcc_mean": np.mean(mfcc, axis=1).tolist(),
        "mfcc_delta_mean": np.mean(mfcc_delta, axis=1).tolist(),
        "mfcc_delta2_mean": np.mean(mfcc_delta2, axis=1).tolist(),
    }
