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
import sys
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
    controlled_transport = _run_controlled_transport_blocker_join(output_root)
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
        _check("webclaude_compete_model_policy", _webclaude_model_policy(dag), {"node": _node(dag, "handler-webclaude")}),
        _check("webclaude_command_requests_opus_5_high", _webclaude_command_requests_model(command_root), {"command_spec_root": str(command_root) if command_root else None}),
        _check(
            "controlled_browser_lock_compete_join",
            controlled_transport.get("ok") is True,
            controlled_transport,
        ),
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
            "webclaude compete browser model preference propagation",
            "compete scorecard and winner revision contract",
            "compete join classification for controlled Surf browser-lock transport blockers",
        ],
        "what_remains_unverified": [
            "No browser or API provider was called.",
            "No candidate implementation quality was evaluated.",
            "No winner revision request was submitted to a live handler.",
            "The controlled transport case uses fixture handler receipts; Surf's separate lock-contention sanity proves native lock behavior.",
        ],
        "output_root": str(output_root),
        "dag_path": str(dag_path) if dag_path else None,
        "controlled_transport_blocker": controlled_transport,
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


def _webclaude_model_policy(dag: dict[str, Any]) -> bool:
    node = _node(dag, "handler-webclaude")
    context = node.get("context") if isinstance(node.get("context"), dict) else {}
    policy = context.get("handler_policy") if isinstance(context.get("handler_policy"), dict) else {}
    prompt_contract = context.get("prompt_contract") if isinstance(context.get("prompt_contract"), dict) else {}
    return (
        policy.get("model_preference") == "Opus 5 High"
        and policy.get("model_preference_scope") == "ask_compete_default"
        and prompt_contract.get("model_preference") == "Opus 5 High"
    )


def _webclaude_command_requests_model(root: Path | None) -> bool:
    if root is None:
        return False
    spec = _read_json(root / "handler-webclaude" / "tau-dispatch-command.json")
    command = spec.get("command") if isinstance(spec.get("command"), list) else []
    if "--browser-model-preference" not in command:
        return False
    return command[command.index("--browser-model-preference") + 1] == "Opus 5 High"


def _run_controlled_transport_blocker_join(output_root: Path) -> dict[str, Any]:
    artifacts = output_root / "controlled-browser-lock-contention" / "node-artifacts"
    request_path = artifacts.parent / "request.json"
    request_path.parent.mkdir(parents=True, exist_ok=True)
    request_path.write_text(
        json.dumps({"request": "Controlled Ask compete browser-handler lock contention."}) + "\n",
        encoding="utf-8",
    )
    for node_id, handler in (("handler-webgpt", "webgpt"), ("handler-webclaude", "webclaude")):
        node_dir = artifacts / node_id
        node_dir.mkdir(parents=True, exist_ok=True)
        response_path = node_dir / "response.md"
        response_path.write_text("", encoding="utf-8")
        recovery_packet = {
            "schema": "ask.browser_failure_recovery_packet.v1",
            "status": "NEEDS_ATTENTION",
            "failure_code": "surf_browser_lock_timeout",
            "auto_retry_allowed": False,
            "auto_retry_blocked_reason": "surf_browser_lock_owner_still_running",
            "next_command": [str(ASK_DIR.parent / "surf" / "run.sh"), f"{handler}.submit", "--input", str(node_dir / "prompt.md")],
            "evidence": {
                "surf_lock_blocker": {
                    "schema": "surf.browser_lock_blocker.v1",
                    "blocker": "surf_browser_lock_timeout",
                    "owner": {"pid": 1838917, "socket": "unix:/tmp/surf.sock"},
                }
            },
        }
        (node_dir / "browser-recovery-packet.json").write_text(
            json.dumps(recovery_packet, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (node_dir / "node-receipt.json").write_text(
            json.dumps(
                {
                    "schema": "ask.tau_dag_handler_receipt.v1",
                    "node_id": node_id,
                    "handler": handler,
                    "status": "BLOCKED",
                    "ok": False,
                    "mocked": False,
                    "live": True,
                    "provider_live": False,
                    "response_path": str(response_path),
                    "failure": "SURF_BROWSER_LOCK_BLOCKED {...}",
                    "failure_code": "surf_browser_lock_timeout",
                    "recovery_packet_path": str(node_dir / "browser-recovery-packet.json"),
                    "recovery_packet": recovery_packet,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    join_dir = artifacts / "join"
    completed = subprocess.run(
        [
            sys.executable,
            str(ASK_DIR / "scripts" / "tau_roundtable_worker.py"),
            "--node-id",
            "join",
            "--handler",
            "join",
            "--topology",
            "concurrent",
            "--workflow-mode",
            "compete",
            "--request-file",
            str(request_path),
            "--artifact-dir",
            str(join_dir),
            "--surf-run",
            str(ASK_DIR.parent / "surf" / "run.sh"),
            "--browser-oracle-run",
            str(ASK_DIR.parent / "browser-oracle" / "run.sh"),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    scorecard_path = join_dir / "compete-scorecard.json"
    scorecard = _read_json(scorecard_path)
    transport_blockers = scorecard.get("transport_blockers") if isinstance(scorecard.get("transport_blockers"), list) else []
    ok = (
        completed.returncode == 1
        and scorecard.get("status") == "NEEDS_ATTENTION"
        and scorecard.get("failure_kind") == "transport"
        and "competition_transport_blocked" in (scorecard.get("blockers") or [])
        and len(transport_blockers) == 2
    )
    return {
        "ok": ok,
        "mocked": False,
        "live": False,
        "fixture_backed_handler_receipts": True,
        "returncode": completed.returncode,
        "artifact_dir": str(artifacts.parent),
        "scorecard_path": str(scorecard_path),
        "transport_blocker_count": len(transport_blockers),
        "blockers": scorecard.get("blockers") or [],
        "failure_kind": scorecard.get("failure_kind"),
        "stdout_tail": completed.stdout[-1000:],
        "stderr_tail": completed.stderr[-1000:],
    }


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
