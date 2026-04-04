"""
Memory + Taxonomy integration for /review-persona.

Pre-hook: Recalls prior persona reviews to surface previously identified
consistency issues and track character evolution.

Post-hook: Learns persona review findings to memory so future reviews can
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
        _spec = importlib.util.spec_from_file_location("review_persona_taxonomy", _TAXONOMY_PATH)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _taxonomy_extract = getattr(_mod, "extract_taxonomy", None)
    except Exception as e:
        logger.debug(f"Taxonomy module load failed: {e}")


# ---------------------------------------------------------------------------
# Bridge extraction
# ---------------------------------------------------------------------------

_BRIDGE_KEYWORDS = {
    "Precision": ["authentic", "consistent", "canonical", "verified"],
    "Resilience": ["adaptive", "evolving", "growth"],
    "Fragility": ["inconsistent", "contradictory", "flat", "robotic"],
    "Corruption": ["toxic", "harmful", "offensive"],
    "Loyalty": ["backstory", "relationship", "lore", "canon"],
    "Stealth": ["subtext", "nuance", "implied"],
}


def extract_bridges(text: str) -> List[str]:
    """Extract taxonomy bridge attributes from persona review content."""
    if _taxonomy_extract:
        try:
            result = _taxonomy_extract(text, collection="persona")
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
# Pre-hook: Recall prior persona reviews
# ---------------------------------------------------------------------------

def recall_prior_persona_reviews(
    persona_name: str,
    k: int = 5,
) -> str:
    """
    Recall prior persona reviews.

    Returns formatted markdown showing previously identified persona
    consistency issues, enabling agents to track character evolution.
    Returns empty string if memory unavailable.
    """
    if not _HAS_MEMORY:
        return ""

    try:
        client = MemoryClient(scope=MemoryScope.PERSONA)
        result = client.recall(
            f"review_persona {persona_name} realism consistency voice",
            k=k,
        )
        if result.found:
            return result.to_context(max_items=k)
        return ""
    except Exception as e:
        logger.warning(f"Prior persona review recall failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Post-hook: Learn persona review
# ---------------------------------------------------------------------------

def learn_persona_review(
    persona_name: str,
    findings: Optional[List[str]] = None,
    realism_score: float = 0.0,
    voice_match: float = 0.0,
    providers_used: Optional[List[str]] = None,
) -> List[str]:
    """
    Learn persona review findings to memory.

    Stores:
    1. Review summary (persona, findings, scores)
    2. Persona evolution tracking (for longitudinal analysis)

    Returns list of learned lesson IDs (empty if memory unavailable).
    """
    if not _HAS_MEMORY:
        logger.info("Memory not available — skipping persona review learn")
        return []

    client = MemoryClient(scope=MemoryScope.PERSONA)
    now = datetime.now().isoformat()
    learned_ids = []

    all_text = " ".join([persona_name or ""] + (findings or []))
    bridges = extract_bridges(all_text)
    base_tags = ["review_persona", persona_name] + bridges

    # 1. Review summary
    profile = json.dumps({
        "persona_name": persona_name,
        "findings": findings or [],
        "realism_score": realism_score,
        "voice_match": voice_match,
        "providers_used": providers_used or [],
        "reviewed_at": now,
        "bridges": bridges,
    })

    try:
        result = client.learn(
            problem=f"Persona review: {persona_name} — realism {realism_score}, voice {voice_match}",
            solution=profile,
            tags=base_tags + ["review"],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
            logger.info(f"Learned persona review: {result.lesson_id}")
    except Exception as e:
        logger.warning(f"Failed to learn persona review: {e}")

    # 2. Evolution tracking
    try:
        result = client.learn(
            problem=f"Persona evolution: {persona_name} review at {now}",
            solution=json.dumps({
                "persona_name": persona_name,
                "realism_score": realism_score,
                "voice_match": voice_match,
                "date": now,
            }),
            tags=base_tags + ["evolution"],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
    except Exception as e:
        logger.warning(f"Failed to learn persona evolution: {e}")

    logger.info(f"Persona review learn complete: {len(learned_ids)} entries stored")
    return learned_ids
