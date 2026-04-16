"""Unresolved session management for episodic archiver.

Provides listing, resolution marking, and fix-success-rate metrics
for sessions that ended without full resolution. All persistence
goes through /memory subprocess calls.
"""

import json
import time
from collections import Counter
from typing import Any, Dict, List

from loguru import logger

from memory_helpers import _memory_cmd, _memory_recall


def list_unresolved():
    """List all unresolved sessions for reflection.

    Delegates context retrieval to /memory recall (scope=episodes)
    instead of raw AQL.
    """
    # Query /memory recall for unresolved session data
    hits = _memory_recall(
        query="unresolved pending session error failure",
        scope="",
        k=20,
        collections="agent_conversations",
    )

    # Query unresolved_sessions collection via /memory sample
    try:
        result = _memory_cmd([
            "sample",
            "--collection", "unresolved_sessions",
            "--filter", 'doc.status=="pending"',
        ])
        sessions = result if isinstance(result, list) else result.get("items", [])
        sessions.sort(key=lambda d: d.get("archived_at", 0), reverse=True)
        sessions = sessions[:20]
    except Exception as exc:
        logger.warning(f"Could not query unresolved_sessions collection: {exc}")
        sessions = []

    if not sessions and not hits:
        print("No unresolved sessions pending.")
        return

    if sessions:
        print(f"\n  {len(sessions)} UNRESOLVED SESSIONS:\n")
        print("-" * 80)

        for s in sessions:
            resolution = s.get("resolution", {})
            print(f"Session: {s.get('session_id', 'unknown')}")
            print(f"  Reason: {resolution.get('reason', 'unknown')}")
            print(f"  Items:  {len(resolution.get('unresolved_items', []))}")
            print(f"  Summary: {s.get('summary', '')[:100]}...")
            print()

        print("-" * 80)

    if hits:
        print(f"\n  Related episodic context ({len(hits)} hits from /memory recall):")
        for h in hits[:5]:
            print(f"  - [{h.get('category', '?')}] {h.get('body', '')[:80]}...")

    print("\nUse '/learn --from-gaps' to generate curiosity from these gaps.")


def mark_resolved(
    session_id: str,
    fix_description: str = None,
    lessons_used: List[str] = None,
    outcome: str = "success",
):
    """Mark a session as resolved and track what fixed it.

    This enables learning from successful fixes:
    - fix_description: What specific action resolved the issue
    - lessons_used: Which memory lessons contributed to the solution
    - outcome: success|partial|workaround

    Args:
        session_id: The session to mark resolved
        fix_description: Description of what fixed the issue
        lessons_used: List of lesson keys that helped
        outcome: Resolution quality (success, partial, workaround)
    """
    ts = int(time.time())

    # Build tag data for the resolution
    tag_data = {
        "status": "resolved",
        "resolved_at": ts,
        "resolution_outcome": outcome,
    }

    if fix_description:
        tag_data["fix_description"] = fix_description

    if lessons_used:
        tag_data["lessons_used"] = lessons_used

    try:
        # Tag the unresolved session as resolved via /memory
        _memory_cmd([
            "tag",
            "--collection", "unresolved_sessions",
            "--key", session_id.replace("/", "_").replace(" ", "_")[:64],
            "--data", json.dumps(tag_data),
        ])

        print(f"Marked session as resolved: {session_id}")
        if fix_description:
            print(f"  Fix: {fix_description[:100]}...")
        if lessons_used:
            print(f"  Lessons used: {', '.join(lessons_used[:5])}")
        print(f"  Outcome: {outcome}")

    except RuntimeError as e:
        logger.error(f"Failed to mark session resolved: {e}")
        print(f"Session not found or memory unavailable: {session_id}")


def get_fix_success_rate() -> Dict[str, Any]:
    """Calculate success rate metrics for fixes.

    Returns metrics for learning which fix patterns work:
    - Overall success rate
    - Success rate by lesson
    - Most effective fix patterns
    """
    try:
        result = _memory_cmd([
            "sample",
            "--collection", "unresolved_sessions",
            "--filter", "true",  # all docs
        ])
        all_docs = result if isinstance(result, list) else result.get("items", [])

        total = len(all_docs)
        resolved = sum(1 for d in all_docs if d.get("status") == "resolved")
        success = sum(1 for d in all_docs if d.get("resolution_outcome") == "success")
        partial = sum(1 for d in all_docs if d.get("resolution_outcome") == "partial")
        pending = sum(1 for d in all_docs if d.get("status") == "pending")

        # Lesson usage stats
        lesson_counter: Counter = Counter()
        for d in all_docs:
            if d.get("status") == "resolved" and d.get("lessons_used"):
                for lesson in d["lessons_used"]:
                    lesson_counter[lesson] += 1
        top_lessons = [
            {"lesson": l, "used_count": c}
            for l, c in lesson_counter.most_common(10)
        ]

        # Common fix patterns
        pattern_counter: Counter = Counter()
        for d in all_docs:
            if d.get("status") == "resolved" and d.get("fix_description"):
                pattern_counter[d["fix_description"][:50]] += 1
        common_fix_patterns = [
            {"pattern": p, "count": c}
            for p, c in pattern_counter.most_common(5)
        ]

        return {
            "total": total,
            "resolved": resolved,
            "success": success,
            "partial": partial,
            "pending": pending,
            "success_rate": resolved / total if total > 0 else 0,
            "top_lessons": top_lessons,
            "common_fix_patterns": common_fix_patterns,
        }
    except Exception as e:
        return {"error": str(e)}
