"""
Content source integration for /ask learn.

Handles book downloads (NZBGeek/Readarr), RSS feed querying,
and ArXiv paper extraction.
"""

import os
import re
import sys
from pathlib import Path
from typing import Optional

from loguru import logger as log

from skills_exec import run_skill, parse_json_output

# Skill paths (relative to this file)
SKILLS_DIR = Path(__file__).parent.parent


# -------------------------------------------------------------------------
# Book Download Integration (ops-nzbgeek, ingest-book)
# -------------------------------------------------------------------------

def search_nzbgeek_books(query: str, limit: int = 5) -> list[dict]:
    """Search NZBGeek for ebooks matching query.

    Args:
        query: Search term (author name, book title)
        limit: Max results to return

    Returns:
        List of {title, link, size, pubDate} dicts
    """
    # Try ops-nzbgeek first (general-purpose)
    result = run_skill("ops-nzbgeek", [
        "search", query,
        "--category", "books",
        "--limit", str(limit * 2),  # Search more, filter later
        "--json",
    ], timeout=30)

    if result["returncode"] == 0 and result["stdout"].strip():
        data = parse_json_output(result["stdout"])
        if isinstance(data, list):
            return data[:limit]

    # Fallback to ingest-book nzb-search
    result = run_skill("ingest-book", [
        "nzb-search", query, "--json"
    ], timeout=30)

    if result["returncode"] == 0 and result["stdout"].strip():
        data = parse_json_output(result["stdout"])
        if isinstance(data, list):
            return data[:limit]

    return []


def download_book_nzb(nzb_link: str, title: str, monitor_progress: bool = True) -> dict:
    """Download an NZB via SABnzbd using ops-nzbgeek.

    Args:
        nzb_link: NZB download URL from NZBGeek
        title: Book title (for logging)
        monitor_progress: Whether to track via task-monitor

    Returns:
        Dict with success, path, error
    """
    log.info("Downloading book NZB: %s", title[:50])

    args = ["download", nzb_link]
    if monitor_progress:
        args.append("--monitor")

    result = run_skill("ops-nzbgeek", args, timeout=300)  # 5 min timeout

    if result["returncode"] == 0:
        # Parse output for download path
        output = result["stdout"]
        # SABnzbd returns nzo_id, we'd need to poll for completion
        # For now, just mark as initiated
        return {"success": True, "initiated": True, "output": output[:200]}

    return {"success": False, "error": result["stderr"][:200]}


def check_downloaded_book(title: str) -> Optional[str]:
    """Check if a book is already downloaded in Readarr library.

    Args:
        title: Book title to search for

    Returns:
        File path if found, None otherwise
    """
    # Use ingest-book retrieve to check
    result = run_skill("ingest-book", ["retrieve", title], timeout=30)

    if result["returncode"] == 0 and "Found file:" in result["stdout"]:
        # Parse file path from output
        for line in result["stdout"].split("\n"):
            if "Found file:" in line:
                path = line.split("Found file:")[-1].strip()
                if path and Path(path).exists():
                    return path

    return None


def extract_book_content(file_path: str, max_pages: int = 100) -> Optional[str]:
    """Extract text content from a downloaded book file.

    Args:
        file_path: Path to ebook file (epub, pdf, mobi)
        max_pages: Max pages to extract

    Returns:
        Extracted text content or None
    """
    log.info("Extracting book content from: %s", file_path)

    result = run_skill("extractor", [
        file_path,
        "--format", "text",
        "--max-pages", str(max_pages),
    ], timeout=120)

    if result["returncode"] == 0 and result["stdout"].strip():
        content = result["stdout"].strip()
        if len(content) > 500:  # Meaningful content
            return content

    return None


# -------------------------------------------------------------------------
# RSS Feed Integration (consume-feed)
# -------------------------------------------------------------------------

def query_feed_items(query: str, limit: int = 10) -> list[dict]:
    """Query RSS feed items from ArangoDB's feed_items collection.

    The consume-feed skill pre-ingests RSS feeds into ArangoDB with
    an ArangoSearch view for full-text search on title, summary, tags.

    Args:
        query: Search term (topic, persona name, keywords)
        limit: Max results to return

    Returns:
        List of {title, url, summary, source_key, published_at} dicts
    """
    # Build AQL query against feed_items_view (ArangoSearch)
    # This requires direct ArangoDB access via memory skill's db.py
    try:
        # Import memory skill's database connection
        MEMORY_SKILL = SKILLS_DIR / "memory"
        if str(MEMORY_SKILL) not in sys.path:
            sys.path.insert(0, str(MEMORY_SKILL))

        from db import get_db
        db = get_db()

        # Check if feed_items collection exists
        if not db.has_collection("feed_items"):
            log.debug("feed_items collection not found - consume-feed not initialized")
            return []

        # ArangoSearch query on feed_items_view
        aql = """
        FOR doc IN feed_items_view
            SEARCH ANALYZER(
                doc.title IN TOKENS(@query, 'text_en')
                OR doc.summary IN TOKENS(@query, 'text_en'),
                'text_en'
            )
            SORT BM25(doc) DESC
            LIMIT @limit
            RETURN {
                title: doc.title,
                url: doc.url,
                summary: doc.summary,
                source_key: doc.source_key,
                published_at: doc.published_at,
                tags: doc.tags
            }
        """

        cursor = db.aql.execute(aql, bind_vars={"query": query, "limit": limit})
        results = list(cursor)

        log.info("Feed query '%s' returned %d items", query[:30], len(results))
        return results

    except ImportError:
        log.debug("Could not import memory db - feed query unavailable")
        return []
    except Exception as e:
        # ArangoSearch view may not exist if consume-feed hasn't been initialized
        log.debug("Feed query failed (view may not exist): %s", str(e)[:100])
        return []


# -------------------------------------------------------------------------
# ArXiv Paper Extraction (arxiv skill)
# -------------------------------------------------------------------------

def extract_arxiv_paper(arxiv_id: str, scope: str, context: str = "", skip_interview: bool = True) -> dict:
    """Extract knowledge from an arXiv paper using the arxiv skill.

    The arxiv skill downloads the paper (HTML from ar5iv.org or PDF fallback),
    extracts content, generates QRA pairs, and stores to memory.

    Args:
        arxiv_id: ArXiv paper ID (e.g., "2501.15355")
        scope: Memory scope to store in
        context: Context string for focused extraction
        skip_interview: Skip paper selection interview (default: True)

    Returns:
        Dict with success, qra_count, error
    """
    log.info("Extracting arXiv paper %s to scope %s", arxiv_id, scope)

    args = [
        "learn", arxiv_id,
        "--scope", scope,
    ]

    if context:
        args.extend(["--context", context])

    if skip_interview:
        args.append("--skip-interview")

    result = run_skill("arxiv", args, timeout=300)  # 5 min for download + extraction

    if result["returncode"] == 0:
        # Try to parse output for stats
        output = result["stdout"]
        qra_count = 0

        # Look for "Stored X QRA pairs" in output
        stored_match = re.search(r"Stored (\d+) QRA", output)
        if stored_match:
            qra_count = int(stored_match.group(1))

        log.info("ArXiv paper %s extracted: %d QRA pairs", arxiv_id, qra_count)
        return {"success": True, "qra_count": qra_count, "arxiv_id": arxiv_id}

    error = result["stderr"][:200] if result["stderr"] else "unknown error"
    log.warning("ArXiv paper %s extraction failed: %s", arxiv_id, error)
    return {"success": False, "error": error, "arxiv_id": arxiv_id}
