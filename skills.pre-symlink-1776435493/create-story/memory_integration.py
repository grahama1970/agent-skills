"""
Memory + Taxonomy integration for /create-story.

Pre-hook: Recalls prior creative patterns, character arcs, and narrative
decisions to inform new story creation — avoiding repetition and building
on what worked before.

Post-hook: Learns story decisions to memory after completion — genre,
themes, characters, and narrative techniques for future recall.

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
    "Precision": ["craft", "technique", "structure", "pacing", "clarity", "polished"],
    "Resilience": ["arc resolution", "catharsis", "growth", "redemption", "triumph", "healing"],
    "Fragility": ["plot hole", "inconsistency", "weak", "flat", "unresolved", "underdeveloped"],
    "Corruption": ["villain", "betrayal", "corruption", "moral decay", "manipulation"],
    "Loyalty": ["bond", "sacrifice", "trust", "alliance", "brotherhood", "devotion"],
    "Stealth": ["subtext", "symbolism", "foreshadowing", "metaphor", "hidden meaning", "irony"],
}


def extract_bridges(text: str) -> List[str]:
    """Extract taxonomy bridge attributes from story content."""
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
    return found or ["Precision"]


# ---------------------------------------------------------------------------
# Pre-hook: Recall prior stories for creative continuity
# ---------------------------------------------------------------------------

def recall_prior_stories(
    theme: str,
    genre: str = "",
    k: int = 5,
) -> str:
    """
    Recall prior stories, narrative patterns, and character arcs.

    Returns formatted context showing what themes, techniques, and
    characters have been explored before — enabling creative continuity
    and avoiding repetition.
    Returns empty string if memory unavailable.
    """
    if not _HAS_MEMORY:
        return ""

    try:
        client = MemoryClient(scope=MemoryScope.OPERATIONAL)
        query = f"story {theme} {genre} characters narrative techniques themes".strip()
        result = client.recall(query, k=k)
        if result.found:
            return result.to_context(max_items=k)
        return ""
    except Exception as e:
        logger.warning(f"Prior story recall failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Post-hook: Learn story to memory
# ---------------------------------------------------------------------------

def learn_story(
    title: str,
    genre: str = "",
    themes: Optional[List[str]] = None,
    characters: Optional[List[str]] = None,
    narrative_decisions: Optional[List[str]] = None,
    phase_outputs: Optional[Dict[str, Any]] = None,
    word_count: int = 0,
    final_score: Optional[float] = None,
    format_type: str = "story",
    iterations: int = 0,
) -> List[str]:
    """
    Learn story decisions and outcomes to memory.

    Stores:
    1. Story summary (title, genre, themes, word count, score)
    2. Narrative decisions (individually, for fine-grained technique recall)
    3. Character profiles (for cross-story character development)

    Returns list of learned lesson IDs (empty if memory unavailable).
    """
    if not _HAS_MEMORY:
        logger.info("Memory not available — skipping story learn")
        return []

    client = MemoryClient(scope=MemoryScope.OPERATIONAL)
    now = datetime.now().isoformat()
    learned_ids = []

    # Build content for bridge extraction
    all_text = " ".join([
        title or "",
        genre or "",
        " ".join(themes or []),
        " ".join(characters or []),
        " ".join(narrative_decisions or []),
    ])
    bridges = extract_bridges(all_text)
    base_tags = ["create_story", genre] + bridges if genre else ["create_story"] + bridges

    # 1. Story summary snapshot
    summary = json.dumps({
        "title": title,
        "genre": genre,
        "format": format_type,
        "themes": themes or [],
        "characters": characters or [],
        "word_count": word_count,
        "final_score": final_score,
        "iterations": iterations,
        "bridges": bridges,
        "created_at": now,
    })

    try:
        result = client.learn(
            problem=f"Story: {title[:80]} — {genre} ({now[:10]})",
            solution=summary,
            tags=base_tags + ["snapshot"],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
            logger.info(f"Learned story snapshot: {result.lesson_id}")
    except Exception as e:
        logger.warning(f"Failed to learn story snapshot: {e}")

    # 2. Narrative decisions (individually, for technique recall)
    for decision in (narrative_decisions or []):
        try:
            result = client.learn(
                problem=f"Narrative decision in '{title[:50]}': {decision[:100]}",
                solution=decision,
                tags=base_tags + ["narrative_decision"],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
        except Exception as e:
            logger.warning(f"Failed to learn narrative decision: {e}")

    # 3. Character profiles (cross-story value)
    for character in (characters or []):
        try:
            result = client.learn(
                problem=f"Character in '{title[:50]}': {character[:100]}",
                solution=json.dumps({
                    "story_title": title,
                    "genre": genre,
                    "character": character,
                    "themes": themes or [],
                }),
                tags=base_tags + ["character"],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
        except Exception as e:
            logger.warning(f"Failed to learn character: {e}")

    logger.info(f"Story learn complete for '{title[:50]}': {len(learned_ids)} entries stored")
    return learned_ids
