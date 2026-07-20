#!/usr/bin/env python3
"""Non-mocked /ask -> Tau DAG sanity runner.

Default profile uses local fixture workers so it does not spend provider calls.
Use --allow-provider-calls and omit --local-fixture only for the live SciLLM path.
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
    parser.add_argument("--allow-provider-calls", action="store_true")
    parser.add_argument("--require-provider-calls", action="store_true")
    parser.add_argument("--local-fixture", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    output_root = args.output_root or Path(tempfile.mkdtemp(prefix="ask-tau-dag-e2e-"))
    cmd = [
        str(ASK_DIR / "run.sh"),
        "tau-dag",
        "ask 2 gpt 5.6 xhigh subagents to solve X concurrently, then claude fable reviews both solutions",
        "--repo",
        "local/tau",
        "--target",
        "e2e-sanity",
        "--criterion",
        "correctness",
        "--criterion",
        "maintainability",
        "--run-output-root",
        str(output_root),
        "--execute",
        "--viewer-link",
        "--json",
    ]
    if args.local_fixture:
        cmd.append("--local-fixture")
    if args.allow_provider_calls:
        cmd.append("--allow-provider-calls")
    if args.require_provider_calls:
        cmd.append("--require-provider-calls")

    completed = subprocess.run(
        cmd,
        cwd=str(ASK_DIR),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    payload = _json_or_error(completed.stdout)
    summary = _summarize(completed, payload, output_root=output_root)
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(f"status: {summary['status']}")
        print(f"mocked: {summary['mocked']}")
        print(f"live: {summary['live']}")
        print(f"provider_live: {summary['provider_live']}")
        print(f"output_root: {summary['output_root']}")
        print(f"dag_path: {summary.get('dag_path')}")
        print(f"receipt_path: {summary.get('receipt_path')}")
    return 0 if summary["ok"] else 1


def _summarize(
    completed: subprocess.CompletedProcess[str],
    payload: dict[str, Any],
    *,
    output_root: Path,
) -> dict[str, Any]:
    bundle = payload.get("bundle") if isinstance(payload.get("bundle"), dict) else {}
    execution = payload.get("execution") if isinstance(payload.get("execution"), dict) else {}
    provider_gate = payload.get("provider_gate") if isinstance(payload.get("provider_gate"), dict) else {}
    receipt = execution.get("receipt") if isinstance(execution.get("receipt"), dict) else {}
    dag_path = Path(str(bundle.get("dag_path"))) if bundle.get("dag_path") else None
    receipt_path = Path(str(execution.get("receipt_path"))) if execution.get("receipt_path") else None
    dag = _read_json(dag_path) if dag_path is not None and dag_path.is_file() else {}
    checks = [
        _check("cli_returncode", completed.returncode == 0, {"returncode": completed.returncode}),
        _check("json_result", bool(payload), {}),
        _check(
            "final_dag_emitted_before_execution",
            bundle.get("final_dag_emitted_before_execution") is True,
            {"value": bundle.get("final_dag_emitted_before_execution")},
        ),
        _check("dag_path_exists", dag_path is not None and dag_path.is_file(), {"path": str(dag_path) if dag_path else None}),
        _check(
            "strict_tau_dag_contract",
            dag.get("schema") == "tau.dag_contract.v1",
            {"schema": dag.get("schema")},
        ),
        _check(
            "gpt_56_xhigh_requested_and_dispatched_via_scillm_route",
            _has_model_policy(
                dag,
                requested_model="gpt-5.6-xhigh",
                model="gpt-5.5",
                reasoning_effort="high",
                requested_reasoning_effort="xhigh",
            ),
            {"policies": _model_policies(dag)},
        ),
        _check(
            "claude_fable_routes_to_scillm_claude_alias",
            _has_model_policy(
                dag,
                requested_model="claude-fable",
                model="claude-fable-5",
                auth="scillm_claude_code_credentials",
            ),
            {"policies": _model_policies(dag)},
        ),
        _check(
            "native_tau_runtime_owner",
            dag.get("context", {}).get("execution_owner") == "$tau"
            and dag.get("context", {}).get("provider_transport") == "$scillm",
            {"context": dag.get("context")},
        ),
        _check("tau_receipt_exists", receipt_path is not None and receipt_path.is_file(), {"path": str(receipt_path) if receipt_path else None}),
        _check("tau_receipt_pass", receipt.get("status") == "PASS", {"status": receipt.get("status"), "verdict": receipt.get("verdict")}),
        _check(
            "parallel_solver_dispatches_observed",
            receipt.get("max_observed_concurrency", 0) >= 2,
            {"max_observed_concurrency": receipt.get("max_observed_concurrency")},
        ),
        _check(
            "viewer_link_available",
            _viewer_available(execution.get("viewer")),
            {"viewer": execution.get("viewer")},
        ),
    ]
    if provider_gate.get("provider_live") is True:
        checks.extend(
            [
                _check(
                    "live_gpt_dispatch_receipt_has_requested_selector",
                    _has_provider_call(
                        provider_gate,
                        requested_model="gpt-5.6-xhigh",
                        model="gpt-5.5",
                        reasoning_effort="high",
                        requested_reasoning_effort="xhigh",
                    ),
                    {"model_calls": provider_gate.get("model_calls")},
                ),
                _check(
                    "live_claude_fable_dispatch_receipt",
                    _has_provider_call(
                        provider_gate,
                        requested_model="claude-fable",
                        model="claude-fable-5",
                    ),
                    {"model_calls": provider_gate.get("model_calls")},
                ),
            ]
        )
    if execution.get("provider_live") is True:
        checks.extend(
            [
                _check(
                    "tau_execution_recorded_live_gpt_node_receipt",
                    _has_execution_node_provider_receipt(
                        execution,
                        requested_model="gpt-5.6-xhigh",
                        model="gpt-5.5",
                        provider_live=True,
                    ),
                    {"node_provider_receipts": execution.get("node_provider_receipts")},
                ),
                _check(
                    "tau_execution_recorded_live_claude_node_receipt",
                    _has_execution_node_provider_receipt(
                        execution,
                        requested_model="claude-fable",
                        model="claude-fable-5",
                        provider_live=True,
                    ),
                    {"node_provider_receipts": execution.get("node_provider_receipts")},
                ),
            ]
        )
    ok = all(item["ok"] for item in checks)
    provider_live = bool(
        provider_gate.get("provider_live") is True
        or execution.get("provider_live") is True
        or receipt.get("provider_live") is True
    )
    return {
        "schema": "ask.tau_dag_e2e_sanity.v1",
        "status": "PASS" if ok else "FAIL",
        "ok": ok,
        "mocked": False,
        "live": True,
        "provider_live": provider_live,
        "what_was_exercised": [
            "/ask run.sh tau-dag CLI",
            "strict tau.dag_contract.v1 artifact emission",
            "real Tau CLI dag-run invocation",
            "real Tau run-status polling",
            "Tau DAG viewer-link command",
            "local command-spec worker subprocesses" if not provider_gate.get("provider_live") else "SciLLM provider route",
        ],
        "what_remains_unverified": _remaining_unverified(provider_live=provider_live),
        "output_root": str(output_root),
        "dag_path": str(dag_path) if dag_path else None,
        "receipt_path": str(receipt_path) if receipt_path else None,
        "checks": checks,
        "provider_gate": provider_gate,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
    }


def _check(name: str, ok: bool, evidence: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "ok": ok, "evidence": evidence}


def _viewer_available(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    parsed = value.get("parsed")
    return isinstance(parsed, dict) and parsed.get("status") == "PASS" and parsed.get("ok") is True


def _read_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _model_policies(dag: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = dag.get("nodes")
    if not isinstance(nodes, list):
        return []
    return [
        node.get("model_policy")
        for node in nodes
        if isinstance(node, dict) and isinstance(node.get("model_policy"), dict)
    ]


def _has_model_policy(dag: dict[str, Any], **expected: Any) -> bool:
    for policy in _model_policies(dag):
        if all(policy.get(key) == value for key, value in expected.items()):
            return True
    return False


def _has_provider_call(provider_gate: dict[str, Any], **expected: Any) -> bool:
    calls = provider_gate.get("model_calls")
    if not isinstance(calls, list):
        return False
    for call in calls:
        if (
            isinstance(call, dict)
            and call.get("ok") is True
            and all(call.get(key) == value for key, value in expected.items())
        ):
            return True
    return False


def _has_execution_node_provider_receipt(execution: dict[str, Any], **expected: Any) -> bool:
    receipts = execution.get("node_provider_receipts")
    if not isinstance(receipts, list):
        return False
    for receipt in receipts:
        if isinstance(receipt, dict) and all(
            receipt.get(key) == value for key, value in expected.items()
        ):
            return True
    return False


def _remaining_unverified(*, provider_live: bool) -> list[str]:
    remaining = [
        "Semantic quality of solver/reviewer responses.",
        "Browser screenshot of the React Flow interface.",
    ]
    if not provider_live:
        remaining.insert(0, "Provider/model calls because provider_live is false.")
    return remaining


def _json_or_error(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return {"parse_error": str(exc), "raw_stdout": text[-4000:]}
    return payload if isinstance(payload, dict) else {"parse_error": "stdout JSON root was not an object"}


if __name__ == "__main__":
    raise SystemExit(main())
