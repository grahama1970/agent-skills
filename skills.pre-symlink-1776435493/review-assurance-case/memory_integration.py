"""Memory + Taxonomy integration for /review-assurance-case.

Pre-hook: Recall prior assurance case reviews for the same project/domain.
Post-hook: Learn review findings with taxonomy bridge tags.

Pattern: Same as review-code/memory_integration.py with graceful degradation.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

_SKILLS_DIR = Path(__file__).parent.parent
if str(_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR))

# Memory client
_HAS_MEMORY = False
try:
    from common.memory_client import MemoryClient, MemoryScope
    _HAS_MEMORY = True
except ImportError:
    logger.debug("common.memory_client not available — memory integration disabled")

# Taxonomy
_taxonomy_extract = None
_TAXONOMY_PATH = _SKILLS_DIR / "taxonomy" / "taxonomy.py"
if _TAXONOMY_PATH.exists():
    try:
        _spec = importlib.util.spec_from_file_location("review_taxonomy", _TAXONOMY_PATH)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _taxonomy_extract = getattr(_mod, "extract_taxonomy", None)
    except Exception as e:
        logger.debug(f"Taxonomy module load failed: {e}")


_BRIDGE_KEYWORDS = {
    "Precision": ["traceable", "verified", "validated", "complete", "correct", "accurate"],
    "Resilience": ["robust", "redundant", "fallback", "recovery", "fault-tolerant", "resilient"],
    "Fragility": ["gap", "missing", "incomplete", "dangling", "circular", "stale", "undeveloped"],
    "Corruption": ["adversarial", "tampering", "injection", "vulnerability", "attack", "exploit"],
    "Loyalty": ["compliance", "standard", "framework", "regulation", "CMMC", "DO-178C", "ISO"],
    "Stealth": ["assumption", "implicit", "hidden", "undocumented", "pseudo-precision", "overconfident"],
}


def extract_bridges(text: str) -> List[str]:
    """Extract taxonomy bridge attributes from review content."""
    if _taxonomy_extract:
        try:
            result = _taxonomy_extract(text, collection="operational")
            bridges = result.get("bridge_tags", []) if isinstance(result, dict) else []
            if bridges:
                return bridges
        except Exception:
            pass

    text_lower = text.lower()
    found = []
    for bridge, keywords in _BRIDGE_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            found.append(bridge)
    return found or ["Precision"]


def recall_prior_reviews(project_name: str, k: int = 5) -> str:
    """Recall prior assurance case review findings."""
    if not _HAS_MEMORY:
        return ""
    try:
        client = MemoryClient(scope=MemoryScope.OPERATIONAL)
        result = client.recall(
            f"assurance case review {project_name} findings defeaters evidence gaps",
            k=k,
        )
        if result.found:
            logger.info(f"Found {len(result.items)} prior review entries")
            return result.to_context(max_items=k)
        return ""
    except Exception as e:
        logger.warning(f"Prior review recall failed: {e}")
        return ""


def learn_review(
    project_name: str,
    findings: Optional[str] = None,
    provider: str = "github",
    model: str = "",
    rounds_completed: int = 0,
) -> List[str]:
    """Learn review findings to memory."""
    if not _HAS_MEMORY:
        return []

    client = MemoryClient(scope=MemoryScope.OPERATIONAL)
    now = datetime.now().isoformat()
    learned_ids = []
    bridges = extract_bridges(findings or "")
    base_tags = ["assurance_review", project_name] + bridges

    summary = json.dumps({
        "project": project_name,
        "date": now,
        "provider": provider,
        "model": model,
        "rounds_completed": rounds_completed,
        "bridges": bridges,
    })

    try:
        result = client.learn(
            problem=f"Assurance case review: {project_name} ({now[:10]}) via {provider}/{model}",
            solution=summary,
            tags=base_tags + ["snapshot"],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
    except Exception as e:
        logger.warning(f"Failed to learn review snapshot: {e}")

    if findings:
        try:
            result = client.learn(
                problem=f"Assurance review findings for {project_name}",
                solution=findings[:4000],
                tags=base_tags + ["findings"],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
        except Exception as e:
            logger.warning(f"Failed to learn review findings: {e}")

    return learned_ids
