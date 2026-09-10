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

from watchdog import config, handlers, native_ticket, primary, resume_state
from watchdog.core import write_json
from watchdog.primary_models import VerificationPlan


def check_verification_plans(root):
    artifact = str(root / "verified-result.json")
    plan = {"schema": "agent_skills.project_watchdog.verification_plan.v1",
            "commands": ["uv run python -c 'print(1)'"], "artifacts": [artifact],
            "coverage": {"Run proof.": "Read the produced result."}}
    checks = {"valid_string_coverage_admitted": VerificationPlan.model_validate(plan).coverage == plan["coverage"]}
    malformed = {
        "empty_command_rejected": {"commands": [""]},
        "multiline_command_rejected": {"commands": ["true\ntrue"]},
        "broken_quoting_rejected": {"commands": ["python -c 'unterminated"]},
        "nul_command_rejected": {"commands": ["python\x00-c"]},
        "dict_coverage_rejected": {"coverage": {"Run proof.": {"unexpected": "not authority"}}},
        "nonstring_coverage_key_rejected": {"coverage": {1: "not a clause"}},
        "empty_artifact_rejected": {"artifacts": [""]},
    }
    for name, change in malformed.items():
        try:
            VerificationPlan.model_validate({**plan, **change})
        except ValueError:
            checks[name] = True
        else:
            checks[name] = False
    parser = getattr(handlers, "validated_verification_plan", None)
    checks["native_plan_consumer_present"] = callable(parser)
    if parser is not None:
        body = "## Required proof\n\nRun proof.\n"
        review = "VERDICT: PASS\nPROOF_ARTIFACT: " + artifact + "\nVERIFY_PLAN: " + json.dumps(plan)
        checks["valid_review_plan_admitted"] = parser(review, body, root).artifacts == [artifact]
        variants = {
            "truncated_reviewer_plan_rejected": review[:-12],
            "missing_reviewer_plan_rejected": "VERDICT: PASS\nPROOF_ARTIFACT: " + artifact,
            "missing_mandatory_artifact_rejected": review.replace(json.dumps([artifact]), json.dumps([str(root / 'other.json')]), 1),
            "missing_proof_clause_rejected": review.replace('"Run proof."', '"Different clause."'),
            "multiple_plans_rejected": review + "\nVERIFY_PLAN: " + json.dumps(plan),
        }
        for name, text in variants.items():
            try:
                parser(text, body, root)
            except ValueError:
                checks[name] = True
            else:
                checks[name] = False
    return checks


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
            "schema": "tau.agent_handoff.v1", "status": "PASS", "verdict": "PASS",
            "github": target, "goal": goal,
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
    operation_area = root / ".git" / "project-watchdog-primary" / "operations"
    operation_area.mkdir(parents=True)
    journal = operation_area / "1628-local-eval.json"
    command = [str(config.ask_run_sh()), "runs", "resume", str(run_dir), "--execute", "--json"]
    checks = check_verification_plans(root)
    lease_agent = "project-watchdog-local-eval"
    for generation, old_status in [(7, "PASS"), (8, "BLOCKED"), (9, None)]:
        write_json(journal, {"schema": "agent_skills.project_watchdog.primary_operation.v2",
            "phase": "running", "run_id": "watchdog-eval", "ask_run_dir": str(run_dir.parent),
            "tau_settled": True, "lease_released": old_status is not None,
            "owner_token": "local-eval", "lease_agent": lease_agent, "lease_actor": "eval",
            "lease_before_event": {"id": generation-1, "event": "unlabeled", "actor": "eval", "created_at": "2026-09-09T00:00:00Z"},
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
    admitted_observation = handlers.inspect_tau_stream(run_dir.parent)
    before_coder_count = (root / "coder-count.txt").read_text()
    before_reviewer_count = (root / "reviewer-count.txt").read_text()
    write_json(journal, {"schema": "agent_skills.project_watchdog.primary_operation.v2",
        "phase": "retryable", "run_id": "watchdog-eval-finalize", "repo": "fixture/repo",
        "project_id": "fixture", "issue_number": 1628, "action": "ticket_repair",
        "owner_token": "local-eval", "root": str(root), "journal": str(journal),
        "result_path": str(root / "finalize-result.json"), "receipt_dir": str(receipts),
        "targets": ["skills/project-watchdog"], "task_sha256": "task", "scheduler_pid": os.getpid(),
        "boot_id": "eval-boot", "lease_actor": "eval", "lease_agent": lease_agent,
        "lease_before_event": {"id": 11, "event": "unlabeled", "actor": "eval", "created_at": "2026-09-09T00:00:00Z"},
        "lease_event": {"id": 12, "event": "labeled", "actor": "eval", "created_at": "2026-09-09T00:00:00Z"},
        "lease_released": True, "ask_run_dir": str(run_dir.parent), "tau_settled": True})
    finalization_invocations = []
    original_identity, original_area = primary.identity, primary._area
    original_acquire = native_ticket.acquire
    original_stream_runner = handlers.run_ask_tau_dag_with_stream_monitor
    original_finish = handlers.finish_primary_operation
    original_release = primary._finish_release
    try:
        primary.identity = lambda candidate: (Path(candidate).resolve(strict=True), (root / ".git").resolve())
        primary._area = lambda candidate: operation_area.parent

        def acquire(record, result, checkpoint):
            result["commands"].append({"command": ["native", "lease", "finalize"]})
            checkpoint("leased", lease_event={"id": 13, "event": "labeled", "actor": "eval", "created_at": "2026-09-09T00:00:01Z"},
                       lease_actor="eval", lease_agent=lease_agent, lease_released=False)

        def unexpected_resume(command, **kwargs):
            finalization_invocations.append(command)
            return {"command": command, "exit_code": 99, "stdout": "", "stderr": "unexpected resume"}

        native_ticket.acquire = acquire
        handlers.run_ask_tau_dag_with_stream_monitor = unexpected_resume
        handlers.finish_primary_operation = lambda row: {"ok": False, "status": "NEEDS_ATTENTION", "summary": "fixture finalized"}
        primary._finish_release = lambda row: True
        primary.reattach_and_resume(root, journal, apply=True, timeout_s=30)
    finally:
        primary.identity, primary._area = original_identity, original_area
        native_ticket.acquire = original_acquire
        handlers.run_ask_tau_dag_with_stream_monitor = original_stream_runner
        handlers.finish_primary_operation = original_finish
        primary._finish_release = original_release
    finalization = json.loads((receipts / "retained-resume-finalization.json").read_text())
    checks["second_finalization_no_ask_invocation"] = finalization_invocations == []
    checks["second_finalization_provider_counts_unchanged"] = ((root / "coder-count.txt").read_text() == before_coder_count
        and (root / "reviewer-count.txt").read_text() == before_reviewer_count)
    checks["second_finalization_receipt_bound"] = (finalization.get("provider_dispatched") is False
        and finalization.get("admitted_generation") == admitted_observation.get("resume_generation")
        and finalization.get("admitted_journal") == str(journal)
        and finalization.get("admitted_lease_agent") == lease_agent
        and finalization.get("new_lease_event_id") == 13
        and finalization.get("new_lease_event_id") != finalization.get("admitted_generation")
        and finalization.get("new_lease_agent") == lease_agent)
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
