"""Session resolution analysis for episodic archiver.

Codex 5.3 review fixes (2026-03-30):
- Uses msg_content()/msg_role() for all content extraction (not raw .get())
- Satisfaction/frustration detection works with Claude Code JSONL format
"""

import json
import time
from typing import Any, Dict, List

from loguru import logger
from memory_helpers import msg_content, msg_role, _memory_cmd, track_error


def extract_failure_episode(
    messages: List[Dict],
    categories: List[str],
    trigger_idx: int,
) -> Dict[str, Any]:
    """Extract a structured failure episode with trigger/diagnosis/action/outcome."""
    if trigger_idx >= len(messages):
        return {"trigger": "", "diagnosis": "", "actions": [], "outcome": "unknown", "confidence": 0.0}

    trigger_content = msg_content(messages[trigger_idx])[:500]

    context_start = max(0, trigger_idx - 2)
    context_end = min(len(messages), trigger_idx + 3)

    diagnosis_parts = []
    for msg in messages[context_start:context_end]:
        content = msg_content(msg)
        if any(kw in content.lower() for kw in ["because", "due to", "caused by", "reason", "issue", "problem"]):
            diagnosis_parts.append(content[:200])

    diagnosis = " | ".join(diagnosis_parts[:2]) if diagnosis_parts else "No explicit diagnosis found"

    actions = []
    for i in range(trigger_idx + 1, min(trigger_idx + 10, len(messages))):
        if i < len(categories) and categories[i] in ("task", "solution"):
            actions.append(msg_content(messages[i])[:200])
            if len(actions) >= 3:
                break

    outcome = "pending"
    confidence = 0.5
    remaining_cats = categories[trigger_idx + 1:trigger_idx + 15] if trigger_idx + 1 < len(categories) else []

    if "solution" in remaining_cats:
        solution_idx = remaining_cats.index("solution")
        after_solution = remaining_cats[solution_idx + 1:solution_idx + 5]
        if "error" in after_solution:
            outcome = "partial"
            confidence = 0.6
        else:
            outcome = "success"
            confidence = 0.7
    elif remaining_cats.count("error") >= 2:
        outcome = "failure"
        confidence = 0.8
    elif not remaining_cats or (remaining_cats and remaining_cats[-1] == "error"):
        outcome = "failure"
        confidence = 0.7

    return {
        "trigger": trigger_content,
        "diagnosis": diagnosis,
        "actions": actions,
        "outcome": outcome,
        "confidence": confidence,
    }


def analyze_session_resolution(messages: List[Dict], categories: List[str]) -> Dict[str, Any]:
    """Analyze if a session was resolved or has unfinished business."""
    unresolved_items = []

    has_error = "error" in categories
    has_solution = "solution" in categories
    ends_with_question = categories[-1] == "question" if categories else False
    ends_with_error = categories[-1] == "error" if categories else False

    failure_episodes = []

    for i, (msg, cat) in enumerate(zip(messages, categories)):
        content = msg_content(msg)[:300]

        if cat == "error":
            has_following_solution = "solution" in categories[i+1:i+5] if i+1 < len(categories) else False
            if not has_following_solution:
                unresolved_items.append({"type": "unresolved_error", "content": content})
            episode = extract_failure_episode(messages, categories, i)
            if episode.get("trigger"):
                failure_episodes.append(episode)

        if cat == "task":
            has_completion = any(c in ("solution", "meta") for c in categories[i+1:i+10]) if i+1 < len(categories) else False
            if not has_completion:
                unresolved_items.append({"type": "incomplete_task", "content": content})

    # Detect user satisfaction using msg_content + msg_role (not raw .get())
    satisfaction_signals = [
        "perfect", "great", "thanks", "excellent", "good job",
        "works", "working", "correct", "yes!", "nice",
        "love it", "exactly", "brilliant", "amazing", "awesome",
        "happy", "pleased", "satisfied", "well done", "nailed it",
        "that's it", "spot on", "beautiful", "ship it", "looks good",
    ]
    frustration_signals = [
        "wrong", "not what", "error", "failed", "no!",
        "frustrat", "livid", "angry", "annoyed", "stop",
        "shouldn't", "why did", "crashed", "broken", "terrible",
    ]

    user_satisfaction = False
    user_frustrated = False
    for msg in messages[-5:]:
        role = msg_role(msg)
        if role in ("user", "human"):
            content = msg_content(msg).lower()
            if any(sig in content for sig in satisfaction_signals):
                user_satisfaction = True
            if any(sig in content for sig in frustration_signals):
                user_frustrated = True

    resolved = True
    reason = "Session appears complete"
    confidence = 0.8
    satisfaction = "neutral"

    if user_satisfaction and not user_frustrated:
        resolved = True
        reason = "User expressed satisfaction"
        confidence = 0.95
        satisfaction = "satisfied"
    elif user_frustrated:
        resolved = False
        reason = "User expressed frustration"
        confidence = 0.9
        satisfaction = "frustrated"
    elif ends_with_error:
        resolved = False
        reason = "Session ended with an error"
        confidence = 0.9
        satisfaction = "likely_frustrated"
    elif ends_with_question:
        resolved = False
        reason = "Session ended with unanswered question"
        confidence = 0.7
    elif has_error and not has_solution:
        resolved = False
        reason = "Errors occurred without solutions"
        confidence = 0.8
    elif len(unresolved_items) > 2:
        resolved = False
        reason = f"Multiple unresolved items ({len(unresolved_items)})"
        confidence = 0.7

    return {
        "resolved": resolved,
        "reason": reason,
        "satisfaction": satisfaction,
        "unresolved_items": unresolved_items[:10],
        "failure_episodes": failure_episodes[:5],
        "confidence": confidence,
    }


def store_unresolved_session(session_id: str, resolution: Dict[str, Any], messages: List[Dict]):
    """Store unresolved session for later reflection via /memory."""
    try:
        all_content = " ".join(msg_content(m)[:200] for m in messages[:20])
        problem = f"Unresolved session {session_id}: {resolution.get('reason', 'unknown')}"
        solution = all_content[:1000]

        _memory_cmd([
            "learn",
            "--problem", problem,
            "--solution", solution,
            "--scope", "unresolved_sessions",
        ])
        logger.info(f"Stored unresolved session: {session_id}")
    except Exception as e:
        track_error("store_unresolved", str(e))
