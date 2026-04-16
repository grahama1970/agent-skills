"""
Memory + Taxonomy integration for /learn-movie.

Pre-hook: Recalls prior cinematographic analyses for the same movie to
surface previously learned techniques, avoiding redundant storage and
enabling cumulative learning across sessions.

Post-hook: After VLM analysis, learns cinematographic techniques to memory
with taxonomy bridge tags. Enables recall of lighting, composition, and
director style patterns across movies.

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
        _spec = importlib.util.spec_from_file_location("learn_movie_taxonomy", _TAXONOMY_PATH)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _taxonomy_extract = getattr(_mod, "extract_taxonomy", None)
    except Exception as e:
        logger.debug(f"Taxonomy module load failed: {e}")


# ---------------------------------------------------------------------------
# Bridge extraction
# ---------------------------------------------------------------------------

_BRIDGE_KEYWORDS = {
    "Precision": ["technique", "frame", "composition", "symmetry", "geometric", "calculated", "exact"],
    "Resilience": ["adaptation", "creative", "enduring", "triumphant", "recovery", "resolve"],
    "Fragility": ["inconsistency", "discontinuity", "fragile", "delicate", "breaking", "vulnerable"],
    "Corruption": ["distortion", "decay", "grotesque", "horror", "darkness", "chaos"],
    "Loyalty": ["devotion", "sacrifice", "bond", "duty", "honor", "ceremonial"],
    "Stealth": ["shadow", "silhouette", "hidden", "subtle", "muted", "minimalist"],
}


def extract_bridges(text: str) -> List[str]:
    """Extract taxonomy bridge attributes from cinematographic analysis text."""
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
# Pre-hook: Recall prior cinematographic analyses
# ---------------------------------------------------------------------------

def recall_prior_analyses(
    movie_name: str,
    k: int = 5,
) -> str:
    """
    Recall prior cinematographic analyses for a movie.

    Returns formatted markdown showing previously learned techniques,
    enabling agents to build on prior analysis and avoid redundancy.
    Returns empty string if memory unavailable.
    """
    if not _HAS_MEMORY:
        return ""

    try:
        client = MemoryClient(scope=MemoryScope.OPERATIONAL)
        result = client.recall(
            f"cinematographic analysis {movie_name} lighting composition technique",
            k=k,
        )
        if result.found:
            return result.to_context(max_items=k)
        return ""
    except Exception as e:
        logger.warning(f"Prior analysis recall failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Post-hook: Learn cinematographic analysis to memory
# ---------------------------------------------------------------------------

def learn_analysis(
    movie_name: str,
    techniques: Optional[List[Dict[str, Any]]] = None,
    scenes: Optional[List[Dict[str, Any]]] = None,
    insights: Optional[List[str]] = None,
) -> List[str]:
    """
    Learn cinematographic analysis to memory after VLM frame analysis.

    Stores:
    1. Analysis summary (movie, date, technique counts, bridge tags)
    2. Individual techniques (shot type, lighting, composition — for recall)
    3. Scene-level insights (for cross-movie pattern matching)

    Returns list of learned lesson IDs (empty if memory unavailable).
    """
    if not _HAS_MEMORY:
        logger.info("Memory not available — skipping analysis learn")
        return []

    client = MemoryClient(scope=MemoryScope.OPERATIONAL)
    now = datetime.now().isoformat()
    learned_ids = []

    # Build content for bridge extraction
    all_text = " ".join([
        movie_name,
        " ".join(json.dumps(t) for t in (techniques or [])),
        " ".join(json.dumps(s) for s in (scenes or [])),
        " ".join(insights or []),
    ])
    bridges = extract_bridges(all_text)
    base_tags = ["learn_movie", movie_name] + bridges

    # 1. Analysis summary snapshot
    summary = json.dumps({
        "movie": movie_name,
        "date": now,
        "techniques_count": len(techniques or []),
        "scenes_count": len(scenes or []),
        "insights_count": len(insights or []),
        "bridges": bridges,
    })

    try:
        result = client.learn(
            problem=f"Cinematographic analysis: {movie_name} ({now[:10]})",
            solution=summary,
            tags=base_tags + ["snapshot"],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
            logger.info(f"Learned analysis snapshot: {result.lesson_id}")
    except Exception as e:
        logger.warning(f"Failed to learn analysis snapshot: {e}")

    # 2. Individual techniques (for fine-grained recall)
    for technique in (techniques or []):
        try:
            shot_type = technique.get("shot_type", "Unknown")
            lighting = technique.get("lighting_key", "")
            desc = f"{shot_type} — {lighting}" if lighting else shot_type
            result = client.learn(
                problem=f"Technique in {movie_name}: {desc[:100]}",
                solution=json.dumps(technique),
                tags=base_tags + ["technique"],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
        except Exception as e:
            logger.warning(f"Failed to learn technique: {e}")

    # 3. Scene-level insights (cross-movie value)
    for scene in (scenes or []):
        try:
            scene_label = scene.get("scene_idx", "?")
            result = client.learn(
                problem=f"Scene {scene_label} in {movie_name}: {json.dumps(scene)[:100]}",
                solution=json.dumps(scene),
                tags=base_tags + ["scene_analysis"],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
        except Exception as e:
            logger.warning(f"Failed to learn scene analysis: {e}")

    # 4. Director/style insights (for cross-movie pattern matching)
    for insight in (insights or []):
        try:
            result = client.learn(
                problem=f"Insight from {movie_name}: {insight[:100]}",
                solution=insight,
                tags=base_tags + ["insight"],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
        except Exception as e:
            logger.warning(f"Failed to learn insight: {e}")

    logger.info(f"Analysis learn complete: {len(learned_ids)} entries stored")
    return learned_ids
