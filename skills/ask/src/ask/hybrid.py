"""
Hybrid RAG+QRA retrieval for /ask queries.

Provides two-phase retrieval that queries structured QRA pairs (from the
lessons collection) and raw document chunks (from doc_chunks) separately,
then merges them with configurable weighting.  Also contains the learn-back
loop that stores key findings to persona memory for knowledge accumulation.
"""

import re
from typing import Optional

from loguru import logger as log

from .skills_exec import parse_memory_output, run_memory_recall, run_skill
from .persona_routing import extract_bridges


# ---------------------------------------------------------------------------
# QRA reasoning extraction
# ---------------------------------------------------------------------------

def extract_reasoning(solution: str) -> Optional[str]:
    """Extract reasoning from a QRA-formatted solution.

    QRA pairs may contain structured reasoning:
    - "Reasoning: ... Answer: ..."
    - "Q: ... R: ... A: ..."
    """
    if not solution:
        return None

    solution_lower = solution.lower()

    if "reasoning:" in solution_lower:
        parts = solution.split("Reasoning:", 1)
        if len(parts) > 1:
            reasoning_part = parts[1]
            if "Answer:" in reasoning_part:
                reasoning_part = reasoning_part.split("Answer:")[0]
            return reasoning_part.strip()[:500]

    if " r: " in solution_lower or "\nr: " in solution_lower:
        match = re.search(r'\bR:\s*(.+?)(?:\bA:|$)', solution, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()[:500]

    return None


# ---------------------------------------------------------------------------
# Result merging
# ---------------------------------------------------------------------------

def merge_hybrid_results(
    qra_items: list[dict],
    rag_items: list[dict],
    qra_weight: float = 0.7,
) -> list[dict]:
    """Merge QRA and RAG results with QRA preference.

    Args:
        qra_items: Structured QRA pairs from the lessons collection.
        rag_items: Raw chunks from the doc_chunks collection.
        qra_weight: Weight for QRA items (0-1).

    Returns:
        Merged and deduplicated items, sorted by weight.
    """
    merged: list[dict] = []
    seen_problems: set[str] = set()

    # QRA items first (higher weight)
    for item in qra_items:
        problem = item.get("problem", "")
        key = problem[:100].lower().strip()

        if key and key not in seen_problems:
            item["source_type"] = "qra"
            item["weight"] = qra_weight

            reasoning = extract_reasoning(item.get("solution", ""))
            if reasoning:
                item["reasoning"] = reasoning

            merged.append(item)
            seen_problems.add(key)

    # RAG items with complementary weight
    for item in rag_items:
        problem = item.get("problem", "")
        key = problem[:100].lower().strip()

        if key and key not in seen_problems:
            item["source_type"] = "rag"
            item["weight"] = 1.0 - qra_weight
            merged.append(item)
            seen_problems.add(key)

    merged.sort(key=lambda x: -x.get("weight", 0.5))

    log.debug(
        "Merged %d QRA + %d RAG items -> %d unique",
        len(qra_items), len(rag_items), len(merged),
    )
    return merged


# ---------------------------------------------------------------------------
# Hybrid retrieval entry-point
# ---------------------------------------------------------------------------

def ask_hybrid(
    question: str,
    scope: str = "ask",
    k: int = 5,
    use_bridges: bool = False,
    bridge_tags: Optional[list[str]] = None,
    qra_weight: float = 0.7,
) -> dict:
    """Hybrid RAG+QRA retrieval with collection-specific queries.

    Phase 1: Query 'lessons' collection for structured QRA pairs.
    Phase 2: Query 'doc_chunks' collection for raw RAG chunks.
    Phase 3: Merge with QRA priority.

    Args:
        question: The search query.
        scope: Memory scope.
        k: Number of results per collection.
        use_bridges: Also extract and use bridge attributes.
        bridge_tags: Explicit bridge tags to filter by.
        qra_weight: Weight for QRA results (0-1).

    Returns:
        dict with items (merged), qra_count, rag_count, bridges_found.
    """
    result: dict = {
        "question": question,
        "scope": scope,
        "items": [],
        "qra_count": 0,
        "rag_count": 0,
        "bridges_found": [],
    }

    tags = bridge_tags or []
    if use_bridges and not tags:
        bridges = extract_bridges(question)
        result["bridges_found"] = bridges
        tags = [f"bridge:{b}" for b in bridges]
        log.info("Hybrid recall: extracted bridges {} -> tags {}", bridges, tags)

    # Phase 1 — QRA recall (lessons)
    log.info("Hybrid Phase 1: QRA recall (lessons) q={} k={}", question, k)
    qra_result = run_memory_recall(
        question, scope, k=k,
        collections="lessons",
        tags=tags if tags else None,
    )

    qra_items: list[dict] = []
    if qra_result["returncode"] == 0:
        qra_items = parse_memory_output(qra_result["stdout"])
        result["qra_count"] = len(qra_items)
        log.info("QRA recall: {} items", len(qra_items))

    # Phase 2 — RAG recall (doc_chunks)
    rag_k = k // 2 + 1
    log.info("Hybrid Phase 2: RAG recall (doc_chunks) q={} k={}", question, rag_k)
    rag_result = run_memory_recall(
        question, scope, k=rag_k,
        collections="doc_chunks",
    )

    rag_items: list[dict] = []
    if rag_result["returncode"] == 0:
        rag_items = parse_memory_output(rag_result["stdout"])
        result["rag_count"] = len(rag_items)
        log.info("RAG recall: {} items", len(rag_items))

    # Phase 3 — merge
    result["items"] = merge_hybrid_results(qra_items, rag_items, qra_weight)

    log.info(
        "Hybrid recall complete: %d QRA + %d RAG -> %d merged",
        result["qra_count"], result["rag_count"], len(result["items"]),
    )
    return result


# ---------------------------------------------------------------------------
# Learn-back (store findings to persona memory)
# ---------------------------------------------------------------------------

def learn_back(result: dict, persona_id: str, scope: str) -> None:
    """Store key findings back to /memory under the persona's scope.

    This enables knowledge accumulation: each /ask cycle builds on the last.
    Only stores when a persona is asking and meaningful results were found.
    """
    items = result.get("items", [])
    question = result.get("question", "")

    if not items or not persona_id:
        return

    item_summaries: list[str] = []
    for item in items[:5]:
        text = item.get("text", item.get("solution", ""))
        if text:
            item_summaries.append(text[:200])

    if not item_summaries:
        return

    problem = f"[{persona_id}] Asked: {question}"
    solution = (
        f"Found {len(items)} items. Key content:\n"
        + "\n".join(f"- {s}" for s in item_summaries[:3])
    )

    memory_result = run_skill("memory", [
        "learn",
        "--problem", problem,
        "--solution", solution,
        "--scope", scope,
        "--tag", "persona-finding",
        "--tag", f"persona:{persona_id}",
    ], timeout=15)
    if memory_result["returncode"] == 0:
        log.info("Learn-back stored for {}: {}", persona_id, question[:60])
    else:
        log.error("Learn-back failed: {}", memory_result["stderr"][:100])
