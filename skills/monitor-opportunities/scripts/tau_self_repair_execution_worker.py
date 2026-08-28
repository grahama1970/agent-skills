#!/usr/bin/env python3
"""No-effect Tau worker for the monitor-opportunities self-repair proof DAG."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


GOAL_HASH = "sha256:96c6a2177ab4b3d588e6662a5e4a4c21a6f8f13ac7b06a899c090074f8630f4c"
RAW_FAILURE = (
    "[monitor_opportunities_nightly_revision_mismatch] scheduler log emitted "
    "NIGHTLY_REVISION_MISMATCH from a stale --expected-revision pin. "
    "expected dbeba84dce got e8a71c3d55"
)

NODE_ORDER = [
    "seed-failed-checkpoint",
    "pipeline-self-repair-record-failure",
    "triage-error-classify",
    "ticket-bind-or-create",
    "project-watchdog-dispatch",
    "agentic-eval-retained-guard",
    "rerun-failed-checkpoint",
]

EVIDENCE_KIND = {
    "seed-failed-checkpoint": "failed_checkpoint_receipt",
    "pipeline-self-repair-record-failure": "pipeline_self_repair_ledger",
    "triage-error-classify": "triage_error_classification",
    "ticket-bind-or-create": "ticket_preview",
    "project-watchdog-dispatch": "watchdog_dispatch_projection",
    "agentic-eval-retained-guard": "agentic_eval_retained_guard",
    "rerun-failed-checkpoint": "checkpoint_rerun_receipt",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--node-id", required=True, choices=NODE_ORDER)
    args = parser.parse_args()

    payload = json.load(sys.stdin)
    repo = find_repo_root(Path(__file__))
    artifact_dir = Path(os.environ["TAU_HANDOFF_COMMAND_ARTIFACT_DIR"])
    artifact_dir.mkdir(parents=True, exist_ok=True)

    node_payload = build_node_artifact(args.node_id, payload, repo, artifact_dir)
    artifact = artifact_dir / f"{args.node_id}.json"
    artifact.write_text(json.dumps(node_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps(handoff(args.node_id, payload, artifact, node_payload), sort_keys=True))
    return 0


def find_repo_root(start: Path) -> Path:
    for parent in start.resolve().parents:
        if (parent / "skills" / "monitor-opportunities").is_dir():
            return parent
    raise RuntimeError(f"could not find agent-skills repo root from {start}")


def build_node_artifact(
    node_id: str, payload: dict[str, Any], repo: Path, artifact_dir: Path
) -> dict[str, Any]:
    if node_id == "seed-failed-checkpoint":
        return seed_failed_checkpoint(payload)
    if node_id == "pipeline-self-repair-record-failure":
        return record_failure(payload, repo, artifact_dir)
    if node_id == "triage-error-classify":
        return classify_failure(repo)
    if node_id == "ticket-bind-or-create":
        return ticket_projection(payload)
    if node_id == "project-watchdog-dispatch":
        return watchdog_projection(payload)
    if node_id == "agentic-eval-retained-guard":
        return eval_guard(payload, repo)
    if node_id == "rerun-failed-checkpoint":
        return rerun_checkpoint(payload)
    raise RuntimeError(f"unsupported node: {node_id}")


def base_artifact(node_id: str) -> dict[str, Any]:
    return {
        "schema": "monitor_opportunities.tau_self_repair_execution_proof.node_receipt.v1",
        "node_id": node_id,
        "status": "PASS",
        "mocked": False,
        "live": False,
        "external_effects": False,
        "goal_hash": GOAL_HASH,
        "proof_boundary": (
            "Local Tau command execution and no-effect self-repair receipts only; "
            "no LinkedIn, ATS, Gmail, GitHub mutation, or watchdog dispatch."
        ),
    }


def seed_failed_checkpoint(payload: dict[str, Any]) -> dict[str, Any]:
    artifact = base_artifact("seed-failed-checkpoint")
    artifact.update(
        {
            "failed_step_id": "nightly-run",
            "failure_code": "NIGHTLY_REVISION_MISMATCH",
            "raw_signal": RAW_FAILURE,
            "checkpoint_id": "nightly-run",
            "run_id": payload.get("run_id") or "monitor-opportunities-self-repair-execution-proof",
        }
    )
    return artifact


def record_failure(payload: dict[str, Any], repo: Path, artifact_dir: Path) -> dict[str, Any]:
    failure_receipt = artifact_dir / "failed-step-receipt.json"
    failure_receipt.write_text(
        json.dumps(
            {
                "schema": "monitor_opportunities.failed_step_receipt.v1",
                "status": "FAIL",
                "step_id": "nightly-run",
                "failure_code": "NIGHTLY_REVISION_MISMATCH",
                "raw_signal": RAW_FAILURE,
                "external_effects": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    run_root = artifact_dir / "pipeline-self-repair-run"
    ledger = run_root / "replay_ledger.jsonl"
    cmd = [
        str(repo / "skills" / "pipeline-self-repair" / "run.sh"),
        "record-failure",
        "--pipeline",
        "monitor-opportunities",
        "--step-id",
        "nightly-run",
        "--run-id",
        "monitor-opportunities-self-repair-execution-proof",
        "--receipt",
        str(failure_receipt),
        "--layer",
        "monitor-opportunities",
        "--target",
        "skills/monitor-opportunities",
        "--run-root",
        str(run_root),
        "--ledger",
        str(ledger),
        "--goal-project",
        "monitor-opportunities",
        "--repo",
        "grahama1970/agent-skills",
        "--skip-memory",
        "--skip-github",
        "--no-ticket",
        "--json",
    ]
    result = subprocess.run(cmd, cwd=repo, text=True, capture_output=True, timeout=90)
    parsed = parse_json_stdout(result.stdout)
    artifact = base_artifact("pipeline-self-repair-record-failure")
    event = parsed.get("event") if isinstance(parsed, dict) else {}
    artifact.update(
        {
            "live": True,
            "command": cmd,
            "returncode": result.returncode,
            "ledger_path": str(ledger),
            "ledger_exists": ledger.is_file(),
            "event_type": event.get("event_type") if isinstance(event, dict) else None,
            "category_key": event.get("category_key") if isinstance(event, dict) else None,
            "triage_code": (event.get("triage") or {}).get("code") if isinstance(event, dict) else None,
            "ticket_action": (event.get("ticket") or {}).get("action") if isinstance(event, dict) else None,
            "stderr_excerpt": result.stderr[-2000:],
        }
    )
    if result.returncode != 0 or not ledger.is_file():
        artifact["status"] = "FAIL"
    return artifact


def classify_failure(repo: Path) -> dict[str, Any]:
    cmd = [
        str(repo / "skills" / "triage-error" / "run.sh"),
        "classify",
        "--text",
        RAW_FAILURE,
        "--layer",
        "monitor-opportunities",
    ]
    result = subprocess.run(cmd, cwd=repo, text=True, capture_output=True, timeout=60)
    parsed = parse_json_stdout(result.stdout)
    artifact = base_artifact("triage-error-classify")
    artifact.update(
        {
            "live": True,
            "command": cmd,
            "returncode": result.returncode,
            "classification": parsed,
            "failure_code": parsed.get("code") if isinstance(parsed, dict) else None,
            "ambiguous": parsed.get("ambiguous") if isinstance(parsed, dict) else None,
            "recoverable": parsed.get("recoverable") if isinstance(parsed, dict) else None,
            "next_command": parsed.get("next_command") if isinstance(parsed, dict) else None,
            "stderr_excerpt": result.stderr[-2000:],
        }
    )
    if (
        result.returncode != 0
        or not isinstance(parsed, dict)
        or parsed.get("code") != "monitor_opportunities_nightly_revision_mismatch"
        or parsed.get("ambiguous") is not False
    ):
        artifact["status"] = "FAIL"
    return artifact


def ticket_projection(payload: dict[str, Any]) -> dict[str, Any]:
    triage = latest_evidence_payload(payload, "triage_error_classification")
    artifact = base_artifact("ticket-bind-or-create")
    artifact.update(
        {
            "ticket_mode": "preview_only",
            "mutation_performed": False,
            "route": "ops_or_scheduler",
            "agent": "agent-skill-maintainer",
            "label": "agent-work",
            "target": "skills/monitor-opportunities",
            "failure_code": triage.get("failure_code"),
            "acceptance_criterion": (
                "scheduler-exec-check no longer emits NIGHTLY_REVISION_MISMATCH "
                "and writes a fresh no-effect receipt from the intended worktree"
            ),
            "required_proof_command": (
                "uv run --project skills/monitor-opportunities python "
                "skills/monitor-opportunities/scripts/eval_nightly_revision_mismatch_triage.py"
            ),
        }
    )
    if triage.get("failure_code") != "monitor_opportunities_nightly_revision_mismatch":
        artifact["status"] = "FAIL"
    return artifact


def watchdog_projection(payload: dict[str, Any]) -> dict[str, Any]:
    ticket = latest_evidence_payload(payload, "ticket_preview")
    artifact = base_artifact("project-watchdog-dispatch")
    artifact.update(
        {
            "dispatch_mode": "projected_no_apply",
            "mutation_performed": False,
            "project": "agent-skills",
            "target": ticket.get("target"),
            "route": ticket.get("route"),
            "tau_stream_monitor_required": True,
            "tau_stream_monitor": {
                "schema": "project_watchdog.tau_stream_monitor.v1",
                "status": "PROJECTED",
                "required_artifact": "tau-stream-monitor.json",
                "stop_condition": "terminal Tau verdict PASS, FAIL, BLOCKED, or NEEDS_ATTENTION",
            },
        }
    )
    if ticket.get("route") != "ops_or_scheduler":
        artifact["status"] = "FAIL"
    return artifact


def eval_guard(payload: dict[str, Any], repo: Path) -> dict[str, Any]:
    fixture = repo / "skills" / "monitor-opportunities" / "fixtures" / "agentic_eval.json"
    data = json.loads(fixture.read_text(encoding="utf-8"))
    case_names = {
        item.get("name")
        for item in data.get("cases", [])
        if isinstance(item, dict)
    }
    required_cases = [
        "nightly-revision-mismatch-triage-regression-2026-08-28",
        "scheduler-exec-check-records-pipeline-self-repair",
        "tau-dag-visualizes-nightly-self-repair-orchestration",
        "tau-dag-executes-self-repair-proof-branch",
    ]
    missing = [name for name in required_cases if name not in case_names]
    artifact = base_artifact("agentic-eval-retained-guard")
    artifact.update(
        {
            "fixture": str(fixture),
            "required_cases": required_cases,
            "missing_cases": missing,
            "guard_present": not missing,
        }
    )
    if missing:
        artifact["status"] = "FAIL"
    return artifact


def rerun_checkpoint(payload: dict[str, Any]) -> dict[str, Any]:
    guard = latest_evidence_payload(payload, "agentic_eval_retained_guard")
    artifact = base_artifact("rerun-failed-checkpoint")
    artifact.update(
        {
            "rerun_mode": "same_checkpoint_no_effect_proof",
            "failed_checkpoint_id": "nightly-run",
            "rerun_command": (
                "skills/monitor-opportunities/run.sh scheduler-exec-check "
                "--out <fresh-receipt> --timeout-seconds 7200"
            ),
            "guard_present": guard.get("guard_present"),
            "external_submit_authority": "none",
            "advance_allowed": bool(guard.get("guard_present")),
        }
    )
    if not guard.get("guard_present"):
        artifact["status"] = "FAIL"
    return artifact


def latest_evidence_payload(payload: dict[str, Any], kind: str) -> dict[str, Any]:
    evidence = payload.get("result", {}).get("evidence", [])
    for item in reversed(evidence if isinstance(evidence, list) else []):
        if not isinstance(item, dict) or item.get("kind") != kind:
            continue
        path = item.get("path")
        if isinstance(path, str) and Path(path).is_file():
            try:
                data = json.loads(Path(path).read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
            if isinstance(data, dict):
                return data
    return {}


def parse_json_stdout(stdout: str) -> dict[str, Any]:
    text = stdout.strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return {}
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return {}
    return parsed if isinstance(parsed, dict) else {}


def handoff(
    node_id: str,
    payload: dict[str, Any],
    artifact: Path,
    node_payload: dict[str, Any],
) -> dict[str, Any]:
    current_index = NODE_ORDER.index(node_id)
    next_agent = NODE_ORDER[current_index + 1] if current_index + 1 < len(NODE_ORDER) else "human"
    next_executor = "local" if next_agent != "human" else "human"
    status = "PASS" if node_payload.get("status") == "PASS" else "FAIL"
    return {
        "schema": "tau.agent_handoff.v1",
        "github": payload.get("github") or {"repo": "grahama1970/agent-skills"},
        "goal": payload.get("goal") or {
            "goal_id": "monitor-opportunities-nightly",
            "goal_version": 1,
            "goal_hash": GOAL_HASH,
        },
        "previous_subagent": node_id,
        "context": {
            "summary": f"{node_id} produced monitor-opportunities self-repair proof evidence.",
            "artifacts": [str(artifact)],
        },
        "result": {
            "status": status,
            "summary": f"{node_id} status {status}; external_effects=false.",
            "evidence": [
                {
                    "kind": EVIDENCE_KIND[node_id],
                    "path": str(artifact),
                    "status": status,
                    "external_effects": False,
                    "goal_hash": GOAL_HASH,
                }
            ],
        },
        "rationale": "The Tau proof DAG exercises the local no-effect self-repair branch.",
        "next_agent": {
            "name": next_agent,
            "executor": next_executor,
            "reason": "Continue along the explicit monitor-opportunities self-repair proof DAG.",
        },
        "required_evidence": [EVIDENCE_KIND[node_id]],
        "stop_condition": "Stop at human terminal node or any fail-closed Tau receipt.",
    }


if __name__ == "__main__":
    raise SystemExit(main())
