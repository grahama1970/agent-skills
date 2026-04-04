"""Heuristic QRA extraction fallback for doc2qra skill.

Provides rule-based question/answer extraction when LLM providers
are unavailable or fail. Uses section titles and first sentences
to construct QRA pairs without any LLM calls.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .text_handler import split_sentences


def extract_qa_heuristic(
    section_content: str,
    source: str = "",
    section_title: str = "",
) -> List[Dict[str, str]]:
    """Heuristic Q&A extraction from a section.

    Uses section title as question context, content as answer.

    Args:
        section_content: Text content to extract from
        source: Source identifier
        section_title: Title of the section

    Returns:
        List of QA dicts with problem and solution keys
    """
    content = section_content.strip()
    if not content:
        return []

    # Build problem from section title or first sentence
    if section_title:
        # Section title tells us what this is about
        problem = f"What is {section_title}?" if not section_title.endswith("?") else section_title
    else:
        # Use first sentence as context
        sents = split_sentences(content)
        problem = sents[0][:200] if sents else "Unknown topic"

    # Add source prefix
    if source:
        problem = f"[{source}] {problem}"

    # Solution is the section content (truncated if needed)
    solution = content[:1000] if len(content) > 1000 else content

    return [{"problem": problem, "solution": solution}]


def section_heuristic_fallback(
    sections: List[Tuple[str, str]],
    section_idx: int,
    source: str,
) -> List[Dict[str, Any]]:
    """Heuristic fallback for a single failed section.

    Args:
        sections: Full sections list
        section_idx: Index of failed section
        source: Source identifier

    Returns:
        List of QA dicts with section metadata
    """
    title, content = sections[section_idx]
    qa_pairs = extract_qa_heuristic(content, source=source, section_title=title)
    for qa in qa_pairs:
        qa["section_idx"] = section_idx
        qa["section_title"] = title
        qa["source"] = source
        qa["type"] = "text"
    return qa_pairs


def fallback_heuristic_extraction(
    sections: List[Tuple[str, str]],
    source: str,
) -> List[Dict[str, Any]]:
    """Full heuristic fallback when batch fails.

    Args:
        sections: List of (title, content) tuples
        source: Source identifier

    Returns:
        List of QA dicts with section metadata
    """
    all_qa = []
    for idx, (title, content) in enumerate(sections):
        qa_pairs = extract_qa_heuristic(content, source=source, section_title=title)
        for qa in qa_pairs:
            qa["section_idx"] = idx
            qa["section_title"] = title
            qa["source"] = source
            qa["type"] = "text"
        all_qa.extend(qa_pairs)
    return all_qa


# Backwards-compatible aliases
_section_heuristic_fallback = section_heuristic_fallback
_fallback_heuristic_extraction = fallback_heuristic_extraction
