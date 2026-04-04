"""
Memory + Taxonomy integration for /pdf-lab.

Pre-hook: Recalls prior convergence results for a PDF type or URL to inform
strategy selection and avoid repeating failed approaches.

Post-hook: Learns convergence outcomes (strategy, iterations, final score,
improvements) so future runs can skip to the winning strategy immediately.

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
        _spec = importlib.util.spec_from_file_location("pdf_lab_taxonomy", _TAXONOMY_PATH)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _taxonomy_extract = getattr(_mod, "extract_taxonomy", None)
    except Exception as e:
        logger.debug(f"Taxonomy module load failed: {e}")


# ---------------------------------------------------------------------------
# Bridge extraction
# ---------------------------------------------------------------------------

_BRIDGE_KEYWORDS = {
    "Precision": ["convergence", "delta", "accuracy", "correct", "validated", "sections", "tables"],
    "Resilience": ["recovery", "fallback", "retry", "robust", "synthetic", "workaround"],
    "Fragility": ["broken", "failing", "undersegmentation", "oversegmentation", "missed", "gap", "regression"],
    "Corruption": ["malformed", "corrupt", "encoding", "garbled", "truncated"],
    "Loyalty": ["pipeline", "extractor", "preset", "calibration", "compatibility"],
    "Stealth": ["hidden", "implicit", "undocumented", "edge case", "multi_column"],
}


def extract_bridges(text: str) -> List[str]:
    """Extract taxonomy bridge attributes from convergence content."""
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
# Pre-hook: Recall prior convergence results
# ---------------------------------------------------------------------------

def recall_prior_convergence(
    pdf_type_or_url: str,
    k: int = 5,
) -> str:
    """
    Recall prior convergence results for a PDF type or URL.

    Returns formatted markdown showing what strategies worked before,
    enabling the tuner to skip failed approaches and start from the
    winning strategy. Returns empty string if memory unavailable.
    """
    if not _HAS_MEMORY:
        return ""

    try:
        client = MemoryClient(scope=MemoryScope.OPERATIONAL)
        result = client.recall(
            f"pdf_lab convergence strategy {pdf_type_or_url} iterations score",
            k=k,
        )
        if result.found:
            return result.to_context(max_items=k)
        return ""
    except Exception as e:
        logger.warning(f"Prior convergence recall failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Post-hook: Learn convergence outcome
# ---------------------------------------------------------------------------

def learn_convergence(
    pdf_url: str,
    strategy: str,
    iterations: int,
    final_score: float,
    improvements: Optional[List[str]] = None,
    patterns: Optional[List[str]] = None,
    write_back_result: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """
    Learn convergence outcome to memory after tuning completes.

    Stores:
    1. Convergence summary (PDF, strategy, iterations, score)
    2. Individual improvements made (for recall across PDFs)
    3. Write-back results if code was modified

    Returns list of learned lesson IDs (empty if memory unavailable).
    """
    if not _HAS_MEMORY:
        logger.info("Memory not available — skipping convergence learn")
        return []

    client = MemoryClient(scope=MemoryScope.OPERATIONAL)
    now = datetime.now().isoformat()
    learned_ids = []

    # Build content for bridge extraction
    all_text = " ".join([
        strategy or "",
        pdf_url or "",
        " ".join(improvements or []),
        " ".join(patterns or []),
    ])
    bridges = extract_bridges(all_text)
    base_tags = ["pdf_lab", "convergence"] + bridges

    # 1. Convergence summary
    summary = json.dumps({
        "pdf_url": pdf_url,
        "strategy": strategy,
        "iterations": iterations,
        "final_score": final_score,
        "improvements": improvements or [],
        "patterns": patterns or [],
        "date": now,
        "bridges": bridges,
        "write_back": bool(write_back_result),
    })

    try:
        result = client.learn(
            problem=f"PDF convergence: {pdf_url[:80]} — strategy={strategy} score={final_score:.2f}",
            solution=summary,
            tags=base_tags + ["snapshot"],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
            logger.info(f"Learned convergence snapshot: {result.lesson_id}")
    except Exception as e:
        logger.warning(f"Failed to learn convergence snapshot: {e}")

    # 2. Individual improvements (cross-PDF value)
    for improvement in (improvements or []):
        try:
            result = client.learn(
                problem=f"PDF extraction improvement: {improvement[:100]}",
                solution=improvement,
                tags=base_tags + ["improvement"],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
        except Exception as e:
            logger.warning(f"Failed to learn improvement: {e}")

    # 3. Write-back result (if code was modified)
    if write_back_result:
        try:
            result = client.learn(
                problem=f"Pipeline code change: {pdf_url[:60]} — {strategy}",
                solution=json.dumps(write_back_result),
                tags=base_tags + ["write_back", "drift_tracking"],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
                logger.info(f"Learned write-back result: {result.lesson_id}")
        except Exception as e:
            logger.warning(f"Failed to learn write-back result: {e}")

    logger.info(f"Convergence learn complete: {len(learned_ids)} entries stored")
    return learned_ids
