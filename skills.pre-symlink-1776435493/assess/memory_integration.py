"""
Memory + Taxonomy integration for /assess.

Pre-hook: Recalls prior project assessments to surface previously identified
health issues and track improvement trajectories.

Post-hook: Learns assessment results to memory so future assessments can
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
        _spec = importlib.util.spec_from_file_location("assess_taxonomy", _TAXONOMY_PATH)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _taxonomy_extract = getattr(_mod, "extract_taxonomy", None)
    except Exception as e:
        logger.debug(f"Taxonomy module load failed: {e}")


# ---------------------------------------------------------------------------
# Bridge extraction
# ---------------------------------------------------------------------------

_BRIDGE_KEYWORDS = {
    "Precision": ["aligned", "consistent", "documented", "tested"],
    "Resilience": ["healthy", "maintained", "active", "evolving"],
    "Fragility": ["stale", "broken", "orphaned", "drift"],
    "Corruption": ["misleading", "outdated", "contradictory"],
    "Loyalty": ["convention", "architecture", "pattern", "standard"],
    "Stealth": ["tech debt", "hidden", "implicit", "undocumented"],
}


def extract_bridges(text: str) -> List[str]:
    """Extract taxonomy bridge attributes from assessment content."""
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
# Pre-hook: Recall prior assessments
# ---------------------------------------------------------------------------

def recall_prior_assessments(
    project_path: str,
    k: int = 5,
) -> str:
    """
    Recall prior project assessments.

    Returns formatted markdown showing previously identified health issues,
    enabling agents to track improvement and avoid duplicate findings.
    Returns empty string if memory unavailable.
    """
    if not _HAS_MEMORY:
        return ""

    try:
        client = MemoryClient(scope=MemoryScope.OPERATIONAL)
        result = client.recall(
            f"assess {project_path} health architecture convention drift",
            k=k,
        )
        if result.found:
            return result.to_context(max_items=k)
        return ""
    except Exception as e:
        logger.warning(f"Prior assessment recall failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Post-hook: Learn assessment
# ---------------------------------------------------------------------------

def learn_assessment(
    project_path: str,
    assessment_type: str = "",
    findings: Optional[List[str]] = None,
    health_score: float = 0.0,
) -> List[str]:
    """
    Learn assessment results to memory.

    Stores:
    1. Assessment summary (project, type, findings, health score)
    2. Project health tracking (for longitudinal analysis)

    Returns list of learned lesson IDs (empty if memory unavailable).
    """
    if not _HAS_MEMORY:
        logger.info("Memory not available — skipping assessment learn")
        return []

    client = MemoryClient(scope=MemoryScope.OPERATIONAL)
    now = datetime.now().isoformat()
    learned_ids = []

    all_text = " ".join([project_path or "", assessment_type or ""] + (findings or []))
    bridges = extract_bridges(all_text)
    base_tags = ["assess", project_path] + bridges

    # 1. Assessment summary
    profile = json.dumps({
        "project_path": project_path,
        "assessment_type": assessment_type,
        "findings": findings or [],
        "health_score": health_score,
        "assessed_at": now,
        "bridges": bridges,
    })

    try:
        result = client.learn(
            problem=f"Assessment: {project_path} ({assessment_type}) — health {health_score}",
            solution=profile,
            tags=base_tags + ["assessment"],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
            logger.info(f"Learned assessment: {result.lesson_id}")
    except Exception as e:
        logger.warning(f"Failed to learn assessment: {e}")

    # 2. Health tracking
    try:
        result = client.learn(
            problem=f"Project health: {project_path} at {now}",
            solution=json.dumps({
                "project_path": project_path,
                "health_score": health_score,
                "finding_count": len(findings or []),
                "date": now,
            }),
            tags=base_tags + ["health_tracking"],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
    except Exception as e:
        logger.warning(f"Failed to learn health tracking: {e}")

    logger.info(f"Assessment learn complete: {len(learned_ids)} entries stored")
    return learned_ids
