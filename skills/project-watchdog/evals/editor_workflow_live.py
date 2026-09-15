#!/usr/bin/env python3
"""Run an editable three-node graph through the real Watchdog sandbox path."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from watchdog_workflow_cli import execute_sandbox, read_run
from watchdog_graph import canonical_bytes, read_graph, revision


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    graph = deepcopy(read_graph("active")[0])
    if not any(node["id"] == "review_1" for node in graph["nodes"]):
        graph["nodes"].append({
            "id": "review_1", "agent": "reviewer", "access": "read",
            "task": "Inspect the fixer result and report concrete findings. Do not edit files.",
            "depends_on": ["fixer"],
        })
        next(node for node in graph["nodes"] if node["id"] == "reviewer")["depends_on"].append("review_1")
        graph["layout"]["review_1"] = {"x": 290, "y": 360}
    result = execute_sandbox(graph, "agentic-eval")
    receipt = read_run(result["run_id"])
    nodes = receipt.get("pi_result", {}).get("nodes") or {}
    transcripts = receipt.get("transcripts") or {}
    assert receipt["graph_hash"] == revision(canonical_bytes(graph))
    assert receipt["native_preflight"]["ok"] is True
    assert receipt["ok"] is True and receipt["proof"]["ok"] is True
    assert receipt["marker"] == "FIXED\n"
    assert set(nodes) == {"fixer", "review_1", "reviewer"}
    assert all(nodes[node]["ok"] for node in nodes)
    assert all(receipt["pi_result"]["inventory"][node]["state"] == "completed" for node in nodes)
    for node in nodes:
        retained = transcripts[node]
        assert retained["available"] is True
        path = Path(retained["path"])
        assert path.is_file() and path.stat().st_size > 0
        assert hashlib.sha256(path.read_bytes()).hexdigest() == retained["sha256"]
    path = Path(__file__).resolve().parents[1] / "workflows" / "watchdog-v2.json"
    assert read_graph("active")[1] == revision(path.read_bytes())
    summary = {"ok": True, "run_id": result["run_id"], "receipt": result["receipt"], "nodes": sorted(nodes), "marker": receipt["marker"], "proof": receipt["proof"]["ok"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, sort_keys=True) + "\n", encoding="utf-8")
    assert json.loads(args.output.read_text(encoding="utf-8")) == summary
    print(json.dumps(summary, sort_keys=True))
    print("PROJECT_WATCHDOG_EDITOR_LIVE_OK")


if __name__ == "__main__":
    main()
