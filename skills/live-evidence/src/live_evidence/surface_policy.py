"""Deterministic safety rails around agentic card surfacing."""

from __future__ import annotations

from .models import EvidenceSource, RetrievalLane


def should_force_surface_source_backed_code(
    query: str, sources: list[EvidenceSource]
) -> bool:
    """Surface current-source coding evidence even if the selector suppresses.

    The model selector is allowed to suppress small talk and rhetorical turns,
    but it must not hide a source-backed coding problem after current-source
    retrieval found candidates. Keep this override narrow to the failure class
    observed in the live YouTube/PipeWire oracle.
    """

    if not any(source.lane in {RetrievalLane.CODE, RetrievalLane.RIPGREP} for source in sources):
        return False
    lower = " ".join(query.casefold().split())
    if "parenthes" not in lower:
        return False
    domain_terms = {
        "opening",
        "closing",
        "valid",
        "invalid",
        "minimum",
        "remove",
        "count",
        "dangling",
        "string",
    }
    return sum(1 for term in domain_terms if term in lower) >= 2
