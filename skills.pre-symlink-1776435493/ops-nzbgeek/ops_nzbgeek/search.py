"""NZBGeek API search module."""

import os
from pathlib import Path
from typing import Optional
import httpx
from dotenv import load_dotenv

# Load environment variables from repo root
REPO_ROOT = Path.home() / "workspace" / "experiments" / "pi-mono"
ENV_FILE = REPO_ROOT / ".env"
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)
else:
    load_dotenv()  # Fallback to default search

# NZBGeek API configuration
NZB_API_KEY = os.getenv("NZBD_GEEK_API_KEY")
NZB_BASE_URL = os.getenv("NZBD_GEEK_BASE_URL", "https://api.nzbgeek.info/")

# Category mappings
CATEGORY_MAP = {
    "movies": "2000",
    "tv": "5000",
    "music": "3000",
    "apps": "4000",
    "books": "7000",
    "all": "",
}


def get_requests_session() -> httpx.Client:
    """Get an httpx client with retry logic."""
    transport = httpx.HTTPTransport(retries=3)
    client = httpx.Client(transport=transport, timeout=30.0)
    return client


def search_nzb(
    query: str,
    category: str = "all",
    limit: int = 10,
    offset: int = 0,
) -> list[dict]:
    """
    Search NZBGeek for content.

    Args:
        query: Search query string
        category: Category filter (movies, tv, music, apps, books, all)
        limit: Maximum number of results
        offset: Result offset for pagination

    Returns:
        List of search results with keys: title, size, pubDate, link, category

    Raises:
        ValueError: If API key is missing or category is invalid
        httpx.HTTPError: If API request fails
    """
    if not NZB_API_KEY:
        raise ValueError("NZBD_GEEK_API_KEY environment variable not set")

    if category not in CATEGORY_MAP:
        raise ValueError(
            f"Invalid category: {category}. Must be one of: {', '.join(CATEGORY_MAP.keys())}"
        )

    cat_id = CATEGORY_MAP[category]

    params = {
        "t": "search",
        "q": query,
        "apikey": NZB_API_KEY,
        "o": "json",
        "limit": limit,
        "offset": offset,
    }

    if cat_id:  # Only add category if not "all"
        params["cat"] = cat_id

    url = f"{NZB_BASE_URL.rstrip('/')}/api"
    session = get_requests_session()

    try:
        resp = session.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as e:
        raise httpx.HTTPError(f"NZBGeek API request failed: {e}")

    # Parse response - handle both single item and array
    items = []
    if "channel" in data and "item" in data["channel"]:
        raw_items = data["channel"]["item"]
        # NZBGeek returns single dict if 1 result, list if multiple
        if isinstance(raw_items, dict):
            raw_items = [raw_items]
        items = raw_items

    # Normalize results
    results = []
    for item in items:
        results.append({
            "title": item.get("title", ""),
            "size": int(item.get("size", 0)),
            "pubDate": item.get("pubDate", ""),
            "link": item.get("link", ""),
            "category": item.get("category", ""),
            "guid": item.get("guid", ""),
            "description": item.get("description", ""),
        })

    return results[:limit]


def format_search_results(results: list[dict], json_output: bool = False) -> str:
    """
    Format search results for display.

    Args:
        results: List of search result dicts
        json_output: If True, return JSON string

    Returns:
        Formatted string (human-readable or JSON)
    """
    if json_output:
        import json
        return json.dumps(results, indent=2)

    if not results:
        return "No results found."

    output = []
    for i, r in enumerate(results, 1):
        size_gb = r["size"] / (1024 ** 3) if r["size"] > 0 else 0
        output.append(
            f"{i}. {r['title']}\n"
            f"   Size: {size_gb:.2f} GB | Date: {r['pubDate']}\n"
            f"   Link: {r['link']}\n"
        )

    return "\n".join(output)
