#!/usr/bin/env python3
"""Deterministic sanity eval for /ask compete DAG compilation.

This eval does not call browser or API providers. It proves the user-facing
`./run.sh compete` command emits an isolated candidate DAG, command specs, and
fail-closed compete join contract.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any


ASK_DIR = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    output_root = args.output_root or Path(tempfile.mkdtemp(prefix="ask-tau-compete-sanity-"))

    cmd = [
        str(ASK_DIR / "run.sh"),
        "compete",
        "Implement a focused Ask compete patch independently. Emit VERIFIED_FEATURE lines only for locally checkable features.",
        "--repo",
        "local/agent-skills",
        "--target",
        "ask-compete-sanity",
        "--handler",
        "webgpt",
        "--handler",
        "webclaude",
        "--handler",
        "gpt-5.5-high",
        "--handler-project",
        "webgpt=tau",
        "--criterion",
        "skill-contract",
        "--criterion",
        "deterministic-proof",
        "--run-output-root",
        str(output_root),
        "--json",
    ]
    completed = subprocess.run(
        cmd,
        cwd=str(ASK_DIR),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    payload = _json_or_empty(completed.stdout)
    summary = _summarize(completed, payload, output_root)
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(f"status: {summary['status']}")
        print(f"mocked: {summary['mocked']}")
        print(f"live: {summary['live']}")
        print(f"provider_live: {summary['provider_live']}")
        print(f"output_root: {summary['output_root']}")
        print(f"dag_path: {summary.get('dag_path')}")
    return 0 if summary["ok"] else 1


def _summarize(
    completed: subprocess.CompletedProcess[str],
    payload: dict[str, Any],
    output_root: Path,
) -> dict[str, Any]:
    bundle = payload.get("bundle") if isinstance(payload.get("bundle"), dict) else {}
    dag_path = Path(str(bundle.get("dag_path"))) if bundle.get("dag_path") else None
    command_root = Path(str(bundle.get("command_spec_root"))) if bundle.get("command_spec_root") else None
    dag = _read_json(dag_path)
    join = _node(dag, "join")
    checks = [
        _check("cli_returncode", completed.returncode == 0, {"returncode": completed.returncode}),
        _check("json_payload", bool(payload), {}),
        _check("bundle_ready", bundle.get("status") == "READY", {"status": bundle.get("status")}),
        _check("dag_exists", dag_path is not None and dag_path.is_file(), {"dag_path": str(dag_path) if dag_path else None}),
        _check("strict_tau_schema", dag.get("schema") == "tau.dag_contract.v1", {"schema": dag.get("schema")}),
        _check("workflow_mode_compete", dag.get("context", {}).get("workflow_mode") == "compete", {"context": dag.get("context")}),
        _check("concurrent_candidate_edges", _has_compete_edges(dag), {"edges": dag.get("edges")}),
        _check("mixed_handlers_present", set(dag.get("context", {}).get("handlers") or []) == {"webgpt", "webclaude", "gpt-5.5-high"}, {"handlers": dag.get("context", {}).get("handlers")}),
        _check("join_requires_scorecard", "compete_scorecard" in (join.get("required_evidence") or []), {"join": join}),
        _check("join_requires_revision_request", "winner_revision_request" in (join.get("required_evidence") or []), {"join": join}),
        _check("command_specs_exist", _command_specs_exist(command_root), {"command_spec_root": str(command_root) if command_root else None}),
        _check("command_specs_mark_compete", _command_specs_mark_compete(command_root), {"command_spec_root": str(command_root) if command_root else None}),
    ]
    ok = all(item["ok"] for item in checks)
    return {
        "schema": "ask.tau_compete_sanity_eval.v1",
        "status": "PASS" if ok else "FAIL",
        "ok": ok,
        "mocked": False,
        "live": False,
        "provider_live": False,
        "what_was_exercised": [
            "/ask run.sh compete CLI",
            "strict tau.dag_contract.v1 artifact emission",
            "mixed browser/API handler command spec generation",
            "compete scorecard and winner revision contract",
        ],
        "what_remains_unverified": [
            "No browser or API provider was called.",
            "No candidate implementation quality was evaluated.",
            "No winner revision request was submitted to a live handler.",
        ],
        "output_root": str(output_root),
        "dag_path": str(dag_path) if dag_path else None,
        "checks": checks,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
    }


def _check(name: str, ok: bool, evidence: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "ok": ok, "evidence": evidence}


def _node(dag: dict[str, Any], node_id: str) -> dict[str, Any]:
    for node in dag.get("nodes") or []:
        if isinstance(node, dict) and node.get("id") == node_id:
            return node
    return {}


def _has_compete_edges(dag: dict[str, Any]) -> bool:
    edges = dag.get("edges")
    if not isinstance(edges, list):
        return False
    expected = {
        ("handler-webgpt", "join"),
        ("handler-webclaude", "join"),
        ("handler-gpt-5-5-high", "join"),
        ("join", "human"),
    }
    actual = {
        (str(edge.get("from")), str(edge.get("to")))
        for edge in edges
        if isinstance(edge, dict)
    }
    return expected <= actual


def _command_specs_exist(root: Path | None) -> bool:
    if root is None:
        return False
    for node_id in ("handler-webgpt", "handler-webclaude", "handler-gpt-5-5-high", "join"):
        if not (root / node_id / "tau-dispatch-command.json").is_file():
            return False
    return True


def _command_specs_mark_compete(root: Path | None) -> bool:
    if root is None:
        return False
    for node_id in ("handler-webgpt", "handler-webclaude", "handler-gpt-5-5-high", "join"):
        spec = _read_json(root / node_id / "tau-dispatch-command.json")
        command = spec.get("command") if isinstance(spec.get("command"), list) else []
        if "--workflow-mode" not in command:
            return False
        if command[command.index("--workflow-mode") + 1] != "compete":
            return False
    return True


def _read_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _json_or_empty(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


if __name__ == "__main__":
    raise SystemExit(main())
