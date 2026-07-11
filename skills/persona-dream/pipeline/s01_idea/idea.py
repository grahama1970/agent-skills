#!/usr/bin/env python3
"""s01_idea — Generate a persona dream idea contract.

Modes:
  seed      : record a human/project-agent supplied idea
  autonomous: synthesize an idea from persona memory + project context
              using multi-hop graph traversal over theory-of-mind edges
              (characters, events, places, emotions, beliefs).

Outputs idea_contract.json conforming to persona_dream.idea_contract.v1.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import memory_client, candidate_generator, selector, brave_search


SCHEMA = "persona_dream.idea_contract.v1"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _artifact_id(persona_ids: list[str], source_mode: str) -> str:
    slug = "_".join(p.replace(" ", "_").lower() for p in persona_ids) or "unknown"
    return f"{slug}_{source_mode}_{int(time.time())}"


def build_contract_from_seed(
    *,
    seed: str,
    persona_ids: list[str],
    about: str | None,
    source_mode: str,
    memory_url: str,
) -> dict[str, Any]:
    """Build an idea contract when a seed idea is supplied."""
    return {
        "schema": SCHEMA,
        "artifact_id": _artifact_id(persona_ids, source_mode),
        "status": "ACCEPTED_AUTOMATED",
        "created_at": now_iso(),
        "source_mode": source_mode,
        "idea": seed,
        "default_source_mode": "autonomous_memory_project_synthesis",
        "inputs_considered": [
            {
                "kind": source_mode,
                "status": "ACCEPTED_AUTOMATED",
                "summary": seed,
            },
            {
                "kind": "persona_memory",
                "status": "DEFERRED_BY_EXPLICIT_SEED",
                "required_in_autonomous_mode": True,
                "summary": "Autonomous runs must recall persona memories before selecting the dream idea.",
            },
            {
                "kind": "project_knowledge_memory",
                "status": "DEFERRED_BY_EXPLICIT_SEED",
                "required_in_autonomous_mode": True,
                "summary": "Autonomous runs must mix project knowledge or recent project activity from memory into the idea pool.",
            },
            {
                "kind": "brave_search_context",
                "status": "OPTIONAL_NOT_USED_FOR_IDEA_SELECTION",
                "required_in_autonomous_mode": False,
                "summary": "Brave Search may add relevant current events or canon/context checks when the idea needs fresh grounding.",
            },
        ],
        "codebase_question_protocol": {
            "required_in_autonomous_mode": True,
            "transport": f"httpx POST {memory_url}/recall",
            "boundary": "/recall returns stored memory only; it does not inspect live git or the filesystem.",
            "default_scope": "memory",
        },
        "selection_policy": [
            "If a human or project agent supplies a specific idea, record it as the chosen idea and preserve it exactly.",
            "Otherwise recall persona memory and project knowledge first, combine several residues into candidate ideas, and select one candidate with source links.",
            "Use Brave Search only when fresh external context or canon-sensitive grounding is needed, and write a search receipt.",
            "Do not proceed to story generation when no source-linked idea can be formed.",
        ],
    }


def build_contract_autonomous(
    *,
    persona_ids: list[str],
    about: str | None,
    memory_url: str,
    selector_mode: str,
    n_candidates: int,
    rng_seed: int | None,
) -> dict[str, Any]:
    """Build an idea contract by sampling memory with graph-traversal and ToM impact."""
    all_chunks: list[dict[str, Any]] = []
    tom_found = False
    graph_connections = 0

    for persona_id in persona_ids:
        # Primary recall with graph traversal (characters, events, places)
        persona_result = memory_client.recall_persona(persona_id, memory_url=memory_url)
        persona_chunks = memory_client.extract_text_chunks(persona_result)
        all_chunks.extend(persona_chunks)

        # Theory-of-mind edges: beliefs, emotions, intentions, desires
        tom_result = memory_client.recall_tom_edges(persona_id, memory_url=memory_url)
        tom_chunks = memory_client.extract_text_chunks(tom_result)
        all_chunks.extend(tom_chunks)
        if tom_chunks:
            tom_found = True

        # Count graph-traversal hits
        graph_connections += sum(1 for c in persona_chunks + tom_chunks if c.get("score_graph", 0.0) > 0.0)

    # Project context
    project_result = memory_client.recall_project_context(about, memory_url=memory_url)
    project_chunks = memory_client.extract_text_chunks(project_result)
    all_chunks.extend(project_chunks)

    # Brave Search for external events / canon context (optional)
    search_receipts: list[dict[str, Any]] = []
    browser_context_texts: list[str] = []
    search_queries = brave_search.build_context_queries(persona_ids, about)
    for query in search_queries:
        receipt = brave_search.search(query)
        search_receipts.append(receipt)
        if receipt["status"] == "ok":
            for r in receipt.get("results", []):
                browser_context_texts.append(r["title"] + ": " + r["description"])

    # Append Brave Search results as memory-style chunks for candidate generation
    if browser_context_texts:
        for i, text in enumerate(browser_context_texts):
            all_chunks.append({
                "text": text,
                "source_id": f"brave_search_{i}",
                "collection": "brave_search",
                "score_bm25": 0.3,
                "score_dense": 0.0,
                "score_graph": 0.0,
                "emotion": "",
                "tom_state_type": "",
                "retrieval_text": text,
            })

    if not all_chunks:
        raise RuntimeError(
            "No memory chunks recalled. The memory service may be empty or unreachable. "
            "Supply a --seed to use seed mode, or ingest memories first."
        )

    candidates = candidate_generator.generate_candidates(
        all_chunks,
        persona_ids=persona_ids,
        about=about,
        n_candidates=n_candidates,
        rng_seed=rng_seed,
    )

    if not candidates:
        raise RuntimeError(
            "No candidates generated from memory chunks. "
            "The available chunks may be too sparse to form coherent ideas. "
            "Supply a --seed or add more persona memory."
        )

    selection = selector.select_best_candidate(
        candidates,
        persona_ids=persona_ids,
        about=about,
        selector=selector_mode,
    )

    # Find the selected candidate (handle case where scillm returned an ID)
    selected = next(
        (c for c in candidates if c["candidate_id"] == selection["selected_candidate_id"]),
        candidates[0],
    )

    inputs_considered = [
        {
            "kind": "persona_memory",
            "status": "USED",
            "required_in_autonomous_mode": True,
            "summary": f"Recalled {len([c for c in all_chunks if c.get('collection') == 'persona_memory'])} persona-memory chunks with graph traversal.",
        },
        {
            "kind": "persona_tom_edges",
            "status": "USED" if tom_found else "NOT_FOUND",
            "required_in_autonomous_mode": False,
            "summary": f"Theory-of-mind edges (beliefs, emotions, intentions): {'found' if tom_found else 'none found'}.",
        },
        {
            "kind": "graph_traversal",
            "status": "USED",
            "required_in_autonomous_mode": False,
            "summary": f"Multi-hop graph traversal discovered {graph_connections} connected nodes across characters, events, and places.",
        },
        {
            "kind": "project_knowledge_memory",
            "status": "USED",
            "required_in_autonomous_mode": True,
            "summary": f"Recalled {len(project_chunks)} project chunks.",
        },
        {
            "kind": "brave_search_context",
            "status": "USED" if browser_context_texts else "SKIPPED",
            "required_in_autonomous_mode": False,
            "summary": (
                f"Brave Search returned {len(browser_context_texts)} contextual results "
                f"across {len(search_queries)} queries."
                if browser_context_texts
                else "Brave Search skipped or returned no results."
            ),
        },
    ]

    return {
        "schema": SCHEMA,
        "artifact_id": _artifact_id(persona_ids, "autonomous"),
        "status": "ACCEPTED_AUTOMATED",
        "created_at": now_iso(),
        "source_mode": "autonomous_memory_project_synthesis",
        "idea": selected["idea"],
        "default_source_mode": "autonomous_memory_project_synthesis",
        "inputs_considered": inputs_considered,
        "candidates": candidates,
        "selection": selection,
        "graph_traversal": {
            "tom_edges_found": tom_found,
            "graph_connections": graph_connections,
            "edge_collections_queried": memory_client.PERSONA_COLLECTIONS,
        },
        "brave_search": {
            "queries": search_queries,
            "receipts": search_receipts,
            "results_count": len(browser_context_texts),
        },
        "codebase_question_protocol": {
            "required_in_autonomous_mode": True,
            "transport": f"httpx POST {memory_url}/recall",
            "boundary": "/recall returns stored memory only; it does not inspect live git or the filesystem.",
            "default_scope": "memory",
        },
        "selection_policy": [
            "Sample candidate ideas from persona memory and project knowledge, weighted by impact rather than recency.",
            "Use theory-of-mind edges (emotion, stance, tom_state_type) to weight dream-worthiness of memories.",
            "Use multi-hop graph traversal to discover connected characters, events, and places that enrich the dream.",
        "Use a subagent selector to choose the candidate with the best theory-of-mind fit and dream potential.",
        "Record all candidates and the selection reason for audit.",
        "Use Brave Search to add fresh external context (news, canon, world events) when the dream needs current-event grounding.",
        "Do not proceed to story generation when no source-linked idea can be formed.",
        ],
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a persona dream idea contract")
    parser.add_argument("--persona", required=True, help="Comma-separated persona IDs (e.g., horus,embry)")
    parser.add_argument("--about", default=None, help="Optional topic to bias memory recall")
    parser.add_argument("--seed", default=None, help="Human/project-agent supplied idea (forces seed mode)")
    parser.add_argument("--output-dir", default="/tmp/persona-dream-idea", help="Output directory")
    parser.add_argument("--memory-url", default="http://127.0.0.1:8601", help="Memory service URL or UDS path")
    parser.add_argument("--selector", default="scillm", choices=["scillm", "impact"], help="Candidate selector")
    parser.add_argument("--n-candidates", type=int, default=3, help="Number of candidates to sample")
    parser.add_argument("--rng-seed", type=int, default=None, help="Random seed for reproducible sampling")
    parser.add_argument("--source-mode", default="autonomous_memory_project_synthesis", choices=[
        "autonomous_memory_project_synthesis",
        "human_supplied_seed",
        "project_agent_supplied_seed",
    ], help="How the idea was sourced")
    args = parser.parse_args(argv)

    persona_ids = [p.strip() for p in args.persona.split(",") if p.strip()]
    output_dir = Path(args.output_dir)

    source_mode = (
        args.source_mode
        if args.source_mode != "autonomous_memory_project_synthesis"
        else "human_supplied_seed"
    ) if args.seed else args.source_mode

    try:
        if args.seed:
            contract = build_contract_from_seed(
                seed=args.seed,
                persona_ids=persona_ids,
                about=args.about,
                source_mode=source_mode,
                memory_url=args.memory_url,
            )
        else:
            contract = build_contract_autonomous(
                persona_ids=persona_ids,
                about=args.about,
                memory_url=args.memory_url,
                selector_mode=args.selector,
                n_candidates=args.n_candidates,
                rng_seed=args.rng_seed,
            )
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}), file=sys.stderr)
        return 1

    out_path = output_dir / "idea_contract.json"
    write_json(out_path, contract)
    print(json.dumps({"status": "PASS", "path": str(out_path), "idea": contract["idea"][:200]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
