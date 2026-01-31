"""
Movie taxonomy mappings for Federated Taxonomy integration.

Maps movie genres to Bridge Attributes for cross-collection traversal.
Enables queries like "movies matching Corruption bridge" which finds noir,
crime, psychological, and horror films.

Bridge Attributes (Tier 0):
- Precision: Calculated, methodical, procedural content
- Resilience: Endurance, triumph, survival content
- Fragility: Vulnerable, delicate, emotional content
- Corruption: Dark, compromised, morally complex content
- Loyalty: Honor, duty, familial content
- Stealth: Hidden, subtle, mysterious content
"""

from typing import Dict, List, Set

# TMDB genre IDs for reference
TMDB_GENRES = {
    28: "Action",
    12: "Adventure",
    16: "Animation",
    35: "Comedy",
    80: "Crime",
    99: "Documentary",
    18: "Drama",
    10751: "Family",
    14: "Fantasy",
    36: "History",
    27: "Horror",
    10402: "Music",
    9648: "Mystery",
    10749: "Romance",
    878: "Science Fiction",
    10770: "TV Movie",
    53: "Thriller",
    10752: "War",
    37: "Western",
}

# Bridge Attribute → TMDB Genre IDs
BRIDGE_TO_GENRE_IDS: Dict[str, List[int]] = {
    "Precision": [
        53,   # Thriller
        80,   # Crime (heist films)
        99,   # Documentary
        878,  # Science Fiction (hard sci-fi)
    ],
    "Resilience": [
        10752,  # War
        12,     # Adventure
        18,     # Drama (survival stories)
        36,     # History (historical epics)
    ],
    "Fragility": [
        18,     # Drama
        10749,  # Romance
        16,     # Animation (emotional anime)
        10402,  # Music
    ],
    "Corruption": [
        27,   # Horror
        80,   # Crime
        53,   # Thriller
        9648, # Mystery
        878,  # Science Fiction (dystopian)
    ],
    "Loyalty": [
        10751,  # Family
        36,     # History
        18,     # Drama (period drama)
        10752,  # War (military honor)
        37,     # Western
    ],
    "Stealth": [
        9648,  # Mystery
        53,    # Thriller (espionage)
        80,    # Crime (noir)
        878,   # Science Fiction (conspiracy)
    ],
}

# Bridge Attribute → Genre names (for text matching)
BRIDGE_TO_GENRES: Dict[str, List[str]] = {
    "Precision": [
        "thriller", "heist", "procedural", "legal", "documentary",
        "hard sci-fi", "techno-thriller", "spy", "cerebral"
    ],
    "Resilience": [
        "war", "epic", "survival", "sports", "biography",
        "historical epic", "adventure", "triumph", "inspirational"
    ],
    "Fragility": [
        "drama", "romance", "indie", "arthouse", "coming-of-age",
        "romantic drama", "emotional", "intimate", "character study"
    ],
    "Corruption": [
        "noir", "crime", "psychological", "horror", "dystopian",
        "dark", "neo-noir", "body horror", "cosmic horror", "morally complex"
    ],
    "Loyalty": [
        "family", "period drama", "historical", "western", "military",
        "war drama", "saga", "dynasty", "honor", "duty"
    ],
    "Stealth": [
        "mystery", "espionage", "slow burn", "neo-noir", "conspiracy",
        "paranoid thriller", "detective", "hidden", "subtle"
    ],
}

# Keywords for fast bridge extraction from movie descriptions
BRIDGE_KEYWORDS: Dict[str, List[str]] = {
    "Precision": [
        "meticulous", "plan", "calculated", "scheme", "heist",
        "procedure", "technical", "method", "systematic", "precise"
    ],
    "Resilience": [
        "survive", "endure", "overcome", "triumph", "fight",
        "struggle", "persever", "battle", "warrior", "unbreakable"
    ],
    "Fragility": [
        "vulnerable", "delicate", "emotional", "heartbreak", "loss",
        "tender", "sensitive", "intimate", "fragile", "poignant"
    ],
    "Corruption": [
        "dark", "corrupt", "sinister", "evil", "twisted",
        "tainted", "morally", "compromised", "possessed", "cursed"
    ],
    "Loyalty": [
        "honor", "duty", "family", "oath", "loyal",
        "devotion", "allegiance", "sacrifice", "brotherhood", "tradition"
    ],
    "Stealth": [
        "hidden", "secret", "mysterious", "shadow", "covert",
        "undercover", "infiltrat", "conspiracy", "subtle", "unseen"
    ],
}


def extract_bridge_tags(
    genres: List[str],
    overview: str = "",
    fast: bool = True
) -> List[str]:
    """
    Extract bridge tags from movie genres and description.

    Args:
        genres: List of genre names
        overview: Movie description/overview
        fast: Use keyword extraction only

    Returns:
        List of matching bridge attribute names
    """
    bridges: Set[str] = set()
    genres_lower = [g.lower() for g in genres]

    # Match by genre
    for bridge, bridge_genres in BRIDGE_TO_GENRES.items():
        for bg in bridge_genres:
            if any(bg.lower() in g for g in genres_lower):
                bridges.add(bridge)
                break

    # Match by keywords in overview
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


def build_taxonomy_output(
    results: List[dict],
    bridge_tags: List[str] = None,
    collection: str = "lore"
) -> dict:
    """
    Build taxonomy metadata for output.

    Args:
        results: List of movie results
        bridge_tags: Explicit bridge tags to include
        collection: Taxonomy collection (lore, operational, sparta)

    Returns:
        Taxonomy dict with bridge_tags, collection_tags, confidence
    """
    # Aggregate bridges from all results if not provided
    if bridge_tags is None:
        all_bridges: Set[str] = set()
        for r in results:
            genres = r.get("genres", [])
            overview = r.get("overview", "")
            tags = extract_bridge_tags(genres, overview)
            all_bridges.update(tags)
        bridge_tags = list(all_bridges)

    # Determine collection tags based on dominant genres
    domain = "World"  # Default
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
