"""
Common utilities for all skills.

This module provides shared functionality to ensure consistency across skills:
- Memory integration (recall, learn)
- Taxonomy extraction (unified Bridge Attributes for multi-hop graph traversal)
"""

from .memory_client import (
    MemoryClient,
    MemoryScope,
    RecallResult,
    LearnResult,
    recall,
    learn,
    batch_learn,
    batch_recall,
    get_client,
    with_retries,
    RateLimiter,
    redact_sensitive,
)

from .taxonomy import (
    ContentType,
    TaxonomyExtractionResult,
    CollectionTags,
    extract_taxonomy_features,
    get_bridge_attributes,
    get_episodic_associations,
    create_verifier,
    is_taxonomy_available,
    MOVIE_BRIDGE_INDICATORS,
    BOOK_BRIDGE_INDICATORS,
    LORE_BRIDGE_MAPPINGS,
)

__all__ = [
    # Memory client
    "MemoryClient",
    "MemoryScope",
    "RecallResult",
    "LearnResult",
    "recall",
    "learn",
    "batch_learn",
    "batch_recall",
    "get_client",
    "with_retries",
    "RateLimiter",
    "redact_sensitive",
    # Taxonomy
    "ContentType",
    "TaxonomyExtractionResult",
    "CollectionTags",
    "extract_taxonomy_features",
    "get_bridge_attributes",
    "get_episodic_associations",
    "create_verifier",
    "is_taxonomy_available",
    "MOVIE_BRIDGE_INDICATORS",
    "BOOK_BRIDGE_INDICATORS",
    "LORE_BRIDGE_MAPPINGS",
]
