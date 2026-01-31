#!/usr/bin/env python3
"""
ListenBrainz client for discover-music skill.

ListenBrainz provides:
- Similar artists based on listening data
- Site-wide trending/popular artists
- User recommendations (requires token)
- Listen history analysis

Token is optional - public endpoints work without authentication.
"""

import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

# API base URL
BASE_URL = "https://api.listenbrainz.org/1"

# Rate limiting
_last_request_time = 0.0
_min_request_interval = 0.5  # seconds (ListenBrainz is more lenient)


def _rate_limit():
    """Ensure minimum interval between requests."""
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < _min_request_interval:
        time.sleep(_min_request_interval - elapsed)
    _last_request_time = time.time()


def _get_token() -> Optional[str]:
    """Get ListenBrainz token from environment."""
    return os.environ.get("LISTENBRAINZ_TOKEN")


def _make_request(
    endpoint: str,
    params: Optional[Dict] = None,
    authenticated: bool = False,
) -> Optional[Dict]:
    """Make a request to ListenBrainz API."""
    _rate_limit()

    url = f"{BASE_URL}/{endpoint.lstrip('/')}"
    headers = {}

    if authenticated:
        token = _get_token()
        if token:
            headers["Authorization"] = f"Token {token}"

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"ListenBrainz API error: {resp.status_code}")
            return None
    except Exception as e:
        print(f"ListenBrainz request error: {e}")
        return None


@dataclass
class LBArtist:
    """ListenBrainz artist result."""
    name: str
    mbid: str = ""
    listen_count: int = 0
    similarity: float = 0.0


@dataclass
class LBRecommendation:
    """ListenBrainz recommendation result."""
    recording_name: str
    recording_mbid: str
    artist_name: str
    artist_mbid: str
    score: float = 0.0


def get_similar_artists(artist_name: str, limit: int = 10) -> List[LBArtist]:
    """
    Get artists similar to the given artist.

    Uses ListenBrainz's LB Radio similar artist endpoint.

    Args:
        artist_name: Artist name to find similar artists for
        limit: Max results

    Returns:
        List of LBArtist results
    """
    # Try the explore endpoint first
    data = _make_request(
        f"/explore/lb-radio/artist/{artist_name}/similar",
        params={"limit": limit}
    )

    if data and "payload" in data:
        similar = data["payload"].get("similar", [])
        return [
            LBArtist(
                name=a.get("artist_name", a.get("name", "Unknown")),
                mbid=a.get("artist_mbid", a.get("mbid", "")),
                similarity=float(a.get("score", 0)),
            )
            for a in similar[:limit]
        ]

    # Fallback: try artist credit endpoint
    data = _make_request(
        "/explore/similar-artists",
        params={"artist_name": artist_name, "limit": limit}
    )

    if data and "payload" in data:
        return [
            LBArtist(
                name=a.get("artist_name", "Unknown"),
                mbid=a.get("artist_mbid", ""),
                similarity=float(a.get("score", 0)),
            )
            for a in data["payload"][:limit]
        ]

    return []


def get_trending_artists(
    time_range: str = "week",
    limit: int = 10,
) -> List[LBArtist]:
    """
    Get trending/popular artists site-wide.

    Args:
        time_range: "week", "month", "year", or "all_time"
        limit: Max results

    Returns:
        List of LBArtist with listen counts
    """
    data = _make_request(
        "/stats/sitewide/artists",
        params={"count": limit, "range": time_range}
    )

    if data and "payload" in data:
        artists = data["payload"].get("artists", [])
        return [
            LBArtist(
                name=a.get("artist_name", "Unknown"),
                mbid=a.get("artist_mbid", ""),
                listen_count=int(a.get("listen_count", 0)),
            )
            for a in artists[:limit]
        ]

    return []


def get_user_recommendations(
    username: str,
    limit: int = 10,
) -> List[LBRecommendation]:
    """
    Get personalized recommendations for a user.

    Requires LISTENBRAINZ_TOKEN to be set.

    Args:
        username: ListenBrainz username
        limit: Max results

    Returns:
        List of LBRecommendation
    """
    data = _make_request(
        f"/cf/recommendation/user/{username}/recording",
        params={"count": limit},
        authenticated=True
    )

    if data and "payload" in data:
        recs = data["payload"].get("mbids", [])
        return [
            LBRecommendation(
                recording_name=r.get("recording_name", "Unknown"),
                recording_mbid=r.get("recording_mbid", ""),
                artist_name=r.get("artist_name", "Unknown"),
                artist_mbid=r.get("artist_mbid", ""),
                score=float(r.get("score", 0)),
            )
            for r in recs[:limit]
        ]

    return []


def get_user_artists(
    username: str,
    time_range: str = "all_time",
    limit: int = 10,
) -> List[LBArtist]:
    """
    Get a user's top artists.

    Args:
        username: ListenBrainz username
        time_range: "week", "month", "year", or "all_time"
        limit: Max results

    Returns:
        List of LBArtist with listen counts
    """
    data = _make_request(
        f"/stats/user/{username}/artists",
        params={"count": limit, "range": time_range}
    )

    if data and "payload" in data:
        artists = data["payload"].get("artists", [])
        return [
            LBArtist(
                name=a.get("artist_name", "Unknown"),
                mbid=a.get("artist_mbid", ""),
                listen_count=int(a.get("listen_count", 0)),
            )
            for a in artists[:limit]
        ]

    return []


def explore_fresh_releases(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get fresh/new releases from ListenBrainz.

    Args:
        limit: Max results

    Returns:
        List of release dicts
    """
    data = _make_request(
        "/explore/fresh-releases",
        params={"limit": limit}
    )

    if data and "payload" in data:
        return data["payload"].get("releases", [])[:limit]

    return []


def is_authenticated() -> bool:
    """Check if ListenBrainz token is configured."""
    return _get_token() is not None
