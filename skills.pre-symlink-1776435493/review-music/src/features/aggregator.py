"""
Feature Aggregator for review-music skill.

Combines all feature extractors into a unified pipeline.
"""
from pathlib import Path
from typing import Dict, Optional, Union

import numpy as np

from .rhythm import extract_rhythm_features
from .harmony import extract_harmony_features, extract_chord_features
from .timbre import extract_timbre_features
from .dynamics import extract_dynamics_features
from .lyrics import extract_lyrics


def extract_all_features(
    source: Union[str, Path, np.ndarray],
    sr: int = 44100,
    include_lyrics: bool = True,
    language: str = "en",
) -> Dict:
    """
    Extract all audio features from source.

    Args:
        source: File path or numpy audio array
        sr: Sample rate (only needed if source is numpy array)
        include_lyrics: Whether to transcribe lyrics
        language: Language for lyrics transcription

    Returns:
        Dictionary with all feature sections:
        - rhythm: BPM, beats, time signature
        - harmony: Key, mode, chroma
        - timbre: Spectral features, MFCC
        - dynamics: Loudness, dynamic range
        - lyrics: Transcribed text (if include_lyrics=True)
        - metadata: Duration, sample rate
    """
    # Load audio if path provided
    if isinstance(source, (str, Path)):
        from ..audio_loader import load_audio
        y, sr = load_audio(source, sr=sr)
        file_path = str(source)
    else:
        y = source
        file_path = None

    # Calculate duration
    duration = len(y) / sr

    # Extract all features
    features = {
        "metadata": {
            "file_path": file_path,
            "duration_seconds": duration,
            "sample_rate": sr,
        },
        "rhythm": extract_rhythm_features(y, sr),
        "harmony": extract_harmony_features(y, sr),
        "timbre": extract_timbre_features(y, sr),
        "dynamics": extract_dynamics_features(y, sr),
    }

    # Add chord features to harmony
    chord_features = extract_chord_features(y, sr)
    features["harmony"].update(chord_features)

    # Extract lyrics if requested
    if include_lyrics:
        if file_path:
            features["lyrics"] = extract_lyrics(file_path, language=language)
        else:
            features["lyrics"] = extract_lyrics(y, sr=sr, language=language)
    else:
        features["lyrics"] = {
            "text": "",
            "is_instrumental": True,
            "word_timestamps": [],
        }

    return features


def extract_selected_features(
    source: Union[str, Path, np.ndarray],
    sr: int = 44100,
    bpm: bool = False,
    key: bool = False,
    chords: bool = False,
    timbre: bool = False,
    dynamics: bool = False,
    lyrics: bool = False,
    language: str = "en",
) -> Dict:
    """
    Extract only selected features.

    Args:
        source: File path or numpy audio array
        sr: Sample rate
        bpm: Extract BPM/tempo features
        key: Extract key/mode features
        chords: Extract chord features
        timbre: Extract timbre/spectral features
        dynamics: Extract loudness/dynamics features
        lyrics: Extract lyrics
        language: Language for lyrics

    Returns:
        Dictionary with only the requested features
    """
    # Load audio if path provided
    if isinstance(source, (str, Path)):
        from ..audio_loader import load_audio
        y, sr = load_audio(source, sr=sr)
        file_path = str(source)
    else:
        y = source
        file_path = None

    features = {
        "metadata": {
            "file_path": file_path,
            "duration_seconds": len(y) / sr,
            "sample_rate": sr,
        }
    }

    if bpm:
        rhythm = extract_rhythm_features(y, sr)
        features["bpm"] = rhythm["bpm"]
        features["beat_positions"] = rhythm["beat_positions"]
        features["time_signature"] = rhythm["time_signature"]

    if key:
        harmony = extract_harmony_features(y, sr)
        features["key"] = harmony["key"]
        features["mode"] = harmony["mode"]
        features["scale"] = harmony["scale"]
        features["key_confidence"] = harmony["key_confidence"]

    if chords:
        chord_features = extract_chord_features(y, sr)
        features["harmonic_complexity"] = chord_features["harmonic_complexity"]
        features["chord_changes_per_minute"] = chord_features["chord_changes_per_minute"]

    if timbre:
        timbre_features = extract_timbre_features(y, sr)
        features["spectral_centroid"] = timbre_features["spectral_centroid"]
        features["brightness"] = timbre_features["brightness"]
        features["texture"] = timbre_features["texture"]
        features["mfcc_mean"] = timbre_features["mfcc_mean"]

    if dynamics:
        dynamics_features = extract_dynamics_features(y, sr)
        features["loudness_integrated"] = dynamics_features["loudness_integrated"]
        features["dynamic_range"] = dynamics_features["dynamic_range"]
        features["loudness_range"] = dynamics_features["loudness_range"]

    if lyrics:
        if file_path:
            lyrics_result = extract_lyrics(file_path, language=language)
        else:
            lyrics_result = extract_lyrics(y, sr=sr, language=language)
        features["lyrics"] = lyrics_result["text"]
        features["is_instrumental"] = lyrics_result["is_instrumental"]

    return features


def validate_features(features: Dict) -> Dict:
    """
    Validate extracted features and return summary.

    Returns:
        Dictionary with:
        - is_valid: Whether all required fields are present
        - missing_fields: List of missing fields
        - summary: Human-readable summary
    """
    required_sections = ["metadata", "rhythm", "harmony", "timbre", "dynamics"]
    missing = []

    for section in required_sections:
        if section not in features:
            missing.append(section)

    # Check specific fields
    required_fields = {
        "rhythm": ["bpm", "beat_positions", "time_signature"],
        "harmony": ["key", "mode", "scale"],
        "timbre": ["spectral_centroid", "mfcc_mean"],
        "dynamics": ["loudness_integrated", "dynamic_range"],
    }

    for section, fields in required_fields.items():
        if section in features:
            for field in fields:
                if field not in features[section]:
                    missing.append(f"{section}.{field}")

    is_valid = len(missing) == 0

    # Generate summary
    if is_valid:
        summary = (
            f"Audio: {features['metadata'].get('duration_seconds', 0):.1f}s, "
            f"{features['rhythm'].get('bpm', 0):.0f} BPM, "
            f"{features['harmony'].get('scale', 'unknown')}"
        )
    else:
        summary = f"Invalid features: missing {', '.join(missing)}"

    return {
        "is_valid": is_valid,
        "missing_fields": missing,
        "summary": summary,
    }
