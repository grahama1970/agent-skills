#!/usr/bin/env python3
"""IP-only host discovery for Dogpile.

Domain-less / IP-address-hosted sites are not reliably surfaced by Brave web
search and there is no canonical public list of them. The practical sources are
internet-scanner APIs. This lane queries Shodan (preferred) or Censys for hosts
matching the query, emits bounded `http(s)://<ip>[:port]/` URLs, and — when
asked — deep-reads them via the existing fetcher path (`deep_extract_url`).

Off by default and key-gated: when no key is present or the plan does not permit
search, the lane returns a `skipped` record, never a hard failure.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx
from loguru import logger

from dogpile.brave import deep_extract_url

_SHODAN_SEARCH = "https://api.shodan.io/shodan/host/search"
_CENSYS_SEARCH = "https://api.platform.censys.io/v3/global/search/query"

_WEB_PORTS = {80, 443, 8080, 8443, 8000, 8888}


def _shodan_ip_urls(query: str, limit: int, key: str) -> List[str]:
    """Query Shodan host search and build bounded http(s) IP URLs."""
    resp = httpx.get(_SHODAN_SEARCH, params={"key": key, "query": query}, timeout=30.0)
    resp.raise_for_status()
    matches = (resp.json() or {}).get("matches", []) or []
    urls: List[str] = []
    for m in matches:
        ip = m.get("ip_str")
        port = m.get("port")
        if not ip:
            continue
        if port in (443, 8443):
            urls.append(f"https://{ip}:{port}/" if port != 443 else f"https://{ip}/")
        elif port in _WEB_PORTS:
            urls.append(f"http://{ip}:{port}/" if port != 80 else f"http://{ip}/")
        else:
            urls.append(f"http://{ip}/")
        if len(urls) >= limit:
            break
    # de-dupe preserving order
    seen: set = set()
    return [u for u in urls if not (u in seen or seen.add(u))]


def discover_ip_hosts(query: str, limit: int = 5) -> Dict[str, Any]:
    """Discover IP-only host URLs for a query via Shodan/Censys.

    Returns {"source", "urls", "skipped"}: `urls` is a bounded list of
    IP-address http(s) URLs; `skipped` is a non-null reason string when the lane
    could not run (no key, plan-denied, or error) — never raised.
    """
    shodan_key = os.environ.get("SHODAN_API_KEY")
    censys_key = os.environ.get("CENSYS_API_KEY")

    if shodan_key:
        try:
            urls = _shodan_ip_urls(query, limit, shodan_key)
            if urls:
                return {"source": "shodan", "urls": urls, "skipped": None}
            return {"source": "shodan", "urls": [], "skipped": "shodan returned no IP hosts for this query"}
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            reason = f"shodan search unavailable (HTTP {code}); host search needs a paid plan"
            logger.warning("IP discovery: {}", reason)
            return {"source": "shodan", "urls": [], "skipped": reason}
        except Exception as e:
            logger.error("IP discovery via Shodan failed: {}", e)
            return {"source": "shodan", "urls": [], "skipped": f"shodan error: {e}"}

    if censys_key:
        # Censys Platform search shape varies by plan; treat as best-effort.
        return {"source": "censys", "urls": [], "skipped": "censys IP discovery not yet wired; provide SHODAN_API_KEY"}

    return {"source": None, "urls": [], "skipped": "no SHODAN_API_KEY/CENSYS_API_KEY present; IP discovery disabled"}


def deep_read_ip_hosts(query: str, limit: int = 5) -> Dict[str, Any]:
    """Discover IP-only hosts and deep-read them via the fetcher.

    Returns {"source", "urls", "skipped", "extractions"} where extractions is a
    list of deep_extract_url results for the discovered IP URLs.
    """
    disc = discover_ip_hosts(query, limit=limit)
    extractions: List[Dict[str, Any]] = []
    for url in disc.get("urls", []):
        try:
            r = deep_extract_url(url, url)
            extractions.append({"url": url, "extracted": bool(r.get("extracted")),
                                "content_verdict": r.get("content_verdict"),
                                "content": (r.get("content") or "")[:4000]})
        except Exception as e:
            logger.warning("IP host deep-read failed for {}: {}", url, e)
            extractions.append({"url": url, "extracted": False, "error": str(e)})
    disc["extractions"] = extractions
    return disc
