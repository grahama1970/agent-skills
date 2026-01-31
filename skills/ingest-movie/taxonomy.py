#!/usr/bin/env python3
"""
Movie Ingest Skill - Taxonomy Integration

Bridges the existing emotion/archetype system to the Federated Taxonomy for
multi-hop graph traversal in /memory.

Maps:
- Movie emotions (rage, anger, sorrow, regret, camaraderie, command) → Bridge Attributes
- Subtitle tags → Bridge Attributes
- Movie scenes → Episodic Associations (Horus lore)

This enables queries like:
- "Find movies that resonate with Siege of Terra" → Resilience bridge
- "Find camaraderie scenes like Luna Wolves brotherhood" → Loyalty bridge
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import common taxonomy module
_COMMON_PATH = Path(__file__).parent.parent / "common"
if str(_COMMON_PATH) not in sys.path:
    sys.path.insert(0, str(_COMMON_PATH))

# Use importlib to avoid circular import with same-named local file
import importlib.util
_spec = importlib.util.spec_from_file_location("common_taxonomy", _COMMON_PATH / "taxonomy.py")
_common_taxonomy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_common_taxonomy)

ContentType = _common_taxonomy.ContentType
TaxonomyExtractionResult = _common_taxonomy.TaxonomyExtractionResult
extract_taxonomy_features = _common_taxonomy.extract_taxonomy_features
get_bridge_attributes = _common_taxonomy.get_bridge_attributes
get_episodic_associations = _common_taxonomy.get_episodic_associations
MOVIE_BRIDGE_INDICATORS = _common_taxonomy.MOVIE_BRIDGE_INDICATORS

from config import (
    VALID_EMOTIONS,
    TAG_TO_EMOTION,
    HORUS_ARCHETYPE_MAP,
    EMOTION_DIMENSIONS,
)


# ==============================================================================
# EMOTION → BRIDGE ATTRIBUTE MAPPING
# ==============================================================================

# Maps Horus ToM emotions to Bridge Attributes
EMOTION_TO_BRIDGE = {
    "rage": ["Corruption"],  # Explosive fury, Davin-adjacent trauma
    "anger": ["Precision", "Corruption"],  # Cold, calculated (Iron Warriors + Corruption)
    "sorrow": ["Fragility"],  # Loss, grief, broken dreams (Magnus's Folly)
    "regret": ["Fragility"],  # Strategic error, irreversible loss
    "camaraderie": ["Loyalty"],  # Brotherhood, warrior bond (Luna Wolves)
    "command": ["Resilience", "Loyalty"],  # Leadership, protection (Dorn, Horus pre-corruption)
}

# Maps subtitle tags to Bridge Attributes
TAG_TO_BRIDGE = {
    # Rage tags → Corruption
    "rage": "Corruption",
    "rage_candidate": "Corruption",
    # Anger tags → Corruption/Precision
    "anger": "Corruption",
    "anger_candidate": "Corruption",
    "shout": "Corruption",
    # Sorrow tags → Fragility
    "cry": "Fragility",
    "sob": "Fragility",
    "sigh": "Fragility",
    "whisper": "Fragility",
    "whisper_candidate": "Fragility",
    "breath": "Fragility",
    # Camaraderie tags → Loyalty
    "laugh": "Loyalty",
}

# Trauma equivalents from HORUS_ARCHETYPE_MAP → Episodic associations
TRAUMA_TO_EPISODE = {
    "sanguinius": ["Sanguinius_Fall", "Siege_of_Terra"],
    "emperor": ["Emperor_Throne", "Siege_of_Terra"],
    "davin": ["Davin_Corruption", "Horus_Primarch"],
    None: [],  # No trauma = no episode association
}


# ==============================================================================
# EXTRACTION FUNCTIONS
# ==============================================================================

def extract_movie_taxonomy(
    title: str,
    emotion: Optional[str] = None,
    tags: Optional[List[str]] = None,
    description: str = "",
) -> TaxonomyExtractionResult:
    """
    Extract taxonomy features from a movie/scene.

    Uses both the common taxonomy extractor and movie-specific mappings.

    Args:
        title: Movie title
        emotion: Primary emotion (rage, anger, sorrow, regret, camaraderie, command)
        tags: Subtitle tags extracted from scene
        description: Scene description or synopsis

    Returns:
        TaxonomyExtractionResult with bridge_attributes, episodic_associations, etc.
    """
    tags = tags or []

    # Start with common taxonomy extraction
    result = extract_taxonomy_features(
        content_type=ContentType.MOVIE,
        title=title,
        tags=tags,
        emotion=emotion or "",
        description=description,
    )

    # Enhance with emotion-specific bridges
    bridge_attributes = list(result["bridge_attributes"])

    if emotion and emotion.lower() in EMOTION_TO_BRIDGE:
        for bridge in EMOTION_TO_BRIDGE[emotion.lower()]:
            if bridge not in bridge_attributes:
                bridge_attributes.append(bridge)

    # Enhance with tag-specific bridges
    for tag in tags:
        tag_lower = tag.lower()
        if tag_lower in TAG_TO_BRIDGE:
            bridge = TAG_TO_BRIDGE[tag_lower]
            if bridge not in bridge_attributes:
                bridge_attributes.append(bridge)

    bridge_attributes = bridge_attributes[:3]  # Max 3

    # Get episodic associations from Horus archetype trauma equivalents
    episodic = list(result["episodic_associations"])
    if emotion and emotion.lower() in HORUS_ARCHETYPE_MAP:
        trauma = HORUS_ARCHETYPE_MAP[emotion.lower()].get("trauma_equivalent")
        for ep in TRAUMA_TO_EPISODE.get(trauma, []):
            if ep not in episodic:
                episodic.append(ep)

    # Also get episodic from bridges
    for ep in get_episodic_associations(bridge_attributes, f"{title} {description}"):
        if ep not in episodic:
            episodic.append(ep)

    # Build enhanced result
    return TaxonomyExtractionResult(
        content_type=ContentType.MOVIE.value,
        bridge_attributes=bridge_attributes,
        collection_tags=result["collection_tags"],
        tactical_tags=["Score", "Immerse"],
        episodic_associations=episodic,
        dimensions=result["dimensions"],
        confidence=result["confidence"],
        raw_matches={
            "emotion": emotion,
            "tags": tags,
            "archetype": HORUS_ARCHETYPE_MAP.get(emotion.lower()) if emotion else None,
        },
    )


def get_bridges_from_tags(tags: List[str]) -> List[str]:
    """
    Get Bridge Attributes from subtitle tags.

    Args:
        tags: List of subtitle tags (cry, laugh, shout, etc.)

    Returns:
        List of Bridge Attribute names
    """
    bridges = set()
    for tag in tags:
        tag_lower = tag.lower()
        if tag_lower in TAG_TO_BRIDGE:
            bridges.add(TAG_TO_BRIDGE[tag_lower])
    return list(bridges)


def get_bridges_from_emotion(emotion: str) -> List[str]:
    """
    Get Bridge Attributes from a Horus ToM emotion.

    Args:
        emotion: Emotion name (rage, anger, sorrow, regret, camaraderie, command)

    Returns:
        List of Bridge Attribute names
    """
    return EMOTION_TO_BRIDGE.get(emotion.lower(), [])


def enrich_scene_with_taxonomy(scene: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enrich a movie scene dict with taxonomy features.

    Args:
        scene: Scene dict with fields like:
            - title: Movie title
            - emotion: Primary emotion
            - tags: Subtitle tags
            - start: Start time
            - end: End time
            - text: Subtitle text

    Returns:
        Same scene dict with added taxonomy fields:
            - bridge_attributes
            - episodic_associations
            - taxonomy_confidence
    """
    result = extract_movie_taxonomy(
        title=scene.get("title", ""),
        emotion=scene.get("emotion"),
        tags=scene.get("tags", []),
        description=scene.get("text", ""),
    )

    scene["bridge_attributes"] = result["bridge_attributes"]
    scene["episodic_associations"] = result["episodic_associations"]
    scene["taxonomy_confidence"] = result["confidence"]

    return scene


def get_archetype_bridge_mapping() -> Dict[str, Dict[str, Any]]:
    """
    Get the full archetype to bridge mapping for reference.

    Returns:
        Dict mapping emotions to their bridge attributes and Horus archetypes.
    """
    result = {}
    for emotion in VALID_EMOTIONS:
        archetype = HORUS_ARCHETYPE_MAP.get(emotion, {})
        result[emotion] = {
            "bridges": EMOTION_TO_BRIDGE.get(emotion, []),
            "archetype": archetype.get("primary_archetype"),
            "actor_model": archetype.get("actor_model"),
            "trauma_equivalent": archetype.get("trauma_equivalent"),
            "voice_tone": archetype.get("voice_tone"),
            "dimensions": EMOTION_DIMENSIONS.get(emotion, {}),
        }
    return result


# ==============================================================================
# MEMORY FORMAT CONVERSION
# ==============================================================================

def scene_to_memory_format(scene: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert a scene dict to memory-compatible format.

    Adds proper taxonomy fields for /memory sync.

    Args:
        scene: Scene dict (enriched with taxonomy)

    Returns:
        Dict ready for memory.learn()
    """
    # Ensure taxonomy enrichment
    if "bridge_attributes" not in scene:
        scene = enrich_scene_with_taxonomy(scene)

    return {
        "category": "movie",
        "title": scene.get("title", "Unknown"),
        "content": scene.get("text", ""),
        "bridge_attributes": scene.get("bridge_attributes", []),
        "episodic_associations": scene.get("episodic_associations", []),
        "collection_tags": {
            "emotion": scene.get("emotion"),
            "tags": scene.get("tags", []),
            "archetype": scene.get("raw_matches", {}).get("archetype", {}).get("primary_archetype"),
        },
        "metadata": {
            "start": scene.get("start"),
            "end": scene.get("end"),
            "duration": scene.get("duration"),
        },
        "confidence": scene.get("taxonomy_confidence", 0.5),
    }


# ==============================================================================
# EXPORTS
# ==============================================================================

__all__ = [
    "extract_movie_taxonomy",
    "get_bridges_from_tags",
    "get_bridges_from_emotion",
    "enrich_scene_with_taxonomy",
    "get_archetype_bridge_mapping",
    "scene_to_memory_format",
    "EMOTION_TO_BRIDGE",
    "TAG_TO_BRIDGE",
    "TRAUMA_TO_EPISODE",
]
