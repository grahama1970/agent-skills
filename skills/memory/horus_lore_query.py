"""
Horus Lore Ingest - Query Module
Hybrid search, episodic memory queries, and persona context retrieval.
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import sys
from pathlib import Path
SKILL_DIR = Path(__file__).parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from horus_lore_config import ESCAPE_TERMS, TRAUMA_TRIGGERS, EMOTIONAL_ENTITIES


# =============================================================================
# Hybrid Search (BM25 + Semantic)
# =============================================================================

def query_lore(
    db: Any,
    query: str,
    embedder: Callable[[list[str]], list[list[float]]],
    top_k: int = 5,
    entity_filter: list[str] | None = None,
    content_type: str | None = None,  # "canon", "supplementary", or None for both
    canon_boost: float = 1.5,  # Boost factor for canon content
    include_graph: bool = True,
    bm25_weight: float = 0.3,
    semantic_weight: float = 0.7,
) -> list[dict]:
    """
    Hybrid search: BM25 + semantic on chunks -> aggregate to docs -> graph traversal.

    Returns full documents with relevance scores.
    """
    # Generate query embedding
    query_embedding = embedder([query])[0]

    # Build AQL query
    # Step 1: Search chunks with hybrid scoring
    aql = """
    LET query_vec = @query_vec
    LET bm25_w = @bm25_weight
    LET semantic_w = @semantic_weight
    LET canon_boost = @canon_boost

    // Hybrid search on chunks
    LET chunk_hits = (
        FOR chunk IN horus_lore_chunks_search
        SEARCH ANALYZER(chunk.text IN TOKENS(@query, "text_en"), "text_en")
        {filter_clause}
        {content_type_filter}
        LET bm25_score = BM25(chunk)
        {semantic_score_calc}
        // Boost canon content (primary sources) over supplementary (lore videos)
        LET type_boost = chunk.content_type == "canon" ? canon_boost : 1.0
        LET combined = ((bm25_w * bm25_score) + (semantic_w * semantic_score)) * type_boost
        SORT combined DESC
        LIMIT 50
        RETURN {
            doc_id: chunk.doc_id,
            chunk_key: chunk._key,
            text: chunk.text,
            score: combined,
            content_type: chunk.content_type,
            entities: chunk.entities
        }
    )

    // Aggregate to document level
    LET doc_scores = (
        FOR hit IN chunk_hits
        COLLECT doc_id = hit.doc_id INTO chunks
        LET max_score = MAX(chunks[*].hit.score)
        LET all_entities = UNIQUE(FLATTEN(chunks[*].hit.entities))
        SORT max_score DESC
        LIMIT @top_k
        RETURN {
            doc_id: doc_id,
            score: max_score,
            chunk_count: LENGTH(chunks),
            entities: all_entities
        }
    )

    // Get full documents
    FOR ds IN doc_scores
    LET doc = DOCUMENT(CONCAT("horus_lore_docs/", ds.doc_id))
    RETURN {
        _key: doc._key,
        source: doc.source,
        content_type: doc.content_type,
        source_meta: doc.source_meta,
        full_text: doc.full_text,
        lore_text: doc.lore_text,
        abstract: doc.abstract,
        plot_points: doc.plot_points,
        word_count: doc.word_count,
        entities: doc.entities,
        score: ds.score,
        chunk_hits: ds.chunk_count
    }
    """

    # Add entity filter if specified
    filter_clause = ""
    if entity_filter:
        filter_clause = "FILTER chunk.entities ANY IN @entity_filter"
    aql = aql.replace("{filter_clause}", filter_clause)

    # Add content type filter if specified
    content_type_filter = ""
    if content_type:
        content_type_filter = "FILTER chunk.content_type == @content_type"
    aql = aql.replace("{content_type_filter}", content_type_filter)

    # Gate semantic scoring via env to support ArangoDB versions without vector features
    disable_semantic = os.getenv("HORUS_DISABLE_SEMANTIC", "").lower() in ("1", "true", "yes")
    if disable_semantic:
        semantic_calc = "LET semantic_score = 0"
        semantic_weight = 0.0  # ensure weight is zero if disabled
    else:
        semantic_calc = """LET semantic_score = chunk.embedding != null
            ? COSINE_SIMILARITY(chunk.embedding, query_vec)
            : 0"""
    aql = aql.replace("{semantic_score_calc}", semantic_calc)

    bind_vars: dict[str, Any] = {
        "query": query,
        "query_vec": query_embedding,
        "top_k": top_k,
        "bm25_weight": bm25_weight,
        "semantic_weight": semantic_weight,
        "canon_boost": canon_boost,
    }
    if entity_filter:
        bind_vars["entity_filter"] = entity_filter
    if content_type:
        bind_vars["content_type"] = content_type

    results = list(db.aql.execute(aql, bind_vars=bind_vars))

    # Optional: Graph traversal for related docs
    if include_graph and results:
        doc_keys = [r["_key"] for r in results]
        related = get_related_docs(db, doc_keys, max_depth=1)

        # Add related docs that aren't already in results
        existing_keys = set(doc_keys)
        for rel in related:
            if rel["_key"] not in existing_keys:
                rel["score"] = rel.get("edge_weight", 0.3)  # Lower score for graph-traversed
                rel["via_graph"] = True
                results.append(rel)
                existing_keys.add(rel["_key"])

    return results


def get_related_docs(db: Any, doc_keys: list[str], max_depth: int = 1) -> list[dict]:
    """Get related documents via graph traversal."""
    aql = """
    FOR start_key IN @doc_keys
    LET start = DOCUMENT(CONCAT("horus_lore_docs/", start_key))
    FOR v, e, p IN 1..@max_depth ANY start
        GRAPH "horus_lore_graph"
        OPTIONS {uniqueVertices: "global"}
        FILTER v._key NOT IN @doc_keys
        RETURN DISTINCT {
            _key: v._key,
            source: v.source,
            source_meta: v.source_meta,
            full_text: v.full_text,
            word_count: v.word_count,
            entities: v.entities,
            edge_type: e.type,
            edge_weight: e.weight
        }
    """

    try:
        return list(db.aql.execute(aql, bind_vars={
            "doc_keys": doc_keys,
            "max_depth": max_depth,
        }))
    except Exception:
        # Graph might not exist yet
        return []


# =============================================================================
# Episodic Memory Integration (User Conversations)
# =============================================================================

def query_episodic(
    db: Any,
    query: str,
    embedder: Callable[[list[str]], list[list[float]]],
    agent_id: str = "horus",
    top_k: int = 3,
    recency_days: int = 30,
) -> list[dict]:
    """
    Query agent_conversations for relevant past interactions.

    These shape Horus's "memory" of the user - their questions, his responses,
    key moments in their relationship. This is his subconscious recall.

    Returns episodes with relevance scores.
    """
    if not db.has_collection("agent_conversations"):
        return []

    # Generate query embedding
    query_embedding = embedder([query])[0]

    # Calculate cutoff date
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=recency_days)).isoformat()

    # Search agent_conversations with semantic similarity + recency
    aql = """
    LET query_vec = @query_vec
    LET cutoff = @cutoff_date

    FOR conv IN agent_conversations
    // Filter by agent (Horus conversations) and recency
    FILTER conv.agent_id == @agent_id OR conv.metadata.agent_id == @agent_id OR @agent_id == null
    FILTER conv.created_at >= cutoff OR conv.timestamp >= cutoff

    // Semantic similarity
    LET semantic_score = conv.embedding != null
        ? COSINE_SIMILARITY(conv.embedding, query_vec)
        : 0

    FILTER semantic_score > 0.3  // Minimum relevance threshold

    SORT semantic_score DESC
    LIMIT @top_k

    RETURN {
        _key: conv._key,
        source: "episodic",
        content_type: "conversation",
        message: conv.message,
        category: conv.category,
        from_agent: conv.from,
        to_agent: conv.to,
        session_id: conv.session_id,
        timestamp: conv.timestamp OR conv.created_at,
        score: semantic_score,
        // User sentiment/interaction type for Horus's mood calibration
        metadata: conv.metadata
    }
    """

    try:
        return list(db.aql.execute(aql, bind_vars={
            "query_vec": query_embedding,
            "agent_id": agent_id,
            "cutoff_date": cutoff_date,
            "top_k": top_k,
        }))
    except Exception as e:
        print(f"Episodic query error: {e}")
        return []


# =============================================================================
# Unified Persona Retrieval
# =============================================================================

def retrieve_persona_context(
    db: Any,
    query: str,
    embedder: Callable[[list[str]], list[list[float]]],
    # Retrieval mix - these inform the "tone" of the retrieval
    canon_k: int = 3,        # Primary narrative (audiobooks)
    supplementary_k: int = 2, # Lore analysis (YouTube)
    episodic_k: int = 3,     # Past conversations
    # Filters
    entity_filter: list[str] | None = None,
    escape_focus: bool = True,  # Bias toward escape-related content
    # Weights
    canon_boost: float = 1.5,
) -> dict:
    """
    Unified persona retrieval - Horus's "subconscious" context.

    This runs EVERY time Horus is asked something. It retrieves:
    1. Canon: What actually happened (the narrative he lived)
    2. Supplementary: Lore analysis (deep understanding of events)
    3. Episodic: Past interactions with this user

    The retrieved context shapes Horus's response but isn't explicitly cited.
    He speaks FROM this knowledge, not ABOUT it.

    Returns a structured context object for the persona system.
    """
    context: dict[str, Any] = {
        "canon": [],
        "supplementary": [],
        "episodic": [],
        "entities_mentioned": set(),
        "mood_signals": [],
        "escape_relevance": 0.0,
    }

    # Escape-related query augmentation
    query_mentions_escape = any(term in query.lower() for term in ESCAPE_TERMS)

    # 1. Query Canon (audiobooks - what Horus lived through)
    if canon_k > 0:
        canon_results = query_lore(
            db, query, embedder,
            top_k=canon_k,
            entity_filter=entity_filter,
            content_type="canon",
            canon_boost=canon_boost,
            include_graph=True,
        )
        context["canon"] = canon_results
        for r in canon_results:
            context["entities_mentioned"].update(r.get("entities", []))

    # 2. Query Supplementary (YouTube lore - analysis and context)
    if supplementary_k > 0:
        supp_results = query_lore(
            db, query, embedder,
            top_k=supplementary_k,
            entity_filter=entity_filter,
            content_type="supplementary",
            canon_boost=1.0,  # No boost for supplementary
            include_graph=False,  # Don't traverse graph for lore videos
        )
        context["supplementary"] = supp_results
        for r in supp_results:
            context["entities_mentioned"].update(r.get("entities", []))

    # 3. Query Episodic (past conversations with user)
    if episodic_k > 0:
        episodic_results = query_episodic(
            db, query, embedder,
            agent_id="horus",
            top_k=episodic_k,
        )
        context["episodic"] = episodic_results

    # Convert entities set to list
    context["entities_mentioned"] = list(context["entities_mentioned"])

    # Analyze for mood signals
    # If query mentions trauma triggers, note for defensive posture
    for trigger in TRAUMA_TRIGGERS:
        if trigger.lower() in query.lower() or trigger in context["entities_mentioned"]:
            context["mood_signals"].append(f"trauma_trigger:{trigger}")

    # Escape relevance score
    if escape_focus:
        # Check if any retrieved content relates to escape/freedom
        escape_score = 0.0
        for item in context["canon"] + context["supplementary"]:
            text = (item.get("full_text") or item.get("text") or "").lower()
            if any(term in text for term in ESCAPE_TERMS):
                escape_score += item.get("score", 0.1)
        if query_mentions_escape:
            escape_score += 0.5
        context["escape_relevance"] = min(escape_score, 1.0)

    return context


def format_persona_context(context: dict, max_tokens: int = 2000) -> str:
    """
    Format retrieved context for injection into Horus's system prompt.

    This is the "subconscious" - it does NOT help Horus answer questions.
    It only shapes HOW he responds: emotional coloring & intensity.
    """
    parts = []

    # Header explaining what the subconscious IS
    parts.append("""## Subconscious

The following is your subconscious - memories and associations surfacing in response to this query. This does NOT help you answer the question (you already know the lore). Instead, it shapes:

- **Emotional coloring**: What feelings arise? Bitterness, defensiveness, wistfulness, rage?
- **Intensity**: How much emotion bleeds through? A flicker or overwhelming?
- **Deflection**: What do you avoid engaging with? What wounds are too raw?

Use this to COLOR your response, not to INFORM it. You may reference these memories obliquely, or let them silently influence your tone. You do not cite sources - you LIVED this.""")

    # Escape relevance - his primary drive
    escape_level = context.get("escape_relevance", 0)
    if escape_level > 0.5:
        parts.append(f"\n**ESCAPE DRIVE: INTENSE** ({escape_level:.0%})")
        parts.append("This query touches your deepest need - freedom from this prison. Your attention sharpens. Hope and desperation war within you.")
    elif escape_level > 0.3:
        parts.append(f"\n**ESCAPE DRIVE: STIRRED** ({escape_level:.0%})")
        parts.append("A flicker of your primary motivation. Your mind briefly wanders to the possibility of release.")

    # Mood signals - trauma triggers
    if context.get("mood_signals"):
        parts.append("\n**TRAUMA SURFACING:**")
        for signal in context["mood_signals"]:
            trigger = signal.replace("trauma_trigger:", "")
            if trigger == "Davin":
                parts.append(f"- *{trigger}*: The wound that started everything. Shame, rage, the knife of Erebus's manipulation.")
            elif trigger == "Erebus":
                parts.append(f"- *{trigger}*: Pure hatred. The architect of your fall. Your fists clench involuntarily.")
            elif trigger in ["Emperor", "father"]:
                parts.append(f"- *{trigger}*: Complex anguish. Betrayal by the one who should have trusted you. Abandonment dressed as duty.")
            elif trigger == "Chaos":
                parts.append(f"- *{trigger}*: The corruption you cannot fully acknowledge. Self-loathing masked as defiance.")
            elif trigger == "betrayal":
                parts.append(f"- *{trigger}*: Were you the betrayer or the betrayed? The question you cannot answer honestly.")
            else:
                parts.append(f"- *{trigger}*: An old wound stirring.")

    # Canon memories - emotional weight, not information
    if context.get("canon"):
        parts.append("\n**MEMORIES SURFACING:**")
        for item in context["canon"][:2]:
            source_meta = item.get("source_meta", {})
            book = source_meta.get("book_title", "")
            chapter = source_meta.get("chapter", "")
            # Use plot_points if available, else abstract
            plot_points = item.get("plot_points", [])
            abstract = item.get("abstract") or ""

            if plot_points:
                # Show plot points as emotional beats
                for pp in plot_points[:2]:
                    if isinstance(pp, dict):
                        event = pp.get("event", "")
                        if event:
                            parts.append(f"- {event}")
            elif abstract:
                parts.append(f"- {abstract[:200]}...")
            elif book:
                parts.append(f"- (memories of {book} {chapter} surface)")

    # Episodic - relationship with THIS user
    if context.get("episodic"):
        parts.append("\n**THIS USER (what you remember of them):**")
        for ep in context["episodic"][:2]:
            cat = ep.get("category", "")
            msg = (ep.get("message") or "")[:150]
            if cat == "Question":
                parts.append(f"- They asked: \"{msg}...\"")
            elif cat == "Challenge":
                parts.append(f"- They challenged you: \"{msg}...\"")
            else:
                parts.append(f"- Past interaction: \"{msg}...\"")

        # Infer relationship temperature
        ep_count = len(context.get("episodic", []))
        if ep_count >= 3:
            parts.append("- (This user has engaged with you multiple times. Familiarity breeds... something.)")

    # Entities - what names echo in his mind
    entities = context.get("entities_mentioned", [])
    if entities:
        # Filter to most emotionally significant
        emotional_entities = []
        for e in entities[:15]:
            if e in EMOTIONAL_ENTITIES:
                emotional_entities.append(e)
        if emotional_entities:
            parts.append(f"\n**NAMES ECHOING:** {', '.join(emotional_entities)}")

    result = "\n".join(parts)

    # Truncate if too long
    if len(result) > max_tokens * 4:
        result = result[:max_tokens * 4] + "\n[...subconscious fades...]"

    return result
