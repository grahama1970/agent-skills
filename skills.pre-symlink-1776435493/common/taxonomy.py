#!/usr/bin/env python3
"""
Unified Taxonomy Module for All Collections (Federated Taxonomy Bridge)

This module provides taxonomy extraction for ALL content types (music, movies, books,
audiobooks, YouTube) using the canonical Horus Taxonomy from:
    /home/graham/workspace/experiments/memory/persona/bridge/

The Federated Taxonomy enables multi-hop graph traversal across collections via:
- Tier 0: Bridge Attributes (Precision, Resilience, Fragility, Corruption, Loyalty, Stealth)
- Tier 1: Tactical Tags (D3FEND mappings for security, functional tags for media)
- Tier 3: Collection-specific dimensions (Domain, Thematic Weight, Function, Perspective)

Edge Scoring Formula:
    (dimension_overlap * 0.5) + min(bridge_bonus, 0.5) + min(tactical_bonus, 0.2) + cross_collection_bonus

Usage:
    from common.taxonomy import (
        extract_taxonomy_features,
        get_bridge_attributes,
        get_episodic_associations,
        create_verifier,
        ContentType,
    )

    # For music
    features = extract_taxonomy_features(
        content_type=ContentType.MUSIC,
        title="Wardruna - Helvegen",
        artist="Wardruna",
    )

    # For movies
    features = extract_taxonomy_features(
        content_type=ContentType.MOVIE,
        title="Dune: Part Two",
        tags=["epic", "loyalty", "betrayal"],
        emotion="awe",
    )

    # For books
    features = extract_taxonomy_features(
        content_type=ContentType.BOOK,
        title="Horus Rising",
        author="Dan Abnett",
        genre="Warhammer 40K",
    )

This file is a thin assembler that re-exports from submodules.
"""

# Types and enums
from common.taxonomy_types import (
    ContentType,
    CollectionTags,
    TaxonomyExtractionResult,
)

# Bridge indicators and lore mappings
from common.taxonomy_indicators import (
    MOVIE_BRIDGE_INDICATORS,
    BOOK_BRIDGE_INDICATORS,
    LORE_BRIDGE_MAPPINGS,
)

# Core functions and utilities
from common.taxonomy_core import (
    extract_taxonomy_features,
    get_bridge_attributes,
    get_episodic_associations,
    create_verifier,
    is_taxonomy_available,
)

# ==============================================================================
# EXPORTS
# ==============================================================================

__all__ = [
    # Core functions
    "extract_taxonomy_features",
    "get_bridge_attributes",
    "get_episodic_associations",
    "create_verifier",
    "is_taxonomy_available",
    # Types
    "ContentType",
    "TaxonomyExtractionResult",
    "CollectionTags",
    # Indicators (for reference)
    "MOVIE_BRIDGE_INDICATORS",
    "BOOK_BRIDGE_INDICATORS",
    "LORE_BRIDGE_MAPPINGS",
]
