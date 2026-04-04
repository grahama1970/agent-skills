"""
Memory + Taxonomy integration for /ingest-audiobook.

Pre-hook: Recalls prior audiobook transcriptions to avoid redundant processing
and surface previously gathered content.

Post-hook: Learns transcription metadata to memory so future lookups can
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
        _spec = importlib.util.spec_from_file_location("ingest_audiobook_taxonomy", _TAXONOMY_PATH)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _taxonomy_extract = getattr(_mod, "extract_taxonomy", None)
    except Exception as e:
        logger.debug(f"Taxonomy module load failed: {e}")


# ---------------------------------------------------------------------------
# Bridge extraction
# ---------------------------------------------------------------------------

_BRIDGE_KEYWORDS = {
    "Precision": ["transcribed", "aligned", "chapter"],
    "Resilience": ["completed", "resumed", "checkpoint"],
    "Fragility": ["corrupt", "silence", "truncated"],
    "Corruption": ["drm", "encrypted"],
    "Loyalty": ["series", "author", "narrator"],
    "Stealth": ["whispered", "quiet", "inaudible"],
}


def extract_bridges(text: str) -> List[str]:
    """Extract taxonomy bridge attributes from audiobook content."""
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
# Pre-hook: Recall prior transcriptions
# ---------------------------------------------------------------------------

def recall_prior_transcription(
    book_title: str,
    author: str = "",
    k: int = 3,
) -> str:
    """
    Recall prior audiobook transcriptions.

    Returns formatted markdown showing previously transcribed audiobooks,
    enabling agents to avoid redundant processing. Returns empty string
    if memory unavailable.
    """
    if not _HAS_MEMORY:
        return ""

    try:
        client = MemoryClient(scope=MemoryScope.OPERATIONAL)
        result = client.recall(
            f"ingest_audiobook {book_title} {author} transcription",
            k=k,
        )
        if result.found:
            return result.to_context(max_items=k)
        return ""
    except Exception as e:
        logger.warning(f"Prior transcription recall failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Post-hook: Learn transcription
# ---------------------------------------------------------------------------

def learn_transcription(
    book_title: str,
    author: str = "",
    chapters: int = 0,
    duration_hours: float = 0.0,
    model_used: str = "",
) -> List[str]:
    """
    Learn audiobook transcription to memory.

    Stores:
    1. Transcription metadata (title, author, chapters, duration, model)
    2. Author association (for cross-book recall)

    Returns list of learned lesson IDs (empty if memory unavailable).
    """
    if not _HAS_MEMORY:
        logger.info("Memory not available — skipping transcription learn")
        return []

    client = MemoryClient(scope=MemoryScope.OPERATIONAL)
    now = datetime.now().isoformat()
    learned_ids = []

    all_text = " ".join([book_title or "", author or "", model_used or ""])
    bridges = extract_bridges(all_text)
    base_tags = ["ingest_audiobook", book_title] + bridges

    # 1. Transcription metadata
    profile = json.dumps({
        "book_title": book_title,
        "author": author,
        "chapters": chapters,
        "duration_hours": duration_hours,
        "model_used": model_used,
        "transcribed_at": now,
        "bridges": bridges,
    })

    try:
        result = client.learn(
            problem=f"Audiobook transcription: {book_title} by {author}",
            solution=profile,
            tags=base_tags + ["transcription"],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
            logger.info(f"Learned transcription: {result.lesson_id}")
    except Exception as e:
        logger.warning(f"Failed to learn transcription: {e}")

    # 2. Author association
    if author:
        try:
            result = client.learn(
                problem=f"Author audiobook: {author} — {book_title}",
                solution=json.dumps({
                    "author": author,
                    "book_title": book_title,
                    "chapters": chapters,
                    "date": now,
                }),
                tags=base_tags + ["author_association", author],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
        except Exception as e:
            logger.warning(f"Failed to learn author association: {e}")

    logger.info(f"Transcription learn complete: {len(learned_ids)} entries stored")
    return learned_ids
