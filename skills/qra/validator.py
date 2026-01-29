"""QRA Validator - Answer grounding validation.

This module validates that extracted answers are grounded in source text
using fuzzy string matching.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from qra.config import DEFAULT_GROUNDING_THRESHOLD
from qra.utils import log

# =============================================================================
# Grounding Validation
# =============================================================================


def check_grounding(
    qra_items: List[Dict[str, Any]],
    sections: List[Tuple[str, str]],
    threshold: float = DEFAULT_GROUNDING_THRESHOLD,
) -> Tuple[List[Dict[str, Any]], int, int]:
    """Validate QRA answers are grounded in source text.

    Uses rapidfuzz for fuzzy matching. Only validates answers (not questions)
    since questions can be phrased many ways but answers must be grounded.

    Args:
        qra_items: List of QRA dicts with section_idx
        sections: Original sections for lookup
        threshold: Minimum similarity score (0-1)

    Returns:
        Tuple of (grounded_items, kept_count, filtered_count)
    """
    try:
        from rapidfuzz import fuzz

        use_rapidfuzz = True
    except ImportError:
        use_rapidfuzz = False
        log("rapidfuzz not available, using word overlap", style="dim")

    grounded = []
    filtered = 0

    for item in qra_items:
        section_idx = item.get("section_idx", 0)
        if section_idx >= len(sections):
            grounded.append(item)
            continue

        source_text = sections[section_idx][1].lower()
        answer = item.get("answer", "").lower()

        if not answer:
            filtered += 1
            continue

        if use_rapidfuzz:
            score = fuzz.token_set_ratio(answer, source_text) / 100.0
        else:
            # Word overlap fallback
            score = _word_overlap_score(answer, source_text)

        if score >= threshold:
            item["grounding_score"] = round(score, 2)
            grounded.append(item)
        else:
            filtered += 1

    return grounded, len(grounded), filtered


def _word_overlap_score(answer: str, source_text: str) -> float:
    """Calculate word overlap score between answer and source.

    Args:
        answer: Answer text (lowercase)
        source_text: Source text (lowercase)

    Returns:
        Overlap score 0-1
    """
    answer_words = set(answer.split())
    source_words = set(source_text.split())
    if answer_words:
        return len(answer_words & source_words) / len(answer_words)
    return 0.0


def validate_qra_structure(qra: Dict[str, Any]) -> Tuple[bool, str]:
    """Validate QRA dict has required fields.

    Args:
        qra: QRA dictionary

    Returns:
        Tuple of (is_valid, error_message)
    """
    required = ["question", "answer"]
    missing = [f for f in required if not qra.get(f)]

    if missing:
        return False, f"Missing required fields: {missing}"

    if len(qra.get("question", "")) < 5:
        return False, "Question too short (< 5 chars)"

    if len(qra.get("answer", "")) < 3:
        return False, "Answer too short (< 3 chars)"

    return True, ""


def deduplicate_qras(
    qra_items: List[Dict[str, Any]],
    similarity_threshold: float = 0.9,
) -> List[Dict[str, Any]]:
    """Remove near-duplicate QRA pairs.

    Uses question similarity to detect duplicates.

    Args:
        qra_items: List of QRA dicts
        similarity_threshold: Minimum similarity to consider duplicate

    Returns:
        Deduplicated list
    """
    if not qra_items:
        return []

    try:
        from rapidfuzz import fuzz

        use_rapidfuzz = True
    except ImportError:
        use_rapidfuzz = False

    seen_questions: List[str] = []
    unique: List[Dict[str, Any]] = []

    for item in qra_items:
        question = item.get("question", "").lower()
        if not question:
            continue

        is_duplicate = False
        for seen in seen_questions:
            if use_rapidfuzz:
                sim = fuzz.ratio(question, seen) / 100.0
            else:
                # Simple word overlap
                q_words = set(question.split())
                s_words = set(seen.split())
                union = q_words | s_words
                sim = len(q_words & s_words) / len(union) if union else 0.0

            if sim >= similarity_threshold:
                is_duplicate = True
                break

        if not is_duplicate:
            seen_questions.append(question)
            unique.append(item)

    removed = len(qra_items) - len(unique)
    if removed > 0:
        log(f"Deduplication: removed {removed} duplicates", style="dim")

    return unique
