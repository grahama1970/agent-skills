#!/usr/bin/env python3
"""
Taste-based recommendation engine for discover-music.

Reads the taste profile built by ingest-yt-history and generates
recommendations using MusicBrainz/ListenBrainz, optionally queuing
artists for learn-artist training.

Usage:
    from .recommend import recommend_from_profile

    results = recommend_from_profile(
        profile_path="~/.pi/ingest-yt-history/profile.json",
        limit=20,
    )
"""
from __future__ import annotations

from loguru import logger

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import listenbrainz_client as lb
from . import musicbrainz_client as mb
from . import taxonomy

# Persona-guided scoring (graceful fallback)
try:
    _SKILLS_DIR = str(Path(__file__).resolve().parent.parent.parent)
    if _SKILLS_DIR not in sys.path:
        sys.path.insert(0, _SKILLS_DIR)
    from common.discovery import load_persona_state, persona_bridge_weights
    _PERSONA_AVAILABLE = True
except ImportError:
    _PERSONA_AVAILABLE = False


@dataclass
class Recommendation:
    """A single artist recommendation."""
    name: str
    mbid: str = ""
    tags: List[str] = field(default_factory=list)
    similarity: float = 0.0
    source_artist: str = ""  # Which top artist led to this recommendation
    bridge_tags: List[str] = field(default_factory=list)
    reason: str = ""  # Why recommended


@dataclass
class RecommendationResult:
    """Full recommendation output."""
    recommendations: List[Recommendation] = field(default_factory=list)
    profile_summary: Dict[str, Any] = field(default_factory=dict)
    already_known: List[str] = field(default_factory=list)  # Artists already in history
    queue_candidates: List[str] = field(default_factory=list)  # Artists suitable for training


def load_taste_profile(profile_path: Optional[str | Path] = None) -> dict:
    """
    Load taste profile from ingest-yt-history.

    Checks multiple locations:
    1. Explicit path
    2. ~/.pi/ingest-yt-history/profile.json
    3. Artist profiles JSON
    """
    candidates = []
    if profile_path:
        candidates.append(Path(profile_path))
    candidates.extend([
        Path.home() / ".pi" / "ingest-yt-history" / "profile.json",
        Path.home() / ".pi" / "ingest-yt-history" / "artist_profiles.json",
    ])

    for path in candidates:
        if path.exists():
            with open(path) as f:
                return json.load(f)

    raise FileNotFoundError(
        f"No taste profile found. Run: ingest-yt-history profile <history.jsonl>"
    )


def load_artist_profiles(profile_path: Optional[str | Path] = None) -> dict:
    """Load enriched artist profiles if available."""
    candidates = []
    if profile_path:
        candidates.append(Path(profile_path))
    candidates.append(Path.home() / ".pi" / "ingest-yt-history" / "artist_profiles.json")

    for path in candidates:
        if path.exists():
            with open(path) as f:
                return json.load(f)

    return {}


def recommend_from_profile(
    profile_path: Optional[str | Path] = None,
    limit: int = 20,
    per_artist: int = 5,
    use_bridges: bool = True,
) -> RecommendationResult:
    """
    Generate recommendations from the user's taste profile.

    Strategy:
    1. Get top artists from profile
    2. For each top artist, find similar artists via ListenBrainz/MusicBrainz
    3. For each top bridge attribute, find tagged artists
    4. Deduplicate and rank by frequency across sources
    5. Filter out artists already in the user's history

    Args:
        profile_path: Path to taste profile JSON.
        limit: Total recommendations to return.
        per_artist: Similar artists to find per top artist.
        use_bridges: Also search by bridge attributes.

    Returns:
        RecommendationResult with ranked recommendations.
    """
    profile = load_taste_profile(profile_path)
    artist_profiles = load_artist_profiles()

    # Extract known artists (to filter out)
    known_artists = set()
    top_artists = profile.get("top_artists", [])
    for a in top_artists:
        known_artists.add(a.get("artist", "").lower())

    # Also check enriched profiles
    if "artists" in artist_profiles:
        for a in artist_profiles["artists"]:
            known_artists.add(a.get("name", "").lower())

    # Collect recommendations with scoring
    candidates: Dict[str, Recommendation] = {}

    # Strategy 1: Similar artists for each top artist
    for artist_info in top_artists[:5]:
        artist_name = artist_info.get("artist", "")
        if not artist_name:
            continue

        try:
            similar = lb.get_similar_artists(artist_name, limit=per_artist)
            if not similar:
                # Fallback to MusicBrainz
                mb_results = mb.search_artists(query=artist_name, limit=1)
                if mb_results:
                    full = mb.get_artist(mb_results[0].mbid)
                    if full:
                        tag_similar = mb.get_similar_by_tags(full, limit=per_artist)
                        similar = [
                            lb.LBArtist(name=a.name, mbid=a.mbid, similarity=a.score / 100)
                            for a in tag_similar
                        ]

            for s in similar:
                name_lower = s.name.lower()
                if name_lower in known_artists:
                    continue

                if name_lower not in candidates:
                    candidates[name_lower] = Recommendation(
                        name=s.name,
                        mbid=s.mbid,
                        similarity=s.similarity or 0.5,
                        source_artist=artist_name,
                        reason=f"Similar to {artist_name}",
                    )
                else:
                    # Boost score for appearing in multiple artist similarities
                    candidates[name_lower].similarity += 0.2
        except Exception as e:
            print(f"Warning: similar search failed for {artist_name}: {e}", file=sys.stderr)

    # Strategy 2: Search by bridge attributes
    if use_bridges:
        top_bridges = profile.get("top_bridge_attributes", [])
        for bridge_attr in top_bridges[:3]:
            try:
                bridge_results = mb.search_by_bridge(bridge_attr, limit=per_artist)
                for r in bridge_results:
                    name_lower = r.name.lower()
                    if name_lower in known_artists:
                        continue

                    bridge_tags = taxonomy.extract_bridge_tags(
                        getattr(r, 'tags', []),
                        getattr(r, 'disambiguation', ''),
                    )

                    if name_lower not in candidates:
                        candidates[name_lower] = Recommendation(
                            name=r.name,
                            mbid=r.mbid,
                            tags=getattr(r, 'tags', []),
                            similarity=0.4,
                            bridge_tags=bridge_tags,
                            reason=f"Bridge: {bridge_attr}",
                        )
                    else:
                        candidates[name_lower].similarity += 0.15
                        candidates[name_lower].bridge_tags = list(
                            set(candidates[name_lower].bridge_tags + bridge_tags)
                        )
            except Exception as e:
                print(f"Warning: bridge search failed for {bridge_attr}: {e}", file=sys.stderr)

    # Apply persona bridge weights to boost aligned candidates
    if _PERSONA_AVAILABLE:
        try:
            state = load_persona_state()
            weights = persona_bridge_weights(state)
            for rec in candidates.values():
                if rec.bridge_tags:
                    persona_boost = sum(weights.get(b, 0.5) for b in rec.bridge_tags) / len(rec.bridge_tags)
                    rec.similarity += 0.15 * persona_boost
        except Exception as e:
            logger.debug("persona bridge tag boost failed: {}", e)

    # Rank by combined score
    ranked = sorted(candidates.values(), key=lambda r: r.similarity, reverse=True)[:limit]

    # Mark queue candidates (artists not yet trained)
    queue_candidates = [r.name for r in ranked]

    return RecommendationResult(
        recommendations=ranked,
        profile_summary={
            "top_artists": [a.get("artist") for a in top_artists[:5]],
            "top_bridges": profile.get("top_bridge_attributes", [])[:3],
            "total_tracks": profile.get("total_tracks", 0),
        },
        already_known=list(known_artists)[:20],
        queue_candidates=queue_candidates,
    )


def append_to_training_queue(
    artists: List[str],
    queue_path: Optional[str | Path] = None,
) -> int:
    """
    Append recommended artists to the learn-artist training queue.

    Args:
        artists: List of artist names to queue.
        queue_path: Path to queue.txt. Defaults to learn-artist default.

    Returns:
        Number of artists actually added (excluding duplicates).
    """
    if queue_path is None:
        queue_path = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb")) / "media/music/rvc-models/queue.txt"

    queue_path = Path(queue_path)

    # Read existing queue
    existing = set()
    if queue_path.exists():
        with open(queue_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    # Extract artist name (before any --flags)
                    name = line.split("--")[0].strip()
                    existing.add(name.lower())

    # Append new artists
    added = 0
    with open(queue_path, "a") as f:
        for artist in artists:
            if artist.lower() not in existing:
                f.write(f"{artist}\n")
                existing.add(artist.lower())
                added += 1

    return added
