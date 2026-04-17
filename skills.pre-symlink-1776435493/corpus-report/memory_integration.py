"""
Memory + Taxonomy integration for /corpus-report.

Pre-hook: Recalls prior corpus report snapshots for trend comparison —
enables agents to detect quality drift over time without re-scanning.

Post-hook: Learns corpus report snapshots (total PDFs, success rate,
failure patterns, top issues) to memory for longitudinal analysis.

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
        _spec = importlib.util.spec_from_file_location("corpus_report_taxonomy", _TAXONOMY_PATH)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _taxonomy_extract = getattr(_mod, "extract_taxonomy", None)
    except Exception as e:
        logger.debug(f"Taxonomy module load failed: {e}")


# ---------------------------------------------------------------------------
# Bridge extraction
# ---------------------------------------------------------------------------

_BRIDGE_KEYWORDS = {
    "Precision": ["accuracy", "ratio", "quality", "correct", "validated", "label"],
    "Resilience": ["recovery", "completed", "stable", "improved", "trend"],
    "Fragility": ["failing", "regression", "bottleneck", "worst", "degraded", "issue"],
    "Corruption": ["corrupt", "malformed", "encoding", "garbled"],
    "Loyalty": ["pipeline", "stage", "preset", "category", "manifest"],
    "Stealth": ["drift", "hidden", "slow", "undetected", "pattern"],
}


def extract_bridges(text: str) -> List[str]:
    """Extract taxonomy bridge attributes from corpus report content."""
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
# Pre-hook: Recall prior corpus reports for trend comparison
# ---------------------------------------------------------------------------

def recall_prior_reports(
    k: int = 5,
) -> str:
    """
    Recall prior corpus report snapshots for trend comparison.

    Returns formatted markdown showing previous corpus stats, enabling
    agents to detect quality drift over time. Returns empty string if
    memory unavailable.
    """
    if not _HAS_MEMORY:
        return ""

    try:
        client = MemoryClient(scope=MemoryScope.OPERATIONAL)
        result = client.recall(
            "corpus_report statistics quality success_rate failure_patterns trends",
            k=k,
        )
        if result.found:
            return result.to_context(max_items=k)
        return ""
    except Exception as e:
        logger.warning(f"Prior corpus report recall failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Post-hook: Learn corpus report snapshot
# ---------------------------------------------------------------------------

def learn_report(
    total_pdfs: int,
    success_rate: float,
    failure_patterns: Optional[List[str]] = None,
    top_issues: Optional[List[str]] = None,
    category_breakdown: Optional[Dict[str, int]] = None,
    quality_metrics: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """
    Learn corpus report snapshot to memory for longitudinal analysis.

    Stores:
    1. Report summary (total, success rate, date)
    2. Failure patterns snapshot (for drift tracking)
    3. Top issues (for trend analysis)

    Returns list of learned lesson IDs (empty if memory unavailable).
    """
    if not _HAS_MEMORY:
        logger.info("Memory not available — skipping report learn")
        return []

    client = MemoryClient(scope=MemoryScope.OPERATIONAL)
    now = datetime.now().isoformat()
    learned_ids = []

    # Build content for bridge extraction
    all_text = " ".join([
        f"total:{total_pdfs} success_rate:{success_rate}",
        " ".join(failure_patterns or []),
        " ".join(top_issues or []),
    ])
    bridges = extract_bridges(all_text)
    base_tags = ["corpus_report", "drift_tracking"] + bridges

    # 1. Report summary snapshot
    summary = json.dumps({
        "total_pdfs": total_pdfs,
        "success_rate": success_rate,
        "failure_patterns": failure_patterns or [],
        "top_issues": top_issues or [],
        "category_breakdown": category_breakdown or {},
        "quality_metrics": quality_metrics or {},
        "date": now,
        "bridges": bridges,
    })

    try:
        result = client.learn(
            problem=f"Corpus report: {total_pdfs} PDFs, {success_rate:.1%} success ({now[:10]})",
            solution=summary,
            tags=base_tags + ["snapshot"],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
            logger.info(f"Learned corpus report snapshot: {result.lesson_id}")
    except Exception as e:
        logger.warning(f"Failed to learn corpus report snapshot: {e}")

    # 2. Failure patterns snapshot (for drift tracking)
    if failure_patterns:
        try:
            result = client.learn(
                problem=f"Corpus failure patterns ({now[:10]}): {len(failure_patterns)} active",
                solution=json.dumps({
                    "date": now,
                    "patterns": failure_patterns,
                    "count": len(failure_patterns),
                }),
                tags=base_tags + ["failure_patterns"],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
        except Exception as e:
            logger.warning(f"Failed to learn failure patterns: {e}")

    # 3. Top issues (individually for fine-grained recall)
    for issue in (top_issues or [])[:5]:
        try:
            result = client.learn(
                problem=f"Corpus top issue: {issue[:100]}",
                solution=issue,
                tags=base_tags + ["top_issue"],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
        except Exception as e:
            logger.warning(f"Failed to learn top issue: {e}")

    logger.info(f"Corpus report learn complete: {len(learned_ids)} entries stored")
    return learned_ids
