"""
Actor/talent taxonomy: delegates bridge extraction to common.taxonomy,
keeps TMDB-specific genre ID and actor type mappings locally.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Set

# Import common taxonomy
_SKILLS_DIR = str(Path(__file__).resolve().parent.parent.parent)
if _SKILLS_DIR not in sys.path:
    sys.path.insert(0, _SKILLS_DIR)

try:
    from common.taxonomy import get_bridge_attributes, get_episodic_associations, ContentType
    _COMMON_AVAILABLE = True
except ImportError:
    _COMMON_AVAILABLE = False

# === TMDB-specific data (kept local) ===

TMDB_GENRES = {
    28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy",
    80: "Crime", 99: "Documentary", 18: "Drama", 10751: "Family",
    14: "Fantasy", 36: "History", 27: "Horror", 10402: "Music",
    9648: "Mystery", 10749: "Romance", 878: "Science Fiction",
    10770: "TV Movie", 53: "Thriller", 10752: "War", 37: "Western",
}

BRIDGE_TO_GENRE_IDS: Dict[str, List[int]] = {
    "Precision": [53, 80, 99, 878],
    "Resilience": [10752, 12, 18, 36],
    "Fragility": [18, 10749, 16, 10402],
    "Corruption": [27, 80, 53, 9648, 878],
    "Loyalty": [10751, 36, 18, 10752, 37],
    "Stealth": [9648, 53, 80, 878],
}

BRIDGE_TO_ACTOR_TYPES: Dict[str, List[str]] = {
    "Precision": ["technical thriller actors", "heist film specialists", "legal drama regulars", "procedural actors", "cerebral thriller performers", "spy movie veterans"],
    "Resilience": ["war film veterans", "epic drama actors", "survival story performers", "sports movie stars", "historical epic regulars", "biographical film actors"],
    "Fragility": ["indie drama actors", "romantic lead specialists", "arthouse film performers", "coming-of-age actors", "emotional drama specialists", "character study performers"],
    "Corruption": ["noir film actors", "crime drama specialists", "psychological thriller performers", "horror veterans", "dystopian film actors", "morally complex character actors"],
    "Loyalty": ["period drama actors", "family film veterans", "western stars", "military film actors", "historical drama performers", "saga/dynasty actors"],
    "Stealth": ["mystery film actors", "espionage thriller specialists", "slow burn drama performers", "neo-noir actors", "conspiracy thriller veterans", "detective story actors"],
}

BRIDGE_KEYWORDS: Dict[str, List[str]] = {
    "Precision": ["meticulous", "calculated", "heist", "legal", "technical", "procedural", "cerebral", "spy"],
    "Resilience": ["war", "survive", "endure", "battle", "overcome", "warrior", "epic", "triumph"],
    "Fragility": ["vulnerable", "emotional", "romantic", "intimate", "delicate", "heartbreak", "tender", "poignant"],
    "Corruption": ["dark", "sinister", "noir", "crime", "psychological", "horror", "twisted", "evil"],
    "Loyalty": ["honor", "duty", "family", "tradition", "brotherhood", "devotion", "western", "military"],
    "Stealth": ["mystery", "espionage", "covert", "shadow", "conspiracy", "detective", "undercover", "hidden"],
}


def extract_bridge_tags_for_person(genre_ids: List[int], biography: str = "", known_for_genres: List[int] = None) -> List[str]:
    """Extract bridge tags from person's filmography genres."""
    if _COMMON_AVAILABLE:
        # Build text from genre names + bio for common extraction
        all_ids = set(genre_ids)
        if known_for_genres:
            all_ids.update(known_for_genres)
        genre_names = [TMDB_GENRES.get(gid, "") for gid in all_ids if gid in TMDB_GENRES]
        text = f"{' '.join(genre_names)} {biography}"
        return get_bridge_attributes(text, content_type=ContentType.MOVIE)

    # Fallback: local extraction
    bridges: Set[str] = set()
    all_genre_ids = set(genre_ids)
    if known_for_genres:
        all_genre_ids.update(known_for_genres)
    for bridge, bridge_genre_ids in BRIDGE_TO_GENRE_IDS.items():
        overlap = all_genre_ids.intersection(set(bridge_genre_ids))
        if len(overlap) >= 2:
            bridges.add(bridge)
        elif overlap and biography:
            bio_lower = biography.lower()
            if any(kw in bio_lower for kw in BRIDGE_KEYWORDS.get(bridge, [])):
                bridges.add(bridge)
    if biography and not bridges:
        bio_lower = biography.lower()
        for bridge, keywords in BRIDGE_KEYWORDS.items():
            if any(kw in bio_lower for kw in keywords):
                bridges.add(bridge)
    return list(bridges)


def get_genre_ids_for_bridge(bridge: str) -> List[int]:
    """Get TMDB genre IDs for a bridge attribute."""
    return BRIDGE_TO_GENRE_IDS.get(bridge, [])


def get_actor_types_for_bridge(bridge: str) -> List[str]:
    """Get actor type descriptions for a bridge attribute."""
    return BRIDGE_TO_ACTOR_TYPES.get(bridge, [])


def build_taxonomy_output(results: List[Dict[str, Any]], bridge_tags: List[str] = None, collection: str = "lore") -> Dict[str, Any]:
    """Build taxonomy metadata for output."""
    if bridge_tags is None:
        all_bridges: Set[str] = set()
        for r in results:
            known_for = r.get("known_for", [])
            genre_ids = []
            for movie in known_for:
                genre_ids.extend(movie.get("genre_ids", []))
            if genre_ids:
                all_bridges.update(extract_bridge_tags_for_person(genre_ids, r.get("biography", "")))
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
