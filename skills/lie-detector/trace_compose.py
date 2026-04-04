"""Post-hoc provenance tracing for lie-detector conversations.

Calls /memory trace for each SPARTA answer turn, then composes
a merged force-graph suitable for /create-figure visualization.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

MEMORY_AGENT = os.getenv("MEMORY_AGENT_BIN", "memory-agent")


def _run_trace(
    q: str, answer: str = "", scope: str = "sparta", mode: str = "fast",
) -> dict[str, Any]:
    """Call memory-agent trace and return parsed JSON."""
    cmd = [
        MEMORY_AGENT, "trace",
        "--q", q,
        "--scope", scope,
        "--mode", mode,
        "--json",
    ]
    if answer:
        cmd.extend(["--answer", answer])
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
    except Exception:
        pass
    return {}


def _merge_graphs(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge per-turn graphs into a session-level graph (union nodes, union links)."""
    seen_nodes: dict[str, dict[str, Any]] = {}
    seen_links: set[tuple[str, str, str]] = set()
    links: list[dict[str, Any]] = []

    for trace in traces:
        graph = trace.get("graph", {})
        for node in graph.get("nodes", []):
            nid = node.get("id", "")
            if nid and nid not in seen_nodes:
                seen_nodes[nid] = node
        for link in graph.get("links", []):
            key = (link.get("source", ""), link.get("target", ""), link.get("type", ""))
            if key not in seen_links:
                seen_links.add(key)
                links.append(link)

    return {
        "nodes": list(seen_nodes.values()),
        "links": links,
    }


def trace_and_visualize(
    conversation_turns: list[dict[str, Any]],
    scope: str = "sparta",
    mode: str = "fast",
    output_dir: str = "",
) -> dict[str, Any]:
    """Post-hoc provenance trace for a conversation.

    Args:
        conversation_turns: List of dicts with 'question' and 'answer' keys
        scope: Memory scope filter
        mode: Trace speed tier (instant|fast|accurate)
        output_dir: Directory for output files (temp if empty)

    Returns:
        Dict with per_turn_traces, merged_graph, and optional figure_path
    """
    per_turn_traces: list[dict[str, Any]] = []

    for turn in conversation_turns:
        question = turn.get("question", turn.get("q", ""))
        answer = turn.get("answer", turn.get("response", ""))
        if not question:
            continue
        trace_result = _run_trace(q=question, answer=answer, scope=scope, mode=mode)
        if trace_result:
            per_turn_traces.append(trace_result)

    merged_graph = _merge_graphs(per_turn_traces)

    # Write merged graph JSON
    out_dir = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="trace_"))
    out_dir.mkdir(parents=True, exist_ok=True)
    graph_path = out_dir / "trace_graph.json"
    graph_path.write_text(json.dumps(merged_graph, indent=2))

    result: dict[str, Any] = {
        "per_turn_traces": per_turn_traces,
        "merged_graph": merged_graph,
        "graph_json_path": str(graph_path),
        "turn_count": len(per_turn_traces),
        "total_nodes": len(merged_graph.get("nodes", [])),
        "total_links": len(merged_graph.get("links", [])),
    }

    # Summary stats
    total_claims = 0
    total_verified = 0
    for t in per_turn_traces:
        v = t.get("verification", {})
        total_claims += v.get("claims_total", 0)
        total_verified += v.get("claims_verified", 0)
    if total_claims > 0:
        result["claims_total"] = total_claims
        result["claims_verified"] = total_verified
        result["verification_rate"] = round(total_verified / total_claims, 3)

    return result
