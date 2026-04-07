"""
Sound searcher for querying sfx-catalog and ranking results.

Integrates with sfx-catalog for library access and memory for prior usage.
"""

import sys
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from loguru import logger

from .schemas import SFXCue, SFXCandidate


# Path to sfx-catalog skill
SFX_CATALOG_PATH = Path(__file__).parent.parent.parent / "sfx-catalog"


@dataclass
class PriorUsage:
    """Record of prior SFX usage from memory."""
    sfx_id: str
    project_name: str
    scene_description: str
    usage_count: int
    success_score: float  # 0.0-1.0 based on recall frequency


def get_sfx_catalog():
    """
    Import and return sfx-catalog components.
    
    Returns tuple of (SFXQueryEngine, SFXMemoryBridge) or (None, None) if unavailable.
    """
    try:
        if str(SFX_CATALOG_PATH) not in sys.path:
            sys.path.insert(0, str(SFX_CATALOG_PATH))
        
        from src.query_engine import SFXQueryEngine
        from src.memory_bridge import SFXMemoryBridge
        
        return SFXQueryEngine, SFXMemoryBridge
    except ImportError as e:
        logger.warning(f"sfx-catalog not available: {e}")
        return None, None


def search_for_cue(
    cue: SFXCue,
    limit: int = 5,
    scope: str = "horus_lore"
) -> List[SFXCandidate]:
    """
    Query sfx-catalog for sounds matching the cue.
    
    Args:
        cue: The SFX cue to search for
        limit: Maximum number of candidates to return
        scope: Memory scope for search
        
    Returns:
        List of SFX candidates ranked by relevance
    """
    SFXQueryEngine, _ = get_sfx_catalog()
    
    if SFXQueryEngine is None:
        logger.warning("sfx-catalog unavailable, returning mock candidates")
        return _mock_search(cue, limit)
    
    try:
        engine = SFXQueryEngine(scope=scope)
        
        # Build duration range from hint
        duration_range = None
        if cue.duration_hint:
            duration_range = (cue.duration_hint * 0.5, cue.duration_hint * 2.0)
        
        # Search with category filter
        results = engine.search(
            query=cue.description,
            k=limit,
            categories=[cue.category] if cue.category else None,
            duration_range=duration_range,
        )
        
        # Convert to SFXCandidate
        candidates = []
        for r in results:
            candidates.append(SFXCandidate(
                sfx_id=r.get("sfx_id", r.get("_key", "")),
                name=r.get("name", r.get("filename", "")),
                path=r.get("path", r.get("file_path", "")),
                duration=r.get("duration", 1.0),
                category=r.get("category", cue.category),
                similarity_score=r.get("similarity", r.get("score", 0.5)),
                description=r.get("description", ""),
            ))
        
        return candidates
        
    except Exception as e:
        logger.error(f"sfx-catalog search failed: {e}")
        return _mock_search(cue, limit)


def _mock_search(cue: SFXCue, limit: int) -> List[SFXCandidate]:
    """Return mock candidates when sfx-catalog is unavailable."""
    # Generate plausible mock candidates based on category
    mock_names = {
        "foley": ["footstep_wood_01", "door_open_creak_01", "cloth_rustle_01"],
        "ambient": ["room_tone_quiet_01", "city_distant_01", "wind_light_01"],
        "impact": ["punch_body_01", "explosion_small_01", "crash_glass_01"],
        "transition": ["whoosh_fast_01", "swipe_transition_01", "fade_sweep_01"],
        "nature": ["birds_morning_01", "rain_light_01", "wind_trees_01"],
        "vocal": ["gasp_female_01", "scream_distant_01", "crowd_murmur_01"],
        "ui": ["beep_confirm_01", "notification_soft_01", "click_button_01"],
    }
    
    category_names = mock_names.get(cue.category, mock_names["foley"])
    
    candidates = []
    for i, name in enumerate(category_names[:limit]):
        candidates.append(SFXCandidate(
            sfx_id=f"mock_{name}",
            name=name,
            path=f"/mock/sfx/{cue.category}/{name}.wav",
            duration=1.0 + i * 0.5,
            category=cue.category,
            similarity_score=0.8 - i * 0.1,
            description=f"Mock {cue.category} sound: {name}",
        ))
    
    return candidates


def recall_prior_usage(
    scene_description: str,
    scope: str = "horus_lore",
    limit: int = 5
) -> List[PriorUsage]:
    """
    Check memory for previously successful SFX choices.
    
    Args:
        scene_description: Description of the scene context
        scope: Memory scope
        limit: Maximum number of prior usages to return
        
    Returns:
        List of prior usages sorted by success score
    """
    _, SFXMemoryBridge = get_sfx_catalog()
    
    if SFXMemoryBridge is None:
        logger.debug("Memory unavailable, no prior usage to recall")
        return []
    
    try:
        bridge = SFXMemoryBridge(scope=scope)
        
        # Query for similar scene usage
        results = bridge.recall_usage(
            scene_description=scene_description,
            threshold=0.7,
            k=limit,
        )
        
        prior = []
        for r in results:
            prior.append(PriorUsage(
                sfx_id=r.get("sfx_id", ""),
                project_name=r.get("project_name", ""),
                scene_description=r.get("scene_description", ""),
                usage_count=r.get("usage_count", 1),
                success_score=r.get("success_score", 0.5),
            ))
        
        return prior
        
    except Exception as e:
        logger.debug(f"Memory recall failed: {e}")
        return []


def rank_candidates(
    candidates: List[SFXCandidate],
    cue: SFXCue,
    prior_usage: List[PriorUsage]
) -> List[SFXCandidate]:
    """
    Rank candidates by semantic similarity, category match, and prior success.
    
    Scoring:
    - similarity_score: 0.5 weight
    - category match: 0.2 weight
    - duration fit: 0.1 weight
    - prior usage: 0.2 weight
    """
    # Build prior usage lookup
    prior_lookup = {p.sfx_id: p for p in prior_usage}
    
    scored = []
    for candidate in candidates:
        score = 0.0
        
        # Similarity (50%)
        score += candidate.similarity_score * 0.5
        
        # Category match (20%)
        if candidate.category == cue.category:
            score += 0.2
        
        # Duration fit (10%)
        if cue.duration_hint:
            ratio = candidate.duration / cue.duration_hint
            if 0.5 <= ratio <= 2.0:
                # Perfect fit at ratio=1.0
                duration_score = 1.0 - abs(1.0 - ratio) * 0.5
                score += duration_score * 0.1
        else:
            score += 0.05  # No hint, partial credit
        
        # Prior usage (20%)
        if candidate.sfx_id in prior_lookup:
            prior = prior_lookup[candidate.sfx_id]
            candidate.prior_usage_count = prior.usage_count
            score += prior.success_score * 0.2
        
        scored.append((score, candidate))
    
    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)
    
    return [c for _, c in scored]


def search_and_rank(
    cue: SFXCue,
    limit: int = 5,
    scope: str = "horus_lore"
) -> List[SFXCandidate]:
    """
    Combined search and rank operation.
    
    1. Query sfx-catalog
    2. Recall prior usage
    3. Rank by combined score
    """
    # Search for candidates
    candidates = search_for_cue(cue, limit=limit * 2, scope=scope)
    
    # Recall prior usage for this scene context
    prior = recall_prior_usage(cue.description, scope=scope)
    
    # Rank and return top N
    ranked = rank_candidates(candidates, cue, prior)
    return ranked[:limit]
