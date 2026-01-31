"""
Music taxonomy mappings for Federated Taxonomy integration.

Maps music genres/tags to Bridge Attributes for cross-collection traversal.
Enables queries like "music matching Corruption bridge" which finds industrial,
doom metal, and dark ambient artists.

Bridge Attributes (Tier 0):
- Precision: Technical, complex, calculated music
- Resilience: Epic, powerful, triumphant music
- Fragility: Delicate, emotional, vulnerable music
- Corruption: Dark, heavy, unsettling music
- Loyalty: Traditional, ritualistic, heritage music
- Stealth: Atmospheric, subtle, ambient music
"""

from typing import Dict, List, Set

# Bridge Attribute → MusicBrainz Tags
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

# Keywords for fast bridge extraction from artist descriptions/bios
BRIDGE_KEYWORDS: Dict[str, List[str]] = {
    "Precision": [
        "technical", "complex", "progressive", "virtuoso", "intricate",
        "mathematical", "precise", "calculated", "polyrhythmic", "jazz"
    ],
    "Resilience": [
        "epic", "triumphant", "powerful", "anthemic", "soaring",
        "uplifting", "majestic", "heroic", "cinematic", "orchestral"
    ],
    "Fragility": [
        "delicate", "intimate", "vulnerable", "melancholic", "tender",
        "acoustic", "quiet", "gentle", "emotional", "heartbreak"
    ],
    "Corruption": [
        "dark", "heavy", "brutal", "sinister", "oppressive",
        "doom", "sludge", "industrial", "harsh", "extreme"
    ],
    "Loyalty": [
        "traditional", "folk", "ancestral", "ritual", "ancient",
        "heritage", "pagan", "medieval", "tribal", "sacred"
    ],
    "Stealth": [
        "ambient", "atmospheric", "drone", "subtle", "hypnotic",
        "minimalist", "ethereal", "spacious", "meditative", "trance"
    ],
}


def extract_bridge_tags(
    tags: List[str],
    description: str = "",
    fast: bool = True
) -> List[str]:
    """
    Extract bridge tags from music tags and description.

    Args:
        tags: List of genre/style tags
        description: Artist/album description or bio
        fast: Use keyword extraction only

    Returns:
        List of matching bridge attribute names
    """
    bridges: Set[str] = set()
    tags_lower = [t.lower() for t in tags]

    # Match by tag
    for bridge, bridge_tags in BRIDGE_TO_TAGS.items():
        for bt in bridge_tags:
            if any(bt.lower() in t for t in tags_lower):
                bridges.add(bridge)
                break

    # Match by keywords in description
    if description and fast:
        desc_lower = description.lower()
        for bridge, keywords in BRIDGE_KEYWORDS.items():
            if any(kw in desc_lower for kw in keywords):
                bridges.add(bridge)

    return list(bridges)


def get_tags_for_bridge(bridge: str) -> List[str]:
    """Get MusicBrainz tags for a bridge attribute."""
    return BRIDGE_TO_TAGS.get(bridge, [])


def build_taxonomy_output(
    results: List[dict],
    bridge_tags: List[str] = None,
    collection: str = "lore"
) -> dict:
    """
    Build taxonomy metadata for output.

    Args:
        results: List of artist/recording results
        bridge_tags: Explicit bridge tags to include
        collection: Taxonomy collection (lore, operational, sparta)

    Returns:
        Taxonomy dict with bridge_tags, collection_tags, confidence
    """
    # Aggregate bridges from all results if not provided
    if bridge_tags is None:
        all_bridges: Set[str] = set()
        for r in results:
            tags = r.get("tags", [])
            description = r.get("description", "") or r.get("disambiguation", "")
            extracted = extract_bridge_tags(tags, description)
            all_bridges.update(extracted)
        bridge_tags = list(all_bridges)

    # Determine collection tags based on dominant styles
    domain = "World"  # Default for lore
    function = "Revelation"  # Discovery is about revealing new content

    if any(b in ["Resilience", "Loyalty"] for b in bridge_tags):
        domain = "Imperium"
    elif any(b in ["Corruption", "Fragility"] for b in bridge_tags):
        domain = "Chaos"
    elif "Precision" in bridge_tags:
        domain = "Imperium"

    return {
        "bridge_tags": bridge_tags,
        "collection_tags": {
            "domain": domain,
            "function": function,
        },
        "confidence": 0.7 if bridge_tags else 0.3,
        "worth_remembering": len(bridge_tags) > 0,
    }
