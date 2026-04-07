#!/usr/bin/env python3
"""Taxonomy type definitions and constants.

Contains enums, typed dicts, and prompt templates used across the taxonomy module.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, TypedDict


# ==============================================================================
# CONTENT TYPES
# ==============================================================================

class ContentType(str, Enum):
    """Supported content types for taxonomy extraction."""
    MUSIC = "music"
    MOVIE = "movie"
    BOOK = "book"
    AUDIOBOOK = "audiobook"
    YOUTUBE = "youtube"
    LORE = "lore"
    OPERATIONAL = "operational"
    SECURITY = "security"  # SPARTA security content
    SESSION = "session"    # Agent conversation sessions


# ==============================================================================
# TYPED RESULTS
# ==============================================================================

class CollectionTags(TypedDict, total=False):
    """Collection-specific tags (Tier 3)."""
    domain: List[str]
    thematic_weight: List[str]
    function: List[str]
    perspective: List[str]
    sensory: List[str]


class Participants(TypedDict, total=False):
    """Conversation/content participants for persona-scoped recall."""
    user_id: str
    persona_id: str
    participants: List[str]  # All participant IDs (users + personas)


class TaxonomyExtractionResult(TypedDict):
    """Complete taxonomy extraction result for any content type."""
    content_type: str
    bridge_attributes: List[str]
    collection_tags: CollectionTags
    tactical_tags: List[str]
    episodic_associations: List[str]
    dimensions: Dict[str, List[str]]
    participants: Participants  # Who was in the conversation/content
    confidence: float
    raw_matches: Dict[str, Any]
    method: Optional[str]  # Added to track extraction method


# ==============================================================================
# LLM EXTRACTION PROMPT
# ==============================================================================

EXTRACTION_PROMPT = """Extract Federated Taxonomy tags from this text.

BRIDGE TAGS (Tier 0 - pick 0-3 most relevant):
Precision, Resilience, Fragility, Corruption, Loyalty, Stealth, Intimacy

COLLECTION: {collection}
COLLECTION TAGS (pick best match per dimension, or null):
{vocab}

TEXT:
{text}

Return JSON only:
{{"bridge_tags": [...], "collection_tags": {{"function": "...", "domain": "..."}}, "confidence": 0.8}}"""
