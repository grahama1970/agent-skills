"""
Tests for review generation and memory sync.

Task 11: Review Generator
Task 12: Memory Sync Integration
"""
import json
import pytest
from pathlib import Path

from src.review.generator import (
    generate_review,
    generate_review_from_features,
    ReviewResult,
    save_review,
    load_review,
)


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
TEST_AUDIO = FIXTURES_DIR / "test_audio.wav"


# Mock features for testing without audio file
MOCK_FEATURES = {
    "metadata": {
        "file_path": "/test/audio.wav",
        "duration_seconds": 180.5,
        "sample_rate": 44100,
    },
    "rhythm": {
        "bpm": 120.0,
        "beat_positions": [0.5, 1.0, 1.5],
        "tempo_variance": 0.05,
        "time_signature": "4/4",
        "beat_strength": 0.75,
    },
    "harmony": {
        "key": "C",
        "mode": "major",
        "scale": "C major",
        "key_confidence": 0.85,
        "harmonic_complexity": 0.6,
    },
    "timbre": {
        "brightness": "bright",
        "texture": "dense",
        "spectral_centroid": 2500.0,
        "spectral_flatness": 0.15,
        "mfcc_mean": [0.1] * 13,
    },
    "dynamics": {
        "loudness_integrated": -14.5,
        "dynamic_range": 15.0,
        "loudness_range": 8.5,
    },
    "lyrics": {
        "is_instrumental": True,
        "text": "",
        "language": "en",
        "word_timestamps": [],
    },
}


class TestReviewResult:
    """Tests for ReviewResult dataclass."""

    def test_review_result_to_dict(self):
        """Converts to dictionary."""
        result = ReviewResult(
            title="Test Track",
            artist="Test Artist",
            bridge_attributes=["Resilience"],
        )
        d = result.to_dict()
        assert d["title"] == "Test Track"
        assert d["artist"] == "Test Artist"
        assert d["bridge_attributes"] == ["Resilience"]

    def test_review_result_to_json(self):
        """Converts to JSON string."""
        result = ReviewResult(
            title="Test Track",
            confidence=0.85,
        )
        json_str = result.to_json()
        parsed = json.loads(json_str)
        assert parsed["title"] == "Test Track"
        assert parsed["confidence"] == 0.85

    def test_review_result_to_memory_format(self):
        """Converts to memory-compatible format."""
        result = ReviewResult(
            title="Test Track",
            artist="Test Artist",
            source="/path/to/audio.wav",
            bridge_attributes=["Resilience", "Precision"],
            collection_tags={"domain": ["Epic_Orchestral"], "function": "Battle"},
            tactical_tags=["Score", "Amplify"],
            episodic_associations=["Siege_of_Terra"],
            summary="An epic orchestral piece.",
            emotional_arc={"primary_mood": "triumphant", "intensity": "high"},
            features=MOCK_FEATURES,
        )
        mem = result.to_memory_format()

        assert mem["category"] == "music"
        assert mem["title"] == "Test Track"
        assert mem["artist"] == "Test Artist"
        assert mem["bridge_attributes"] == ["Resilience", "Precision"]
        assert mem["tactical_tags"] == ["Score", "Amplify"]
        assert mem["episodic_associations"] == ["Siege_of_Terra"]
        assert "content" in mem
        assert "metadata" in mem


class TestReviewGenerator:
    """Task 11: Review Generator"""

    def test_generate_review(self):
        """Returns complete review JSON matching SKILL.md output format."""
        # Use rule-based analysis (no LLM) for testing
        result = generate_review(
            TEST_AUDIO,
            title="Test Audio",
            use_llm=False,
        )

        # Check it's a ReviewResult
        assert isinstance(result, ReviewResult)

        # Check has required fields
        assert result.title == "Test Audio"
        assert result.source == str(TEST_AUDIO)
        assert result.generated_at != ""
        assert result.version == "1.0.0"

    def test_generate_review_from_features(self):
        """Generates review from pre-extracted features."""
        result = generate_review_from_features(
            MOCK_FEATURES,
            title="Mock Track",
            artist="Mock Artist",
            use_llm=False,
        )

        assert result.title == "Mock Track"
        assert result.artist == "Mock Artist"
        assert len(result.bridge_attributes) > 0

    def test_review_has_metadata(self):
        """Review includes metadata (artist, title, duration, file_path)."""
        result = generate_review_from_features(
            MOCK_FEATURES,
            title="Test Track",
            artist="Test Artist",
            source="/test/path.wav",
            use_llm=False,
        )

        assert result.title == "Test Track"
        assert result.artist == "Test Artist"
        assert result.source == "/test/path.wav"
        assert result.features["metadata"]["duration_seconds"] == 180.5

    def test_review_has_features(self):
        """Review includes features (rhythm, harmony, timbre, dynamics, lyrics)."""
        result = generate_review_from_features(
            MOCK_FEATURES,
            title="Test",
            use_llm=False,
        )

        assert "rhythm" in result.features
        assert "harmony" in result.features
        assert "timbre" in result.features
        assert "dynamics" in result.features
        assert "lyrics" in result.features

        # Check specific feature values
        assert result.features["rhythm"]["bpm"] == 120.0
        assert result.features["harmony"]["scale"] == "C major"

    def test_review_has_hmt_taxonomy(self):
        """Review includes hmt_taxonomy (bridge_attributes, collection_tags, tactical_tags)."""
        result = generate_review_from_features(
            MOCK_FEATURES,
            title="Test",
            use_llm=False,
        )

        # Should have bridge attributes
        assert isinstance(result.bridge_attributes, list)
        assert len(result.bridge_attributes) > 0

        # Should have collection tags with required fields
        assert isinstance(result.collection_tags, dict)
        assert "domain" in result.collection_tags
        assert "thematic_weight" in result.collection_tags
        assert "function" in result.collection_tags

        # Should have tactical tags
        assert isinstance(result.tactical_tags, list)
        assert len(result.tactical_tags) > 0

    def test_review_has_analysis(self):
        """Review includes LLM/rule-based analysis."""
        result = generate_review_from_features(
            MOCK_FEATURES,
            title="Test",
            use_llm=False,
        )

        assert result.summary != ""
        assert isinstance(result.music_theory, dict)
        assert isinstance(result.emotional_arc, dict)
        assert isinstance(result.use_cases, list)

    def test_review_has_confidence(self):
        """Review includes confidence score."""
        result = generate_review_from_features(
            MOCK_FEATURES,
            title="Test",
            use_llm=False,
        )

        assert isinstance(result.confidence, float)
        assert 0 <= result.confidence <= 1.0

    def test_review_analysis_method_tracked(self):
        """Review tracks whether LLM or rule-based analysis was used."""
        result = generate_review_from_features(
            MOCK_FEATURES,
            title="Test",
            use_llm=False,
        )

        assert result.analysis_method == "rule_based"


class TestSaveLoadReview:
    """Tests for saving and loading reviews."""

    def test_save_review(self, tmp_path):
        """Saves review to JSON file."""
        result = ReviewResult(
            title="Test Track",
            bridge_attributes=["Resilience"],
            confidence=0.85,
        )

        output_path = tmp_path / "review.json"
        saved_path = save_review(result, output_path)

        assert saved_path.exists()
        with open(saved_path) as f:
            data = json.load(f)
        assert data["title"] == "Test Track"

    def test_load_review(self, tmp_path):
        """Loads review from JSON file."""
        # Save first
        result = ReviewResult(
            title="Test Track",
            artist="Test Artist",
            bridge_attributes=["Precision", "Corruption"],
            confidence=0.75,
        )
        output_path = tmp_path / "review.json"
        save_review(result, output_path)

        # Load and verify
        loaded = load_review(output_path)
        assert loaded.title == "Test Track"
        assert loaded.artist == "Test Artist"
        assert loaded.bridge_attributes == ["Precision", "Corruption"]
        assert loaded.confidence == 0.75


class TestMemorySync:
    """Task 12: Memory Sync Integration"""

    def test_sync_to_memory(self):
        """Creates memory entry with category='music', bridge_attributes, collection_tags."""
        result = generate_review_from_features(
            MOCK_FEATURES,
            title="Test Track",
            use_llm=False,
        )

        mem_format = result.to_memory_format()

        # Check required memory fields
        assert mem_format["category"] == "music"
        assert "bridge_attributes" in mem_format
        assert "collection_tags" in mem_format
        assert len(mem_format["bridge_attributes"]) > 0

    def test_memory_entry_structure(self):
        """Memory entry has correct fields for /memory recall."""
        result = ReviewResult(
            title="Epic Battle Theme",
            artist="Composer Name",
            source="/path/to/epic.mp3",
            bridge_attributes=["Resilience", "Loyalty"],
            collection_tags={
                "domain": ["Epic_Orchestral", "Power_Metal"],
                "thematic_weight": "Epic",
                "function": "Battle",
            },
            tactical_tags=["Score", "Amplify", "Endure"],
            episodic_associations=["Siege_of_Terra", "Imperial_Palace_Defense"],
            summary="A triumphant orchestral piece.",
            emotional_arc={"primary_mood": "triumphant", "intensity": "high"},
            features=MOCK_FEATURES,
            confidence=0.9,
        )

        mem = result.to_memory_format()

        # Verify structure
        assert mem["category"] == "music"
        assert mem["title"] == "Epic Battle Theme"
        assert mem["artist"] == "Composer Name"
        assert "content" in mem
        assert len(mem["content"]) > 0

        # Verify metadata
        assert "metadata" in mem
        assert mem["metadata"]["source"] == "/path/to/epic.mp3"
        assert mem["metadata"]["bpm"] == 120.0
        assert mem["metadata"]["confidence"] == 0.9

    def test_episodic_association(self):
        """Memory entry includes episodic_associations for lore connection."""
        result = generate_review_from_features(
            MOCK_FEATURES,
            title="Test",
            use_llm=False,
        )

        mem = result.to_memory_format()

        # Should have episodic_associations field
        assert "episodic_associations" in mem
        assert isinstance(mem["episodic_associations"], list)

    def test_memory_content_includes_summary(self):
        """Memory content includes summary for search."""
        result = ReviewResult(
            title="Test Track",
            summary="A dark ambient piece with drone elements.",
            bridge_attributes=["Stealth"],
            emotional_arc={"primary_mood": "mysterious", "intensity": "low"},
            features=MOCK_FEATURES,
        )

        mem = result.to_memory_format()
        content = mem["content"]

        assert "dark ambient" in content
        assert "mysterious" in content.lower() or "Mood:" in content
