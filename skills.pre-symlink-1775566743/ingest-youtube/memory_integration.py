"""
Memory + Taxonomy integration for /ingest-youtube.

Pre-hook: Recalls prior transcript ingestions for a video/channel to avoid
redundant downloads and surface previously gathered content.

Post-hook: Learns transcript metadata to memory so future lookups can
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

# Memory client
_HAS_MEMORY = False
try:
    from common.memory_client import MemoryClient, MemoryScope, RecallResult
    _HAS_MEMORY = True
except ImportError:
    logger.debug("common.memory_client not available — memory integration disabled")

# Taxonomy (loaded dynamically to avoid name conflicts)
_taxonomy_extract = None
_TAXONOMY_PATH = _SKILLS_DIR / "taxonomy" / "taxonomy.py"
if _TAXONOMY_PATH.exists():
    try:
        _spec = importlib.util.spec_from_file_location("ingest_youtube_taxonomy", _TAXONOMY_PATH)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _taxonomy_extract = getattr(_mod, "extract_taxonomy", None)
    except Exception as e:
        logger.debug(f"Taxonomy module load failed: {e}")


# ---------------------------------------------------------------------------
# Bridge extraction
# ---------------------------------------------------------------------------

_BRIDGE_KEYWORDS = {
    "Precision": ["transcript", "captions", "verbatim"],
    "Resilience": ["fallback", "proxy", "whisper"],
    "Fragility": ["blocked", "rate limited"],
    "Corruption": ["copyright", "removed"],
    "Loyalty": ["channel", "playlist"],
    "Stealth": ["unlisted", "private", "geoblocked"],
}


def extract_bridges(text: str) -> List[str]:
    """Extract taxonomy bridge attributes from transcript content."""
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
# Pre-hook: Recall prior transcripts
# ---------------------------------------------------------------------------

def recall_prior_transcripts(
    video_id: str,
    channel: str = "",
    k: int = 3,
) -> str:
    """
    Recall prior transcript ingestions for a video or channel.

    Returns formatted markdown showing previously ingested transcripts,
    enabling agents to avoid redundant downloads and detect changes.
    Returns empty string if memory unavailable.
    """
    if not _HAS_MEMORY:
        return ""

    try:
        client = MemoryClient(scope=MemoryScope.OPERATIONAL)
        result = client.recall(
            f"ingest_youtube {video_id} {channel} transcript",
            k=k,
        )
        if result.found:
            return result.to_context(max_items=k)
        return ""
    except Exception as e:
        logger.warning(f"Prior transcript recall failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Post-hook: Learn transcript ingestion
# ---------------------------------------------------------------------------

def learn_transcript(
    video_id: str,
    title: str = "",
    channel: str = "",
    duration_sec: int = 0,
    method: str = "",
    word_count: int = 0,
    summary: str = "",
    qra_count: int = 0,
    scope: str = "operational",
) -> List[str]:
    """
    Learn transcript ingestion to memory.

    Stores:
    1. Transcript metadata + summary (video_id, title, channel, duration, method, summary)
    2. Channel association (for cross-video recall)

    Args:
        scope: Memory scope — passed from CLI --scope flag.

    Returns list of learned lesson IDs (empty if memory unavailable).
    """
    if not _HAS_MEMORY:
        logger.info("Memory not available — skipping transcript learn")
        return []

    scope_enum = getattr(MemoryScope, scope.upper(), MemoryScope.OPERATIONAL)
    client = MemoryClient(scope=scope_enum)
    now = datetime.now().isoformat()
    learned_ids = []

    all_text = " ".join([
        video_id or "",
        title or "",
        channel or "",
        method or "",
        summary or "",
    ])
    bridges = extract_bridges(all_text)
    base_tags = ["ingest_youtube", video_id] + bridges

    # 1. Transcript metadata + summary
    profile = json.dumps({
        "video_id": video_id,
        "title": title,
        "channel": channel,
        "duration_sec": duration_sec,
        "method": method,
        "word_count": word_count,
        "qra_count": qra_count,
        "summary": summary[:2000] if summary else "",
        "ingested_at": now,
        "bridges": bridges,
    })

    # Use summary as the problem text for better recall via semantic search
    problem_text = summary[:500] if summary else f"YouTube transcript: {title} ({video_id}) from {channel}"

    try:
        result = client.learn(
            problem=problem_text,
            solution=profile,
            tags=base_tags + ["transcript"],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
            logger.info(f"Learned transcript: {result.lesson_id}")
    except Exception as e:
        logger.warning(f"Failed to learn transcript: {e}")

    # 2. Channel association
    if channel:
        try:
            result = client.learn(
                problem=f"Channel transcript: {channel} — {title} ({video_id})",
                solution=json.dumps({
                    "channel": channel,
                    "video_id": video_id,
                    "title": title,
                    "date": now,
                }),
                tags=base_tags + ["channel_association", channel],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
        except Exception as e:
            logger.warning(f"Failed to learn channel association: {e}")

    logger.info(f"Transcript learn complete: {len(learned_ids)} entries stored")
    return learned_ids
