"""
Tests for LLM music analysis.

Task 9: LLM Music Theory Analyzer
"""
import pytest
from pathlib import Path

from src.analysis.llm_analyzer import (
    format_features_for_prompt,
    create_analysis_prompt,
    analyze_without_llm,
    _parse_json_response,
)


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


# Mock features for testing
MOCK_FEATURES = {
    "metadata": {
        "duration_seconds": 180.5,
        "sample_rate": 44100,
    },
    "rhythm": {
        "bpm": 120.0,
        "time_signature": "4/4",
        "tempo_variance": 0.05,
        "beat_strength": 0.75,
    },
    "harmony": {
        "key": "C",
        "mode": "major",
        "scale": "C major",
        "key_confidence": 0.85,
        "harmonic_complexity": 0.6,
        "chord_changes_per_minute": 8.5,
    },
    "timbre": {
        "brightness": "bright",
        "texture": "dense",
        "spectral_centroid": 2500.0,
        "spectral_flatness": 0.15,
    },
    "dynamics": {
        "loudness_integrated": -14.5,
        "dynamic_range": 12.0,
        "loudness_range": 8.5,
    },
    "lyrics": {
        "is_instrumental": True,
        "text": "",
        "language": "en",
    },
}


class TestFormatFeatures:
    """Tests for feature formatting."""

    def test_format_features_includes_duration(self):
        """Includes duration in formatted output."""
        result = format_features_for_prompt(MOCK_FEATURES)
        assert "180.5 seconds" in result

    def test_format_features_includes_rhythm(self):
        """Includes rhythm section."""
        result = format_features_for_prompt(MOCK_FEATURES)
        assert "## Rhythm" in result
        assert "BPM: 120.0" in result
        assert "Time Signature: 4/4" in result

    def test_format_features_includes_harmony(self):
        """Includes harmony section."""
        result = format_features_for_prompt(MOCK_FEATURES)
        assert "## Harmony" in result
        assert "Key/Scale: C major" in result

    def test_format_features_includes_timbre(self):
        """Includes timbre section."""
        result = format_features_for_prompt(MOCK_FEATURES)
        assert "## Timbre" in result
        assert "Brightness: bright" in result

    def test_format_features_includes_dynamics(self):
        """Includes dynamics section."""
        result = format_features_for_prompt(MOCK_FEATURES)
        assert "## Dynamics" in result
        assert "LUFS" in result

    def test_format_features_handles_instrumental(self):
        """Handles instrumental tracks."""
        result = format_features_for_prompt(MOCK_FEATURES)
        assert "Instrumental" in result

    def test_format_features_handles_vocals(self):
        """Handles vocal tracks with lyrics."""
        features = MOCK_FEATURES.copy()
        features["lyrics"] = {
            "is_instrumental": False,
            "text": "Hello world these are lyrics",
            "language": "en",
        }
        result = format_features_for_prompt(features)
        assert "Vocal track" in result
        assert "Language: en" in result


class TestCreatePrompt:
    """Tests for prompt creation."""

    def test_create_prompt_includes_features(self):
        """Prompt includes formatted features."""
        prompt = create_analysis_prompt(MOCK_FEATURES)
        assert "BPM: 120.0" in prompt

    def test_create_prompt_includes_chain_of_thought(self):
        """Prompt includes chain-of-thought instructions."""
        prompt = create_analysis_prompt(MOCK_FEATURES)
        assert "step by step" in prompt
        assert "Tempo & Rhythm Analysis" in prompt
        assert "Harmonic Analysis" in prompt
        assert "Timbral Analysis" in prompt
        assert "Dynamic Analysis" in prompt

    def test_create_prompt_includes_json_format(self):
        """Prompt specifies JSON output format."""
        prompt = create_analysis_prompt(MOCK_FEATURES)
        assert "JSON" in prompt
        assert '"summary"' in prompt
        assert '"music_theory"' in prompt
        assert '"emotional_arc"' in prompt


class TestParseJsonResponse:
    """Tests for JSON response parsing."""

    def test_parse_valid_json(self):
        """Parses valid JSON response."""
        json_str = '{"summary": "Test", "confidence": 0.8}'
        result = _parse_json_response(json_str)
        assert result["summary"] == "Test"
        assert result["confidence"] == 0.8

    def test_parse_json_with_markdown(self):
        """Parses JSON wrapped in markdown code blocks."""
        json_str = '```json\n{"summary": "Test"}\n```'
        result = _parse_json_response(json_str)
        assert result["summary"] == "Test"

    def test_parse_invalid_json(self):
        """Returns error structure for invalid JSON."""
        json_str = "not valid json"
        result = _parse_json_response(json_str)
        assert "_error" in result
        assert result["confidence"] == 0.0


class TestAnalyzeWithoutLLM:
    """Tests for rule-based fallback analysis."""

    def test_analyze_without_llm_returns_structure(self):
        """Returns structured analysis without API call."""
        result = analyze_without_llm(MOCK_FEATURES)

        # Check required fields
        assert "summary" in result
        assert "music_theory" in result
        assert "production" in result
        assert "emotional_arc" in result
        assert "use_cases" in result
        assert "similar_artists" in result
        assert "confidence" in result

    def test_analyze_without_llm_includes_tempo(self):
        """Includes tempo analysis."""
        result = analyze_without_llm(MOCK_FEATURES)
        assert "120" in result["music_theory"]["tempo_analysis"]

    def test_analyze_without_llm_includes_key(self):
        """Includes key/mode analysis."""
        result = analyze_without_llm(MOCK_FEATURES)
        assert "C" in result["music_theory"]["harmonic_analysis"]
        assert "major" in result["music_theory"]["harmonic_analysis"]

    def test_analyze_without_llm_intensity_from_loudness(self):
        """Determines intensity from loudness."""
        # High loudness
        features = MOCK_FEATURES.copy()
        features["dynamics"] = {"loudness_integrated": -8}
        result = analyze_without_llm(features)
        assert result["emotional_arc"]["intensity"] == "high"

        # Low loudness
        features["dynamics"] = {"loudness_integrated": -25}
        result = analyze_without_llm(features)
        assert result["emotional_arc"]["intensity"] == "low"

    def test_analyze_without_llm_mood_from_mode(self):
        """Determines mood from major/minor mode."""
        # Major key
        result = analyze_without_llm(MOCK_FEATURES)
        assert "uplifting" in result["emotional_arc"]["primary_mood"] or \
               "optimistic" in result["emotional_arc"]["primary_mood"]

        # Minor key
        features = MOCK_FEATURES.copy()
        features["harmony"] = {"mode": "minor", "key": "A"}
        result = analyze_without_llm(features)
        assert "melancholic" in result["emotional_arc"]["primary_mood"] or \
               "introspective" in result["emotional_arc"]["primary_mood"]

    def test_analyze_without_llm_has_use_cases(self):
        """Returns use cases."""
        result = analyze_without_llm(MOCK_FEATURES)
        assert len(result["use_cases"]) > 0

    def test_analyze_without_llm_lower_confidence(self):
        """Rule-based has lower confidence than LLM."""
        result = analyze_without_llm(MOCK_FEATURES)
        assert result["confidence"] <= 0.5

    def test_analyze_without_llm_marks_method(self):
        """Marks the analysis method as rule_based."""
        result = analyze_without_llm(MOCK_FEATURES)
        assert result.get("_method") == "rule_based"


class TestLLMAnalysis:
    """Task 9: LLM Music Theory Analyzer"""

    def test_llm_music_analysis(self):
        """Returns structured review with summary, music_theory, production, emotional_arc."""
        # Test the rule-based fallback (doesn't require API key)
        result = analyze_without_llm(MOCK_FEATURES)

        # Check structure matches expected format
        assert isinstance(result["summary"], str)
        assert isinstance(result["music_theory"], dict)
        assert isinstance(result["production"], dict)
        assert isinstance(result["emotional_arc"], dict)

    def test_chain_of_thought_reasoning(self):
        """Uses chain-of-thought prompting for music theory reasoning."""
        prompt = create_analysis_prompt(MOCK_FEATURES)

        # Verify chain-of-thought structure
        assert "1." in prompt  # Numbered steps
        assert "2." in prompt
        assert "3." in prompt
        assert "step by step" in prompt.lower()

    def test_multi_aspect_review(self):
        """Generates review covering tempo, key, chords, structure, dynamics, mood."""
        result = analyze_without_llm(MOCK_FEATURES)

        # Check music_theory covers multiple aspects
        mt = result["music_theory"]
        assert "tempo_analysis" in mt
        assert "harmonic_analysis" in mt
        assert "timbral_analysis" in mt
        assert "dynamic_analysis" in mt

        # Check emotional_arc has required fields
        ea = result["emotional_arc"]
        assert "primary_mood" in ea
        assert "intensity" in ea
