#!/usr/bin/env python3
"""
HMT (Horus Music Taxonomy) extraction for YouTube music history.

Task 6: Extract bridge_attributes, collection_tags, and tactical_tags
from music entries using the HMT verifier.

Bridge Attributes (Tier 0):
- Precision: polyrhythmic, technical (Meshuggah, Tool)
- Resilience: triumphant, epic (Sabaton, Two Steps From Hell)
- Fragility: acoustic, delicate (Chelsea Wolfe, Daughter)
- Corruption: industrial, harsh (Nine Inch Nails, HEALTH)
- Loyalty: ceremonial, sacred (Wardruna, Heilung)
- Stealth: ambient, drone (Sunn O))), Boris)
"""
import sys
from pathlib import Path
from typing import Any, TypedDict

# Add the HMT verifier location to the path
HMT_VERIFIER_PATH = Path("/home/graham/workspace/experiments/memory/persona/bridge")
if str(HMT_VERIFIER_PATH) not in sys.path:
    sys.path.insert(0, str(HMT_VERIFIER_PATH))

# Import the HMT verifier
try:
    from horus_music_taxonomy import (
        HorusMusicTaxonomyVerifier,
        MUSIC_BRIDGE_INDICATORS,
        MUSIC_TACTICAL_TAGS,
        HMT_VOCABULARY,
        MusicDimension,
    )
    HMT_AVAILABLE = True
except ImportError:
    HMT_AVAILABLE = False


class CollectionTags(TypedDict):
    """Collection tags for a music entry."""
    domain: list[str]
    thematic_weight: list[str]
    function: list[str]


class HMTExtractionResult(TypedDict):
    """Result of HMT taxonomy extraction."""
    bridge_attributes: list[str]
    collection_tags: CollectionTags
    tactical_tags: list[str]
    confidence: float
    raw_dimensions: dict[str, list[str]]


def _create_verifier() -> "HorusMusicTaxonomyVerifier | None":
    """Create an HMT verifier instance, or None if unavailable."""
    if not HMT_AVAILABLE:
        return None
    return HorusMusicTaxonomyVerifier()


# Singleton verifier instance
_verifier: "HorusMusicTaxonomyVerifier | None" = None


def get_verifier() -> "HorusMusicTaxonomyVerifier | None":
    """Get or create the singleton HMT verifier instance."""
    global _verifier
    if _verifier is None:
        _verifier = _create_verifier()
    return _verifier


def extract_hmt_features(entry: dict[str, Any]) -> HMTExtractionResult:
    """Extract HMT taxonomy features from a music entry.

    Uses the HMT verifier to extract bridge attributes, collection tags,
    and tactical tags from a music entry.

    Args:
        entry: Dict with title, artist/channel, url, duration, tags, etc.
            Expected fields:
            - title: Video title
            - artist or channel: Artist/channel name
            - tags: Optional list of tags
            - products: Optional list (e.g., ["YouTube Music"])

    Returns:
        HMTExtractionResult with:
        - bridge_attributes: List of Tier 0 bridges (Precision, Resilience, etc.)
        - collection_tags: Dict with domain, thematic_weight, function
        - tactical_tags: List of Tier 1 tags (Score, Recall, Amplify, etc.)
        - confidence: Confidence score (0.0-1.0)
        - raw_dimensions: Full dimension dict from verifier

    Example:
        >>> entry = {"title": "Chelsea Wolfe - Carrion Flowers", "artist": "Chelsea Wolfe"}
        >>> result = extract_hmt_features(entry)
        >>> "Fragility" in result["bridge_attributes"]
        True
    """
    verifier = get_verifier()

    if verifier is None:
        # Return empty result if HMT verifier is not available
        return HMTExtractionResult(
            bridge_attributes=[],
            collection_tags=CollectionTags(domain=[], thematic_weight=[], function=[]),
            tactical_tags=[],
            confidence=0.0,
            raw_dimensions={},
        )

    # Normalize entry for HMT verifier
    # The verifier expects: title, artist, channel, tags
    normalized_entry = {
        "title": entry.get("title", ""),
        "artist": entry.get("artist", entry.get("channel", "")),
        "channel": entry.get("channel", entry.get("artist", "")),
        "tags": entry.get("tags", []),
    }

    # Extract features using the HMT verifier
    features = verifier.extract_features(normalized_entry)

    # Extract collection tags from dimensions
    dimensions = features.get("dimensions", {})
    collection_tags = CollectionTags(
        domain=dimensions.get("domain", []),
        thematic_weight=dimensions.get("thematic_weight", []),
        function=dimensions.get("function", []),
    )

    return HMTExtractionResult(
        bridge_attributes=features.get("bridge_attributes", []),
        collection_tags=collection_tags,
        tactical_tags=features.get("tactical_tags", []),
        confidence=features.get("confidence", 0.0),
        raw_dimensions=dimensions,
    )


def extract_bridge_attributes(entry: dict[str, Any]) -> list[str]:
    """Extract only bridge attributes from a music entry.

    Convenience function for getting just the Tier 0 bridges.

    Args:
        entry: Music entry dict

    Returns:
        List of bridge attribute names (e.g., ["Fragility", "Corruption"])
    """
    result = extract_hmt_features(entry)
    return result["bridge_attributes"]


def extract_collection_tags(entry: dict[str, Any]) -> CollectionTags:
    """Extract only collection tags from a music entry.

    Convenience function for getting domain, thematic_weight, and function.

    Args:
        entry: Music entry dict

    Returns:
        CollectionTags dict with domain, thematic_weight, function lists
    """
    result = extract_hmt_features(entry)
    return result["collection_tags"]


def extract_tactical_tags(entry: dict[str, Any]) -> list[str]:
    """Extract only tactical tags from a music entry.

    Convenience function for getting Tier 1 tactical tags.

    Args:
        entry: Music entry dict

    Returns:
        List of tactical tag names (e.g., ["Score", "Recall"])
    """
    result = extract_hmt_features(entry)
    return result["tactical_tags"]


def enrich_entry_with_hmt(entry: dict[str, Any]) -> dict[str, Any]:
    """Enrich a music entry with HMT taxonomy data.

    Adds HMT fields to the entry in-place and returns it.

    Args:
        entry: Music entry dict to enrich

    Returns:
        The same entry dict with added HMT fields:
        - hmt_bridge_attributes
        - hmt_collection_tags
        - hmt_tactical_tags
        - hmt_confidence
    """
    result = extract_hmt_features(entry)

    entry["hmt_bridge_attributes"] = result["bridge_attributes"]
    entry["hmt_collection_tags"] = result["collection_tags"]
    entry["hmt_tactical_tags"] = result["tactical_tags"]
    entry["hmt_confidence"] = result["confidence"]

    return entry


def is_hmt_available() -> bool:
    """Check if the HMT verifier is available.

    Returns:
        True if the HMT verifier can be imported
    """
    return HMT_AVAILABLE


def get_bridge_indicators() -> dict[str, dict[str, Any]]:
    """Get the bridge indicator definitions from HMT.

    Returns:
        Dict mapping bridge names to their indicators and artists
    """
    if not HMT_AVAILABLE:
        return {}
    return MUSIC_BRIDGE_INDICATORS


def get_tactical_tag_definitions() -> dict[str, str]:
    """Get the tactical tag definitions from HMT.

    Returns:
        Dict mapping tactical tag names to their descriptions
    """
    if not HMT_AVAILABLE:
        return {}
    return MUSIC_TACTICAL_TAGS
