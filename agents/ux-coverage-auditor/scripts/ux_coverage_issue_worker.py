#!/usr/bin/env python3
"""Claim and process one monitor-sparta UX coverage queue item."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping

COMMON_DIR = Path(__file__).resolve().parents[2] / "qra-auditor" / "scripts"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))

from lane_worker_common import (
    build_tau_agent_handoff,
    claim_one,
    update_issue,
    utc_now,
    write_json,
    write_tau_handoff_artifacts,
)

DEFAULT_QUEUE = Path("/mnt/storage12tb/media/agents/shared/monitor-sparta/repair_queue.jsonl")
DEFAULT_RUN_ROOT = Path("/mnt/storage12tb/skills/review-db/outputs/ux-coverage-auditor")
DEFAULT_MEMORY_ROOT = Path(os.environ.get("MONITOR_SPARTA_MEMORY_ROOT", Path.home() / "workspace" / "experiments" / "memory"))
ALLOWED_LANES = {"ux_coverage"}


def source_failures(issue: Mapping[str, Any]) -> list[str]:
    source_check = issue.get("source_check") if isinstance(issue.get("source_check"), Mapping) else {}
    failures = source_check.get("failures")
    if isinstance(failures, list):
        return [str(item) for item in failures]
    return []


def build_repair_plan(issue: Mapping[str, Any], *, run_dir: Path) -> dict[str, Any]:
    source_check = issue.get("source_check") if isinstance(issue.get("source_check"), Mapping) else {}
    slice_ = issue.get("slice") if isinstance(issue.get("slice"), Mapping) else {}
    failures = source_failures(issue)
    checked_files = source_check.get("checked_files") if isinstance(source_check.get("checked_files"), list) else []
    plan = {
        "schema": "ux_coverage_auditor.repair_plan.v1",
        "created_at": utc_now(),
        "issue_id": issue.get("issue_id"),
        "lane": issue.get("lane"),
        "terminal_status": "REVIEW_REQUIRED",
        "mutation_applied": False,
        "database_mutation_allowed": False,
        "react_edits_allowed": False,
        "observed_failure_count": len(failures) or int(slice_.get("observed_guardrail_failures") or issue.get("expected_before_count") or 0),
        "success_condition": issue.get("success_condition") or slice_.get("success_condition"),
        "checked_files": [str(path) for path in checked_files],
        "failures": failures,
        "required_action": slice_.get("required_action") or source_check.get("required_action"),
        "default_repair_sequence": [
            "Inspect the checked Sparta Explorer coverage files named in this plan.",
            "Restore or add page-purpose contract labels for each missing tab/page listed in failures.",
            "Restore rendered tab contract hooks for the missing rendered tabs.",
            "Run the existing Sparta Explorer page-purpose guardrail health check again.",
            "Only after the health check reports zero page-purpose failures, update the monitor-sparta queue issue with proof.",
        ],
        "human_gated_behavior": [
            "React route/component edits are not applied by this worker.",
            "UX/product acceptance remains human-gated unless a separate approved UX apply path exists.",
        ],
        "proof_required_before_done": [
            "fresh monitor-sparta health JSON with sparta_explorer_page_purpose ok=true",
            "receipt path for any React/UX patch",
            "no fake dashboard or static operational status data",
        ],
        "source_check": dict(source_check),
    }
    write_json(run_dir / "ux_repair_plan.json", plan)
    return plan


def run(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    run_id = args.run_id or f"ux-coverage-auditor-{utc_now().replace(':', '').replace('-', '')}"
    run_dir = Path(args.run_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    queue = Path(args.queue)
    issue = claim_one(
        queue,
        owner="ux-coverage-auditor",
        run_id=run_id,
        allowed_lanes=ALLOWED_LANES,
        claim_statuses={"READY", "READY_RETRY", "OPERATOR_REQUIRED"},
        issue_id=args.issue_id,
    )
    if issue is None:
        receipt = {
            "schema": "ux_coverage_auditor.issue_worker.receipt.v1",
            "run_id": run_id,
            "run_dir": str(run_dir),
            "queue_path": str(queue),
            "requested_issue_id": args.issue_id,
            "terminal_status": "NO_CLAIMABLE_ISSUE",
            "mocked": False,
            "live": True,
            "created_at": utc_now(),
        }
        write_json(run_dir / "receipt.json", receipt)
        return 3, receipt

    write_json(run_dir / "issue.json", issue)
    plan = build_repair_plan(issue, run_dir=run_dir)
    queue_update = update_issue(
        queue,
        issue,
        status="OPERATOR_REQUIRED",
        run_id=run_id,
        event="ux_coverage_repair_plan_written",
        fields={
            "blocked_reason": "react_edits_human_gated",
            "dispatch_terminal_status": "REVIEW_REQUIRED",
            "ux_repair_plan_path": str(run_dir / "ux_repair_plan.json"),
            "ux_observed_failure_count": plan.get("observed_failure_count"),
            "operator_action_required": "Review/apply UX repair plan; React edits are human-gated.",
            "resume_condition": "fresh_sparta_explorer_page_purpose_health_ok",
            "mocked": False,
            "live": True,
        },
    )
    tau_handoff = write_tau_handoff_artifacts(
        run_dir,
        filename_stem="ux_coverage_issue_worker",
        handoff=build_tau_agent_handoff(
            previous_subagent="ux-coverage-auditor",
            next_agent="human",
            reason="Subjective React/UX acceptance remains human-gated for this monitor-sparta issue.",
            result_status="REVIEW_REQUIRED",
            result_summary=(
                f"UX coverage worker claimed one issue and wrote a repair plan. "
                f"issue_id={issue.get('issue_id')}, observed_failure_count={plan.get('observed_failure_count')}."
            ),
            context_summary="monitor-sparta queued one UX coverage issue for deterministic monitorability review.",
            rationale="The worker claims one queue issue, writes one repair plan, updates the queue, and exits without applying React edits.",
            stop_condition="A reviewer/operator attaches live Sparta Explorer proof or supersedes the queue issue.",
            issue_id=str(issue.get("issue_id") or ""),
            evidence=[
                str(run_dir / "issue.json"),
                str(run_dir / "ux_repair_plan.json"),
                str(run_dir / "receipt.json"),
            ],
            artifacts=[str(run_dir / "ux_repair_plan.json")],
            required_evidence=[
                "fresh monitor-sparta health JSON with sparta_explorer_page_purpose ok=true",
                "live /test-interactions or browser/CDP proof for affected Sparta Explorer surfaces",
                "receipt path for any React/UX patch",
            ],
        ),
    )
    receipt = {
        "schema": "ux_coverage_auditor.issue_worker.receipt.v1",
        "run_id": run_id,
        "run_dir": str(run_dir),
        "queue_path": str(queue),
        "claimed_issue_id": issue.get("issue_id"),
        "lane": issue.get("lane"),
        "terminal_status": "REVIEW_REQUIRED",
        "tau_handoff": tau_handoff,
        "repair_plan_path": str(run_dir / "ux_repair_plan.json"),
        "queue_update": queue_update,
        "mutation_applied": False,
        "mocked": False,
        "live": True,
        "forbidden_paths": {
            "repair_cycle_invoked": False,
            "health_fix_invoked": False,
            "database_mutation": False,
            "react_edits_applied": False,
        },
    }
    write_json(run_dir / "receipt.json", receipt)
    return 0, receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    run_p = sub.add_parser("run")
    run_p.add_argument("--run-id")
    run_p.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    run_p.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    run_p.add_argument("--memory-root", type=Path, default=DEFAULT_MEMORY_ROOT)
    run_p.add_argument("--issue-id")
    run_p.add_argument("--apply", action="store_true", help="Accepted for supervisor compatibility; ignored because UX edits are human-gated.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "run":
        rc, receipt = run(args)
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return rc
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
