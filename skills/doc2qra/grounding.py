#!/usr/bin/env python3
"""Grounding validation for QRA extraction.

Validates that extracted QRA answers are grounded in the source text,
filtering out hallucinated content.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .config import DEFAULT_GROUNDING_THRESHOLD
from .utils import log


def check_grounding(
    qra_items: List[Dict[str, Any]],
    sections: List[Tuple[str, str]],
    threshold: float = DEFAULT_GROUNDING_THRESHOLD,
) -> Tuple[List[Dict[str, Any]], int, int]:
    """Validate QRA answers are grounded in source text.

    Uses rapidfuzz for fuzzy matching to catch paraphrased answers.
    Filters out hallucinated QRAs where the answer doesn't appear in the source.

    Args:
        qra_items: List of QRA dicts with section_idx
        sections: Original sections list for lookup
        threshold: Minimum similarity score (0-1) to consider grounded

    Returns:
        Tuple of (grounded_items, kept_count, filtered_count)
    """
    # Try to import rapidfuzz, fall back to simple word overlap
    try:
        from rapidfuzz import fuzz
        use_rapidfuzz = True
    except ImportError:
        use_rapidfuzz = False
        log("rapidfuzz not available, using word overlap for grounding", style="dim")

    grounded = []
    filtered = 0

    for item in qra_items:
        section_idx = item.get("section_idx", 0)
        if section_idx >= len(sections):
            grounded.append(item)  # Keep if can't validate
            continue

        source_text = sections[section_idx][1].lower()
        answer = item.get("answer", "").lower()

        if not answer:
            filtered += 1
            continue

        # Calculate grounding score
        if use_rapidfuzz:
            # Use token_set_ratio for best partial matching
            score = fuzz.token_set_ratio(answer, source_text) / 100.0
        else:
            # Simple word overlap fallback
            answer_words = set(answer.split())
            source_words = set(source_text.split())
            if answer_words:
                overlap = len(answer_words & source_words) / len(answer_words)
                score = overlap
            else:
                score = 0.0

        if score >= threshold:
            item["grounding_score"] = round(score, 2)
            grounded.append(item)
        else:
            filtered += 1

    return grounded, len(grounded), filtered


def validate_and_filter_qras(
    all_qa: List[Dict[str, Any]],
    sections: List[Tuple[str, str]],
    validate_grounding: bool = True,
    grounding_threshold: float = DEFAULT_GROUNDING_THRESHOLD,
) -> List[Dict[str, Any]]:
    """Post-process QRAs with optional grounding validation.

    Args:
        all_qa: All extracted QRA items
        sections: Source sections for grounding check
        validate_grounding: Whether to filter out ungrounded QRAs
        grounding_threshold: Minimum similarity score (0.0-1.0)

    Returns:
        Validated QRA list
    """
    if not validate_grounding or not all_qa:
        return all_qa

    grounded, kept, filtered = check_grounding(all_qa, sections, grounding_threshold)

    if filtered > 0:
        log(f"Grounding check: {kept} kept, {filtered} filtered (threshold={grounding_threshold})", style="yellow")
    else:
        log(f"Grounding check: all {kept} QRAs validated", style="green")

    return grounded
