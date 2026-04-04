"""
Memory + Taxonomy integration for /quality-audit.

Pre-hook: Recalls prior audit results for a project or pipeline to surface
quality trends, recurring failure patterns, and drift detection.

Post-hook: After generating an audit report, learns results (pass rate,
findings, statistics) to memory with taxonomy bridge tags for trend tracking.

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
        _spec = importlib.util.spec_from_file_location("audit_taxonomy", _TAXONOMY_PATH)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _taxonomy_extract = getattr(_mod, "extract_taxonomy", None)
    except Exception as e:
        logger.debug(f"Taxonomy module load failed: {e}")


# ---------------------------------------------------------------------------
# Bridge extraction
# ---------------------------------------------------------------------------

_BRIDGE_KEYWORDS = {
    "Precision": ["accurate", "correct", "validated", "exact", "verified", "precise"],
    "Resilience": ["consistent", "stable", "passing", "robust", "reliable", "sustained"],
    "Fragility": ["failing", "regression", "drift", "degraded", "broken", "flaky", "declining"],
    "Corruption": ["corrupted", "invalid", "hallucination", "fabricated", "injected"],
    "Loyalty": ["compliant", "conforming", "standard", "contract", "specification"],
    "Stealth": ["edge case", "hidden", "subtle", "undetected", "silent failure"],
}


def extract_bridges(text: str) -> List[str]:
    """Extract taxonomy bridge attributes from audit content."""
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
# Pre-hook: Recall prior audit results
# ---------------------------------------------------------------------------

def recall_prior_audits(
    project_or_pipeline: str,
    k: int = 5,
) -> str:
    """
    Recall prior quality audit results for a project or pipeline.

    Returns formatted markdown showing past audit results,
    quality trends, and drift detection data.
    Returns empty string if memory unavailable.
    """
    if not _HAS_MEMORY:
        return ""

    try:
        client = MemoryClient(scope=MemoryScope.OPERATIONAL)
        result = client.recall(
            f"quality audit {project_or_pipeline} pass_rate findings drift statistics",
            k=k,
        )
        if result.found:
            return result.to_context(max_items=k)
        return ""
    except Exception as e:
        logger.warning(f"Prior audit recall failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Post-hook: Learn audit results to memory
# ---------------------------------------------------------------------------

def learn_audit(
    project_name: str,
    pipeline: str = "",
    sample_size: int = 0,
    pass_rate: Optional[float] = None,
    findings: Optional[List[str]] = None,
    stats: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """
    Learn audit results to memory after quality audit.

    Stores:
    1. Audit summary (project, pipeline, pass rate, sample size, bridges)
    2. Individual findings (for recurring issue detection)
    3. Statistics snapshot (for drift tracking over time)

    Returns list of learned lesson IDs (empty if memory unavailable).
    """
    if not _HAS_MEMORY:
        logger.info("Memory not available — skipping audit learn")
        return []

    client = MemoryClient(scope=MemoryScope.OPERATIONAL)
    now = datetime.now().isoformat()
    learned_ids = []

    # Build content for bridge extraction
    all_text = " ".join([
        project_name or "",
        pipeline or "",
        " ".join(findings or []),
        json.dumps(stats or {}),
        f"pass_rate={pass_rate}" if pass_rate is not None else "",
    ])
    bridges = extract_bridges(all_text)
    base_tags = ["quality_audit", project_name] + bridges + ["drift_tracking"]

    # 1. Audit summary snapshot
    summary = json.dumps({
        "project": project_name,
        "pipeline": pipeline,
        "date": now,
        "sample_size": sample_size,
        "pass_rate": pass_rate,
        "findings_count": len(findings or []),
        "bridges": bridges,
        "stats_keys": list((stats or {}).keys()),
    })

    try:
        result = client.learn(
            problem=f"Quality audit: {project_name} ({now[:10]}) — pass_rate:{pass_rate}, samples:{sample_size}",
            solution=summary,
            tags=base_tags + ["audit_snapshot"],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
            logger.info(f"Learned audit snapshot: {result.lesson_id}")
    except Exception as e:
        logger.warning(f"Failed to learn audit snapshot: {e}")

    # 2. Individual findings (for recurring issue detection)
    for finding in (findings or []):
        try:
            result = client.learn(
                problem=f"Audit finding in {project_name}: {finding[:100]}",
                solution=finding,
                tags=base_tags + ["finding"],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
        except Exception as e:
            logger.warning(f"Failed to learn finding: {e}")

    # 3. Statistics snapshot (for drift tracking over time)
    if stats:
        try:
            result = client.learn(
                problem=f"Audit statistics: {project_name} ({now[:10]})",
                solution=json.dumps({
                    "project": project_name,
                    "pipeline": pipeline,
                    "date": now,
                    "pass_rate": pass_rate,
                    "sample_size": sample_size,
                    "stats": stats,
                }),
                tags=base_tags + ["statistics", "trend_data"],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
                logger.info(f"Learned statistics snapshot: {result.lesson_id}")
        except Exception as e:
            logger.warning(f"Failed to learn statistics snapshot: {e}")

    logger.info(f"Audit learn complete: {len(learned_ids)} entries stored")
    return learned_ids
