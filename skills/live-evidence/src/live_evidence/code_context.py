"""Recover code-problem context from admitted evidence."""

from __future__ import annotations

from .models import EvidenceSource, RetrievalLane
from .query_bounds import bounded_query


def current_source_query_from_memory(query: str, sources: list[EvidenceSource]) -> str:
    """Derive a current-source query when Memory names the coding problem.

    Live STT sometimes accepts only the tail of a coding interview explanation
    while Memory still identifies the intended LeetCode problem. Use that
    admitted source text to give ripgrep a second, bounded chance to find the
    current checkout implementation.
    """

    memory_text = " ".join(
        f"{source.label} {source.excerpt}"
        for source in sources[:6]
        if source.lane is RetrievalLane.MEMORY
    )
    if not memory_text:
        return ""
    bounded = bounded_query(f"{query} {memory_text}", None)
    lower = bounded.casefold()
    if "remove the minimum number of parentheses" not in lower or "valid" not in lower:
        return ""
    return (
        f"{bounded} source code implementation "
        "remove_invalid_parentheses valid_parentheses"
    )
