"""
Bridge-to-prompt augmentation for HMT-aware music generation.

Maps Federated Taxonomy bridge attributes to ACE-Step prompt keywords
to ensure generated music matches the thematic intent.
"""

from __future__ import annotations

from typing import List

# Bridge Attribute → Musical keywords for ACE-Step prompts
BRIDGE_PROMPT_AUGMENTS: dict[str, list[str]] = {
    "Precision": [
        "polyrhythmic",
        "technical",
        "algorithmic patterns",
        "complex rhythms",
        "mathematical",
        "precise",
    ],
    "Resilience": [
        "triumphant",
        "epic strings",
        "powerful brass",
        "heroic",
        "defiant",
        "enduring",
        "crescendo",
    ],
    "Fragility": [
        "delicate",
        "acoustic",
        "tender piano",
        "breaking",
        "vulnerable",
        "melancholic",
        "sparse",
    ],
    "Corruption": [
        "industrial",
        "distorted",
        "harsh textures",
        "oppressive",
        "dark",
        "ominous",
        "dissonant",
    ],
    "Loyalty": [
        "ceremonial",
        "choral",
        "sacred tones",
        "anthemic",
        "solemn",
        "reverent",
        "oath",
    ],
    "Stealth": [
        "ambient",
        "drone",
        "minimal",
        "atmospheric pads",
        "subtle",
        "tension",
        "suspense",
    ],
}

# Episode → Primary bridge mapping (for automatic bridge inference)
EPISODE_BRIDGES: dict[str, list[str]] = {
    "Siege_of_Terra": ["Resilience", "Fragility"],
    "Davin_Corruption": ["Corruption"],
    "Webway_Collapse": ["Fragility", "Precision"],
    "Mournival_Oath": ["Loyalty"],
    "Iron_Cage": ["Precision", "Resilience"],
    "Sanguinius_Fall": ["Fragility", "Loyalty"],
    "Isstvan_Betrayal": ["Corruption", "Fragility"],
    "Prospero_Burning": ["Fragility", "Corruption"],
    "Emperor_Throne": ["Resilience", "Loyalty"],
    "Horus_Primarch": ["Precision", "Corruption"],
}


def get_bridges_for_episode(episode: str) -> list[str]:
    """Get bridge attributes associated with an episode."""
    # Try exact match first
    if episode in EPISODE_BRIDGES:
        return EPISODE_BRIDGES[episode]

    # Try case-insensitive match
    episode_lower = episode.lower().replace(" ", "_")
    for ep, bridges in EPISODE_BRIDGES.items():
        if ep.lower() == episode_lower:
            return bridges

    return []


def augment_prompt_for_bridges(prompt: str, bridges: list[str]) -> str:
    """
    Augment a prompt with bridge-appropriate musical keywords.

    Args:
        prompt: Original generation prompt
        bridges: List of bridge attributes (e.g., ["Resilience", "Precision"])

    Returns:
        Augmented prompt with bridge keywords appended
    """
    if not bridges:
        return prompt

    # Collect keywords for all bridges
    keywords: list[str] = []
    for bridge in bridges:
        bridge_keywords = BRIDGE_PROMPT_AUGMENTS.get(bridge, [])
        # Add first 2-3 keywords per bridge to avoid overwhelming
        keywords.extend(bridge_keywords[:3])

    if not keywords:
        return prompt

    # Remove duplicates while preserving order
    seen = set()
    unique_keywords = []
    for kw in keywords:
        if kw.lower() not in seen:
            seen.add(kw.lower())
            unique_keywords.append(kw)

    # Append keywords to prompt
    keyword_str = ", ".join(unique_keywords[:6])  # Max 6 keywords
    return f"{prompt}, {keyword_str}"


def extract_bridges_from_prompt(prompt: str) -> list[str]:
    """
    Extract likely bridge attributes from a prompt based on keywords.

    This is a fast heuristic for when explicit bridges aren't provided.
    """
    prompt_lower = prompt.lower()
    detected: list[str] = []

    # Check for bridge keywords in prompt
    for bridge, keywords in BRIDGE_PROMPT_AUGMENTS.items():
        for kw in keywords:
            if kw.lower() in prompt_lower:
                if bridge not in detected:
                    detected.append(bridge)
                break

    # Also check for lore entity mentions
    lore_bridge_hints = {
        "iron warriors": "Precision",
        "perturabo": "Precision",
        "imperial fists": "Resilience",
        "dorn": "Resilience",
        "siege": "Resilience",
        "webway": "Fragility",
        "magnus": "Fragility",
        "chaos": "Corruption",
        "warp": "Corruption",
        "davin": "Corruption",
        "loyalty": "Loyalty",
        "oath": "Loyalty",
        "alpha legion": "Stealth",
        "alpharius": "Stealth",
        "infiltrat": "Stealth",
    }

    for hint, bridge in lore_bridge_hints.items():
        if hint in prompt_lower and bridge not in detected:
            detected.append(bridge)

    return detected[:3]  # Max 3 bridges


def get_all_bridges() -> List[str]:
    """Get list of all valid bridge attributes."""
    return list(BRIDGE_PROMPT_AUGMENTS.keys())
