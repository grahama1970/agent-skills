"""
Tests for HMT taxonomy mapping.

Task 10: HMT Bridge Attribute Mapper
"""
import pytest
from pathlib import Path

from src.taxonomy import (
    map_features_to_bridges,
    calculate_bridge_score,
    extract_collection_tags,
    extract_tactical_tags,
    get_bridge_indicators,
    get_episodic_associations,
    BRIDGE_INDICATORS,
)


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


class TestHMTMapping:
    """Task 10: HMT Bridge Attribute Mapper"""

    def test_map_to_bridges(self):
        """Returns bridge_attributes list, collection_tags dict, tactical_tags list, confidence float."""
        # Create mock features that should match Resilience (triumphant, major key, building dynamics)
        features = {
            "rhythm": {
                "bpm": 120,
                "tempo_variance": 0.05,
                "beat_strength": 0.7,
                "time_signature": "4/4",
            },
            "harmony": {
                "key": "C",
                "mode": "major",
                "harmonic_complexity": 0.4,
            },
            "timbre": {
                "brightness": "bright",
                "texture": "dense",
                "spectral_flatness": 0.1,
            },
            "dynamics": {
                "loudness_integrated": -12,
                "dynamic_range": 15,
                "loudness_range": 10,
            },
            "lyrics": {
                "is_instrumental": True,
            },
        }

        result = map_features_to_bridges(features)

        # Check required fields
        assert "bridge_attributes" in result
        assert "collection_tags" in result
        assert "tactical_tags" in result
        assert "confidence" in result
        assert "bridge_scores" in result

        # Check types
        assert isinstance(result["bridge_attributes"], list)
        assert isinstance(result["collection_tags"], dict)
        assert isinstance(result["tactical_tags"], list)
        assert isinstance(result["confidence"], float)

        # Check confidence range
        assert 0 <= result["confidence"] <= 1.0

    def test_precision_mapping(self):
        """Maps polyrhythmic/technical features to Precision bridge."""
        features = {
            "rhythm": {
                "tempo_variance": 0.25,  # High variance (> 0.15)
                "time_signature": "7/8",  # Odd time signature
                "beat_strength": 0.8,
            },
            "harmony": {
                "mode": "minor",
                "harmonic_complexity": 0.85,  # High complexity (> 0.7)
            },
            "timbre": {
                "brightness": "bright",
                "texture": "dense",
                "spectral_flatness": 0.35,  # High (> 0.3)
                "zero_crossing_rate": 0.2,
            },
            "dynamics": {
                "dynamic_range": 10,
            },
        }

        result = map_features_to_bridges(features)

        # Should have Precision in top bridges
        assert "Precision" in result["bridge_attributes"]

    def test_resilience_mapping(self):
        """Maps triumphant/crescendo features to Resilience bridge."""
        features = {
            "rhythm": {
                "tempo_variance": 0.05,
                "time_signature": "4/4",
                "beat_strength": 0.8,
            },
            "harmony": {
                "mode": "major",  # Major key
                "harmonic_complexity": 0.4,
            },
            "timbre": {
                "brightness": "bright",  # Bright sound
                "texture": "dense",  # Full orchestration
                "spectral_flatness": 0.1,
            },
            "dynamics": {
                "dynamic_range": 18,  # Wide dynamics (> 12)
                "loudness_integrated": -10,
            },
        }

        result = map_features_to_bridges(features)

        # Should have Resilience in bridges
        assert "Resilience" in result["bridge_attributes"]

    def test_fragility_mapping(self):
        """Maps sparse/acoustic features to Fragility bridge."""
        features = {
            "rhythm": {
                "tempo_variance": 0.03,
                "time_signature": "4/4",
                "beat_strength": 0.3,
            },
            "harmony": {
                "mode": "minor",  # Minor key
                "harmonic_complexity": 0.3,
            },
            "timbre": {
                "brightness": "dark",  # Dark sound
                "texture": "sparse",  # Minimal instrumentation
                "spectral_flatness": 0.05,
                "spectral_bandwidth": 1200,  # Low bandwidth
            },
            "dynamics": {
                "dynamic_range": 8,
                "loudness_integrated": -25,  # Quiet
            },
        }

        result = map_features_to_bridges(features)

        # Should have Fragility in bridges
        assert "Fragility" in result["bridge_attributes"]

    def test_corruption_mapping(self):
        """Maps distorted/industrial features to Corruption bridge."""
        features = {
            "rhythm": {
                "tempo_variance": 0.1,
                "time_signature": "4/4",
                "beat_strength": 0.6,
            },
            "harmony": {
                "mode": "minor",
                "harmonic_complexity": 0.7,
            },
            "timbre": {
                "brightness": "bright",  # Industrial harshness
                "texture": "dense",
                "spectral_flatness": 0.5,  # High (> 0.4) = noise-like
                "zero_crossing_rate": 0.25,  # High (> 0.2)
            },
            "dynamics": {
                "dynamic_range": 6,
                "loudness_integrated": -8,
            },
        }

        result = map_features_to_bridges(features)

        # Should have Corruption in bridges
        assert "Corruption" in result["bridge_attributes"]

    def test_loyalty_mapping(self):
        """Maps ceremonial/choral features to Loyalty bridge."""
        features = {
            "rhythm": {
                "tempo_variance": 0.04,
                "time_signature": "4/4",
                "beat_strength": 0.5,
            },
            "harmony": {
                "mode": "major",
                "harmonic_complexity": 0.25,  # Low complexity (< 0.3) = modal simplicity
            },
            "timbre": {
                "brightness": "neutral",
                "texture": "layered",  # Choral layers
                "spectral_flatness": 0.1,
                "spectral_contrast": 55,  # High contrast (> 50)
            },
            "dynamics": {
                "dynamic_range": 8,  # Medium (around 8)
                "loudness_integrated": -16,
            },
        }

        result = map_features_to_bridges(features)

        # Should have Loyalty in bridges
        assert "Loyalty" in result["bridge_attributes"]

    def test_stealth_mapping(self):
        """Maps ambient/drone features to Stealth bridge."""
        features = {
            "rhythm": {
                "tempo_variance": 0.02,  # Very low (< 0.05) = steady/droning
                "time_signature": "4/4",
                "beat_strength": 0.2,  # Low (< 0.3)
            },
            "harmony": {
                "mode": "minor",
                "harmonic_complexity": 0.3,
            },
            "timbre": {
                "brightness": "dark",  # Low frequencies
                "texture": "sparse",  # Minimal elements
                "spectral_flatness": 0.1,
                "spectral_centroid": 800,  # Low (< 1000) = bass-heavy
            },
            "dynamics": {
                "dynamic_range": 5,
                "loudness_integrated": -30,
            },
        }

        result = map_features_to_bridges(features)

        # Should have Stealth in bridges
        assert "Stealth" in result["bridge_attributes"]

    def test_collection_tags_structure(self):
        """Validates collection_tags has domain, thematic_weight, function."""
        features = {
            "rhythm": {"bpm": 100, "tempo_variance": 0.1, "time_signature": "4/4"},
            "harmony": {"mode": "minor", "harmonic_complexity": 0.5},
            "timbre": {"brightness": "dark", "texture": "sparse"},
            "dynamics": {"dynamic_range": 10, "loudness_integrated": -18},
        }

        result = map_features_to_bridges(features)
        tags = result["collection_tags"]

        assert "domain" in tags
        assert "thematic_weight" in tags
        assert "function" in tags

        assert isinstance(tags["domain"], list)
        assert isinstance(tags["thematic_weight"], str)
        assert isinstance(tags["function"], str)


class TestBridgeIndicators:
    """Tests for bridge indicator definitions."""

    def test_all_bridges_defined(self):
        """All six bridges are defined."""
        expected_bridges = [
            "Precision", "Resilience", "Fragility",
            "Corruption", "Loyalty", "Stealth"
        ]
        for bridge in expected_bridges:
            assert bridge in BRIDGE_INDICATORS

    def test_bridge_has_required_fields(self):
        """Each bridge has description, lore_resonance, indicators, audio_patterns, artists."""
        for bridge_name, bridge_def in BRIDGE_INDICATORS.items():
            assert "description" in bridge_def, f"{bridge_name} missing description"
            assert "lore_resonance" in bridge_def, f"{bridge_name} missing lore_resonance"
            assert "indicators" in bridge_def or "audio_patterns" in bridge_def, \
                f"{bridge_name} missing indicators or audio_patterns"
            assert "artists" in bridge_def, f"{bridge_name} missing artists"


class TestEpisodicAssociations:
    """Tests for episodic (lore) associations."""

    def test_get_episodic_associations(self):
        """Returns lore events for bridges."""
        associations = get_episodic_associations(["Precision", "Corruption"])

        assert isinstance(associations, list)
        assert len(associations) > 0
        # Should include events from both bridges
        assert "Iron_Cage" in associations or "Olympia_Campaign" in associations
        assert "Davin_Corruption" in associations or "Isstvan_III" in associations

    def test_empty_bridges_returns_empty(self):
        """Empty bridge list returns empty associations."""
        associations = get_episodic_associations([])
        assert associations == []


class TestTacticalTags:
    """Tests for tactical tag extraction."""

    def test_tactical_tags_always_includes_score_and_recall(self):
        """Score and Recall are always included."""
        features = {
            "rhythm": {"bpm": 100},
            "dynamics": {"loudness_range": 5},
            "lyrics": {"is_instrumental": True},
        }

        tags = extract_tactical_tags(features, [])

        assert "Score" in tags
        assert "Recall" in tags

    def test_contrast_tag_for_wide_dynamics(self):
        """Contrast tag for loudness_range > 15."""
        features = {
            "rhythm": {"bpm": 100},
            "dynamics": {"loudness_range": 20},
            "lyrics": {"is_instrumental": True},
        }

        tags = extract_tactical_tags(features, [])

        assert "Contrast" in tags

    def test_amplify_tag_for_fast_tempo(self):
        """Amplify tag for bpm > 120."""
        features = {
            "rhythm": {"bpm": 140},
            "dynamics": {"loudness_range": 5},
            "lyrics": {"is_instrumental": True},
        }

        tags = extract_tactical_tags(features, [])

        assert "Amplify" in tags

    def test_invoke_tag_for_lyrics(self):
        """Invoke tag for tracks with lyrics."""
        features = {
            "rhythm": {"bpm": 100},
            "dynamics": {"loudness_range": 5},
            "lyrics": {"is_instrumental": False},
        }

        tags = extract_tactical_tags(features, [])

        assert "Invoke" in tags
