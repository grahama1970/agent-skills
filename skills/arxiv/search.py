#!/usr/bin/env python3
"""
ArXiv search and paper retrieval API.

Provides functions for searching arXiv, retrieving paper metadata,
and parsing API responses.
"""
from __future__ import annotations

import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError

from config import (
    SKILLS_DIR,
    ARXIV_MAX_REQ_PER_MIN,
    ARXIV_REQUEST_TIMEOUT,
    SKIP_WORDS,
)

# =============================================================================
# Rate Limiting State
# =============================================================================

_REQ_TIMES: list[float] = []

# =============================================================================
# LLM Query Translation
# =============================================================================

QUERY_TRANSLATION_PROMPT = """Convert this natural language query into an arXiv API search query.

arXiv query syntax:
- ti:word - search in title
- abs:word - search in abstract
- au:name - search by author
- cat:cs.LG - filter by category
- AND, OR, ANDNOT - boolean operators
- Use parentheses for grouping

Common categories:
- cs.LG (Machine Learning), cs.AI (AI), cs.CL (NLP), cs.CV (Computer Vision)
- cs.NE (Neural/Evolutionary), cs.IR (Information Retrieval), stat.ML (Stats ML)

Rules:
1. For multi-word concepts, search both title and abstract: (ti:word1 AND ti:word2) OR (abs:word1 AND abs:word2)
2. Keep it simple - don't over-complicate
3. Return ONLY the query string, no explanation

Examples:
- "hypergraph transformers" -> (ti:hypergraph AND ti:transformer) OR (abs:hypergraph AND abs:transformer)
- "LLM reasoning papers" -> (ti:LLM OR ti:language model) AND (ti:reasoning OR abs:reasoning)
- "attention mechanism in vision" -> (abs:attention AND abs:mechanism) AND cat:cs.CV

Natural language query: {query}

arXiv query:"""


def translate_query_llm(query: str) -> Optional[str]:
    """Use scillm to translate natural language to arXiv query syntax.

    Args:
        query: Natural language search query

    Returns:
        Translated arXiv API query string, or None if translation fails
    """
    scillm_path = SKILLS_DIR / "scillm"
    if scillm_path.exists() and str(scillm_path) not in sys.path:
        sys.path.insert(0, str(scillm_path))

    try:
        from batch import quick_completion
    except ImportError:
        return None

    prompt = QUERY_TRANSLATION_PROMPT.format(query=query)

    try:
        content = quick_completion(
            prompt=prompt,
            max_tokens=256,
            temperature=0.1,
            timeout=15,
        ).strip()

        # Clean up any markdown or extra text
        if content.startswith("```"):
            content = content.split("```")[1].strip()
        # Take first line only
        content = content.split("\n")[0].strip()
        return content if content else None
    except Exception:
        return None

# =============================================================================
# arXiv API Query
# =============================================================================

def query_arxiv(
    search_query: str | None,
    start: int,
    max_results: int,
    sort_by: str | None = None,
    sort_order: str | None = None,
    *,
    id_list: str | None = None,
) -> bytes:
    """Query arXiv API with rate limiting and retries.

    Args:
        search_query: Search query string
        start: Starting index for pagination
        max_results: Maximum results to return
        sort_by: Sort field (relevance, submittedDate, lastUpdatedDate)
        sort_order: Sort order (ascending, descending)
        id_list: Comma-separated list of paper IDs

    Returns:
        Raw XML bytes from arXiv API

    Raises:
        HTTPError: If request fails after retries
        URLError: If network error occurs
    """
    base = "https://export.arxiv.org/api/query"
    params = {
        "start": max(0, int(start)),
        "max_results": max(1, int(max_results)),
    }
    if id_list:
        params["id_list"] = id_list
    else:
        params["search_query"] = search_query or "all:"
    if sort_by:
        params["sortBy"] = sort_by
    if sort_order:
        params["sortOrder"] = sort_order

    url = base + "?" + urllib.parse.urlencode(params)

    # Rate limit
    min_interval = 60.0 / max(1, ARXIV_MAX_REQ_PER_MIN)
    now = time.time()
    if _REQ_TIMES and (now - _REQ_TIMES[-1]) < min_interval:
        time.sleep(min_interval - (now - _REQ_TIMES[-1]))

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "ArxivSkill/1.0 (+https://github.com/agent-skills)",
            "Accept": "application/atom+xml",
        },
    )

    attempt = 0
    while True:
        try:
            with urllib.request.urlopen(req, timeout=ARXIV_REQUEST_TIMEOUT) as resp:
                data = resp.read()
                _REQ_TIMES.append(time.time())
                if len(_REQ_TIMES) > 100:
                    del _REQ_TIMES[:-100]
                return data
        except HTTPError as he:
            if he.code in (429, 500, 502, 503, 504) and attempt < 3:
                back = (0.5 * (2**attempt)) + (0.1 * attempt)
                time.sleep(back)
                attempt += 1
                continue
            raise
        except URLError:
            raise

# =============================================================================
# Response Parsing
# =============================================================================

def parse_atom(data: bytes, include_html: bool = True) -> list[dict]:
    """Parse Atom feed from arXiv API.

    Args:
        data: Raw XML bytes
        include_html: Whether to include ar5iv HTML URLs

    Returns:
        List of paper metadata dicts
    """
    ns = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    root = ET.fromstring(data)
    out: list[dict] = []

    for entry in root.findall("a:entry", ns):
        rid = (entry.findtext("a:id", default="", namespaces=ns) or "").strip()
        title = (
            (entry.findtext("a:title", default="", namespaces=ns) or "")
            .strip()
            .replace("\n", " ")
        )
        summary = (entry.findtext("a:summary", default="", namespaces=ns) or "").strip()
        published = (
            entry.findtext("a:published", default="", namespaces=ns) or ""
        ).strip()
        updated = (entry.findtext("a:updated", default="", namespaces=ns) or "").strip()

        links = [
            (lnk.get("rel"), lnk.get("href"))
            for lnk in entry.findall("a:link", ns)
            if lnk.get("href")
        ]
        pdf = next(
            (h for r, h in links if (r in ("related", "", None)) and h.endswith(".pdf")),
            "",
        )
        alt = next((h for r, h in links if r == "alternate"), "")
        cats = [c.get("term") for c in entry.findall("a:category", ns) if c.get("term")]
        primary_category = cats[0] if cats else ""

        authors = []
        for au in entry.findall("a:author", ns):
            name = (au.findtext("a:name", default="", namespaces=ns) or "").strip()
            aff = (
                au.findtext("arxiv:affiliation", default="", namespaces=ns) or ""
            ).strip()
            authors.append({"name": name, "affiliation": aff})

        # Extract clean ID
        arxiv_id = rid.split("/")[-1] if rid else ""

        # Build URLs
        abs_url = alt or rid
        pdf_url = pdf or (f"https://arxiv.org/pdf/{arxiv_id}.pdf" if arxiv_id else "")

        # ar5iv HTML version (renders LaTeX as HTML)
        html_url = ""
        if include_html and arxiv_id:
            # Extract base ID without version for ar5iv
            base_id = arxiv_id.split("v")[0] if "v" in arxiv_id else arxiv_id
            html_url = f"https://ar5iv.org/abs/{base_id}"

        out.append(
            {
                "id": arxiv_id,
                "title": title,
                "abstract": summary,
                "authors": [a["name"] for a in authors],
                "published": published[:10] if published else "",
                "updated": updated[:10] if updated else "",
                "pdf_url": pdf_url,
                "abs_url": abs_url,
                "html_url": html_url,
                "categories": cats,
                "primary_category": primary_category,
            }
        )
    return out

# =============================================================================
# ID Extraction
# =============================================================================

def extract_arxiv_id(text: str) -> tuple[str | None, str | None]:
    """Extract arXiv ID from text/URL.

    Args:
        text: Text containing arXiv ID or URL

    Returns:
        Tuple of (base_id, full_id_with_version)
    """
    s = (text or "").strip()
    if s.startswith("http://") or s.startswith("https://"):
        tail = s.rstrip("/").split("/")[-1]
        if tail.endswith(".pdf"):
            tail = tail[:-4]
    else:
        tail = s

    m = re.match(r"^(?P<base>[0-9]{4}\.[0-9]{4,5})(?P<v>v\d+)?$", tail)
    if not m:
        return None, None
    base = m.group("base")
    v = m.group("v")
    return base, (base + v) if v else base

# =============================================================================
# Query Building
# =============================================================================

def build_query(
    query: str,
    categories: list[str] | None = None,
) -> str:
    """Build arXiv query string with optional category filter.

    For simple queries, searches both title and abstract.
    Multi-word queries are split and ANDed for better matching.

    Args:
        query: Search query
        categories: Optional list of category filters

    Returns:
        arXiv API query string
    """
    parts = []

    # Main query
    if query:
        # Check if it's already a structured query
        if any(op in query for op in ["AND", "OR", "ti:", "abs:", "au:", "cat:"]):
            parts.append(f"({query})")
        else:
            # Split multi-word queries and AND them together
            words = query.split()
            if len(words) == 1:
                # Single word: search in title or abstract
                parts.append(f"(ti:{query} OR abs:{query})")
            else:
                # Multi-word: AND terms together, each in title OR abstract
                word_parts = []
                for word in words:
                    if word.lower() not in SKIP_WORDS and len(word) > 1:
                        word_parts.append(f"(ti:{word} OR abs:{word})")
                if word_parts:
                    parts.append(f"({' AND '.join(word_parts)})")
                else:
                    # Fallback if all words were filtered
                    parts.append(f"(ti:{query} OR abs:{query})")

    # Category filter
    if categories:
        cat_parts = [f"cat:{cat}" for cat in categories]
        parts.append(f"({' OR '.join(cat_parts)})")

    return " AND ".join(parts) if parts else "all:"

# =============================================================================
# High-Level Search Functions
# =============================================================================

def search_papers(
    query: str,
    max_results: int = 10,
    categories: list[str] | None = None,
    sort_by: str = "submittedDate",
    smart: bool = False,
) -> tuple[list[dict], str | None]:
    """Search arXiv for papers matching query.

    Args:
        query: Search query
        max_results: Maximum results to return
        categories: Optional category filters
        sort_by: Sort field
        smart: Whether to use LLM query translation

    Returns:
        Tuple of (papers list, translated_query or None)
    """
    translated_query = None

    # Smart mode: translate natural language
    effective_query = query
    if smart:
        translated_query = translate_query_llm(query)
        if translated_query:
            effective_query = translated_query

    # Try exact ID first
    base_id, _ = extract_arxiv_id(effective_query)
    if base_id:
        try:
            data = query_arxiv(None, 0, max_results, id_list=base_id)
            papers = parse_atom(data)
            if papers:
                return papers, translated_query
        except Exception:
            pass

    # Build structured query
    search_query = build_query(effective_query, categories)

    # Map sort_by to API values
    sort_map = {
        "relevance": "relevance",
        "date": "submittedDate",
        "submittedDate": "submittedDate",
        "lastUpdatedDate": "lastUpdatedDate",
    }
    api_sort = sort_map.get(sort_by, "submittedDate")

    try:
        data = query_arxiv(
            search_query, 0, max_results,
            sort_by=api_sort,
            sort_order="descending"
        )
        papers = parse_atom(data)
        return papers, translated_query
    except Exception:
        return [], translated_query


def get_paper(paper_id: str) -> dict | None:
    """Get a single paper by ID.

    Args:
        paper_id: arXiv paper ID

    Returns:
        Paper metadata dict or None if not found
    """
    base_id, _ = extract_arxiv_id(paper_id)
    if not base_id:
        base_id = paper_id

    try:
        data = query_arxiv(None, 0, 1, id_list=base_id)
        papers = parse_atom(data)
        return papers[0] if papers else None
    except Exception:
        return None

# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "translate_query_llm",
    "query_arxiv",
    "parse_atom",
    "extract_arxiv_id",
    "build_query",
    "search_papers",
    "get_paper",
]
