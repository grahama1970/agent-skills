"""
Movie taxonomy: delegates bridge extraction to common.taxonomy,
keeps TMDB-specific genre ID mappings locally.
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

BRIDGE_TO_GENRES: Dict[str, List[str]] = {
    "Precision": ["thriller", "heist", "procedural", "legal", "documentary", "hard sci-fi", "techno-thriller", "spy", "cerebral"],
    "Resilience": ["war", "epic", "survival", "sports", "biography", "historical epic", "adventure", "triumph", "inspirational"],
    "Fragility": ["drama", "romance", "indie", "arthouse", "coming-of-age", "romantic drama", "emotional", "intimate", "character study"],
    "Corruption": ["noir", "crime", "psychological", "horror", "dystopian", "dark", "neo-noir", "body horror", "cosmic horror", "morally complex"],
    "Loyalty": ["family", "period drama", "historical", "western", "military", "war drama", "saga", "dynasty", "honor", "duty"],
    "Stealth": ["mystery", "espionage", "slow burn", "neo-noir", "conspiracy", "paranoid thriller", "detective", "hidden", "subtle"],
}

BRIDGE_KEYWORDS: Dict[str, List[str]] = {
    "Precision": ["meticulous", "plan", "calculated", "scheme", "heist", "procedure", "technical", "method", "systematic", "precise"],
    "Resilience": ["survive", "endure", "overcome", "triumph", "fight", "struggle", "persever", "battle", "warrior", "unbreakable"],
    "Fragility": ["vulnerable", "delicate", "emotional", "heartbreak", "loss", "tender", "sensitive", "intimate", "fragile", "poignant"],
    "Corruption": ["dark", "corrupt", "sinister", "evil", "twisted", "tainted", "morally", "compromised", "possessed", "cursed"],
    "Loyalty": ["honor", "duty", "family", "oath", "loyal", "devotion", "allegiance", "sacrifice", "brotherhood", "tradition"],
    "Stealth": ["hidden", "secret", "mysterious", "shadow", "covert", "undercover", "infiltrat", "conspiracy", "subtle", "unseen"],
}


def extract_bridge_tags(genres: List[str], overview: str = "", fast: bool = True) -> List[str]:
    """Extract bridge tags from movie genres and overview."""
    if _COMMON_AVAILABLE:
        text = f"{' '.join(genres)} {overview}"
        return get_bridge_attributes(text, content_type=ContentType.MOVIE)

    # Fallback: local extraction
    bridges: Set[str] = set()
    genres_lower = [g.lower() for g in genres]
    for bridge, bridge_genres in BRIDGE_TO_GENRES.items():
        for bg in bridge_genres:
            if any(bg.lower() in g for g in genres_lower):
                bridges.add(bridge)
                break
    if overview and fast:
        overview_lower = overview.lower()
        for bridge, keywords in BRIDGE_KEYWORDS.items():
            if any(kw in overview_lower for kw in keywords):
                bridges.add(bridge)
    return list(bridges)


def get_genre_ids_for_bridge(bridge: str) -> List[int]:
    """Get TMDB genre IDs for a bridge attribute."""
    return BRIDGE_TO_GENRE_IDS.get(bridge, [])


def get_genres_for_bridge(bridge: str) -> List[str]:
    """Get genre names for a bridge attribute."""
    return BRIDGE_TO_GENRES.get(bridge, [])


def build_taxonomy_output(results: List[dict], bridge_tags: List[str] = None, collection: str = "lore") -> dict:
    """Build taxonomy metadata for output."""
    if bridge_tags is None:
        all_bridges: Set[str] = set()
        for r in results:
            genres = r.get("genres", [])
            overview = r.get("overview", "")
            all_bridges.update(extract_bridge_tags(genres, overview))
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
