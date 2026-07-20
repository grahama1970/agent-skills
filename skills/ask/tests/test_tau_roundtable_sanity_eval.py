"""Tests for the Tau roundtable sanity eval runner."""

from __future__ import annotations

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
