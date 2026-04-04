"""
Memory + Taxonomy integration for /review-story.

Pre-hook: Recalls prior critiques for a story title or genre to surface
patterns, recurring issues, and what improved between drafts.

Post-hook: After generating a critique, learns key findings (scores,
strengths, weaknesses, suggestions) to memory with taxonomy bridge tags.

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
        _spec = importlib.util.spec_from_file_location("story_taxonomy", _TAXONOMY_PATH)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _taxonomy_extract = getattr(_mod, "extract_taxonomy", None)
    except Exception as e:
        logger.debug(f"Taxonomy module load failed: {e}")


# ---------------------------------------------------------------------------
# Bridge extraction
# ---------------------------------------------------------------------------

_BRIDGE_KEYWORDS = {
    "Precision": ["craft", "prose", "pacing", "calculated", "method", "precise", "technical"],
    "Resilience": ["arc", "resolution", "character growth", "endurance", "recovery", "triumph"],
    "Fragility": ["plot hole", "pacing issue", "weak dialogue", "brittle", "gap", "flaw"],
    "Corruption": ["warp", "chaos", "moral compromise", "betrayal", "taint", "dark"],
    "Loyalty": ["oath", "brotherhood", "honor", "trust", "bond", "duty"],
    "Stealth": ["subtext", "theme", "symbolism", "hidden", "implicit", "undercurrent"],
}


def extract_bridges(text: str) -> List[str]:
    """Extract taxonomy bridge attributes from critique content."""
    if _taxonomy_extract:
        try:
            result = _taxonomy_extract(text, collection="lore")
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
# Pre-hook: Recall prior critiques
# ---------------------------------------------------------------------------

def recall_prior_critiques(
    title_or_genre: str,
    k: int = 5,
) -> str:
    """
    Recall prior story critiques for a title or genre.

    Returns formatted markdown showing past critique patterns,
    recurring issues, and what improved between drafts.
    Returns empty string if memory unavailable.
    """
    if not _HAS_MEMORY:
        return ""

    try:
        client = MemoryClient(scope=MemoryScope.OPERATIONAL)
        result = client.recall(
            f"story critique review {title_or_genre} strengths weaknesses score",
            k=k,
        )
        if result.found:
            return result.to_context(max_items=k)
        return ""
    except Exception as e:
        logger.warning(f"Prior critique recall failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Post-hook: Learn critique findings to memory
# ---------------------------------------------------------------------------

def learn_critique(
    title: str,
    genre: str = "",
    provider: str = "",
    findings: Optional[Dict[str, Any]] = None,
    strengths: Optional[List[str]] = None,
    weaknesses: Optional[List[str]] = None,
    score: Optional[float] = None,
) -> List[str]:
    """
    Learn critique findings to memory after story review.

    Stores:
    1. Critique summary (title, genre, provider, scores, bridges)
    2. Individual strengths (for pattern recall)
    3. Individual weaknesses (for recurring issue detection)

    Returns list of learned lesson IDs (empty if memory unavailable).
    """
    if not _HAS_MEMORY:
        logger.info("Memory not available — skipping critique learn")
        return []

    client = MemoryClient(scope=MemoryScope.OPERATIONAL)
    now = datetime.now().isoformat()
    learned_ids = []

    # Build content for bridge extraction
    all_text = " ".join([
        title or "",
        genre or "",
        " ".join(strengths or []),
        " ".join(weaknesses or []),
        json.dumps(findings or {}),
    ])
    bridges = extract_bridges(all_text)
    base_tags = ["story_review", genre] + bridges if genre else ["story_review"] + bridges

    # 1. Critique summary snapshot
    summary = json.dumps({
        "title": title,
        "genre": genre,
        "provider": provider,
        "date": now,
        "score": score,
        "strengths_count": len(strengths or []),
        "weaknesses_count": len(weaknesses or []),
        "bridges": bridges,
        "findings_keys": list((findings or {}).keys()),
    })

    try:
        result = client.learn(
            problem=f"Story critique: {title} ({now[:10]}) — {genre or 'unspecified genre'}",
            solution=summary,
            tags=base_tags + ["critique_snapshot"],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
            logger.info(f"Learned critique snapshot: {result.lesson_id}")
    except Exception as e:
        logger.warning(f"Failed to learn critique snapshot: {e}")

    # 2. Strengths (individually, for pattern recall across stories)
    for strength in (strengths or []):
        try:
            result = client.learn(
                problem=f"Story strength in {title}: {strength[:100]}",
                solution=strength,
                tags=base_tags + ["strength"],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
        except Exception as e:
            logger.warning(f"Failed to learn strength: {e}")

    # 3. Weaknesses (individually, for recurring issue detection)
    for weakness in (weaknesses or []):
        try:
            result = client.learn(
                problem=f"Story weakness in {title}: {weakness[:100]}",
                solution=weakness,
                tags=base_tags + ["weakness"],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
        except Exception as e:
            logger.warning(f"Failed to learn weakness: {e}")

    # 4. Full findings (for deep recall of specific dimension scores)
    if findings:
        try:
            result = client.learn(
                problem=f"Full critique findings: {title} ({now[:10]})",
                solution=json.dumps({
                    "title": title,
                    "date": now,
                    "findings": findings,
                    "overall_score": score,
                }),
                tags=base_tags + ["full_findings"],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
                logger.info(f"Learned full findings: {result.lesson_id}")
        except Exception as e:
            logger.warning(f"Failed to learn full findings: {e}")

    logger.info(f"Critique learn complete: {len(learned_ids)} entries stored")
    return learned_ids
