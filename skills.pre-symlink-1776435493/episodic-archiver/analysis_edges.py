"""Cross-session edge verification and memory-first checks for episodic archiver."""

import json
import os
import time
from typing import Any, Dict, List

from analysis_llm import _get_llm_config, _llm_batch, get_embedding
from loguru import logger

# Optimal K for failure retrieval (research shows K~4 is optimal)
OPTIMAL_FAILURE_K = 4


async def verify_cross_session_edges(
    session_summary: dict, db, max_candidates: int = 10
) -> list:
    """Find and verify edges between this session and prior sessions."""
    cfg = _get_llm_config()
    if not cfg["api_key"]:
        return []

    # Build search text from assessment
    assessment = session_summary.get("assessment", {})
    search_text = " ".join(
        assessment.get("problems_addressed", [])
        + assessment.get("solutions_found", [])
        + assessment.get("key_learnings", [])
    )
    if not search_text.strip():
        return []

    # Find similar prior sessions via BM25
    session_key = session_summary.get("_key", "")
    try:
        candidates = list(db.aql.execute("""
            FOR doc IN session_summaries_search
              SEARCH ANALYZER(
                doc.assessment.problems_addressed IN TOKENS(@q, 'text_en')
                OR doc.assessment.solutions_found IN TOKENS(@q, 'text_en')
                OR doc.assessment.key_learnings IN TOKENS(@q, 'text_en'),
                'text_en'
              )
              FILTER doc._key != @self_key
              SORT BM25(doc) DESC
              LIMIT @limit
              RETURN KEEP(doc, '_key', 'session_id', 'assessment', 'source_name', 'created_at')
        """, bind_vars={"q": search_text[:2000], "self_key": session_key, "limit": max_candidates}))
    except Exception:
        return []

    if not candidates:
        return []

    # Build batch requests for stance verification
    new_summary = {
        "session_id": session_summary.get("session_id"),
        "problems": assessment.get("problems_addressed", [])[:5],
        "solutions": assessment.get("solutions_found", [])[:5],
        "learnings": assessment.get("key_learnings", [])[:3],
    }

    reqs = []
    for i, cand in enumerate(candidates):
        prior_assessment = cand.get("assessment", {})
        prior_summary = {
            "session_id": cand.get("session_id"),
            "problems": prior_assessment.get("problems_addressed", [])[:5],
            "solutions": prior_assessment.get("solutions_found", [])[:5],
            "learnings": prior_assessment.get("key_learnings", [])[:3],
        }
        reqs.append({
            "model": cfg["model"],
            "messages": [{"role": "user", "content": f"""Compare two agent sessions. Determine the relationship.

Session A (new): {json.dumps(new_summary)}
Session B (prior): {json.dumps(prior_summary)}

Return JSON:
{{
  "stance": "resolves" | "contradicts" | "bolsters" | "augments" | "irrelevant",
  "weight": 0.0,
  "rationale": "brief explanation"
}}

Rules:
- resolves: Session A fixed a problem that Session B left unresolved
- contradicts: Session A's findings conflict with Session B's
- bolsters: Session A confirms/strengthens Session B's findings
- augments: Session A adds new related knowledge to Session B's
- irrelevant: No meaningful relationship
- weight: 0.0-1.0 confidence"""}],
            "max_tokens": 256,
            "temperature": 0.2,
            "index": i,
        })

    results = await _llm_batch(reqs, concurrency=4)

    # Create edges for non-irrelevant stances
    edges_created = []
    for res in results:
        if not res.get("ok"):
            continue
        try:
            parsed = json.loads(res["content"]) if isinstance(res["content"], str) else res["content"]
        except (json.JSONDecodeError, TypeError):
            continue

        stance = parsed.get("stance", "irrelevant")
        if stance == "irrelevant":
            continue
        weight = min(1.0, max(0.0, float(parsed.get("weight", 0.5))))
        if weight < 0.3:
            continue

        idx = res.get("index", 0)
        if idx >= len(candidates):
            continue
        cand = candidates[idx]

        edge_type = f"session_{stance}"
        edge_doc = {
            "_from": f"session_summaries/{session_key}",
            "_to": f"session_summaries/{cand['_key']}",
            "type": edge_type,
            "stance": stance,
            "weight_llm": weight,
            "llm_rationale": parsed.get("rationale", ""),
            "source": "session-analysis",
            "created_at": int(time.time()),
            "updated_at": int(time.time()),
        }

        try:
            db.collection("lesson_edges").insert(edge_doc)
            edges_created.append({"to": cand.get("session_id"), "type": edge_type, "weight": weight})
        except Exception as e:
            logger.debug("value lookup failed: {}", e)

    return edges_created


async def check_already_solved(problems: list, db) -> list:
    """Check memory for prior solutions to this session's problems."""
    prior_solutions = []
    for problem in problems[:5]:  # Cap at 5 problems
        if not problem or len(problem) < 10:
            continue
        try:
            results = list(db.aql.execute("""
                FOR d IN lessons_search
                  SEARCH ANALYZER(d.problem IN TOKENS(@q, 'text_en'), 'text_en')
                  SORT BM25(d) DESC
                  LIMIT 2
                  RETURN KEEP(d, '_key', 'title', 'problem', 'solution', 'scope')
            """, bind_vars={"q": problem[:500]}))
            for r in results:
                prior_solutions.append({
                    "problem_query": problem[:200],
                    "lesson_key": r.get("_key"),
                    "lesson_title": r.get("title", ""),
                    "lesson_solution": (r.get("solution") or "")[:300],
                })
        except Exception as e:
            logger.debug("value lookup failed: {}", e)
    return prior_solutions


async def search_similar_failures(
    problem: str, db, k: int = OPTIMAL_FAILURE_K, min_similarity: float = 0.4
) -> list:
    """Retrieve K~4 similar past failures using embedding similarity.

    Research shows K~4 is optimal for failure episode retrieval:
    - Too few (K<3): Miss relevant context
    - Too many (K>6): Noise degrades performance
    - K~4: Sweet spot for actionable similar-failure patterns
    """
    if not problem or len(problem) < 10:
        return []

    try:
        embedding = get_embedding(problem[:1000])
    except Exception:
        return []

    if not embedding:
        return []

    try:
        results = list(db.aql.execute("""
            FOR doc IN unresolved_sessions
                LET sim = (
                    LENGTH(doc.embedding) > 0 AND LENGTH(@emb) > 0
                    ? (
                        SUM(
                            FOR i IN 0..MIN(LENGTH(doc.embedding), LENGTH(@emb))-1
                            RETURN doc.embedding[i] * @emb[i]
                        ) / (
                            SQRT(SUM(FOR v IN doc.embedding RETURN v*v)) *
                            SQRT(SUM(FOR v IN @emb RETURN v*v))
                        )
                    )
                    : 0
                )
                FILTER sim >= @min_sim
                SORT sim DESC
                LIMIT @k
                RETURN {
                    session_id: doc.session_id,
                    resolution: doc.resolution,
                    summary: doc.summary,
                    status: doc.status,
                    fix_description: doc.fix_description,
                    lessons_used: doc.lessons_used,
                    similarity: sim,
                    archived_at: doc.archived_at
                }
        """, bind_vars={"emb": embedding, "k": k, "min_sim": min_similarity}))

        return results
    except Exception:
        # Fallback: BM25 search if embedding search fails
        try:
            results = list(db.aql.execute("""
                FOR doc IN unresolved_sessions
                    LET score = BM25(doc)
                    FILTER CONTAINS(LOWER(doc.summary), LOWER(@q))
                    SORT score DESC
                    LIMIT @k
                    RETURN {
                        session_id: doc.session_id,
                        resolution: doc.resolution,
                        summary: doc.summary,
                        status: doc.status,
                        fix_description: doc.fix_description,
                        lessons_used: doc.lessons_used,
                        similarity: 0.5,
                        archived_at: doc.archived_at
                    }
            """, bind_vars={"q": problem[:200], "k": k}))
            return results
        except Exception:
            return []


async def get_failure_context(problems: list, db) -> dict:
    """Get comprehensive failure context using K~4 retrieval."""
    context = {
        "similar_failures": [],
        "prior_solutions": [],
        "success_patterns": [],
        "failure_patterns": [],
    }

    for problem in problems[:3]:
        if not problem or len(problem) < 10:
            continue

        similar = await search_similar_failures(problem, db, k=OPTIMAL_FAILURE_K)
        context["similar_failures"].extend(similar)

        resolved = [s for s in similar if s.get("status") == "resolved"]
        unresolved = [s for s in similar if s.get("status") != "resolved"]

        if resolved:
            context["success_patterns"].append({
                "problem": problem[:200],
                "resolved_count": len(resolved),
                "fixes_used": [
                    s.get("fix_description") for s in resolved
                    if s.get("fix_description")
                ][:3],
            })

        if unresolved:
            context["failure_patterns"].append({
                "problem": problem[:200],
                "unresolved_count": len(unresolved),
                "common_issues": [
                    s.get("resolution", {}).get("reason") for s in unresolved
                ][:3],
            })

    context["prior_solutions"] = await check_already_solved(problems, db)

    return context
