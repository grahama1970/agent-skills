#!/usr/bin/env python3
"""
Sanity script for essentia key/loudness extraction.

PURPOSE: Verify essentia API works for key detection, loudness (LUFS), dynamics
DOCUMENTATION: https://essentia.upf.edu/documentation/
LAST VERIFIED: 2026-01-30

Exit codes:
  0 = PASS
  1 = FAIL
  42 = CLARIFY (needs human)

NOTE: essentia has two APIs:
  - essentia.standard (simple, synchronous)
  - essentia.streaming (for real-time processing)
We use essentia.standard here.
"""
import sys
from pathlib import Path

# Ensure fixtures exist
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
TEST_AUDIO = FIXTURES_DIR / "test_audio.wav"


def check_dependencies():
    """Check if essentia is installed."""
    try:
        import essentia
        print(f"essentia version: {essentia.__version__}")
        return True
    except ImportError as e:
        print(f"FAIL: essentia not installed: {e}")
        print("Fix: pip install essentia")
        print("     or: pip install essentia-tensorflow (for ML models)")
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


def load_audio():
    """Load audio using essentia."""
    import essentia.standard as es

    loader = es.MonoLoader(filename=str(TEST_AUDIO))
    audio = loader()
    print(f"Loaded audio: {len(audio)} samples ({len(audio)/44100:.2f}s at 44100 Hz)")

    return audio


def test_key_extraction(audio):
    """Test key and scale detection."""
    import essentia.standard as es

    # KeyExtractor is a high-level algorithm that estimates key
    key_extractor = es.KeyExtractor()
    key, scale, strength = key_extractor(audio)

    print(f"Detected key: {key} {scale}")
    print(f"Key strength: {strength:.3f}")

    # Validate output
    valid_keys = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    valid_scales = ['major', 'minor']

    assert key in valid_keys, f"Invalid key: {key}"
    assert scale in valid_scales, f"Invalid scale: {scale}"
    assert 0 <= strength <= 1, f"Invalid strength: {strength}"

    return key, scale, strength


def test_loudness(audio):
    """Test loudness measurement (EBU R128 / LUFS)."""
    import essentia.standard as es

    # LoudnessEBUR128 measures integrated loudness per EBU R128
    loudness = es.LoudnessEBUR128(sampleRate=44100)

    # Returns: momentaryLoudness, shortTermLoudness, integratedLoudness, loudnessRange
    momentary, short_term, integrated, loudness_range = loudness(audio)

    print(f"Integrated loudness: {integrated:.1f} LUFS")
    print(f"Loudness range: {loudness_range:.1f} LU")
    print(f"Momentary loudness samples: {len(momentary)}")

    # Typical values: -24 to 0 LUFS for music
    assert -60 < integrated < 0, f"Unusual integrated loudness: {integrated}"

    return {
        "integrated": integrated,
        "range": loudness_range,
        "momentary": momentary,
        "short_term": short_term,
    }


def test_dynamics(audio):
    """Test dynamic range analysis."""
    import essentia.standard as es
    import numpy as np

    # DynamicComplexity measures how dynamic the audio is
    dynamic_complexity = es.DynamicComplexity()
    complexity, loudness = dynamic_complexity(audio)

    print(f"Dynamic complexity: {complexity:.3f}")
    print(f"Average loudness: {loudness:.1f} dB")

    # RMS energy
    rms = es.RMS()
    rms_value = rms(audio)
    print(f"RMS: {rms_value:.4f}")

    # Peak amplitude
    peak = np.max(np.abs(audio))
    print(f"Peak amplitude: {peak:.4f}")

    # Crest factor (peak to RMS ratio)
    crest_factor = peak / rms_value if rms_value > 0 else 0
    print(f"Crest factor: {crest_factor:.2f}")

    return {
        "dynamic_complexity": complexity,
        "rms": rms_value,
        "peak": peak,
        "crest_factor": crest_factor,
    }


def test_rhythm_features(audio):
    """Test rhythm-related features."""
    import essentia.standard as es

    # BPM histogram
    rhythm_extractor = es.RhythmExtractor2013()
    bpm, beats, confidence, _, histogram = rhythm_extractor(audio)

    print(f"BPM: {bpm:.1f} (confidence: {confidence:.2f})")
    print(f"Beats detected: {len(beats)}")

    # Danceability
    danceability = es.Danceability()
    dance_value, _ = danceability(audio)
    print(f"Danceability: {dance_value:.3f}")

    return {
        "bpm": bpm,
        "beats": beats,
        "confidence": confidence,
        "danceability": dance_value,
    }


def main():
    print("=== essentia Sanity Check ===\n")

    if not check_dependencies():
        return 1

    if not ensure_test_audio():
        return 1

    try:
        audio = load_audio()
        print()

        print("1. Key Extraction")
        print("-" * 40)
        key, scale, strength = test_key_extraction(audio)
        print()

        print("2. Loudness (EBU R128)")
        print("-" * 40)
        loudness = test_loudness(audio)
        print()

        print("3. Dynamics")
        print("-" * 40)
        dynamics = test_dynamics(audio)
        print()

        print("4. Rhythm Features")
        print("-" * 40)
        rhythm = test_rhythm_features(audio)
        print()

        print("=" * 40)
        print("PASS: All essentia features extracted successfully")
        print(f"  - Key: {key} {scale} (strength: {strength:.2f})")
        print(f"  - Loudness: {loudness['integrated']:.1f} LUFS")
        print(f"  - Dynamic range: {loudness['range']:.1f} LU")
        print(f"  - BPM: {rhythm['bpm']:.0f}")
        return 0

    except Exception as e:
        print(f"\nFAIL: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
