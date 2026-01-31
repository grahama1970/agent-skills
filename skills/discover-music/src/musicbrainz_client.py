#!/usr/bin/env python3
"""
MusicBrainz client for discover-music skill.

MusicBrainz provides:
- Artist search by name, tag, genre
- Artist relationships (similar, members, etc.)
- Recording/track metadata
- Release (album) information

No API key required - only User-Agent string.
Rate limit: 1 request per second (handled by musicbrainzngs).
"""

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import musicbrainzngs

# Initialize with User-Agent (required)
musicbrainzngs.set_useragent(
    "HorusAgent",
    "1.0",
    "grahama@me.com"
)

# Rate limiting
_last_request_time = 0.0
_min_request_interval = 1.1  # seconds


def _rate_limit():
    """Ensure minimum interval between requests."""
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < _min_request_interval:
        time.sleep(_min_request_interval - elapsed)
    _last_request_time = time.time()


@dataclass
class MBArtist:
    """MusicBrainz artist result."""
    name: str
    mbid: str
    tags: List[str]
    disambiguation: str = ""
    country: str = ""
    score: int = 100


@dataclass
class MBRecording:
    """MusicBrainz recording (track) result."""
    title: str
    mbid: str
    artist: str
    artist_mbid: str
    duration_ms: int = 0
    tags: List[str] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []


def search_artists(
    query: str = "",
    tag: str = "",
    limit: int = 10,
) -> List[MBArtist]:
    """
    Search for artists by name or tag.

    Args:
        query: Artist name to search
        tag: Genre/style tag to search
        limit: Max results

    Returns:
        List of MBArtist results
    """
    _rate_limit()

    try:
        if query:
            result = musicbrainzngs.search_artists(artist=query, limit=limit)
        elif tag:
            result = musicbrainzngs.search_artists(tag=tag, limit=limit)
        else:
            return []

        artists = []
        for a in result.get("artist-list", []):
            artists.append(MBArtist(
                name=a.get("name", "Unknown"),
                mbid=a.get("id", ""),
                tags=[t.get("name", "") for t in a.get("tag-list", [])],
                disambiguation=a.get("disambiguation", ""),
                country=a.get("country", ""),
                score=int(a.get("ext:score", 100)),
            ))
        return artists

    except Exception as e:
        print(f"MusicBrainz search error: {e}")
        return []


def get_artist(mbid: str, includes: Optional[List[str]] = None) -> Optional[MBArtist]:
    """
    Get artist details by MBID.

    Args:
        mbid: MusicBrainz artist ID
        includes: Additional data to include (tags, url-rels, etc.)

    Returns:
        MBArtist or None
    """
    _rate_limit()
    includes = includes or ["tags", "url-rels"]

    try:
        result = musicbrainzngs.get_artist_by_id(mbid, includes=includes)
        a = result.get("artist", {})

        return MBArtist(
            name=a.get("name", "Unknown"),
            mbid=a.get("id", mbid),
            tags=[t.get("name", "") for t in a.get("tag-list", [])],
            disambiguation=a.get("disambiguation", ""),
            country=a.get("country", ""),
        )
    except Exception as e:
        print(f"MusicBrainz get_artist error: {e}")
        return None


def search_recordings(
    query: str = "",
    artist: str = "",
    limit: int = 10,
) -> List[MBRecording]:
    """
    Search for recordings (tracks).

    Args:
        query: Recording title
        artist: Filter by artist name
        limit: Max results

    Returns:
        List of MBRecording results
    """
    _rate_limit()

    try:
        if artist:
            result = musicbrainzngs.search_recordings(
                recording=query,
                artist=artist,
                limit=limit
            )
        else:
            result = musicbrainzngs.search_recordings(recording=query, limit=limit)

        recordings = []
        for r in result.get("recording-list", []):
            # Get first artist credit
            artist_credit = r.get("artist-credit", [])
            if artist_credit and isinstance(artist_credit[0], dict):
                artist_name = artist_credit[0].get("name", "Unknown")
                artist_id = artist_credit[0].get("artist", {}).get("id", "")
            else:
                artist_name = "Unknown"
                artist_id = ""

            recordings.append(MBRecording(
                title=r.get("title", "Unknown"),
                mbid=r.get("id", ""),
                artist=artist_name,
                artist_mbid=artist_id,
                duration_ms=int(r.get("length", 0) or 0),
                tags=[t.get("name", "") for t in r.get("tag-list", [])],
            ))
        return recordings

    except Exception as e:
        print(f"MusicBrainz search_recordings error: {e}")
        return []


def search_by_tag(tag: str, limit: int = 10) -> List[MBArtist]:
    """
    Search artists by genre/style tag.

    Args:
        tag: Genre or style tag (e.g., "doom metal", "dark folk")
        limit: Max results

    Returns:
        List of MBArtist results
    """
    return search_artists(tag=tag, limit=limit)


def get_similar_by_tags(artist: MBArtist, limit: int = 10) -> List[MBArtist]:
    """
    Find similar artists based on shared tags.

    MusicBrainz doesn't have direct "similar artists" API,
    so we search for artists with the same tags.

    Args:
        artist: Source artist
        limit: Max results

    Returns:
        List of similar MBArtist results
    """
    if not artist.tags:
        return []

    # Search by first 2 tags
    results = []
    seen_mbids = {artist.mbid}

    for tag in artist.tags[:2]:
        _rate_limit()
        try:
            found = search_artists(tag=tag, limit=limit)
            for a in found:
                if a.mbid not in seen_mbids:
                    seen_mbids.add(a.mbid)
                    results.append(a)
        except Exception:
            continue

    return results[:limit]


# ==============================================================================
# BRIDGE ATTRIBUTE → TAG MAPPING
# ==============================================================================
# Import from taxonomy module for consistency with movies/books skills
from .taxonomy import BRIDGE_TO_TAGS, get_tags_for_bridge


def search_by_bridge(bridge: str, limit: int = 10) -> List[MBArtist]:
    """
    Search artists by HMT bridge attribute.

    Args:
        bridge: Bridge attribute name (Precision, Resilience, etc.)
        limit: Max results per tag

    Returns:
        List of MBArtist results
    """
    tags = get_tags_for_bridge(bridge)
    if not tags:
        return []

    results = []
    seen_mbids = set()

    for tag in tags[:3]:  # Search first 3 tags
        found = search_artists(tag=tag, limit=limit)
        for a in found:
            if a.mbid not in seen_mbids:
                seen_mbids.add(a.mbid)
                results.append(a)

    return results[:limit]
