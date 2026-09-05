"""Retain Tau's completed-response/semantic-rejection shape and safety negatives.

Fixture-backed, no GitHub mutation or provider calls. The live incident and
owned-lease recovery are separate receipts; this only guards their parser seam.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
from watchdog import handlers

parser = argparse.ArgumentParser()
parser.add_argument("--baseline-ref")
parser.add_argument("--run-dir", type=Path)
args = parser.parse_args()
if args.baseline_ref:
    source = subprocess.check_output(["git", "show", args.baseline_ref +
        ":skills/project-watchdog/scripts/watchdog/handlers.py"], cwd=SKILL)
    baseline = types.ModuleType("watchdog.semantic_refusal_baseline")
    baseline.__package__ = "watchdog"
    exec(compile(source, "baseline-handlers.py", "exec"), baseline.__dict__)
    inspect = baseline.inspect_tau_stream
else:
    inspect = handlers.inspect_tau_stream

if args.run_dir:
    result = inspect(args.run_dir)
    assert result["terminal"] and result["terminal_status"] == "BLOCKED", result
    assert result["semantic_refusal"]["failure_code"] == "evidence_receipt_verdict_failed"
    print(json.dumps({"status": "PASS", "mocked": False, "live": False,
        "proof_scope": "replay of captured real canary receipts; no new execution",
        "terminal_status": result["terminal_status"], "source": result["terminal_source"]}))
    raise SystemExit(0)

with tempfile.TemporaryDirectory(prefix="watchdog-semantic-refusal-") as temp:
    ask = Path(temp)
    root = ask / "retained-run"
    def put(name, value):
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(value))
    goal_hash = "sha256:" + hashlib.sha256(b"incident-goal").hexdigest()
    plan = {"schema": "tau.dag_contract.v1", "dag_id": "retained-run", "goal": {"goal_hash": goal_hash},
            "nodes": [{"id": "creator"}, {"id": "reviewer"}]}
    put("dag.json", plan)
    progress = {"schema": "tau.dag_progress.v1", "dag_id": "retained-run",
                "status": "BLOCKED", "active_subagents": [], "event_count": 5}
    put("tau-receipts/dag-progress.json", progress)
    native = {"schema": "tau.dag_receipt.v1", "dag_id": "retained-run",
        "status": "BLOCKED", "durable": True, "active_goal_hash": goal_hash,
        "contract_sha256": "sha256:" + hashlib.sha256((root / "dag.json").read_bytes()).hexdigest(),
        "node_terminal_states": {"creator": "blocked", "reviewer": "pending"},
        "dispatches": [{"status": "COMPLETED", "stop_reason": "response_consumed"}],
        "alerts": [{"code": "evidence_receipt_verdict_failed"}],
        "scheduler_events": [{"event": "scheduler_finished"}]}
    def final(value):
        put("tau-receipts/dag-receipt.json", value)
        put("execution-status.json", {"schema": "ask.tau_dag_execution.v1", "status": value["status"], "receipt": value})
    put("node-artifacts/creator/node-receipt.json", {"node_id": "creator", "status": "PASS"})
    assert not inspect(ask)["terminal"], "node PASS and progress alone cannot settle a run"
    final(native)
    result = inspect(ask)
    assert result["terminal"] and result["terminal_status"] == "BLOCKED", result
    assert result["event_count"] == 5
    for field, value in [("contract_sha256", "wrong"), ("dag_id", "foreign-run"),
                         ("active_goal_hash", "foreign-goal"), ("status", "PASS"),
                         ("node_terminal_states", {"creator": "running", "reviewer": "pending"}),
                         ("alerts", [{"code": "transport_timeout"}]),
                         ("dispatches", [{"status": "CANCELLED", "stop_reason": "timeout"}])]:
        altered = copy.deepcopy(native)
        altered[field] = value
        final(altered)
        assert not inspect(ask)["terminal"], field
    final(native)
    progress["active_subagents"] = [{"node_id": "creator"}]
    put("tau-receipts/dag-progress.json", progress)
    assert not inspect(ask)["terminal"], "active execution cannot be released"
print(json.dumps({"status": "PASS", "checks": 10, "mocked": True,
                  "proof_scope": "semantic-refusal parser boundary only"}))
