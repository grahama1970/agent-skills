#!/usr/bin/env python3
"""
Sanity script for madmom beat/tempo detection.

PURPOSE: Verify madmom API works for beat tracking, tempo estimation
DOCUMENTATION: https://madmom.readthedocs.io/
LAST VERIFIED: 2026-01-30

Exit codes:
  0 = PASS
  1 = FAIL
  42 = CLARIFY (needs human)

NOTE: madmom uses neural networks and may be slower than librosa.
      First run downloads model weights.
"""
import sys
from pathlib import Path

# Ensure fixtures exist
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
TEST_AUDIO = FIXTURES_DIR / "test_audio.wav"


def check_dependencies():
    """Check if madmom is installed."""
    try:
        import madmom
        print(f"madmom version: {madmom.__version__}")
        return True
    except ImportError as e:
        print(f"FAIL: madmom not installed: {e}")
        print("Fix: pip install madmom")
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


def test_beat_tracking():
    """Test RNN-based beat tracking."""
    from madmom.features.beats import RNNBeatProcessor, BeatTrackingProcessor

    print("Loading RNN beat processor (may download models on first run)...")
    proc = RNNBeatProcessor()

    print(f"Processing: {TEST_AUDIO}")
    activations = proc(str(TEST_AUDIO))
    print(f"Activations shape: {activations.shape}")

    # Decode beats from activations
    beat_proc = BeatTrackingProcessor(fps=100)
    beats = beat_proc(activations)
    print(f"Detected {len(beats)} beats")

    # Verify beats are reasonable
    assert len(beats) > 0, "No beats detected"

    # Show first few beat times
    print(f"First 5 beat times: {beats[:5]}")

    return beats


def test_tempo_estimation():
    """Test tempo estimation."""
    from madmom.features.tempo import TempoEstimationProcessor
    from madmom.features.beats import RNNBeatProcessor

    proc = RNNBeatProcessor()
    activations = proc(str(TEST_AUDIO))

    tempo_proc = TempoEstimationProcessor(fps=100)
    tempos = tempo_proc(activations)
    print(f"Tempo estimates: {tempos}")

    # tempos is array of (tempo, strength) tuples
    if len(tempos) > 0:
        primary_tempo = tempos[0][0]
        strength = tempos[0][1]
        print(f"Primary tempo: {primary_tempo:.1f} BPM (strength: {strength:.2f})")

        # Our test audio is 120 BPM
        assert 80 < primary_tempo < 160, f"Tempo {primary_tempo} outside expected range"
        return primary_tempo

    return None


def test_downbeat_tracking():
    """Test downbeat (measure boundary) detection."""
    from madmom.features.downbeats import RNNDownBeatProcessor, DBNDownBeatTrackingProcessor

    print("Loading downbeat processor...")
    proc = RNNDownBeatProcessor()

    activations = proc(str(TEST_AUDIO))
    print(f"Downbeat activations shape: {activations.shape}")

    # Decode downbeats
    downbeat_proc = DBNDownBeatTrackingProcessor(beats_per_bar=[4, 3], fps=100)
    downbeats = downbeat_proc(activations)
    print(f"Detected {len(downbeats)} downbeats")

    # downbeats is array of (time, beat_position) tuples
    # beat_position 1 = downbeat (start of measure)
    if len(downbeats) > 0:
        measure_starts = [d for d in downbeats if d[1] == 1]
        print(f"Measure starts: {len(measure_starts)}")
        print(f"First 3 downbeats: {downbeats[:3]}")

    return downbeats


def main():
    print("=== madmom Sanity Check ===\n")

    if not check_dependencies():
        return 1

    if not ensure_test_audio():
        return 1

    try:
        print("1. Beat Tracking")
        print("-" * 40)
        beats = test_beat_tracking()
        print()

        print("2. Tempo Estimation")
        print("-" * 40)
        tempo = test_tempo_estimation()
        print()

        print("3. Downbeat Tracking")
        print("-" * 40)
        downbeats = test_downbeat_tracking()
        print()

        print("=" * 40)
        print("PASS: All madmom features extracted successfully")
        print(f"  - Beats: {len(beats)} detected")
        print(f"  - Tempo: {tempo:.0f} BPM" if tempo else "  - Tempo: N/A")
        print(f"  - Downbeats: {len(downbeats)} detected")
        return 0

    except Exception as e:
        print(f"\nFAIL: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
