"""
OpenLibrary client for discover-books skill.

OpenLibrary provides:
- Book search by title, author, subject
- Work details with subjects/genres
- Author bibliographies
- Trending/popular lists

Free API - no key required.
Rate limit: ~100 requests/5 min (self-imposed 0.5 req/sec for safety).
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests

# OpenLibrary API configuration
OL_BASE_URL = "https://openlibrary.org"
OL_SEARCH_URL = "https://openlibrary.org/search.json"

# Rate limiting
_last_request_time = 0.0
_min_request_interval = 0.5  # 2 req/sec max


def _rate_limit():
    """Ensure minimum interval between requests."""
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < _min_request_interval:
        time.sleep(_min_request_interval - elapsed)
    _last_request_time = time.time()


def _api_request(url: str, params: Optional[Dict] = None) -> Optional[Dict]:
    """Make API request with error handling."""
    _rate_limit()
    params = params or {}

    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"OpenLibrary API error: {e}")
        return None


@dataclass
class OLBook:
    """OpenLibrary book result."""
    key: str  # OpenLibrary work key (e.g., /works/OL45804W)
    title: str
    author_name: List[str] = field(default_factory=list)
    author_key: List[str] = field(default_factory=list)
    first_publish_year: int = 0
    subjects: List[str] = field(default_factory=list)
    description: str = ""
    cover_i: int = 0  # Cover image ID
    edition_count: int = 0

    @property
    def year(self) -> str:
        """Publication year as string."""
        return str(self.first_publish_year) if self.first_publish_year else ""

    @property
    def authors(self) -> str:
        """Authors as comma-separated string."""
        return ", ".join(self.author_name) if self.author_name else "Unknown"

    @property
    def cover_url(self) -> str:
        """Cover image URL."""
        if self.cover_i:
            return f"https://covers.openlibrary.org/b/id/{self.cover_i}-L.jpg"
        return ""

    @property
    def ol_url(self) -> str:
        """OpenLibrary URL for this work."""
        return f"https://openlibrary.org{self.key}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON output."""
        return {
            "key": self.key,
            "title": self.title,
            "authors": self.authors,
            "author_list": self.author_name,
            "year": self.year,
            "subjects": self.subjects[:10],  # Limit subjects
            "description": self.description[:500] if self.description else "",
            "cover_url": self.cover_url,
            "ol_url": self.ol_url,
            "edition_count": self.edition_count,
        }


def _parse_search_result(data: Dict) -> OLBook:
    """Parse search API response to OLBook."""
    # Handle description which can be string or dict
    description = data.get("description", "")
    if isinstance(description, dict):
        description = description.get("value", "")

    return OLBook(
        key=data.get("key", ""),
        title=data.get("title", "Unknown"),
        author_name=data.get("author_name", []),
        author_key=data.get("author_key", []),
        first_publish_year=data.get("first_publish_year", 0),
        subjects=data.get("subject", [])[:20],  # Limit subjects
        description=description,
        cover_i=data.get("cover_i", 0),
        edition_count=data.get("edition_count", 0),
    )


def search_books(query: str, limit: int = 10) -> List[OLBook]:
    """
    Search books by title.

    Args:
        query: Book title to search
        limit: Max results

    Returns:
        List of OLBook results
    """
    params = {
        "q": query,
        "limit": limit,
        "fields": "key,title,author_name,author_key,first_publish_year,subject,cover_i,edition_count",
    }
    data = _api_request(OL_SEARCH_URL, params)
    if not data:
        return []

    results = data.get("docs", [])[:limit]
    return [_parse_search_result(r) for r in results]


def search_by_author(author: str, limit: int = 10) -> List[OLBook]:
    """
    Search books by author name.

    Args:
        author: Author name
        limit: Max results

    Returns:
        List of OLBook results
    """
    params = {
        "author": author,
        "limit": limit,
        "sort": "editions",  # Sort by number of editions (popularity)
        "fields": "key,title,author_name,author_key,first_publish_year,subject,cover_i,edition_count",
    }
    data = _api_request(OL_SEARCH_URL, params)
    if not data:
        return []

    results = data.get("docs", [])[:limit]
    return [_parse_search_result(r) for r in results]


def search_by_subject(subject: str, limit: int = 10) -> List[OLBook]:
    """
    Search books by subject/genre.

    Args:
        subject: Subject or genre name
        limit: Max results

    Returns:
        List of OLBook results
    """
    params = {
        "subject": subject,
        "limit": limit,
        "sort": "editions",
        "fields": "key,title,author_name,author_key,first_publish_year,subject,cover_i,edition_count",
    }
    data = _api_request(OL_SEARCH_URL, params)
    if not data:
        return []

    results = data.get("docs", [])[:limit]
    return [_parse_search_result(r) for r in results]


def get_work(work_key: str) -> Optional[OLBook]:
    """
    Get work details by key.

    Args:
        work_key: OpenLibrary work key (e.g., /works/OL45804W or OL45804W)

    Returns:
        OLBook or None
    """
    # Normalize key
    if not work_key.startswith("/works/"):
        work_key = f"/works/{work_key}"

    data = _api_request(f"{OL_BASE_URL}{work_key}.json")
    if not data:
        return None

    # Work API has different structure than search
    description = data.get("description", "")
    if isinstance(description, dict):
        description = description.get("value", "")

    subjects = data.get("subjects", [])

    return OLBook(
        key=work_key,
        title=data.get("title", "Unknown"),
        subjects=subjects[:20],
        description=description,
        cover_i=data.get("covers", [0])[0] if data.get("covers") else 0,
    )


def get_trending(limit: int = 10) -> List[OLBook]:
    """
    Get trending/popular books.

    OpenLibrary doesn't have a true trending API, so we use highly-rated
    fiction works with many editions as a proxy.

    Args:
        limit: Max results

    Returns:
        List of popular OLBook results
    """
    # Search for popular fiction
    params = {
        "subject": "fiction",
        "limit": limit,
        "sort": "editions",  # Most editions = most popular
        "fields": "key,title,author_name,author_key,first_publish_year,subject,cover_i,edition_count",
    }
    data = _api_request(OL_SEARCH_URL, params)
    if not data:
        return []

    results = data.get("docs", [])[:limit]
    return [_parse_search_result(r) for r in results]


def get_new_releases(limit: int = 10) -> List[OLBook]:
    """
    Get recent/new releases.

    Uses current year as filter for fresh books.

    Args:
        limit: Max results

    Returns:
        List of recent OLBook results
    """
    import datetime
    current_year = datetime.datetime.now().year

    params = {
        "first_publish_year": f"[{current_year - 1} TO {current_year}]",
        "limit": limit,
        "sort": "new",
        "fields": "key,title,author_name,author_key,first_publish_year,subject,cover_i,edition_count",
    }
    data = _api_request(OL_SEARCH_URL, params)
    if not data:
        return []

    results = data.get("docs", [])[:limit]
    return [_parse_search_result(r) for r in results]


def check_api() -> bool:
    """
    Test API connectivity.

    Returns:
        True if API is accessible
    """
    data = _api_request(OL_SEARCH_URL, {"q": "test", "limit": 1})
    return data is not None and "docs" in data
