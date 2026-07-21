"""Tests for the Tau roundtable sanity eval runner."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "tau_roundtable_sanity_eval.py"
SPEC = importlib.util.spec_from_file_location("tau_roundtable_sanity_eval", SCRIPT_PATH)
assert SPEC and SPEC.loader
tau_roundtable_sanity_eval = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tau_roundtable_sanity_eval
SPEC.loader.exec_module(tau_roundtable_sanity_eval)

WORKER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "tau_roundtable_worker.py"
WORKER_SPEC = importlib.util.spec_from_file_location("tau_roundtable_worker", WORKER_PATH)
assert WORKER_SPEC and WORKER_SPEC.loader
tau_roundtable_worker = importlib.util.module_from_spec(WORKER_SPEC)
sys.modules[WORKER_SPEC.name] = tau_roundtable_worker
WORKER_SPEC.loader.exec_module(tau_roundtable_worker)


def test_plan_lists_roundtable_eval_cases(tmp_path: Path) -> None:
    result = tau_roundtable_sanity_eval.build_plan(output_root=tmp_path, webgpt_project="tau")

    assert result["schema"] == "ask.tau_roundtable_sanity_eval.v1"
    assert result["status"] == "PLANNED"
    assert result["mocked"] is False
    assert result["live"] is False
    assert {case["id"] for case in result["cases"]} == {
        "browser_oracle_bindings",
        "compile_concurrent_all_handlers",
        "compile_sequential_all_handlers",
        "live_two_handler_smoke",
        "live_four_handler_sequential",
    }
    assert "plan-only" in result["what_remains_unverified"][0]


def test_join_command_checker_rejects_empty_args(tmp_path: Path) -> None:
    spec_dir = tmp_path / "join"
    spec_dir.mkdir()
    spec_path = spec_dir / "tau-dispatch-command.json"
    spec_path.write_text(json.dumps({"command": ["python", "worker.py", ""]}), encoding="utf-8")

    assert tau_roundtable_sanity_eval._join_command_has_no_empty_args(tmp_path) is False

    spec_path.write_text(json.dumps({"command": ["python", "worker.py"]}), encoding="utf-8")
    assert tau_roundtable_sanity_eval._join_command_has_no_empty_args(tmp_path) is True


def test_sequential_chain_checker_requires_handler_order() -> None:
    dag = {
        "edges": [
            {"from": "handler-webclaude", "to": "handler-webkimi"},
            {"from": "handler-webkimi", "to": "handler-webgemini"},
            {"from": "handler-webgemini", "to": "handler-webgpt"},
            {"from": "handler-webgpt", "to": "join"},
            {"from": "join", "to": "human"},
        ]
    }

    assert tau_roundtable_sanity_eval._has_sequential_chain(dag) is True
    dag["edges"][0] = {"from": "handler-webkimi", "to": "handler-webclaude"}
    assert tau_roundtable_sanity_eval._has_sequential_chain(dag) is False


def test_node_receipts_collects_statuses(tmp_path: Path) -> None:
    receipt_dir = tmp_path / "node-artifacts" / "handler-webkimi"
    receipt_dir.mkdir(parents=True)
    (receipt_dir / "node-receipt.json").write_text(
        json.dumps({"status": "PASS", "ok": True, "provider_live": True}),
        encoding="utf-8",
    )

    receipts = tau_roundtable_sanity_eval._node_receipts(tmp_path)

    assert receipts["handler-webkimi"]["ok"] is True
    assert tau_roundtable_sanity_eval._receipt_statuses(receipts) == {
        "handler-webkimi": {"status": "PASS", "ok": True, "provider_live": True}
    }


def test_worker_prompt_includes_prior_receipts_and_verdict_contract(tmp_path: Path) -> None:
    prior_dir = tmp_path / "handler-webgpt"
    prior_dir.mkdir(parents=True)
    response_path = prior_dir / "response.md"
    response_path.write_text("WebGPT produced the implementation.", encoding="utf-8")
    receipt_path = prior_dir / "node-receipt.json"
    receipt_path.write_text(
        json.dumps(
            {
                "schema": "ask.tau_dag_handler_receipt.v1",
                "node_id": "handler-webgpt",
                "handler": "webgpt",
                "status": "PASS",
                "ok": True,
                "response_path": str(response_path),
            }
        ),
        encoding="utf-8",
    )

    receipts = tau_roundtable_worker._load_prior_receipts(tmp_path, ["handler-webgpt"])
    prompt = tau_roundtable_worker._handler_prompt(
        "Ask webgpt to do the work, then ask webclaude to review it for pass/fail.",
        "webclaude",
        prior_receipts=receipts,
        requires_verdict=True,
    )

    assert "Prior handler receipts" in prompt
    assert "WebGPT produced the implementation." in prompt
    assert "VERDICT: PASS" in prompt
    assert tau_roundtable_worker._extract_verdict("VERDICT: FAIL\nReason") == "FAIL"
    assert tau_roundtable_worker._has_verdict("No clear verdict") is False


def test_worker_prior_receipts_marks_missing_upstream_not_ready(tmp_path: Path) -> None:
    receipts = tau_roundtable_worker._load_prior_receipts(tmp_path, ["handler-webgpt"])

    assert receipts == [
        {
            "node_id": "handler-webgpt",
            "status": "MISSING",
            "ok": False,
            "failure": f"missing prior receipt: {tmp_path / 'handler-webgpt' / 'node-receipt.json'}",
            "path": str(tmp_path / "handler-webgpt" / "node-receipt.json"),
        }
    ]


def test_worker_refreshes_webgpt_binding_after_response_proof_metadata(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps({"request": "Ask WebGPT for a concise answer."}), encoding="utf-8")
    artifact_dir = tmp_path / "node-artifacts" / "handler-webgpt"
    artifact_dir.mkdir(parents=True)
    bind_log = tmp_path / "bind-args.json"
    browser_oracle_run = tmp_path / "browser-oracle-run.sh"
    browser_oracle_run.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
case "${{1:-}}" in
  resolve)
    printf '%s\\n' '{{"project":"sparta-f36-review","tab_id":"837360696","conversation_url":"https://chatgpt.com/c/old","binding_path":"/tmp/sparta-f36-review.json"}}'
    ;;
  bind)
    python3 - "$@" > {str(bind_log)!r} <<'PY'
import json, sys
print(json.dumps(sys.argv[1:]))
PY
    printf '%s\\n' '{{"name":"sparta-f36-review","backend":"webgpt","tab_id":"837360696","conversation_url":"https://chatgpt.com/c/new","state_path":"/tmp/sparta-f36-review.json"}}'
    ;;
  *)
    echo "unexpected browser-oracle command: $*" >&2
    exit 99
    ;;
esac
""",
        encoding="utf-8",
    )
    browser_oracle_run.chmod(0o755)
    surf_run = tmp_path / "surf-run.sh"
    surf_run.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
output=""
raw_output=""
meta_output=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --output) output="$2"; shift 2 ;;
    --raw-output) raw_output="$2"; shift 2 ;;
    --meta-output) meta_output="$2"; shift 2 ;;
    *) shift ;;
  esac
done
printf 'A concise response.\\n' > "$output"
printf 'A concise response.\\n<<<WEBGPT_DONE:test>>>\\n' > "$raw_output"
cat > "$meta_output" <<'JSON'
{
  "status": "completed",
  "response_proof_status": "response_proven",
  "requested_tab_id": "837360696",
  "controlled_tab_id": "837360696",
  "conversation_url": "https://chatgpt.com/c/new",
  "current_url": "https://chatgpt.com/c/new",
  "raw_contains_sentinel": true,
  "clean_contains_sentinel": false
}
JSON
""",
        encoding="utf-8",
    )
    surf_run.chmod(0o755)
    args = argparse.Namespace(
        node_id="handler-webgpt",
        handler="webgpt",
        topology="parallel",
        request_file=str(request_path),
        browser_oracle_project="sparta-f36-review",
        next_agent="human",
        artifact_dir=str(artifact_dir),
        surf_run=str(surf_run),
        browser_oracle_run=str(browser_oracle_run),
        scillm_base_url="http://127.0.0.1:4001",
        scillm_api_key="",
        prior_node=[],
        timeout=10,
        stable_polls=1,
        no_activate=True,
        evidence=[],
    )

    result = tau_roundtable_worker._run_handler(args, {}, artifact_dir)

    assert result["exit_code"] == 0
    receipt = json.loads((artifact_dir / "node-receipt.json").read_text(encoding="utf-8"))
    assert receipt["browser_oracle_binding_refresh"]["status"] == "updated"
    assert receipt["browser_oracle_binding_refresh"]["previous_url"] == "https://chatgpt.com/c/old"
    assert receipt["browser_oracle_binding_refresh"]["current_url"] == "https://chatgpt.com/c/new"
    bind_args = json.loads(bind_log.read_text(encoding="utf-8"))
    assert bind_args == [
        "bind",
        "sparta-f36-review",
        "--backend",
        "webgpt",
        "--tab-id",
        "837360696",
        "--url",
        "https://chatgpt.com/c/new",
        "--manual",
        "--json",
    ]
