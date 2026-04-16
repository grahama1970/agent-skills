"""
Memory + Taxonomy integration for /create-context.

Post-hook: After generating CONTEXT.md, learns key sections (decisions,
lessons, known issues, next steps) to memory with taxonomy bridge tags.
Enables recall of prior context across sessions for versioning and drift.

Pre-hook: Recalls prior contexts for the same project to surface what
changed since last handoff (delta/drift detection).

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
        _spec = importlib.util.spec_from_file_location("context_taxonomy", _TAXONOMY_PATH)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _taxonomy_extract = getattr(_mod, "extract_taxonomy", None)
    except Exception as e:
        logger.debug(f"Taxonomy module load failed: {e}")


# ---------------------------------------------------------------------------
# Bridge extraction
# ---------------------------------------------------------------------------

_BRIDGE_KEYWORDS = {
    "Precision": ["verification", "exact", "correct", "validated", "tested"],
    "Resilience": ["recovery", "fallback", "retry", "robust", "working"],
    "Fragility": ["broken", "failing", "risk", "incomplete", "gap", "issue", "bug"],
    "Corruption": ["security", "vulnerability", "exploit", "injection"],
    "Loyalty": ["dependency", "contract", "integration", "compatibility"],
    "Stealth": ["hidden", "implicit", "undocumented", "side effect"],
}


def extract_bridges(text: str) -> List[str]:
    """Extract taxonomy bridge attributes from context content."""
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
# Pre-hook: Recall prior contexts for delta/drift
# ---------------------------------------------------------------------------

def recall_prior_contexts(
    project_name: str,
    k: int = 3,
) -> str:
    """
    Recall prior context snapshots for a project.

    Returns formatted markdown showing what was previously recorded,
    enabling agents to detect what changed (delta/drift).
    Returns empty string if memory unavailable.
    """
    if not _HAS_MEMORY:
        return ""

    try:
        client = MemoryClient(scope=MemoryScope.OPERATIONAL)
        result = client.recall(
            f"context handoff {project_name} decisions lessons issues",
            k=k,
        )
        if result.found:
            return result.to_context(max_items=k)
        return ""
    except Exception as e:
        logger.warning(f"Prior context recall failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Post-hook: Learn context to memory
# ---------------------------------------------------------------------------

def learn_context(
    project_name: str,
    focus: str,
    git_branch: str = "",
    decisions: Optional[List[str]] = None,
    lessons: Optional[List[str]] = None,
    known_issues: Optional[List[str]] = None,
    next_steps: Optional[List[str]] = None,
    files_modified: Optional[List[str]] = None,
    context_path: str = "",
) -> List[str]:
    """
    Learn context snapshot to memory after CONTEXT.md generation.

    Stores:
    1. Context summary (project, date, branch, focus, file counts)
    2. Decisions made (for recall in future sessions)
    3. Lessons learned (for recall across projects)
    4. Known issues snapshot (for drift tracking)

    Returns list of learned lesson IDs (empty if memory unavailable).
    """
    if not _HAS_MEMORY:
        logger.info("Memory not available — skipping context learn")
        return []

    client = MemoryClient(scope=MemoryScope.OPERATIONAL)
    now = datetime.now().isoformat()
    learned_ids = []

    # Build content for bridge extraction
    all_text = " ".join([
        focus or "",
        " ".join(decisions or []),
        " ".join(lessons or []),
        " ".join(known_issues or []),
    ])
    bridges = extract_bridges(all_text)
    base_tags = ["context_handoff", project_name] + bridges

    # 1. Context summary snapshot
    summary = json.dumps({
        "project": project_name,
        "date": now,
        "focus": focus,
        "git_branch": git_branch,
        "files_modified": len(files_modified or []),
        "decisions_count": len(decisions or []),
        "issues_count": len(known_issues or []),
        "next_steps_count": len(next_steps or []),
        "bridges": bridges,
        "context_file": context_path,
    })

    try:
        result = client.learn(
            problem=f"Context snapshot: {project_name} ({now[:10]}) — {focus[:80]}",
            solution=summary,
            tags=base_tags + ["snapshot"],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
            logger.info(f"Learned context snapshot: {result.lesson_id}")
    except Exception as e:
        logger.warning(f"Failed to learn context snapshot: {e}")

    # 2. Decisions (individually, for fine-grained recall)
    for decision in (decisions or []):
        try:
            result = client.learn(
                problem=f"Decision in {project_name}: {decision[:100]}",
                solution=decision,
                tags=base_tags + ["decision"],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
        except Exception as e:
            logger.warning(f"Failed to learn decision: {e}")

    # 3. Lessons learned (cross-project value)
    for lesson in (lessons or []):
        try:
            result = client.learn(
                problem=f"Lesson from {project_name}: {lesson[:100]}",
                solution=lesson,
                tags=base_tags + ["lesson_learned"],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
        except Exception as e:
            logger.warning(f"Failed to learn lesson: {e}")

    # 4. Known issues snapshot (for drift tracking over time)
    if known_issues:
        try:
            result = client.learn(
                problem=f"Known issues: {project_name} ({now[:10]})",
                solution=json.dumps({
                    "project": project_name,
                    "date": now,
                    "issues": known_issues,
                    "count": len(known_issues),
                }),
                tags=base_tags + ["known_issues", "drift_tracking"],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
                logger.info(f"Learned issues snapshot: {result.lesson_id}")
        except Exception as e:
            logger.warning(f"Failed to learn issues snapshot: {e}")

    logger.info(f"Context learn complete: {len(learned_ids)} entries stored")
    return learned_ids
