"""
Memory + Taxonomy integration for /ingest-book.

Pre-hook: Recalls prior book ingestions to avoid redundant downloads and
surface previously gathered metadata.

Post-hook: Learns book ingestion metadata to memory so future lookups can
leverage accumulated knowledge across sessions.

Pattern: Follows discover-contacts/memory_integration.py with graceful degradation.
"""

import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

# ---------------------------------------------------------------------------
# Lazy imports with graceful degradation
# ---------------------------------------------------------------------------
_SKILLS_DIR = Path(__file__).parent.parent
if str(_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR))

_HAS_MEMORY = False
try:
    from common.memory_client import MemoryClient, MemoryScope, RecallResult
    _HAS_MEMORY = True
except ImportError:
    logger.debug("common.memory_client not available — memory integration disabled")

_taxonomy_extract = None
_TAXONOMY_PATH = _SKILLS_DIR / "taxonomy" / "taxonomy.py"
if _TAXONOMY_PATH.exists():
    try:
        _spec = importlib.util.spec_from_file_location("ingest_book_taxonomy", _TAXONOMY_PATH)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _taxonomy_extract = getattr(_mod, "extract_taxonomy", None)
    except Exception as e:
        logger.debug(f"Taxonomy module load failed: {e}")


# ---------------------------------------------------------------------------
# Bridge extraction
# ---------------------------------------------------------------------------

_BRIDGE_KEYWORDS = {
    "Precision": ["downloaded", "matched", "cataloged"],
    "Resilience": ["retry", "found", "alternative"],
    "Fragility": ["missing", "unavailable", "partial"],
    "Corruption": ["piracy", "fake"],
    "Loyalty": ["series", "author", "library"],
    "Stealth": ["rare", "out-of-print", "restricted"],
}


def extract_bridges(text: str) -> List[str]:
    """Extract taxonomy bridge attributes from book ingestion content."""
    if _taxonomy_extract:
        try:
            result = _taxonomy_extract(text, collection="operational")
            bridges = result.get("bridge_tags", []) if isinstance(result, dict) else []
            if bridges:
                return bridges
        except Exception as e:
            logger.debug(f"Taxonomy extraction failed, using keyword fallback: {e}")

    text_lower = text.lower()
    found = []
    for bridge, keywords in _BRIDGE_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            found.append(bridge)
    return found or ["Precision"]


# ---------------------------------------------------------------------------
# Pre-hook: Recall prior ingestions
# ---------------------------------------------------------------------------

def recall_prior_ingestion(
    book_title: str,
    author: str = "",
    k: int = 3,
) -> str:
    """
    Recall prior book ingestions.

    Returns formatted markdown showing previously ingested books,
    enabling agents to avoid redundant downloads. Returns empty string
    if memory unavailable.
    """
    if not _HAS_MEMORY:
        return ""

    try:
        client = MemoryClient(scope=MemoryScope.OPERATIONAL)
        result = client.recall(
            f"ingest_book {book_title} {author} ingestion",
            k=k,
        )
        if result.found:
            return result.to_context(max_items=k)
        return ""
    except Exception as e:
        logger.warning(f"Prior book ingestion recall failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Post-hook: Learn book ingestion
# ---------------------------------------------------------------------------

def learn_book_ingestion(
    book_title: str,
    author: str = "",
    isbn: str = "",
    status: str = "",
    source: str = "",
) -> List[str]:
    """
    Learn book ingestion to memory.

    Stores:
    1. Book ingestion metadata (title, author, isbn, status, source)
    2. Author association (for cross-book recall)

    Returns list of learned lesson IDs (empty if memory unavailable).
    """
    if not _HAS_MEMORY:
        logger.info("Memory not available — skipping book ingestion learn")
        return []

    client = MemoryClient(scope=MemoryScope.OPERATIONAL)
    now = datetime.now().isoformat()
    learned_ids = []

    all_text = " ".join([book_title or "", author or "", isbn or "", status or "", source or ""])
    bridges = extract_bridges(all_text)
    base_tags = ["ingest_book", book_title] + bridges

    # 1. Book ingestion metadata
    profile = json.dumps({
        "book_title": book_title,
        "author": author,
        "isbn": isbn,
        "status": status,
        "source": source,
        "ingested_at": now,
        "bridges": bridges,
    })

    try:
        result = client.learn(
            problem=f"Book ingestion: {book_title} by {author} (ISBN: {isbn})",
            solution=profile,
            tags=base_tags + ["ingestion"],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
            logger.info(f"Learned book ingestion: {result.lesson_id}")
    except Exception as e:
        logger.warning(f"Failed to learn book ingestion: {e}")

    # 2. Author association
    if author:
        try:
            result = client.learn(
                problem=f"Author book: {author} — {book_title}",
                solution=json.dumps({
                    "author": author,
                    "book_title": book_title,
                    "isbn": isbn,
                    "date": now,
                }),
                tags=base_tags + ["author_association", author],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
        except Exception as e:
            logger.warning(f"Failed to learn author association: {e}")

    logger.info(f"Book ingestion learn complete: {len(learned_ids)} entries stored")
    return learned_ids
