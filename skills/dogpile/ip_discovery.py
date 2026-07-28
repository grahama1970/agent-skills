#!/usr/bin/env python3
"""IP-only host discovery for Dogpile.

Domain-less / IP-address-hosted sites are not reliably surfaced by Brave web
search and there is no canonical public list of them. The practical sources are
internet-scanner APIs. This lane queries Censys (preferred) or Shodan for hosts
matching the query, emits bounded `http(s)://<ip>[:port]/` URLs, and — when
asked — deep-reads them via the existing fetcher path (`deep_extract_url`).

Off by default and key-gated. IP discovery is experimental; Censys is the
preferred source (Shodan host search needs a paid plan). When no usable
credential is present the lane returns a `skipped` record, never a hard failure.

Censys Platform search requires a Personal Access Token (`CENSYS_API_KEY`) AND
an organization id (`CENSYS_ORG_ID`, sent as the `X-Organization-ID` header);
free tokens without an org id are rejected by the endpoint.
"""
from __future__ import annotations

import ipaddress
import os
from typing import Any, Dict, List

import httpx
from loguru import logger

from dogpile.brave import deep_extract_url

_CENSYS_SEARCH = "https://api.platform.censys.io/v3/global/search/query"
_SHODAN_SEARCH = "https://api.shodan.io/shodan/host/search"

_WEB_PORTS = {80, 443, 8080, 8443, 8000, 8888}


def _is_public_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    return not (ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_multicast or ip.is_link_local)


def _extract_public_ips(obj: Any, found: List[str]) -> None:
    """Recursively collect valid public IP strings from a Censys hit object."""
    if isinstance(obj, str):
        if _is_public_ip(obj):
            found.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _extract_public_ips(v, found)
    elif isinstance(obj, list):
        for v in obj:
            _extract_public_ips(v, found)


def _censys_ip_urls(query: str, limit: int, key: str, org_id: str) -> List[str]:
    """Query Censys Platform search and build bounded http IP URLs."""
    resp = httpx.post(
        _CENSYS_SEARCH,
        headers={
            "Authorization": f"Bearer {key}",
            "X-Organization-ID": org_id,
            "Content-Type": "application/json",
        },
        json={"query": query, "page_size": max(limit * 2, 10)},
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json() or {}
    hits = (data.get("result") or {}).get("hits") or data.get("hits") or []
    ips: List[str] = []
    for hit in hits:
        per_hit: List[str] = []
        _extract_public_ips(hit, per_hit)
        if per_hit:
            ips.append(per_hit[0])  # the hit's primary IP
    urls = [f"http://{ip}/" for ip in ips]
    seen: set = set()
    urls = [u for u in urls if not (u in seen or seen.add(u))]
    return urls[:limit]


def _shodan_ip_urls(query: str, limit: int, key: str) -> List[str]:
    """Query Shodan host search and build bounded http(s) IP URLs (paid-plan fallback)."""
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
            urls.append(f"https://{ip}/" if port == 443 else f"https://{ip}:{port}/")
        elif port in _WEB_PORTS and port != 80:
            urls.append(f"http://{ip}:{port}/")
        else:
            urls.append(f"http://{ip}/")
        if len(urls) >= limit:
            break
    seen: set = set()
    return [u for u in urls if not (u in seen or seen.add(u))]


def discover_ip_hosts(query: str, limit: int = 5) -> Dict[str, Any]:
    """Discover IP-only host URLs for a query via Censys (preferred) or Shodan.

    Returns {"source", "urls", "skipped"}: `urls` is a bounded list of
    IP-address http(s) URLs; `skipped` is a non-null reason string when the lane
    could not run (no key/org, plan-denied, or error) — never raised.
    """
    censys_key = os.environ.get("CENSYS_API_KEY")
    censys_org = os.environ.get("CENSYS_ORG_ID")
    shodan_key = os.environ.get("SHODAN_API_KEY")

    # Preferred: Censys Platform search.
    if censys_key:
        if not censys_org:
            return {"source": "censys", "urls": [],
                    "skipped": "CENSYS_API_KEY present but CENSYS_ORG_ID unset; Censys Platform search requires an organization id (X-Organization-ID)"}
        try:
            urls = _censys_ip_urls(query, limit, censys_key, censys_org)
            if urls:
                return {"source": "censys", "urls": urls, "skipped": None}
            return {"source": "censys", "urls": [], "skipped": "censys returned no IP hosts for this query"}
        except httpx.HTTPStatusError as e:
            reason = f"censys search unavailable (HTTP {e.response.status_code})"
            logger.warning("IP discovery: {}", reason)
            return {"source": "censys", "urls": [], "skipped": reason}
        except Exception as e:
            logger.error("IP discovery via Censys failed: {}", e)
            return {"source": "censys", "urls": [], "skipped": f"censys error: {e}"}

    # Fallback: Shodan (host search needs a paid plan; not preferred for cost).
    if shodan_key:
        try:
            urls = _shodan_ip_urls(query, limit, shodan_key)
            if urls:
                return {"source": "shodan", "urls": urls, "skipped": None}
            return {"source": "shodan", "urls": [], "skipped": "shodan returned no IP hosts for this query"}
        except httpx.HTTPStatusError as e:
            reason = f"shodan search unavailable (HTTP {e.response.status_code}); host search needs a paid plan"
            logger.warning("IP discovery: {}", reason)
            return {"source": "shodan", "urls": [], "skipped": reason}
        except Exception as e:
            logger.error("IP discovery via Shodan failed: {}", e)
            return {"source": "shodan", "urls": [], "skipped": f"shodan error: {e}"}

    return {"source": None, "urls": [], "skipped": "no CENSYS_API_KEY/CENSYS_ORG_ID or SHODAN_API_KEY present; IP discovery disabled"}


def deep_read_ip_hosts(query: str, limit: int = 5) -> Dict[str, Any]:
    """Discover IP-only hosts and deep-read them via the fetcher.

    Returns {"source", "urls", "skipped", "extractions"} where extractions is a
    list of deep-read results for the discovered IP URLs.
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
