"""
Memory + Taxonomy integration for /create-walkthrough.

Post-hook: After successful claim verification, learns walkthrough findings
to memory with taxonomy bridge tags for recall/versioning/drift detection.

Pre-hook: Recalls prior walkthroughs for the same system to surface past
failures, risks, and lessons before writing a new walkthrough.

Pattern: Follows create-cast/taxonomy_integration.py with graceful degradation.
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
        _spec = importlib.util.spec_from_file_location("walkthrough_taxonomy", _TAXONOMY_PATH)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _taxonomy_extract = getattr(_mod, "extract_taxonomy", None)
    except Exception as e:
        logger.debug(f"Taxonomy module load failed: {e}")


# ---------------------------------------------------------------------------
# Bridge extraction
# ---------------------------------------------------------------------------

# Keyword fallback when taxonomy module unavailable
_BRIDGE_KEYWORDS = {
    "Precision": ["verification", "claim", "validated", "correct", "exact", "line count"],
    "Resilience": ["recovery", "fallback", "retry", "graceful", "degradation", "robust"],
    "Fragility": ["risk", "failure", "brittle", "broken", "crash", "timeout", "race condition"],
    "Corruption": ["security", "vulnerability", "exploit", "injection", "bypass"],
    "Loyalty": ["dependency", "contract", "interface", "compatibility", "trust"],
    "Stealth": ["hidden", "implicit", "undocumented", "side effect", "silent"],
}


def extract_bridges(text: str) -> List[str]:
    """Extract taxonomy bridge attributes from walkthrough content."""
    if _taxonomy_extract:
        try:
            result = _taxonomy_extract(text, collection="operational")
            bridges = result.get("bridge_tags", []) if isinstance(result, dict) else []
            if bridges:
                return bridges
        except Exception as e:
            logger.debug(f"Taxonomy extraction failed, using keyword fallback: {e}")

    # Keyword fallback
    text_lower = text.lower()
    found = []
    for bridge, keywords in _BRIDGE_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            found.append(bridge)
    return found or ["Precision"]  # Walkthroughs are inherently about precision


# ---------------------------------------------------------------------------
# Pre-hook: Recall prior walkthroughs
# ---------------------------------------------------------------------------

def recall_prior_walkthroughs(
    system_name: str,
    k: int = 5,
) -> str:
    """
    Recall prior walkthrough findings for a system.

    Returns formatted markdown context for injection into the walkthrough
    writing phase. Returns empty string if memory unavailable.
    """
    if not _HAS_MEMORY:
        return ""

    try:
        client = MemoryClient(scope=MemoryScope.OPERATIONAL)
        result = client.recall(
            f"walkthrough {system_name} risks lessons failures",
            k=k,
        )
        if result.found:
            return result.to_context(max_items=k)
        return ""
    except Exception as e:
        logger.warning(f"Prior walkthrough recall failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Post-hook: Learn walkthrough findings to memory
# ---------------------------------------------------------------------------

def learn_walkthrough(
    walkthrough_path: str,
    system_name: str,
    verification_summary: Optional[Dict[str, Any]] = None,
    risks: Optional[List[str]] = None,
    bottom_line: str = "",
) -> List[str]:
    """
    Learn walkthrough findings to memory after successful verification.

    Stores:
    1. Overall walkthrough summary (system, date, verdict, bottom line)
    2. Individual risks identified (for future recall)
    3. Verification stats (for drift detection over time)

    Returns list of learned lesson IDs (empty if memory unavailable).
    """
    if not _HAS_MEMORY:
        logger.info("Memory not available — skipping walkthrough learn")
        return []

    client = MemoryClient(scope=MemoryScope.OPERATIONAL)
    now = datetime.now().isoformat()
    learned_ids = []

    # Read walkthrough content for bridge extraction
    content = ""
    try:
        content = Path(walkthrough_path).read_text()
    except Exception as e:
        logger.debug("path resolution failed: {}", e)

    bridges = extract_bridges(content or bottom_line)
    base_tags = ["walkthrough", system_name] + bridges

    # 1. Overall walkthrough summary
    verified = verification_summary.get("verified", 0) if verification_summary else 0
    mismatched = verification_summary.get("mismatched", 0) if verification_summary else 0
    total = verification_summary.get("total", 0) if verification_summary else 0

    summary_solution = json.dumps({
        "file": walkthrough_path,
        "system": system_name,
        "date": now,
        "verification": {
            "total_claims": total,
            "verified": verified,
            "mismatched": mismatched,
        },
        "bottom_line": bottom_line,
        "bridges": bridges,
    })

    try:
        result = client.learn(
            problem=f"Walkthrough: {system_name} ({now[:10]})",
            solution=summary_solution,
            tags=base_tags + ["summary"],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
            logger.info(f"Learned walkthrough summary: {result.lesson_id}")
    except Exception as e:
        logger.warning(f"Failed to learn walkthrough summary: {e}")

    # 2. Individual risks
    if risks:
        for i, risk in enumerate(risks):
            try:
                result = client.learn(
                    problem=f"Risk in {system_name}: {risk[:100]}",
                    solution=risk,
                    tags=base_tags + ["risk"],
                )
                if result.success:
                    learned_ids.append(result.lesson_id)
            except Exception as e:
                logger.warning(f"Failed to learn risk {i}: {e}")

    # 3. Verification stats (for drift tracking)
    if verification_summary and total > 0:
        try:
            result = client.learn(
                problem=f"Verification stats: {system_name} ({now[:10]})",
                solution=json.dumps({
                    "system": system_name,
                    "date": now,
                    "total_claims": total,
                    "verified": verified,
                    "mismatched": mismatched,
                    "unverified": verification_summary.get("unverified", 0),
                    "accuracy_pct": round(verified / total * 100, 1) if total else 0,
                }),
                tags=base_tags + ["verification_stats", "drift_tracking"],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
                logger.info(f"Learned verification stats: {result.lesson_id}")
        except Exception as e:
            logger.warning(f"Failed to learn verification stats: {e}")

    logger.info(f"Walkthrough learn complete: {len(learned_ids)} entries stored")
    return learned_ids
