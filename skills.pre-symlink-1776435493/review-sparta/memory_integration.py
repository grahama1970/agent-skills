"""
Memory + Taxonomy integration for /review-sparta.

Pre-hook: Recalls prior SPARTA assessments to surface previously identified
quality issues and track improvement trajectories.

Post-hook: Learns assessment results to memory so future reviews can leverage
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
        _spec = importlib.util.spec_from_file_location("review_sparta_taxonomy", _TAXONOMY_PATH)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _taxonomy_extract = getattr(_mod, "extract_taxonomy", None)
    except Exception as e:
        logger.debug(f"Taxonomy module load failed: {e}")


# ---------------------------------------------------------------------------
# Bridge extraction
# ---------------------------------------------------------------------------

_BRIDGE_KEYWORDS = {
    "Precision": ["grounding", "verbatim", "citation", "fidelity"],
    "Resilience": ["convergence", "improvement", "iteration"],
    "Fragility": ["hallucination", "orphan", "generic", "stale"],
    "Corruption": ["gaming", "false positive"],
    "Loyalty": ["sparta", "aerospace", "att&ck", "nist"],
    "Stealth": ["regression", "plateau", "subtle drift"],
}


def extract_bridges(text: str) -> List[str]:
    """Extract taxonomy bridge attributes from SPARTA assessment content."""
    if _taxonomy_extract:
        try:
            result = _taxonomy_extract(text, collection="brandon_bailey")
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
    run_id: str = "",
    dimension: str = "",
    k: int = 5,
) -> str:
    """
    Recall prior SPARTA assessments.

    Returns formatted markdown showing previously graded assessments,
    enabling agents to track quality trends and avoid re-grading.
    Returns empty string if memory unavailable.
    """
    if not _HAS_MEMORY:
        return ""

    try:
        client = MemoryClient(scope=MemoryScope.BRANDON_BAILEY)
        result = client.recall(
            f"review_sparta {run_id} {dimension} assessment grading fidelity",
            k=k,
        )
        if result.found:
            return result.to_context(max_items=k)
        return ""
    except Exception as e:
        logger.warning(f"Prior SPARTA assessment recall failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Post-hook: Learn assessment
# ---------------------------------------------------------------------------

def learn_assessment(
    run_id: str,
    grade: str = "",
    weighted_score: float = 0.0,
    critical_issues: Optional[List[str]] = None,
    dimension_scores: Optional[Dict[str, float]] = None,
) -> List[str]:
    """
    Learn SPARTA assessment results to memory.

    Stores:
    1. Assessment summary (run_id, grade, scores, issues)
    2. Dimension breakdown (for trend analysis)

    Returns list of learned lesson IDs (empty if memory unavailable).
    """
    if not _HAS_MEMORY:
        logger.info("Memory not available — skipping SPARTA assessment learn")
        return []

    client = MemoryClient(scope=MemoryScope.BRANDON_BAILEY)
    now = datetime.now().isoformat()
    learned_ids = []

    all_text = " ".join([run_id or "", grade or ""] + (critical_issues or []))
    bridges = extract_bridges(all_text)
    base_tags = ["review_sparta", run_id] + bridges

    # 1. Assessment summary
    profile = json.dumps({
        "run_id": run_id,
        "grade": grade,
        "weighted_score": weighted_score,
        "critical_issues": critical_issues or [],
        "dimension_scores": dimension_scores or {},
        "assessed_at": now,
        "bridges": bridges,
    })

    try:
        result = client.learn(
            problem=f"SPARTA assessment: {run_id} — grade {grade}, score {weighted_score}",
            solution=profile,
            tags=base_tags + ["assessment"],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
            logger.info(f"Learned SPARTA assessment: {result.lesson_id}")
    except Exception as e:
        logger.warning(f"Failed to learn SPARTA assessment: {e}")

    # 2. Dimension breakdown
    if dimension_scores:
        try:
            result = client.learn(
                problem=f"SPARTA dimensions: {run_id} — {json.dumps(dimension_scores)}",
                solution=json.dumps({
                    "run_id": run_id,
                    "dimension_scores": dimension_scores,
                    "date": now,
                }),
                tags=base_tags + ["dimension_breakdown"],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
        except Exception as e:
            logger.warning(f"Failed to learn dimension breakdown: {e}")

    logger.info(f"SPARTA assessment learn complete: {len(learned_ids)} entries stored")
    return learned_ids
