"""Thin client for the memory /recall endpoint with persona-graph traversal."""
from __future__ import annotations

from typing import Any

import httpx


PERSONA_SCOPE = "persona-dream"
PERSONA_COLLECTIONS = [
    "persona_memory",
    "persona_memory_edges",
    "tom_edges",
    "persona_entity_edges",
    "persona_entities",
]

# Code intensity signals — determined from text content (until memory service
# adds explicit failure/iteration/emotion fields for project_activity chunks).
CODE_INTENSITY_KEYWORDS: list[str] = [
    "failure", "failed", "fail",
    "error", "crash", "broken", "bug", "fix",
    "swear", "fuck", "damn", "shit",
    "iteration", "retry", "re-run", "second attempt",
    "urgent", "critical", "blocker", "deadline",
    "finally", "after hours", "late night",
]


# Emotion impact weights — higher = more dream-worthy
EMOTION_IMPACT: dict[str, float] = {
    "fear": 1.0,
    "anger": 0.9,
    "sadness": 0.85,
    "guilt": 0.9,
    "grief": 0.95,
    "dread": 1.0,
    "regret": 0.85,
    "joy": 0.5,
    "hope": 0.6,
    "trust": 0.5,
    "neutral": 0.3,
    "calm": 0.3,
}

# tom_state_type impact — how impactful a ToM state change is for dreaming
TOM_STATE_IMPACT: dict[str, float] = {
    "belief_change": 1.0,
    "belief": 0.8,
    "emotional_state": 0.9,
    "intention": 0.7,
    "desire": 0.85,
    "knowledge": 0.5,
    "fact": 0.4,
    "mention": 0.2,
}


def _call_recall(
    query: str,
    *,
    collections: list[str] | None = None,
    tags: list[str] | None = None,
    scope: str = "memory",
    k: int = 8,
    memory_url: str = "http://127.0.0.1:8601",
    timeout: float = 20.0,
) -> dict[str, Any]:
    request: dict[str, Any] = {"q": query, "scope": scope, "k": k}
    if collections:
        request["collections"] = collections
    if tags:
        request["tags"] = tags

    try:
        if memory_url.startswith("http"):
            with httpx.Client(base_url=memory_url.rstrip("/"), timeout=timeout) as client:
                resp = client.post("/recall", json=request)
                resp.raise_for_status()
                return resp.json()
        transport = httpx.HTTPTransport(uds=memory_url)
        with httpx.Client(transport=transport, base_url="http://localhost", timeout=timeout) as client:
            resp = client.post("/recall", json=request)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        return {"error": str(exc), "recall_request": request}


def recall_persona(
    persona_id: str,
    *,
    memory_url: str = "http://127.0.0.1:8601",
    k: int = 12,
) -> dict[str, Any]:
    """Recall persona memory with graph traversal (characters, events, places)."""
    return _call_recall(
        (
            f"What facts, relationships, and emotional memories define {persona_id}? "
            "Include character relationships, significant events, inner beliefs, and places they are connected to."
        ),
        collections=PERSONA_COLLECTIONS,
        tags=[f"persona:{persona_id}"],
        scope=PERSONA_SCOPE,
        k=k,
        memory_url=memory_url,
    )


def recall_tom_edges(
    persona_id: str,
    *,
    memory_url: str = "http://127.0.0.1:8601",
    k: int = 12,
) -> dict[str, Any]:
    """Recall theory-of-mind edges: beliefs, emotions, intentions, desires.

    The persona tag is omitted because ToM edges may reference the persona
    through _from/_to fields rather than a persona: tag.
    """
    return _call_recall(
        (
            f"What does {persona_id} believe, feel, desire, or fear? "
            "What emotional states and theory-of-mind beliefs exist for this persona?"
        ),
        collections=["persona_memory_edges", "tom_edges"],
        scope=PERSONA_SCOPE,
        k=k,
        memory_url=memory_url,
    )


def recall_project_context(
    about: str | None,
    *,
    memory_url: str = "http://127.0.0.1:8601",
    k: int = 12,
) -> dict[str, Any]:
    """Recall recent project activity and knowledge."""
    query = (
        f"What changed recently related to {about}?"
        if about
        else "What did we work on recently that could become a persona dream?"
    )
    return _call_recall(
        query,
        collections=["project_activity", "project_knowledge"],
        scope="memory",
        k=k,
        memory_url=memory_url,
    )


def extract_text_chunks(recall_result: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract text chunks from a recall result.

    Captures text, scores (bm25/dense/graph), collection source, and
    persona-specific fields like emotion, stance, tom_state_type for impact weighting.
    """
    chunks: list[dict[str, Any]] = []
    if not isinstance(recall_result, dict):
        return chunks

    candidates = (
        recall_result.get("items")
        or recall_result.get("results")
        or recall_result.get("rows")
        or recall_result.get("documents")
        or []
    )
    for item in candidates:
        if not isinstance(item, dict):
            continue
        text = _extract_text(item)
        if not text:
            continue

        scores = item.get("scores") or {}
        chunk = {
            "text": str(text),
            "source_id": item.get("_key") or item.get("id") or item.get("source_id", ""),
            "collection": item.get("_source") or item.get("collection", ""),
            "score_bm25": float(scores.get("bm25", 0.0)),
            "score_dense": float(scores.get("dense", 0.0)),
            "score_graph": float(scores.get("graph", 0.0)),
            "score_freshness": float(scores.get("freshness", 0.0)),
            "doc_type": item.get("doc_type", ""),
            "tags": item.get("tags", []),
            "title": item.get("title", ""),
            "persona_id": item.get("persona_id", ""),
            "book_id": item.get("book_id", ""),
            # Theory-of-mind fields — populated in different collections
            "tom_state_type": item.get("tom_state_type", ""),  # in tom_edges
            "emotion": item.get("emotion", ""),                # currently null in most records
            "stance": item.get("stance", ""),
            "edge_type": item.get("edge_type", ""),            # held_by, residue_for_persona
            "dream_safe": item.get("dream_safe", False),       # explicitly marked for dreams
            "canon_status": item.get("canon_status", ""),      # source_grounded vs inferred
            "edges": item.get("edges", ""),                    # relationship data with confidence
            "tom_tags": item.get("tom_tags", []),
            "relationship_type": item.get("relationship_type", ""),
            "from_canonical_name": item.get("from_canonical_name", ""),
            "to_canonical_name": item.get("to_canonical_name", ""),
            "retrieval_text": item.get("retrieval_text", ""),
            "claim_text": item.get("claim_text", ""),
            "evidence_text": item.get("evidence_text", ""),
            "mention_text": item.get("mention_text", ""),
            "canonical_name": item.get("canonical_name", ""),
            "entity_kind": item.get("entity_kind", ""),
            # Code intensity fields from project_activity ingestion
            "intensity_score": float(item.get("intensity_score", 0.0)),
            "failure_hints": float(item.get("failure_hints", 0.0)),
            "iteration_hints": float(item.get("iteration_hints", 0.0)),
            "swear_hints": float(item.get("swear_hints", 0.0)),
            "emotional_tags": item.get("emotional_tags", []),
            "churn_score": float(item.get("churn_score", 0.0)),
            "_from": item.get("_from", ""),
            "_to": item.get("_to", ""),
        }
        chunks.append(chunk)

    return chunks


def _extract_text(item: dict[str, Any]) -> str:
    """Extract the most useful text field from a memory item."""
    # Prioritize retrieval_text for persona memory (pre-formatted for LLM)
    for key in (
        "retrieval_text",
        "text",
        "content",
        "body",
        "solution",
        "problem",
        "title",
        "mention_text",
    ):
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def compute_impact(chunk: dict[str, Any]) -> float:
    """Compute dream-impact score using fields that actually exist in persona_memory.

    Weighted by real signals:
    - dream_safe: memories explicitly marked for dreaming (1.5x multiplier)
    - scores.graph: multi-hop connections via Arango traversal (40% of base)
    - scores.bm25: lexical relevance from recall (30% of base)
    - tom_state_type: from tom_edges — desire, belief, intention (30% additive)
    - canon_status: source_grounded > inferred > unknown
    - edge_type: held_by and residue_for_persona edges indicate direct persona connection
    """
    base = (
        chunk.get("score_bm25", 0.0) * 0.3
        + chunk.get("score_dense", 0.0) * 0.1
        + chunk.get("score_graph", 0.0) * 0.4  # graph connections = theory-of-mind depth
    )

    # dream_safe explicitly marks dream-appropriate memories
    dream_safe_boost = 1.5 if chunk.get("dream_safe") else 1.0

    # tom_state_type from edge documents (desire, belief, intention, emotional_state)
    tom_weight = TOM_STATE_IMPACT.get(
        (chunk.get("tom_state_type") or "").lower(), 0.3
    )

    # edge_type tells us how the memory connects to the persona
    edge_type = (chunk.get("edge_type") or "").lower()
    edge_boost = 0.0
    if edge_type in ("held_by", "residue_for_persona"):
        edge_boost = 0.3  # direct persona connection
    elif edge_type in ("belief", "desire", "intention"):
        edge_boost = 0.4  # explicit mental state

    # canon_status: source_grounded items are more trustworthy
    canon = (chunk.get("canon_status") or "").lower()
    canon_boost = 0.2 if canon == "source_grounded" else 0.0

    # Freshness: moderate boost, not dominance
    freshness = chunk.get("score_freshness", 0.0)
    freshness_boost = freshness * 0.2

    # Edge documents (connections, not facts) get a discount
    collection = chunk.get("collection", "")
    is_edge = collection in ("persona_memory_edges", "tom_edges", "persona_entity_edges")
    edge_multiplier = 0.7 if is_edge else 1.0

    # Code chunk intensity: use stored intensity_score from memory if available,
    # fall back to keyword heuristic if not yet populated.
    code_intensity = 0.0
    if collection in ("project_activity", "project_knowledge"):
        intensity_score = chunk.get("intensity_score", 0.0)
        if intensity_score > 0:
            # Real intensity from project_activity ingestion
            code_intensity = intensity_score * 1.5
        else:
            # Keyword fallback — used until project_activity is re-ingested
            text = (chunk.get("retrieval_text") or chunk.get("text") or "").lower()
            hits = sum(1 for kw in CODE_INTENSITY_KEYWORDS if kw in text)
            code_intensity = min(hits * 0.15, 0.6)

        # doc_type signals
        doc_type = (chunk.get("doc_type") or "").lower()
        if doc_type == "stale_chunk":
            code_intensity += 0.15  # iteration happened — content was replaced

    # If graph traversal found connections, boost impact
    has_graph = 1.5 if chunk.get("score_graph", 0.0) > 0.0 else 1.0

    return (base + tom_weight + edge_boost + canon_boost + code_intensity + freshness_boost) * dream_safe_boost * has_graph * edge_multiplier
