#!/usr/bin/env python3
"""arXiv paper search and retrieval CLI.

Self-contained - no database dependencies.
Outputs JSON to stdout for pipeline integration.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List
from urllib.error import HTTPError, URLError

import typer

app = typer.Typer(add_completion=False, help="Search and retrieve arXiv papers")

# Query translation prompt for LLM
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
- "hypergraph transformers" → (ti:hypergraph AND ti:transformer) OR (abs:hypergraph AND abs:transformer)
- "LLM reasoning papers" → (ti:LLM OR ti:language model) AND (ti:reasoning OR abs:reasoning)
- "attention mechanism in vision" → (abs:attention AND abs:mechanism) AND cat:cs.CV

Natural language query: {query}

arXiv query:"""


def _translate_query_llm(query: str) -> Optional[str]:
    """Use scillm to translate natural language to arXiv query syntax."""
    # Import quick_completion from sibling scillm skill
    skills_dir = Path(__file__).parent.parent
    scillm_path = skills_dir / "scillm"
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

# Rate limiting state
_REQ_TIMES: list[float] = []

# Common arXiv categories
CATEGORIES = {
    "cs.AI": "Artificial Intelligence",
    "cs.CL": "Computation and Language (NLP)",
    "cs.CV": "Computer Vision",
    "cs.LG": "Machine Learning",
    "cs.NE": "Neural and Evolutionary Computing",
    "cs.IR": "Information Retrieval",
    "stat.ML": "Machine Learning (Stats)",
    "math.OC": "Optimization and Control",
    "physics.comp-ph": "Computational Physics",
}


def _query_arxiv(
    search_query: str | None,
    start: int,
    max_results: int,
    sort_by: str | None = None,
    sort_order: str | None = None,
    *,
    id_list: str | None = None,
) -> bytes:
    """Query arXiv API with rate limiting and retries."""
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

    # Rate limit: default 30 req/min
    max_rpm = int(os.environ.get("ARXIV_MAX_REQ_PER_MIN", "30") or "30")
    min_interval = 60.0 / max(1, max_rpm)
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
            with urllib.request.urlopen(req, timeout=20) as resp:
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


def _parse_atom(data: bytes, include_html: bool = True) -> list[dict]:
    """Parse Atom feed from arXiv API."""
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


def _extract_arxiv_id(text: str) -> tuple[str | None, str | None]:
    """Extract arXiv ID from text/URL. Returns (base_id, full_id_with_version)."""
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


def _parse_date(date_str: str) -> Optional[datetime]:
    """Parse date string in various formats."""
    formats = ["%Y-%m-%d", "%Y-%m", "%Y"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def _filter_by_date(items: list[dict], since: Optional[str], until: Optional[str]) -> list[dict]:
    """Filter papers by publication date."""
    if not since and not until:
        return items

    since_dt = _parse_date(since) if since else None
    until_dt = _parse_date(until) if until else None

    filtered = []
    for item in items:
        pub_date = _parse_date(item.get("published", ""))
        if not pub_date:
            continue
        if since_dt and pub_date < since_dt:
            continue
        if until_dt and pub_date > until_dt:
            continue
        filtered.append(item)

    return filtered


def _build_query(
    query: str,
    categories: Optional[List[str]] = None,
) -> str:
    """Build arXiv query string with optional category filter."""
    parts = []

    # Main query
    if query:
        # Check if it's already a structured query
        if any(op in query for op in ["AND", "OR", "ti:", "abs:", "au:", "cat:"]):
            parts.append(f"({query})")
        else:
            # Search in title and abstract
            parts.append(f"(ti:{query} OR abs:{query})")

    # Category filter
    if categories:
        cat_parts = [f"cat:{cat}" for cat in categories]
        parts.append(f"({' OR '.join(cat_parts)})")

    return " AND ".join(parts) if parts else "all:"


def _fetch_arxiv(
    q: str,
    max_results: int = 10,
    categories: Optional[List[str]] = None,
    sort_by: str = "submittedDate",
) -> list[dict]:
    """Fetch papers with smart fallbacks."""
    # Try exact ID first
    base_id, _ = _extract_arxiv_id(q)
    if base_id:
        try:
            data = _query_arxiv(None, 0, max_results, id_list=base_id)
            papers = _parse_atom(data)
            if papers:
                return papers
        except Exception:
            pass

    # Build structured query
    search_query = _build_query(q, categories)

    # Map sort_by to API values
    sort_map = {
        "relevance": "relevance",
        "date": "submittedDate",
        "submittedDate": "submittedDate",
        "lastUpdatedDate": "lastUpdatedDate",
    }
    api_sort = sort_map.get(sort_by, "submittedDate")

    try:
        data = _query_arxiv(
            search_query, 0, max_results,
            sort_by=api_sort,
            sort_order="descending"
        )
        papers = _parse_atom(data)
        if papers:
            return papers
    except Exception:
        pass

    return []


@app.command()
def search(
    query: str = typer.Option(..., "--query", "-q", help="Search query"),
    max_results: int = typer.Option(10, "--max-results", "-n", help="Max results"),
    sort_by: str = typer.Option("date", "--sort-by", "-s", help="relevance|date|lastUpdatedDate"),
    category: Optional[List[str]] = typer.Option(None, "--category", "-c", help="Filter by category (e.g., cs.LG, cs.AI)"),
    since: Optional[str] = typer.Option(None, "--since", help="Filter papers after date (YYYY-MM-DD or YYYY-MM)"),
    until: Optional[str] = typer.Option(None, "--until", help="Filter papers before date (YYYY-MM-DD or YYYY-MM)"),
    months: Optional[int] = typer.Option(None, "--months", "-m", help="Papers from last N months"),
    smart: bool = typer.Option(False, "--smart", help="Use LLM to translate natural language query"),
):
    """Search arXiv for papers matching query.

    Examples:
        python arxiv_cli.py search -q "hypergraph transformer" -n 20
        python arxiv_cli.py search -q "LLM reasoning" -c cs.LG -c cs.AI --months 12
        python arxiv_cli.py search -q "attention mechanism" --since 2024-01-01
        python arxiv_cli.py search --smart -q "papers on hypergraph transformers in ML" --months 18
    """
    t0 = time.time()
    errors: list[str] = []
    translated_query: Optional[str] = None

    # Smart mode: translate natural language to arXiv query
    effective_query = query
    if smart:
        typer.echo(f"Translating query via LLM...", err=True)
        translated_query = _translate_query_llm(query)
        if translated_query:
            typer.echo(f"Translated: {translated_query}", err=True)
            effective_query = translated_query
        else:
            typer.echo("LLM translation failed, using original query", err=True)

    # Convert --months to --since
    effective_since = since
    if months and not since:
        since_date = datetime.now() - timedelta(days=months * 30)
        effective_since = since_date.strftime("%Y-%m-%d")

    try:
        # Fetch more results if filtering by date (to account for filtered-out items)
        fetch_count = max_results * 3 if (effective_since or until) else max_results
        items = _fetch_arxiv(effective_query, fetch_count, category, sort_by)

        # Apply date filter
        items = _filter_by_date(items, effective_since, until)

        # Trim to requested count
        items = items[:max_results]
    except Exception as e:
        items = []
        errors.append(str(e))

    took_ms = int((time.time() - t0) * 1000)
    out = {
        "meta": {
            "query": query,
            "translated_query": translated_query,
            "count": len(items),
            "took_ms": took_ms,
            "filters": {
                "categories": category,
                "since": effective_since,
                "until": until,
                "smart": smart,
            },
        },
        "items": items,
        "errors": errors,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


@app.command()
def get(
    paper_id: str = typer.Option(..., "--paper-id", "-i", help="arXiv paper ID (e.g., 2301.00001)"),
):
    """Get details for a specific paper by ID.

    Examples:
        python arxiv_cli.py get -i 2301.00001
        python arxiv_cli.py get -i https://arxiv.org/abs/2301.00001
    """
    t0 = time.time()
    errors: list[str] = []

    base_id, _ = _extract_arxiv_id(paper_id)
    if not base_id:
        base_id = paper_id

    try:
        data = _query_arxiv(None, 0, 1, id_list=base_id)
        items = _parse_atom(data)
    except Exception as e:
        items = []
        errors.append(str(e))

    took_ms = int((time.time() - t0) * 1000)
    out = {
        "meta": {"paper_id": paper_id, "count": len(items), "took_ms": took_ms},
        "items": items,
        "errors": errors,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


@app.command()
def download(
    paper_id: str = typer.Option(..., "--paper-id", "-i", help="arXiv paper ID"),
    output: Path = typer.Option(Path("."), "--output", "-o", help="Output directory"),
):
    """Download PDF for a paper.

    Examples:
        python arxiv_cli.py download -i 2301.00001 -o ./papers/
    """
    t0 = time.time()
    errors: list[str] = []
    downloaded: Optional[str] = None

    base_id, _ = _extract_arxiv_id(paper_id)
    if not base_id:
        base_id = paper_id

    try:
        # Get paper info first
        data = _query_arxiv(None, 0, 1, id_list=base_id)
        items = _parse_atom(data)

        if items and items[0].get("pdf_url"):
            pdf_url = items[0]["pdf_url"]
            output.mkdir(parents=True, exist_ok=True)
            filename = output / f"{base_id.replace('.', '_')}.pdf"

            req = urllib.request.Request(
                pdf_url,
                headers={"User-Agent": "ArxivSkill/1.0"},
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                with open(filename, "wb") as f:
                    f.write(resp.read())
            downloaded = str(filename)
        else:
            errors.append("No PDF URL found")
    except Exception as e:
        errors.append(str(e))

    took_ms = int((time.time() - t0) * 1000)
    out = {
        "meta": {"paper_id": paper_id, "took_ms": took_ms},
        "downloaded": downloaded,
        "errors": errors,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


@app.command()
def categories():
    """List common arXiv categories.

    Example:
        python arxiv_cli.py categories
    """
    print(json.dumps({"categories": CATEGORIES}, indent=2))


if __name__ == "__main__":
    app()
