"""Extractive evidence-card summarization.

The default summarizer cannot invent facts: it selects and trims sentences from
ranked sources, computes confidence from source state, and emits a visible
qualification. An optional future model lane can sit behind the same card model
only if it remains source-bound and receipt-gated.
"""

from __future__ import annotations

import re

from .models import (
    CardStatus,
    EvidenceCard,
    EvidenceSource,
    Freshness,
    RetrievalLane,
)


class ExtractiveSummarizer:
    """Produce one glanceable card from ranked evidence sources."""

    def build(self, query: str, thread: str, sources: list[EvidenceSource]) -> EvidenceCard:
        """Build a supported or explicit insufficient card."""

        selected = _select_with_lane_diversity(sources, 4)
        if not selected:
            return EvidenceCard(
                query=query,
                thread=thread,
                question=query,
                answer="No source-bound support surfaced yet.",
                evidence="Graph Memory and current-source retrieval returned no admissible evidence for this turn.",
                talking_point="No source-bound support surfaced yet.",
                proof="Graph Memory and current-source retrieval returned no admissible evidence for this turn.",
                qualifier="Do not improvise a repository claim. Answer from direct experience or ask for a narrower question.",
                confidence=0.0,
                status=CardStatus.INSUFFICIENT,
                sources=[],
                lanes=[],
            )

        primary = selected[0]
        answer = _answer_sentence(primary.excerpt, 1_600)
        talking_point = answer[:1_000]
        proof_parts = [_source_proof(source) for source in selected[:2]]
        proof = " · ".join(part for part in proof_parts if part)
        qualifier = _qualifier(selected)
        confidence = _confidence(selected)
        lanes = list(dict.fromkeys(source.lane for source in selected))
        return EvidenceCard(
            query=query,
            thread=thread,
            question=query,
            answer=answer,
            evidence=proof or _sentence(primary.excerpt, 520),
            talking_point=talking_point,
            proof=proof or _sentence(primary.excerpt, 520),
            qualifier=qualifier,
            confidence=confidence,
            status=CardStatus.SUPPORTED,
            sources=selected,
            lanes=lanes,
        )


def _select_with_lane_diversity(
    sources: list[EvidenceSource], limit: int
) -> list[EvidenceSource]:
    """Top-ranked sources, but every lane that produced evidence keeps a seat.

    Ripgrep sources carry structural rank bonuses (CURRENT freshness + path
    locator) that memory recall cannot earn, so four code hits could sweep
    every card slot even when the question is answered by a memory document
    (observed live: the Sparta hard-rules card published ripgrep-only while
    the memory index held the answer as its top recall hit).
    """

    selected = list(sources[:limit])
    for source in sources[limit:]:
        lanes = {item.lane for item in selected}
        if source.lane in lanes:
            continue
        for index in range(len(selected) - 1, -1, -1):
            candidate = selected[index]
            if sum(1 for item in selected if item.lane == candidate.lane) > 1:
                selected[index] = source
                break
        else:
            continue
    return selected


def _answer_sentence(text: str, limit: int) -> str:
    oracle = _oracle_answer_text(text)
    if oracle:
        return _bounded_text(oracle, limit)
    return _sentence(text, limit)


def _bounded_text(text: str, limit: int) -> str:
    clean = " ".join(text.split())
    clean = re.sub(r"(?:^|(?<= ))#{1,6}\s*", "", clean)
    clean = clean.lstrip("#*>-— \t")
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "…"


def _oracle_answer_text(text: str) -> str:
    clean = " ".join(text.split())
    for marker in ("Reviewed solution:", "Expected solution:", "A:"):
        index = clean.find(marker)
        if index >= 0:
            return clean[index + len(marker):].lstrip(" -—:\t")
    return ""


def _sentence(text: str, limit: int) -> str:
    # Strip leading markdown header/emphasis noise so the answer opens on the
    # document's actual content, not its title ("# SPARTA Project Memory Index
    # ## READ FIRST"). Without this the extractive answer was a bare header.
    clean = " ".join(text.split())
    clean = re.sub(r"(?:^|(?<= ))#{1,6}\s*", "", clean)
    clean = clean.lstrip("#*>-— \t")
    if len(clean) <= limit:
        return clean
    # " — " (em-dash) is deliberately NOT a boundary: it joins phrases inside a
    # heading ("READ FIRST — HARD RULES") and cutting there returned the header
    # alone (caught by the agentic transcript eval on the SPARTA rules card).
    boundaries = [clean.rfind(mark, 0, limit) for mark in (". ", "; ", ": ")]
    boundary = max(boundaries)
    if boundary >= int(limit * 0.55):
        return clean[: boundary + 1].strip()
    return clean[: limit - 1].rstrip() + "…"


def _source_proof(source: EvidenceSource) -> str:
    locator = source.repository or ""
    if source.path:
        name = source.path.rsplit("/", 1)[-1]
        locator = f"{locator}/{name}" if locator else name
    if source.line_start:
        locator += f":{source.line_start}"
    excerpt = _sentence(source.excerpt, 260)
    return f"{excerpt} [{locator or source.label}]"


def _qualifier(sources: list[EvidenceSource]) -> str:
    if any(source.freshness is Freshness.STALE for source in sources):
        return "At least one indexed source is stale. Use the current checkout before quoting implementation detail."
    if all(source.lane in {RetrievalLane.BRAVE, RetrievalLane.DOGPILE} for source in sources):
        return "External results are research leads, not proof of Graham's implementation or the current client context."
    if any(source.freshness is Freshness.UNKNOWN for source in sources):
        return "Relevant evidence surfaced, but freshness is not established for every source. Keep the claim bounded."
    return "Current source supports the point; it still does not prove semantic correctness beyond the cited artifact."


def _confidence(sources: list[EvidenceSource]) -> float:
    top = sources[:3]
    base = sum(source.score for source in top) / len(top)
    if any(source.freshness is Freshness.STALE for source in top):
        base -= 0.22
    if top and top[0].freshness is Freshness.CURRENT:
        base += 0.08
    return round(max(0.0, min(0.99, base)), 2)
