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
"""

import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, TypedDict

# ==============================================================================
# CANONICAL TAXONOMY IMPORTS
# ==============================================================================

_MEMORY_PERSONA_PATH = Path("/home/graham/workspace/experiments/memory/persona")
if str(_MEMORY_PERSONA_PATH) not in sys.path:
    sys.path.insert(0, str(_MEMORY_PERSONA_PATH))

# Import canonical HMT (for music)
_HMT_AVAILABLE = False
try:
    from bridge.horus_music_taxonomy import (
        MUSIC_BRIDGE_INDICATORS,
        EPISODIC_ASSOCIATIONS,
        HMT_VOCABULARY,
        MUSIC_TACTICAL_TAGS,
        MusicDimension,
        MathematicalMusicFeatures,
        HorusMusicTaxonomyVerifier,
        create_music_verifier,
    )
    _HMT_AVAILABLE = True
except ImportError as e:
    import warnings
    warnings.warn(f"Cannot import canonical HMT: {e}")
    MUSIC_BRIDGE_INDICATORS = {}
    EPISODIC_ASSOCIATIONS = {}
    HMT_VOCABULARY = {}
    MUSIC_TACTICAL_TAGS = {}
    MusicDimension = None

# Import main verifier (for lore, operational, sparta)
_VERIFIER_AVAILABLE = False
try:
    from bridge.horus_taxonomy_verifier import (
        HorusTaxonomyVerifier,
        BRIDGE_ATTRIBUTES,
        HLT_VOCABULARY,
        OPERATIONAL_VOCABULARY,
        SPARTA_VOCABULARY,
        TACTICAL_TO_CONCEPTUAL,
        Dimension,
        TaxonomyFeatures,
    )
    _VERIFIER_AVAILABLE = True
except ImportError as e:
    import warnings
    warnings.warn(f"Cannot import canonical taxonomy verifier: {e}")
    BRIDGE_ATTRIBUTES = {}
    HLT_VOCABULARY = {}
    OPERATIONAL_VOCABULARY = {}
    SPARTA_VOCABULARY = {}
    TACTICAL_TO_CONCEPTUAL = {}
    Dimension = None


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


# ==============================================================================
# CONTENT-SPECIFIC BRIDGE INDICATORS
# ==============================================================================

# Movie/Film Bridge Indicators (maps visual/emotional to bridges)
MOVIE_BRIDGE_INDICATORS = {
    "Precision": {
        "themes": ["strategy", "planning", "calculated", "methodical"],
        "emotions": ["focused", "determined"],
        "genres": ["thriller", "heist", "war"],
        "lore_resonance": "Iron Warriors, siege craft, calculated warfare",
    },
    "Resilience": {
        "themes": ["survival", "endurance", "triumph", "last stand", "defense"],
        "emotions": ["triumphant", "defiant", "hopeful"],
        "genres": ["war", "survival", "sports", "epic"],
        "lore_resonance": "Imperial Fists, Siege of Terra, Dorn's defense",
    },
    "Fragility": {
        "themes": ["loss", "broken", "vulnerable", "shattered"],
        "emotions": ["sorrow", "melancholy", "despair"],
        "genres": ["drama", "tragedy", "romance"],
        "lore_resonance": "Webway collapse, Magnus's Folly, shattered dreams",
    },
    "Corruption": {
        "themes": ["betrayal", "fall", "darkness", "possession", "influence"],
        "emotions": ["dread", "horror", "fear"],
        "genres": ["horror", "psychological", "thriller"],
        "lore_resonance": "Davin corruption, Chaos influence, Warp taint",
    },
    "Loyalty": {
        "themes": ["oath", "duty", "honor", "brotherhood", "sacrifice"],
        "emotions": ["devotion", "pride", "camaraderie"],
        "genres": ["war", "drama", "action"],
        "lore_resonance": "Oaths of Moment, Loken's loyalty, Luna Wolves",
    },
    "Stealth": {
        "themes": ["infiltration", "deception", "hidden", "covert"],
        "emotions": ["tension", "suspense"],
        "genres": ["spy", "thriller", "noir"],
        "lore_resonance": "Alpha Legion, Alpharius, hidden agendas",
    },
}

# Book Bridge Indicators (maps literary elements to bridges)
BOOK_BRIDGE_INDICATORS = {
    "Precision": {
        "themes": ["strategy", "tactics", "logic", "systems", "engineering"],
        "genres": ["military sci-fi", "hard sci-fi", "technical thriller"],
        "authors": ["Andy Weir", "Isaac Asimov", "Michael Crichton"],
        "lore_resonance": "Iron Warriors, Perturabo's calculated siege craft",
    },
    "Resilience": {
        "themes": ["survival", "perseverance", "hope", "rebuilding"],
        "genres": ["post-apocalyptic", "survival", "epic fantasy"],
        "authors": ["Brandon Sanderson", "Cormac McCarthy"],
        "lore_resonance": "Imperial Fists, Siege of Terra, endurance",
    },
    "Fragility": {
        "themes": ["loss", "mortality", "memory", "grief", "vulnerability"],
        "genres": ["literary fiction", "tragedy", "memoir"],
        "authors": ["Kazuo Ishiguro", "Donna Tartt"],
        "lore_resonance": "Webway, shattered plans, irreversible loss",
    },
    "Corruption": {
        "themes": ["fall", "power", "temptation", "darkness", "descent"],
        "genres": ["dark fantasy", "horror", "psychological thriller"],
        "authors": ["H.P. Lovecraft", "Joe Abercrombie"],
        "lore_resonance": "Chaos corruption, Davin, moral descent",
    },
    "Loyalty": {
        "themes": ["duty", "honor", "oaths", "brotherhood", "service"],
        "genres": ["military fiction", "samurai", "knight fiction"],
        "authors": ["Dan Abnett", "Bernard Cornwell"],
        "lore_resonance": "Oaths of Moment, Luna Wolves, sworn duty",
    },
    "Stealth": {
        "themes": ["secrets", "espionage", "hidden", "subterfuge"],
        "genres": ["spy thriller", "mystery", "noir"],
        "authors": ["John le Carré", "Ian Fleming"],
        "lore_resonance": "Alpha Legion, hidden identities, deception",
    },
}

# Warhammer 40K/Horus Heresy specific mappings
LORE_BRIDGE_MAPPINGS = {
    # Primarchs
    "Horus": ["Corruption"],
    "Perturabo": ["Precision"],
    "Dorn": ["Resilience"],
    "Rogal Dorn": ["Resilience"],
    "Magnus": ["Fragility"],
    "Alpharius": ["Stealth"],
    "Omegon": ["Stealth"],
    "Lorgar": ["Corruption"],
    "Sanguinius": ["Loyalty"],
    "Fulgrim": ["Corruption"],
    "Mortarion": ["Corruption"],
    "Angron": ["Fragility"],  # broken by the Nails

    # Legions
    "Iron Warriors": ["Precision"],
    "Imperial Fists": ["Resilience"],
    "Alpha Legion": ["Stealth"],
    "Luna Wolves": ["Loyalty"],
    "Sons of Horus": ["Corruption"],
    "Word Bearers": ["Corruption"],
    "Death Guard": ["Resilience", "Corruption"],
    "Thousand Sons": ["Fragility"],
    "Blood Angels": ["Loyalty"],
    "Ultramarines": ["Resilience"],

    # Events
    "Siege of Terra": ["Resilience"],
    "Davin": ["Corruption"],
    "Isstvan": ["Corruption", "Fragility"],
    "Prospero": ["Fragility"],
    "Webway": ["Fragility"],
    "Iron Cage": ["Precision", "Resilience"],
}


# ==============================================================================
# TYPED RESULTS
# ==============================================================================

class CollectionTags(TypedDict):
    """Collection-specific tags (Tier 3)."""
    domain: List[str]
    thematic_weight: List[str]
    function: List[str]
    perspective: List[str]


class TaxonomyExtractionResult(TypedDict):
    """Complete taxonomy extraction result for any content type."""
    content_type: str
    bridge_attributes: List[str]
    collection_tags: CollectionTags
    tactical_tags: List[str]
    episodic_associations: List[str]
    dimensions: Dict[str, List[str]]
    confidence: float
    raw_matches: Dict[str, Any]


# ==============================================================================
# CORE EXTRACTION FUNCTIONS
# ==============================================================================

def extract_taxonomy_features(
    content_type: ContentType,
    title: str = "",
    artist: str = "",
    author: str = "",
    genre: str = "",
    tags: Optional[List[str]] = None,
    emotion: str = "",
    description: str = "",
    audio_features: Optional[Dict[str, Any]] = None,
) -> TaxonomyExtractionResult:
    """
    Extract taxonomy features from any content type.

    This is the unified entry point for all content types. It routes to the
    appropriate extractor based on content_type.

    Args:
        content_type: Type of content (music, movie, book, etc.)
        title: Content title
        artist: Artist/performer name (for music/video)
        author: Author name (for books)
        genre: Genre or category
        tags: Additional tags/keywords
        emotion: Primary emotion/mood
        description: Extended description or synopsis
        audio_features: Audio feature dict (for music with MIR analysis)

    Returns:
        TaxonomyExtractionResult with bridge_attributes, collection_tags,
        tactical_tags, episodic_associations, dimensions, and confidence.
    """
    tags = tags or []
    combined_text = _build_combined_text(title, artist, author, genre, tags, emotion, description)

    if content_type == ContentType.MUSIC:
        return _extract_music_features(title, artist, tags, audio_features, combined_text)
    elif content_type == ContentType.MOVIE:
        return _extract_movie_features(title, tags, emotion, combined_text)
    elif content_type in (ContentType.BOOK, ContentType.AUDIOBOOK):
        return _extract_book_features(title, author, genre, tags, combined_text)
    elif content_type == ContentType.YOUTUBE:
        return _extract_youtube_features(title, artist, tags, combined_text)
    elif content_type == ContentType.LORE:
        return _extract_lore_features(title, tags, combined_text)
    elif content_type == ContentType.OPERATIONAL:
        return _extract_operational_features(title, tags, combined_text)
    elif content_type == ContentType.SECURITY:
        return _extract_security_features(title, tags, combined_text)
    else:
        # Default fallback
        return _extract_generic_features(content_type, combined_text)


def _build_combined_text(*args) -> str:
    """Build combined text from all inputs for pattern matching."""
    parts = []
    for arg in args:
        if isinstance(arg, str) and arg:
            parts.append(arg.lower())
        elif isinstance(arg, list):
            parts.extend(t.lower() for t in arg if t)
    return " ".join(parts)


def _extract_bridges_from_text(text: str, indicators: Dict[str, Dict]) -> Tuple[List[str], Dict[str, float]]:
    """Extract bridge attributes from text using indicators."""
    scores = {}
    text_lower = text.lower()

    for bridge, bridge_def in indicators.items():
        score = 0.0
        matches = 0

        # Check various indicator fields
        for field_name in ["indicators", "themes", "artists", "authors", "genres", "emotions"]:
            field_values = bridge_def.get(field_name, [])
            if isinstance(field_values, dict):
                field_values = list(field_values.keys())
            for indicator in field_values:
                if isinstance(indicator, str) and indicator.lower() in text_lower:
                    score += 1.0
                    matches += 1

        if matches > 0:
            scores[bridge] = score / max(len(indicators.get(bridge, {})), 1)

    # Get top bridges with significant scores
    threshold = 0.2
    bridges = [name for name, score in sorted(scores.items(), key=lambda x: -x[1]) if score >= threshold][:3]

    # If no strong matches, use best guess
    if not bridges and scores:
        bridges = [max(scores, key=scores.get)]

    return bridges, scores


def _check_lore_entities(text: str) -> List[str]:
    """Check for Warhammer 40K/Horus Heresy entities in text."""
    bridges = set()
    text_lower = text.lower()

    for entity, entity_bridges in LORE_BRIDGE_MAPPINGS.items():
        if entity.lower() in text_lower:
            bridges.update(entity_bridges)

    return list(bridges)


def _get_episodic_associations(bridges: List[str], text: str = "") -> List[str]:
    """Get episodic associations for bridges."""
    associations = []

    if _HMT_AVAILABLE:
        for episode_name, episode_data in EPISODIC_ASSOCIATIONS.items():
            episode_bridge = episode_data.get("bridge", "")
            if episode_bridge in bridges:
                if episode_name not in associations:
                    associations.append(episode_name)
                continue

            # Match by music indicators in text
            for indicator in episode_data.get("music_indicators", []):
                if indicator.lower() in text.lower():
                    if episode_name not in associations:
                        associations.append(episode_name)
                    break
    else:
        # Fallback episode map
        episode_map = {
            "Precision": ["Iron_Cage", "Horus_Primarch"],
            "Resilience": ["Siege_of_Terra", "Emperor_Throne"],
            "Fragility": ["Webway_Collapse", "Sanguinius_Fall"],
            "Corruption": ["Davin_Corruption", "Isstvan_Betrayal"],
            "Loyalty": ["Mournival_Oath"],
            "Stealth": ["Alpharius_Deception"],
        }
        for bridge in bridges:
            associations.extend(episode_map.get(bridge, []))

    return list(set(associations))


# ==============================================================================
# CONTENT-SPECIFIC EXTRACTORS
# ==============================================================================

def _extract_music_features(
    title: str,
    artist: str,
    tags: List[str],
    audio_features: Optional[Dict],
    combined_text: str,
) -> TaxonomyExtractionResult:
    """Extract features for music content."""
    # Use canonical HMT verifier if available
    if _HMT_AVAILABLE:
        verifier = create_music_verifier()
        music_entry = {"title": title, "artist": artist, "channel": artist, "tags": tags}
        hmt_features = verifier.extract_features(music_entry)

        bridge_attributes = hmt_features.get("bridge_attributes", [])
        dimensions = hmt_features.get("dimensions", {})
        confidence = hmt_features.get("confidence", 0.5)
        tactical_tags = hmt_features.get("tactical_tags", [])
    else:
        # Fallback extraction
        bridge_attributes, _ = _extract_bridges_from_text(combined_text, MUSIC_BRIDGE_INDICATORS or {})
        dimensions = {}
        confidence = 0.3
        tactical_tags = ["Score", "Recall"]

    # Check for lore entities
    lore_bridges = _check_lore_entities(combined_text)
    bridge_attributes = list(set(bridge_attributes + lore_bridges))[:3]

    # Get episodic associations
    episodic = _get_episodic_associations(bridge_attributes, combined_text)

    return TaxonomyExtractionResult(
        content_type=ContentType.MUSIC.value,
        bridge_attributes=bridge_attributes,
        collection_tags=CollectionTags(
            domain=dimensions.get("domain", []),
            thematic_weight=dimensions.get("thematic_weight", []),
            function=dimensions.get("function", ["Contemplation"]),
            perspective=[],
        ),
        tactical_tags=tactical_tags,
        episodic_associations=episodic,
        dimensions=dimensions,
        confidence=confidence,
        raw_matches={},
    )


def _extract_movie_features(
    title: str,
    tags: List[str],
    emotion: str,
    combined_text: str,
) -> TaxonomyExtractionResult:
    """Extract features for movie content."""
    # Extract bridges from movie indicators
    bridge_attributes, scores = _extract_bridges_from_text(combined_text, MOVIE_BRIDGE_INDICATORS)

    # Check for lore entities
    lore_bridges = _check_lore_entities(combined_text)
    bridge_attributes = list(set(bridge_attributes + lore_bridges))[:3]

    # Map emotion to bridge
    emotion_bridge_map = {
        "rage": "Corruption",
        "anger": "Corruption",
        "sorrow": "Fragility",
        "regret": "Fragility",
        "camaraderie": "Loyalty",
        "triumphant": "Resilience",
        "dread": "Corruption",
        "tension": "Stealth",
    }
    if emotion and emotion.lower() in emotion_bridge_map:
        bridge = emotion_bridge_map[emotion.lower()]
        if bridge not in bridge_attributes:
            bridge_attributes.append(bridge)

    # Determine function
    function = "Contemplation"
    if "Resilience" in bridge_attributes:
        function = "Battle"
    elif "Fragility" in bridge_attributes:
        function = "Mourning"
    elif "Corruption" in bridge_attributes:
        function = "Dread"
    elif "Stealth" in bridge_attributes:
        function = "Tension"

    # Get episodic associations
    episodic = _get_episodic_associations(bridge_attributes, combined_text)

    return TaxonomyExtractionResult(
        content_type=ContentType.MOVIE.value,
        bridge_attributes=bridge_attributes[:3],
        collection_tags=CollectionTags(
            domain=[],
            thematic_weight=[emotion.capitalize()] if emotion else [],
            function=[function],
            perspective=["Visual"],
        ),
        tactical_tags=["Score", "Immerse"],
        episodic_associations=episodic,
        dimensions={},
        confidence=max(scores.values()) if scores else 0.3,
        raw_matches={"emotion": emotion, "tags": tags},
    )


def _extract_book_features(
    title: str,
    author: str,
    genre: str,
    tags: List[str],
    combined_text: str,
) -> TaxonomyExtractionResult:
    """Extract features for book/audiobook content."""
    # Extract bridges from book indicators
    bridge_attributes, scores = _extract_bridges_from_text(combined_text, BOOK_BRIDGE_INDICATORS)

    # Check for lore entities
    lore_bridges = _check_lore_entities(combined_text)
    bridge_attributes = list(set(bridge_attributes + lore_bridges))[:3]

    # Warhammer 40K / Horus Heresy detection
    is_wh40k = any(k in combined_text for k in ["warhammer", "40k", "40,000", "horus", "primarch", "astartes", "black library"])

    # Get episodic associations
    episodic = _get_episodic_associations(bridge_attributes, combined_text)

    # Determine domain
    domain = []
    if is_wh40k:
        domain.append("Lore")
    if genre:
        domain.append(genre)

    return TaxonomyExtractionResult(
        content_type=ContentType.BOOK.value,
        bridge_attributes=bridge_attributes[:3],
        collection_tags=CollectionTags(
            domain=domain,
            thematic_weight=[],
            function=["Study"] if is_wh40k else ["Entertainment"],
            perspective=["Literary"],
        ),
        tactical_tags=["Recall", "Invoke"] if is_wh40k else ["Recall"],
        episodic_associations=episodic,
        dimensions={},
        confidence=max(scores.values()) if scores else 0.3,
        raw_matches={"author": author, "genre": genre, "is_wh40k": is_wh40k},
    )


def _extract_youtube_features(
    title: str,
    channel: str,
    tags: List[str],
    combined_text: str,
) -> TaxonomyExtractionResult:
    """Extract features for YouTube content."""
    # Delegate to music extractor for music channels
    music_indicators = ["music", "song", "album", "track", "official video", "lyrics"]
    is_music = any(ind in combined_text for ind in music_indicators)

    if is_music:
        return _extract_music_features(title, channel, tags, None, combined_text)

    # Check for lore content
    lore_indicators = ["warhammer", "40k", "horus heresy", "lore", "luetin", "oculus imperia"]
    is_lore = any(ind in combined_text for ind in lore_indicators)

    if is_lore:
        return _extract_lore_features(title, tags, combined_text)

    # Default YouTube extraction
    bridge_attributes, scores = _extract_bridges_from_text(combined_text, MOVIE_BRIDGE_INDICATORS)
    episodic = _get_episodic_associations(bridge_attributes, combined_text)

    return TaxonomyExtractionResult(
        content_type=ContentType.YOUTUBE.value,
        bridge_attributes=bridge_attributes[:3],
        collection_tags=CollectionTags(
            domain=[],
            thematic_weight=[],
            function=["Education"],
            perspective=["Digital"],
        ),
        tactical_tags=["Recall"],
        episodic_associations=episodic,
        dimensions={},
        confidence=max(scores.values()) if scores else 0.3,
        raw_matches={"channel": channel},
    )


def _extract_lore_features(
    title: str,
    tags: List[str],
    combined_text: str,
) -> TaxonomyExtractionResult:
    """Extract features for Warhammer 40K lore content."""
    # Check for lore entities first
    bridge_attributes = _check_lore_entities(combined_text)

    # Use main verifier if available
    if _VERIFIER_AVAILABLE:
        verifier = HorusTaxonomyVerifier()
        features = verifier.extract_features(combined_text, collection="lore")
        if features.bridge_attributes:
            bridge_attributes = list(set(bridge_attributes + features.bridge_attributes))
        confidence = features.confidence
    else:
        confidence = 0.5 if bridge_attributes else 0.3

    bridge_attributes = bridge_attributes[:3]
    episodic = _get_episodic_associations(bridge_attributes, combined_text)

    return TaxonomyExtractionResult(
        content_type=ContentType.LORE.value,
        bridge_attributes=bridge_attributes,
        collection_tags=CollectionTags(
            domain=["Lore"],
            thematic_weight=[],
            function=["Study"],
            perspective=["Narrative"],
        ),
        tactical_tags=["Invoke", "Recall"],
        episodic_associations=episodic,
        dimensions={},
        confidence=confidence,
        raw_matches={"tags": tags},
    )


def _extract_operational_features(
    title: str,
    tags: List[str],
    combined_text: str,
) -> TaxonomyExtractionResult:
    """Extract features for operational/technical content."""
    if _VERIFIER_AVAILABLE:
        verifier = HorusTaxonomyVerifier()
        features = verifier.extract_features(combined_text, collection="operational")
        bridge_attributes = features.bridge_attributes
        tactical_tags = features.tactical_tags
        confidence = features.confidence
    else:
        bridge_attributes = []
        tactical_tags = []
        confidence = 0.3

        # Fallback operational extraction
        op_indicators = {
            "Resilience": ["error handling", "fault tolerance", "redundancy", "uptime"],
            "Fragility": ["technical debt", "legacy", "brittle", "single point"],
            "Corruption": ["memory leak", "state bug", "race condition"],
            "Precision": ["optimized", "efficient", "algorithmic"],
            "Loyalty": ["security", "auth", "encryption", "access control"],
        }
        for bridge, indicators in op_indicators.items():
            if any(ind in combined_text for ind in indicators):
                bridge_attributes.append(bridge)

    return TaxonomyExtractionResult(
        content_type=ContentType.OPERATIONAL.value,
        bridge_attributes=bridge_attributes[:3],
        collection_tags=CollectionTags(
            domain=["Code"],
            thematic_weight=[],
            function=["Fix"],
            perspective=["Technical"],
        ),
        tactical_tags=tactical_tags or ["Model"],
        episodic_associations=[],
        dimensions={},
        confidence=confidence,
        raw_matches={"tags": tags},
    )


def _extract_security_features(
    title: str,
    tags: List[str],
    combined_text: str,
) -> TaxonomyExtractionResult:
    """Extract features for SPARTA security content."""
    if _VERIFIER_AVAILABLE:
        verifier = HorusTaxonomyVerifier()
        features = verifier.extract_features(combined_text, collection="sparta")
        bridge_attributes = features.bridge_attributes
        tactical_tags = features.tactical_tags
        confidence = features.confidence
    else:
        bridge_attributes = []
        tactical_tags = []
        confidence = 0.3

        # Use tactical-to-conceptual mapping
        for tactical, bridge in TACTICAL_TO_CONCEPTUAL.items() if TACTICAL_TO_CONCEPTUAL else {}:
            if tactical.lower() in combined_text:
                bridge_attributes.append(bridge)
                tactical_tags.append(tactical)

    return TaxonomyExtractionResult(
        content_type=ContentType.SECURITY.value,
        bridge_attributes=list(set(bridge_attributes))[:3],
        collection_tags=CollectionTags(
            domain=["Security"],
            thematic_weight=[],
            function=["Defend"],
            perspective=["Risk"],
        ),
        tactical_tags=list(set(tactical_tags)) or ["Detect"],
        episodic_associations=[],
        dimensions={},
        confidence=confidence,
        raw_matches={"tags": tags},
    )


def _extract_generic_features(
    content_type: ContentType,
    combined_text: str,
) -> TaxonomyExtractionResult:
    """Fallback extractor for unknown content types."""
    bridge_attributes = _check_lore_entities(combined_text)
    episodic = _get_episodic_associations(bridge_attributes, combined_text)

    return TaxonomyExtractionResult(
        content_type=content_type.value if isinstance(content_type, ContentType) else str(content_type),
        bridge_attributes=bridge_attributes[:3],
        collection_tags=CollectionTags(
            domain=[],
            thematic_weight=[],
            function=[],
            perspective=[],
        ),
        tactical_tags=["Recall"],
        episodic_associations=episodic,
        dimensions={},
        confidence=0.3,
        raw_matches={},
    )


# ==============================================================================
# UTILITY FUNCTIONS
# ==============================================================================

def get_bridge_attributes(text: str, content_type: Optional[ContentType] = None) -> List[str]:
    """
    Quick utility to get just bridge attributes from text.

    Args:
        text: Text to analyze
        content_type: Optional content type for specialized extraction

    Returns:
        List of Bridge Attribute names
    """
    if content_type:
        result = extract_taxonomy_features(content_type, title=text)
        return result["bridge_attributes"]

    # Check for lore entities first
    bridges = _check_lore_entities(text)

    # Try all indicator sets
    for indicators in [MOVIE_BRIDGE_INDICATORS, BOOK_BRIDGE_INDICATORS]:
        found, _ = _extract_bridges_from_text(text, indicators)
        bridges.extend(found)

    if _HMT_AVAILABLE:
        found, _ = _extract_bridges_from_text(text, MUSIC_BRIDGE_INDICATORS)
        bridges.extend(found)

    return list(set(bridges))[:3]


def get_episodic_associations(bridges: List[str], text: str = "") -> List[str]:
    """
    Get episodic associations for given bridges.

    Args:
        bridges: List of Bridge Attribute names
        text: Optional text for additional matching

    Returns:
        List of episode names (e.g., "Siege_of_Terra", "Davin_Corruption")
    """
    return _get_episodic_associations(bridges, text)


def create_verifier(content_type: ContentType = ContentType.LORE):
    """
    Create appropriate taxonomy verifier for content type.

    Args:
        content_type: Type of content to verify

    Returns:
        Verifier instance or None if not available
    """
    if content_type == ContentType.MUSIC and _HMT_AVAILABLE:
        return create_music_verifier()
    elif _VERIFIER_AVAILABLE:
        return HorusTaxonomyVerifier()
    return None


def is_taxonomy_available() -> Dict[str, bool]:
    """Check which taxonomy components are available."""
    return {
        "hmt": _HMT_AVAILABLE,
        "verifier": _VERIFIER_AVAILABLE,
        "music_indicators": bool(MUSIC_BRIDGE_INDICATORS),
        "episodic_associations": bool(EPISODIC_ASSOCIATIONS),
        "bridge_attributes": bool(BRIDGE_ATTRIBUTES),
    }


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
