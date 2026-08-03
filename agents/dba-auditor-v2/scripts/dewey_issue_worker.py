#!/usr/bin/env python3
from __future__ import annotations
"""Dewey one-issue worker.

Cron should invoke this worker.  It reads monitor-sparta's durable repair queue,
claims exactly one Dewey-owned issue, runs exactly one bounded lane slice, writes
receipt.json, updates the queue, and exits.

This file is the replacement for using dewey_overnight_run.py as a broad repair
loop.  A compatibility wrapper may still call this worker, but all automatic
repair attempts must go through the issue-claim path here.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
_COMMON_DIR = Path(__file__).resolve().parents[2] / "qra-auditor" / "scripts"
if str(_COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(_COMMON_DIR))

from dewey_lane_runner import run_lane, write_json
from dewey_repair_queue import (
    claim_one,
    default_queue_path,
    load_latest,
    select_next,
    summarize,
    update_issue,
    utc_now,
    utc_stamp,
)
from lane_worker_common import build_tau_agent_handoff, write_tau_handoff_artifacts

DEFAULT_MEMORY_REPO_ROOT = "/home/graham/workspace/experiments/memory"
DEFAULT_AGENT_SKILLS_ROOT = "/home/graham/workspace/experiments/agent-skills"
DEFAULT_RUN_ROOT = "/mnt/storage12tb/skills/review-db/outputs/dewey-sessions"
DEFAULT_HEALTH_TIMEOUT_S = 300
EXIT_NO_READY_ISSUE = 3
EXIT_OPERATOR_REQUIRED = 10
EXIT_TRANSIENT_BLOCKER = 11
EXIT_FAILED_NEEDS_REVIEW = 12


def bootstrap_queue_if_needed(
    *,
    queue_path: Path,
    memory_root: Path,
    run_dir: Path,
    limit: int,
    health_timeout_s: int,
) -> dict[str, Any]:
    latest = load_latest(queue_path)
    if select_next(latest):
        return {"bootstrapped": False, "reason": "ready_issue_already_exists", "queued": 0}
    return {
        "bootstrapped": False,
        "queued": 0,
        "reason": "queue_construction_owned_by_monitor_sparta",
        "expected_builder": str(memory_root / "scripts" / "validation" / "monitor_sparta_repair_queue.py"),
    }


def queue_status_from_lane_result(result: Mapping[str, Any]) -> str:
    terminal = str(result.get("terminal_status") or "")
    if terminal == "DRY_RUN_PASS":
        return "DRY_RUN_DONE"
    if terminal == "DONE":
        return "DONE"
    if terminal == "BLOCKED_TRANSIENT_SERVICE":
        return "READY_RETRY"
    if terminal == "BLOCKED_TIMEOUT":
        return "READY_RETRY"
    if terminal == "OPERATOR_REQUIRED":
        return "OPERATOR_REQUIRED"
    return "FAILED_NEEDS_REVIEW"


def exit_code_from_status(status: str) -> int:
    if status in {"DONE", "DRY_RUN_DONE"}:
        return 0
    if status == "OPERATOR_REQUIRED":
        return EXIT_OPERATOR_REQUIRED
    if status == "READY_RETRY":
        return EXIT_TRANSIENT_BLOCKER
    return EXIT_FAILED_NEEDS_REVIEW


def lane_command_modes(lane_result: Mapping[str, Any] | None) -> tuple[bool, bool]:
    """Return (live, mocked) from concrete command receipts.

    A read-only scanner/canary is live when at least one command actually ran.
    A command-preview dry run is mocked when every command is marked dry_run.
    """
    commands = lane_result.get("commands") if isinstance(lane_result, Mapping) else None
    if not isinstance(commands, list) or not commands:
        return False, False
    dry_flags = [bool(cmd.get("dry_run")) for cmd in commands if isinstance(cmd, Mapping)]
    if not dry_flags:
        return False, False
    return any(not flag for flag in dry_flags), all(dry_flags)


def build_receipt(
    *,
    run_id: str,
    run_dir: Path,
    queue_path: Path,
    issue: Mapping[str, Any] | None,
    lane_result: Mapping[str, Any] | None,
    queue_update: Mapping[str, Any] | None,
    bootstrap: Mapping[str, Any] | None,
    terminal_status: str,
    started_at: str,
    finished_at: str,
    apply: bool,
) -> dict[str, Any]:
    lane = issue.get("lane") if issue else None
    commands: list[Any] = []
    if isinstance(lane_result, Mapping) and isinstance(lane_result.get("commands"), list):
        commands = lane_result["commands"]
    repair_cycle_commands = [cmd for cmd in commands if "repair-cycle" in " ".join(str(x) for x in (cmd.get("cmd") if isinstance(cmd, Mapping) else []))]
    return {
        "schema": "dewey.issue_worker.receipt.v1",
        "agent": "dba-auditor",
        "run_id": run_id,
        "run_dir": str(run_dir),
        "queue_path": str(queue_path),
        "started_at": started_at,
        "finished_at": finished_at,
        "terminal_status": terminal_status,
        "claimed_issue_id": issue.get("issue_id") if issue else None,
        "lane": lane,
        "dimension": issue.get("dimension") if issue else None,
        "collection": issue.get("collection") if issue else None,
        "slice": issue.get("slice") if issue else None,
        "apply_requested": apply,
        "mutation_applied": bool(lane_result and lane_result.get("mutation_applied")),
        "proof_ok": bool(lane_result and lane_result.get("proof_ok")),
        "before_count": lane_result.get("before_count") if isinstance(lane_result, Mapping) else None,
        "after_count": lane_result.get("after_count") if isinstance(lane_result, Mapping) else None,
        "changed_count": lane_result.get("changed_count") if isinstance(lane_result, Mapping) else None,
        "rollback_manifest": lane_result.get("rollback_manifest") if isinstance(lane_result, Mapping) else None,
        "rollback_records": lane_result.get("rollback_records") if isinstance(lane_result, Mapping) else None,
        "preflight": dict(lane_result.get("preflight") or {}) if isinstance(lane_result, Mapping) else {},
        "proof": dict(lane_result.get("proof") or {}) if isinstance(lane_result, Mapping) else {},
        "ran_more_than_one_lane": False,
        "ran_repair_cycle": bool(repair_cycle_commands),
        "repair_cycle_commands": repair_cycle_commands,
        "bootstrap": dict(bootstrap or {}),
        "lane_result": dict(lane_result or {}),
        "queue_update": dict(queue_update or {}),
        "artifact_paths": {
            "issue": str(run_dir / "issue.json") if issue else None,
            "lane_result": str(run_dir / "lane_result.json") if lane_result else None,
            "receipt": str(run_dir / "receipt.json"),
            "nightly_receipt_compat": str(run_dir / "nightly_receipt.json"),
        },
        "receipt_authority": {
            "authoritative_receipt": str(run_dir / "receipt.json"),
            "nightly_receipt_compat": str(run_dir / "nightly_receipt.json"),
            "nightly_receipt_compat_is_alias": True,
        },
        "honesty": {
            "mocked": lane_command_modes(lane_result)[1],
            "live": lane_command_modes(lane_result)[0],
            "does_not_prove": [
                "full monitor-sparta green",
                "all QRA coverage closed",
                "human review of generated QRA content",
            ],
        },
    }


def run_one_issue(
    *,
    run_id: str,
    run_root: Path,
    queue_path: Path,
    memory_root: Path,
    agent_skills_root: Path,
    apply: bool,
    bootstrap: bool,
    bootstrap_limit: int,
    timeout_s: int,
    health_timeout_s: int,
    heartbeat_s: int,
) -> tuple[int, dict[str, Any]]:
    started_at = utc_now()
    run_dir = run_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    bootstrap_result: Mapping[str, Any] | None = None
    if bootstrap:
        try:
            bootstrap_result = bootstrap_queue_if_needed(
                queue_path=queue_path,
                memory_root=memory_root,
                run_dir=run_dir,
                limit=bootstrap_limit,
                health_timeout_s=health_timeout_s,
            )
            write_json(run_dir / "bootstrap.json", bootstrap_result)
        except Exception as exc:  # noqa: BLE001 - bootstrapping is best-effort detection only
            bootstrap_result = {"bootstrapped": False, "reason": f"bootstrap_error: {exc}"}
            write_json(run_dir / "bootstrap.json", bootstrap_result)

    issue = claim_one(queue_path, run_id=run_id, claimed_by="dba-auditor")
    if issue is None:
        finished_at = utc_now()
        receipt = build_receipt(
            run_id=run_id,
            run_dir=run_dir,
            queue_path=queue_path,
            issue=None,
            lane_result=None,
            queue_update=None,
            bootstrap=bootstrap_result,
            terminal_status="NO_READY_ISSUE",
            started_at=started_at,
            finished_at=finished_at,
            apply=apply,
        )
        write_json(run_dir / "receipt.json", receipt)
        write_json(run_dir / "nightly_receipt.json", receipt)
        return EXIT_NO_READY_ISSUE, receipt

    write_json(run_dir / "issue.json", issue)
    lane_result = run_lane(
        issue,
        run_dir=run_dir,
        memory_root=memory_root,
        agent_skills_root=agent_skills_root,
        apply=apply,
        timeout_s=timeout_s,
        heartbeat_s=heartbeat_s,
    )
    queue_status = queue_status_from_lane_result(lane_result)
    queue_update = update_issue(queue_path, issue, status=queue_status, result=lane_result)
    finished_at = utc_now()
    receipt = build_receipt(
        run_id=run_id,
        run_dir=run_dir,
        queue_path=queue_path,
        issue=issue,
        lane_result=lane_result,
        queue_update=queue_update,
        bootstrap=bootstrap_result,
        terminal_status=queue_status,
        started_at=started_at,
        finished_at=finished_at,
        apply=apply,
    )
    tau_handoff = write_tau_handoff_artifacts(
        run_dir,
        filename_stem="dewey_issue_worker",
        handoff=build_tau_agent_handoff(
            previous_subagent="dba-auditor-v2",
            next_agent="monitor-sparta-supervisor" if queue_status in {"DONE", "DRY_RUN_DONE", "READY_RETRY"} else "human",
            reason=(
                "Supervisor/router should select the next monitor-sparta issue."
                if queue_status in {"DONE", "DRY_RUN_DONE", "READY_RETRY"}
                else "Human/operator review is required before Dewey continues this lane."
            ),
            result_status=queue_status,
            result_summary=(
                f"Dewey ran one issue/lane. lane={issue.get('lane')}, "
                f"collection={issue.get('collection')}, proof_ok={bool(lane_result.get('proof_ok')) if isinstance(lane_result, Mapping) else False}, "
                f"mutation_applied={bool(lane_result.get('mutation_applied')) if isinstance(lane_result, Mapping) else False}."
            ),
            context_summary="monitor-sparta queued one deterministic DBA repair issue for Dewey.",
            rationale="Dewey claims one queue issue, runs one memory-owned primitive lane, writes one receipt, updates one issue, and exits.",
            stop_condition="monitor-sparta supervisor consumes the queue update and selects the next eligible issue.",
            issue_id=str(issue.get("issue_id") or ""),
            evidence=[
                str(run_dir / "issue.json"),
                str(run_dir / "lane_result.json"),
                str(run_dir / "receipt.json"),
            ],
            artifacts=[
                str(run_dir / "dewey_evidence_summary.json"),
            ],
            required_evidence=[
                "receipt.json",
                "lane_result.json",
                "queue update",
                "rollback manifest when mutation_applied=true",
            ],
        ),
    )
    receipt["tau_handoff"] = tau_handoff
    write_json(run_dir / "receipt.json", receipt)
    write_json(run_dir / "nightly_receipt.json", receipt)
    write_json(run_dir / "dewey_evidence_summary.json", {
        "schema": "dewey.evidence_summary.v1",
        "run_id": run_id,
        "terminal_status": queue_status,
        "claimed_issue_id": issue.get("issue_id"),
        "lane": issue.get("lane"),
        "collection": issue.get("collection"),
        "scope": lane_result.get("scope") if isinstance(lane_result, Mapping) else None,
        "bulk_embedding_contract": lane_result.get("bulk_embedding_contract") if isinstance(lane_result, Mapping) else None,
        "proof_ok": bool(lane_result.get("proof_ok")) if isinstance(lane_result, Mapping) else False,
        "before_count": lane_result.get("before_count") if isinstance(lane_result, Mapping) else None,
        "after_count": lane_result.get("after_count") if isinstance(lane_result, Mapping) else None,
        "changed_count": lane_result.get("changed_count") if isinstance(lane_result, Mapping) else None,
        "rollback_manifest": lane_result.get("rollback_manifest") if isinstance(lane_result, Mapping) else None,
        "queue_path": str(queue_path),
        "receipt_path": str(run_dir / "receipt.json"),
        "updated_at": finished_at,
    })
    return exit_code_from_status(queue_status), receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Claim and run exactly one monitor-sparta repair issue")
    p_run.add_argument("--run-id", default=f"dewey-{utc_stamp()}")
    p_run.add_argument("--run-root", type=Path, default=Path(os.environ.get("DEWEY_SESSION_BASE") or os.environ.get("DEWEY_SESSION_ROOT") or DEFAULT_RUN_ROOT))
    p_run.add_argument("--queue", type=Path, default=default_queue_path())
    p_run.add_argument("--memory-repo-root", type=Path, default=Path(os.environ.get("MEMORY_ROOT") or os.environ.get("MEMORY_REPO_ROOT") or DEFAULT_MEMORY_REPO_ROOT))
    p_run.add_argument("--agent-skills-root", type=Path, default=Path(os.environ.get("AGENT_SKILLS_ROOT") or DEFAULT_AGENT_SKILLS_ROOT))
    p_run.add_argument("--apply", action="store_true")
    p_run.add_argument("--no-bootstrap", action="store_true", help="Do not run read-only health fallback when queue is empty")
    p_run.add_argument("--bootstrap-limit", type=int, default=int(os.environ.get("DEWEY_BOOTSTRAP_LIMIT", "0")))
    p_run.add_argument("--timeout-s", type=int, default=int(os.environ.get("DEWEY_LANE_TIMEOUT_S", os.environ.get("DEWEY_REPAIR_TIMEOUT_S", "7200"))))
    p_run.add_argument("--health-timeout-s", type=int, default=int(os.environ.get("DEWEY_HEALTH_JSON_TIMEOUT_S", str(DEFAULT_HEALTH_TIMEOUT_S))))
    p_run.add_argument("--heartbeat-s", type=int, default=int(os.environ.get("DEWEY_SUBPROCESS_HEARTBEAT_S", "60")))
    p_run.add_argument("--json", action="store_true")

    p_status = sub.add_parser("status")
    p_status.add_argument("--queue", type=Path, default=default_queue_path())
    p_status.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    if args.cmd == "status":
        status = summarize(args.queue)
        print(json.dumps(status, indent=2, sort_keys=True))
        return 0

    if args.cmd == "run":
        rc, receipt = run_one_issue(
            run_id=args.run_id,
            run_root=args.run_root,
            queue_path=args.queue,
            memory_root=args.memory_repo_root,
            agent_skills_root=args.agent_skills_root,
            apply=bool(args.apply),
            bootstrap=not bool(args.no_bootstrap),
            bootstrap_limit=args.bootstrap_limit,
            timeout_s=args.timeout_s,
            health_timeout_s=args.health_timeout_s,
            heartbeat_s=args.heartbeat_s,
        )
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return rc

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
