#!/usr/bin/env python3
"""Run and read back the no-effect Tau self-repair execution proof."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


EXPECTED_SELECTED = [
    "seed-failed-checkpoint",
    "pipeline-self-repair-record-failure",
    "triage-error-classify",
    "ticket-bind-or-create",
    "project-watchdog-dispatch",
    "agentic-eval-retained-guard",
    "rerun-failed-checkpoint",
]

EXPECTED_EVIDENCE = [
    "failed_checkpoint_receipt",
    "pipeline_self_repair_ledger",
    "triage_error_classification",
    "ticket_preview",
    "watchdog_dispatch_projection",
    "agentic_eval_retained_guard",
    "checkpoint_rerun_receipt",
]

NODE_EVIDENCE_KIND = dict(zip(EXPECTED_SELECTED, EXPECTED_EVIDENCE, strict=True))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        default="/tmp/monitor-opportunities-self-repair-execution-proof-summary.json",
        help="Summary receipt path.",
    )
    args = parser.parse_args()

    repo = find_repo_root(Path(__file__))
    tau_repo = repo.parent / "tau"
    dag = (
        repo
        / "skills"
        / "monitor-opportunities"
        / "fixtures"
        / "tau"
        / "monitor-opportunities-self-repair-execution-proof.dag.json"
    )
    run_dir = Path(tempfile.mkdtemp(prefix="monitor-opportunities-self-repair-execution-proof-"))
    cmd = [
        "uv",
        "run",
        "tau",
        "dag-run",
        str(dag),
        "--receipt-dir",
        str(run_dir),
        "--scheduler",
        "bounded-ready-queue",
        "--no-resume",
    ]
    result = subprocess.run(cmd, cwd=tau_repo, text=True, capture_output=True, timeout=180)
    summary = {
        "schema": "monitor_opportunities.tau_self_repair_execution_eval.v1",
        "status": "FAIL",
        "mocked": False,
        "live": True,
        "external_effects": False,
        "command": cmd,
        "returncode": result.returncode,
        "run_dir": str(run_dir),
        "dag_receipt": str(run_dir / "dag-receipt.json"),
        "errors": [],
    }

    receipt = load_json(run_dir / "dag-receipt.json")
    summary["tau_status"] = receipt.get("status")
    summary["tau_verdict"] = receipt.get("verdict")
    summary["selected_agents"] = receipt.get("selected_agents")
    summary["scheduler_event_count"] = len(receipt.get("scheduler_events") or [])
    summary["command_executed"] = receipt.get("command_executed")
    summary["tau_mocked"] = receipt.get("mocked")
    summary["tau_live"] = receipt.get("live")

    errors: list[str] = []
    if result.returncode != 0:
        errors.append(f"tau dag-run exit {result.returncode}")
    if receipt.get("status") != "PASS":
        errors.append(f"unexpected receipt status {receipt.get('status')!r}")
    if receipt.get("verdict") != "PASS":
        errors.append(f"unexpected receipt verdict {receipt.get('verdict')!r}")
    if receipt.get("selected_agents") != EXPECTED_SELECTED:
        errors.append("selected_agents mismatch")
    if receipt.get("command_executed") is not True:
        errors.append("command_executed was not true")
    if receipt.get("mocked") is not False:
        errors.append("Tau receipt unexpectedly marked mocked")
    if receipt.get("live") is not True:
        errors.append("Tau receipt did not mark live local command execution")

    evidence = response_evidence(receipt)
    kinds = {item.get("kind") for item in evidence if isinstance(item, dict)}
    missing = [kind for kind in EXPECTED_EVIDENCE if kind not in kinds]
    if missing:
        errors.append(f"missing evidence kinds: {missing}")
    summary["evidence_kinds"] = sorted(str(kind) for kind in kinds)

    ledger_artifact = load_evidence_artifact(evidence, "pipeline_self_repair_ledger")
    triage_artifact = load_evidence_artifact(evidence, "triage_error_classification")
    summary["ledger_exists"] = ledger_artifact.get("ledger_exists")
    summary["ledger_triage_code"] = ledger_artifact.get("triage_code")
    summary["triage_ambiguous"] = (triage_artifact.get("classification") or {}).get("ambiguous")
    if ledger_artifact.get("ledger_exists") is not True:
        errors.append("pipeline-self-repair ledger artifact was not written")
    if ledger_artifact.get("triage_code") != "monitor_opportunities_nightly_revision_mismatch":
        errors.append("pipeline-self-repair triage_code mismatch")
    if (triage_artifact.get("classification") or {}).get("ambiguous") is not False:
        errors.append("triage-error classification was ambiguous")

    summary["errors"] = errors
    summary["status"] = "PASS" if not errors else "FAIL"
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if errors:
        print(f"TAU_SELF_REPAIR_EXECUTION_PROOF_FAIL proof={out}", file=sys.stderr)
        for error in errors:
            print(error, file=sys.stderr)
        print(result.stderr[-2000:], file=sys.stderr)
        return 1
    print(
        "TAU_SELF_REPAIR_EXECUTION_PROOF_OK "
        f"selected={len(EXPECTED_SELECTED)} "
        f"status={summary['tau_status']} "
        f"ledger_exists={summary['ledger_exists']} "
        f"triage_code={summary['ledger_triage_code']} "
        "external_effects=false "
        f"proof={out}"
    )
    return 0


def find_repo_root(start: Path) -> Path:
    for parent in start.resolve().parents:
        if (parent / "skills" / "monitor-opportunities").is_dir():
            return parent
    raise RuntimeError(f"could not find agent-skills repo root from {start}")


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def response_evidence(receipt: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    node_artifacts = receipt.get("node_artifacts")
    if isinstance(node_artifacts, dict):
        for node_id, paths in node_artifacts.items():
            if not isinstance(node_id, str) or not isinstance(paths, list):
                continue
            kind = NODE_EVIDENCE_KIND.get(node_id)
            if not kind:
                continue
            for raw_path in paths:
                if not isinstance(raw_path, str):
                    continue
                path = Path(raw_path)
                if path.name != f"{node_id}.json":
                    continue
                items.append({"kind": kind, "path": str(path), "status": "PASS"})
                break
        if items:
            return items
    for response in receipt.get("responses") or []:
        if not isinstance(response, dict):
            continue
        result = response.get("result")
        if not isinstance(result, dict):
            continue
        for item in result.get("evidence") or []:
            if isinstance(item, dict):
                items.append(item)
    return items


def load_evidence_artifact(evidence: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    for item in evidence:
        if item.get("kind") != kind:
            continue
        path = item.get("path")
        if not isinstance(path, str):
            continue
        return load_json(Path(path))
    return {}


if __name__ == "__main__":
    raise SystemExit(main())
