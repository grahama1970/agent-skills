"""
Book taxonomy: delegates bridge extraction to common.taxonomy,
keeps OpenLibrary-specific subject mappings locally.
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

# === OpenLibrary-specific data (kept local) ===

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

BRIDGE_KEYWORDS: Dict[str, List[str]] = {
    "Precision": ["meticulous", "calculated", "technical", "scientific", "logical", "mathematical", "precise", "methodical", "analytical", "systematic"],
    "Resilience": ["survive", "endure", "overcome", "triumph", "hero", "epic", "quest", "journey", "battle", "warrior", "persevere"],
    "Fragility": ["vulnerable", "emotional", "intimate", "heartbreak", "tender", "sensitive", "fragile", "poignant", "melancholy", "introspective"],
    "Corruption": ["dark", "corrupt", "sinister", "evil", "twisted", "horror", "nightmare", "cursed", "damned", "possessed", "apocalyptic"],
    "Loyalty": ["honor", "duty", "family", "oath", "loyal", "devotion", "allegiance", "sacrifice", "tradition", "legacy", "heritage"],
    "Stealth": ["hidden", "secret", "mysterious", "shadow", "covert", "spy", "infiltrate", "conspiracy", "undercover", "detective"],
}


def extract_bridge_tags(subjects: List[str], description: str = "", fast: bool = True) -> List[str]:
    """Extract bridge tags from book subjects and description."""
    if _COMMON_AVAILABLE:
        text = f"{' '.join(subjects)} {description}"
        return get_bridge_attributes(text, content_type=ContentType.BOOK)

    # Fallback: local extraction
    bridges: Set[str] = set()
    subjects_lower = [s.lower() for s in subjects]
    for bridge, bridge_subjects in BRIDGE_TO_SUBJECTS.items():
        for bs in bridge_subjects:
            if any(bs.lower() in s for s in subjects_lower):
                bridges.add(bridge)
                break
    if description and fast:
        desc_lower = description.lower()
        for bridge, keywords in BRIDGE_KEYWORDS.items():
            if any(kw in desc_lower for kw in keywords):
                bridges.add(bridge)
    return list(bridges)


def get_subjects_for_bridge(bridge: str) -> List[str]:
    """Get OpenLibrary subjects for a bridge attribute."""
    return BRIDGE_TO_SUBJECTS.get(bridge, [])


def build_taxonomy_output(results: List[dict], bridge_tags: List[str] = None, collection: str = "lore") -> dict:
    """Build taxonomy metadata for output."""
    if bridge_tags is None:
        all_bridges: Set[str] = set()
        for r in results:
            subjects = r.get("subjects", [])
            description = r.get("description", "")
            all_bridges.update(extract_bridge_tags(subjects, description))
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
