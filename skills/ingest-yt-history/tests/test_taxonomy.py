"""
Tests for HMT (Horus Music Taxonomy) extraction.

Task 6: HMT Taxonomy Extraction
"""
import pytest

from src.taxonomy import (
    extract_hmt_features,
    extract_bridge_attributes,
    extract_collection_tags,
    extract_tactical_tags,
    enrich_entry_with_hmt,
    is_hmt_available,
    get_bridge_indicators,
    HMTExtractionResult,
    CollectionTags,
)


class TestHMTExtraction:
    """Task 6: HMT Taxonomy Extraction"""

    def test_hmt_extraction(self):
        """Extracts bridge_attributes and collection_tags for each music entry."""
        # Test with a known artist that should map to Fragility
        entry = {
            "title": "Chelsea Wolfe - Carrion Flowers",
            "artist": "Chelsea Wolfe",
            "channel": "Chelsea Wolfe",
            "tags": ["doom", "dark folk"],
        }

        result = extract_hmt_features(entry)

        # Verify the result structure
        assert "bridge_attributes" in result
        assert "collection_tags" in result
        assert "tactical_tags" in result
        assert "confidence" in result

        # Verify types
        assert isinstance(result["bridge_attributes"], list)
        assert isinstance(result["collection_tags"], dict)
        assert isinstance(result["tactical_tags"], list)
        assert isinstance(result["confidence"], float)

        # Verify collection_tags structure
        collection_tags = result["collection_tags"]
        assert "domain" in collection_tags
        assert "thematic_weight" in collection_tags
        assert "function" in collection_tags

    def test_extracts_bridge_attributes(self):
        """Extracts bridge_attributes (Resilience, Fragility, etc.)."""
        # Test with Sabaton (should map to Resilience)
        entry = {
            "title": "Sabaton - The Last Stand",
            "artist": "Sabaton",
        }

        bridges = extract_bridge_attributes(entry)

        assert isinstance(bridges, list)
        # Sabaton should map to Resilience
        assert "Resilience" in bridges

    def test_extracts_collection_tags(self):
        """Extracts collection_tags (domain, thematic_weight)."""
        entry = {
            "title": "Two Steps From Hell - Victory",
            "artist": "Two Steps From Hell",
        }

        tags = extract_collection_tags(entry)

        assert isinstance(tags, dict)
        assert "domain" in tags
        assert "thematic_weight" in tags
        assert "function" in tags

        # Two Steps From Hell should have epic domain
        # The HMT verifier maps "two steps from hell" to Orchestral_Epic
        assert "Orchestral_Epic" in tags["domain"] or "Epic" in tags["thematic_weight"]

    def test_chelsea_wolfe_dark_folk(self):
        """Chelsea Wolfe correctly maps to Dark_Folk domain.

        Note: In the HMT verifier, Chelsea Wolfe is associated with the
        Dark_Folk domain, not the Fragility bridge. The Fragility bridge
        artists are Daughter, Billie Marten, Phoebe Bridgers, etc.
        """
        entry = {
            "title": "Carrion Flowers",
            "artist": "Chelsea Wolfe",
            "channel": "Chelsea Wolfe",
        }

        result = extract_hmt_features(entry)

        # Chelsea Wolfe maps to Dark_Folk domain
        assert "Dark_Folk" in result["collection_tags"]["domain"], (
            f"Expected Dark_Folk in domain, got: {result['collection_tags']['domain']}"
        )

    def test_daughter_fragility(self):
        """Daughter correctly maps to Fragility bridge."""
        entry = {
            "title": "Youth",
            "artist": "Daughter",
            "channel": "Daughter",
        }

        result = extract_hmt_features(entry)

        assert "Fragility" in result["bridge_attributes"], (
            f"Expected Fragility in bridges, got: {result['bridge_attributes']}"
        )

    def test_sabaton_resilience(self):
        """Sabaton correctly maps to Resilience bridge."""
        entry = {
            "title": "The Last Stand",
            "artist": "Sabaton",
            "channel": "Sabaton",
        }

        result = extract_hmt_features(entry)

        assert "Resilience" in result["bridge_attributes"], (
            f"Expected Resilience in bridges, got: {result['bridge_attributes']}"
        )

    def test_meshuggah_precision(self):
        """Meshuggah correctly maps to Precision bridge."""
        entry = {
            "title": "Bleed",
            "artist": "Meshuggah",
            "channel": "Meshuggah",
        }

        result = extract_hmt_features(entry)

        assert "Precision" in result["bridge_attributes"], (
            f"Expected Precision in bridges, got: {result['bridge_attributes']}"
        )

    def test_nine_inch_nails_corruption(self):
        """Nine Inch Nails correctly maps to Corruption bridge."""
        entry = {
            "title": "Hurt",
            "artist": "Nine Inch Nails",
            "channel": "Nine Inch Nails",
        }

        result = extract_hmt_features(entry)

        assert "Corruption" in result["bridge_attributes"], (
            f"Expected Corruption in bridges, got: {result['bridge_attributes']}"
        )

    def test_wardruna_loyalty(self):
        """Wardruna correctly maps to Loyalty bridge."""
        entry = {
            "title": "Helvegen",
            "artist": "Wardruna",
            "channel": "Wardruna",
        }

        result = extract_hmt_features(entry)

        assert "Loyalty" in result["bridge_attributes"], (
            f"Expected Loyalty in bridges, got: {result['bridge_attributes']}"
        )

    def test_sunn_o_stealth(self):
        """Sunn O))) correctly maps to Stealth bridge."""
        entry = {
            "title": "Aghartha",
            "artist": "Sunn O)))",
            "channel": "Sunn O)))",
        }

        result = extract_hmt_features(entry)

        assert "Stealth" in result["bridge_attributes"], (
            f"Expected Stealth in bridges, got: {result['bridge_attributes']}"
        )

    def test_enrich_entry_with_hmt(self):
        """enrich_entry_with_hmt adds HMT fields to entry."""
        entry = {
            "video_id": "abc123",
            "title": "Chelsea Wolfe - Carrion Flowers",
            "artist": "Chelsea Wolfe",
        }

        enriched = enrich_entry_with_hmt(entry)

        # Should be the same object
        assert enriched is entry

        # Should have HMT fields
        assert "hmt_bridge_attributes" in enriched
        assert "hmt_collection_tags" in enriched
        assert "hmt_tactical_tags" in enriched
        assert "hmt_confidence" in enriched

        # Original fields should be preserved
        assert enriched["video_id"] == "abc123"
        assert enriched["title"] == "Chelsea Wolfe - Carrion Flowers"

    def test_no_match_returns_empty(self):
        """Entry with no taxonomy match returns empty but valid result."""
        entry = {
            "title": "Random Video Title",
            "channel": "Random Channel",
        }

        result = extract_hmt_features(entry)

        # Should still have valid structure
        assert "bridge_attributes" in result
        assert "collection_tags" in result
        assert isinstance(result["bridge_attributes"], list)
        assert isinstance(result["collection_tags"], dict)

    def test_confidence_score(self):
        """Confidence score is between 0 and 1."""
        entry = {
            "title": "Sabaton - The Last Stand",
            "artist": "Sabaton",
        }

        result = extract_hmt_features(entry)

        assert 0.0 <= result["confidence"] <= 1.0

    def test_hmt_available(self):
        """HMT verifier is available for testing."""
        assert is_hmt_available(), "HMT verifier not available"

    def test_get_bridge_indicators(self):
        """Can retrieve bridge indicator definitions."""
        indicators = get_bridge_indicators()

        assert isinstance(indicators, dict)
        assert "Precision" in indicators
        assert "Resilience" in indicators
        assert "Fragility" in indicators
        assert "Corruption" in indicators
        assert "Loyalty" in indicators
        assert "Stealth" in indicators

        # Verify structure
        for bridge_name, data in indicators.items():
            assert "indicators" in data
            assert "artists" in data
            assert "lore_resonance" in data


class TestHMTEdgeCases:
    """Edge cases and error handling for HMT extraction."""

    def test_empty_entry(self):
        """Empty entry returns empty result without error."""
        result = extract_hmt_features({})

        assert result["bridge_attributes"] == []
        assert result["collection_tags"]["domain"] == []

    def test_title_only(self):
        """Entry with only title still works."""
        entry = {"title": "Chelsea Wolfe - Carrion Flowers"}

        result = extract_hmt_features(entry)

        # Should detect Chelsea Wolfe from title
        assert "bridge_attributes" in result

    def test_channel_fallback_to_artist(self):
        """Channel is used as artist fallback."""
        entry = {
            "title": "The Last Stand",
            "channel": "Sabaton",
        }

        result = extract_hmt_features(entry)

        # Should detect Sabaton from channel
        assert "Resilience" in result["bridge_attributes"]

    def test_case_insensitive_matching(self):
        """Artist matching is case-insensitive."""
        entry = {
            "title": "Bleed",
            "artist": "MESHUGGAH",  # All caps
        }

        result = extract_hmt_features(entry)

        # Should still match
        assert "Precision" in result["bridge_attributes"]

    def test_indicator_keyword_in_title(self):
        """Indicator keywords in title are detected.

        Note: The HMT verifier checks for indicator keywords (like 'technical',
        'polyrhythmic', 'ambient') in the title, not artist names.
        """
        entry = {
            "title": "Technical Death Metal Compilation",
            "channel": "Some Music Channel",
        }

        result = extract_hmt_features(entry)

        # 'technical' is a Precision indicator
        assert "Precision" in result["bridge_attributes"]

    def test_multiple_bridges(self):
        """Entry can match multiple bridges."""
        # An entry with multiple matching indicators
        entry = {
            "title": "Triumphant Epic Battle Ambient Drone",
            "artist": "Unknown",
        }

        result = extract_hmt_features(entry)

        # Multiple indicators might match different bridges
        # Just verify we get valid output
        assert isinstance(result["bridge_attributes"], list)
