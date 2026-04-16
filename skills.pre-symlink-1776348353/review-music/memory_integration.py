"""
Memory + Taxonomy integration for /review-music.

Pre-hook: Recalls prior music analyses for an artist or track to surface
patterns, stylistic preferences, and HMT bridge trends.

Post-hook: After generating a review, learns analysis results (BPM, key,
features, taxonomy tags) to memory with taxonomy bridge tags.

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
        _spec = importlib.util.spec_from_file_location("music_taxonomy", _TAXONOMY_PATH)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _taxonomy_extract = getattr(_mod, "extract_taxonomy", None)
    except Exception as e:
        logger.debug(f"Taxonomy module load failed: {e}")


# ---------------------------------------------------------------------------
# Bridge extraction
# ---------------------------------------------------------------------------

_BRIDGE_KEYWORDS = {
    "Precision": ["rhythm", "tempo", "pitch", "polyrhythm", "technical", "complex", "algorithmic"],
    "Resilience": ["harmony", "resolution", "crescendo", "triumphant", "anthemic", "building"],
    "Fragility": ["dissonance", "distortion", "clipping", "sparse", "delicate", "fragile", "acoustic"],
    "Corruption": ["corrupted", "industrial", "harsh", "warp", "noise", "mechanical"],
    "Loyalty": ["ceremonial", "ritual", "choral", "solemn", "drone", "modal"],
    "Stealth": ["ambient", "subtle", "minimalist", "atmospheric", "drone", "ethereal"],
}


def extract_bridges(text: str) -> List[str]:
    """Extract taxonomy bridge attributes from music analysis content."""
    if _taxonomy_extract:
        try:
            result = _taxonomy_extract(text, collection="music")
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
# Pre-hook: Recall prior music analyses
# ---------------------------------------------------------------------------

def recall_prior_analyses(
    artist_or_track: str,
    k: int = 5,
) -> str:
    """
    Recall prior music analyses for an artist or track.

    Returns formatted markdown showing past analysis results,
    stylistic patterns, and HMT bridge trends.
    Returns empty string if memory unavailable.
    """
    if not _HAS_MEMORY:
        return ""

    try:
        client = MemoryClient(scope=MemoryScope.OPERATIONAL)
        result = client.recall(
            f"music analysis review {artist_or_track} bpm key features taxonomy",
            k=k,
        )
        if result.found:
            return result.to_context(max_items=k)
        return ""
    except Exception as e:
        logger.warning(f"Prior analysis recall failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Post-hook: Learn analysis results to memory
# ---------------------------------------------------------------------------

def learn_analysis(
    track_title: str,
    artist: str = "",
    bpm: Optional[float] = None,
    key: str = "",
    features: Optional[Dict[str, Any]] = None,
    taxonomy_tags: Optional[List[str]] = None,
) -> List[str]:
    """
    Learn music analysis results to memory after review.

    Stores:
    1. Analysis summary (title, artist, BPM, key, bridges)
    2. Feature details (for recall of specific audio characteristics)

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
        track_title or "",
        artist or "",
        key or "",
        json.dumps(features or {}),
        " ".join(taxonomy_tags or []),
    ])
    bridges = extract_bridges(all_text)

    # Build tags: base + bridges + top taxonomy tags
    top_taxonomy = (taxonomy_tags or [])[:3]
    base_tags = ["music_review"]
    if artist:
        base_tags.append(artist)
    base_tags.extend(bridges)
    base_tags.extend(top_taxonomy)

    # 1. Analysis summary snapshot
    summary = json.dumps({
        "track_title": track_title,
        "artist": artist,
        "bpm": bpm,
        "key": key,
        "date": now,
        "bridges": bridges,
        "taxonomy_tags": taxonomy_tags or [],
        "feature_keys": list((features or {}).keys()),
    })

    try:
        result = client.learn(
            problem=f"Music analysis: {track_title} by {artist or 'unknown'} ({now[:10]}) — BPM:{bpm}, Key:{key}",
            solution=summary,
            tags=base_tags + ["analysis_snapshot"],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
            logger.info(f"Learned analysis snapshot: {result.lesson_id}")
    except Exception as e:
        logger.warning(f"Failed to learn analysis snapshot: {e}")

    # 2. Feature details (for deeper recall of audio characteristics)
    if features:
        try:
            result = client.learn(
                problem=f"Audio features: {track_title} by {artist or 'unknown'} ({now[:10]})",
                solution=json.dumps({
                    "track_title": track_title,
                    "artist": artist,
                    "date": now,
                    "features": features,
                    "bpm": bpm,
                    "key": key,
                }),
                tags=base_tags + ["audio_features"],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
                logger.info(f"Learned audio features: {result.lesson_id}")
        except Exception as e:
            logger.warning(f"Failed to learn audio features: {e}")

    logger.info(f"Analysis learn complete: {len(learned_ids)} entries stored")
    return learned_ids
