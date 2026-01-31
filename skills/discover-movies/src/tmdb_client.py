"""
TMDB (The Movie Database) client for discover-movies skill.

TMDB provides:
- Movie search by title, keywords
- Similar movies
- Trending movies (day/week)
- Movie details with genres
- Person (director) filmography

Free API with generous limits (1000 req/day).
Rate limit: ~40 requests per 10 seconds (self-imposed 1 req/sec for safety).
"""

import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests

# TMDB API configuration
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "")
TMDB_BASE_URL = "https://api.themoviedb.org/3"

# Rate limiting
_last_request_time = 0.0
_min_request_interval = 0.25  # 4 req/sec max


def _rate_limit():
    """Ensure minimum interval between requests."""
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < _min_request_interval:
        time.sleep(_min_request_interval - elapsed)
    _last_request_time = time.time()


def _get_headers() -> Dict[str, str]:
    """Get API headers. Prefer Bearer token over api_key param."""
    return {
        "Authorization": f"Bearer {TMDB_API_KEY}",
        "Accept": "application/json",
    }


def _api_request(endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
    """Make API request with error handling.

    Supports both:
    - v4 API Read Access Token (Bearer auth)
    - v3 API Key (query parameter)
    """
    _rate_limit()
    url = f"{TMDB_BASE_URL}{endpoint}"
    params = params or {}

    try:
        if not TMDB_API_KEY:
            raise ValueError("TMDB_API_KEY not set")

        # Try Bearer token first (v4 API Read Access Token)
        response = requests.get(url, headers=_get_headers(), params=params, timeout=10)

        # If 401, fall back to v3 API key as query param
        if response.status_code == 401:
            params["api_key"] = TMDB_API_KEY
            response = requests.get(url, params=params, timeout=10)

        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"TMDB API error: {e}")
        return None
    except ValueError as e:
        print(f"TMDB config error: {e}")
        return None


@dataclass
class TMDBMovie:
    """TMDB movie result."""
    id: int
    title: str
    overview: str
    release_date: str
    genres: List[str] = field(default_factory=list)
    genre_ids: List[int] = field(default_factory=list)
    vote_average: float = 0.0
    popularity: float = 0.0
    poster_path: str = ""

    @property
    def year(self) -> str:
        """Extract year from release date."""
        if self.release_date:
            return self.release_date[:4]
        return ""

    @property
    def poster_url(self) -> str:
        """Full poster URL."""
        if self.poster_path:
            return f"https://image.tmdb.org/t/p/w500{self.poster_path}"
        return ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON output."""
        return {
            "id": self.id,
            "title": self.title,
            "year": self.year,
            "overview": self.overview,
            "genres": self.genres,
            "vote_average": self.vote_average,
            "popularity": self.popularity,
            "poster_url": self.poster_url,
        }


# Genre ID to name mapping (cached from TMDB)
_GENRE_CACHE: Dict[int, str] = {
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


def _parse_movie(data: Dict) -> TMDBMovie:
    """Parse API response to TMDBMovie."""
    genre_ids = data.get("genre_ids", [])
    # If we have full genre objects (from details endpoint)
    if "genres" in data:
        genres = [g["name"] for g in data["genres"]]
    else:
        genres = [_GENRE_CACHE.get(gid, "") for gid in genre_ids if gid in _GENRE_CACHE]

    return TMDBMovie(
        id=data.get("id", 0),
        title=data.get("title", "Unknown"),
        overview=data.get("overview", ""),
        release_date=data.get("release_date", ""),
        genres=genres,
        genre_ids=genre_ids,
        vote_average=data.get("vote_average", 0.0),
        popularity=data.get("popularity", 0.0),
        poster_path=data.get("poster_path", ""),
    )


def search_movies(query: str, limit: int = 10) -> List[TMDBMovie]:
    """
    Search movies by title.

    Args:
        query: Movie title to search
        limit: Max results

    Returns:
        List of TMDBMovie results
    """
    data = _api_request("/search/movie", {"query": query})
    if not data:
        return []

    results = data.get("results", [])[:limit]
    return [_parse_movie(m) for m in results]


def get_movie(movie_id: int) -> Optional[TMDBMovie]:
    """
    Get movie details by ID.

    Args:
        movie_id: TMDB movie ID

    Returns:
        TMDBMovie or None
    """
    data = _api_request(f"/movie/{movie_id}")
    if not data:
        return None
    return _parse_movie(data)


def get_similar_movies(movie_id: int, limit: int = 10) -> List[TMDBMovie]:
    """
    Get movies similar to a given movie.

    Args:
        movie_id: TMDB movie ID
        limit: Max results

    Returns:
        List of similar TMDBMovie results
    """
    data = _api_request(f"/movie/{movie_id}/similar")
    if not data:
        return []

    results = data.get("results", [])[:limit]
    return [_parse_movie(m) for m in results]


def get_recommendations(movie_id: int, limit: int = 10) -> List[TMDBMovie]:
    """
    Get movie recommendations based on a movie.

    Args:
        movie_id: TMDB movie ID
        limit: Max results

    Returns:
        List of recommended TMDBMovie results
    """
    data = _api_request(f"/movie/{movie_id}/recommendations")
    if not data:
        return []

    results = data.get("results", [])[:limit]
    return [_parse_movie(m) for m in results]


def get_trending(time_window: str = "week", limit: int = 10) -> List[TMDBMovie]:
    """
    Get trending movies.

    Args:
        time_window: "day" or "week"
        limit: Max results

    Returns:
        List of trending TMDBMovie results
    """
    if time_window not in ("day", "week"):
        time_window = "week"

    data = _api_request(f"/trending/movie/{time_window}")
    if not data:
        return []

    results = data.get("results", [])[:limit]
    return [_parse_movie(m) for m in results]


def discover_by_genre(genre_ids: List[int], limit: int = 10) -> List[TMDBMovie]:
    """
    Discover movies by genre IDs.

    Args:
        genre_ids: List of TMDB genre IDs
        limit: Max results

    Returns:
        List of TMDBMovie results
    """
    params = {
        "with_genres": ",".join(str(g) for g in genre_ids),
        "sort_by": "popularity.desc",
    }
    data = _api_request("/discover/movie", params)
    if not data:
        return []

    results = data.get("results", [])[:limit]
    return [_parse_movie(m) for m in results]


def get_now_playing(limit: int = 10) -> List[TMDBMovie]:
    """
    Get movies currently in theaters (fresh releases).

    Args:
        limit: Max results

    Returns:
        List of TMDBMovie results
    """
    data = _api_request("/movie/now_playing")
    if not data:
        return []

    results = data.get("results", [])[:limit]
    return [_parse_movie(m) for m in results]


def search_person(name: str) -> Optional[int]:
    """
    Search for a person (director, actor) and get their ID.

    Args:
        name: Person name

    Returns:
        Person ID or None
    """
    data = _api_request("/search/person", {"query": name})
    if not data:
        return None

    results = data.get("results", [])
    if results:
        return results[0].get("id")
    return None


def get_person_movies(person_id: int, limit: int = 10, department: str = "Directing") -> List[TMDBMovie]:
    """
    Get movies by a person (director/actor).

    Args:
        person_id: TMDB person ID
        limit: Max results
        department: Filter by department (Directing, Acting)

    Returns:
        List of TMDBMovie results
    """
    data = _api_request(f"/person/{person_id}/movie_credits")
    if not data:
        return []

    # Get crew credits for directors
    if department == "Directing":
        credits = data.get("crew", [])
        credits = [c for c in credits if c.get("job") == "Director"]
    else:
        credits = data.get("cast", [])

    # Sort by popularity and limit
    credits = sorted(credits, key=lambda x: x.get("popularity", 0), reverse=True)[:limit]
    return [_parse_movie(c) for c in credits]


def check_api() -> bool:
    """
    Test API connectivity.

    Returns:
        True if API is accessible
    """
    data = _api_request("/configuration")
    return data is not None
