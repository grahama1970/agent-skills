"""Audio analysis utilities for SFX cataloging."""

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
        
        # Frequency profile
        spectral_centroids = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
        centroid = float(np.mean(spectral_centroids))
        
        # Dominant frequency (via zero crossing rate as proxy)
        zcr = librosa.feature.zero_crossing_rate(y)[0]
        dominant_freq = float(np.mean(zcr) * sr / 2)
        
        # Envelope analysis
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        
        # Determine envelope type based on attack time
        onset_frames = librosa.onset.onset_detect(y=y, sr=sr)
        if len(onset_frames) > 0:
            attack_ms = float((onset_frames[0] / sr) * 1000)
            if attack_ms < 50:
                envelope_type = "impact"
            elif attack_ms < 200:
                envelope_type = "percussive"
            else:
                envelope_type = "sustained"
        else:
            envelope_type = "sustained"
        
        # Loudness
        rms = librosa.feature.rms(y=y)[0]
        peak_db = float(librosa.amplitude_to_db(np.abs(y).max(), ref=1.0))
        rms_db = float(librosa.amplitude_to_db(np.mean(rms), ref=1.0))
        
        return {
            "duration": float(duration),
            "sample_rate": int(sr),
            "channels": 1,  # We loaded as mono
            "frequency_profile": {
                "dominant_freq": dominant_freq,
                "spectral_centroid": centroid
            },
            "envelope": {
                "type": envelope_type,
                "attack_ms": attack_ms if len(onset_frames) > 0 else 0.0
            },
            "loudness": {
                "peak_db": peak_db,
                "rms_db": rms_db
            }
        }
    
    except Exception as e:
        print(f"[WARN] Failed to analyze {path}: {e}", file=sys.stderr)
        return None


def catalog_directory(directory: Path, output: Path) -> dict:
    """Catalog all MP3 files in a directory.
    
    Args:
        directory: Directory containing MP3 files
        output: Output JSON manifest path
        
    Returns:
        Dictionary with count and manifest path
    """
    from .content_classifier import classify_sound
    from .metadata_generator import generate_metadata
    
    directory = Path(directory)
    output = Path(output)
    
    # Ensure output directory exists
    output.parent.mkdir(parents=True, exist_ok=True)
    
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
        
        # Analyze audio
        features = analyze_audio_file(mp3_path)
        if features is None:
            continue
        
        # Classify
        categories = classify_sound(features)
        
        # Generate metadata
        metadata = generate_metadata(features, categories, mp3_path.name)
        
        # Combine into item
        item = {
            "_key": mp3_path.stem.replace(" ", "_").replace("-", "_"),
            "filename": mp3_path.name,
            "filepath": str(mp3_path),
            "categories": categories,
            **features,
            **metadata
        }
        
        items.append(item)
    
    # Write manifest
    manifest = {"items": items, "count": len(items)}
    with open(output, "w") as f:
        json.dump(manifest, f, indent=2)
    
    print(f"[INFO] Cataloged {len(items)} files to {output}", file=sys.stderr)
    return {"count": len(items), "manifest": str(output)}
