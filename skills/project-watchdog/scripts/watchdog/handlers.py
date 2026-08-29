"""Bounded per-issue dispatch handlers.

Purpose
    Execute exactly one bounded unit of work for one leased GitHub issue, then
    hand back a receipt fragment. Handlers never loop, never retry, and never
    decide what to work on next — ``registry`` selects, ``commands`` sequences.

Inputs
    A run id, a receipt directory, the registered project entry, and the issue
    payload returned by ``gh issue list --json``.

Outputs
    A result dictionary appended to the tick receipt's ``handled_issues`` list,
    plus artifacts written under the receipt directory.

Failure modes
    - Malformed issue directives return ``status=BLOCKED`` without mutating
      GitHub.
    - A failed bounded command relabels the issue ``agent-blocked`` and returns
      ``status=NEEDS_ATTENTION`` so cron does not retry it every minute.
    - Every path is derived from the registered project worktree, so a handler
      cannot act on a repository it was not dispatched for.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

from loguru import logger

from . import config, github, registry
from .core import iso_now, log_event, run_cmd, write_json
from .issue_fields import (
    parse_bool,
    parse_goal_hash,
    parse_issue_fields,
    parse_positive_int,
    repo_relative_existing_path,
)
from .registry import project_repo, project_worktree, worktree_readiness


def handle_issue(
    run_id: str,
    receipt_dir: Path,
    project: dict[str, Any],
    issue: dict[str, Any],
    *,
    apply: bool,
) -> dict[str, Any]:
    """Route one issue to the handler named by its ``watchdog_action``."""
    action = issue.get("watchdog_action")
    if action == "tau_handoff_dispatch":
        return handle_tau_handoff_dispatch(run_id, receipt_dir, project, issue, apply=apply)
    if action == "add_tau_coder_command_spec":
        return handle_tau_coder_spec(run_id, receipt_dir, project, issue, apply=apply)
    if action == "ticket_repair":
        return handle_ticket_repair(run_id, receipt_dir, project, issue, apply=apply)
    return {
        "project_id": project.get("project_id"),
        "issue_number": int(issue["number"]),
        "issue_url": str(issue.get("url", "")),
        "action": action,
        "ok": False,
        "status": "BLOCKED",
        "summary": f"no handler registered for watchdog_action={action!r}",
        "commands": [],
        "artifacts": [],
    }


def _new_result(project: dict[str, Any], issue: dict[str, Any], action: str) -> dict[str, Any]:
    return {
        "project_id": project.get("project_id"),
        "repo": project_repo(project),
        "issue_number": int(issue["number"]),
        "issue_url": str(issue["url"]),
        "selected_agent": None,
        "action": action,
        "ok": False,
        "commands": [],
        "artifacts": [],
    }


def handle_tau_handoff_dispatch(
    run_id: str,
    receipt_dir: Path,
    project: dict[str, Any],
    issue: dict[str, Any],
    *,
    apply: bool,
) -> dict[str, Any]:
    """Run one bounded ``tau handoff-command-loop`` tick from an issue directive."""
    repo = project_repo(project)
    worktree = project_worktree(project)
    issue_number = int(issue["number"])
    log_event(run_id, "handle_handoff_dispatch_start", issue=issue_number, repo=repo)
    result = _new_result(project, issue, "tau_handoff_dispatch")
    result["selected_agent"] = "tau-handoff-dispatch"

    try:
        fields = parse_issue_fields(issue.get("body") or "")
        if "start" not in fields:
            raise ValueError("issue directive is missing the required 'start' field")
        start_path = repo_relative_existing_path(fields["start"], worktree=worktree)
        max_steps = parse_positive_int(fields.get("max_steps", "1"), field="max_steps")
        active_goal_hash = parse_goal_hash(
            fields.get("active_goal_hash", config.TAU_ACTIVE_GOAL_HASH)
        )
        apply_transport = parse_bool(
            fields.get("apply_transport", "false"), field="apply_transport"
        )
    except ValueError as exc:
        result.update({"ok": False, "status": "BLOCKED", "summary": str(exc)})
        log_event(run_id, "handle_handoff_dispatch_blocked", issue=issue_number, error=str(exc))
        return result

    resolved = {
        "schema": "agent_skills.project_watchdog.tau_handoff_dispatch_inputs.v1",
        "issue": f"issue#{issue_number}",
        "issue_url": result["issue_url"],
        "repo": repo,
        "start": str(start_path.relative_to(worktree.resolve())),
        "max_steps": max_steps,
        "active_goal_hash": active_goal_hash,
        "apply_transport": apply_transport,
    }
    resolved_path = receipt_dir / "tau-handoff-dispatch-inputs.json"
    write_json(resolved_path, resolved)
    result["artifacts"].append(str(resolved_path))

    if not apply:
        result.update(
            {"ok": True, "status": "DRY_RUN", "summary": "would run Tau handoff dispatch"}
        )
        return result

    result["commands"].append(
        github.issue_comment(
            repo,
            issue_number,
            github.watchdog_comment(
                "Lease acquired",
                {
                    "schema": "agent_skills.project_watchdog.lease.v1",
                    "acquired_at": iso_now(),
                    "run_id": run_id,
                    "issue": f"issue#{issue_number}",
                    "selected_agent": "tau-handoff-dispatch",
                    "action": "tau_handoff_dispatch",
                    "inputs": resolved,
                },
            ),
        )
    )
    if not acquire_lease(run_id, result, repo, issue_number):
        return result

    uv_bin = config.resolve_uv_bin()
    loop_dir = receipt_dir / "tau-command-loop"
    loop_receipt = loop_dir / "command-loop-receipt.json"
    loop_result = run_cmd(
        [
            uv_bin,
            "run",
            "tau",
            "handoff-command-loop",
            "--start",
            str(start_path),
            "--receipt-dir",
            str(loop_dir),
            "--agents-root",
            str(config.agents_root()),
            "--command-spec-root",
            str(worktree / "experiments/goal-locked-subagents/agent-command-specs"),
            "--active-goal-hash",
            active_goal_hash,
            "--max-steps",
            str(max_steps),
        ],
        cwd=worktree,
        timeout_s=120,
    )
    result["commands"].append(loop_result)
    result["artifacts"].append(str(loop_receipt))

    transport_path = receipt_dir / "tau-github-transport.json"
    transport_command = [
        uv_bin,
        "run",
        "tau",
        "handoff-command-loop-github-transport",
        str(loop_receipt),
        "--receipt",
        str(transport_path),
    ]
    if apply_transport:
        transport_command.append("--apply")
    transport_result = run_cmd(transport_command, cwd=worktree, timeout_s=120)
    result["commands"].append(transport_result)
    result["artifacts"].append(str(transport_path))

    if loop_result["exit_code"] != 0 or transport_result["exit_code"] != 0:
        result.update(
            {"ok": False, "status": "NEEDS_ATTENTION", "summary": "Tau handoff dispatch failed"}
        )
        result["commands"].append(
            github.issue_edit(
                repo, issue_number, add=[config.BLOCKED_LABEL], remove=[config.LEASE_LABEL]
            )
        )
        log_event(run_id, "handle_handoff_dispatch_failed", issue=issue_number)
        return result

    result["commands"].append(
        github.issue_comment(
            repo,
            issue_number,
            github.watchdog_comment(
                "Tau handoff dispatch evidence",
                {
                    "schema": "agent_skills.project_watchdog.tau_handoff_dispatch_receipt.v1",
                    "run_id": run_id,
                    "issue": f"issue#{issue_number}",
                    "repo": repo,
                    "inputs": resolved,
                    "loop_exit_code": loop_result["exit_code"],
                    "transport_exit_code": transport_result["exit_code"],
                    "command_loop_receipt": str(loop_receipt),
                    "github_transport_receipt": str(transport_path),
                    "mocked": False,
                    "live": True,
                    "scope": (
                        "Runs one bounded Tau handoff command-loop tick from a GitHub issue "
                        "and renders or applies terminal Tau GitHub transport."
                    ),
                },
            ),
        )
    )
    result["commands"].append(
        github.issue_edit(
            repo,
            issue_number,
            add=[config.DONE_LABEL],
            remove=[config.LEASE_LABEL, "next:coder", "next:reviewer", "executor:local"],
        )
    )
    close = github.issue_close(repo, issue_number)
    result["commands"].append(close)
    result.update(
        {
            "ok": close["exit_code"] == 0,
            "status": "COMPLETED",
            "summary": "Tau handoff dispatch executed",
        }
    )
    log_event(run_id, "handle_handoff_dispatch_finish", issue=issue_number, ok=result["ok"])
    return result


def handle_tau_coder_spec(
    run_id: str,
    receipt_dir: Path,
    project: dict[str, Any],
    issue: dict[str, Any],
    *,
    apply: bool,
) -> dict[str, Any]:
    """Write the Tau coder command-spec overlay and prove one command-loop route."""
    repo = project_repo(project)
    worktree = project_worktree(project)
    issue_number = int(issue["number"])
    log_event(run_id, "handle_coder_spec_start", issue=issue_number, repo=repo)
    result = _new_result(project, issue, "add_tau_coder_command_spec")
    result["selected_agent"] = "coder"

    if not apply:
        result.update({"ok": True, "status": "DRY_RUN", "summary": "would add coder command spec"})
        return result

    result["commands"].append(
        github.issue_comment(
            repo,
            issue_number,
            github.watchdog_comment(
                "Lease acquired",
                {
                    "schema": "agent_skills.project_watchdog.lease.v1",
                    "acquired_at": iso_now(),
                    "run_id": run_id,
                    "issue": f"issue#{issue_number}",
                    "selected_agent": "coder",
                    "action": "add_tau_coder_command_spec",
                },
            ),
        )
    )
    if not acquire_lease(run_id, result, repo, issue_number):
        return result

    uv_bin = config.resolve_uv_bin()
    coder_spec = tau_coder_spec_path(worktree)
    write_json(coder_spec, tau_coder_command_spec(uv_bin))
    result["artifacts"].append(str(coder_spec))

    start_path = receipt_dir / "tau-coder-start-handoff.json"
    write_json(
        start_path,
        tau_coder_start_handoff(repo, issue_number, result["issue_url"], coder_spec),
    )
    result["artifacts"].append(str(start_path))

    loop_dir = receipt_dir / "tau-command-loop"
    loop_result = run_cmd(
        [
            uv_bin,
            "run",
            "tau",
            "handoff-command-loop",
            "--start",
            str(start_path),
            "--receipt-dir",
            str(loop_dir),
            "--agents-root",
            str(config.agents_root()),
            "--command-spec-root",
            str(worktree / "experiments/goal-locked-subagents/agent-command-specs"),
            "--active-goal-hash",
            config.TAU_ACTIVE_GOAL_HASH,
            "--max-steps",
            "2",
        ],
        cwd=worktree,
        timeout_s=120,
    )
    result["commands"].append(loop_result)
    result["artifacts"].append(str(loop_dir / "command-loop-receipt.json"))

    targeted = run_cmd(
        [
            uv_bin,
            "run",
            "--project",
            str(worktree),
            "pytest",
            "-q",
            "tests/test_cli.py::test_cli_handoff_agent_adapter_emits_tau_handoff",
            "tests/test_subagent_receipt.py"
            "::test_headless_subagent_receipt_import_does_not_require_textual",
        ],
        cwd=worktree,
        timeout_s=120,
    )
    result["commands"].append(targeted)
    result["commands"].append(run_cmd(["git", "status", "--short"], cwd=worktree))

    if loop_result["exit_code"] != 0 or targeted["exit_code"] != 0:
        result.update(
            {"ok": False, "status": "NEEDS_ATTENTION", "summary": "repair command failed"}
        )
        result["commands"].append(
            github.issue_edit(
                repo, issue_number, add=[config.BLOCKED_LABEL], remove=[config.LEASE_LABEL]
            )
        )
        log_event(run_id, "handle_coder_spec_failed", issue=issue_number)
        return result

    relative_spec = coder_spec.relative_to(worktree.resolve())
    run_cmd(["git", "add", str(relative_spec)], cwd=worktree)
    commit = run_cmd(["git", "commit", "-m", "Add Tau coder command spec overlay"], cwd=worktree)
    result["commands"].append(commit)
    if commit["exit_code"] == 0:
        result["commands"].append(
            run_cmd(["git", "push", "origin", "HEAD"], cwd=worktree, timeout_s=120)
        )

    result["commands"].append(
        github.issue_comment(
            repo,
            issue_number,
            github.watchdog_comment(
                "Repair evidence",
                {
                    "schema": "agent_skills.project_watchdog.repair_receipt.v1",
                    "run_id": run_id,
                    "issue": f"issue#{issue_number}",
                    "repo": repo,
                    "selected_agent": "coder",
                    "changed_file": str(relative_spec),
                    "loop_exit_code": loop_result["exit_code"],
                    "targeted_tests_exit_code": targeted["exit_code"],
                    "command_loop_receipt": str(loop_dir / "command-loop-receipt.json"),
                    "mocked": False,
                    "live": True,
                    "scope": (
                        "Adds the missing Tau coder command-spec overlay and verifies "
                        "one command-loop route to coder."
                    ),
                },
            ),
        )
    )
    result["commands"].append(
        github.issue_edit(
            repo,
            issue_number,
            add=[config.DONE_LABEL],
            remove=[config.LEASE_LABEL, "next:coder", "executor:local"],
        )
    )
    close = github.issue_close(repo, issue_number)
    result["commands"].append(close)
    result.update(
        {
            "ok": close["exit_code"] == 0,
            "status": "COMPLETED",
            "summary": "coder command spec added",
        }
    )
    log_event(run_id, "handle_coder_spec_finish", issue=issue_number, ok=result["ok"])
    return result


def tau_coder_spec_path(worktree: Path) -> Path:
    return (
        worktree
        / "experiments/goal-locked-subagents/agent-command-specs/coder/tau-dispatch-command.json"
    )


def tau_coder_command_spec(uv_bin: str) -> dict[str, Any]:
    return {
        "command": [
            uv_bin,
            "run",
            "tau",
            "handoff-agent-adapter",
            "--result-status",
            "COMPLETED",
            "--result-summary",
            "Coder consumed the Tau handoff JSON contract through the Tau-owned "
            "command-spec overlay.",
            "--next-agent",
            "human",
            "--next-executor",
            "human",
            "--next-reason",
            "Human review is required after this bounded watchdog repair proof.",
            "--required-evidence",
            "Human reviews the watchdog receipt, Tau command-loop receipt, pushed commit, "
            "and issue comment.",
            "--stop-condition",
            "Human accepts, redirects, or requests another bounded subagent.",
        ],
        "cwd": ".",
        "timeout_s": 30,
    }


def tau_coder_start_handoff(
    repo: str,
    issue_number: int,
    issue_url: str,
    coder_spec: Path,
) -> dict[str, Any]:
    return {
        "schema": "tau.agent_handoff.v1",
        "github": {
            "repo": repo,
            "target": f"issue#{issue_number}",
            "current_labels": [config.READY_LABEL, "next:coder", "executor:local"],
        },
        "goal": {
            "goal_id": "goal-project-watchdog-live-coder-spec",
            "goal_version": 1,
            "goal_hash": config.TAU_ACTIVE_GOAL_HASH,
        },
        "previous_subagent": "coder",
        "context": {
            "summary": (
                "Project watchdog found Tau allows coder routes but lacks a coder "
                "command-spec overlay."
            ),
            "artifacts": [issue_url, str(coder_spec)],
        },
        "result": {
            "status": "NEEDS_AGENT",
            "summary": (
                "Coder command-spec overlay is required for Tau cron to dispatch next:coder issues."
            ),
            "evidence": [f"Missing before repair: {coder_spec}"],
        },
        "rationale": (
            "Tau's command-loop cannot run a selected coder subagent without a "
            "command-spec overlay."
        ),
        "next_agent": {
            "name": "coder",
            "executor": "local",
            "reason": "Coder should consume the handoff and route to reviewer for validation.",
        },
        "required_evidence": [
            "Coder command-spec overlay exists.",
            "Tau command-loop selects coder and emits a schema-valid next handoff.",
        ],
        "stop_condition": "Coder routes to reviewer or Tau fails closed.",
    }


#: runner_kind values this generic handler knows how to drive.
#: Kept as the module-level default for tests; the live values come from
#: ``config.repair_creator``/``config.repair_reviewer`` so a project can name its
#: own seats (agent-skills#1086).
REPAIR_REVIEWER_HANDLER = config.DEFAULT_REPAIR_REVIEWER


def repair_immutable_goal(repo: str, issue_number: int) -> str:
    """The bar every seat in the repair DAG is held to.

    $ask fails preflight without one, before any handler is contacted.
    """
    return (
        f"Resolve {repo}#{issue_number} so its stated acceptance criterion holds, "
        f"proven by the proof command the ticket names. Change only the paths the "
        f"ticket targets. Do not weaken or delete a test to make it pass. "
        f"Commit to the current branch only: do not push, do not merge, and do not "
        f"modify any other branch. The reviewer seat decides whether this lands."
    )


def _ticket_repair_execution_timeout(project: dict[str, Any]) -> int:
    """Ask/Tau per-node timeout for creator/reviewer repair lanes."""
    configured = int(
        project.get("ticket_repair_execution_timeout_s")
        or project.get("ticket_repair_node_timeout_s")
        or 0
    )
    if configured <= 0:
        configured = min(int(project.get("ticket_repair_timeout_s", 1800)), 3600)
    return max(300, min(configured, 3600))


def build_repair_task(
    *,
    repo: str,
    issue_number: int,
    issue_title: str,
    issue_body: str,
    targets: list[str],
) -> str:
    """The prose task $ask compiles into the creator-reviewer DAG.

    The whole ticket body goes in: it carries the orientation block, required
    context files and proof command that a cron-dispatched agent with no prior
    session needs.
    """
    return (
        f"Repair {repo}#{issue_number}: {issue_title}\n\n"
        f"Allowed paths: {', '.join(targets) or '(as stated in the ticket)'}\n\n"
        f"Commit to the current branch only. Do not push, do not merge, do not "
        f"switch branches. Whether this reaches main is the reviewer's decision "
        f"and a human's, not the creator's.\n\n"
        f"The creator seat implements the fix and commits it. The reviewer seat "
        f"checks it against the ticket's acceptance criterion and required proof, "
        f"and answers VERDICT: PASS, VERDICT: FAIL, or VERDICT: NEEDS_ATTENTION.\n\n"
        f"The verdict must be on a line of its own. Only VERDICT: PASS closes "
        f"this ticket, and only when the ticket's proof command has actually run "
        f"and its artifact reads as a completed pass -- name the artifact path in "
        f"the review. A proof that is still running, that failed, or that was not "
        f"run is VERDICT: NEEDS_ATTENTION.\n\n"
        f"--- ticket body ---\n{issue_body}"
    )


def acquire_lease(run_id: str, result: dict[str, Any], repo: str, issue_number: int) -> bool:
    """Apply the lease label, and report whether it actually took.

    The lease is the ONLY thing stopping a later tick from dispatching a second
    repair on the same ticket, so a lease that silently failed is worse than no
    lease attempt at all -- the guard reads the ticket as free.

    Observed 2026-07-28: neither ``agent-active`` nor ``agent-blocked`` existed
    as a label in grahama1970/agent-skills, so every ``gh issue edit
    --add-label`` exited nonzero, the lease comment posted regardless, and the
    dispatch went ahead unleased. Nothing checked the exit code.
    """
    lease = github.issue_edit(repo, issue_number, add=[config.LEASE_LABEL])
    result["commands"].append(lease)
    if lease.get("exit_code") == 0:
        return True
    result.update(
        {
            "ok": False,
            "status": "BLOCKED",
            "summary": (
                f"could not apply {config.LEASE_LABEL!r} to {repo}#{issue_number}: "
                f"{str(lease.get('stderr'))[:200]}. Not dispatching unleased -- nothing "
                f"would stop the next tick starting a second repair on the same ticket. "
                f"Run: skills/ticket/run.sh ensure-labels --repo {repo}"
            ),
        }
    )
    log_event(run_id, "lease_failed", issue=issue_number, stderr=lease.get("stderr"))
    return False


def issue_goal_hash(repo: str, issue_number: int) -> str:
    """Derive a stable per-issue goal hash.

    Tau requires ``goal.goal_hash`` to be identical across every node, receipt,
    and rerun for one workflow. Deriving it from repo and issue number makes it
    reproducible on resume without storing extra state.
    """
    digest = hashlib.sha256(f"{repo}#{issue_number}".encode()).hexdigest()
    return f"sha256:{digest}"


TAU_STREAM_TERMINAL_STATUSES = frozenset(
    {"PASS", "FAIL", "BLOCKED", "NEEDS_ATTENTION", "COMPLETED", "LANDED"}
)


def _json_from_file(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _jsonl_stats(path: Path) -> dict[str, Any]:
    stats: dict[str, Any] = {"path": str(path), "line_count": 0}
    latest: dict[str, Any] | None = None
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.strip():
                    continue
                stats["line_count"] += 1
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    latest = parsed
    except OSError as exc:
        stats["error"] = str(exc)
        return stats
    if latest is not None:
        stats["latest"] = latest
        for key in ("event_id", "id", "timestamp", "ts", "status", "stage", "node", "node_id"):
            if key in latest:
                stats[f"latest_{key}"] = latest[key]
    return stats


def inspect_tau_stream(ask_run_dir: Path) -> dict[str, Any]:
    """Read Ask/Tau stream artifacts into one watchdog status snapshot."""
    record: dict[str, Any] = {
        "schema": "agent_skills.project_watchdog.tau_stream_monitor.v1",
        "checked_at": iso_now(),
        "ask_run_dir": str(ask_run_dir),
        "stream_readable": False,
        "terminal": False,
        "terminal_status": None,
        "current_node": None,
        "current_status": None,
        "event_count": 0,
        "event_files": [],
        "progress_files": [],
        "node_receipts": [],
        "reason": "no Ask/Tau stream artifacts observed",
    }
    if not ask_run_dir.exists():
        return record

    for event_path in sorted(ask_run_dir.glob("**/events.jsonl")):
        stats = _jsonl_stats(event_path)
        record["event_files"].append(stats)
        record["event_count"] += int(stats.get("line_count") or 0)
        latest = stats.get("latest")
        if isinstance(latest, dict):
            record["latest_event"] = latest

    for progress_path in sorted(ask_run_dir.glob("**/dag-progress.json")):
        progress = _json_from_file(progress_path)
        item: dict[str, Any] = {"path": str(progress_path), "readable": progress is not None}
        if progress:
            item["status"] = progress.get("status") or progress.get("verdict") or progress.get("state")
            item["current_node"] = (
                progress.get("current_node")
                or progress.get("active_node")
                or progress.get("node_id")
            )
        record["progress_files"].append(item)

    for receipt_path in sorted(ask_run_dir.glob("**/node-receipt.json")):
        receipt = _json_from_file(receipt_path)
        item: dict[str, Any] = {"path": str(receipt_path), "readable": receipt is not None}
        if receipt:
            item["status"] = receipt.get("status") or receipt.get("verdict") or receipt.get("state")
            item["node_id"] = receipt.get("node_id") or receipt_path.parent.name
        record["node_receipts"].append(item)

    candidates: list[dict[str, Any]] = []
    candidates.extend(record["progress_files"])
    candidates.extend(record["node_receipts"])
    for item in reversed(candidates):
        status = item.get("status")
        if status is not None:
            record["current_status"] = str(status)
            record["current_node"] = item.get("current_node") or item.get("node_id")
            break

    terminal = [
        item for item in candidates
        if str(item.get("status", "")).upper() in TAU_STREAM_TERMINAL_STATUSES
    ]
    if terminal:
        last = terminal[-1]
        record["terminal"] = True
        record["terminal_status"] = str(last.get("status")).upper()
        record["current_node"] = last.get("current_node") or last.get("node_id")

    record["stream_readable"] = bool(
        record["event_count"] or record["progress_files"] or record["node_receipts"]
    )
    if record["terminal"]:
        record["reason"] = "terminal Ask/Tau stream state observed"
    elif record["stream_readable"]:
        record["reason"] = "Ask/Tau stream readable but no terminal status observed"
    return record


def run_ask_tau_dag_with_stream_monitor(
    command: list[str],
    *,
    cwd: Path,
    timeout_s: int,
    ask_run_dir: Path,
    monitor_path: Path,
    poll_interval_s: float = 5.0,
) -> dict[str, Any]:
    """Run Ask/Tau while writing a live stream-monitor receipt."""
    started = time.time()
    env = os.environ.copy()
    uv_parent = str(Path(config.resolve_uv_bin()).parent)
    env["PATH"] = f"{uv_parent}:{env.get('PATH', '')}"
    monitor_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    poll_count = 0
    timed_out = False
    try:
        while proc.poll() is None:
            poll_count += 1
            snapshot = inspect_tau_stream(ask_run_dir)
            snapshot.update(
                {
                    "poll_count": poll_count,
                    "process_running": True,
                    "elapsed_seconds": round(time.time() - started, 3),
                    "stop_condition": "process_exit_or_timeout",
                }
            )
            write_json(monitor_path, snapshot)
            if time.time() - started > timeout_s:
                timed_out = True
                os.killpg(proc.pid, signal.SIGTERM)
                break
            time.sleep(poll_interval_s)
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(proc.pid, signal.SIGKILL)
            stdout, stderr = proc.communicate()
    finally:
        final = inspect_tau_stream(ask_run_dir)
        final.update(
            {
                "poll_count": poll_count,
                "process_running": False,
                "elapsed_seconds": round(time.time() - started, 3),
                "stop_condition": "terminal_status" if final.get("terminal") else "process_exit",
            }
        )
        if timed_out:
            final["stop_condition"] = "timeout"
        write_json(monitor_path, final)

    return {
        "command": command,
        "cwd": str(cwd),
        "exit_code": 124 if timed_out else proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "duration_seconds": round(time.time() - started, 3),
        "timed_out": timed_out,
        "stream_monitor": str(monitor_path),
    }


def _land_repair_to_main(worktree: Path, run_id: str, issue_number: int) -> tuple[bool, list[dict[str, Any]]]:
    """Rebase the reviewer-passed repair branch onto origin/main and push to main.

    Alpha-project policy (operator): main is the single directly-pushable branch.
    Fails closed on any git error (a rebase conflict aborts and leaves the branch
    for a human) so a bad landing never corrupts main.
    """
    cmds: list[dict[str, Any]] = []
    fetch = run_cmd(["git", "fetch", "origin", "main"], cwd=worktree, timeout_s=60)
    cmds.append(fetch)
    if fetch["exit_code"] != 0:
        return False, cmds
    rebase = run_cmd(["git", "rebase", "origin/main"], cwd=worktree, timeout_s=180)
    cmds.append(rebase)
    if rebase["exit_code"] != 0:
        cmds.append(run_cmd(["git", "rebase", "--abort"], cwd=worktree, timeout_s=60))
        log_event(run_id, "auto_land_rebase_conflict", issue=issue_number)
        return False, cmds
    push = run_cmd(["git", "push", "origin", "HEAD:main"], cwd=worktree, timeout_s=120)
    cmds.append(push)
    landed = push["exit_code"] == 0
    log_event(run_id, "auto_land_to_main", issue=issue_number, landed=landed)
    return landed, cmds


def _cleanup_landed_repair_worktree(
    project_worktree: Path,
    repair_worktree: Path,
    run_id: str,
    issue_number: int,
) -> dict[str, Any]:
    """Archive and unregister a repair worktree after its branch lands on main."""
    repo_root = Path(__file__).resolve().parents[4]
    ops_worktrees = repo_root / "skills" / "ops-worktrees" / "run.sh"
    command = [str(ops_worktrees), "archive", str(repair_worktree), "--apply", "--json"]
    start = time.monotonic()
    if not ops_worktrees.exists():
        return {
            "cmd": command,
            "exit_code": 127,
            "stdout": "",
            "stderr": f"missing ops-worktrees runtime at {ops_worktrees}",
            "duration_seconds": 0,
            "receipt": None,
        }
    env = os.environ.copy()
    env["OPS_WORKTREES_REPO"] = str(project_worktree)
    try:
        proc = subprocess.run(command, cwd=repo_root, env=env, text=True, capture_output=True, timeout=120)
    except subprocess.TimeoutExpired as exc:
        duration = round(time.monotonic() - start, 3)
        log_event(
            run_id,
            "landed_repair_worktree_cleanup_timeout",
            issue=issue_number,
            worktree=str(repair_worktree),
        )
        return {
            "cmd": command,
            "cwd": str(repo_root),
            "exit_code": 124,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "ops-worktrees archive timed out after 120s",
            "duration_seconds": duration,
            "receipt": None,
            "timed_out": True,
        }
    duration = round(time.monotonic() - start, 3)
    receipt: dict[str, Any] | None = None
    if proc.stdout.strip():
        try:
            parsed = json.loads(proc.stdout)
            if isinstance(parsed, dict):
                receipt = parsed
        except json.JSONDecodeError:
            receipt = None
    outcome = receipt.get("outcome") if receipt else None
    log_event(
        run_id,
        "landed_repair_worktree_cleanup",
        issue=issue_number,
        exit_code=proc.returncode,
        outcome=outcome,
        worktree=str(repair_worktree),
    )
    return {
        "cmd": command,
        "cwd": str(repo_root),
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "duration_seconds": duration,
        "receipt": receipt,
    }


def _landed_repair_cleanup_ok(command_result: dict[str, Any]) -> bool:
    if command_result.get("exit_code") != 0:
        return False
    receipt = command_result.get("receipt")
    if not isinstance(receipt, dict):
        return False
    return receipt.get("outcome") in {"archived", "removed", "skipped"}


# --------------------------------------------------------------------------- #
# Repair proof gate — a DAG that exited 0 is not a repaired ticket
# --------------------------------------------------------------------------- #

#: The verdict vocabulary the repair task asks each seat for. A response that
#: declares nothing from this vocabulary has declared no verdict; the watchdog
#: reads what a seat states, it does not interpret prose into a verdict.
REPAIR_VERDICT_TOKENS = frozenset({"PASS", "FAIL", "NEEDS_ATTENTION", "BLOCKED"})

#: Verdicts that are an explicit refusal to claim the repair is done.
REPAIR_REFUSAL_TOKENS = frozenset({"FAIL", "NEEDS_ATTENTION", "BLOCKED"})

#: Values a machine-readable proof artifact may carry that mean "this run
#: finished and passed".
PROOF_PASS_VALUES = frozenset(
    {"PASS", "PASSED", "READY", "OK", "COMPLETED", "SUCCESS", "GREEN", "TRUE"}
)

#: Values that mean the proof did not finish, or finished badly. ``RUNNING``
#: and ``PENDING`` are failures here on purpose: agent-skills#1499 was closed
#: while its second proof attempt was still going.
PROOF_FAIL_VALUES = frozenset(
    {
        "FAIL", "FAILED", "BLOCKED", "ERROR", "ERRORED", "NOT_READY",
        "NEEDS_ATTENTION", "RUNNING", "PENDING", "IN_PROGRESS", "TIMEOUT",
        "TIMED_OUT", "CANCELLED", "SKIPPED", "UNKNOWN", "FALSE",
    }
)

#: Keys whose value states the outcome of a run. Read at any depth so a
#: per-case ``status: FAIL`` inside an otherwise READY report still fails.
PROOF_RESULT_KEYS = frozenset(
    {"readiness", "status", "verdict", "result", "outcome", "overall",
     "overall_status", "state", "ok", "passed"}
)

#: How far into a proof artifact to read result keys. Deep enough for a
#: per-case eval report, bounded so a huge artifact cannot stall a tick.
PROOF_SCAN_DEPTH = 6

_POSITION_HEADING = re.compile(r"^#{1,6}\s*position\s*$", re.IGNORECASE)
_OUTPUT_FLAG = re.compile(r"--(?:output|out|output-file|report)[ =]+([^\s`'\"]+)")
_PROOF_PATH = re.compile(
    r"(?:^|[\s`'\"(=])((?:/|\./|~/)?[\w.@+-]+(?:/[\w.@+-]+)+\.(?:json|xml|txt|log|md|csv|html))"
)


def repair_node_id(handler: str) -> str:
    """The ``node-artifacts`` directory ``$ask`` writes for one handler seat."""
    return "handler-" + re.sub(r"[^a-z0-9]+", "-", handler.lower()).strip("-")


def declared_verdict(text: str) -> str | None:
    """The verdict a seat declared, or ``None`` if it declared none.

    Two structural forms, both of which the repair task and the roundtable
    prompt ask for by name: a ``VERDICT: <token>`` line, or the first word of
    the ``## Position`` section. This is extraction, not classification --
    prose that describes a problem in its own words yields ``None``, and the
    gate treats "no verdict" as unproven rather than guessing at it.
    """
    def token(raw: str) -> str | None:
        words = raw.strip().split()
        if not words:
            return None
        candidate = words[0].strip("*`_.,:;#—–-").upper()
        return candidate if candidate in REPAIR_VERDICT_TOKENS else None

    lines = text.splitlines()
    for line in lines:
        stripped = line.strip().lstrip("*#>- ").strip()
        if stripped.upper().startswith("VERDICT:"):
            found = token(stripped.split(":", 1)[1])
            if found:
                return found
    for index, line in enumerate(lines):
        if not _POSITION_HEADING.match(line.strip()):
            continue
        for following in lines[index + 1:]:
            if not following.strip():
                continue
            return token(following)
    return None


def seat_response_text(ask_run_dir: Path, handler: str) -> str | None:
    """The response one seat actually wrote, across every ``$ask`` run dir."""
    node_id = repair_node_id(handler)
    for candidate in sorted(ask_run_dir.glob(f"*/node-artifacts/{node_id}/response.md")):
        try:
            return candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:  # pragma: no cover - unreadable artifact is "no response"
            continue
    return None


def required_proof_artifacts(issue_body: str) -> list[str]:
    """The artifact paths the ticket's own proof section names.

    Only the ``Required proof`` section is read: paths elsewhere in a ticket
    body are context files and reproduction pointers, not things the repair is
    supposed to produce. When the section names an ``--output`` operand those
    win outright, because that is the artifact the proof command writes.
    """
    section: list[str] = []
    collecting = False
    for line in issue_body.splitlines():
        heading = re.match(r"^#{1,6}\s*(.+?)\s*$", line.strip())
        if heading:
            collecting = heading.group(1).strip().lower() == "required proof"
            continue
        if collecting:
            section.append(line)
    text = "\n".join(section)
    if not text.strip():
        return []
    outputs = [m.group(1) for m in _OUTPUT_FLAG.finditer(text)]
    if outputs:
        return sorted(dict.fromkeys(outputs))
    return sorted(dict.fromkeys(m.group(1) for m in _PROOF_PATH.finditer(text)))


def _result_values(payload: Any, depth: int = 0) -> list[str]:
    """Every outcome-key value in a parsed artifact, uppercased."""
    if depth > PROOF_SCAN_DEPTH:
        return []
    found: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key).lower() in PROOF_RESULT_KEYS and isinstance(value, (str, bool)):
                found.append(str(value).upper())
            else:
                found.extend(_result_values(value, depth + 1))
    elif isinstance(payload, list):
        for item in payload:
            found.extend(_result_values(item, depth + 1))
    return found


def inspect_proof_artifact(raw_path: str, *, not_before: float) -> dict[str, Any]:
    """Whether one named proof artifact is present, fresh, and a completed pass.

    Freshness is load-bearing: agent-skills#1499 had a passing receipt on disk
    from July, and accepting it would have closed the ticket on a proof no seat
    in this dispatch ever ran.
    """
    path = Path(raw_path).expanduser()
    record: dict[str, Any] = {
        "path": str(path), "exists": False, "fresh": False,
        "machine_readable": False, "passed": False, "reason": "",
    }
    if not path.is_file():
        record["reason"] = "not written"
        return record
    record["exists"] = True
    stat = path.stat()
    record["mtime"] = stat.st_mtime
    record["size"] = stat.st_size
    if stat.st_mtime < not_before:
        record["reason"] = "predates this dispatch"
        return record
    record["fresh"] = True
    if stat.st_size == 0:
        record["reason"] = "empty"
        return record
    if path.suffix.lower() != ".json":
        record["passed"] = True
        record["reason"] = "fresh non-empty artifact"
        return record
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError) as exc:
        record["reason"] = f"unreadable json: {exc}"
        return record
    values = _result_values(payload)
    record["machine_readable"] = bool(values)
    failing = sorted({v for v in values if v in PROOF_FAIL_VALUES})
    passing = sorted({v for v in values if v in PROOF_PASS_VALUES})
    record["failing_values"] = failing
    record["passing_values"] = passing
    if failing:
        record["reason"] = f"reports {', '.join(failing)}"
        return record
    if not passing:
        record["reason"] = "no machine-readable result"
        return record
    record["passed"] = True
    record["reason"] = f"reports {', '.join(passing)}"
    return record


def repair_commits_ahead(worktree: Path) -> int | None:
    """Commits the repair branch has that ``origin/main`` does not.

    ``None`` means git could not answer, which the gate treats as unproven.
    """
    counted = run_cmd(
        ["git", "rev-list", "--count", "origin/main..HEAD"], cwd=worktree, timeout_s=60
    )
    if counted.get("exit_code") != 0:
        return None
    try:
        return int(str(counted.get("stdout", "")).strip())
    except ValueError:  # pragma: no cover - git printed something unexpected
        return None


def evaluate_repair_proof(
    *,
    ask_run_dir: Path,
    issue_body: str,
    creator: str,
    reviewer: str,
    repair_worktree: Path,
    not_before: float,
) -> dict[str, Any]:
    """Decide whether this repair may close its ticket.

    ``$ask tau-dag`` exiting 0 means the DAG ran, not that the ticket was
    repaired: in agent-skills#1499 both seats reported ``status: PASS`` in
    their node receipts while the creator's response said it had no tools and
    the reviewer's said the live proof failed and a retry was still running.
    The issue was closed as completed with no proof and no commit.

    So closure requires positive evidence, and everything else fails closed:

    - the reviewer seat declares ``VERDICT: PASS`` in its response;
    - no seat declares FAIL, BLOCKED, or NEEDS_ATTENTION;
    - if the ticket names proof artifacts, at least one exists, was written
      during this dispatch, and reads as a completed pass;
    - the repair branch is at least one commit ahead of ``origin/main``.
    """
    gate: dict[str, Any] = {
        "schema": "agent_skills.project_watchdog.repair_proof_gate.v1",
        "ok": False,
        "reasons": [],
        "seat_verdicts": {},
        "required_proof_artifacts": [],
        "artifact_results": [],
        "commits_ahead": None,
        "checked_at": iso_now(),
    }
    reasons: list[str] = []

    for role, handler in (("creator", creator), ("reviewer", reviewer)):
        response = seat_response_text(ask_run_dir, handler)
        verdict = declared_verdict(response) if response is not None else None
        gate["seat_verdicts"][role] = {
            "handler": handler,
            "node_id": repair_node_id(handler),
            "responded": response is not None,
            "verdict": verdict,
        }
        if response is None:
            reasons.append(f"{role} seat {handler} wrote no response artifact")
            continue
        if verdict in REPAIR_REFUSAL_TOKENS:
            reasons.append(f"{role} seat {handler} declared {verdict}")
        elif verdict is None and role == "reviewer":
            reasons.append(
                f"reviewer seat {handler} declared no VERDICT; the repair task "
                f"requires VERDICT: PASS, FAIL, or NEEDS_ATTENTION"
            )
        elif verdict != "PASS" and role == "reviewer":
            reasons.append(f"reviewer seat {handler} declared {verdict}, not PASS")

    artifacts = required_proof_artifacts(issue_body)
    gate["required_proof_artifacts"] = artifacts
    if artifacts:
        results = [inspect_proof_artifact(a, not_before=not_before) for a in artifacts]
        gate["artifact_results"] = results
        if not any(r["passed"] for r in results):
            detail = "; ".join(f"{r['path']}: {r['reason']}" for r in results)
            reasons.append(f"no required proof artifact was produced and passing ({detail})")

    commits = repair_commits_ahead(repair_worktree)
    gate["commits_ahead"] = commits
    if commits is None:
        reasons.append(f"could not read commits on the repair branch in {repair_worktree}")
    elif commits < 1:
        reasons.append("the repair branch has no commit ahead of origin/main")

    gate["reasons"] = reasons
    gate["ok"] = not reasons
    return gate


def handle_ticket_repair(
    run_id: str,
    receipt_dir: Path,
    project: dict[str, Any],
    issue: dict[str, Any],
    *,
    apply: bool,
) -> dict[str, Any]:
    """Repair one ordinary ``/ticket``-filed issue through a Tau DAG contract.

    This is the route for tickets filed the normal way: labelled ``agent-work``
    with a ``type:``/``route:`` vocabulary and no hand-authored body marker.

    The watchdog compiles the contract and calls ``tau dag-run``. It does not
    drive the loop, count attempts, or decide when the work is done — Tau does,
    and its receipt is the verdict.
    """
    repo = project_repo(project)
    worktree = project_worktree(project)
    issue_number = int(issue["number"])
    runner_kind = str(project.get("runner_kind", ""))
    log_event(run_id, "handle_ticket_repair_start", issue=issue_number, repo=repo)
    result = _new_result(project, issue, "ticket_repair")
    result["selected_agent"] = "coder"
    result["runner_kind"] = runner_kind

    # Two seats, deliberately different model families: a reviewer that shares
    # the creator's blind spots is a second pass, not a second opinion.
    creator = config.repair_creator(project)
    reviewer = config.repair_reviewer(project)
    result["seats"] = {"creator": creator, "reviewer": reviewer}
    # The reviewer must be an INDEPENDENT second opinion (different provider) AND
    # able to run the ticket's live proof (not a browser chat). Fail loudly here
    # rather than dispatch a review that shares the creator's blind spots or a
    # browser seat that cannot execute the proof (which failed silently as
    # "$ask tau-dag failed" — agent-skills#1484).
    try:
        config.assert_cross_provider_seats(creator, reviewer)
    except config.SeatIndependenceError as exc:
        result.update({"ok": False, "status": "BLOCKED", "summary": str(exc)})
        log_event(run_id, "repair_seats_not_independent", issue=issue_number,
                  creator=creator, reviewer=reviewer, reason=str(exc))
        return result

    ask_run = config.ask_run_sh()
    if not ask_run.is_file():
        result.update(
            {
                "ok": False,
                "status": "BLOCKED",
                "summary": f"$ask runner not found at {ask_run}; the repair lane needs it.",
            }
        )
        log_event(run_id, "handle_ticket_repair_no_ask", issue=issue_number, ask_run=str(ask_run))
        return result

    # Fail closed on an unusable checkout BEFORE leasing the issue or calling
    # Tau. A repair is authored in a separate worktree from origin/main, so
    # dirty target files in the registered checkout are operational context, not
    # an authoring blocker. Branch/missing/non-git failures still block because
    # they make origin/main discovery and repair-worktree preparation unsafe.
    targets = registry.issue_targets(issue)
    result["targets"] = sorted(targets)

    readiness = worktree_readiness(worktree, targets)
    result["worktree_readiness"] = readiness
    blocking_reasons = [
        reason
        for reason in readiness.get("reasons", [])
        if not str(reason).startswith("tracked_files_dirty:")
    ]
    result["registered_checkout_dirty_tracked"] = readiness.get("dirty_tracked", 0)
    result["registered_checkout_untracked"] = readiness.get("untracked", 0)
    result["worktree_dispatch_blocking_reasons"] = blocking_reasons
    if blocking_reasons:
        result.update(
            {
                "ok": False,
                "status": "BLOCKED",
                "summary": (
                    f"worktree {worktree} is not safe to author a repair in: "
                    f"{', '.join(blocking_reasons or ['unknown'])}. "
                    f"branch={readiness.get('branch')} "
                    f"dirty_tracked={readiness.get('dirty_tracked')} "
                    f"untracked={readiness.get('untracked')}."
                ),
            }
        )
        log_event(
            run_id,
            "handle_ticket_repair_worktree_unready",
            issue=issue_number,
            reasons=readiness.get("reasons"),
        )
        return result

    goal_hash = issue_goal_hash(repo, issue_number)
    result["goal_hash"] = goal_hash
    ask_run_dir = receipt_dir / "ask"
    task = build_repair_task(
        repo=repo,
        issue_number=issue_number,
        issue_title=str(issue.get("title", "")),
        issue_body=str(issue.get("body", "")),
        targets=sorted(targets),
    )
    task_path = receipt_dir / "repair-task.md"
    task_path.write_text(task, encoding="utf-8")
    result["artifacts"].append(str(task_path))

    if not apply:
        result.update(
            {
                "ok": True,
                "status": "DRY_RUN",
                "summary": (
                    f"would author {repo}#{issue_number} in a fresh worktree off origin/main "
                    f"and run $ask tau-dag over {sorted(targets)}"
                ),
            }
        )
        return result

    # Author in a worktree of our own, created from origin/main per dispatch.
    repair_worktree = config.repair_worktrees_dir() / f"{project.get('project_id')}-{issue_number}"
    prepared = registry.prepare_repair_worktree(worktree, repair_worktree, issue_number)
    result["repair_worktree"] = prepared
    if not prepared.get("ok"):
        result.update(
            {
                "ok": False,
                "status": "BLOCKED",
                "summary": f"could not prepare a repair worktree: {prepared.get('error')}",
            }
        )
        log_event(run_id, "repair_worktree_failed", issue=issue_number, error=prepared.get("error"))
        return result
    result["artifacts"].append(str(repair_worktree))

    # The creator commits on its own branch; only the reviewer's verdict should
    # move main. Observed 2026-07-28: the codex seat pushed a850e22a6 straight to
    # origin/main while its own DAG node reported NEEDS_ATTENTION and the ticket
    # stayed agent-blocked -- unreviewed work landed anyway.
    main_before = registry.remote_main_sha(worktree)
    result["origin_main_before"] = main_before

    result["commands"].append(
        github.issue_comment(
            repo,
            issue_number,
            github.watchdog_comment(
                "Lease acquired",
                {
                    "schema": "agent_skills.project_watchdog.lease.v1",
                    "acquired_at": iso_now(),
                    "run_id": run_id,
                    "issue": f"issue#{issue_number}",
                    "repo": repo,
                    "selected_agent": "coder",
                    "action": "ticket_repair",
                    "targets": sorted(targets),
                    "goal_hash": goal_hash,
                },
            ),
        )
    )
    if not acquire_lease(run_id, result, repo, issue_number):
        return result

    # $ask compiles the creator/reviewer DAG and Tau executes it. The watchdog
    # does not hand-author a tau.dag_contract.v1: doing so bound this lane to
    # Tau's own command-spec tree, which only the tau checkout has, so every
    # other project was refused before it could dispatch anything.
    # Everything the proof gate accepts must be written after this instant: a
    # proof artifact older than the dispatch proves a previous run, not this one.
    dispatched_at = time.time()
    dag_command = [
        str(config.ask_run_sh()),
        "tau-dag",
        task,
        "--repo", repo,
        "--target", ",".join(sorted(targets)),
        "--immutable-goal", repair_immutable_goal(repo, issue_number),
        "--dag-template", "creator-reviewer",
        "--handler", creator,
        "--handler-workspace", f"{creator}={repair_worktree}",
        "--handler", reviewer,
        "--topology", "sequential",
        "--run-output-root", str(ask_run_dir),
        "--execute",
        "--execution-timeout-seconds", str(_ticket_repair_execution_timeout(project)),
        "--allow-provider-calls",
        "--json",
    ]
    stream_monitor_path = receipt_dir / "tau-stream-monitor.json"
    dag_result = run_ask_tau_dag_with_stream_monitor(
        dag_command,
        cwd=config.ask_run_sh().parent,
        timeout_s=int(project.get("ticket_repair_timeout_s", 1800)),
        ask_run_dir=ask_run_dir,
        monitor_path=stream_monitor_path,
    )
    result["commands"].append(dag_result)
    result["artifacts"].append(str(ask_run_dir))
    result["artifacts"].append(str(stream_monitor_path))
    result["tau_stream_monitor"] = inspect_tau_stream(ask_run_dir)

    if dag_result["exit_code"] != 0:
        result.update(
            {
                "ok": False,
                "status": "NEEDS_ATTENTION",
                "summary": f"$ask tau-dag failed for {repo}#{issue_number}",
            }
        )
        result["commands"].append(
            github.issue_edit(
                repo, issue_number, add=[config.BLOCKED_LABEL], remove=[config.LEASE_LABEL]
            )
        )
        log_event(run_id, "handle_ticket_repair_failed", issue=issue_number)
        return result

    result["commands"].append(
        github.issue_comment(
            repo,
            issue_number,
            github.watchdog_comment(
                "Ticket repair evidence",
                {
                    "schema": "agent_skills.project_watchdog.ticket_repair_receipt.v1",
                    "run_id": run_id,
                    "issue": f"issue#{issue_number}",
                    "repo": repo,
                    "targets": sorted(targets),
                    "goal_hash": goal_hash,
                    "dag_exit_code": dag_result["exit_code"],
                    "ask_run_dir": str(ask_run_dir),
                    "mocked": False,
                    "live": True,
                    "scope": (
                        "Runs one $ask creator-reviewer Tau DAG for a /ticket-filed issue. "
                        "Closure and evidence acceptance are owned by Tau's DAG receipt, "
                        "not by this watchdog."
                    ),
                },
            ),
        )
    )
    main_after = registry.remote_main_sha(worktree)
    result["origin_main_after"] = main_after
    if main_before and main_after and main_before != main_after:
        result.update(
            {
                "ok": False,
                "status": "NEEDS_ATTENTION",
                "summary": (
                    f"origin/main moved during this repair ({main_before[:9]} -> "
                    f"{main_after[:9]}). The creator seat must commit to its own branch "
                    f"and let the reviewer decide what lands; unreviewed work on main is "
                    f"exactly what the two-seat loop exists to prevent."
                ),
            }
        )
        log_event(run_id, "origin_main_moved_during_repair", issue=issue_number,
                  before=main_before, after=main_after)
        result["commands"].append(
            github.issue_edit(repo, issue_number, add=[config.BLOCKED_LABEL],
                              remove=[config.LEASE_LABEL])
        )
        return result

    # A DAG that exited 0 says the seats were reached, nothing more. Closure
    # needs the reviewer's own PASS, the ticket's proof, and a commit --
    # agent-skills#1499 was closed as completed with none of the three.
    gate = evaluate_repair_proof(
        ask_run_dir=ask_run_dir,
        issue_body=str(issue.get("body", "")),
        creator=creator,
        reviewer=reviewer,
        repair_worktree=repair_worktree,
        not_before=dispatched_at,
    )
    result["proof_gate"] = gate
    gate_path = receipt_dir / "repair-proof-gate.json"
    write_json(gate_path, gate)
    result["artifacts"].append(str(gate_path))
    if not gate["ok"]:
        result.update(
            {
                "ok": False,
                "status": "NEEDS_ATTENTION",
                "summary": (
                    f"$ask tau-dag passed but the repair is unproven for "
                    f"{repo}#{issue_number}: {'; '.join(gate['reasons'])}. "
                    f"Not landing and not closing."
                ),
            }
        )
        result["commands"].append(
            github.issue_comment(
                repo,
                issue_number,
                github.watchdog_comment("Repair proof gate refused closure", gate),
            )
        )
        result["commands"].append(
            github.issue_edit(
                repo, issue_number, add=[config.BLOCKED_LABEL], remove=[config.LEASE_LABEL]
            )
        )
        log_event(run_id, "repair_proof_gate_refused", issue=issue_number,
                  reasons=gate["reasons"])
        return result

    # Alpha projects (operator rule): a reviewer-passed repair lands directly on
    # main -- main is the single directly-pushable branch until a project is
    # stable-reliable, so the branch-and-await-human dance is skipped here.
    if config.auto_land_main(project):
        landed, land_cmds = _land_repair_to_main(repair_worktree, run_id, issue_number)
        result["commands"].extend(land_cmds)
        if landed:
            cleanup = _cleanup_landed_repair_worktree(worktree, repair_worktree, run_id, issue_number)
            result["repair_worktree_cleanup"] = cleanup
            result["commands"].append(cleanup)
            if not _landed_repair_cleanup_ok(cleanup):
                result.update(
                    {
                        "ok": False,
                        "status": "NEEDS_ATTENTION",
                        "summary": (
                            f"$ask tau-dag repair for {repo}#{issue_number} landed on main, "
                            "but project-watchdog could not archive/remove the repair worktree."
                        ),
                    }
                )
                result["commands"].append(
                    github.issue_comment(
                        repo,
                        issue_number,
                        github.watchdog_comment("Landed repair worktree cleanup failed", cleanup),
                    )
                )
                result["commands"].append(
                    github.issue_edit(
                        repo, issue_number, add=[config.BLOCKED_LABEL], remove=[config.LEASE_LABEL]
                    )
                )
                log_event(
                    run_id,
                    "handle_ticket_repair_landed_cleanup_failed",
                    issue=issue_number,
                    cleanup_exit_code=cleanup.get("exit_code"),
                )
                return result
            result["commands"].append(
                github.issue_edit(repo, issue_number, add=[config.DONE_LABEL], remove=[config.LEASE_LABEL])
            )
            result["commands"].append(
                github.issue_comment(
                    repo, issue_number,
                    "Project Watchdog: reviewer passed; repair landed directly on main "
                    "(alpha project, main is the single branch). Repair worktree archived. Closing.",
                )
            )
            result["commands"].append(github.issue_close(repo, issue_number, reason="completed"))
            result.update({"ok": True, "status": "LANDED",
                           "summary": f"$ask tau-dag repair for {repo}#{issue_number} passed review and landed on main"})
            log_event(run_id, "handle_ticket_repair_finish", issue=issue_number, ok=True, landed=True)
            return result
        # Landing failed (e.g. rebase conflict): fall through to await-review.

    # Mark the repair done and stop routing it. The ticket stays OPEN because the
    # work has not landed -- it is a branch awaiting review -- but leaving it
    # routable made cron re-dispatch every tick, and each dispatch reset the
    # branch over the previous repair.
    result["commands"].append(
        github.issue_edit(
            repo, issue_number,
            add=[config.DONE_LABEL],
            remove=[config.LEASE_LABEL],
        )
    )
    result.update(
        {
            "ok": True,
            "status": "COMPLETED",
            "summary": f"$ask tau-dag completed for {repo}#{issue_number}; branch {prepared.get('branch')} awaiting review",
        }
    )
    log_event(run_id, "handle_ticket_repair_finish", issue=issue_number, ok=True)
    return result


# --------------------------------------------------------------------------- #
# Closure audit — a closure is a claim, not evidence
# --------------------------------------------------------------------------- #

#: Marks an audit comment so a later tick can count prior reopens without
#: re-reading every comment body for meaning.
CLOSURE_AUDIT_MARKER = "project-watchdog:closure-audit"


#: Closure-evidence schema `/ticket close --results` submits. Its `unit` and
#: `e2e` blocks name the commands that ran and the artifact each wrote.
CLOSURE_EVIDENCE_SCHEMA = "agent_skills.ticket_closure_evidence.v1"

CLOSURE_AUDIT_NONZERO_NEEDS_ATTENTION_CODE = (
    "project_watchdog_closure_audit_nonzero_needs_attention"
)

#: Cap per artifact. The auditors read a prompt, not a filesystem; a 50MB log
#: would crowd out the ticket itself.
ARTIFACT_EXCERPT_CHARS = 4000

_LOCAL_PATH_IN_PROMPT = re.compile(r"(?<![\w.])(?:/home|/tmp)/[^\s`'\"),\]]+")


def sanitize_local_paths_for_browser_prompt(text: str) -> str:
    """Remove absolute local paths from prompts sent to browser-backed seats."""
    def replace(match: re.Match[str]) -> str:
        name = Path(match.group(0)).name or "path"
        return f"[local path omitted: {name}]"

    return _LOCAL_PATH_IN_PROMPT.sub(replace, text)


def collect_closure_artifacts(comments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Read the proof artifacts a closure claimed, so the audit can see them.

    Both audit seats reported they could not read local files, so they judged
    "was the proof actually run" from the ticket thread alone -- and a closing
    comment that summarises rather than pastes its output could never pass. The
    closer already submits artifact paths in the closure-evidence JSON; nothing
    read them.

    A path that no longer exists is reported as missing rather than omitted. An
    artifact that cannot be produced is itself a fact about the closure.
    """
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for comment in comments:
        for block in re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", str(comment.get("body", "")), re.S):
            try:
                payload = json.loads(block)
            except ValueError:
                continue
            if payload.get("schema") != CLOSURE_EVIDENCE_SCHEMA:
                continue
            for tier in ("unit", "e2e"):
                entry = payload.get(tier)
                if not isinstance(entry, dict):
                    continue
                path = str(entry.get("artifact") or "").strip()
                if not path or path in seen:
                    continue
                seen.add(path)
                record: dict[str, Any] = {"tier": tier, "path": path,
                                          "command": entry.get("command")}
                try:
                    text = Path(path).read_text(encoding="utf-8", errors="replace")
                    record["content"] = text[:ARTIFACT_EXCERPT_CHARS]
                    record["bytes"] = len(text)
                except OSError as exc:
                    record["missing"] = str(exc)
                found.append(record)
    return found


def render_closure_artifacts(artifacts: list[dict[str, Any]]) -> str:
    """Format collected artifacts for the audit prompt."""
    if not artifacts:
        return "(the closure cited no artifact paths)"
    chunks = []
    for a in artifacts:
        head = f"[{a['tier']}] {a['path']}"
        if a.get("command"):
            head += f"\n  command: {a['command']}"
        if "missing" in a:
            chunks.append(f"{head}\n  NOT READABLE: {a['missing']}")
        else:
            chunks.append(f"{head}\n  ({a['bytes']} chars)\n{a['content']}")
    return "\n\n".join(chunks)


def build_closure_audit_task(
    *,
    repo: str,
    issue_number: int,
    issue_title: str,
    issue_body: str,
    evidence: str,
    artifacts: str = "(no artifacts collected)",
) -> str:
    """The prompt the auditor answers.

    It gets the ticket's own acceptance criterion and required proof, and the
    closing evidence, and nothing else. The question is narrow on purpose: not
    "is this good work" but "does the closure hold against what the ticket
    asked for".
    """
    task = (
        f"Audit the closure of {repo}#{issue_number}: {issue_title}\n\n"
        f"Decide one thing: does the evidence below actually establish the "
        f"acceptance criterion and the required proof the ticket names?\n\n"
        f"Answer VERDICT: PASS only if the named proof was actually run and its "
        f"result is shown. Answer VERDICT: FAIL if the criterion is unmet, the "
        f"proof was not run, the evidence is asserted rather than shown, or the "
        f"change demonstrably does something other than what was asked. Answer "
        f"VERDICT: NEEDS_ATTENTION if you cannot tell from what is here.\n\n"
        f"A closing comment claiming success is not evidence that the proof ran. "
        f"Deterministic tests over the closer's own new code are weak evidence "
        f"for a live defect. Say which specific criterion fails and why.\n\n"
        f"You are shown the proof artifacts the closure cited, read from disk. "
        f"Treat those as the actual output of the proof command. An artifact "
        f"marked NOT READABLE is a gap; an artifact whose contents show the proof "
        f"passing is the evidence you are looking for.\n\n"
        f"If the closure cites NO artifacts at all, it predates the evidence "
        f"contract and cannot produce them. That is not grounds for FAIL. Answer "
        f"NEEDS_ATTENTION unless the thread itself positively shows the criterion "
        f"is unmet. Reserve FAIL for evidence that the work is wrong, not for "
        f"evidence that is absent by design -- FAIL reopens the ticket and sends "
        f"a repair agent at work that may well be finished.\n\n"
        f"--- ticket ---\n{issue_body}\n\n"
        f"--- closing evidence ---\n{evidence}\n\n"
        f"--- proof artifacts read from disk ---\n{artifacts}"
    )
    return sanitize_local_paths_for_browser_prompt(task)


def _extract_verdict(text: str) -> str | None:
    """Same convention $ask's reviewer seats use."""
    upper = text.upper()
    for verdict in ("NEEDS_ATTENTION", "PASS", "FAIL"):
        if f"VERDICT: {verdict}" in upper or f"VERDICT {verdict}" in upper:
            return verdict
    return None


def read_seat_failures(run_root: Path) -> dict[str, str]:
    """Per-seat failure codes from an $ask run, for the summary.

    Without these a panel that could not reach a provider reported only "no
    usable panel verdict", and the operator had to dig through recovery packets
    to find `scillm_auth_invalid_api_key`. The cause belongs in the receipt.
    """
    failures: dict[str, str] = {}
    for receipt in sorted(run_root.glob("*/node-artifacts/*/node-receipt.json")):
        if receipt.parent.name == "join":
            continue
        try:
            data = json.loads(receipt.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.error("could not read node receipt {}: {}", receipt, exc)
            continue
        code = data.get("failure_code")
        if code:
            failures[receipt.parent.name] = str(code)
    return failures


def _read_ask_responses_by_node(run_root: Path) -> dict[str, str]:
    """Each handler seat's cleaned answer, keyed by node id.

    A panel needs per-seat verdicts: concatenating them would let one seat's
    "VERDICT: PASS" be read as the panel's answer.
    """
    responses: dict[str, str] = {}
    for node_dir in sorted(run_root.glob("*/node-artifacts/*")):
        if node_dir.name == "join":
            continue
        clean = node_dir / "response.md"
        raw = node_dir / "response.raw.md"
        path = clean if clean.is_file() else raw
        if not path.is_file():
            continue
        try:
            responses[node_dir.name] = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.error("could not read $ask response {}: {}", path, exc)
    return responses


def _read_ask_response(run_root: Path) -> str:
    """The handler's cleaned answer from an $ask run directory.

    `response.md` is the cleaned text; `response.raw.md` is the provider's whole
    chat-completion envelope. Globbing `response*.md` matched both, so the
    reviewer excerpt posted to GitHub was raw JSON with the reasoning buried in
    it. Only fall back to raw when a lane produced no cleaned response at all.
    """
    chunks: list[str] = []
    for node_dir in sorted(run_root.glob("*/node-artifacts/*")):
        clean = node_dir / "response.md"
        raw = node_dir / "response.raw.md"
        path = clean if clean.is_file() else raw
        if not path.is_file():
            continue
        try:
            chunks.append(path.read_text(encoding="utf-8"))
        except OSError as exc:
            logger.error("could not read $ask response {}: {}", path, exc)
    return "\n\n".join(chunks)


def handle_closure_audit(
    run_id: str,
    receipt_dir: Path,
    project: dict[str, Any],
    issue: dict[str, Any],
    *,
    apply: bool,
) -> dict[str, Any]:
    """Review one closed ticket and reopen it if the closure does not hold.

    Closing a ticket is a claim that the work is done, and nothing checked it.
    The repair lane's reviewer judges a diff before it lands; this judges the
    closure afterwards, including closures no agent made.
    """
    repo = project_repo(project)
    issue_number = int(issue["number"])
    auditors = config.closure_auditors(project)
    result = _new_result(project, issue, "closure_audit")
    result["selected_agent"] = ",".join(auditors)
    result["auditors"] = auditors
    log_event(run_id, "closure_audit_start", issue=issue_number, repo=repo, auditors=auditors)

    if len(auditors) < 2 or len(set(auditors)) != len(auditors):
        result.update(
            {
                "ok": False,
                "status": "BLOCKED",
                "summary": (
                    f"closure audit needs at least two distinct seats, got {auditors}. "
                    f"One model that over-accepts would uphold its own bad closures."
                ),
            }
        )
        log_event(run_id, "closure_audit_panel_invalid", issue=issue_number, auditors=auditors)
        return result

    comments = github.issue_comments(repo, issue_number)
    reopens = sum(
        1
        for c in comments
        if CLOSURE_AUDIT_MARKER in str(c.get("body", "")) and "REOPENED" in str(c.get("body", ""))
    )
    result["prior_reopens"] = reopens

    evidence = "\n\n".join(
        f"[{c.get('author', {}).get('login', '?')} {str(c.get('createdAt', ''))[:19]}]\n"
        f"{str(c.get('body', ''))[:4000]}"
        for c in comments
    ) or "(no comments on this issue)"

    collected = collect_closure_artifacts(comments)
    result["closure_artifacts"] = [
        {k: v for k, v in a.items() if k != "content"} for a in collected
    ]
    task = build_closure_audit_task(
        repo=repo,
        issue_number=issue_number,
        issue_title=str(issue.get("title", "")),
        issue_body=str(issue.get("body", ""))[:8000],
        evidence=evidence,
        artifacts=render_closure_artifacts(collected),
    )
    if not apply:
        # Write nothing on a preview: creating the receipt directory is what
        # makes a tick leave a directory behind, and a previewed audit is not an
        # event. A per-minute cron would otherwise accumulate one per tick.
        result.update(
            {
                "ok": True,
                "status": "DRY_RUN",
                "summary": (
                    f"would audit the closure of {repo}#{issue_number} with {auditors}"
                ),
            }
        )
        return result

    task_path = receipt_dir / f"closure-audit-{issue_number}.md"
    task_path.write_text(task, encoding="utf-8")
    result["artifacts"].append(str(task_path))

    ask_run_dir = receipt_dir / f"closure-audit-{issue_number}"
    audit = run_cmd(
        [
            str(config.ask_run_sh()),
            "tau-dag",
            task,
            "--repo", repo,
            "--target", f"issue#{issue_number}",
            "--immutable-goal", (
                f"Decide whether the closure of {repo}#{issue_number} is supported by "
                f"evidence for the acceptance criterion and proof the ticket names. "
                f"Do not accept an assertion of success as evidence that a proof ran."
            ),
            "--dag-template", "roundtable",
            "--topology", "concurrent",
            *[arg for seat in auditors for arg in ("--handler", seat)],
            "--run-output-root", str(ask_run_dir),
            "--execute",
            "--allow-provider-calls",
            "--json",
        ],
        cwd=config.ask_run_sh().parent,
        timeout_s=int(project.get("closure_audit_timeout_s", 900)),
    )
    result["commands"].append(audit)
    result["artifacts"].append(str(ask_run_dir))

    by_node = _read_ask_responses_by_node(ask_run_dir)
    seat_failures = read_seat_failures(ask_run_dir)
    result["seat_failures"] = seat_failures
    seat_verdicts = {node: _extract_verdict(text) for node, text in by_node.items()}
    result["seat_verdicts"] = seat_verdicts
    answered = [v for v in seat_verdicts.values() if v]

    # A closure is upheld only if every seat that answered says so, and only if
    # the whole panel answered. Any FAIL reopens: one competent reviewer showing
    # the named proof was never run is decisive, and a closure is a claim that
    # has to be established rather than a default to fall back on.
    if any(v == "FAIL" for v in answered):
        verdict = "FAIL"
    elif answered and len(answered) == len(auditors) and all(v == "PASS" for v in answered):
        verdict = "PASS"
    elif any(v == "NEEDS_ATTENTION" for v in answered):
        verdict = "NEEDS_ATTENTION"
    else:
        verdict = None
    result["verdict"] = verdict
    response = "\n\n".join(
        f"### {node}\n{text.strip()}" for node, text in sorted(by_node.items())
    )

    if (audit.get("exit_code") != 0 and verdict != "NEEDS_ATTENTION") or verdict is None:
        # No verdict is not a pass. Leave the ticket closed and say so, rather
        # than reopening on a failed reviewer or silently accepting.
        result.update(
            {
                "ok": False,
                "status": "NEEDS_ATTENTION",
                "summary": (
                    f"closure audit of {repo}#{issue_number} produced no usable panel verdict "
                    f"(exit {audit.get('exit_code')}, seats {seat_verdicts}"
                    + (f", failures {seat_failures}" if seat_failures else "")
                    + "). The closure is unreviewed, not accepted."
                ),
            }
        )
        log_event(run_id, "closure_audit_no_verdict", issue=issue_number)
        return result

    if verdict == "PASS":
        result["commands"].append(
            github.issue_comment(
                repo,
                issue_number,
                github.watchdog_comment(
                    "Closure audit: PASS",
                    {
                        "schema": "agent_skills.project_watchdog.closure_audit.v1",
                        "marker": CLOSURE_AUDIT_MARKER,
                        "run_id": run_id,
                        "issue": f"issue#{issue_number}",
                        "repo": repo,
                        "auditors": auditors,
                        "seat_verdicts": seat_verdicts,
                        "verdict": verdict,
                        "outcome": "closure_upheld",
                    },
                ),
            )
        )
        # The label is what stops this closure being re-audited every tick, so a
        # failed edit is not cosmetic. Observed: `closure-verified` existed in no
        # repo and was absent from ensure-labels, so the first unanimous PASS
        # marked nothing.
        mark = github.issue_edit(repo, issue_number, add=[config.CLOSURE_VERIFIED_LABEL])
        result["commands"].append(mark)
        if mark.get("exit_code") != 0:
            result.update(
                {
                    "ok": False,
                    "status": "NEEDS_ATTENTION",
                    "summary": (
                        f"closure of {repo}#{issue_number} was upheld but "
                        f"{config.CLOSURE_VERIFIED_LABEL!r} could not be applied: "
                        f"{str(mark.get('stderr'))[:160]}. Without it the same closure is "
                        f"re-audited every tick. Run: skills/ticket/run.sh ensure-labels "
                        f"--repo {repo}"
                    ),
                }
            )
            log_event(run_id, "closure_verified_label_failed", issue=issue_number)
            return result
        result.update(
            {
                "ok": True,
                "status": "COMPLETED",
                "summary": (
                    f"closure of {repo}#{issue_number} upheld unanimously by {auditors}"
                ),
            }
        )
        log_event(run_id, "closure_audit_pass", issue=issue_number)
        return result

    if verdict == "NEEDS_ATTENTION":
        # "I cannot tell from what is here" is not a finding that the work is
        # wrong. Reopening on it would churn every ticket whose proof lives in
        # an artifact the auditor cannot read. Say so and leave it closed.
        audit_triage = None
        if audit.get("exit_code") != 0:
            audit_triage = {
                "code": CLOSURE_AUDIT_NONZERO_NEEDS_ATTENTION_CODE,
                "layer": "project-watchdog",
                "cause": (
                    "Ask/Tau exited nonzero while closure-audit seats declared "
                    "VERDICT: NEEDS_ATTENTION. The semantic verdict is usable; "
                    "the watchdog must make it durable with closure-unverified or cooldown."
                ),
                "next_command": (
                    f"Ensure {config.CLOSURE_UNVERIFIED_LABEL!r} exists for {repo}, "
                    "then re-run the project-watchdog closure-audit regression eval."
                ),
            }
            result["triage"] = audit_triage
        result["commands"].append(
            github.issue_comment(
                repo,
                issue_number,
                github.watchdog_comment(
                    "Closure audit: NEEDS_ATTENTION",
                    {
                        "schema": "agent_skills.project_watchdog.closure_audit.v1",
                        "marker": CLOSURE_AUDIT_MARKER,
                        "run_id": run_id,
                        "issue": f"issue#{issue_number}",
                        "repo": repo,
                        "auditors": auditors,
                        "seat_verdicts": seat_verdicts,
                        "seat_failures": seat_failures,
                        "verdict": verdict,
                        "wrapper_exit_code": audit.get("exit_code"),
                        "wrapper_stderr_excerpt": str(audit.get("stderr", ""))[:1000],
                        "triage": audit_triage,
                        "outcome": "left_closed_unverified",
                        "reviewer_excerpt": response.strip()[:2000],
                    },
                ),
            )
        )
        # Same durability rule as closure-verified: without a label the scan
        # selects this closure again next tick and the panel re-answers the
        # identical question every minute (observed as a window-flash loop).
        mark = github.issue_edit(repo, issue_number, add=[config.CLOSURE_UNVERIFIED_LABEL])
        result["commands"].append(mark)
        if mark.get("exit_code") != 0:
            result.update(
                {
                    "ok": False,
                    "status": "NEEDS_ATTENTION",
                    "failure_code": (
                        audit_triage["code"] if audit_triage else "closure_unverified_label_failed"
                    ),
                    "summary": (
                        (f"[{audit_triage['code']}] " if audit_triage else "")
                        + f"closure of {repo}#{issue_number} was left unverified but "
                        f"{config.CLOSURE_UNVERIFIED_LABEL!r} could not be applied: "
                        f"{str(mark.get('stderr'))[:160]}. Without it the same closure is "
                        f"re-audited every tick. Run: skills/ticket/run.sh ensure-labels "
                        f"--repo {repo}"
                    ),
                }
            )
            log_event(run_id, "closure_unverified_label_failed", issue=issue_number)
            return result
        result.update(
            {
                "ok": True,
                "status": "NEEDS_ATTENTION",
                "failure_code": audit_triage["code"] if audit_triage else None,
                "summary": (
                    (f"[{audit_triage['code']}] " if audit_triage else "")
                    + f"closure of {repo}#{issue_number} could not be judged from the ticket "
                    f"thread; left closed and unverified rather than reopened "
                    f"(wrapper exit {audit.get('exit_code')}, seats {seat_verdicts}"
                    + (f", failures {seat_failures}" if seat_failures else "")
                    + ")"
                ),
            }
        )
        log_event(run_id, "closure_audit_inconclusive", issue=issue_number)
        return result

    # FAIL: a seat showed the closure does not hold.
    exhausted = reopens >= config.CLOSURE_AUDIT_MAX_REOPENS
    # Lead of the reviewer's reasoning, not the tail: taking the last N characters
    # started the excerpt mid-word and cut off the argument that justified it.
    excerpt = response.strip()[:2000]
    outcome = "reopen_budget_exhausted" if exhausted else "REOPENED"
    result["commands"].append(
        github.issue_comment(
            repo,
            issue_number,
            github.watchdog_comment(
                f"Closure audit: {verdict}",
                {
                    "schema": "agent_skills.project_watchdog.closure_audit.v1",
                    "marker": CLOSURE_AUDIT_MARKER,
                    "run_id": run_id,
                    "issue": f"issue#{issue_number}",
                    "repo": repo,
                    "auditors": auditors,
                    "seat_verdicts": seat_verdicts,
                    "verdict": verdict,
                    "outcome": outcome,
                    "prior_reopens": reopens,
                    "reviewer_excerpt": excerpt,
                },
            ),
        )
    )
    if exhausted:
        # Reopening again would loop. Hand it to a person instead.
        result["commands"].append(
            github.issue_edit(repo, issue_number, add=["needs-human"])
        )
        result.update(
            {
                "ok": False,
                "status": "NEEDS_ATTENTION",
                "summary": (
                    f"{repo}#{issue_number} failed closure audit {reopens + 1} times; "
                    f"not reopening again, needs a person."
                ),
            }
        )
        log_event(run_id, "closure_audit_reopen_budget_exhausted", issue=issue_number)
        return result

    result["commands"].append(github.issue_reopen(repo, issue_number))
    result["commands"].append(
        github.issue_edit(
            repo, issue_number, add=[config.READY_LABEL], remove=[config.CLOSURE_VERIFIED_LABEL]
        )
    )
    result.update(
        {
            "ok": True,
            "status": "COMPLETED",
            "summary": (
                f"reopened {repo}#{issue_number}: closure did not survive review ({verdict})"
            ),
        }
    )
    log_event(run_id, "closure_audit_reopened", issue=issue_number, verdict=verdict)
    return result


# --------------------------------------------------------------------------- #
# Completion attestation — "everything is closed" is also a claim
# --------------------------------------------------------------------------- #


def build_completion_attestation_task(*, repo: str, recent: list[dict[str, Any]]) -> str:
    """Ask an independent seat whether this project is genuinely finished."""
    # Include each ticket's audit status. Shown only titles and statuses, the
    # attestor correctly refused to certify anything -- "this ticket list is a
    # set of titles and statuses with no underlying evidence" -- so the lane
    # could only ever answer NEEDS_ATTENTION. Whether a closure was
    # independently reviewed and upheld is the fact worth weighing here.
    rows = []
    for i in recent[:40]:
        labels = {str(lbl.get("name")) for lbl in i.get("labels", [])}
        audited = (
            "audited+upheld" if config.CLOSURE_VERIFIED_LABEL in labels
            else "closure NOT independently verified"
        )
        rows.append(
            f"- #{i['number']} [{i.get('stateReason') or 'CLOSED'}] [{audited}] "
            f"{str(i.get('title', ''))[:100]}"
        )
    listing = "\n".join(rows) or "(no recently closed tickets)"
    return (
        f"Every agent-routable ticket in {repo} is closed. Decide whether each one "
        f"is legitimately closed, and whether the set as a whole means the work is "
        f"actually done.\n\n"
        f"Answer VERDICT: PASS if these closures look legitimate and nothing "
        f"obvious is missing. Answer VERDICT: FAIL if any ticket was closed without "
        f"the work plausibly being done, if a closure contradicts another, or if the "
        f"pattern looks like scope was quietly abandoned rather than completed. "
        f"Answer VERDICT: NEEDS_ATTENTION only if you genuinely cannot tell.\n\n"
        f"If you answer FAIL, list the tickets to reopen on their own final line, "
        f"exactly:\n\n"
        f"REOPEN: #123, #456\n\n"
        f"Each ticket is marked with whether its closure was independently "
        f"reviewed and upheld by the closure audit. A repo where most closures "
        f"were never verified is weaker evidence of completion than the same "
        f"list where they were; say that rather than guess from titles.\n\n"
        f"List only tickets from the set below, and only ones you can say are "
        f"wrongly closed. Reopening is not free: each one goes back to a repair "
        f"agent. An empty queue is not evidence of a finished project -- it is "
        f"equally consistent with nobody filing the remaining work.\n\n"
        f"--- recently closed ---\n{listing}"
    )


def handle_completion_attestation(
    run_id: str,
    receipt_dir: Path,
    project: dict[str, Any],
    recent: list[dict[str, Any]],
    *,
    apply: bool,
) -> dict[str, Any]:
    """Independent check that a project with nothing open is genuinely done.

    Every judgement up to here came from the API-routed models that did and
    reviewed the work. This asks a different transport entirely, so "everything
    is done" is not self-certified by the system that did it.
    """
    repo = project_repo(project)
    attestor = config.completion_attestor(project)
    result = {
        "project_id": project.get("project_id"),
        "repo": repo,
        "action": "completion_attestation",
        "selected_agent": attestor,
        "ok": False,
        "commands": [],
        "artifacts": [],
    }
    log_event(run_id, "completion_attestation_start", repo=repo, attestor=attestor)

    task = build_completion_attestation_task(repo=repo, recent=recent)
    if not apply:
        result.update(
            {
                "ok": True,
                "status": "DRY_RUN",
                "summary": f"would ask {attestor} whether {repo} is genuinely finished",
            }
        )
        return result

    task_path = receipt_dir / "completion-attestation.md"
    task_path.write_text(task, encoding="utf-8")
    result["artifacts"].append(str(task_path))

    run_dir = receipt_dir / "completion-attestation"
    attest = run_cmd(
        [
            str(config.ask_run_sh()),
            "tau-dag",
            task,
            "--repo", repo,
            "--target", "project-completion",
            "--immutable-goal", (
                f"Decide whether {repo} is genuinely finished, or whether an empty "
                f"ticket queue is hiding unfiled work. Name the specific gap if there is one."
            ),
            "--dag-template", "single-call",
            "--handler", attestor,
            "--run-output-root", str(run_dir),
            "--execute",
            "--allow-provider-calls",
            "--json",
        ],
        cwd=config.ask_run_sh().parent,
        timeout_s=int(project.get("completion_attest_timeout_s", 1200)),
    )
    result["commands"].append(attest)
    result["artifacts"].append(str(run_dir))

    response = _read_ask_response(run_dir)
    verdict = _extract_verdict(response)
    result["verdict"] = verdict
    result["excerpt"] = response.strip()[:2000]

    if attest.get("exit_code") != 0 or verdict is None:
        result.update(
            {
                "ok": False,
                "status": "NEEDS_ATTENTION",
                "summary": (
                    f"completion attestation for {repo} produced no verdict "
                    f"(exit {attest.get('exit_code')}). Not attested."
                ),
            }
        )
        log_event(run_id, "completion_attestation_no_verdict", repo=repo)
        return result

    if verdict == "PASS":
        result.update(
            {"ok": True, "status": "COMPLETED", "summary": f"{attestor} attests {repo} is finished"}
        )
        log_event(run_id, "completion_attestation_verdict", repo=repo, verdict="PASS")
        return result

    # FAIL: reopen exactly what it named, so the repair lane picks them up and
    # the cycle runs again. NEEDS_ATTENTION reopens nothing -- "cannot tell" is
    # not a finding.
    reopen = extract_reopen_list(response, allowed={int(i["number"]) for i in recent})
    result["reopen_requested"] = reopen
    reopened: list[int] = []
    if verdict == "FAIL":
        for number in reopen:
            r = github.issue_reopen(repo, number)
            result["commands"].append(r)
            if r.get("exit_code") != 0:
                continue
            result["commands"].append(
                github.issue_edit(
                    repo, number,
                    add=[config.READY_LABEL],
                    remove=[config.CLOSURE_VERIFIED_LABEL],
                )
            )
            result["commands"].append(
                github.issue_comment(
                    repo, number,
                    github.watchdog_comment(
                        "Reopened by completion attestation",
                        {
                            "schema": "agent_skills.project_watchdog.completion_attestation.v1",
                            "run_id": run_id,
                            "repo": repo,
                            "attestor": attestor,
                            "verdict": verdict,
                            "reason": "not legitimately closed",
                            "excerpt": response.strip()[:1500],
                        },
                    ),
                )
            )
            reopened.append(number)
    result["reopened"] = reopened
    result.update(
        {
            "ok": False,
            "status": "NEEDS_ATTENTION",
            "summary": (
                f"{attestor} does not attest {repo} is finished ({verdict}); "
                f"reopened {reopened or 'nothing'}"
            ),
        }
    )
    log_event(run_id, "completion_attestation_verdict", repo=repo, verdict=verdict,
              reopened=reopened)
    return result


_REOPEN_LINE = re.compile(r"^\s*REOPEN:\s*(.+)$", re.MULTILINE | re.IGNORECASE)


def extract_reopen_list(text: str, *, allowed: set[int]) -> list[int]:
    """Ticket numbers the attestor asked to reopen.

    Restricted to the set it was shown. A model naming a number outside that set
    is guessing, and reopening on a guess sends a repair agent at a ticket
    nobody reviewed.
    """
    numbers: list[int] = []
    for match in _REOPEN_LINE.finditer(text):
        for token in re.findall(r"#?(\d+)", match.group(1)):
            number = int(token)
            if number in allowed and number not in numbers:
                numbers.append(number)
    return numbers
