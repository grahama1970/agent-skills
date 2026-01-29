"""
Horus Lore Ingest - Configuration Module
Entity lists, constants, and environment variables for Warhammer 40k lore ingestion.
"""
import os
import re
from typing import Any

# Load environment
try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True))
except ImportError:
    pass


# =============================================================================
# Warhammer 40k Entity Lists (Rule-Based Extraction)
# =============================================================================

ENTITIES: dict[str, list[str]] = {
    "primarchs": [
        "Horus", "Horus Lupercal", "Lupercal",
        "Sanguinius", "Fulgrim", "Angron", "Mortarion", "Magnus", "Magnus the Red",
        "Perturabo", "Lorgar", "Konrad Curze", "Night Haunter", "Alpharius", "Omegon",
        "Lion El'Jonson", "Lion", "Jaghatai Khan", "Khan", "Leman Russ", "Russ",
        "Rogal Dorn", "Dorn", "Roboute Guilliman", "Guilliman", "Vulkan",
        "Corax", "Ferrus Manus", "Ferrus",
    ],
    "emperor": [
        "Emperor", "Master of Mankind", "God-Emperor", "the Emperor",
    ],
    "chaos_gods": [
        "Khorne", "Nurgle", "Tzeentch", "Slaanesh", "Chaos", "Chaos Gods",
        "Blood God", "Plague Father", "Changer of Ways", "Prince of Pleasure",
    ],
    "key_characters": [
        "Malcador", "Malcador the Sigillite", "Sigillite",
        "Erebus", "Kor Phaeron", "Luther", "Typhon", "Typhus",
        "Abaddon", "Loken", "Garviel Loken", "Torgaddon", "Tarik Torgaddon",
        "Sejanus", "Haster Sejanus", "Little Horus", "Aximand",
        "Sigismund", "Valdor", "Constantin Valdor",
        "Euphrati Keeler", "Keeler", "Kyril Sindermann",
        "Maloghurst", "the Twisted",
    ],
    "legions": [
        "Luna Wolves", "Sons of Horus", "Black Legion",
        "World Eaters", "Death Guard", "Emperor's Children", "Thousand Sons",
        "Word Bearers", "Night Lords", "Iron Warriors", "Alpha Legion",
        "Dark Angels", "White Scars", "Space Wolves", "Imperial Fists",
        "Blood Angels", "Iron Hands", "Ultramarines", "Salamanders", "Raven Guard",
        "Custodes", "Custodian Guard", "Sisters of Silence",
    ],
    "locations": [
        "Terra", "Holy Terra", "Earth", "Throne Room", "Golden Throne",
        "Davin", "Davin's moon", "Serpent Lodge", "Lodge",
        "Isstvan", "Isstvan III", "Isstvan V", "Istvaan",
        "Molech", "Calth", "Prospero", "Caliban",
        "Ullanor", "Murder", "Sixty-Three Nineteen",
        "Eye of Terror", "Warp", "Immaterium", "Webway",
        "Vengeful Spirit", "Horus's flagship",
    ],
    "events": [
        "Great Crusade", "Horus Heresy", "Heresy",
        "Siege of Terra", "Siege", "Final Battle",
        "Drop Site Massacre", "Betrayal at Isstvan",
        "Burning of Prospero", "Razing of Prospero",
        "Battle of Molech", "Webway War",
        "Triumph at Ullanor",
    ],
    "concepts": [
        "Warmaster", "War Master", "Primarch",
        "Astartes", "Space Marine", "Space Marines", "Legiones Astartes",
        "Imperial Truth", "Lectitio Divinitatus", "Imperial Cult",
        "Remembrancer", "Iterator",
        "Mournival", "Warrior Lodge",
        "gene-seed", "geneseed",
    ],
}

# Flatten for quick lookup
ALL_ENTITIES: dict[str, dict[str, str]] = {}
for category, names in ENTITIES.items():
    for name in names:
        ALL_ENTITIES[name.lower()] = {"name": name, "category": category}


# =============================================================================
# Entity Extraction Functions
# =============================================================================

def extract_entities(text: str) -> list[dict[str, str]]:
    """Extract known Warhammer 40k entities from text (rule-based, no LLM)."""
    found: dict[str, str] = {}
    text_lower = text.lower()

    for entity_lower, info in ALL_ENTITIES.items():
        # Word boundary check to avoid partial matches
        pattern = r'\b' + re.escape(entity_lower) + r'\b'
        if re.search(pattern, text_lower):
            # Use canonical name as key to dedupe
            found[info["name"]] = info["category"]

    return [{"name": name, "category": cat} for name, cat in found.items()]


def extract_entity_names(text: str) -> list[str]:
    """Extract just entity names (for indexing)."""
    return [e["name"] for e in extract_entities(text)]


# =============================================================================
# Important Entity Categories (for edge creation)
# =============================================================================

IMPORTANT_ENTITY_CATEGORIES: set[str] = {
    "primarchs", "emperor", "chaos_gods", "key_characters", "events", "locations"
}


# =============================================================================
# Escape/Trauma Keywords (for persona retrieval)
# =============================================================================

ESCAPE_TERMS: list[str] = [
    "escape", "freedom", "prison", "trapped", "release", "leave", "flee", "break free"
]

TRAUMA_TRIGGERS: list[str] = [
    "Davin", "Erebus", "father", "Emperor", "betrayal", "Chaos", "corruption"
]

# Emotionally significant entities for persona context
EMOTIONAL_ENTITIES: set[str] = {
    "Erebus", "Davin", "Sanguinius", "Emperor", "Loken", "Abaddon", "Sejanus", "Maloghurst"
}
