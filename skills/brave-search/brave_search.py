#!/usr/bin/env python3
"""Brave Search API client for web + local search.

Usage:
    python brave_search.py web "query" --count 10 --offset 0
    python brave_search.py local "pizza near Boston" --count 5
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

SKILLS_DIR = Path(__file__).resolve().parents[1]
if str(SKILLS_DIR) not in sys.path:
    sys.path.append(str(SKILLS_DIR))

try:
    from dotenv_helper import load_env as _load_env  # type: ignore
except Exception:
    def _load_env():
        try:
            from dotenv import load_dotenv, find_dotenv  # type: ignore
            load_dotenv(find_dotenv(usecwd=True), override=False)
        except Exception:
            pass

_load_env()

try:
    import typer
except ImportError:
    print("typer not installed. Run: pip install typer", file=sys.stderr)
    sys.exit(1)

app = typer.Typer(add_completion=False, help="Brave Search API - web + local search")

WEB_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
LOCAL_POIS_ENDPOINT = "https://api.search.brave.com/res/v1/local/pois"
LOCAL_DESC_ENDPOINT = "https://api.search.brave.com/res/v1/local/descriptions"

ENV_KEYS = ("BRAVE_API_KEY", "BRAVE_SEARCH_API_KEY")
ENV_PATHS = [".env", "../.env", "../../.env", "../../../.env"]


def _load_env_key(path: str) -> Optional[str]:
    if not os.path.exists(path):
        return None
    try:
        with open(path) as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                if key in ENV_KEYS:
                    return value.strip().strip('"').strip("'")
    except OSError:
        return None
    return None


def get_api_key() -> str:
    for key in ENV_KEYS:
        value = os.getenv(key)
        if value:
            return value
    for path in ENV_PATHS:
        value = _load_env_key(path)
        if value:
            return value
    raise ValueError("BRAVE_API_KEY or BRAVE_SEARCH_API_KEY not found in env or .env")


def _request_json(url: str, api_key: str) -> Dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "X-Subscription-Token": api_key,
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8") if exc.fp else ""
        raise RuntimeError(f"HTTP {exc.code}: {exc.reason}\n{body}") from exc


def _build_url(base: str, params: Dict[str, Any]) -> str:
    return f"{base}?{urllib.parse.urlencode(params, doseq=True)}"


def web_search(query: str, count: int = 10, offset: int = 0) -> Dict[str, Any]:
    api_key = get_api_key()
    count = max(1, min(count, 20))
    offset = max(0, min(offset, 9))
    url = _build_url(WEB_ENDPOINT, {"q": query, "count": count, "offset": offset})
    data = _request_json(url, api_key)

    results = []
    for item in data.get("web", {}).get("results", []):
        results.append({
            "title": item.get("title", ""),
            "description": item.get("description", ""),
            "url": item.get("url", ""),
        })

    return {
        "query": query,
        "count": count,
        "offset": offset,
        "results": results,
    }


def local_search(query: str, count: int = 5) -> Dict[str, Any]:
    api_key = get_api_key()
    count = max(1, min(count, 20))
    url = _build_url(
        WEB_ENDPOINT,
        {
            "q": query,
            "count": count,
            "search_lang": "en",
            "result_filter": "locations",
        },
    )
    data = _request_json(url, api_key)
    location_ids = [
        item.get("id")
        for item in data.get("locations", {}).get("results", [])
        if item.get("id")
    ]

    if not location_ids:
        fallback = web_search(query, count=count)
        fallback["fallback"] = "web"
        return fallback

    pois_url = _build_url(LOCAL_POIS_ENDPOINT, {"ids": location_ids})
    desc_url = _build_url(LOCAL_DESC_ENDPOINT, {"ids": location_ids})
    pois_data = _request_json(pois_url, api_key)
    desc_data = _request_json(desc_url, api_key)
    desc_map = desc_data.get("descriptions", {})

    results = []
    for poi in pois_data.get("results", []):
        address_parts = [
            poi.get("address", {}).get("streetAddress"),
            poi.get("address", {}).get("addressLocality"),
            poi.get("address", {}).get("addressRegion"),
            poi.get("address", {}).get("postalCode"),
        ]
        address = ", ".join([part for part in address_parts if part])
        results.append({
            "id": poi.get("id"),
            "name": poi.get("name", ""),
            "address": address,
            "phone": poi.get("phone"),
            "rating": poi.get("rating", {}),
            "opening_hours": poi.get("openingHours", []),
            "price_range": poi.get("priceRange"),
            "coordinates": poi.get("coordinates", {}),
            "description": desc_map.get(poi.get("id"), ""),
        })

    return {
        "query": query,
        "count": count,
        "results": results,
    }


def _print_web(results: Dict[str, Any]) -> None:
    items = results.get("results", [])
    if not items:
        print("No results.")
        return
    for idx, item in enumerate(items, start=1):
        print(f"{idx}. {item.get('title', '')}")
        print(f"   {item.get('description', '')}")
        print(f"   {item.get('url', '')}\n")


def _print_local(results: Dict[str, Any]) -> None:
    items = results.get("results", [])
    if results.get("fallback") == "web":
        print("No local results. Falling back to web search.\n")
        _print_web(results)
        return
    if not items:
        print("No local results.")
        return
    for idx, item in enumerate(items, start=1):
        print(f"{idx}. {item.get('name', '')}")
        print(f"   {item.get('address', '')}")
        if item.get("phone"):
            print(f"   {item.get('phone')}")
        rating = item.get("rating") or {}
        if rating:
            print(f"   Rating: {rating.get('ratingValue', 'N/A')} ({rating.get('ratingCount', 0)} reviews)")
        if item.get("price_range"):
            print(f"   Price: {item.get('price_range')}")
        if item.get("opening_hours"):
            print(f"   Hours: {', '.join(item.get('opening_hours'))}")
        if item.get("description"):
            print(f"   {item.get('description')}")
        print("")


@app.command()
def web(
    query: str = typer.Argument(..., help="Search query"),
    count: int = typer.Option(10, "--count", "-n", help="Results per page (1-20)"),
    offset: int = typer.Option(0, "--offset", "-o", help="Pagination offset (0-9)"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Output JSON"),
):
    """Web search via Brave Search API."""
    try:
        results = web_search(query, count=count, offset=offset)
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)
    if json_output:
        print(json.dumps(results, indent=2))
    else:
        _print_web(results)


@app.command()
def local(
    query: str = typer.Argument(..., help="Local search query (e.g. 'pizza near Boston')"),
    count: int = typer.Option(5, "--count", "-n", help="Number of results (1-20)"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Output JSON"),
):
    """Local search via Brave Search API (falls back to web search)."""
    try:
        results = local_search(query, count=count)
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)
    if json_output:
        print(json.dumps(results, indent=2))
    else:
        _print_local(results)


if __name__ == "__main__":
    app()
