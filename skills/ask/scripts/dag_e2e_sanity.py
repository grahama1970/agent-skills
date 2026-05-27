#!/usr/bin/env python3
"""Live DAG sanity for /ask with memory fanout and create-report join."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ASK_DIR = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a live /ask DAG E2E sanity check.")
    parser.add_argument("--output-root", default="", help="Artifact root; defaults to a temporary directory")
    parser.add_argument("--ask-id", default="ask-dag-e2e-sanity", help="Stable ask run id")
    parser.add_argument("--keep", action="store_true", help="Keep temporary directory path in output")
    parser.add_argument("--include-oracle", action="store_true", help="Also run two live one-shot scillm oracle nodes")
    args = parser.parse_args()

    temp_dir_ctx = None
    if args.output_root:
        output_root = Path(args.output_root).expanduser().resolve()
        output_root.mkdir(parents=True, exist_ok=True)
    else:
        temp_dir_ctx = tempfile.TemporaryDirectory(prefix="ask-dag-e2e-")
        output_root = Path(temp_dir_ctx.name)

    dag_path = output_root / "realistic.scillm-dag.json"
    report_depends_on = ["memory_ask_contract", "memory_report_contract"]
    nodes: list[dict[str, Any]] = [
        {
            "id": "memory_ask_contract",
            "title": "Recall ask DAG and oracle contract",
            "execution": {"call_type": "memory.recall"},
            "query": "project knowledge overview for ask DAG scillm metadata oracle review artifacts",
            "input": {"scope": "ask", "k": 3},
        },
        {
            "id": "memory_report_contract",
            "title": "Recall report contract",
            "execution": {"call_type": "memory.recall"},
            "query": "best practices report source-of-truth inventory findings non-claims plan-iterate seed",
            "input": {"scope": "ask", "k": 3},
        },
    ]
    if args.include_oracle:
        report_depends_on.extend(["brandon_comment", "margaret_comment"])
        nodes.extend([
            {
                "id": "brandon_comment",
                "title": "Brandon one-shot comment",
                "depends_on": ["memory_ask_contract", "memory_report_contract"],
                "execution": {"call_type": "one-shot", "model": "gpt 5.5 high"},
                "prompt_payload": {
                    "prompt": (
                        "Brandon persona: briefly assess whether this ask DAG E2E contract preserves "
                        "evidence, failure visibility, and non-claims. Keep the response under 150 words."
                    )
                },
            },
            {
                "id": "margaret_comment",
                "title": "Margaret one-shot comment",
                "depends_on": ["memory_ask_contract", "memory_report_contract"],
                "execution": {"call_type": "one-shot", "model": "gpt-5.5 high"},
                "prompt_payload": {
                    "prompt": (
                        "Margaret persona: briefly assess whether this ask DAG E2E contract has enough "
                        "source-of-truth inventory and acceptance gates. Keep the response under 150 words."
                    )
                },
            },
        ])
    nodes.append(
        {
            "id": "final_report",
            "title": "Create evidence-first DAG report",
            "depends_on": report_depends_on,
            "execution": {
                "call_type": "skill.run",
                "skill": "create-report",
                "args": [
                    "--title",
                    "Ask DAG E2E Sanity Report",
                    "--input",
                    "${dag_context_json}",
                    "--output",
                    "${dag_node_output}",
                    "--persona",
                    "project agent",
                    "--primary-object",
                    "ask DAG JSON execution",
                ],
            },
        }
    )
    dag = {
        "exec_graph_version": "scillm.exec.graph.v1",
        "graph_id": "ask-dag-e2e-sanity",
        "graph_goal": "Prove /ask can run concurrent memory nodes and a sequential create-report join.",
        "max_concurrency": 2,
        "nodes": nodes,
    }
    dag_path.write_text(json.dumps(dag, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    command = [
        str(ASK_DIR / "run.sh"),
        "ask",
        "Run the ask DAG E2E sanity check.",
        "--dag-file",
        str(dag_path),
        "--ask-id",
        args.ask_id,
        "--run-output-root",
        str(output_root / "runs"),
        "--overwrite",
        "--raw",
        "--json",
    ]
    completed = subprocess.run(command, cwd=ASK_DIR, text=True, capture_output=True, timeout=180)
    run_dir = output_root / "runs" / args.ask_id
    request_path = run_dir / f"{args.ask_id}.request.json"
    status_path = run_dir / f"{args.ask_id}.status.json"
    events_path = run_dir / f"{args.ask_id}.events.jsonl"
    manifest_path = run_dir / "dag" / "manifest.json"
    report_path = run_dir / "dag" / "final_report.out.md"

    checks = {
        "command_returncode_zero": completed.returncode == 0,
        "request_exists": request_path.exists(),
        "status_exists": status_path.exists(),
        "events_exists": events_path.exists(),
        "manifest_exists": manifest_path.exists(),
        "report_exists": report_path.exists(),
    }
    manifest = _read_json(manifest_path)
    status = _read_json(status_path)
    request = _read_json(request_path)
    node_ids = [node.get("id") for node in manifest.get("nodes", []) if isinstance(node, dict)]
    node_ok = {node.get("id"): node.get("ok") for node in manifest.get("nodes", []) if isinstance(node, dict)}
    events = events_path.read_text(encoding="utf-8", errors="replace") if events_path.exists() else ""
    report = report_path.read_text(encoding="utf-8", errors="replace") if report_path.exists() else ""
    expected_node_ids = [node["id"] for node in nodes]
    checks.update({
        "request_normalized_scillm_graph": (request.get("ask_dag") or {}).get("source_graph_version") == "scillm.exec.graph.v1",
        "concurrent_layer_recorded": '"event": "dag_layer_started"' in events and '"concurrent": true' in events,
        "expected_nodes_present": node_ids == expected_node_ids,
        "all_nodes_ok": all(value is True for value in node_ok.values()) if node_ok else False,
        "report_has_summary": "## Report Summary" in report,
        "report_has_source_inventory": "## Source-of-Truth Inventory" in report,
        "report_has_non_claims": "## Non-Claims" in report,
    })
    ok = all(checks.values())
    summary: dict[str, Any] = {
        "ok": ok,
        "checks": checks,
        "command": command,
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-2000:],
        "stderr_tail": completed.stderr[-2000:],
        "artifacts": {
            "output_root": str(output_root),
            "dag_file": str(dag_path),
            "request": str(request_path),
            "status": str(status_path),
            "events": str(events_path),
            "manifest": str(manifest_path),
            "report": str(report_path),
        },
        "status_state": status.get("state", ""),
        "node_ok": node_ok,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    if temp_dir_ctx is not None and not args.keep:
        temp_dir_ctx.cleanup()
    return 0 if ok else 1


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


if __name__ == "__main__":
    sys.exit(main())
