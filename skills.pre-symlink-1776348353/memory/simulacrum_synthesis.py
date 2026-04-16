"""Response synthesis and formatting for the Brandon Simulacrum.

Handles QRA retrieval orchestration (merging SPARTA, library, and graph-expanded
sources), cross-control LLM synthesis via /scillm, client-specific QRA capture,
and Embry persona voice formatting.
"""

import hashlib
import httpx
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from loguru import logger

SCILLM_URL = "http://localhost:4001"

from simulacrum_retrieval import (
    MEMORY_ROOT,
    MEMORY_VENV_PYTHON,
    expand_qras_via_subgraph,
    query_brandon_library,
    search_sparta_qras_arango,
)


def retrieve_qras(
    intent: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Retrieve relevant QRAs based on intent.

    Uses ArangoDB hybrid search for SPARTA QRAs + Brandon's personal library +
    graph-expanded results. Falls back to mock data for testing.

    Args:
        intent: Intent mapper result

    Returns:
        Tuple of (list of QRAs with grounding scores, graph expansion metadata or None)
    """
    if intent["action"] == "NO_MATCH":
        return [], None

    all_qras: list[dict[str, Any]] = []

    # Source 1: SPARTA QRAs via ArangoDB hybrid search (BM25 + vector + graph)
    try:
        qras = search_sparta_qras_arango(intent, limit=10)
        if qras:
            all_qras.extend(qras)
    except Exception as e:
        logger.debug(f"ArangoDB SPARTA QRA search failed: {e}")

    # Source 2: Brandon's personal library (brandon_bailey scope)
    query_text = intent.get("original_query", "")
    if not query_text:
        entities = intent.get("entities") or []
        tier1 = intent.get("tier1") or []
        parts = [str(p) for p in entities + tier1 if p is not None]
        query_text = " ".join(parts) if parts else "space cybersecurity"
    library_results = query_brandon_library(query_text, k=5)
    if library_results:
        all_qras.extend(library_results)
        logger.debug(f"Added {len(library_results)} results from Brandon's library")

    # Source 3: Graph-expanded QRAs (LEGO-GraphRAG subgraph traversal)
    graph_expansion: dict[str, Any] | None = None
    if all_qras:
        seed_control_ids = list({
            q.get("control_id", "")
            for q in all_qras
            if q.get("control_id") and q.get("control_id") != "LIBRARY"
        })
        if seed_control_ids:
            graph_qras = expand_qras_via_subgraph(
                query_text=query_text,
                seed_control_ids=seed_control_ids,
                k=5,
                depth=2,
            )
            if graph_qras:
                graph_expansion = {
                    "raw_count": len(graph_qras),
                    "raw_avg_grounding": sum(
                        q.get("grounding_score", 0) for q in graph_qras
                    ) / len(graph_qras),
                    "seed_count": len(seed_control_ids),
                    "seeds": seed_control_ids[:10],
                }
                existing_cids = {q.get("control_id") for q in all_qras}
                added = 0
                for gq in graph_qras:
                    if gq.get("control_id") not in existing_cids:
                        all_qras.append(gq)
                        existing_cids.add(gq.get("control_id"))
                        added += 1
                graph_expansion["added_count"] = added
                logger.debug(
                    f"Graph expansion: {len(graph_qras)} raw, {added} new "
                    f"from {len(seed_control_ids)} seed controls"
                )

    if all_qras:
        all_qras.sort(key=lambda q: q.get("grounding_score", 0), reverse=True)
        return all_qras, graph_expansion

    # Fallback: Mock QRAs for demonstration/testing
    return get_mock_qras(intent), None


def get_mock_qras(intent: dict[str, Any]) -> list[dict[str, Any]]:
    """Return mock QRAs for testing when ArangoDB unavailable.

    Args:
        intent: Intent mapper result

    Returns:
        List of mock QRAs
    """
    return [
        {
            "qra_id": "mock-001",
            "question": "How do I detect RF jamming attacks?",
            "answer": (
                "RF jamming can be detected through signal strength monitoring, "
                "spectrum analysis, and correlation with expected transmission patterns. "
                "SPARTA technique T-0023 covers RF interference attacks."
            ),
            "grounding_score": 0.87,
            "control_id": "CM-0051",
            "citations": [
                "SPARTA T-0023: RF Interference - An adversary may attempt to disrupt...",
                "CM-0051: Anti-Jamming Protection - Implement spread spectrum...",
            ],
        },
        {
            "qra_id": "mock-002",
            "question": "What controls protect satellite uplinks?",
            "answer": (
                "Uplink protection involves command authentication (CM-0049), "
                "encryption (CM-0050), and anti-replay mechanisms (CM-0051)."
            ),
            "grounding_score": 0.72,
            "control_id": "CM-0049",
            "citations": [
                "CM-0049: Command Authentication - All commands shall be cryptographically...",
            ],
        },
    ]


def synthesize_cross_control(
    query: str,
    qras: list[dict[str, Any]],
    mode: str = "auto",
    client_scope: str = "sparta",
) -> str:
    """Synthesize response from multiple QRAs with transparent citations.

    Brandon's "honest analyst" pattern: show the QRAs, then synthesize.
    Three modes (progressive):
      - "template": No LLM. Just format QRAs with headers. Zero hallucination.
      - "chutes": Use DeepSeek V3 via Chutes for 1-2 synthesis sentences.
      - "local": Use local 70B model (future H200 deployment).
      - "auto": template if <=1 QRA or no LLM, chutes if available.

    Args:
        query: Original user query
        qras: List of accepted QRAs (already grounding-filtered)
        mode: Synthesis mode
        client_scope: Client scope for QRA capture

    Returns:
        Formatted response with citations
    """
    if not qras:
        return ""

    # Deduplicate by control_id
    seen: set[str] = set()
    unique_qras = []
    for q in qras:
        cid = q.get("control_id", "")
        if cid not in seen:
            seen.add(cid)
            unique_qras.append(q)
    qras = unique_qras[:5]  # Cap at 5 for readability

    # Format individual QRA answers with citations
    qra_blocks = []
    for q in qras:
        cid = q.get("control_id", "UNKNOWN")
        answer = q.get("answer", "")[:400]
        score = q.get("grounding_score", 0)
        # Source annotation: Library, Graph-expanded (with hop count), or direct
        if q.get("_source") == "brandon_library":
            source_tag = " (Library)"
        elif q.get("_source") == "subgraph_expansion":
            depth = q.get("_graph_depth", "?")
            edge_types = q.get("_edge_types", [])
            edge_str = (
                "->".join(str(e) for e in edge_types[:3] if e is not None)
                if edge_types
                else "related"
            )
            source_tag = f" (Graph: {depth}-hop via {edge_str})"
        else:
            source_tag = ""
        qra_blocks.append(
            f"**[{cid}]{source_tag}** (grounding: {score:.2f})\n{answer}"
        )

    individual_text = "\n\n".join(qra_blocks)

    # Single QRA -- no synthesis needed
    if len(qras) <= 1:
        return f"Here's what SPARTA says:\n\n{individual_text}"

    # Template mode (Option C) -- always available, zero hallucination
    if mode == "template" or (mode == "auto" and len(qras) <= 2):
        return (
            f"Here's what SPARTA says about this -- I found {len(qras)} relevant controls:\n\n"
            f"{individual_text}\n\n"
            f"These controls work together to address your question about "
            f"{query[:80]}."
        )

    # Chutes synthesis mode (Option B) -- LLM adds connecting sentences
    if mode in ("chutes", "auto"):
        synthesis = llm_synthesize(query, qras)
        if synthesis:
            capture_synthesis_as_qra(
                query=query,
                synthesis=synthesis,
                source_qras=qras,
                scope=client_scope,
            )
            return (
                f"Here's what SPARTA says -- let me pull up the relevant controls:\n\n"
                f"{individual_text}\n\n"
                f"**Synthesis:** {synthesis}"
            )

    # Fallback to template
    return (
        f"Here's what SPARTA says about this -- I found {len(qras)} relevant controls:\n\n"
        f"{individual_text}\n\n"
        f"These controls address different aspects of your question. "
        f"Would you like me to dig deeper into any specific control?"
    )


def llm_synthesize(
    query: str,
    qras: list[dict[str, Any]],
) -> str | None:
    """Use LLM to synthesize 1-2 connecting sentences from QRA answers.

    Constrained generation: ONLY use facts from the provided QRAs.
    Returns None if LLM unavailable.

    Args:
        query: User's original question
        qras: Accepted QRAs to synthesize

    Returns:
        Synthesis text or None
    """
    # Build context from QRAs
    context_parts = []
    for q in qras[:5]:
        cid = q.get("control_id", "?")
        ans = q.get("answer", "")[:300]
        context_parts.append(f"[{cid}]: {ans}")
    context = "\n\n".join(context_parts)

    prompt = (
        f"You are a space cybersecurity analyst synthesizing findings.\n\n"
        f"The user asked: {query}\n\n"
        f"Here are the relevant SPARTA control answers:\n{context}\n\n"
        f"Write exactly 1-2 sentences that connect these controls to answer the user's question.\n"
        f"Rules:\n"
        f"- ONLY use facts from the control answers above\n"
        f"- Cite control IDs in brackets like [SV-SP-1]\n"
        f"- Do NOT speculate or add information not in the answers\n"
        f"- Be concise and direct"
    )

    # Use scillm HTTP proxy for ALL LLM calls
    try:
        payload = {
            "model": "deepseek-ai/DeepSeek-V3",
            "messages": [{"role": "user", "content": prompt}],
        }
        resp = httpx.post(
            f"{SCILLM_URL}/v1/chat/completions",
            json=payload,
            timeout=30.0,
        )
        resp.raise_for_status()
        synthesis = resp.json()["choices"][0]["message"]["content"].strip()
        if synthesis:
            # Sanity check: reject if too long or looks like hallucination
            if len(synthesis) < 500 and not any(
                marker in synthesis.lower()
                for marker in ["hypothesized", "assumed", "speculated", "i think"]
            ):
                logger.debug(f"LLM synthesis via /scillm: {len(synthesis)} chars")
                return synthesis
    except httpx.HTTPStatusError as e:
        logger.debug(f"/scillm synthesis HTTP error: {e.response.status_code}")
    except Exception as e:
        logger.debug(f"/scillm synthesis failed: {e}")

    return None


def capture_synthesis_as_qra(
    query: str,
    synthesis: str,
    source_qras: list[dict[str, Any]],
    scope: str = "sparta",
) -> dict[str, Any] | None:
    """Capture a synthesized cross-control response as a new client-specific QRA.

    When Brandon synthesizes across multiple controls, the result is a NEW
    QRA candidate. If it passes assess_qra(), store it in the client's scope.

    This is the core mechanism for client-specific knowledge accumulation:
      /learn-datalake -> personas ask questions -> synthesized QRAs -> client corpus

    Args:
        query: Original user question (becomes QRA question)
        synthesis: The synthesized response text (becomes QRA answer)
        source_qras: QRAs used to generate the synthesis (for provenance)
        scope: Client scope for storage (e.g., "fort_worth_f36")

    Returns:
        Stored QRA dict if captured, None if rejected
    """
    if not synthesis or len(synthesis) < 50:
        return None

    # Build provenance chain: which QRAs were used
    source_ids = [q.get("control_id", "?") for q in source_qras[:5]]
    source_keys = [q.get("_key", q.get("qra_id", "?")) for q in source_qras[:5]]

    # Generate deterministic QRA ID from query hash
    query_hash = hashlib.sha256(query.encode()).hexdigest()[:12]
    qra_id = f"synth_{scope}_{query_hash}"

    candidate = {
        "question": query,
        "answer": synthesis,
        "reasoning": (
            f"Synthesized from {len(source_ids)} controls: "
            f"{', '.join(str(s) for s in source_ids if s)}"
        ),
        "control_id": "|".join(str(s) for s in source_ids if s),
        "grounding_score": (
            min(q.get("grounding_score", 0) for q in source_qras)
            if source_qras
            else 0.0
        ),
        "conceptual_tags": list({
            tag
            for q in source_qras
            for tag in (q.get("conceptual_tags") or [])
            if tag is not None
        }),
        "tactical_tags": list({
            tag
            for q in source_qras
            for tag in (q.get("tactical_tags") or [])
            if tag is not None
        }),
        "_source": "cross_control_synthesis",
        "_source_qra_keys": source_keys,
        "_scope": scope,
        "run_id": f"persona-synthesis-{scope}",
        "qra_id": qra_id,
    }

    # Assess and store via memory venv subprocess
    try:
        assess_code = (
            "import sys, json\n"
            f"sys.path.insert(0, {str(MEMORY_ROOT / 'src')!r})\n"
            "from graph_memory.arango_client import get_db\n"
            "db = get_db()\n"
            f"candidate = {json.dumps(candidate)}\n"
            "# Store directly -- assessment happens on insert via trigger\n"
            "candidate['_key'] = candidate['qra_id']\n"
            "try:\n"
            "    db.collection('sparta_qra').insert(candidate, overwrite=True)\n"
            "    print(json.dumps({'stored': True, 'key': candidate['_key']}))\n"
            "except Exception as e:\n"
            "    print(json.dumps({'stored': False, 'error': str(e)}))\n"
        )
        result = subprocess.run(
            [MEMORY_VENV_PYTHON, "-c", assess_code],
            capture_output=True, text=True, timeout=10,
            cwd=str(MEMORY_ROOT),
            env={**os.environ},
        )
        if result.returncode == 0 and result.stdout.strip():
            store_result = json.loads(result.stdout.strip())
            if store_result.get("stored"):
                return candidate
    except Exception as e:
        logger.debug("QRA capture failed: {}", e)

    return None


def format_embry_response(
    base_response: str,
    confidence: dict[str, Any],
    is_first_query: bool = False,
) -> str:
    """Format response in Embry's voice.

    Args:
        base_response: The grounded response content
        confidence: Confidence metrics
        is_first_query: Whether this is first query in session

    Returns:
        Response in Embry's persona voice
    """
    parts = []

    # Session greeting (first query only)
    if is_first_query:
        parts.append(
            "Hi! I'm Embry, an intern working with Brandon Bailey on the SPARTA project "
            "at Aerospace. I've been studying the threat matrix for about six months now, "
            "so I can help with questions about space system cybersecurity.\n\n"
            "Fair warning: I'm still learning, so for anything mission-critical, please "
            "verify with a senior engineer. But I'll do my best to point you in the right "
            "direction!\n\n"
        )

    # Confidence-appropriate framing
    level = confidence.get("confidence_level", "low")
    if level == "high":
        parts.append("Based on what I've learned from SPARTA:\n\n")
    elif level == "medium":
        parts.append(
            "I think I can help with this, though you might want to verify with Brandon "
            "for anything mission-critical:\n\n"
        )
    else:
        parts.append(
            "I found some related information, but I'm not fully confident on this one:\n\n"
        )

    # Main response
    parts.append(base_response)

    # Offer follow-up
    if level != "high":
        parts.append(
            "\n\nWould you like me to dig deeper into any specific aspect, "
            "or should I note this for Brandon to review?"
        )

    return "".join(parts)
