"""
Federated Taxonomy bridge extraction for /ask learn.

Handles importing the taxonomy module (with fallback stubs) and
extracting/aggregating bridge attributes from content.
"""

import sys
from collections import Counter
from pathlib import Path

from loguru import logger as log

# Skill paths (relative to this file)
SKILLS_DIR = Path(__file__).parent.parent

# -------------------------------------------------------------------------
# Federated Taxonomy Integration
# -------------------------------------------------------------------------
_TAXONOMY_AVAILABLE = False
try:
    if str(SKILLS_DIR) not in sys.path:
        sys.path.insert(0, str(SKILLS_DIR))
    from common.taxonomy import (
        get_bridge_attributes,
        extract_taxonomy_features,
        ContentType,
        BOOK_BRIDGE_INDICATORS,
    )
    _TAXONOMY_AVAILABLE = True
    log.debug("Federated Taxonomy loaded from common/taxonomy.py")
except ImportError as e:
    log.warning("Federated Taxonomy not available: %s", e)
    # Fallback stubs
    def get_bridge_attributes(text: str, content_type=None) -> list:
        return []
    def extract_taxonomy_features(*args, **kwargs) -> dict:
        return {"bridge_attributes": [], "collection_tags": {}, "tactical_tags": []}
    class ContentType:
        BOOK = "book"
        VIDEO = "video"
        ARTICLE = "article"
        YOUTUBE = "youtube"
        LORE = "lore"
        MUSIC = "music"
        MOVIE = "movie"
        AUDIOBOOK = "audiobook"
    BOOK_BRIDGE_INDICATORS = {}


def extract_bridges_from_content(
    text: str,
    content_type: str = "article",
    topic: str = "",
) -> list[str]:
    """Extract Federated Taxonomy bridge attributes from text content.

    Args:
        text: The content text to analyze
        content_type: Type of content (book, video, article)
        topic: Optional topic context for better extraction

    Returns:
        List of bridge attribute names (Precision, Resilience, Fragility, etc.)
    """
    if not _TAXONOMY_AVAILABLE:
        log.debug("Taxonomy not available, skipping bridge extraction")
        return []

    try:
        # Map content_type to ContentType enum
        ct_map = {
            "book": ContentType.BOOK,
            "video": ContentType.YOUTUBE,
            "article": ContentType.LORE,
            "youtube": ContentType.YOUTUBE,
            "web": ContentType.LORE,
            "dogpile": ContentType.LORE,
            "feed": ContentType.LORE,
        }
        ct = ct_map.get(content_type.lower(), None)

        # Use extract_taxonomy_features with description parameter for better extraction
        analysis_text = text[:2000]
        result = extract_taxonomy_features(
            content_type=ct or ContentType.LORE,
            title=topic or "",
            description=analysis_text,
        )
        bridges = result.get("bridge_attributes", [])
        if bridges:
            log.debug("Extracted bridges from %s: %s", content_type, bridges)
        return bridges

    except Exception as e:
        log.warning("Bridge extraction failed: %s", e)
        return []


def aggregate_bridges(bridge_lists: list[list[str]], min_count: int = 2) -> list[str]:
    """Aggregate multiple bridge extractions into a consensus set.

    Args:
        bridge_lists: List of bridge attribute lists from different content
        min_count: Minimum occurrences required to include a bridge

    Returns:
        List of bridge attributes that appear frequently enough
    """
    all_bridges = []
    for bridges in bridge_lists:
        all_bridges.extend(bridges)

    counts = Counter(all_bridges)

    # If we have few sources, lower the threshold
    threshold = min(min_count, max(1, len(bridge_lists) // 2))

    result = [bridge for bridge, count in counts.items() if count >= threshold]
    log.debug("Aggregated bridges: %s (threshold=%d)", result, threshold)
    return result
