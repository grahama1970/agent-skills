"""
Memory integration for ingest-kindle, following the ingest-book/consume-book pattern.

Hooks into the common memory client for recall/learn operations.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add skills parent dir for common module access
_SKILLS_DIR = Path(__file__).resolve().parent.parent
if str(_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR))

_HAS_MEMORY = False
try:
    from common.memory_client import MemoryClient
    _HAS_MEMORY = True
except ImportError:
    _HAS_MEMORY = False

HAS_MEMORY = _HAS_MEMORY  # backward compat alias


_BRIDGE_KEYWORDS = {
    "Precision": ["accuracy", "quality", "extract", "parse"],
    "Resilience": ["robust", "fallback", "retry", "recover"],
    "Fragility": ["corrupt", "malformed", "encoding", "missing"],
    "Loyalty": ["pipeline", "ingest", "library", "catalog"],
    "Stealth": ["edge case", "ambiguous", "unknown format"],
}


def extract_bridges(text: str) -> list[str]:
    """Extract taxonomy bridge attributes from book content."""
    text_lower = text.lower()
    found = []
    for bridge, keywords in _BRIDGE_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            found.append(bridge)
    return found or ["Loyalty"]


def recall_books(query: str, k: int = 5) -> list[dict]:
    """Recall previously ingested books from memory."""
    if not _HAS_MEMORY:
        return []
    try:
        client = MemoryClient()
        result = client.recall(f"kindle book {query}", k=k)
        if hasattr(result, "items"):
            return result.items
        return []
    except Exception:
        return []


def learn_book(title: str, author: str, metadata: dict) -> bool:
    """Learn book metadata to memory."""
    if not _HAS_MEMORY:
        return False
    try:
        client = MemoryClient()
        bridges = extract_bridges(f"{title} {author}")
        client.learn(
            problem=f"What is '{title}' by {author}?",
            solution=json.dumps(metadata, indent=2),
            tags=["kindle", "book", f"author:{author}"] + bridges,
        )
        return True
    except Exception:
        return False


def store_book_metadata(
    title: str,
    author: str,
    scope: str,
    metadata: dict,
    tags: list[str] | None = None,
) -> bool:
    """Store book metadata in memory for recall."""
    if not HAS_MEMORY:
        return False

    tags = tags or []
    tags.extend(["kindle", "book", f"author:{author}"])

    client = MemoryClient()
    client.learn(
        problem=f"What is the book '{title}' by {author} about?",
        solution=json.dumps(metadata, indent=2),
        scope=scope,
        tags=tags,
    )
    return True


def store_highlights(
    title: str,
    author: str,
    scope: str,
    highlights: list[dict],
) -> int:
    """Store highlights as individual memory entries."""
    if not HAS_MEMORY:
        return 0

    client = MemoryClient()
    stored = 0

    for h in highlights:
        content = h.get("content", "").strip()
        if not content or len(content) < 20:
            continue

        page = h.get("page", "?")
        location = h.get("location_start", "?")

        client.learn(
            problem=f"Highlight from '{title}' by {author} (p.{page}, loc.{location})",
            solution=content,
            scope=scope,
            tags=["kindle", "highlight", f"book:{title}", f"author:{author}"],
        )
        stored += 1

    return stored
