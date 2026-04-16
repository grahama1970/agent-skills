"""
TMDB (The Movie Database) client for discover-talent skill.

TMDB provides:
- Person search by name
- Person details (bio, known-for)
- Person movie credits (filmography)
- Person images (profile photos)
- Movie cast lookup

Free API with generous limits (1000 req/day).
Rate limit: ~40 requests per 10 seconds (self-imposed 1 req/sec for safety).
"""

import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx
from dotenv import find_dotenv, load_dotenv

# Load .env file if present
load_dotenv(find_dotenv(usecwd=True))

# TMDB API configuration
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "")
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p"

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
        with httpx.Client(timeout=10) as client:
            response = client.get(url, headers=_get_headers(), params=params)

            # If 401, fall back to v3 API key as query param
            if response.status_code == 401:
                params["api_key"] = TMDB_API_KEY
                response = client.get(url, params=params)

            response.raise_for_status()
            return response.json()
    except httpx.RequestError as e:
        print(f"TMDB API error: {e}")
        return None
    except ValueError as e:
        print(f"TMDB config error: {e}")
        return None


@dataclass
class KnownForMovie:
    """A movie an actor is known for."""
    id: int
    title: str
    release_date: str
    genre_ids: List[int] = field(default_factory=list)
    
    @property
    def year(self) -> str:
        """Extract year from release date."""
        if self.release_date:
            return self.release_date[:4]
        return ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "year": self.year,
            "genre_ids": self.genre_ids,
        }


@dataclass
class TMDBPerson:
    """TMDB person/actor result."""
    id: int
    name: str
    known_for_department: str
    popularity: float = 0.0
    profile_path: str = ""
    known_for: List[KnownForMovie] = field(default_factory=list)
    biography: str = ""
    birthday: str = ""
    place_of_birth: str = ""
    character: str = ""  # When from movie cast
    
    @property
    def profile_url(self) -> str:
        """Full profile image URL (w500 size)."""
        if self.profile_path:
            return f"{TMDB_IMAGE_BASE}/w500{self.profile_path}"
        return ""
    
    @property
    def profile_url_original(self) -> str:
        """Full profile image URL (original size)."""
        if self.profile_path:
            return f"{TMDB_IMAGE_BASE}/original{self.profile_path}"
        return ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON output."""
        result = {
            "id": self.id,
            "name": self.name,
            "known_for_department": self.known_for_department,
            "popularity": self.popularity,
            "profile_url": self.profile_url,
        }
        if self.known_for:
            result["known_for"] = [m.to_dict() for m in self.known_for]
        if self.biography:
            result["biography"] = self.biography[:500]  # Truncate long bios
        if self.birthday:
            result["birthday"] = self.birthday
        if self.place_of_birth:
            result["place_of_birth"] = self.place_of_birth
        if self.character:
            result["character"] = self.character
        return result


@dataclass
class PersonImage:
    """A profile image for a person."""
    file_path: str
    width: int
    height: int
    vote_average: float = 0.0
    
    @property
    def url(self) -> str:
        """Full image URL (w500 size)."""
        return f"{TMDB_IMAGE_BASE}/w500{self.file_path}"
    
    @property
    def url_original(self) -> str:
        """Full image URL (original size)."""
        return f"{TMDB_IMAGE_BASE}/original{self.file_path}"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "url_original": self.url_original,
            "width": self.width,
            "height": self.height,
            "vote_average": self.vote_average,
        }


# Genre ID to name mapping (cached from TMDB)
GENRE_CACHE: Dict[int, str] = {
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


def _parse_known_for(data: List[Dict]) -> List[KnownForMovie]:
    """Parse known_for movies from search results."""
    movies = []
    for item in data:
        if item.get("media_type") == "movie":
            movies.append(KnownForMovie(
                id=item.get("id", 0),
                title=item.get("title", "Unknown"),
                release_date=item.get("release_date", ""),
                genre_ids=item.get("genre_ids", []),
            ))
    return movies


def _parse_person(data: Dict, include_details: bool = False) -> TMDBPerson:
    """Parse API response to TMDBPerson."""
    known_for = _parse_known_for(data.get("known_for", []))
    
    person = TMDBPerson(
        id=data.get("id", 0),
        name=data.get("name", "Unknown"),
        known_for_department=data.get("known_for_department", "Acting"),
        popularity=data.get("popularity", 0.0),
        profile_path=data.get("profile_path", ""),
        known_for=known_for,
        character=data.get("character", ""),
    )
    
    if include_details:
        person.biography = data.get("biography", "")
        person.birthday = data.get("birthday", "")
        person.place_of_birth = data.get("place_of_birth", "")
    
    return person


def search_people(query: str, limit: int = 10) -> List[TMDBPerson]:
    """
    Search for people (actors, directors) by name.

    Args:
        query: Person name to search
        limit: Max results

    Returns:
        List of TMDBPerson results
    """
    data = _api_request("/search/person", {"query": query})
    if not data:
        return []

    results = data.get("results", [])[:limit]
    return [_parse_person(p) for p in results]


def get_person(person_id: int) -> Optional[TMDBPerson]:
    """
    Get detailed person information by ID.

    Args:
        person_id: TMDB person ID

    Returns:
        TMDBPerson with full details or None
    """
    data = _api_request(f"/person/{person_id}")
    if not data:
        return None
    return _parse_person(data, include_details=True)


def get_person_images(person_id: int, limit: int = 5) -> List[PersonImage]:
    """
    Get profile images for a person.

    Args:
        person_id: TMDB person ID
        limit: Max images

    Returns:
        List of PersonImage
    """
    data = _api_request(f"/person/{person_id}/images")
    if not data:
        return []

    profiles = data.get("profiles", [])[:limit]
    return [
        PersonImage(
            file_path=p.get("file_path", ""),
            width=p.get("width", 0),
            height=p.get("height", 0),
            vote_average=p.get("vote_average", 0.0),
        )
        for p in profiles
    ]


@dataclass
class MovieCredit:
    """A movie credit (role in a film)."""
    id: int
    title: str
    release_date: str
    character: str
    genre_ids: List[int] = field(default_factory=list)
    popularity: float = 0.0
    job: str = ""  # For crew credits
    
    @property
    def year(self) -> str:
        if self.release_date:
            return self.release_date[:4]
        return ""
    
    @property
    def genres(self) -> List[str]:
        return [GENRE_CACHE.get(gid, "") for gid in self.genre_ids if gid in GENRE_CACHE]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "year": self.year,
            "character": self.character,
            "genres": self.genres,
            "popularity": self.popularity,
        }


def get_person_movie_credits(
    person_id: int,
    limit: int = 10,
    department: str = "Acting"
) -> List[MovieCredit]:
    """
    Get movie credits for a person.

    Args:
        person_id: TMDB person ID
        limit: Max results
        department: "Acting" or "Directing"

    Returns:
        List of MovieCredit sorted by popularity
    """
    data = _api_request(f"/person/{person_id}/movie_credits")
    if not data:
        return []

    if department == "Acting":
        credits_data = data.get("cast", [])
    else:
        credits_data = [c for c in data.get("crew", []) if c.get("job") == "Director"]

    # Sort by popularity and limit
    credits_data = sorted(credits_data, key=lambda x: x.get("popularity", 0), reverse=True)[:limit]
    
    return [
        MovieCredit(
            id=c.get("id", 0),
            title=c.get("title", "Unknown"),
            release_date=c.get("release_date", ""),
            character=c.get("character", ""),
            genre_ids=c.get("genre_ids", []),
            popularity=c.get("popularity", 0.0),
            job=c.get("job", ""),
        )
        for c in credits_data
    ]


def search_movie(query: str) -> Optional[int]:
    """
    Search for a movie and return its ID.

    Args:
        query: Movie title

    Returns:
        Movie ID or None
    """
    data = _api_request("/search/movie", {"query": query})
    if not data:
        return None

    results = data.get("results", [])
    if results:
        return results[0].get("id")
    return None


def get_movie_cast(movie_id: int, limit: int = 10) -> List[TMDBPerson]:
    """
    Get cast of a movie.

    Args:
        movie_id: TMDB movie ID
        limit: Max cast members

    Returns:
        List of TMDBPerson (with character field populated)
    """
    data = _api_request(f"/movie/{movie_id}/credits")
    if not data:
        return []

    cast = data.get("cast", [])[:limit]
    return [
        TMDBPerson(
            id=c.get("id", 0),
            name=c.get("name", "Unknown"),
            known_for_department=c.get("known_for_department", "Acting"),
            popularity=c.get("popularity", 0.0),
            profile_path=c.get("profile_path", ""),
            character=c.get("character", ""),
        )
        for c in cast
    ]


def discover_people_by_genre(genre_ids: List[int], limit: int = 10) -> List[TMDBPerson]:
    """
    Discover actors by finding popular movies in genres and extracting cast.
    
    This is a workaround since TMDB doesn't have direct "actors by genre" endpoint.

    Args:
        genre_ids: List of TMDB genre IDs
        limit: Max people to return

    Returns:
        List of TMDBPerson
    """
    # First discover popular movies in these genres
    params = {
        "with_genres": ",".join(str(g) for g in genre_ids),
        "sort_by": "popularity.desc",
    }
    data = _api_request("/discover/movie", params)
    if not data:
        return []

    # Get cast from top movies
    movies = data.get("results", [])[:3]  # Top 3 movies
    seen_ids = set()
    people = []
    
    for movie in movies:
        movie_id = movie.get("id")
        if movie_id:
            cast = get_movie_cast(movie_id, limit=5)
            for person in cast:
                if person.id not in seen_ids:
                    seen_ids.add(person.id)
                    people.append(person)
                    if len(people) >= limit:
                        return people
    
    return people


def check_api() -> bool:
    """
    Test API connectivity.

    Returns:
        True if API is accessible
    """
    data = _api_request("/configuration")
    return data is not None
