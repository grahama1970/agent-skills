"""
Book taxonomy mappings for Federated Taxonomy integration.

Maps book subjects/genres to Bridge Attributes for cross-collection traversal.
Enables queries like "books matching Resilience bridge" which finds epic fantasy,
military fiction, and adventure novels.

Bridge Attributes (Tier 0):
- Precision: Calculated, methodical, technical content
- Resilience: Endurance, triumph, heroic content
- Fragility: Vulnerable, emotional, intimate content
- Corruption: Dark, morally complex, horrific content
- Loyalty: Honor, duty, tradition content
- Stealth: Hidden, mysterious, subtle content
"""

from typing import Dict, List, Set

# Bridge Attribute → OpenLibrary Subjects
BRIDGE_TO_SUBJECTS: Dict[str, List[str]] = {
    "Precision": [
        "hard science fiction", "technical thriller", "procedural",
        "mathematics", "philosophy", "logic", "physics",
        "scientific method", "engineering", "computer science"
    ],
    "Resilience": [
        "epic fantasy", "military fiction", "adventure",
        "survival", "heroic fantasy", "quest", "war fiction",
        "exploration", "mountaineering", "endurance"
    ],
    "Fragility": [
        "literary fiction", "poetry", "memoir", "psychological fiction",
        "tragedy", "coming of age", "domestic fiction",
        "intimate", "emotional", "introspective"
    ],
    "Corruption": [
        "dark fantasy", "horror", "grimdark", "cosmic horror",
        "dystopian", "gothic", "psychological horror",
        "lovecraftian", "apocalyptic", "nihilism"
    ],
    "Loyalty": [
        "historical fiction", "saga", "mythology", "war",
        "family saga", "dynasty", "chivalry", "knighthood",
        "ancient history", "tradition", "legacy"
    ],
    "Stealth": [
        "mystery", "espionage", "thriller", "psychological thriller",
        "noir", "detective", "spy fiction", "conspiracy",
        "crime fiction", "suspense"
    ],
}

# Keywords for fast bridge extraction from book descriptions
BRIDGE_KEYWORDS: Dict[str, List[str]] = {
    "Precision": [
        "meticulous", "calculated", "technical", "scientific",
        "logical", "mathematical", "precise", "methodical",
        "analytical", "systematic", "engineering"
    ],
    "Resilience": [
        "survive", "endure", "overcome", "triumph", "hero",
        "epic", "quest", "journey", "battle", "warrior",
        "persevere", "struggle", "adventure"
    ],
    "Fragility": [
        "vulnerable", "emotional", "intimate", "heartbreak",
        "tender", "sensitive", "fragile", "poignant",
        "melancholy", "introspective", "delicate"
    ],
    "Corruption": [
        "dark", "corrupt", "sinister", "evil", "twisted",
        "horror", "nightmare", "cursed", "damned", "possessed",
        "apocalyptic", "dystopian", "grim"
    ],
    "Loyalty": [
        "honor", "duty", "family", "oath", "loyal",
        "devotion", "allegiance", "sacrifice", "tradition",
        "legacy", "heritage", "dynasty"
    ],
    "Stealth": [
        "hidden", "secret", "mysterious", "shadow", "covert",
        "spy", "infiltrate", "conspiracy", "undercover",
        "detective", "investigation", "enigma"
    ],
}


def extract_bridge_tags(
    subjects: List[str],
    description: str = "",
    fast: bool = True
) -> List[str]:
    """
    Extract bridge tags from book subjects and description.

    Args:
        subjects: List of subject/genre names
        description: Book description
        fast: Use keyword extraction only

    Returns:
        List of matching bridge attribute names
    """
    bridges: Set[str] = set()
    subjects_lower = [s.lower() for s in subjects]

    # Match by subject
    for bridge, bridge_subjects in BRIDGE_TO_SUBJECTS.items():
        for bs in bridge_subjects:
            if any(bs.lower() in s for s in subjects_lower):
                bridges.add(bridge)
                break

    # Match by keywords in description
    if description and fast:
        desc_lower = description.lower()
        for bridge, keywords in BRIDGE_KEYWORDS.items():
            if any(kw in desc_lower for kw in keywords):
                bridges.add(bridge)

    return list(bridges)


def get_subjects_for_bridge(bridge: str) -> List[str]:
    """Get OpenLibrary subjects for a bridge attribute."""
    return BRIDGE_TO_SUBJECTS.get(bridge, [])


def build_taxonomy_output(
    results: List[dict],
    bridge_tags: List[str] = None,
    collection: str = "lore"
) -> dict:
    """
    Build taxonomy metadata for output.

    Args:
        results: List of book results
        bridge_tags: Explicit bridge tags to include
        collection: Taxonomy collection (lore, operational, sparta)

    Returns:
        Taxonomy dict with bridge_tags, collection_tags, confidence
    """
    # Aggregate bridges from all results if not provided
    if bridge_tags is None:
        all_bridges: Set[str] = set()
        for r in results:
            subjects = r.get("subjects", [])
            description = r.get("description", "")
            tags = extract_bridge_tags(subjects, description)
            all_bridges.update(tags)
        bridge_tags = list(all_bridges)

    # Determine collection tags based on dominant subjects
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
