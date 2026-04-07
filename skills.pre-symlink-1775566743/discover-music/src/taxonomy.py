"""
Music taxonomy: delegates bridge extraction to common.taxonomy,
keeps MusicBrainz-specific tag mappings locally.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Set

# Import common taxonomy
_SKILLS_DIR = str(Path(__file__).resolve().parent.parent.parent)
if _SKILLS_DIR not in sys.path:
    sys.path.insert(0, _SKILLS_DIR)

try:
    from common.taxonomy import get_bridge_attributes, get_episodic_associations, ContentType
    _COMMON_AVAILABLE = True
except ImportError:
    _COMMON_AVAILABLE = False

# === MusicBrainz-specific data (kept local) ===

BRIDGE_TO_TAGS: Dict[str, List[str]] = {
    "Precision": [
        "progressive metal", "math rock", "technical death metal",
        "djent", "progressive rock", "jazz fusion", "avant-garde",
        "experimental", "polyrhythm", "complex"
    ],
    "Resilience": [
        "epic metal", "power metal", "post-rock", "cinematic",
        "symphonic metal", "orchestral", "epic", "triumphant",
        "anthemic", "uplifting"
    ],
    "Fragility": [
        "dark folk", "acoustic", "slowcore", "sadcore", "folk",
        "singer-songwriter", "chamber", "intimate", "melancholic",
        "ethereal", "dream pop"
    ],
    "Corruption": [
        "industrial", "doom metal", "sludge metal", "dark ambient",
        "noise", "black metal", "death metal", "harsh noise",
        "dark", "heavy", "oppressive"
    ],
    "Loyalty": [
        "neofolk", "neoclassical", "world", "ritual ambient",
        "medieval", "traditional", "folk metal", "pagan",
        "ancestral", "heritage"
    ],
    "Stealth": [
        "drone", "dark ambient", "ambient", "minimalist",
        "atmospheric", "post-metal", "shoegaze", "subtle",
        "hypnotic", "trance"
    ],
}

BRIDGE_KEYWORDS: Dict[str, List[str]] = {
    "Precision": ["technical", "complex", "progressive", "virtuoso", "intricate", "mathematical", "precise", "calculated", "polyrhythmic", "jazz"],
    "Resilience": ["epic", "triumphant", "powerful", "anthemic", "soaring", "uplifting", "majestic", "heroic", "cinematic", "orchestral"],
    "Fragility": ["delicate", "intimate", "vulnerable", "melancholic", "tender", "acoustic", "quiet", "gentle", "emotional", "heartbreak"],
    "Corruption": ["dark", "heavy", "brutal", "sinister", "oppressive", "doom", "sludge", "industrial", "harsh", "extreme"],
    "Loyalty": ["traditional", "folk", "ancestral", "ritual", "ancient", "heritage", "pagan", "medieval", "tribal", "sacred"],
    "Stealth": ["ambient", "atmospheric", "drone", "subtle", "hypnotic", "minimalist", "ethereal", "spacious", "meditative", "trance"],
}


def extract_bridge_tags(tags: List[str], description: str = "", fast: bool = True) -> List[str]:
    """Extract bridge tags from music tags and description."""
    if _COMMON_AVAILABLE:
        text = f"{' '.join(tags)} {description}"
        return get_bridge_attributes(text, content_type=ContentType.MUSIC)

    # Fallback: local extraction
    bridges: Set[str] = set()
    tags_lower = [t.lower() for t in tags]
    for bridge, bridge_tags in BRIDGE_TO_TAGS.items():
        for bt in bridge_tags:
            if any(bt.lower() in t for t in tags_lower):
                bridges.add(bridge)
                break
    if description and fast:
        desc_lower = description.lower()
        for bridge, keywords in BRIDGE_KEYWORDS.items():
            if any(kw in desc_lower for kw in keywords):
                bridges.add(bridge)
    return list(bridges)


def get_tags_for_bridge(bridge: str) -> List[str]:
    """Get MusicBrainz tags for a bridge attribute."""
    return BRIDGE_TO_TAGS.get(bridge, [])


def build_taxonomy_output(results: List[dict], bridge_tags: List[str] = None, collection: str = "lore") -> dict:
    """Build taxonomy metadata for output."""
    if bridge_tags is None:
        all_bridges: Set[str] = set()
        for r in results:
            tags = r.get("tags", [])
            description = r.get("description", "") or r.get("disambiguation", "")
            all_bridges.update(extract_bridge_tags(tags, description))
        bridge_tags = list(all_bridges)

    domain = "World"
    if any(b in ["Resilience", "Loyalty", "Precision"] for b in bridge_tags):
        domain = "Imperium"
    elif any(b in ["Corruption", "Fragility"] for b in bridge_tags):
        domain = "Chaos"

    return {
        "bridge_tags": bridge_tags,
        "collection_tags": {"domain": domain, "function": "Revelation"},
        "confidence": 0.7 if bridge_tags else 0.3,
        "worth_remembering": len(bridge_tags) > 0,
    }
