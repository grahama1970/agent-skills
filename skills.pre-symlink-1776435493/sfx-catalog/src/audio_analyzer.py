"""Audio analysis utilities for SFX cataloging.

Extracts acoustic features for classification and bridge-tag prediction.
Rich feature set enables both rule-based classification and trained models.
"""

import sys
import json
from pathlib import Path
from typing import Optional
import warnings

# Suppress librosa warnings
warnings.filterwarnings("ignore", category=UserWarning)

import librosa
import soundfile as sf
import numpy as np


def analyze_audio_file(path: Path) -> Optional[dict]:
    """Analyze an audio file and extract features.

    Args:
        path: Path to audio file

    Returns:
        Dictionary of audio features, or None if file is corrupted
    """
    try:
        # Load audio
        y, sr = librosa.load(str(path), sr=None, mono=True)
        duration = librosa.get_duration(y=y, sr=sr)

        # --- Spectral features ---
        spectral_centroids = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
        centroid = float(np.mean(spectral_centroids))
        centroid_std = float(np.std(spectral_centroids))

        spectral_bw = librosa.feature.spectral_bandwidth(y=y, sr=sr)[0]
        bandwidth_mean = float(np.mean(spectral_bw))

        spectral_ro = librosa.feature.spectral_rolloff(y=y, sr=sr)[0]
        rolloff_mean = float(np.mean(spectral_ro))

        spectral_flatness = librosa.feature.spectral_flatness(y=y)[0]
        flatness_mean = float(np.mean(spectral_flatness))

        # Zero crossing rate
        zcr = librosa.feature.zero_crossing_rate(y)[0]
        zcr_mean = float(np.mean(zcr))
        zcr_std = float(np.std(zcr))
        dominant_freq = float(zcr_mean * sr / 2)

        # MFCCs (13 coefficients — standard for audio classification)
        mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
        mfcc_means = [float(np.mean(mfccs[i])) for i in range(13)]
        mfcc_stds = [float(np.std(mfccs[i])) for i in range(13)]

        # Chroma (12 pitch classes)
        chroma = librosa.feature.chroma_stft(y=y, sr=sr)
        chroma_means = [float(np.mean(chroma[i])) for i in range(12)]

        # Spectral contrast (7 bands)
        contrast = librosa.feature.spectral_contrast(y=y, sr=sr)
        contrast_means = [float(np.mean(contrast[i])) for i in range(contrast.shape[0])]

        # --- Envelope / temporal features ---
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        onset_rate = float(np.mean(onset_env))
        onset_std = float(np.std(onset_env))

        # Onset detection with correct frame-to-time conversion
        onset_frames = librosa.onset.onset_detect(y=y, sr=sr)
        num_onsets = len(onset_frames)
        if num_onsets > 0:
            # FIX: use frames_to_time, not frame_index / sr
            attack_s = float(librosa.frames_to_time(onset_frames[0], sr=sr))
            attack_ms = attack_s * 1000.0
            if attack_ms < 50:
                envelope_type = "impact"
            elif attack_ms < 200:
                envelope_type = "percussive"
            else:
                envelope_type = "sustained"
        else:
            attack_ms = 0.0
            envelope_type = "sustained"

        # Onset density (onsets per second)
        onset_density = num_onsets / max(duration, 0.01)

        # --- Loudness / dynamics ---
        rms = librosa.feature.rms(y=y)[0]
        rms_mean = float(np.mean(rms))
        rms_std = float(np.std(rms))
        peak_db = float(librosa.amplitude_to_db(np.abs(y).max(), ref=1.0))
        rms_db = float(librosa.amplitude_to_db(rms_mean, ref=1.0))

        # Dynamic range (difference between loud and quiet parts)
        rms_db_frames = librosa.amplitude_to_db(rms, ref=1.0)
        dynamic_range = float(np.percentile(rms_db_frames, 95) - np.percentile(rms_db_frames, 5))

        # Crest factor (peak-to-RMS ratio — higher = more impulsive)
        crest_factor = float(np.abs(y).max() / max(rms_mean, 1e-10))

        return {
            "duration": float(duration),
            "sample_rate": int(sr),
            "channels": 1,  # We loaded as mono
            "frequency_profile": {
                "dominant_freq": dominant_freq,
                "spectral_centroid": centroid,
                "centroid_std": centroid_std,
                "bandwidth": bandwidth_mean,
                "rolloff": rolloff_mean,
                "flatness": flatness_mean,
                "zcr_mean": zcr_mean,
                "zcr_std": zcr_std,
            },
            "envelope": {
                "type": envelope_type,
                "attack_ms": attack_ms,
                "num_onsets": num_onsets,
                "onset_density": onset_density,
                "onset_strength_mean": onset_rate,
                "onset_strength_std": onset_std,
            },
            "loudness": {
                "peak_db": peak_db,
                "rms_db": rms_db,
                "rms_std": rms_std,
                "dynamic_range": dynamic_range,
                "crest_factor": crest_factor,
            },
            "mfcc": {
                "means": mfcc_means,
                "stds": mfcc_stds,
            },
            "chroma": chroma_means,
            "spectral_contrast": contrast_means,
        }

    except Exception as e:
        print(f"[WARN] Failed to analyze {path}: {e}", file=sys.stderr)
        return None


def extract_feature_vector(features: dict) -> list[float]:
    """Flatten audio features into a fixed-length vector for ML.

    Returns a 67-dimensional vector:
      - 8 spectral features
      - 6 envelope features
      - 5 loudness features
      - 13 MFCC means + 13 MFCC stds
      - 12 chroma means
      - 7 spectral contrast means
      - 2 duration features
      - 1 sample rate (normalized)

    Args:
        features: Dictionary from analyze_audio_file()

    Returns:
        List of floats, fixed length 67
    """
    freq = features.get("frequency_profile", {})
    env = features.get("envelope", {})
    loud = features.get("loudness", {})
    mfcc = features.get("mfcc", {})
    chroma = features.get("chroma", [0.0] * 12)
    contrast = features.get("spectral_contrast", [0.0] * 7)

    vec = []
    # Spectral (8)
    vec.append(freq.get("spectral_centroid", 0.0))
    vec.append(freq.get("centroid_std", 0.0))
    vec.append(freq.get("bandwidth", 0.0))
    vec.append(freq.get("rolloff", 0.0))
    vec.append(freq.get("flatness", 0.0))
    vec.append(freq.get("dominant_freq", 0.0))
    vec.append(freq.get("zcr_mean", 0.0))
    vec.append(freq.get("zcr_std", 0.0))
    # Envelope (6)
    vec.append(env.get("attack_ms", 0.0))
    vec.append(env.get("num_onsets", 0))
    vec.append(env.get("onset_density", 0.0))
    vec.append(env.get("onset_strength_mean", 0.0))
    vec.append(env.get("onset_strength_std", 0.0))
    vec.append(1.0 if env.get("type") == "impact" else (0.5 if env.get("type") == "percussive" else 0.0))
    # Loudness (5)
    vec.append(loud.get("peak_db", -60.0))
    vec.append(loud.get("rms_db", -60.0))
    vec.append(loud.get("rms_std", 0.0))
    vec.append(loud.get("dynamic_range", 0.0))
    vec.append(loud.get("crest_factor", 1.0))
    # MFCCs (26)
    vec.extend(mfcc.get("means", [0.0] * 13))
    vec.extend(mfcc.get("stds", [0.0] * 13))
    # Chroma (12)
    vec.extend(chroma[:12] + [0.0] * max(0, 12 - len(chroma)))
    # Spectral contrast (7)
    vec.extend(contrast[:7] + [0.0] * max(0, 7 - len(contrast)))
    # Duration (2)
    vec.append(features.get("duration", 0.0))
    vec.append(np.log1p(features.get("duration", 0.0)))
    # Sample rate normalized (1)
    vec.append(features.get("sample_rate", 44100) / 44100.0)

    return [float(v) for v in vec]


def catalog_directory(directory: Path, output: Path) -> dict:
    """Catalog all MP3 files in a directory.

    Extracts rich audio features, acoustic categories, and bridge tags
    for each file. Stores feature vectors for ML training.

    Args:
        directory: Directory containing MP3 files
        output: Output JSON manifest path

    Returns:
        Dictionary with count and manifest path
    """
    from .content_classifier import (
        classify_sound, classify_bridge_tags, classify_bridge_tags_ml, load_trained_model,
    )
    from .metadata_generator import generate_metadata

    directory = Path(directory)
    output = Path(output)

    # Ensure output directory exists
    output.parent.mkdir(parents=True, exist_ok=True)

    # Try loading trained ML model for bridge tags
    model_path = Path(__file__).parent.parent / "data" / "bridge_classifier.joblib"
    use_ml = model_path.exists() and load_trained_model(model_path)

    # Handle missing directory
    if not directory.exists():
        print(f"[WARN] Directory {directory} does not exist, creating empty catalog", file=sys.stderr)
        manifest = {"items": [], "count": 0}
        with open(output, "w") as f:
            json.dump(manifest, f, indent=2)
        return {"count": 0, "manifest": str(output)}

    # Scan for MP3 files
    mp3_files = list(directory.rglob("*.mp3"))
    items = []

    for i, mp3_path in enumerate(mp3_files, 1):
        print(f"[{i}/{len(mp3_files)}] Analyzing {mp3_path.name}", file=sys.stderr)

        # Analyze audio (rich features)
        features = analyze_audio_file(mp3_path)
        if features is None:
            continue

        # Acoustic categories
        categories = classify_sound(features)

        # Feature vector for ML training + inference
        feature_vec = extract_feature_vector(features)

        # Bridge tags: prefer ML model, fall back to heuristic
        ml_scores = {}
        if use_ml:
            ml_scores = classify_bridge_tags_ml(feature_vec)
        if ml_scores:
            bridge_scores = ml_scores
        else:
            bridge_scores = classify_bridge_tags(features)
        bridge_tags = [tag for tag, score in bridge_scores.items() if score >= 0.5]

        # Generate metadata
        metadata = generate_metadata(features, categories, mp3_path.name)

        # Combine into item
        item = {
            "_key": mp3_path.stem.replace(" ", "_").replace("-", "_"),
            "filename": mp3_path.name,
            "filepath": str(mp3_path),
            "categories": categories,
            "bridge_tags": bridge_tags,
            "bridge_scores": {k: round(v, 3) for k, v in bridge_scores.items()},
            "bridge_method": "ml" if use_ml and ml_scores else "heuristic",
            "feature_vector": feature_vec,
            **features,
            **metadata,
        }

        items.append(item)

    # Write manifest
    manifest = {"items": items, "count": len(items)}
    with open(output, "w") as f:
        json.dump(manifest, f, indent=2)

    # Summary stats
    tag_counts = {}
    for item in items:
        for tag in item.get("bridge_tags", []):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    cat_counts = {}
    for item in items:
        for cat in item.get("categories", []):
            cat_counts[cat] = cat_counts.get(cat, 0) + 1

    print(f"[INFO] Cataloged {len(items)} files to {output}", file=sys.stderr)
    print(f"[INFO] Categories: {cat_counts}", file=sys.stderr)
    print(f"[INFO] Bridge tags: {tag_counts}", file=sys.stderr)
    return {"count": len(items), "manifest": str(output)}
