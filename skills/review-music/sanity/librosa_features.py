#!/usr/bin/env python3
"""
Sanity script for librosa audio feature extraction.

PURPOSE: Verify librosa API works for MFCC, spectral features, chroma
DOCUMENTATION: https://librosa.org/doc/latest/
LAST VERIFIED: 2026-01-30

Exit codes:
  0 = PASS
  1 = FAIL
  42 = CLARIFY (needs human)
"""
import sys
from pathlib import Path

# Ensure fixtures exist
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
TEST_AUDIO = FIXTURES_DIR / "test_audio.wav"


def check_dependencies():
    """Check if librosa is installed."""
    try:
        import librosa
        print(f"librosa version: {librosa.__version__}")
        return True
    except ImportError as e:
        print(f"FAIL: librosa not installed: {e}")
        print("Fix: pip install librosa")
        return False


def ensure_test_audio():
    """Generate test audio if it doesn't exist."""
    if not TEST_AUDIO.exists():
        print(f"Generating test audio: {TEST_AUDIO}")
        sys.path.insert(0, str(FIXTURES_DIR))
        from generate_test_audio import main as generate
        generate()

    if not TEST_AUDIO.exists():
        print(f"FAIL: Could not create test audio at {TEST_AUDIO}")
        return False
    return True


def test_load_audio():
    """Test loading audio file."""
    import librosa

    y, sr = librosa.load(str(TEST_AUDIO), sr=None)
    print(f"Loaded audio: {len(y)} samples at {sr} Hz ({len(y)/sr:.2f}s)")

    assert len(y) > 0, "No audio samples loaded"
    assert sr > 0, "Invalid sample rate"
    return y, sr


def test_mfcc(y, sr):
    """Test MFCC extraction."""
    import librosa
    import numpy as np

    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    print(f"MFCC shape: {mfcc.shape} (13 coefficients x {mfcc.shape[1]} frames)")

    assert mfcc.shape[0] == 13, f"Expected 13 MFCCs, got {mfcc.shape[0]}"
    assert not np.isnan(mfcc).any(), "MFCC contains NaN values"

    # Return mean MFCC for feature vector
    mfcc_mean = np.mean(mfcc, axis=1)
    print(f"MFCC mean: {mfcc_mean[:3]}... (first 3)")
    return mfcc_mean


def test_spectral_features(y, sr):
    """Test spectral feature extraction."""
    import librosa
    import numpy as np

    # Spectral centroid (brightness)
    spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
    centroid_mean = np.mean(spectral_centroid)
    print(f"Spectral centroid mean: {centroid_mean:.2f} Hz")

    # Spectral bandwidth
    spectral_bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr)
    bandwidth_mean = np.mean(spectral_bandwidth)
    print(f"Spectral bandwidth mean: {bandwidth_mean:.2f} Hz")

    # Spectral rolloff
    spectral_rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)
    rolloff_mean = np.mean(spectral_rolloff)
    print(f"Spectral rolloff mean: {rolloff_mean:.2f} Hz")

    # Zero crossing rate
    zcr = librosa.feature.zero_crossing_rate(y)
    zcr_mean = np.mean(zcr)
    print(f"Zero crossing rate mean: {zcr_mean:.4f}")

    return {
        "spectral_centroid": centroid_mean,
        "spectral_bandwidth": bandwidth_mean,
        "spectral_rolloff": rolloff_mean,
        "zero_crossing_rate": zcr_mean,
    }


def test_chroma(y, sr):
    """Test chromagram extraction."""
    import librosa
    import numpy as np

    chroma = librosa.feature.chroma_stft(y=y, sr=sr)
    print(f"Chroma shape: {chroma.shape} (12 pitches x {chroma.shape[1]} frames)")

    assert chroma.shape[0] == 12, f"Expected 12 chroma bins, got {chroma.shape[0]}"

    # Find dominant pitch class
    chroma_mean = np.mean(chroma, axis=1)
    pitch_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    dominant_pitch = pitch_names[np.argmax(chroma_mean)]
    print(f"Dominant pitch class: {dominant_pitch}")

    return chroma_mean, dominant_pitch


def test_tempo(y, sr):
    """Test tempo estimation."""
    import librosa

    tempo, beats = librosa.beat.beat_track(y=y, sr=sr)

    # Handle newer librosa returning array
    if hasattr(tempo, '__len__'):
        tempo = float(tempo[0]) if len(tempo) > 0 else 0.0

    print(f"Estimated tempo: {tempo:.1f} BPM")
    print(f"Beat frames: {len(beats)} beats detected")

    # Our test audio is 120 BPM, allow some tolerance
    assert 80 < tempo < 160, f"Tempo {tempo} outside expected range (80-160)"

    return tempo, beats


def main():
    print("=== librosa Sanity Check ===\n")

    if not check_dependencies():
        return 1

    if not ensure_test_audio():
        return 1

    try:
        y, sr = test_load_audio()
        print()

        mfcc_mean = test_mfcc(y, sr)
        print()

        spectral = test_spectral_features(y, sr)
        print()

        chroma, pitch = test_chroma(y, sr)
        print()

        tempo, beats = test_tempo(y, sr)
        print()

        print("=" * 40)
        print("PASS: All librosa features extracted successfully")
        print(f"  - MFCC: 13 coefficients")
        print(f"  - Spectral centroid: {spectral['spectral_centroid']:.0f} Hz")
        print(f"  - Dominant pitch: {pitch}")
        print(f"  - Tempo: {tempo:.0f} BPM")
        return 0

    except Exception as e:
        print(f"\nFAIL: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
