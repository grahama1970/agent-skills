#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
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
DEFAULT_RUN_ROOT = Path("/mnt/storage12tb/skills/review-db/outputs/ops-arango")
DEFAULT_MEMORY_ROOT = Path("/home/graham/workspace/experiments/memory")
ALLOWED_LANES = {"backup_freshness"}


def backup_plan(issue: Mapping[str, Any], *, run_dir: Path) -> dict[str, Any]:
    slice_ = issue.get("slice") if isinstance(issue.get("slice"), Mapping) else {}
    source_check = issue.get("source_check") if isinstance(issue.get("source_check"), Mapping) else {}
    plan = {
        "schema": "ops_arango.backup_freshness_plan.v1",
        "created_at": utc_now(),
        "issue_id": issue.get("issue_id"),
        "lane": issue.get("lane"),
        "terminal_status": "OPERATOR_REQUIRED",
        "mutation_applied": False,
        "backup_started": False,
        "backup_base": slice_.get("backup_base") or source_check.get("backup_base"),
        "latest_backup_dir": slice_.get("latest_backup_dir") or source_check.get("latest_backup_dir"),
        "receipt_path": slice_.get("receipt_path") or source_check.get("receipt_path"),
        "age_hours": slice_.get("age_hours") or source_check.get("age_hours"),
        "max_age_hours": slice_.get("max_age_hours") or source_check.get("max_age_hours"),
        "success_condition": issue.get("success_condition") or slice_.get("success_condition"),
        "approved_manual_command": str(DEFAULT_MEMORY_ROOT / "scripts" / "overnight_backup.sh"),
        "policy": [
            "Do not run ArangoDB backup inside every monitor-sparta tick.",
            "Use the approved ops-arango/overnight backup path.",
            "At most one explicit backup lane should run per day unless the human requests otherwise.",
        ],
        "apply_preconditions": [
            "SPARTA_MONITOR_MUTATION_ENABLED=1",
            "operator or scheduler selected backup_freshness lane explicitly",
            "no fresh backup receipt already satisfies max_age_hours",
        ],
        "proof_required_before_done": [
            "latest_backup_receipt.json exists",
            "backup_age_hours_lte success condition is true",
            "dump_json exists under backup_dir",
            "sparta_controls_at_backup is nonzero",
        ],
        "source_check": dict(source_check),
    }
    write_json(run_dir / "backup_freshness_plan.json", plan)
    return plan


def issue_already_satisfies_backup_freshness(issue: Mapping[str, Any]) -> bool:
    slice_ = issue.get("slice") if isinstance(issue.get("slice"), Mapping) else {}
    source_check = issue.get("source_check") if isinstance(issue.get("source_check"), Mapping) else {}
    success_condition = issue.get("success_condition") if isinstance(issue.get("success_condition"), Mapping) else {}
    age_raw = slice_.get("age_hours", source_check.get("age_hours"))
    max_raw = (
        success_condition.get("backup_age_hours_lte")
        or slice_.get("max_age_hours")
        or source_check.get("max_age_hours")
    )
    try:
        age_hours = float(age_raw)
        max_age_hours = float(max_raw)
    except (TypeError, ValueError):
        return False
    return age_hours <= max_age_hours


def run_backup(*, run_dir: Path, timeout_s: int) -> dict[str, Any]:
    script = DEFAULT_MEMORY_ROOT / "scripts" / "overnight_backup.sh"
    stdout_path = run_dir / "overnight_backup.stdout.log"
    stderr_path = run_dir / "overnight_backup.stderr.log"
    if os.environ.get("SPARTA_MONITOR_MUTATION_ENABLED") != "1":
        return {
            "ok": False,
            "terminal_status": "APPLY_ENV_NOT_ENABLED",
            "cmd": [str(script)],
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
        }
    proc = subprocess.run([str(script)], cwd=str(DEFAULT_MEMORY_ROOT), text=True, capture_output=True, check=False, timeout=timeout_s)
    stdout_path.write_text(proc.stdout or "", encoding="utf-8")
    stderr_path.write_text(proc.stderr or "", encoding="utf-8")
    receipt_path = Path("/mnt/storage12tb/backups/arangodb/latest_backup_receipt.json")
    receipt: dict[str, Any] = {}
    if receipt_path.exists():
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            receipt = {"parse_error": f"{type(exc).__name__}: {exc}"}
    return {
        "ok": proc.returncode == 0 and bool(receipt.get("backup_dir")),
        "terminal_status": "DONE" if proc.returncode == 0 and bool(receipt.get("backup_dir")) else "BACKUP_FAILED",
        "cmd": [str(script)],
        "exit_code": proc.returncode,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "stdout_tail": (proc.stdout or "")[-4000:],
        "stderr_tail": (proc.stderr or "")[-4000:],
        "latest_backup_receipt_path": str(receipt_path),
        "latest_backup_receipt": receipt,
    }


def run(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    run_id = args.run_id or f"ops-arango-{utc_now().replace(':', '').replace('-', '')}"
    run_dir = Path(args.run_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    queue = Path(args.queue)
    issue = claim_one(
        queue,
        owner="ops-arango",
        run_id=run_id,
        allowed_lanes=ALLOWED_LANES,
        claim_statuses={"READY", "READY_RETRY", "OPERATOR_REQUIRED"},
        issue_id=args.issue_id,
    )
    if issue is None:
        receipt = {
            "schema": "ops_arango.issue_worker.receipt.v1",
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
    plan = backup_plan(issue, run_dir=run_dir)
    backup_result: dict[str, Any] | None = None
    already_satisfied = issue_already_satisfies_backup_freshness(issue)
    if already_satisfied:
        queue_update = update_issue(
            queue,
            issue,
            status="DONE",
            run_id=run_id,
            event="ops_arango_backup_freshness_already_satisfied",
            fields={
                "blocked_reason": None,
                "dispatch_terminal_status": "DONE",
                "backup_freshness_plan_path": str(run_dir / "backup_freshness_plan.json"),
                "mutation_applied": False,
                "already_satisfied": True,
                "mocked": False,
                "live": True,
            },
        )
    elif args.apply:
        backup_result = run_backup(run_dir=run_dir, timeout_s=args.timeout_s)
        if backup_result.get("terminal_status") == "DONE":
            queue_update = update_issue(
                queue,
                issue,
                status="DONE",
                run_id=run_id,
                event="ops_arango_backup_freshness_restored",
                fields={
                    "blocked_reason": None,
                    "dispatch_terminal_status": "DONE",
                    "backup_freshness_plan_path": str(run_dir / "backup_freshness_plan.json"),
                    "latest_backup_receipt_path": backup_result.get("latest_backup_receipt_path"),
                    "mutation_applied": True,
                    "mocked": False,
                    "live": True,
                },
            )
        else:
            queue_update = update_issue(
                queue,
                issue,
                status="OPERATOR_REQUIRED",
                run_id=run_id,
                event="ops_arango_backup_apply_failed",
                fields={
                    "blocked_reason": str(backup_result.get("terminal_status") or "backup_apply_failed"),
                    "dispatch_terminal_status": str(backup_result.get("terminal_status") or "backup_apply_failed"),
                    "backup_freshness_plan_path": str(run_dir / "backup_freshness_plan.json"),
                    "operator_action_required": "Inspect backup logs and rerun approved ops-arango backup path.",
                    "resume_condition": "latest_backup_receipt_satisfies_backup_age_hours_lte",
                    "mutation_applied": False,
                    "mocked": False,
                    "live": True,
                },
            )
    else:
        queue_update = update_issue(
            queue,
            issue,
            status="OPERATOR_REQUIRED",
            run_id=run_id,
            event="ops_arango_backup_policy_handoff_written",
            fields={
                "blocked_reason": "backup_policy_handoff_required",
                "dispatch_terminal_status": "OPERATOR_REQUIRED",
                "backup_freshness_plan_path": str(run_dir / "backup_freshness_plan.json"),
                "operator_action_required": "Run the approved nightly/ops-arango backup path or explicitly dispatch this lane with --apply.",
                "resume_condition": "latest_backup_receipt_satisfies_backup_age_hours_lte",
                "mutation_applied": False,
                "mocked": False,
                "live": True,
            },
        )
    terminal_status = "DONE" if already_satisfied or (backup_result and backup_result.get("terminal_status") == "DONE") else "OPERATOR_REQUIRED"
    tau_handoff = write_tau_handoff_artifacts(
        run_dir,
        filename_stem="ops_arango_issue_worker",
        handoff=build_tau_agent_handoff(
            previous_subagent="ops-arango",
            next_agent="monitor-sparta-supervisor" if terminal_status == "DONE" else "human",
            reason=(
                "Supervisor/router should select the next monitor-sparta issue."
                if terminal_status == "DONE"
                else "An operator must run or approve the backup path before this issue can close."
            ),
            result_status=terminal_status,
            result_summary=(
                f"Ops Arango claimed one backup freshness issue. issue_id={issue.get('issue_id')}, "
                f"backup_started={bool(backup_result)}, already_satisfied={already_satisfied}, "
                f"mutation_applied={bool(backup_result and backup_result.get('terminal_status') == 'DONE')}."
            ),
            context_summary="monitor-sparta queued one backup freshness issue for ops-arango.",
            rationale="The worker claims one queue issue, writes a backup freshness plan, optionally runs the approved backup command, updates the queue, and exits.",
            stop_condition="Backup freshness proof is attached or the queue issue remains operator-required with a resume condition.",
            issue_id=str(issue.get("issue_id") or ""),
            evidence=[
                str(run_dir / "issue.json"),
                str(run_dir / "backup_freshness_plan.json"),
                str(run_dir / "receipt.json"),
            ],
            artifacts=[str(run_dir / "backup_freshness_plan.json")],
            required_evidence=[
                "latest_backup_receipt.json exists",
                "backup_age_hours_lte success condition is true",
                "dump_json exists under backup_dir",
                "sparta_controls_at_backup is nonzero",
            ],
        ),
    )
    receipt = {
        "schema": "ops_arango.issue_worker.receipt.v1",
        "run_id": run_id,
        "run_dir": str(run_dir),
        "queue_path": str(queue),
        "claimed_issue_id": issue.get("issue_id"),
        "lane": issue.get("lane"),
        "terminal_status": terminal_status,
        "tau_handoff": tau_handoff,
        "backup_freshness_plan_path": str(run_dir / "backup_freshness_plan.json"),
        "backup_result": backup_result,
        "queue_update": queue_update,
        "mutation_applied": bool(backup_result and backup_result.get("terminal_status") == "DONE"),
        "already_satisfied": already_satisfied,
        "mocked": False,
        "live": True,
        "forbidden_paths": {
            "repair_cycle_invoked": False,
            "health_fix_invoked": False,
            "database_mutation": bool(backup_result and backup_result.get("terminal_status") == "DONE"),
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
    run_p.add_argument("--apply", action="store_true")
    run_p.add_argument("--timeout-s", type=int, default=7200)
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
