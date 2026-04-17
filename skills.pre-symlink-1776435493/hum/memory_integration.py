"""
Memory + Taxonomy integration for /hum.

Pre-hook: Recalls prior hum generations for a persona/song to avoid redundant
processing and surface previously generated audio.

Post-hook: Learns hum metadata to memory so future requests can leverage
accumulated knowledge across sessions.

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
        _spec = importlib.util.spec_from_file_location("hum_taxonomy", _TAXONOMY_PATH)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _taxonomy_extract = getattr(_mod, "extract_taxonomy", None)
    except Exception as e:
        logger.debug(f"Taxonomy module load failed: {e}")


# ---------------------------------------------------------------------------
# Bridge extraction
# ---------------------------------------------------------------------------

_BRIDGE_KEYWORDS = {
    "Precision": ["natural", "clean", "quality", "faithful", "melodic"],
    "Resilience": ["cached", "stored", "available"],
    "Fragility": ["distorted", "artifact", "glitch", "clipping", "noise"],
    "Corruption": ["copyright", "dmca"],
    "Loyalty": ["persona", "voice", "character", "mood"],
    "Stealth": ["ambient", "background", "idle", "subtle"],
}


def extract_bridges(text: str) -> List[str]:
    """Extract taxonomy bridge attributes from hum content."""
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
# Pre-hook: Recall prior hums
# ---------------------------------------------------------------------------

def recall_prior_hums(
    persona_name: str,
    song_title: str = "",
    k: int = 5,
) -> str:
    """
    Recall prior hum generations.

    Returns formatted markdown showing previously generated hums,
    enabling agents to avoid redundant processing and reuse cached audio.
    Returns empty string if memory unavailable.
    """
    if not _HAS_MEMORY:
        return ""

    try:
        client = MemoryClient(scope=MemoryScope.PERSONA)
        result = client.recall(
            f"hum {persona_name} {song_title} rvc voice",
            k=k,
        )
        if result.found:
            return result.to_context(max_items=k)
        return ""
    except Exception as e:
        logger.warning(f"Prior hum recall failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Post-hook: Learn hum
# ---------------------------------------------------------------------------

def learn_hum(
    persona_name: str,
    song_title: str = "",
    artist: str = "",
    rvc_model: str = "",
    quality_score: float = 0.0,
) -> List[str]:
    """
    Learn hum generation to memory.

    Stores:
    1. Hum metadata (persona, song, artist, model, quality)
    2. Persona repertoire (for cross-song recall)

    Returns list of learned lesson IDs (empty if memory unavailable).
    """
    if not _HAS_MEMORY:
        logger.info("Memory not available — skipping hum learn")
        return []

    client = MemoryClient(scope=MemoryScope.PERSONA)
    now = datetime.now().isoformat()
    learned_ids = []

    all_text = " ".join([persona_name or "", song_title or "", artist or "", rvc_model or ""])
    bridges = extract_bridges(all_text)
    base_tags = ["hum", persona_name] + bridges

    # 1. Hum metadata
    profile = json.dumps({
        "persona_name": persona_name,
        "song_title": song_title,
        "artist": artist,
        "rvc_model": rvc_model,
        "quality_score": quality_score,
        "generated_at": now,
        "bridges": bridges,
    })

    try:
        result = client.learn(
            problem=f"Hum: {persona_name} — {song_title} by {artist}, quality {quality_score}",
            solution=profile,
            tags=base_tags + ["hum_generation"],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
            logger.info(f"Learned hum: {result.lesson_id}")
    except Exception as e:
        logger.warning(f"Failed to learn hum: {e}")

    # 2. Persona repertoire
    try:
        result = client.learn(
            problem=f"Persona repertoire: {persona_name} — {song_title}",
            solution=json.dumps({
                "persona_name": persona_name,
                "song_title": song_title,
                "artist": artist,
                "quality_score": quality_score,
                "date": now,
            }),
            tags=base_tags + ["repertoire", persona_name],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
    except Exception as e:
        logger.warning(f"Failed to learn persona repertoire: {e}")

    logger.info(f"Hum learn complete: {len(learned_ids)} entries stored")
    return learned_ids
