"""
Memory + Taxonomy integration for /consume-music.

Pre-hook: Recalls prior music annotations for a query to surface previously
tagged tracks, avoiding redundant annotation and enabling cumulative taste
profile building across sessions.

Post-hook: After annotation or HMT tagging, learns music entries to memory
with taxonomy bridge tags and HMT tier-0 attributes. Enables recall of
track associations across personas, episodes, and scenes.

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
        _spec = importlib.util.spec_from_file_location("consume_music_taxonomy", _TAXONOMY_PATH)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _taxonomy_extract = getattr(_mod, "extract_taxonomy", None)
    except Exception as e:
        logger.debug(f"Taxonomy module load failed: {e}")


# ---------------------------------------------------------------------------
# Bridge extraction
# ---------------------------------------------------------------------------

_BRIDGE_KEYWORDS = {
    "Precision": ["rhythm", "tempo", "technique", "polyrhythm", "algorithmic", "technical", "math"],
    "Resilience": ["resolution", "harmony", "triumphant", "enduring", "crescendo", "anthem", "epic"],
    "Fragility": ["dissonance", "distortion", "delicate", "acoustic", "breaking", "ethereal", "tender"],
    "Corruption": ["noise", "industrial", "harsh", "chaos", "warp", "distorted", "abrasive"],
    "Loyalty": ["ceremonial", "choral", "sacred", "devotion", "oath", "gregorian"],
    "Stealth": ["ambient", "drone", "minimalist", "atmospheric", "subtle", "dark"],
    "Transcendence": ["post-rock", "shoegaze", "expansive", "reverb", "layered"],
    "Defiance": ["aggressive", "rebellion", "punk", "thrash", "rage", "hardcore"],
}


def extract_bridges(text: str) -> List[str]:
    """Extract taxonomy bridge attributes from music annotation text."""
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
# Pre-hook: Recall prior music annotations
# ---------------------------------------------------------------------------

def recall_prior_annotations(
    query: str,
    k: int = 5,
) -> str:
    """
    Recall prior music annotations matching a query.

    Returns formatted markdown showing previously annotated tracks,
    enabling agents to build on prior tagging and avoid redundancy.
    Returns empty string if memory unavailable.
    """
    if not _HAS_MEMORY:
        return ""

    try:
        client = MemoryClient(scope=MemoryScope.OPERATIONAL)
        result = client.recall(
            f"music annotation {query} bridge hmt taxonomy",
            k=k,
        )
        if result.found:
            return result.to_context(max_items=k)
        return ""
    except Exception as e:
        logger.warning(f"Prior annotation recall failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Post-hook: Learn music annotation to memory
# ---------------------------------------------------------------------------

def learn_annotation(
    track_title: str,
    artist: str,
    annotation: str,
    hmt_tags: Optional[List[str]] = None,
    persona_id: Optional[str] = None,
) -> List[str]:
    """
    Learn music annotation to memory after HMT tagging.

    Stores:
    1. Track annotation (title, artist, HMT tags, bridge attributes)
    2. Persona association (which persona tagged this track)

    Tags: ["consume_music", persona_id] + bridges + hmt_tags[:3]

    Returns list of learned lesson IDs (empty if memory unavailable).
    """
    if not _HAS_MEMORY:
        logger.info("Memory not available — skipping annotation learn")
        return []

    client = MemoryClient(scope=MemoryScope.OPERATIONAL)
    now = datetime.now().isoformat()
    learned_ids = []

    # Build content for bridge extraction
    all_text = " ".join([
        track_title,
        artist,
        annotation,
        " ".join(hmt_tags or []),
    ])
    bridges = extract_bridges(all_text)

    # Build tag list: base + bridges + first 3 HMT tags
    base_tags = ["consume_music"]
    if persona_id:
        base_tags.append(persona_id)
    base_tags.extend(bridges)
    if hmt_tags:
        base_tags.extend(hmt_tags[:3])

    # 1. Track annotation entry
    entry = json.dumps({
        "track": track_title,
        "artist": artist,
        "annotation": annotation,
        "hmt_tags": hmt_tags or [],
        "bridges": bridges,
        "persona_id": persona_id or "",
        "date": now,
    })

    try:
        problem_desc = f"Music: {artist} - {track_title}" if artist else f"Music: {track_title}"
        result = client.learn(
            problem=problem_desc,
            solution=entry,
            tags=base_tags + ["annotation"],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
            logger.info(f"Learned annotation: {result.lesson_id}")
    except Exception as e:
        logger.warning(f"Failed to learn annotation: {e}")

    # 2. Persona taste association (if persona specified)
    if persona_id and annotation:
        try:
            result = client.learn(
                problem=f"Taste note ({persona_id}): {artist} - {track_title}"[:120],
                solution=json.dumps({
                    "persona_id": persona_id,
                    "artist": artist,
                    "track": track_title,
                    "note": annotation,
                    "bridges": bridges,
                    "date": now,
                }),
                tags=base_tags + ["taste_profile"],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
        except Exception as e:
            logger.warning(f"Failed to learn taste association: {e}")

    logger.info(f"Annotation learn complete: {len(learned_ids)} entries stored")
    return learned_ids
