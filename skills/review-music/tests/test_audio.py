"""
Tests for audio loading module.

Task 2: Audio Loader Module
"""
import numpy as np
import pytest
from pathlib import Path

from src.audio_loader import (
    load_audio,
    load_from_file,
    is_youtube_url,
    get_audio_info,
    STANDARD_SR,
)


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
TEST_AUDIO = FIXTURES_DIR / "test_audio.wav"


class TestLoadAudio:
    """Tests for load_audio function."""

    def test_load_audio_file(self):
        """Loads mp3/wav/flac, returns numpy array with sample rate."""
        y, sr = load_audio(TEST_AUDIO)

        # Should return numpy array
        assert isinstance(y, np.ndarray)
        assert len(y) > 0

        # Should return standard sample rate by default
        assert sr == STANDARD_SR

        # Should be mono by default
        assert y.ndim == 1

    def test_load_audio_with_custom_sr(self):
        """Loads audio with custom sample rate."""
        y, sr = load_audio(TEST_AUDIO, sr=22050)

        assert sr == 22050
        assert isinstance(y, np.ndarray)

    def test_load_audio_with_duration(self):
        """Loads only first N seconds of audio."""
        # Load full file
        y_full, sr = load_audio(TEST_AUDIO)

        # Load first 2 seconds
        y_short, sr = load_audio(TEST_AUDIO, duration=2.0)

        # Short should be approximately 2 seconds
        expected_samples = int(2.0 * sr)
        assert len(y_short) <= expected_samples + sr  # Allow some tolerance

        # Short should be shorter than full
        assert len(y_short) < len(y_full)

    def test_load_nonexistent_file(self):
        """Raises FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            load_audio("/nonexistent/path/audio.wav")


class TestYouTubeDetection:
    """Tests for YouTube URL detection."""

    def test_youtube_watch_url(self):
        """Detects youtube.com/watch URLs."""
        assert is_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert is_youtube_url("http://youtube.com/watch?v=abc123")

    def test_youtu_be_url(self):
        """Detects youtu.be short URLs."""
        assert is_youtube_url("https://youtu.be/dQw4w9WgXcQ")

    def test_youtube_music_url(self):
        """Detects music.youtube.com URLs."""
        assert is_youtube_url("https://music.youtube.com/watch?v=abc123")

    def test_non_youtube_url(self):
        """Returns False for non-YouTube URLs."""
        assert not is_youtube_url("https://soundcloud.com/artist/track")
        assert not is_youtube_url("https://spotify.com/track/abc")
        assert not is_youtube_url("/path/to/file.mp3")


class TestAudioInfo:
    """Tests for get_audio_info function."""

    def test_get_file_info(self):
        """Gets info for local audio file."""
        info = get_audio_info(TEST_AUDIO)

        assert info["type"] == "file"
        assert info["duration"] > 0
        assert info["sample_rate"] > 0
        assert info["channels"] >= 1

    def test_get_youtube_info(self):
        """Gets placeholder info for YouTube URL."""
        info = get_audio_info("https://youtube.com/watch?v=abc123")

        assert info["type"] == "youtube"
        assert info["source"] == "https://youtube.com/watch?v=abc123"


@pytest.mark.skip(reason="Requires network access - run manually")
class TestYouTubeDownload:
    """Tests for YouTube download functionality."""

    def test_load_from_youtube_url(self):
        """Downloads and loads audio from YouTube URL."""
        from src.audio_loader import load_from_youtube

        # Use a short, reliable test video
        url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"  # "Me at the zoo" (18s)
        y, sr = load_from_youtube(url, duration=5.0)

        assert isinstance(y, np.ndarray)
        assert len(y) > 0
        assert sr == STANDARD_SR
