#!/usr/bin/env python3
"""Exercise public Ask/Tau CLIs with real SQLite and scripted local node outputs.

No GitHub/provider calls. Synthetic leases exercise the watchdog contract only.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

from watchdog import config, handlers, resume_state
from watchdog.core import write_json


def run(command, cwd, env=None):
    p = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, timeout=90)
    return {"command": command, "exit_code": p.returncode, "stdout": p.stdout, "stderr": p.stderr}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="resume-generation-", dir=args.out.parent.resolve()))
    tau = Path.home() / "workspace/experiments/tau"
    run_dir = root / "ask" / "ask-resume-eval"
    receipts = run_dir / "tau-receipts"
    agents = run_dir / "agents"
    agents.mkdir(parents=True)
    goal = {"goal_id": "resume-eval", "goal_version": 1, "goal_hash": "sha256:active-goal"}
    target = {"repo": "fixture/repo", "target": "resume-eval"}
    specs = run_dir / "command-specs"
    nodes = []
    for name, next_node in [("coder", "reviewer"), ("reviewer", "human")]:
        handoff = {
            "schema": "tau.agent_handoff.v1", "github": target, "goal": goal,
            "previous_subagent": name, "context": {"summary": name, "artifacts": []},
            "result": {"status": "PASS", "summary": name, "evidence": []},
            "rationale": "Follow the declared edge.",
            "next_agent": {"name": next_node, "executor": "human" if next_node == "human" else "local", "reason": "next"},
            "required_evidence": [], "stop_condition": "human",
        }
        write_json(root / f"{name}-pass.json", handoff)
        write_json(root / f"{name}-response.json", handoff if name == "coder" else {"status": "BLOCKED", "verdict": "EVAL_REVIEWER_BLOCK"})
        code = (
            "import json; from pathlib import Path; "
            f"p=Path({str(root / (name + '-count.txt'))!r}); "
            "p.write_text(str(int(p.read_text())+1 if p.exists() else 1)); "
            f"r=json.loads(Path({str(root / (name + '-response.json'))!r}).read_text()); "
            f"n=Path({str(run_dir / 'node-artifacts' / name / 'node-receipt.json')!r}); "
            "n.parent.mkdir(parents=True,exist_ok=True); "
            f"n.write_text(json.dumps({{'node_id':{name!r},'status':r.get('result',r).get('status'),"
            "'ok':r.get('result',r).get('status')=='PASS'})); print(json.dumps(r))"
        )
        spec = specs / name / "tau-dispatch-command.json"
        write_json(spec, {"command": [sys.executable, "-c", code], "timeout_s": 10, "cwd": str(root)})
        nodes.append({"id": name, "agent": name, "executor": "local", "max_attempts": 1, "command_spec": str(spec), "required_evidence": []})
    dag = {"schema": "tau.dag_contract.v1", "dag_id": run_dir.name, "goal": goal, "target": target,
           "entry_node": "coder", "terminal_nodes": ["human"], "nodes": nodes,
           "edges": [{"from": "coder", "to": "reviewer"}, {"from": "reviewer", "to": "human"}],
           "limits": {"resume": True, "max_total_attempts": 3}, "required_evidence": [],
           "fail_closed_on": ["goal_hash_mismatch", "target_changed", "unexpected_node", "unexpected_edge", "missing_required_evidence", "max_attempts_exceeded", "malformed_handoff"]}
    write_json(run_dir / "dag.json", dag)
    first = run(["uv", "run", "tau", "dag-run", str(run_dir / "dag.json"), "--receipt-dir", str(receipts),
                 "--agents-root", str(agents), "--command-spec-root", str(specs), "--scheduler", "bounded-ready-queue"], tau)
    write_json(root / "initial-command.json", first)
    assert (receipts / "dag-run.sqlite3").is_file(), first
    (root / "reviewer-response.json").write_bytes((root / "reviewer-pass.json").read_bytes())
    journal = root / "operation.json"
    command = [str(config.ask_run_sh()), "runs", "resume", str(run_dir), "--execute", "--json"]
    checks = {}
    for generation, old_status in [(7, "PASS"), (8, "BLOCKED"), (9, None)]:
        lease_agent = "project-watchdog-local-eval"
        write_json(journal, {"schema": "agent_skills.project_watchdog.primary_operation.v2",
            "phase": "running", "run_id": "watchdog-eval", "ask_run_dir": str(run_dir.parent),
            "tau_settled": True, "lease_released": old_status is not None,
            "owner_token": "local-eval", "lease_agent": lease_agent, "lease_actor": "eval",
            "lease_before_event": {"id": generation-1, "event": "unlabeled"},
            "lease_event": {"id": generation, "event": "labeled", "actor": "eval", "created_at": "2026-09-09T00:00:00Z"}})
        if old_status:
            write_json(receipts / "dag-progress.json", {"status": old_status})
        record = SimpleNamespace(journal=str(journal), lease_event=SimpleNamespace(id=generation), lease_agent=lease_agent)
        fence = resume_state.begin(record, run_dir)
        assert handlers.inspect_tau_stream(run_dir.parent)["terminal"] is False
        env = dict(os.environ, PROJECT_WATCHDOG_OPERATION_JOURNAL=str(journal))
        row = run(command, root, env)
        write_json(root / f"resume-command-{generation}.json", row)
        resume_state.complete(fence, row)
        observed = handlers.inspect_tau_stream(run_dir.parent)
        write_json(root / f"observed-{generation}.json", observed)
        if old_status:
            checks[f"old_{old_status}_not_reused"] = observed.get("invocation_failed") is True and observed["terminal"] is False
            checks[f"nested_error_{old_status}_preserved"] = observed["resume_control"]["returncode"] == 2 and "confirmed active lease" in observed["resume_control"]["stderr_excerpt"]
        else:
            checks["current_generation_settled"] = observed["terminal"] is True and observed["terminal_status"] == "PASS"
    write_json(run_dir / "archive/extra/dag.json", {"nodes": [{"id": "decoy"}]})
    checks["decoy_dag_ignored"] = handlers.inspect_tau_stream(run_dir.parent)["terminal"] is True
    checks["creator_not_relaunched"] = (root / "coder-count.txt").read_text() == "1"
    checks["reviewer_reran_once"] = (root / "reviewer-count.txt").read_text() == "2"
    result_path = receipts / "command-spec-resume-result.json"
    result = json.loads(result_path.read_text())
    result["watchdog_journal"]["lease_event_id"] = 999
    write_json(result_path, result)
    checks["cross_generation_rejected"] = handlers.inspect_tau_stream(run_dir.parent)["terminal"] is False
    result["watchdog_journal"]["lease_event_id"] = 9
    write_json(result_path, result)
    with sqlite3.connect(receipts / "dag-run.sqlite3") as db:
        attempt, original = db.execute(
            "SELECT attempt_id,committed_json FROM dag_node_attempts "
            "JOIN dag_attempt_outputs USING(attempt_id) WHERE node_id='coder'"
        ).fetchone()
        tampered = json.loads(original)
        tampered["accepted_output"]["context"]["summary"] = "forged preserved creator"
        db.execute("UPDATE dag_attempt_outputs SET committed_json=? WHERE attempt_id=?",
                   (json.dumps(tampered), attempt))
        db.commit()
    checks["preserved_admission_mutation_rejected"] = handlers.inspect_tau_stream(run_dir.parent)["terminal"] is False
    proof = {"schema": "agent_skills.project_watchdog.resume_generation_proof.v1",
             "ok": all(checks.values()), "status": "PASS" if all(checks.values()) else "FAIL",
             "mocked": False, "live": True, "provider_live": False, "github_live": False,
             "proof_boundary": "Public Ask/Tau CLI and real SQLite; scripted local nodes and synthetic leases, no provider/GitHub calls.",
             "checks": checks, "artifacts_root": str(root)}
    write_json(args.out, proof)
    print(json.dumps(proof, indent=2))
    return 0 if proof["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
