"""Deterministic evidence-source ranking."""

from __future__ import annotations

from ..config import InterviewProfile
from ..models import EvidenceSource, Freshness, RetrievalLane


LANE_WEIGHT = {
    RetrievalLane.CODE: 0.12,
    RetrievalLane.MEMORY: 0.08,
    RetrievalLane.RIPGREP: 0.10,
    RetrievalLane.ASK: 0.16,
    RetrievalLane.BRAVE: -0.04,
    RetrievalLane.DOGPILE: -0.02,
}

FRESHNESS_WEIGHT = {
    Freshness.CURRENT: 0.12,
    Freshness.STALE: -0.20,
    Freshness.UNKNOWN: 0.0,
    Freshness.EXTERNAL: -0.05,
}


def rank_sources(
    sources: list[EvidenceSource],
    query: str,
    profile: InterviewProfile,
) -> list[EvidenceSource]:
    """Rank source-bound candidates without rewriting their evidence."""

    query_tokens = _tokens(query)
    priorities = {name.casefold(): index for index, name in enumerate(profile.repo_priorities)}

    def rank(source: EvidenceSource) -> tuple[float, str]:
        overlap = len(query_tokens & _tokens(f"{source.label} {source.excerpt}"))
        overlap_score = min(0.18, overlap * 0.025)
        repo_score = 0.0
        repo = (source.repository or "").casefold()
        if repo in priorities:
            repo_score = max(0.0, 0.08 - priorities[repo] * 0.01)
        locator_score = 0.05 if source.path or source.url else 0.0
        total = (
            source.score
            + LANE_WEIGHT[source.lane]
            + FRESHNESS_WEIGHT[source.freshness]
            + overlap_score
            + repo_score
            + locator_score
        )
        return total, source.label.casefold()

    return sorted(sources, key=rank, reverse=True)


def _tokens(text: str) -> set[str]:
    current: list[str] = []
    tokens: set[str] = set()
    for char in text.casefold():
        if char.isalnum() or char in {"-", "_"}:
            current.append(char)
        elif current:
            token = "".join(current).strip("-_")
            if len(token) >= 3:
                tokens.add(token)
            current = []
    if current:
        token = "".join(current).strip("-_")
        if len(token) >= 3:
            tokens.add(token)
    return tokens
