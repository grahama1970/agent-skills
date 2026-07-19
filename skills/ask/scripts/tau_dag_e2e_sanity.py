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
    checks = [
        _check("cli_returncode", completed.returncode == 0, {"returncode": completed.returncode}),
        _check("json_result", bool(payload), {}),
        _check("dag_path_exists", dag_path is not None and dag_path.is_file(), {"path": str(dag_path) if dag_path else None}),
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
    ok = all(item["ok"] for item in checks)
    return {
        "schema": "ask.tau_dag_e2e_sanity.v1",
        "status": "PASS" if ok else "FAIL",
        "ok": ok,
        "mocked": False,
        "live": True,
        "provider_live": bool(provider_gate.get("provider_live") is True or receipt.get("provider_live") is True),
        "what_was_exercised": [
            "/ask run.sh tau-dag CLI",
            "strict tau.dag_contract.v1 artifact emission",
            "real Tau CLI dag-run invocation",
            "real Tau run-status polling",
            "Tau DAG viewer-link command",
            "local command-spec worker subprocesses" if not provider_gate.get("provider_live") else "SciLLM provider route",
        ],
        "what_remains_unverified": [
            "Provider/model calls, unless provider_live is true.",
            "Semantic quality of solver/reviewer responses.",
            "Browser screenshot of the React Flow interface.",
        ],
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


def _json_or_error(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return {"parse_error": str(exc), "raw_stdout": text[-4000:]}
    return payload if isinstance(payload, dict) else {"parse_error": "stdout JSON root was not an object"}


if __name__ == "__main__":
    raise SystemExit(main())
