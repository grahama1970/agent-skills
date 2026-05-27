#!/usr/bin/env python3
"""Live DAG sanity proving required-node failure stops dependents."""

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
    parser = argparse.ArgumentParser(
        description="Run a live /ask DAG check that fails closed on a required node.",
    )
    parser.add_argument("--output-root", default="", help="Artifact root; defaults to a temp directory")
    parser.add_argument("--ask-id", default="ask-dag-negative-sanity", help="Stable ask run id")
    parser.add_argument("--keep", action="store_true", help="Keep temporary directory path in output")
    args = parser.parse_args()

    temp_dir_ctx = None
    if args.output_root:
        output_root = Path(args.output_root).expanduser().resolve()
        output_root.mkdir(parents=True, exist_ok=True)
    else:
        temp_dir_ctx = tempfile.TemporaryDirectory(prefix="ask-dag-negative-")
        output_root = Path(temp_dir_ctx.name)

    dag = {
        "schema_version": "ask.dag.v1",
        "graph_id": "ask-dag-negative-sanity",
        "description": "Prove required-node failure stops dependents and records dag_layer_failed.",
        "nodes": [
            {
                "id": "broken_step",
                "type": "skill.run",
                "input": {
                    "skill": "create-report",
                    "args": ["--definitely-not-a-real-flag"],
                },
            },
            {
                "id": "final_report",
                "type": "skill.run",
                "depends_on": ["broken_step"],
                "input": {
                    "skill": "create-report",
                    "args": ["--help"],
                },
            },
        ],
    }
    dag_path = output_root / "negative.ask-dag.json"
    dag_path.write_text(json.dumps(dag, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    command = [
        str(ASK_DIR / "run.sh"),
        "ask",
        "Run the ask DAG negative fail-closed sanity check.",
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
    completed = subprocess.run(command, cwd=ASK_DIR, text=True, capture_output=True, timeout=120)
    run_dir = output_root / "runs" / args.ask_id
    request_path = run_dir / f"{args.ask_id}.request.json"
    status_path = run_dir / f"{args.ask_id}.status.json"
    events_path = run_dir / f"{args.ask_id}.events.jsonl"
    broken_artifact = run_dir / "dag" / "broken_step.json"
    dependent_artifact = run_dir / "dag" / "final_report.json"

    checks = {
        "command_returncode_nonzero": completed.returncode != 0,
        "request_exists": request_path.exists(),
        "status_exists": status_path.exists(),
        "events_exists": events_path.exists(),
        "broken_node_artifact_exists": broken_artifact.exists(),
        "dependent_node_artifact_absent": not dependent_artifact.exists(),
    }
    status = _read_json(status_path)
    events = events_path.read_text(encoding="utf-8", errors="replace") if events_path.exists() else ""
    broken = _read_json(broken_artifact)
    checks.update({
        "status_failed": status.get("state") == "failed",
        "dag_layer_failed_recorded": '"event": "dag_layer_failed"' in events,
        "failed_node_ids_include_broken_step": '"failed_node_ids": ["broken_step"]' in events,
        "broken_node_not_ok": broken.get("ok") is False,
        "stderr_mentions_ask_dag_error": "AskDagError" in (completed.stdout + completed.stderr),
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
            "broken_node": str(broken_artifact),
            "dependent_node": str(dependent_artifact),
        },
        "status_state": status.get("state", ""),
        "broken_node_ok": broken.get("ok"),
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
