"""
Memory + Taxonomy integration for /review-code.

Pre-hook: Before running a code review, recalls prior review findings for the
same project/files to surface patterns already seen (e.g., "we found this
race condition before in auth.py").

Post-hook: After review completes, learns review findings, severity counts,
and provider used to memory with taxonomy bridge tags. Enables cross-session
pattern detection and institutional review memory.

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
        _spec = importlib.util.spec_from_file_location("review_taxonomy", _TAXONOMY_PATH)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _taxonomy_extract = getattr(_mod, "extract_taxonomy", None)
    except Exception as e:
        logger.debug(f"Taxonomy module load failed: {e}")


# ---------------------------------------------------------------------------
# Bridge extraction
# ---------------------------------------------------------------------------

_BRIDGE_KEYWORDS = {
    "Precision": ["correct", "verified", "clean", "passes", "tested", "validated", "lint-free"],
    "Resilience": ["error handling", "robust", "retry", "fallback", "graceful", "recovery", "defensive"],
    "Fragility": ["bug", "vulnerability", "race condition", "crash", "undefined", "flaky", "leak", "deadlock"],
    "Corruption": ["security", "injection", "XSS", "CSRF", "SQL injection", "auth bypass", "privilege escalation"],
    "Loyalty": ["dependency", "breaking change", "API contract", "backward compatible", "interface"],
    "Stealth": ["hidden", "side effect", "implicit", "undocumented", "magic number", "tech debt"],
}


def extract_bridges(text: str) -> List[str]:
    """Extract taxonomy bridge attributes from review content."""
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
# Pre-hook: Recall prior reviews for the same project/files
# ---------------------------------------------------------------------------

def recall_prior_reviews(
    project_name: str,
    file_path: Optional[str] = None,
    k: int = 5,
) -> str:
    """
    Recall prior review findings for a project or specific files.

    Called BEFORE starting a new code review. Surfaces patterns already
    identified in prior reviews (e.g., recurring bugs, known fragile areas,
    previously-flagged security issues).

    Returns formatted markdown of prior findings, or empty string if
    memory unavailable or no prior reviews found.
    """
    if not _HAS_MEMORY:
        return ""

    try:
        client = MemoryClient(scope=MemoryScope.OPERATIONAL)
        query_parts = [f"code review {project_name} findings"]
        if file_path:
            query_parts.append(file_path)
        query_parts.append("bugs vulnerabilities patterns")

        result = client.recall(
            " ".join(query_parts),
            k=k,
        )
        if result.found:
            logger.info(f"Found {len(result.items)} prior review entries for: {project_name}")
            return result.to_context(max_items=k)
        return ""
    except Exception as e:
        logger.warning(f"Prior review recall failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Post-hook: Learn review findings to memory
# ---------------------------------------------------------------------------

def learn_review(
    project_name: str,
    files_reviewed: Optional[List[str]] = None,
    findings: Optional[str] = None,
    severity_counts: Optional[Dict[str, int]] = None,
    provider: str = "github",
    model: str = "",
    rounds_completed: int = 0,
    diff_generated: bool = False,
) -> List[str]:
    """
    Learn review findings to memory after code review completes.

    Stores:
    1. Review summary (project, provider, model, severity breakdown)
    2. Review findings (the actual issues found, for pattern detection)

    Returns list of learned lesson IDs (empty if memory unavailable).
    """
    if not _HAS_MEMORY:
        logger.info("Memory not available — skipping review learn")
        return []

    client = MemoryClient(scope=MemoryScope.OPERATIONAL)
    now = datetime.now().isoformat()
    learned_ids = []

    # Build content for bridge extraction
    all_text = " ".join(filter(None, [
        project_name,
        findings or "",
        " ".join(files_reviewed or []),
    ]))
    bridges = extract_bridges(all_text)
    base_tags = ["code_review", project_name] + bridges

    # 1. Review summary snapshot
    summary = json.dumps({
        "project": project_name,
        "date": now,
        "provider": provider,
        "model": model,
        "files_reviewed": files_reviewed or [],
        "files_count": len(files_reviewed or []),
        "severity_counts": severity_counts or {},
        "rounds_completed": rounds_completed,
        "diff_generated": diff_generated,
        "bridges": bridges,
    })

    try:
        result = client.learn(
            problem=f"Code review: {project_name} ({now[:10]}) via {provider}/{model}",
            solution=summary,
            tags=base_tags + ["snapshot"],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
            logger.info(f"Learned review snapshot: {result.lesson_id}")
    except Exception as e:
        logger.warning(f"Failed to learn review snapshot: {e}")

    # 2. Review findings (the actual issues, for pattern recall)
    if findings:
        try:
            # Truncate very long findings to stay within memory limits
            findings_content = findings[:4000] if len(findings) > 4000 else findings
            result = client.learn(
                problem=f"Review findings for {project_name}: issues and recommendations",
                solution=findings_content,
                tags=base_tags + ["findings"],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
                logger.info(f"Learned review findings: {result.lesson_id}")
        except Exception as e:
            logger.warning(f"Failed to learn review findings: {e}")

    logger.info(f"Review learn complete: {len(learned_ids)} entries stored for '{project_name}'")
    return learned_ids
