#!/usr/bin/env python3
"""Brave Search API client for web, local, and LLM-oriented search.

Usage:
    python brave_search.py web "query" --count 10 --offset 0
    python brave_search.py local "pizza near Boston" --count 5
    python brave_search.py context "query" --max-tokens 4096
    python brave_search.py summarize "query"
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional
from loguru import logger

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
        except Exception as e:
            logger.debug("loading failed: {}", e)

_load_env()

try:
    import typer
except ImportError:
    print("typer not installed. Run: pip install typer", file=sys.stderr)
    sys.exit(1)

app = typer.Typer(add_completion=False, help="Brave Search API - web + local search")

WEB_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
LLM_CONTEXT_ENDPOINT = "https://api.search.brave.com/res/v1/llm/context"
SUMMARIZER_SEARCH_ENDPOINT = "https://api.search.brave.com/res/v1/summarizer/search"
LOCAL_POIS_ENDPOINT = "https://api.search.brave.com/res/v1/local/pois"
LOCAL_DESC_ENDPOINT = "https://api.search.brave.com/res/v1/local/descriptions"

ENV_KEYS = ("BRAVE_API_KEY", "BRAVE_SEARCH_API_KEY")
ENV_KEYS_PAID = ("BRAVE_API_KEY_PAID",)
ENV_PATHS = [".env", "../.env", "../../.env", "../../../.env"]


def _load_env_keys_from_file(path: str) -> Dict[str, str]:
    """Load all BRAVE_API_KEY* values from a .env file."""
    result: Dict[str, str] = {}
    if not os.path.exists(path):
        return result
    try:
        with open(path) as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                if key.startswith("BRAVE_"):
                    result[key] = value.strip().strip('"').strip("'")
    except OSError:
        pass
    return result


def _resolve_all_keys() -> list[tuple[str, str]]:
    """Return all available API keys with their environment source names."""
    key_pairs: list[tuple[str, str]] = []
    seen: set[str] = set()

    # Check environment variables
    for key_name in (*ENV_KEYS, *ENV_KEYS_PAID):
        value = os.getenv(key_name)
        if value and value not in seen:
            key_pairs.append((key_name, value))
            seen.add(value)

    # Check .env files
    for path in ENV_PATHS:
        env_keys = _load_env_keys_from_file(path)
        for key_name in (*ENV_KEYS, *ENV_KEYS_PAID):
            value = env_keys.get(key_name)
            if value and value not in seen:
                key_pairs.append((key_name, value))
                seen.add(value)

    return key_pairs


def get_api_key(*, paid: bool = False) -> str:
    """Get an API key. Paid keys are used only for explicit paid lanes."""
    key_pairs = _resolve_all_keys()
    if paid:
        for key_name, value in key_pairs:
            if key_name in ENV_KEYS_PAID:
                return value
    for key_name, value in key_pairs:
        if key_name in ENV_KEYS:
            return value
    if key_pairs:
        return key_pairs[0][1]
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


def web_search(
    query: str,
    count: int = 10,
    offset: int = 0,
    *,
    freshness: Optional[str] = None,
    extra_snippets: bool = False,
    summary: bool = False,
) -> Dict[str, Any]:
    api_key = get_api_key(paid=summary)
    count = max(1, min(count, 20))
    offset = max(0, min(offset, 9))
    params: Dict[str, Any] = {"q": query, "count": count, "offset": offset}
    if freshness:
        params["freshness"] = freshness
    if extra_snippets:
        params["extra_snippets"] = "true"
    if summary:
        params["summary"] = "1"
    url = _build_url(WEB_ENDPOINT, params)
    data = _request_json(url, api_key)

    results = []
    for item in data.get("web", {}).get("results", []):
        result = {
            "title": item.get("title", ""),
            "description": item.get("description", ""),
            "url": item.get("url", ""),
        }
        if item.get("extra_snippets"):
            result["extra_snippets"] = item.get("extra_snippets")
        results.append(result)

    output: Dict[str, Any] = {
        "query": query,
        "count": count,
        "offset": offset,
        "results": results,
    }
    if data.get("summarizer"):
        output["summarizer"] = data.get("summarizer")
    return output


def llm_context(
    query: str,
    count: int = 20,
    max_urls: int = 10,
    max_tokens: int = 8192,
    max_snippets: int = 50,
    threshold: str = "balanced",
    freshness: Optional[str] = None,
) -> Dict[str, Any]:
    """Get Brave LLM Context output for agent/RAG consumption."""
    api_key = get_api_key(paid=True)
    params: Dict[str, Any] = {
        "q": query,
        "count": max(1, min(count, 50)),
        "maximum_number_of_urls": max(1, min(max_urls, 50)),
        "maximum_number_of_tokens": max(1024, min(max_tokens, 32768)),
        "maximum_number_of_snippets": max(1, min(max_snippets, 256)),
        "context_threshold_mode": threshold,
    }
    if freshness:
        params["freshness"] = freshness
    url = _build_url(LLM_CONTEXT_ENDPOINT, params)
    data = _request_json(url, api_key)
    return {
        "query": query,
        "endpoint": "llm_context",
        "params": params,
        "response": data,
    }


def summarize_search(query: str, *, inline_references: bool = True, entity_info: bool = False) -> Dict[str, Any]:
    """Run Brave's two-step summarizer flow."""
    api_key = get_api_key(paid=True)
    try:
        web = web_search(query, count=10, summary=True)
    except RuntimeError as exc:
        return {
            "query": query,
            "endpoint": "summarizer",
            "status": "unavailable_plan_or_request_error",
            "step": "web_search_summary_key",
            "error": str(exc),
        }
    key = (web.get("summarizer") or {}).get("key")
    if not key:
        return {
            "query": query,
            "endpoint": "summarizer",
            "status": "skipped_no_summary_key",
            "web": web,
        }
    params: Dict[str, Any] = {"key": key}
    if inline_references:
        params["inline_references"] = "true"
    if entity_info:
        params["entity_info"] = "1"
    url = _build_url(SUMMARIZER_SEARCH_ENDPOINT, params)
    try:
        summary_data = _request_json(url, api_key)
    except RuntimeError as exc:
        return {
            "query": query,
            "endpoint": "summarizer",
            "status": "unavailable_plan_or_request_error",
            "step": "summarizer_search",
            "error": str(exc),
            "web": web,
        }
    return {
        "query": query,
        "endpoint": "summarizer",
        "web": web,
        "summary": summary_data,
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
    freshness: Optional[str] = typer.Option(None, "--freshness", help="Freshness filter: pd, pw, pm, py, or YYYY-MM-DDtoYYYY-MM-DD"),
    extra_snippets: bool = typer.Option(False, "--extra-snippets", help="Request extra snippets when supported by the plan"),
    summary_key: bool = typer.Option(False, "--summary-key", help="Request a summarizer key in the web response"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Output JSON"),
):
    """Web search via Brave Search API."""
    try:
        results = web_search(
            query,
            count=count,
            offset=offset,
            freshness=freshness,
            extra_snippets=extra_snippets,
            summary=summary_key,
        )
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)
    if json_output:
        print(json.dumps(results, indent=2))
    else:
        _print_web(results)


@app.command()
def context(
    query: str = typer.Argument(..., help="Search query for Brave LLM Context"),
    count: int = typer.Option(20, "--count", "-n", help="Search results considered (1-50)"),
    max_urls: int = typer.Option(10, "--max-urls", help="Maximum URLs in context (1-50)"),
    max_tokens: int = typer.Option(8192, "--max-tokens", help="Approximate maximum context tokens (1024-32768)"),
    max_snippets: int = typer.Option(50, "--max-snippets", help="Maximum snippets across URLs (1-256)"),
    threshold: str = typer.Option("balanced", "--threshold", help="Context threshold: strict, balanced, lenient, or disabled"),
    freshness: Optional[str] = typer.Option(None, "--freshness", help="Freshness filter: pd, pw, pm, py, or YYYY-MM-DDtoYYYY-MM-DD"),
):
    """LLM Context API output for agent/RAG grounding."""
    try:
        results = llm_context(
            query,
            count=count,
            max_urls=max_urls,
            max_tokens=max_tokens,
            max_snippets=max_snippets,
            threshold=threshold,
            freshness=freshness,
        )
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)
    print(json.dumps(results, indent=2))


@app.command()
def summarize(
    query: str = typer.Argument(..., help="Search query to summarize"),
    inline_references: bool = typer.Option(True, "--inline-references/--no-inline-references", help="Request inline citation markers"),
    entity_info: bool = typer.Option(False, "--entity-info", help="Request entity info in the summary response"),
):
    """Brave Summarizer two-step search flow."""
    try:
        results = summarize_search(query, inline_references=inline_references, entity_info=entity_info)
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)
    print(json.dumps(results, indent=2))


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
