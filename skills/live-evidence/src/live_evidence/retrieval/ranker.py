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
    repo_scope: set[str] | None = None,
) -> list[EvidenceSource]:
    """Rank source-bound candidates without rewriting their evidence.

    repo_scope: casefolded basenames of the repositories this meeting is
    about (from the configured repo roots). Memory recall is cross-project on
    this machine -- a Sparta question pulled a live-evidence "Open Questions"
    chunk that outscored the SPARTA memory index because it happened to
    mention SPARTA (caught by the agentic transcript eval). When scope is
    known, a memory source whose own project matches an in-scope repo is
    preferred, and a foreign local-memory project is penalized, so the card
    cites the meeting's own knowledge rather than a same-topic stranger.
    """

    query_tokens = _tokens(query)
    priorities = {name.casefold(): index for index, name in enumerate(profile.repo_priorities)}
    scope = repo_scope or set()

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
            + _project_affinity(source, scope)
        )
        return total, source.label.casefold()

    return sorted(sources, key=rank, reverse=True)


def _project_affinity(source: EvidenceSource, scope: set[str]) -> float:
    """Boost in-scope memory, penalize a foreign local-memory project."""

    if source.lane is not RetrievalLane.MEMORY or not scope:
        return 0.0
    meta = source.metadata or {}
    identity = " ".join(
        str(meta.get(field) or "") for field in ("_key", "source", "profile")
    ).casefold() + " " + (source.repository or "").casefold()
    if any(name in identity for name in scope):
        return 0.15
    # A local Claude Code memory doc that belongs to some OTHER project. The
    # penalty is firm (not symmetric with the boost): a same-topic chunk from
    # a foreign project scored ~0.94 and beat the in-scope SPARTA index at
    # ~0.79, so a light nudge was not decisive. For a meeting scoped to a
    # specific repo, another project's memory is genuinely off-target.
    if "local_memory__" in identity or "experiments-" in identity:
        return -0.30
    return 0.0


def _tokens(text: str) -> set[str]:
    current: list[str] = []
    tokens: set[str] = set()
    for char in text.casefold():
        if char.isalnum():
            current.append(char)
        elif current:
            token = "".join(current)
            if len(token) >= 3:
                tokens.add(token)
            current = []
    if current:
        token = "".join(current)
        if len(token) >= 3:
            tokens.add(token)
    return tokens
