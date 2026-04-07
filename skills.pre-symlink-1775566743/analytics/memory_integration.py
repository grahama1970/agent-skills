"""
Memory + Taxonomy integration for /analytics.

Pre-hook: Recalls prior analyses for a dataset to surface previously generated
insights and avoid redundant computation.

Post-hook: Learns analysis metadata to memory so future analyses can
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
        _spec = importlib.util.spec_from_file_location("analytics_taxonomy", _TAXONOMY_PATH)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _taxonomy_extract = getattr(_mod, "extract_taxonomy", None)
    except Exception as e:
        logger.debug(f"Taxonomy module load failed: {e}")


# ---------------------------------------------------------------------------
# Bridge extraction
# ---------------------------------------------------------------------------

_BRIDGE_KEYWORDS = {
    "Precision": ["metric", "statistic", "correlation", "distribution"],
    "Resilience": ["complete", "clean", "validated", "normalized"],
    "Fragility": ["missing", "null", "outlier", "skewed", "sparse"],
    "Corruption": ["inconsistent", "duplicate", "conflicting"],
    "Loyalty": ["dataset", "schema", "pipeline", "source"],
    "Stealth": ["latent", "hidden pattern", "anomaly", "trend"],
}


def extract_bridges(text: str) -> List[str]:
    """Extract taxonomy bridge attributes from analytics content."""
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
# Pre-hook: Recall prior analyses
# ---------------------------------------------------------------------------

def recall_prior_analyses(
    dataset_name: str,
    k: int = 5,
) -> str:
    """
    Recall prior analyses for a dataset.

    Returns formatted markdown showing previously generated insights,
    enabling agents to avoid redundant analysis and build on prior work.
    Returns empty string if memory unavailable.
    """
    if not _HAS_MEMORY:
        return ""

    try:
        client = MemoryClient(scope=MemoryScope.OPERATIONAL)
        result = client.recall(
            f"analytics {dataset_name} chart insight correlation distribution",
            k=k,
        )
        if result.found:
            return result.to_context(max_items=k)
        return ""
    except Exception as e:
        logger.warning(f"Prior analysis recall failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Post-hook: Learn analysis
# ---------------------------------------------------------------------------

def learn_analysis(
    dataset_name: str,
    chart_types: Optional[List[str]] = None,
    row_count: int = 0,
    column_count: int = 0,
    insights: Optional[List[str]] = None,
) -> List[str]:
    """
    Learn analysis metadata to memory.

    Stores:
    1. Analysis summary (dataset, charts, dimensions, insights)
    2. Dataset profile (for cross-analysis recall)

    Returns list of learned lesson IDs (empty if memory unavailable).
    """
    if not _HAS_MEMORY:
        logger.info("Memory not available — skipping analysis learn")
        return []

    client = MemoryClient(scope=MemoryScope.OPERATIONAL)
    now = datetime.now().isoformat()
    learned_ids = []

    all_text = " ".join([dataset_name or ""] + (chart_types or []) + (insights or []))
    bridges = extract_bridges(all_text)
    base_tags = ["analytics", dataset_name] + bridges

    # 1. Analysis summary
    profile = json.dumps({
        "dataset_name": dataset_name,
        "chart_types": chart_types or [],
        "row_count": row_count,
        "column_count": column_count,
        "insights": insights or [],
        "analyzed_at": now,
        "bridges": bridges,
    })

    try:
        result = client.learn(
            problem=f"Analysis: {dataset_name} — {row_count}x{column_count}, {len(insights or [])} insights",
            solution=profile,
            tags=base_tags + ["analysis"],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
            logger.info(f"Learned analysis: {result.lesson_id}")
    except Exception as e:
        logger.warning(f"Failed to learn analysis: {e}")

    # 2. Dataset profile
    try:
        result = client.learn(
            problem=f"Dataset profile: {dataset_name} ({row_count} rows, {column_count} cols)",
            solution=json.dumps({
                "dataset_name": dataset_name,
                "row_count": row_count,
                "column_count": column_count,
                "date": now,
            }),
            tags=base_tags + ["dataset_profile"],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
    except Exception as e:
        logger.warning(f"Failed to learn dataset profile: {e}")

    logger.info(f"Analysis learn complete: {len(learned_ids)} entries stored")
    return learned_ids
