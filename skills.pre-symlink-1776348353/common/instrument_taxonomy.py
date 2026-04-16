#!/usr/bin/env python3
"""
Shared Instrument Taxonomy for All Skills

Maps natural instrument names to canonical categories, Demucs source names,
and learn-artist subcategories. Used by:
- create-stems: instrument → Demucs two-stems source
- ingest-yt-history: artist tags → instrument classification
- discover-music: instrument-aware recommendations
- learn-artist: subcategory assignment

Usage:
    from common.instrument_taxonomy import (
        classify_instrument,
        classify_artist_instrument,
        INSTRUMENT_FAMILIES,
    )

    # Classify a single instrument name
    result = classify_instrument("oud")
    # → {"canonical": "oud", "family": "plucked_strings", "demucs_source": "guitar",
    #    "subcategory": "oud-player", "display": "oud player"}

    # Classify from artist tags/genres
    result = classify_artist_instrument(
        genres=["persian classical", "world music", "oud"],
        subcategory="oud-player",
    )
    # → {"instrument": "oud", "family": "plucked_strings", ...}
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


# =============================================================================
# INSTRUMENT FAMILIES
# =============================================================================

@dataclass(frozen=True)
class InstrumentInfo:
    """Canonical instrument classification."""
    canonical: str          # e.g., "oud"
    family: str             # e.g., "plucked_strings"
    demucs_source: str      # e.g., "guitar" (for --two-stems)
    subcategory: str        # e.g., "oud-player" (learn-artist)
    display: str            # e.g., "oud player" (human-readable)
    keywords: tuple         # Additional matching keywords


# Family definitions with all member instruments
INSTRUMENT_FAMILIES: Dict[str, List[InstrumentInfo]] = {
    "vocals": [
        InstrumentInfo("vocals", "vocals", "vocals", "vocalist", "vocalist",
                       ("voice", "singing", "singer", "vocal", "vocalist")),
    ],
    "plucked_strings": [
        InstrumentInfo("guitar", "plucked_strings", "guitar", "guitarist", "guitar player",
                       ("electric guitar", "acoustic guitar", "classical guitar", "fingerstyle")),
        InstrumentInfo("oud", "plucked_strings", "guitar", "oud-player", "oud player",
                       ("ud", "ʿūd",)),
        InstrumentInfo("lute", "plucked_strings", "guitar", "lute-player", "lute player",
                       ("renaissance lute", "baroque lute")),
        InstrumentInfo("banjo", "plucked_strings", "guitar", "banjo-player", "banjo player",
                       ("5-string banjo", "clawhammer")),
        InstrumentInfo("mandolin", "plucked_strings", "guitar", "mandolin-player", "mandolin player",
                       ("mandola", "octave mandolin")),
        InstrumentInfo("sitar", "plucked_strings", "guitar", "sitar-player", "sitar player",
                       ("hindustani",)),
        InstrumentInfo("ukulele", "plucked_strings", "guitar", "ukulele-player", "ukulele player",
                       ()),
        InstrumentInfo("bouzouki", "plucked_strings", "guitar", "bouzouki-player", "bouzouki player",
                       ("greek bouzouki", "irish bouzouki")),
        InstrumentInfo("kora", "plucked_strings", "guitar", "kora-player", "kora player",
                       ("west african",)),
        InstrumentInfo("harp", "plucked_strings", "guitar", "harpist", "harpist",
                       ("celtic harp", "concert harp", "lever harp")),
        InstrumentInfo("balalaika", "plucked_strings", "guitar", "balalaika-player", "balalaika player",
                       ()),
        InstrumentInfo("pipa", "plucked_strings", "guitar", "pipa-player", "pipa player",
                       ("chinese lute",)),
        InstrumentInfo("shamisen", "plucked_strings", "guitar", "shamisen-player", "shamisen player",
                       ("japanese",)),
        InstrumentInfo("tar", "plucked_strings", "guitar", "tar-player", "tar player",
                       ("persian tar",)),
        InstrumentInfo("setar", "plucked_strings", "guitar", "setar-player", "setar player",
                       ("persian setar",)),
    ],
    "bowed_strings": [
        InstrumentInfo("violin", "bowed_strings", "other", "violinist", "violinist",
                       ("fiddle", "first violin")),
        InstrumentInfo("viola", "bowed_strings", "other", "violist", "violist",
                       ()),
        InstrumentInfo("cello", "bowed_strings", "other", "cellist", "cellist",
                       ("violoncello",)),
        InstrumentInfo("double bass", "bowed_strings", "other", "bassist", "double bass player",
                       ("upright bass", "contrabass", "string bass")),
        InstrumentInfo("erhu", "bowed_strings", "other", "erhu-player", "erhu player",
                       ("chinese violin",)),
        InstrumentInfo("kamancheh", "bowed_strings", "other", "kamancheh-player", "kamancheh player",
                       ("persian fiddle",)),
    ],
    "keyboards": [
        InstrumentInfo("piano", "keyboards", "piano", "pianist", "pianist",
                       ("keyboard", "keys", "grand piano")),
        InstrumentInfo("organ", "keyboards", "piano", "organist", "organist",
                       ("church organ", "hammond organ", "pipe organ")),
        InstrumentInfo("synthesizer", "keyboards", "piano", "synth-player", "synthesizer player",
                       ("synth", "analog synth", "modular")),
        InstrumentInfo("accordion", "keyboards", "piano", "accordionist", "accordionist",
                       ("concertina", "bandoneon")),
        InstrumentInfo("harpsichord", "keyboards", "piano", "harpsichordist", "harpsichordist",
                       ()),
    ],
    "drums_percussion": [
        InstrumentInfo("drums", "drums_percussion", "drums", "drummer", "drummer",
                       ("drum kit", "drum set", "trap set")),
        InstrumentInfo("percussion", "drums_percussion", "drums", "percussionist", "percussionist",
                       ("congas", "bongos", "djembe", "tablas", "timpani", "marimba",
                        "vibraphone", "xylophone", "cajon")),
        InstrumentInfo("tabla", "drums_percussion", "drums", "tabla-player", "tabla player",
                       ("indian percussion",)),
        InstrumentInfo("darbuka", "drums_percussion", "drums", "darbuka-player", "darbuka player",
                       ("doumbek", "goblet drum")),
    ],
    "bass": [
        InstrumentInfo("bass guitar", "bass", "bass", "bassist", "bass player",
                       ("electric bass", "bass", "fretless bass")),
    ],
    "brass": [
        InstrumentInfo("trumpet", "brass", "other", "trumpeter", "trumpet player",
                       ("cornet", "flugelhorn")),
        InstrumentInfo("trombone", "brass", "other", "trombonist", "trombone player",
                       ()),
        InstrumentInfo("french horn", "brass", "other", "horn-player", "french horn player",
                       ("horn",)),
        InstrumentInfo("tuba", "brass", "other", "tuba-player", "tuba player",
                       ("sousaphone",)),
    ],
    "woodwinds": [
        InstrumentInfo("saxophone", "woodwinds", "other", "saxophonist", "saxophone player",
                       ("sax", "alto sax", "tenor sax", "soprano sax", "baritone sax")),
        InstrumentInfo("flute", "woodwinds", "other", "flutist", "flute player",
                       ("western flute", "concert flute")),
        InstrumentInfo("clarinet", "woodwinds", "other", "clarinetist", "clarinet player",
                       ()),
        InstrumentInfo("oboe", "woodwinds", "other", "oboist", "oboe player",
                       ()),
        InstrumentInfo("ney", "woodwinds", "other", "ney-player", "ney player",
                       ("persian flute", "arabic flute")),
        InstrumentInfo("duduk", "woodwinds", "other", "duduk-player", "duduk player",
                       ("armenian",)),
        InstrumentInfo("bagpipes", "woodwinds", "other", "bagpiper", "bagpiper",
                       ("uilleann pipes", "highland pipes")),
    ],
}

# Flat lookup: instrument name → InstrumentInfo
_INSTRUMENT_LOOKUP: Dict[str, InstrumentInfo] = {}
# Keyword lookup: keyword → InstrumentInfo
_KEYWORD_LOOKUP: Dict[str, InstrumentInfo] = {}
# Subcategory lookup: subcategory → InstrumentInfo
_SUBCATEGORY_LOOKUP: Dict[str, InstrumentInfo] = {}

for _family_name, _instruments in INSTRUMENT_FAMILIES.items():
    for _info in _instruments:
        _INSTRUMENT_LOOKUP[_info.canonical] = _info
        _SUBCATEGORY_LOOKUP[_info.subcategory] = _info
        for _kw in _info.keywords:
            _KEYWORD_LOOKUP[_kw] = _info


# =============================================================================
# CLASSIFICATION FUNCTIONS
# =============================================================================

def classify_instrument(name: str) -> Optional[InstrumentInfo]:
    """
    Classify an instrument by its natural name.

    Args:
        name: Instrument name (e.g., "oud", "electric guitar", "tabla")

    Returns:
        InstrumentInfo or None if not recognized.

    Examples:
        >>> classify_instrument("oud")
        InstrumentInfo(canonical='oud', family='plucked_strings', ...)
        >>> classify_instrument("electric guitar")
        InstrumentInfo(canonical='guitar', family='plucked_strings', ...)
    """
    name_lower = name.lower().strip()

    # Direct canonical match
    if name_lower in _INSTRUMENT_LOOKUP:
        return _INSTRUMENT_LOOKUP[name_lower]

    # Keyword match
    if name_lower in _KEYWORD_LOOKUP:
        return _KEYWORD_LOOKUP[name_lower]

    # Partial match: check if any instrument/keyword is contained in the name
    for canonical, info in _INSTRUMENT_LOOKUP.items():
        if canonical in name_lower:
            return info
    for kw, info in _KEYWORD_LOOKUP.items():
        if kw in name_lower:
            return info

    return None


def classify_from_subcategory(subcategory: str) -> Optional[InstrumentInfo]:
    """
    Classify from a learn-artist subcategory.

    Args:
        subcategory: e.g., "oud-player", "guitarist", "vocalist"

    Returns:
        InstrumentInfo or None.
    """
    return _SUBCATEGORY_LOOKUP.get(subcategory)


def classify_artist_instrument(
    genres: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    subcategory: Optional[str] = None,
    title: Optional[str] = None,
) -> Optional[InstrumentInfo]:
    """
    Classify an artist's primary instrument from available metadata.

    Tries multiple strategies in order:
    1. Direct subcategory match (from learn-artist ARTIST_DB)
    2. Genre/tag scanning for instrument keywords
    3. Title scanning for instrument mentions

    Args:
        genres: Artist genres (e.g., ["persian classical", "oud"])
        tags: Additional tags
        subcategory: learn-artist subcategory (e.g., "oud-player")
        title: Video/track title that might mention instrument

    Returns:
        InstrumentInfo or None if instrument cannot be determined.
    """
    # Strategy 1: Direct subcategory
    if subcategory:
        result = classify_from_subcategory(subcategory)
        if result:
            return result

    # Strategy 2: Scan genres and tags
    all_text_items = (genres or []) + (tags or [])
    for item in all_text_items:
        result = classify_instrument(item)
        if result:
            return result

    # Strategy 3: Scan title
    if title:
        result = classify_instrument(title)
        if result:
            return result

    # Strategy 4: Check if any genre/tag contains an instrument keyword
    combined = " ".join(all_text_items).lower()
    if title:
        combined += " " + title.lower()

    for canonical, info in _INSTRUMENT_LOOKUP.items():
        if canonical in combined:
            return info
    for kw, info in _KEYWORD_LOOKUP.items():
        if kw in combined:
            return info

    return None


def get_demucs_source(instrument_name: str) -> Optional[str]:
    """
    Get the Demucs two-stems source for an instrument.

    This is the key function for create-stems: given a natural instrument
    name, return the Demucs source to isolate.

    Args:
        instrument_name: Natural instrument name (e.g., "oud", "tabla")

    Returns:
        Demucs source name (e.g., "guitar", "drums") or None.
    """
    info = classify_instrument(instrument_name)
    return info.demucs_source if info else None


def list_instruments_by_family(family: str) -> List[InstrumentInfo]:
    """List all instruments in a family."""
    return INSTRUMENT_FAMILIES.get(family, [])


def list_all_families() -> List[str]:
    """List all instrument family names."""
    return list(INSTRUMENT_FAMILIES.keys())


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "InstrumentInfo",
    "INSTRUMENT_FAMILIES",
    "classify_instrument",
    "classify_from_subcategory",
    "classify_artist_instrument",
    "get_demucs_source",
    "list_instruments_by_family",
    "list_all_families",
]
