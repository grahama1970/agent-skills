"""
Memory + Taxonomy integration for /argue (CRUCIAL SKILL — IMPROVE).

Pre-hook: Recalls prior debates on a topic to surface previously established
positions, consensus points, and strongest arguments.

Post-hook: Learns debate outcomes to memory so future debates can
leverage accumulated knowledge and avoid re-litigating settled points.

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
        _spec = importlib.util.spec_from_file_location("argue_taxonomy", _TAXONOMY_PATH)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _taxonomy_extract = getattr(_mod, "extract_taxonomy", None)
    except Exception as e:
        logger.debug(f"Taxonomy module load failed: {e}")


# ---------------------------------------------------------------------------
# Bridge extraction
# ---------------------------------------------------------------------------

_BRIDGE_KEYWORDS = {
    "Precision": ["evidence", "citation", "fact", "verified", "logical"],
    "Resilience": ["consensus", "compromise", "synthesis", "resolved"],
    "Fragility": ["fallacy", "circular", "strawman", "ad hominem", "unsupported"],
    "Corruption": ["bias", "propaganda", "disinformation", "manipulation"],
    "Loyalty": ["position", "principle", "framework", "methodology"],
    "Stealth": ["assumption", "implicit", "unstated", "subtext"],
}


def extract_bridges(text: str) -> List[str]:
    """Extract taxonomy bridge attributes from debate content."""
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
# Pre-hook: Recall prior debates
# ---------------------------------------------------------------------------

def recall_prior_debates(
    topic: str,
    k: int = 5,
) -> str:
    """
    Recall prior debates on a topic.

    Returns formatted markdown showing previously established positions,
    consensus points, and strongest arguments, enabling agents to build
    on prior discourse rather than re-litigating settled questions.
    Returns empty string if memory unavailable.
    """
    if not _HAS_MEMORY:
        return ""

    try:
        client = MemoryClient(scope=MemoryScope.OPERATIONAL)
        result = client.recall(
            f"argue {topic} debate consensus position argument evidence",
            k=k,
        )
        if result.found:
            return result.to_context(max_items=k)
        return ""
    except Exception as e:
        logger.warning(f"Prior debate recall failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Post-hook: Learn debate
# ---------------------------------------------------------------------------

def learn_debate(
    topic: str,
    positions: Optional[List[str]] = None,
    consensus: str = "",
    strongest_arguments: Optional[List[str]] = None,
    persona_ids: Optional[List[str]] = None,
) -> List[str]:
    """
    Learn debate outcome to memory.

    Stores:
    1. Debate summary (topic, positions, consensus, strongest arguments)
    2. Topic knowledge base (for cross-debate recall)
    3. Persona contribution tracking (which personas argued what)

    Returns list of learned lesson IDs (empty if memory unavailable).
    """
    if not _HAS_MEMORY:
        logger.info("Memory not available — skipping debate learn")
        return []

    client = MemoryClient(scope=MemoryScope.OPERATIONAL)
    now = datetime.now().isoformat()
    learned_ids = []

    all_text = " ".join([
        topic or "",
        consensus or "",
        " ".join(positions or []),
        " ".join(strongest_arguments or []),
    ])
    bridges = extract_bridges(all_text)
    base_tags = ["argue", topic] + bridges

    # 1. Debate summary
    profile = json.dumps({
        "topic": topic,
        "positions": positions or [],
        "consensus": consensus,
        "strongest_arguments": strongest_arguments or [],
        "persona_ids": persona_ids or [],
        "debated_at": now,
        "bridges": bridges,
    })

    try:
        result = client.learn(
            problem=f"Debate: {topic} — consensus: {consensus[:100] if consensus else 'none'}",
            solution=profile,
            tags=base_tags + ["debate"],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
            logger.info(f"Learned debate: {result.lesson_id}")
    except Exception as e:
        logger.warning(f"Failed to learn debate: {e}")

    # 2. Topic knowledge base
    if consensus:
        try:
            result = client.learn(
                problem=f"Debate consensus: {topic}",
                solution=json.dumps({
                    "topic": topic,
                    "consensus": consensus,
                    "position_count": len(positions or []),
                    "date": now,
                }),
                tags=base_tags + ["consensus", topic],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
        except Exception as e:
            logger.warning(f"Failed to learn debate consensus: {e}")

    # 3. Persona contributions
    if persona_ids:
        try:
            result = client.learn(
                problem=f"Debate participants: {topic} — {', '.join(persona_ids[:5])}",
                solution=json.dumps({
                    "topic": topic,
                    "persona_ids": persona_ids,
                    "date": now,
                }),
                tags=base_tags + ["participants"] + persona_ids[:5],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
        except Exception as e:
            logger.warning(f"Failed to learn persona contributions: {e}")

    logger.info(f"Debate learn complete: {len(learned_ids)} entries stored")
    return learned_ids
