"""Generate dream-idea candidates by jumbling memory, code, and world events.

Human dreams don't isolate sources. A persona memory of betrayal collides with
a Brave Search headline about a rocket test, layered over project code about
false-green gates. The jumble is piped through scillm to synthesize an actual
surreal dream narrative.
"""
from __future__ import annotations

import random
from typing import Any

from . import memory_client, dream_synthesis


def _source_pillar(collection: str | None) -> str:
    c = (collection or "").lower()
    if c in ("persona_memory", "persona_memory_edges", "tom_edges"):
        return "persona"
    if c in ("persona_entity_edges", "persona_entities"):
        return "persona"
    if c in ("project_activity", "project_knowledge"):
        return "code"
    if c == "brave_search":
        return "events"
    return "unknown"


def _jumble_candidate(
    chunks_by_source: dict[str, list[dict[str, Any]]],
    persona_ids: list[str],
    about: str | None,
    rng: random.Random,
    base_id: int,
) -> dict[str, Any] | None:
    """Build one candidate by cross-sampling from 2-3 source pillars,
    then synthesizing a dream narrative via scillm."""
    available = [s for s, chunks in chunks_by_source.items() if chunks]
    if not available:
        return None

    n_sources = min(rng.choice([2, 3]), len(available))
    chosen_sources = rng.sample(available, k=n_sources)

    picked: list[dict[str, Any]] = []
    for src in chosen_sources:
        chunks = chunks_by_source[src]
        impacts = [memory_client.compute_impact(c) for c in chunks]
        total = sum(impacts) or 1.0
        weights = [i / total for i in impacts]
        idx = rng.choices(range(len(chunks)), weights=weights, k=1)[0]
        picked.append(chunks[idx])

    picked.sort(key=lambda c: memory_client.compute_impact(c), reverse=True)
    dominant = picked[0]
    supporting = picked[1:]

    # Synthesize a dream narrative from the jumbled chunks
    persona_id = rng.choice(persona_ids)
    supporting_texts = [s.get("retrieval_text") or s.get("text", "") for s in supporting]
    dream_text = dream_synthesis.synthesize_dream(
        persona_id,
        dominant.get("retrieval_text") or dominant.get("text", ""),
        supporting_texts,
        about=about,
    )

    source_ids = [c.get("source_id") for c in picked if c.get("source_id")]
    sources_used = list({_source_pillar(c.get("collection", "")) for c in picked})
    impact = sum(memory_client.compute_impact(c) for c in picked) / len(picked)

    return {
        "candidate_id": f"idea_{base_id}",
        "idea": dream_text,
        "source_memory_ids": source_ids,
        "sources_used": sources_used,
        "source_text_preview": dominant.get("retrieval_text") or dominant.get("text", "")[:200],
        "impact_score": round(impact, 4),
        "dominant_collection": dominant.get("collection", ""),
        "dominant_emotion": dominant.get("emotion", ""),
        "dominant_tom_state_type": dominant.get("tom_state_type", ""),
        "score_graph": dominant.get("score_graph", 0.0),
        "num_sources": len(sources_used),
    }


def generate_candidates(
    memory_chunks: list[dict[str, Any]],
    *,
    persona_ids: list[str],
    about: str | None = None,
    n_candidates: int = 3,
    rng_seed: int | None = None,
) -> list[dict[str, Any]]:
    """Sample N candidate ideas by jumbling across source pillars.

    Each candidate pulls 2-3 chunks from different pillars (persona, code, events),
    weighted by impact. The jumbled chunks are piped through scillm (gpt-5.5) to
    synthesize a surreal dream narrative — not a summary, but a visual, sensory,
    slightly disorienting dream scene one paragraph long.
    """
    chunks_by_source: dict[str, list[dict[str, Any]]] = {
        "persona": [],
        "code": [],
        "events": [],
    }
    for chunk in memory_chunks:
        pillar = _source_pillar(chunk.get("collection", ""))
        if pillar in chunks_by_source:
            chunks_by_source[pillar].append(chunk)
        else:
            chunks_by_source["persona"].append(chunk)

    if not any(chunks for chunks in chunks_by_source.values()):
        return []

    rng = random.Random(rng_seed)
    candidates: list[dict[str, Any]] = []

    for i in range(1, n_candidates + 1):
        candidate = _jumble_candidate(chunks_by_source, persona_ids, about, rng, i)
        if candidate:
            candidates.append(candidate)

    return candidates
