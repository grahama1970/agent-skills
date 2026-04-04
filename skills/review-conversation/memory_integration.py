"""Memory integration for review-conversation.

Composes with /memory via common.memory_client to provide:
- Semantic search across conversation sessions (BM25 + embedding + multi-hop)
- Post-stress-test learn hooks to ingest session summaries
- Graceful degradation when memory service is unavailable

Follows the canonical pattern from /best-practices-skills:
  - Pre-hook: recall before bespoke search
  - Post-hook: learn after completing work
  - Graceful degradation: return empty on failure
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

from loguru import logger

# ---------------------------------------------------------------------------
# Import common memory client (graceful degradation)
# ---------------------------------------------------------------------------

_SKILLS_DIR = Path(__file__).resolve().parents[1]
if str(_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR))

try:
    from common.memory_client import MemoryClient, MemoryScope

    _HAS_MEMORY = True
except ImportError:
    _HAS_MEMORY = False
    logger.debug("common.memory_client not available — memory features disabled")


_BRIDGE_KEYWORDS = {
    "Precision": ["accuracy", "quality", "grading", "score", "composite"],
    "Resilience": ["recovery", "retry", "fallback", "re-run"],
    "Fragility": ["failure", "unsatisfied", "regression", "broken"],
    "Loyalty": ["pipeline", "cascade", "conversation", "session"],
    "Stealth": ["edge case", "ambiguous", "adversarial"],
}


def extract_bridges(text: str) -> list[str]:
    """Extract taxonomy bridge attributes from conversation content."""
    text_lower = text.lower()
    found = []
    for bridge, keywords in _BRIDGE_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            found.append(bridge)
    return found or ["Precision"]


# ---------------------------------------------------------------------------
# Recall: semantic search for conversations
# ---------------------------------------------------------------------------


def recall_conversations(
    query: str,
    scope: str = "sparta",
    k: int = 10,
) -> list[dict[str, Any]]:
    """Search for conversation sessions via /memory recall.

    Uses BM25 + semantic embedding + multi-hop graph traversal.
    Returns list of matching items with problem/solution/metadata.
    Falls back to empty list if memory is unavailable.
    """
    if not _HAS_MEMORY:
        logger.warning("Memory not available — skipping semantic search")
        return []

    try:
        client = MemoryClient(scope=scope)
        result = client.recall(query, k=k)
        if result.found:
            return result.items
        return []
    except Exception as e:
        logger.warning(f"Memory recall failed: {e}")
        return []


def recall_conversations_context(
    query: str,
    scope: str = "sparta",
    k: int = 5,
) -> str:
    """Search for conversations and return formatted markdown context.

    Suitable for pasting directly into chat or agent prompts.
    """
    if not _HAS_MEMORY:
        return ""

    try:
        client = MemoryClient(scope=scope)
        result = client.recall(query, k=k)
        if result.found:
            return result.to_context(max_items=k)
        return ""
    except Exception as e:
        logger.warning(f"Memory recall failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Learn: ingest session summaries after stress tests
# ---------------------------------------------------------------------------


def learn_session(
    session: dict[str, Any],
    scope: str = "sparta",
    tags: Optional[list[str]] = None,
) -> Optional[str]:
    """Learn a single session summary to /memory for future recall.

    Extracts a problem/solution pair from the session data:
    - problem: question + difficulty + target_control + persona eval
    - solution: answer quality + grade + resolution + key findings

    Returns the lesson_id on success, None on failure.
    """
    if not _HAS_MEMORY:
        return None

    sid = session.get("session_id", "unknown")
    seed = session.get("seed_question", {})
    grade_data = session.get("grade", {}) or {}
    resolution = session.get("resolution", "unknown")
    persona = session.get("persona", "unknown")

    # Build problem: what was asked
    question = ""
    for turn in session.get("turns", []):
        if turn.get("action") in ("QUERY", "query"):
            question = turn.get("content", "")[:300]
            break

    target = seed.get("target_control", "")
    difficulty = seed.get("difficulty", "")

    # Build evaluations summary
    evals = []
    for turn in session.get("turns", []):
        meta = turn.get("metadata", {})
        ev = meta.get("evaluation")
        if ev:
            evals.append(ev)

    eval_str = " → ".join(evals) if evals else "no_eval"

    problem = (
        f"SPARTA session {sid}: {persona} asked about {target} "
        f"(difficulty={difficulty}). Persona evaluations: {eval_str}. "
        f"Question: {question}"
    )

    # Build solution: what happened
    grade_letter = grade_data.get("grade", "?")
    composite = grade_data.get("composite", 0)
    rationale = grade_data.get("rationale", "")[:200]
    turn_count = len(session.get("turns", []))

    solution = (
        f"Grade: {grade_letter} (composite={composite:.2f}), "
        f"resolution={resolution}, turns={turn_count}. "
        f"Rationale: {rationale}"
    )

    base_tags = ["review_conversation", "sparta_session", f"grade_{grade_letter}"]
    if difficulty:
        base_tags.append(f"difficulty_{difficulty}")
    if resolution:
        base_tags.append(f"resolution_{resolution}")
    if tags:
        base_tags.extend(tags)

    try:
        client = MemoryClient(scope=scope)
        result = client.learn(
            problem=problem,
            solution=solution,
            tags=base_tags,
        )
        if result.success:
            logger.info(f"Learned session {sid} → {result.lesson_id}")
            return result.lesson_id
        return None
    except Exception as e:
        logger.warning(f"Memory learn failed for {sid}: {e}")
        return None


def learn_batch(
    sessions: list[dict[str, Any]],
    scope: str = "sparta",
    tags: Optional[list[str]] = None,
) -> list[str]:
    """Learn multiple sessions to /memory. Returns list of learned IDs."""
    if not _HAS_MEMORY:
        return []

    learned = []
    for session in sessions:
        lid = learn_session(session, scope=scope, tags=tags)
        if lid:
            learned.append(lid)

    logger.info(f"Learned {len(learned)}/{len(sessions)} sessions to /memory")
    return learned


# ---------------------------------------------------------------------------
# Search: combine structured filters with semantic recall
# ---------------------------------------------------------------------------


def semantic_find(
    query: str,
    sessions: list[dict[str, Any]],
    scope: str = "sparta",
    k: int = 10,
) -> list[str]:
    """Use /memory recall to find session IDs matching a semantic query.

    Returns list of session_ids that match the query semantically.
    The caller can then cross-reference these with the structured session data.
    """
    items = recall_conversations(query, scope=scope, k=k)
    if not items:
        return []

    # Extract session IDs from recalled items
    session_ids = set()
    for item in items:
        # The problem field contains "SPARTA session {sid}: ..."
        problem = item.get("problem", "") or item.get("title", "")
        for session in sessions:
            sid = session.get("session_id", "")
            if sid and sid in problem:
                session_ids.add(sid)
                break

    return list(session_ids)


# ---------------------------------------------------------------------------
# Status check
# ---------------------------------------------------------------------------


def memory_available() -> bool:
    """Check if /memory is available for semantic search."""
    return _HAS_MEMORY
