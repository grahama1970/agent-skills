"""
Tests for audio feature extraction.

Task 3: Rhythm Feature Extraction (librosa)
Task 4: Harmony Feature Extraction (librosa)
Task 5: Timbre Feature Extraction (librosa)
Task 6: Dynamics Feature Extraction (librosa)
Task 7: Lyrics Transcription (Whisper)
Task 8: Feature Aggregator
"""
import numpy as np
import pytest
from pathlib import Path

from src.audio_loader import load_audio
from src.features.rhythm import extract_rhythm_features, detect_downbeats


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
TEST_AUDIO = FIXTURES_DIR / "test_audio.wav"


class TestRhythmFeatures:
    """Task 3: Rhythm Feature Extraction (librosa)"""

    @pytest.fixture
    def audio_data(self):
        """Load test audio."""
        y, sr = load_audio(TEST_AUDIO)
        return y, sr

    def test_extract_rhythm_features(self, audio_data):
        """Returns bpm (float), beat_positions (list), tempo_variance (float), time_signature (str)."""
        y, sr = audio_data
        features = extract_rhythm_features(y, sr)

        # Check required fields
        assert "bpm" in features
        assert "beat_positions" in features
        assert "tempo_variance" in features
        assert "time_signature" in features

        # Check types
        assert isinstance(features["bpm"], float)
        assert isinstance(features["beat_positions"], list)
        assert isinstance(features["tempo_variance"], float)
        assert isinstance(features["time_signature"], str)

        # Check values are reasonable
        assert 40 < features["bpm"] < 200  # Reasonable BPM range
        assert len(features["beat_positions"]) > 0
        assert features["tempo_variance"] >= 0
        assert features["time_signature"] in ["2/4", "3/4", "4/4", "6/8"]

    def test_extract_rhythm_bpm_accuracy(self, audio_data):
        """Detects 120 BPM from test audio (generated at 120 BPM)."""
        y, sr = audio_data
        features = extract_rhythm_features(y, sr)

        # Test audio was generated at 120 BPM
        assert 100 < features["bpm"] < 140  # Allow some tolerance

    def test_detect_downbeats(self, audio_data):
        """Detects measure boundaries (downbeats)."""
        y, sr = audio_data
        features = extract_rhythm_features(y, sr)
        beat_frames = np.array([
            int(t * sr / 512) for t in features["beat_positions"]
        ])

        downbeats = detect_downbeats(y, sr, beat_frames, beats_per_bar=4)

        assert isinstance(downbeats, list)
        # Should have fewer downbeats than beats
        assert len(downbeats) <= len(features["beat_positions"])


class TestHarmonyFeatures:
    """Task 4: Harmony Feature Extraction (librosa)"""

    @pytest.fixture
    def audio_data(self):
        """Load test audio."""
        y, sr = load_audio(TEST_AUDIO)
        return y, sr

    def test_extract_harmony_features(self, audio_data):
        """Returns key (str), mode (str), scale (str)."""
        from src.features.harmony import extract_harmony_features

        y, sr = audio_data
        features = extract_harmony_features(y, sr)

        # Check required fields
        assert "key" in features
        assert "mode" in features
        assert "scale" in features
        assert "key_confidence" in features

        # Check types
        assert isinstance(features["key"], str)
        assert isinstance(features["mode"], str)
        assert isinstance(features["scale"], str)
        assert isinstance(features["key_confidence"], float)

        # Check values are valid
        assert features["key"] in ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        assert features["mode"] in ["major", "minor"]
        assert 0 <= features["key_confidence"] <= 1

    def test_key_confidence(self, audio_data):
        """Returns key detection confidence score."""
        from src.features.harmony import extract_harmony_features

        y, sr = audio_data
        features = extract_harmony_features(y, sr)

        # Test audio is in C major, should have reasonable confidence
        assert features["key_confidence"] > 0.3


class TestTimbreFeatures:
    """Task 5: Timbre Feature Extraction (librosa)"""

    @pytest.fixture
    def audio_data(self):
        """Load test audio."""
        y, sr = load_audio(TEST_AUDIO)
        return y, sr

    def test_extract_timbre_features(self, audio_data):
        """Returns spectral_centroid, spectral_bandwidth, mfcc_mean, zero_crossing_rate."""
        from src.features.timbre import extract_timbre_features

        y, sr = audio_data
        features = extract_timbre_features(y, sr)

        # Check required fields
        assert "spectral_centroid" in features
        assert "spectral_bandwidth" in features
        assert "mfcc_mean" in features
        assert "zero_crossing_rate" in features
        assert "brightness" in features
        assert "texture" in features

        # Check types
        assert isinstance(features["spectral_centroid"], float)
        assert isinstance(features["spectral_bandwidth"], float)
        assert isinstance(features["mfcc_mean"], list)
        assert isinstance(features["zero_crossing_rate"], float)

    def test_mfcc_extraction(self, audio_data):
        """Extracts 13 MFCC coefficients."""
        from src.features.timbre import extract_timbre_features

        y, sr = audio_data
        features = extract_timbre_features(y, sr, n_mfcc=13)

        assert len(features["mfcc_mean"]) == 13


class TestDynamicsFeatures:
    """Task 6: Dynamics Feature Extraction (librosa)"""

    @pytest.fixture
    def audio_data(self):
        """Load test audio."""
        y, sr = load_audio(TEST_AUDIO)
        return y, sr

    def test_extract_dynamics_features(self, audio_data):
        """Returns loudness_integrated (LUFS), dynamic_range, loudness_range."""
        from src.features.dynamics import extract_dynamics_features

        y, sr = audio_data
        features = extract_dynamics_features(y, sr)

        # Check required fields
        assert "loudness_integrated" in features
        assert "dynamic_range" in features
        assert "loudness_range" in features
        assert "peak_db" in features
        assert "rms_db" in features

        # Check types
        assert isinstance(features["loudness_integrated"], float)
        assert isinstance(features["dynamic_range"], float)
        assert isinstance(features["loudness_range"], float)

        # Check values are reasonable (dB values should be negative)
        assert features["peak_db"] < 0
        assert features["rms_db"] < 0
        assert features["dynamic_range"] >= 0

    def test_loudness_estimate(self, audio_data):
        """Estimates loudness in LUFS-like scale."""
        from src.features.dynamics import extract_dynamics_features

        y, sr = audio_data
        features = extract_dynamics_features(y, sr)

        # LUFS typically -60 to 0
        assert -60 < features["loudness_integrated"] < 0


class TestLyricsTranscription:
    """Task 7: Lyrics Transcription (Whisper)"""

    def test_transcribe_lyrics(self):
        """Returns lyrics text, language, word_timestamps."""
        from src.features.lyrics import extract_lyrics

        # Use test audio file
        result = extract_lyrics(TEST_AUDIO, language="en")

        # Check required fields
        assert "text" in result
        assert "language" in result
        assert "word_timestamps" in result
        assert "is_instrumental" in result

        # Check types
        assert isinstance(result["text"], str)
        assert isinstance(result["language"], str)
        assert isinstance(result["word_timestamps"], list)
        assert isinstance(result["is_instrumental"], bool)

    def test_instrumental_detection(self):
        """Detects instrumental tracks (no lyrics)."""
        from src.features.lyrics import extract_lyrics

        # Test audio is instrumental (synthesized)
        result = extract_lyrics(TEST_AUDIO, language="en")

        # Should detect as instrumental (no real speech)
        assert result["is_instrumental"] is True


class TestFeatureAggregator:
    """Task 8: Feature Aggregator"""

    def test_extract_all_features(self):
        """Returns complete feature dict with rhythm, harmony, timbre, dynamics, lyrics sections."""
        from src.features.aggregator import extract_all_features

        features = extract_all_features(TEST_AUDIO)

        # Check all sections present
        assert "metadata" in features
        assert "rhythm" in features
        assert "harmony" in features
        assert "timbre" in features
        assert "dynamics" in features
        assert "lyrics" in features

        # Check rhythm section
        assert "bpm" in features["rhythm"]
        assert "beat_positions" in features["rhythm"]

        # Check harmony section
        assert "key" in features["harmony"]
        assert "mode" in features["harmony"]

        # Check timbre section
        assert "spectral_centroid" in features["timbre"]
        assert "mfcc_mean" in features["timbre"]

        # Check dynamics section
        assert "loudness_integrated" in features["dynamics"]
        assert "dynamic_range" in features["dynamics"]

    def test_feature_dict_structure(self):
        """Validates feature dictionary has all required sections."""
        from src.features.aggregator import extract_all_features, validate_features

        features = extract_all_features(TEST_AUDIO)
        validation = validate_features(features)

        assert validation["is_valid"] is True
        assert len(validation["missing_fields"]) == 0
        assert "summary" in validation
