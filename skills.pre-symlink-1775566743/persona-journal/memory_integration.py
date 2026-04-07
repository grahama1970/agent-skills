"""
Memory + Taxonomy integration for /persona-journal.

Pre-hook: Recalls recent journal entries for a persona to provide continuity
across sessions — mood arcs, recurring themes, unresolved emotions.

Post-hook: Learns journal snapshot to memory after generation — mood, topics,
key events, and bridges for multi-hop retrieval.

Pattern: Follows create-context/memory_integration.py with graceful degradation.
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
        _spec = importlib.util.spec_from_file_location("journal_taxonomy", _TAXONOMY_PATH)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _taxonomy_extract = getattr(_mod, "extract_taxonomy", None)
    except Exception as e:
        logger.debug(f"Taxonomy module load failed: {e}")


# ---------------------------------------------------------------------------
# Bridge extraction
# ---------------------------------------------------------------------------

_BRIDGE_KEYWORDS = {
    "Precision": ["clarity", "insight", "understanding", "realization", "awareness", "noticed"],
    "Resilience": ["growth", "healing", "strength", "recovery", "gratitude", "hope", "progress"],
    "Fragility": ["worry", "fear", "uncertainty", "loneliness", "anxiety", "doubt", "sadness", "grief"],
    "Corruption": ["anger", "resentment", "betrayal", "injustice", "manipulation"],
    "Loyalty": ["connection", "friendship", "trust", "love", "family", "bond", "devotion"],
    "Stealth": ["secret", "hidden", "unspoken", "suppressed", "denial", "pretending"],
}


def extract_bridges(text: str) -> List[str]:
    """Extract taxonomy bridge attributes from journal content."""
    if _taxonomy_extract:
        try:
            result = _taxonomy_extract(text, collection="behavioral")
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
    return found or ["Fragility"]


# ---------------------------------------------------------------------------
# Pre-hook: Recall recent journals for continuity
# ---------------------------------------------------------------------------

def recall_recent_journals(
    persona_id: str,
    k: int = 5,
) -> str:
    """
    Recall recent journal entries for a persona.

    Returns formatted context showing prior mood arcs, recurring themes,
    and unresolved emotional threads — enabling continuity across sessions.
    Returns empty string if memory unavailable.
    """
    if not _HAS_MEMORY:
        return ""

    try:
        client = MemoryClient(scope=MemoryScope.OPERATIONAL)
        result = client.recall(
            f"persona journal {persona_id} mood topics events reflection",
            k=k,
        )
        if result.found:
            return result.to_context(max_items=k)
        return ""
    except Exception as e:
        logger.warning(f"Prior journal recall failed for {persona_id}: {e}")
        return ""


# ---------------------------------------------------------------------------
# Post-hook: Learn journal entry to memory
# ---------------------------------------------------------------------------

def learn_journal_entry(
    persona_id: str,
    date: str,
    mood: str,
    topics: Optional[List[str]] = None,
    key_events: Optional[List[str]] = None,
    bridges_mentioned: Optional[List[str]] = None,
    reflection: str = "",
    energy_label: str = "",
) -> List[str]:
    """
    Learn journal entry snapshot to memory after generation.

    Stores:
    1. Journal summary (persona, date, mood, energy, topic count)
    2. Key events individually (for fine-grained recall)

    Returns list of learned lesson IDs (empty if memory unavailable).
    """
    if not _HAS_MEMORY:
        logger.info("Memory not available — skipping journal learn")
        return []

    client = MemoryClient(scope=MemoryScope.OPERATIONAL)
    now = datetime.now().isoformat()
    learned_ids = []

    # Build content for bridge extraction
    all_text = " ".join([
        mood or "",
        " ".join(topics or []),
        " ".join(key_events or []),
        reflection or "",
    ])
    bridges = bridges_mentioned or extract_bridges(all_text)
    base_tags = ["persona_journal", persona_id] + bridges

    # 1. Journal summary snapshot
    summary = json.dumps({
        "persona": persona_id,
        "date": date,
        "mood": mood,
        "energy_label": energy_label,
        "topics": topics or [],
        "key_events_count": len(key_events or []),
        "bridges": bridges,
        "recorded_at": now,
    })

    try:
        result = client.learn(
            problem=f"Journal snapshot: {persona_id} ({date}) — mood: {mood}",
            solution=summary,
            tags=base_tags + ["snapshot"],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
            logger.info(f"Learned journal snapshot: {result.lesson_id}")
    except Exception as e:
        logger.warning(f"Failed to learn journal snapshot: {e}")

    # 2. Key events (individually, for fine-grained recall)
    for event in (key_events or []):
        try:
            result = client.learn(
                problem=f"Journal event for {persona_id} ({date}): {event[:100]}",
                solution=event,
                tags=base_tags + ["key_event"],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
        except Exception as e:
            logger.warning(f"Failed to learn journal event: {e}")

    # 3. Reflection (cross-session emotional thread)
    if reflection:
        try:
            result = client.learn(
                problem=f"Journal reflection for {persona_id} ({date}): {reflection[:100]}",
                solution=json.dumps({
                    "persona": persona_id,
                    "date": date,
                    "mood": mood,
                    "reflection": reflection,
                }),
                tags=base_tags + ["reflection"],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
                logger.info(f"Learned journal reflection: {result.lesson_id}")
        except Exception as e:
            logger.warning(f"Failed to learn journal reflection: {e}")

    logger.info(f"Journal learn complete for {persona_id}: {len(learned_ids)} entries stored")
    return learned_ids
