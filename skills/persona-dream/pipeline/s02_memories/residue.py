"""s02_memories — Deep persona memory recall biased by the idea contract.

Takes an idea_contract.json and runs targeted, graph-aware recall to surface
specific memories, contradictions, and emotional threads that will feed the
story step. Different from s01_idea's broad jumble — this step follows graph
edges from specific memory IDs and explores themes surfaced in the dream idea.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Reuse memory client from s01_idea
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "s01_idea"))
from memory_client import (
    recall_persona,
    recall_tom_edges,
    recall_project_context,
    extract_text_chunks,
    compute_impact,
    PERSONA_COLLECTIONS,
)


SCHEMA = "persona_dream.residue_links.v1"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _follow_graph_edges(
    source_ids: list[str],
    *,
    memory_url: str,
) -> list[dict[str, Any]]:
    """Query memory for documents connected to specific source IDs via graph edges."""
    all_chunks: list[dict[str, Any]] = []
    for source_id in source_ids:
        if not source_id:
            continue
        result = recall_persona(
            f"facts and relationships connected to memory {source_id}",
            memory_url=memory_url,
            k=5,
        )
        chunks = extract_text_chunks(result)
        all_chunks.extend(chunks)
    return all_chunks


def _theme_recall(
    idea_text: str,
    persona_ids: list[str],
    *,
    memory_url: str,
) -> list[dict[str, Any]]:
    """Run focused recall on the emotional themes from the dream idea."""
    # Extract key phrases from the idea for targeted recall
    idea_lower = idea_text.lower()
    theme_queries: list[str] = []

    # Detect persona-relevant emotional themes
    emotional_themes = {
        "grief": "grief loss mourning sadness",
        "betrayal": "betrayal trust broken loyalty",
        "fear": "fear dread terror anxiety",
        "hope": "hope optimism future possibility",
        "conflict": "conflict battle struggle tension",
        "memory": "memory past flashback recollection",
        "guilt": "guilt regret remorse shame",
        "family": "family father mother brother sister parent child",
    }
    for theme, query in emotional_themes.items():
        if theme in idea_lower:
            theme_queries.append(f"{query} for {', '.join(persona_ids)}")

    chunks: list[dict[str, Any]] = []
    for query in theme_queries[:4]:  # Cap at 4 theme queries
        result = recall_persona(query, memory_url=memory_url, k=8)
        chunks.extend(extract_text_chunks(result))

    return chunks


def _detect_contradictions(
    chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Find pairs of memory chunks that may contradict each other."""
    contradictions: list[dict[str, Any]] = []
    # Simple heuristic: same persona, opposite emotional tones
    by_persona: dict[str, list[dict[str, Any]]] = {}
    for chunk in chunks:
        pid = chunk.get("persona_id", "") or chunk.get("source_id", "")[:20]
        if pid:
            by_persona.setdefault(pid, []).append(chunk)

    for pid, items in by_persona.items():
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                c1 = items[i]
                c2 = items[j]
                # Check for opposing emotional tones via tom_state_type
                t1 = c1.get("tom_state_type", "")
                t2 = c2.get("tom_state_type", "")
                if t1 and t2 and t1 != t2:
                    contradictions.append({
                        "persona_id": pid,
                        "chunk_a_id": c1.get("source_id", ""),
                        "chunk_b_id": c2.get("source_id", ""),
                        "tom_state_a": t1,
                        "tom_state_b": t2,
                        "text_a": c1.get("retrieval_text") or c1.get("text", "")[:200],
                        "text_b": c2.get("retrieval_text") or c2.get("text", "")[:200],
                    })

    return contradictions


def build_residue_links(
    idea_contract: dict[str, Any],
    *,
    memory_url: str = "http://127.0.0.1:8601",
) -> dict[str, Any]:
    """Build residue_links.json from an idea contract."""
    persona_ids: list[str] = []
    # Extract persona IDs from the contract (may be stored in various places)
    for inp in idea_contract.get("inputs_considered", []):
        if inp.get("kind") == "persona_memory":
            summary = inp.get("summary", "")
            # The idea_contract doesn't store persona_ids explicitly yet
            # We infer from the artifact_id
            break

    artifact_id = idea_contract.get("artifact_id", "")
    # Parse persona_ids from artifact_id (format: "horus_embry_autonomous_123")
    parts = artifact_id.split("_")
    persona_ids = [p for p in parts if p in ("horus", "embry", "horus_lupercal", "embry_lawson")]

    idea_text = idea_contract.get("idea", "")

    # Collect source memory IDs from the selected candidate
    source_ids: list[str] = []
    for cand in idea_contract.get("candidates", []):
        if idea_contract.get("selection", {}).get("selected_candidate_id") == cand.get("candidate_id"):
            source_ids = cand.get("source_memory_ids", [])
            break

    # 1. Follow graph edges from the idea's source memory IDs
    graph_chunks = _follow_graph_edges(source_ids, memory_url=memory_url)

    # 2. Theme-based recall
    theme_chunks = _theme_recall(idea_text, persona_ids, memory_url=memory_url)

    # 3. For each persona, recall tom_edges for emotional depth
    tom_chunks: list[dict[str, Any]] = []
    for pid in persona_ids:
        tom_result = recall_tom_edges(pid, memory_url=memory_url)
        tom_chunks.extend(extract_text_chunks(tom_result))

    all_chunks = graph_chunks + theme_chunks + tom_chunks

    # Compute impact and contradictions
    impacts = {chunk.get("source_id", ""): compute_impact(chunk) for chunk in all_chunks}
    contradictions = _detect_contradictions(all_chunks)

    # Sort chunks by impact
    sorted_chunks = sorted(all_chunks, key=lambda c: impacts.get(c.get("source_id", ""), 0), reverse=True)

    return {
        "schema": SCHEMA,
        "artifact_id": f"residue_links_{artifact_id}",
        "created_at": now_iso(),
        "source_idea_contract": artifact_id,
        "persona_ids": persona_ids,
        "graph_edges_followed": source_ids,
        "total_chunks_recalled": len(all_chunks),
        "graph_chunks": len(graph_chunks),
        "theme_chunks": len(theme_chunks),
        "tom_chunks": len(tom_chunks),
        "contradictions": contradictions,
        "contradiction_count": len(contradictions),
        "residue": [
            {
                "source_id": chunk.get("source_id", ""),
                "collection": chunk.get("collection", ""),
                "persona_id": chunk.get("persona_id", ""),
                "impact_score": round(impacts.get(chunk.get("source_id", ""), 0), 4),
                "text_preview": (chunk.get("retrieval_text") or chunk.get("text", ""))[:300],
                "tom_state_type": chunk.get("tom_state_type", ""),
                "emotion": chunk.get("emotion", ""),
                "emotional_tags": chunk.get("emotional_tags", []),
                "score_graph": chunk.get("score_graph", 0.0),
                "dream_safe": chunk.get("dream_safe", False),
                "intensity_score": chunk.get("intensity_score", 0.0),
            }
            for chunk in sorted_chunks[:20]
        ],
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deep persona memory recall from an idea contract")
    parser.add_argument("--idea-contract", required=True, help="Path to idea_contract.json")
    parser.add_argument("--output-dir", default="/tmp/persona-dream-memories", help="Output directory")
    parser.add_argument("--memory-url", default="http://127.0.0.1:8601", help="Memory service URL")
    args = parser.parse_args(argv)

    contract_path = Path(args.idea_contract)
    if not contract_path.exists():
        print(json.dumps({"status": "FAIL", "error": f"Contract not found: {contract_path}"}), file=sys.stderr)
        return 1

    try:
        idea_contract = json.loads(contract_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}), file=sys.stderr)
        return 1

    try:
        result = build_residue_links(idea_contract, memory_url=args.memory_url)
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}), file=sys.stderr)
        return 1

    output_dir = Path(args.output_dir)
    out_path = output_dir / "residue_links.json"
    write_json(out_path, result)
    print(json.dumps({
        "status": "PASS",
        "path": str(out_path),
        "chunks": result["total_chunks_recalled"],
        "graph_edges_followed": len(result["graph_edges_followed"]),
        "contradictions": result["contradiction_count"],
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
