"""
Memory integration for recording usage and recalling prior designs.

Stores SFX usage in sfx-catalog memory for learning and future recall.
"""

import sys
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from loguru import logger

from .schemas import SFXEvent, SFXCue


# Path to sfx-catalog skill
SFX_CATALOG_PATH = Path(__file__).parent.parent.parent / "sfx-catalog"


@dataclass
class PriorDesign:
    """A prior sound design from memory."""
    project_name: str
    scene_description: str
    events: List[Dict[str, Any]]
    created_at: str
    similarity_score: float


@dataclass  
class SFXPattern:
    """A successful SFX usage pattern."""
    category: str
    sfx_id: str
    usage_count: int
    avg_volume: float
    avg_duration: float
    common_contexts: List[str]


def get_memory_bridge():
    """Get SFXMemoryBridge from sfx-catalog."""
    try:
        if str(SFX_CATALOG_PATH) not in sys.path:
            sys.path.insert(0, str(SFX_CATALOG_PATH))
        
        from src.memory_bridge import SFXMemoryBridge
        return SFXMemoryBridge
    except ImportError as e:
        logger.debug(f"SFXMemoryBridge not available: {e}")
        return None


def record_sfx_usage(
    event: SFXEvent,
    cue: SFXCue,
    project_name: str,
    scene_description: str,
    episode: Optional[str] = None,
    bridges: Optional[List[str]] = None,
    scope: str = "horus_lore"
) -> Optional[str]:
    """
    Store usage in sfx-catalog memory for learning.
    
    Args:
        event: The placed SFX event
        cue: The original cue that was fulfilled
        project_name: Name of the project
        scene_description: Description of the scene context
        episode: Optional episode association
        bridges: Optional HMT bridge attributes
        scope: Memory scope
        
    Returns:
        Usage record ID if successful, None otherwise
    """
    SFXMemoryBridge = get_memory_bridge()
    
    if SFXMemoryBridge is None:
        logger.debug("Memory bridge unavailable, skipping usage recording")
        return None
    
    try:
        bridge = SFXMemoryBridge(scope=scope)
        
        usage_id = bridge.record_usage(
            sfx_id=event.sfx_id,
            project_name=project_name,
            scene_description=scene_description,
            timestamp_in_scene=event.timestamp,
            rationale=f"Matched cue: {cue.description}",
            category=cue.category,
            intensity=cue.intensity,
            episode=episode,
            bridges=bridges or [],
            volume=event.volume,
            duration=event.duration,
        )
        
        logger.debug(f"Recorded usage: {usage_id}")
        return usage_id
        
    except Exception as e:
        logger.warning(f"Failed to record usage: {e}")
        return None


def recall_similar_scenes(
    scene_description: str,
    limit: int = 5,
    scope: str = "horus_lore"
) -> List[PriorDesign]:
    """
    Find prior sound designs for similar scenes.
    
    Args:
        scene_description: Description of the scene context
        limit: Maximum number of prior designs to return
        scope: Memory scope
        
    Returns:
        List of prior designs sorted by similarity
    """
    SFXMemoryBridge = get_memory_bridge()
    
    if SFXMemoryBridge is None:
        logger.debug("Memory unavailable, no prior designs to recall")
        return []
    
    try:
        bridge = SFXMemoryBridge(scope=scope)
        
        # Query for similar scene contexts
        results = bridge.recall_designs(
            scene_description=scene_description,
            threshold=0.6,
            k=limit,
        )
        
        prior_designs = []
        for r in results:
            prior_designs.append(PriorDesign(
                project_name=r.get("project_name", ""),
                scene_description=r.get("scene_description", ""),
                events=r.get("events", []),
                created_at=r.get("created_at", ""),
                similarity_score=r.get("similarity", 0.5),
            ))
        
        return prior_designs
        
    except Exception as e:
        logger.debug(f"Failed to recall prior designs: {e}")
        return []


def get_successful_patterns(
    category: str,
    bridges: Optional[List[str]] = None,
    scope: str = "horus_lore",
    min_usage_count: int = 2
) -> List[SFXPattern]:
    """
    Retrieve patterns that worked well (high recall frequency).
    
    Args:
        category: SFX category to filter by
        bridges: Optional HMT bridge attributes
        scope: Memory scope
        min_usage_count: Minimum usage count to consider a pattern
        
    Returns:
        List of successful patterns
    """
    SFXMemoryBridge = get_memory_bridge()
    
    if SFXMemoryBridge is None:
        return []
    
    try:
        bridge = SFXMemoryBridge(scope=scope)
        
        # Query for frequently used sounds in this category
        results = bridge.get_patterns(
            category=category,
            bridges=bridges or [],
            min_count=min_usage_count,
        )
        
        patterns = []
        for r in results:
            patterns.append(SFXPattern(
                category=r.get("category", category),
                sfx_id=r.get("sfx_id", ""),
                usage_count=r.get("usage_count", 0),
                avg_volume=r.get("avg_volume", 0.5),
                avg_duration=r.get("avg_duration", 1.0),
                common_contexts=r.get("common_contexts", []),
            ))
        
        return patterns
        
    except Exception as e:
        logger.debug(f"Failed to get patterns: {e}")
        return []


def batch_record_usage(
    events: List[SFXEvent],
    cues: Dict[str, SFXCue],
    project_name: str,
    scene_descriptions: Dict[str, str],
    episode: Optional[str] = None,
    bridges: Optional[List[str]] = None,
    scope: str = "horus_lore"
) -> List[str]:
    """
    Record multiple SFX usages in batch.
    
    Args:
        events: List of placed SFX events
        cues: Dict mapping cue_id to SFXCue
        project_name: Name of the project
        scene_descriptions: Dict mapping scene_id to description
        episode: Optional episode association
        bridges: Optional HMT bridge attributes
        scope: Memory scope
        
    Returns:
        List of usage record IDs
    """
    usage_ids = []
    
    for event in events:
        cue = cues.get(event.cue_id)
        if not cue:
            continue
        
        scene_desc = scene_descriptions.get(
            cue.scene_id, 
            f"Scene {cue.scene_id}"
        )
        
        usage_id = record_sfx_usage(
            event=event,
            cue=cue,
            project_name=project_name,
            scene_description=scene_desc,
            episode=episode,
            bridges=bridges,
            scope=scope,
        )
        
        if usage_id:
            usage_ids.append(usage_id)
    
    logger.info(f"Recorded {len(usage_ids)} usage records")
    return usage_ids


def get_recommended_sounds(
    cue: SFXCue,
    bridges: Optional[List[str]] = None,
    scope: str = "horus_lore",
    limit: int = 3
) -> List[Dict[str, Any]]:
    """
    Get recommended sounds based on successful prior usage.
    
    Combines pattern matching with contextual similarity.
    """
    recommendations = []
    
    # Get patterns for this category
    patterns = get_successful_patterns(
        category=cue.category,
        bridges=bridges,
        scope=scope,
    )
    
    # Add top patterns as recommendations
    for pattern in patterns[:limit]:
        recommendations.append({
            "sfx_id": pattern.sfx_id,
            "reason": f"Used {pattern.usage_count}x in similar contexts",
            "avg_volume": pattern.avg_volume,
            "confidence": min(pattern.usage_count / 10, 1.0),
        })
    
    return recommendations
