#!/usr/bin/env python3
"""
Book Ingest Skill - Taxonomy Integration

Maps books to the Federated Taxonomy for multi-hop graph traversal in /memory.

Special handling for:
- Warhammer 40K / Horus Heresy novels → Direct lore connections
- Black Library authors (Dan Abnett, Aaron Dembski-Bowden, etc.)
- Primarch-specific books → Primarch-to-bridge mappings

This enables queries like:
- "Find books related to Siege of Terra" → Resilience bridge
- "Find books about Iron Warriors" → Precision bridge
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import common taxonomy module
_COMMON_PATH = Path(__file__).parent.parent / "common"
if str(_COMMON_PATH) not in sys.path:
    sys.path.insert(0, str(_COMMON_PATH))

# Use importlib to avoid circular import
import importlib.util
_spec = importlib.util.spec_from_file_location("common_taxonomy", _COMMON_PATH / "taxonomy.py")
_common_taxonomy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_common_taxonomy)

ContentType = _common_taxonomy.ContentType
TaxonomyExtractionResult = _common_taxonomy.TaxonomyExtractionResult
extract_taxonomy_features = _common_taxonomy.extract_taxonomy_features
get_bridge_attributes = _common_taxonomy.get_bridge_attributes
get_episodic_associations = _common_taxonomy.get_episodic_associations
BOOK_BRIDGE_INDICATORS = _common_taxonomy.BOOK_BRIDGE_INDICATORS
LORE_BRIDGE_MAPPINGS = _common_taxonomy.LORE_BRIDGE_MAPPINGS


# ==============================================================================
# WARHAMMER 40K / HORUS HERESY SPECIFIC MAPPINGS
# ==============================================================================

# Black Library authors → Bridge preferences
AUTHOR_BRIDGE_HINTS = {
    "dan abnett": ["Loyalty", "Resilience"],  # Gaunt's Ghosts, Horus Rising
    "aaron dembski-bowden": ["Corruption", "Fragility"],  # Night Lords, First Heretic
    "graham mcneill": ["Precision", "Corruption"],  # Iron Warriors, Fulgrim
    "chris wraight": ["Loyalty", "Stealth"],  # Scars, Alpha Legion
    "guy haley": ["Resilience"],  # Dark Imperium
    "david annandale": ["Corruption"],  # Horror elements
    "john french": ["Stealth", "Corruption"],  # Ahriman series
    "gav thorpe": ["Fragility"],  # Angels of Darkness
}

# Horus Heresy novel → Bridge and Episode mappings
HORUS_HERESY_NOVELS = {
    "horus rising": {
        "bridges": ["Loyalty"],
        "episodes": ["Horus_Primarch", "Mournival_Oath"],
        "primarchs": ["Horus"],
    },
    "false gods": {
        "bridges": ["Corruption", "Fragility"],
        "episodes": ["Davin_Corruption"],
        "primarchs": ["Horus"],
    },
    "galaxy in flames": {
        "bridges": ["Corruption", "Loyalty"],
        "episodes": ["Isstvan_Betrayal"],
        "primarchs": ["Horus"],
    },
    "flight of the eisenstein": {
        "bridges": ["Loyalty"],
        "episodes": ["Isstvan_Betrayal"],
        "primarchs": [],
    },
    "fulgrim": {
        "bridges": ["Corruption"],
        "episodes": ["Isstvan_Betrayal"],
        "primarchs": ["Fulgrim"],
    },
    "descent of angels": {
        "bridges": ["Loyalty"],
        "episodes": [],
        "primarchs": ["Lion El'Jonson"],
    },
    "legion": {
        "bridges": ["Stealth"],
        "episodes": ["Alpharius_Deception"],
        "primarchs": ["Alpharius", "Omegon"],
    },
    "battle for the abyss": {
        "bridges": ["Resilience"],
        "episodes": [],
        "primarchs": [],
    },
    "mechanicum": {
        "bridges": ["Precision"],
        "episodes": [],
        "primarchs": [],
    },
    "tales of heresy": {
        "bridges": ["Loyalty", "Corruption"],
        "episodes": [],
        "primarchs": [],
    },
    "fallen angels": {
        "bridges": ["Loyalty", "Corruption"],
        "episodes": [],
        "primarchs": ["Lion El'Jonson"],
    },
    "a thousand sons": {
        "bridges": ["Fragility"],
        "episodes": ["Webway_Collapse"],
        "primarchs": ["Magnus"],
    },
    "nemesis": {
        "bridges": ["Stealth", "Precision"],
        "episodes": [],
        "primarchs": [],
    },
    "the first heretic": {
        "bridges": ["Corruption"],
        "episodes": ["Davin_Corruption"],
        "primarchs": ["Lorgar"],
    },
    "prospero burns": {
        "bridges": ["Resilience", "Fragility"],
        "episodes": ["Webway_Collapse"],
        "primarchs": ["Russ", "Magnus"],
    },
    "age of darkness": {
        "bridges": ["Corruption"],
        "episodes": [],
        "primarchs": [],
    },
    "the outcast dead": {
        "bridges": ["Loyalty", "Corruption"],
        "episodes": ["Emperor_Throne"],
        "primarchs": [],
    },
    "deliverance lost": {
        "bridges": ["Resilience"],
        "episodes": [],
        "primarchs": ["Corax"],
    },
    "know no fear": {
        "bridges": ["Resilience", "Corruption"],
        "episodes": [],
        "primarchs": ["Roboute Guilliman"],
    },
    "the primarchs": {
        "bridges": ["Loyalty", "Corruption"],
        "episodes": [],
        "primarchs": [],
    },
    "fear to tread": {
        "bridges": ["Loyalty", "Corruption"],
        "episodes": ["Sanguinius_Fall"],
        "primarchs": ["Sanguinius"],
    },
    "shadows of treachery": {
        "bridges": ["Stealth", "Corruption"],
        "episodes": [],
        "primarchs": [],
    },
    "angel exterminatus": {
        "bridges": ["Precision", "Corruption"],
        "episodes": ["Iron_Cage"],
        "primarchs": ["Perturabo", "Fulgrim"],
    },
    "betrayer": {
        "bridges": ["Corruption", "Fragility"],
        "episodes": [],
        "primarchs": ["Angron", "Lorgar"],
    },
    "mark of calth": {
        "bridges": ["Resilience"],
        "episodes": [],
        "primarchs": [],
    },
    "vulkan lives": {
        "bridges": ["Resilience"],
        "episodes": [],
        "primarchs": ["Vulkan"],
    },
    "the unremembered empire": {
        "bridges": ["Resilience", "Loyalty"],
        "episodes": [],
        "primarchs": ["Roboute Guilliman"],
    },
    "scars": {
        "bridges": ["Loyalty", "Stealth"],
        "episodes": [],
        "primarchs": ["Jaghatai Khan"],
    },
    "vengeful spirit": {
        "bridges": ["Corruption"],
        "episodes": [],
        "primarchs": ["Horus"],
    },
    "the damnation of pythos": {
        "bridges": ["Corruption"],
        "episodes": [],
        "primarchs": [],
    },
    "legacies of betrayal": {
        "bridges": ["Corruption", "Loyalty"],
        "episodes": [],
        "primarchs": [],
    },
    "deathfire": {
        "bridges": ["Resilience"],
        "episodes": [],
        "primarchs": ["Vulkan"],
    },
    "war without end": {
        "bridges": ["Corruption"],
        "episodes": [],
        "primarchs": [],
    },
    "pharos": {
        "bridges": ["Resilience"],
        "episodes": [],
        "primarchs": [],
    },
    "eye of terra": {
        "bridges": ["Corruption"],
        "episodes": [],
        "primarchs": [],
    },
    "the path of heaven": {
        "bridges": ["Loyalty", "Stealth"],
        "episodes": [],
        "primarchs": ["Jaghatai Khan"],
    },
    "the silent war": {
        "bridges": ["Stealth"],
        "episodes": [],
        "primarchs": [],
    },
    "angels of caliban": {
        "bridges": ["Loyalty", "Fragility"],
        "episodes": [],
        "primarchs": ["Lion El'Jonson"],
    },
    "praetorian of dorn": {
        "bridges": ["Resilience", "Precision"],
        "episodes": ["Siege_of_Terra"],
        "primarchs": ["Dorn"],
    },
    "corax": {
        "bridges": ["Stealth", "Resilience"],
        "episodes": [],
        "primarchs": ["Corax"],
    },
    "master of mankind": {
        "bridges": ["Fragility", "Resilience"],
        "episodes": ["Webway_Collapse", "Emperor_Throne"],
        "primarchs": [],
    },
    "garro": {
        "bridges": ["Loyalty"],
        "episodes": [],
        "primarchs": [],
    },
    "shattered legions": {
        "bridges": ["Resilience", "Fragility"],
        "episodes": [],
        "primarchs": [],
    },
    "the crimson king": {
        "bridges": ["Fragility", "Corruption"],
        "episodes": ["Webway_Collapse"],
        "primarchs": ["Magnus"],
    },
    "tallarn": {
        "bridges": ["Precision", "Resilience"],
        "episodes": ["Iron_Cage"],
        "primarchs": ["Perturabo"],
    },
    "ruinstorm": {
        "bridges": ["Loyalty", "Corruption"],
        "episodes": ["Sanguinius_Fall"],
        "primarchs": ["Sanguinius"],
    },
    "old earth": {
        "bridges": ["Resilience"],
        "episodes": [],
        "primarchs": ["Vulkan"],
    },
    "the burden of loyalty": {
        "bridges": ["Loyalty"],
        "episodes": [],
        "primarchs": [],
    },
    "wolfsbane": {
        "bridges": ["Loyalty", "Corruption"],
        "episodes": [],
        "primarchs": ["Russ", "Horus"],
    },
    "born of flame": {
        "bridges": ["Resilience"],
        "episodes": [],
        "primarchs": ["Vulkan"],
    },
    "slaves to darkness": {
        "bridges": ["Corruption"],
        "episodes": [],
        "primarchs": ["Horus"],
    },
    "heralds of the siege": {
        "bridges": ["Resilience"],
        "episodes": ["Siege_of_Terra"],
        "primarchs": ["Dorn"],
    },
    "titandeath": {
        "bridges": ["Precision", "Resilience"],
        "episodes": ["Siege_of_Terra"],
        "primarchs": [],
    },
    "the buried dagger": {
        "bridges": ["Corruption"],
        "episodes": [],
        "primarchs": ["Mortarion"],
    },
    # Siege of Terra sub-series
    "the solar war": {
        "bridges": ["Resilience", "Precision"],
        "episodes": ["Siege_of_Terra"],
        "primarchs": ["Dorn", "Horus"],
    },
    "the lost and the damned": {
        "bridges": ["Corruption", "Resilience"],
        "episodes": ["Siege_of_Terra"],
        "primarchs": [],
    },
    "the first wall": {
        "bridges": ["Resilience"],
        "episodes": ["Siege_of_Terra"],
        "primarchs": ["Dorn"],
    },
    "saturnine": {
        "bridges": ["Resilience", "Corruption"],
        "episodes": ["Siege_of_Terra"],
        "primarchs": ["Dorn", "Perturabo"],
    },
    "mortis": {
        "bridges": ["Corruption", "Resilience"],
        "episodes": ["Siege_of_Terra"],
        "primarchs": [],
    },
    "warhawk": {
        "bridges": ["Loyalty", "Stealth"],
        "episodes": ["Siege_of_Terra"],
        "primarchs": ["Jaghatai Khan"],
    },
    "echoes of eternity": {
        "bridges": ["Loyalty", "Fragility"],
        "episodes": ["Siege_of_Terra", "Sanguinius_Fall"],
        "primarchs": ["Sanguinius", "Angron"],
    },
    "the end and the death": {
        "bridges": ["Resilience", "Corruption"],
        "episodes": ["Siege_of_Terra", "Emperor_Throne"],
        "primarchs": ["Horus", "Sanguinius"],
    },
}


# ==============================================================================
# EXTRACTION FUNCTIONS
# ==============================================================================

def extract_book_taxonomy(
    title: str,
    author: str = "",
    genre: str = "",
    description: str = "",
    tags: Optional[List[str]] = None,
) -> TaxonomyExtractionResult:
    """
    Extract taxonomy features from a book.

    Special handling for Warhammer 40K / Horus Heresy content.

    Args:
        title: Book title
        author: Author name
        genre: Genre or category
        description: Book description or synopsis
        tags: Additional tags

    Returns:
        TaxonomyExtractionResult with bridge_attributes, episodic_associations, etc.
    """
    tags = tags or []

    # Start with common taxonomy extraction
    result = extract_taxonomy_features(
        content_type=ContentType.BOOK,
        title=title,
        author=author,
        genre=genre,
        tags=tags,
        description=description,
    )

    bridge_attributes = list(result["bridge_attributes"])
    episodic = list(result["episodic_associations"])

    # Check for Horus Heresy novel match
    title_lower = title.lower().strip()
    if title_lower in HORUS_HERESY_NOVELS:
        novel_data = HORUS_HERESY_NOVELS[title_lower]
        for bridge in novel_data["bridges"]:
            if bridge not in bridge_attributes:
                bridge_attributes.append(bridge)
        for ep in novel_data["episodes"]:
            if ep not in episodic:
                episodic.append(ep)

    # Check author for bridge hints
    author_lower = author.lower().strip()
    for known_author, hints in AUTHOR_BRIDGE_HINTS.items():
        if known_author in author_lower:
            for bridge in hints:
                if bridge not in bridge_attributes:
                    bridge_attributes.append(bridge)
            break

    # Check for lore entities in title/description
    combined = f"{title} {description}".lower()
    for entity, entity_bridges in LORE_BRIDGE_MAPPINGS.items():
        if entity.lower() in combined:
            for bridge in entity_bridges:
                if bridge not in bridge_attributes:
                    bridge_attributes.append(bridge)

    bridge_attributes = bridge_attributes[:3]  # Max 3

    # Get additional episodic from bridges
    for ep in get_episodic_associations(bridge_attributes, f"{title} {description}"):
        if ep not in episodic:
            episodic.append(ep)

    # Determine if Warhammer 40K
    is_wh40k = any(k in combined for k in [
        "warhammer", "40k", "40,000", "horus", "primarch", "astartes",
        "black library", "space marine", "imperium", "emperor"
    ])

    # Determine function
    function = ["Study"] if is_wh40k else result["collection_tags"].get("function", ["Entertainment"])

    return TaxonomyExtractionResult(
        content_type=ContentType.BOOK.value,
        bridge_attributes=bridge_attributes,
        collection_tags={
            "domain": result["collection_tags"].get("domain", []) + (["Lore"] if is_wh40k else []),
            "thematic_weight": result["collection_tags"].get("thematic_weight", []),
            "function": function,
            "perspective": ["Literary"],
        },
        tactical_tags=["Invoke", "Recall"] if is_wh40k else ["Recall"],
        episodic_associations=episodic,
        dimensions=result["dimensions"],
        confidence=0.9 if is_wh40k and title_lower in HORUS_HERESY_NOVELS else result["confidence"],
        raw_matches={
            "author": author,
            "genre": genre,
            "is_wh40k": is_wh40k,
            "hh_novel": title_lower if title_lower in HORUS_HERESY_NOVELS else None,
        },
    )


def get_horus_heresy_metadata(title: str) -> Optional[Dict[str, Any]]:
    """
    Get Horus Heresy novel metadata if available.

    Args:
        title: Book title

    Returns:
        Dict with bridges, episodes, primarchs or None if not found
    """
    title_lower = title.lower().strip()
    return HORUS_HERESY_NOVELS.get(title_lower)


def enrich_book_with_taxonomy(book: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enrich a book dict with taxonomy features.

    Args:
        book: Book dict with fields like title, author, genre

    Returns:
        Same book dict with added taxonomy fields
    """
    result = extract_book_taxonomy(
        title=book.get("title", ""),
        author=book.get("author", book.get("authorName", "")),
        genre=book.get("genre", ""),
        description=book.get("description", book.get("overview", "")),
        tags=book.get("tags", []),
    )

    book["bridge_attributes"] = result["bridge_attributes"]
    book["episodic_associations"] = result["episodic_associations"]
    book["taxonomy_confidence"] = result["confidence"]
    book["is_wh40k"] = result["raw_matches"].get("is_wh40k", False)

    return book


def book_to_memory_format(book: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert a book dict to memory-compatible format.

    Args:
        book: Book dict (enriched with taxonomy)

    Returns:
        Dict ready for memory.learn()
    """
    if "bridge_attributes" not in book:
        book = enrich_book_with_taxonomy(book)

    return {
        "category": "book",
        "title": book.get("title", "Unknown"),
        "content": book.get("description", book.get("overview", "")),
        "bridge_attributes": book.get("bridge_attributes", []),
        "episodic_associations": book.get("episodic_associations", []),
        "collection_tags": {
            "author": book.get("author", book.get("authorName")),
            "genre": book.get("genre"),
            "is_wh40k": book.get("is_wh40k", False),
        },
        "metadata": {
            "year": book.get("year"),
            "isbn": book.get("isbn"),
        },
        "confidence": book.get("taxonomy_confidence", 0.5),
    }


# ==============================================================================
# EXPORTS
# ==============================================================================

__all__ = [
    "extract_book_taxonomy",
    "get_horus_heresy_metadata",
    "enrich_book_with_taxonomy",
    "book_to_memory_format",
    "HORUS_HERESY_NOVELS",
    "AUTHOR_BRIDGE_HINTS",
]
