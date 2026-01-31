#!/usr/bin/env python3
"""
Horus Lore Connection - Enable music recall based on lore episodes and scenes.

Task 9: Connect music entries to Warhammer 40k Horus Heresy lore episodes,
allowing Horus to recall appropriate music for storytelling scenes.

Episodic Associations map lore episodes to bridge attributes and canonical artists,
enabling thematic music discovery for persona-driven narrative work.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Episodic Associations: Lore episode -> bridge attribute + canonical artists
# These map Horus Heresy story beats to musical moods
EPISODIC_ASSOCIATIONS: dict[str, dict[str, Any]] = {
    "Siege_of_Terra": {
        "bridge": "Resilience",
        "artists": ["Sabaton", "Two Steps From Hell"],
        "keywords": ["defense", "last stand", "heroic", "desperate"],
    },
    "Davin_Corruption": {
        "bridge": "Corruption",
        "artists": ["Chelsea Wolfe", "Nine Inch Nails"],
        "keywords": ["chaos", "temptation", "fall", "dark"],
    },
    "Webway_Collapse": {
        "bridge": "Fragility",
        "artists": ["Daughter", "Phoebe Bridgers"],
        "keywords": ["loss", "tragedy", "broken", "mourning"],
    },
    "Mournival_Oath": {
        "bridge": "Loyalty",
        "artists": ["Wardruna", "Heilung"],
        "keywords": ["oath", "brotherhood", "sacred", "ceremony"],
    },
    "Iron_Cage": {
        "bridge": "Precision",
        "artists": ["Tool", "Meshuggah"],
        "keywords": ["tactical", "calculated", "methodical", "siege"],
    },
    "Sanguinius_Fall": {
        "bridge": "Fragility",
        "artists": ["Chelsea Wolfe", "Billie Marten"],
        "keywords": ["sacrifice", "angel", "death", "nobility"],
    },
}

# Scene keyword to bridge attribute mappings
SCENE_KEYWORD_BRIDGES: dict[str, str] = {
    # Resilience keywords
    "battle": "Resilience",
    "defense": "Resilience",
    "siege": "Resilience",
    "stand": "Resilience",
    "fight": "Resilience",
    "war": "Resilience",
    "heroic": "Resilience",
    "triumph": "Resilience",
    # Fragility keywords
    "fall": "Fragility",
    "mourning": "Fragility",
    "loss": "Fragility",
    "death": "Fragility",
    "grief": "Fragility",
    "sorrow": "Fragility",
    "tragic": "Fragility",
    "broken": "Fragility",
    # Corruption keywords
    "corruption": "Corruption",
    "chaos": "Corruption",
    "dark": "Corruption",
    "temptation": "Corruption",
    "betrayal": "Corruption",
    "warp": "Corruption",
    "daemon": "Corruption",
    # Loyalty keywords
    "oath": "Loyalty",
    "brotherhood": "Loyalty",
    "sacred": "Loyalty",
    "ceremony": "Loyalty",
    "honor": "Loyalty",
    "duty": "Loyalty",
    # Precision keywords
    "tactical": "Precision",
    "calculated": "Precision",
    "methodical": "Precision",
    "strategy": "Precision",
    "logic": "Precision",
}


@dataclass
class MusicMatch:
    """A music entry matched to a lore query with relevance score."""

    entry: dict[str, Any]
    score: float
    matched_bridge: str | None = None
    matched_artist: bool = False


def get_episode_bridges(episode_name: str) -> dict[str, Any] | None:
    """Get bridge attributes and artists for a lore episode.

    Args:
        episode_name: Name of the lore episode (e.g., "Siege_of_Terra")

    Returns:
        Dict with bridge attribute, artists, and keywords, or None if not found.

    Example:
        >>> bridges = get_episode_bridges("Siege_of_Terra")
        >>> bridges["bridge"]
        'Resilience'
        >>> "Sabaton" in bridges["artists"]
        True
    """
    # Normalize episode name: handle spaces, underscores, case
    normalized = episode_name.strip().replace(" ", "_")

    # Try exact match first
    if normalized in EPISODIC_ASSOCIATIONS:
        return EPISODIC_ASSOCIATIONS[normalized]

    # Try case-insensitive match
    for ep_name, data in EPISODIC_ASSOCIATIONS.items():
        if ep_name.lower() == normalized.lower():
            return data

    return None


def _extract_bridge_from_entry(entry: dict[str, Any]) -> list[str]:
    """Extract bridge attributes from a music entry.

    Checks for HMT-enriched fields first, then falls back to text matching.
    """
    # Check for HMT-enriched bridge attributes
    bridges = entry.get("hmt_bridge_attributes", [])
    if bridges:
        return bridges

    # Also check flat bridge_attributes field (from sync_memory format)
    bridges = entry.get("bridge_attributes", [])
    if bridges:
        return bridges

    return []


def _extract_artist_from_entry(entry: dict[str, Any]) -> str:
    """Extract artist name from entry, normalized for matching."""
    artist = entry.get("artist") or entry.get("channel") or ""
    return artist.lower().strip()


def _calculate_episode_relevance(
    entry: dict[str, Any],
    episode_data: dict[str, Any],
) -> MusicMatch:
    """Calculate relevance score for an entry against an episode.

    Scoring:
    - Artist match: +20 points
    - Bridge attribute match: +15 points
    - Keyword match in title/tags: +5 points each
    """
    score = 0.0
    matched_bridge = None
    matched_artist = False

    target_bridge = episode_data.get("bridge", "")
    target_artists = [a.lower() for a in episode_data.get("artists", [])]
    target_keywords = [k.lower() for k in episode_data.get("keywords", [])]

    # Check artist match
    entry_artist = _extract_artist_from_entry(entry)
    for artist in target_artists:
        if artist in entry_artist or entry_artist in artist:
            score += 20.0
            matched_artist = True
            break

    # Check bridge attribute match
    entry_bridges = _extract_bridge_from_entry(entry)
    if target_bridge in entry_bridges:
        score += 15.0
        matched_bridge = target_bridge

    # Check keyword matches in title and tags
    title = (entry.get("title") or "").lower()
    tags = [t.lower() for t in entry.get("tags", [])]
    searchable = f"{title} {' '.join(tags)}"

    for keyword in target_keywords:
        if keyword in searchable:
            score += 5.0

    return MusicMatch(
        entry=entry,
        score=score,
        matched_bridge=matched_bridge,
        matched_artist=matched_artist,
    )


def _extract_bridges_from_scene(scene_description: str) -> list[str]:
    """Extract bridge attributes from a scene description using keyword matching.

    Args:
        scene_description: Text describing a scene

    Returns:
        List of bridge attributes found in the description
    """
    description_lower = scene_description.lower()
    bridges: set[str] = set()

    for keyword, bridge in SCENE_KEYWORD_BRIDGES.items():
        if keyword in description_lower:
            bridges.add(bridge)

    # Also check if it's an episode name
    episode_data = get_episode_bridges(scene_description)
    if episode_data:
        bridges.add(episode_data["bridge"])

    return list(bridges)


def _calculate_scene_relevance(
    entry: dict[str, Any],
    target_bridges: list[str],
) -> MusicMatch:
    """Calculate relevance score for an entry against scene bridges.

    Scoring:
    - Each matching bridge: +15 points
    """
    score = 0.0
    matched_bridge = None

    entry_bridges = _extract_bridge_from_entry(entry)

    for bridge in target_bridges:
        if bridge in entry_bridges:
            score += 15.0
            matched_bridge = bridge

    return MusicMatch(
        entry=entry,
        score=score,
        matched_bridge=matched_bridge,
        matched_artist=False,
    )


def find_music_for_episode(
    episode_name: str,
    music_entries: list[dict[str, Any]],
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Find music matching a lore episode.

    Args:
        episode_name: Name of the lore episode (e.g., "Siege_of_Terra")
        music_entries: List of music entry dicts
        limit: Maximum number of results to return

    Returns:
        List of matching music entries sorted by relevance score (highest first).
        Returns empty list if episode not found.

    Example:
        >>> entries = [
        ...     {"artist": "Sabaton", "title": "The Last Stand", "bridge_attributes": ["Resilience"]},
        ...     {"artist": "Daughter", "title": "Smother", "bridge_attributes": ["Fragility"]},
        ... ]
        >>> results = find_music_for_episode("Siege_of_Terra", entries)
        >>> results[0]["artist"]
        'Sabaton'
    """
    episode_data = get_episode_bridges(episode_name)
    if not episode_data:
        return []

    # Calculate relevance for each entry
    matches: list[MusicMatch] = []
    for entry in music_entries:
        match = _calculate_episode_relevance(entry, episode_data)
        if match.score > 0:
            matches.append(match)

    # Sort by score descending
    matches.sort(key=lambda m: m.score, reverse=True)

    # Return entries only
    return [m.entry for m in matches[:limit]]


def find_music_for_scene(
    scene_description: str,
    music_entries: list[dict[str, Any]],
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Find music matching a scene description.

    Analyzes the scene description for keywords that map to bridge attributes,
    then finds music entries with matching bridges.

    Args:
        scene_description: Text describing the scene (e.g., "Siege of Terra")
        music_entries: List of music entry dicts
        limit: Maximum number of results to return

    Returns:
        List of matching music entries sorted by relevance score (highest first).
        Returns empty list if no bridge attributes found in description.

    Example:
        >>> entries = [
        ...     {"artist": "Sabaton", "title": "The Last Stand", "bridge_attributes": ["Resilience"]},
        ...     {"artist": "Daughter", "title": "Smother", "bridge_attributes": ["Fragility"]},
        ... ]
        >>> results = find_music_for_scene("A desperate battle for defense", entries)
        >>> results[0]["artist"]
        'Sabaton'
    """
    # Extract bridges from scene description
    target_bridges = _extract_bridges_from_scene(scene_description)
    if not target_bridges:
        return []

    # Calculate relevance for each entry
    matches: list[MusicMatch] = []
    for entry in music_entries:
        match = _calculate_scene_relevance(entry, target_bridges)
        if match.score > 0:
            matches.append(match)

    # Sort by score descending
    matches.sort(key=lambda m: m.score, reverse=True)

    # Return entries only
    return [m.entry for m in matches[:limit]]


def get_all_episodes() -> list[str]:
    """Get all available episode names.

    Returns:
        List of episode names in the EPISODIC_ASSOCIATIONS registry.
    """
    return list(EPISODIC_ASSOCIATIONS.keys())


def get_all_bridges() -> list[str]:
    """Get all unique bridge attributes from episodes.

    Returns:
        List of unique bridge attribute names.
    """
    bridges = set()
    for data in EPISODIC_ASSOCIATIONS.values():
        bridges.add(data["bridge"])
    return sorted(bridges)
