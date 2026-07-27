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

import shlex
from pathlib import Path
from typing import Any

from . import config, github, herdr_space
from .core import log_event, run_cmd, write_json
from .issue_fields import (
    parse_bool,
    parse_goal_hash,
    parse_issue_fields,
    parse_positive_int,
    repo_relative_existing_path,
)
from .registry import project_repo, project_worktree


def run_bounded(
    command: list[str],
    *,
    worktree: Path,
    project: dict[str, Any],
    agent_name: str,
    timeout_s: int = 120,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Run one bounded dispatch through the project's configured backend.

    Returns ``(result_record, pane_block)``. ``result_record`` is always
    ``run_cmd``-shaped so callers branch on ``exit_code`` regardless of backend.
    ``pane_block`` is the Herdr receipt block, or ``None`` for local dispatch.
    """
    backend = config.dispatch_backend_for(project)
    if backend != "herdr":
        return run_cmd(command, cwd=worktree, timeout_s=timeout_s), None

    pane = herdr_space.dispatch_in_pane(
        agent_name=agent_name,
        command=["bash", "-lc", f"cd {shlex.quote(str(worktree))} && {shlex.join(command)}"],
        space_label=config.DISPATCH_SPACE_LABEL,
        timeout_s=timeout_s,
    )
    record = {
        "command": command,
        "cwd": str(worktree),
        "exit_code": 0 if pane.ok else (pane.exit_code if pane.exit_code is not None else 1),
        "stdout": "",
        "stderr": pane.error or "",
        "backend": "herdr_pane",
        "agent_name": pane.agent_name,
    }
    return record, pane.as_receipt_block()


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
                    "run_id": run_id,
                    "issue": f"issue#{issue_number}",
                    "selected_agent": "tau-handoff-dispatch",
                    "action": "tau_handoff_dispatch",
                    "inputs": resolved,
                },
            ),
        )
    )
    result["commands"].append(github.issue_edit(repo, issue_number, add=[config.LEASE_LABEL]))

    uv_bin = config.resolve_uv_bin()
    loop_dir = receipt_dir / "tau-command-loop"
    loop_receipt = loop_dir / "command-loop-receipt.json"
    loop_result, pane_block = run_bounded(
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
        worktree=worktree,
        project=project,
        agent_name=f"pw-{project.get('project_id')}-issue-{issue_number}",
        timeout_s=120,
    )
    result["commands"].append(loop_result)
    if pane_block:
        result["pane"] = pane_block
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
                    "run_id": run_id,
                    "issue": f"issue#{issue_number}",
                    "selected_agent": "coder",
                    "action": "add_tau_coder_command_spec",
                },
            ),
        )
    )
    result["commands"].append(github.issue_edit(repo, issue_number, add=[config.LEASE_LABEL]))

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
    loop_result, pane_block = run_bounded(
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
        worktree=worktree,
        project=project,
        agent_name=f"pw-{project.get('project_id')}-coderspec-{issue_number}",
        timeout_s=120,
    )
    result["commands"].append(loop_result)
    if pane_block:
        result["pane"] = pane_block
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
TICKET_REPAIR_RUNNERS = {"tau-command-loop"}


def handle_ticket_repair(
    run_id: str,
    receipt_dir: Path,
    project: dict[str, Any],
    issue: dict[str, Any],
    *,
    apply: bool,
) -> dict[str, Any]:
    """Repair one ordinary ``/ticket``-filed issue through the project's harness.

    This is the route for tickets filed the normal way: labelled ``agent-work``
    with a ``type:``/``route:`` vocabulary and no hand-authored body marker.
    Dispatch is delegated to the project's own repair surface rather than
    reimplemented here — for ``tau-command-loop`` projects that is
    ``tau self-fix tick --repo <repo> --issue <n>``, which owns subagent
    selection, receipt validation, and closure.

    Projects whose ``runner_kind`` has no bounded per-issue repair surface are
    refused with a named reason instead of being handed to a runner that cannot
    accept an issue number.
    """
    repo = project_repo(project)
    worktree = project_worktree(project)
    issue_number = int(issue["number"])
    runner_kind = str(project.get("runner_kind", ""))
    log_event(run_id, "handle_ticket_repair_start", issue=issue_number, repo=repo)
    result = _new_result(project, issue, "ticket_repair")
    result["selected_agent"] = "tau-self-fix"
    result["runner_kind"] = runner_kind

    if runner_kind not in TICKET_REPAIR_RUNNERS:
        result.update(
            {
                "ok": False,
                "status": "BLOCKED",
                "summary": (
                    f"project {project.get('project_id')!r} has runner_kind "
                    f"{runner_kind!r}, which exposes no bounded per-issue repair "
                    f"command. Supported: {sorted(TICKET_REPAIR_RUNNERS)}. Register a "
                    "bounded runner before enabling ticket_repair for this project."
                ),
            }
        )
        log_event(run_id, "handle_ticket_repair_unsupported", issue=issue_number, kind=runner_kind)
        return result

    if not apply:
        result.update(
            {
                "ok": True,
                "status": "DRY_RUN",
                "summary": f"would run tau self-fix tick for {repo}#{issue_number}",
            }
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
                    "run_id": run_id,
                    "issue": f"issue#{issue_number}",
                    "repo": repo,
                    "selected_agent": "tau-self-fix",
                    "action": "ticket_repair",
                },
            ),
        )
    )
    result["commands"].append(github.issue_edit(repo, issue_number, add=[config.LEASE_LABEL]))

    repair_dir = receipt_dir / "self-fix"
    repair_result, pane_block = run_bounded(
        [
            config.resolve_uv_bin(),
            "run",
            "tau",
            "self-fix",
            "tick",
            "--repo",
            repo,
            "--issue",
            str(issue_number),
            "--receipt-dir",
            str(repair_dir),
        ],
        worktree=worktree,
        project=project,
        agent_name=f"pw-{project.get('project_id')}-ticket-{issue_number}",
        timeout_s=int(project.get("ticket_repair_timeout_s", 900)),
    )
    result["commands"].append(repair_result)
    result["artifacts"].append(str(repair_dir))
    if pane_block:
        result["pane"] = pane_block

    if repair_result["exit_code"] != 0:
        result.update(
            {
                "ok": False,
                "status": "NEEDS_ATTENTION",
                "summary": f"tau self-fix tick failed for {repo}#{issue_number}",
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
                    "self_fix_exit_code": repair_result["exit_code"],
                    "receipt_dir": str(repair_dir),
                    "mocked": False,
                    "live": True,
                    "scope": (
                        "Runs one bounded Tau self-fix tick against a /ticket-filed "
                        "GitHub issue. Closure is owned by Tau's self-fix receipt, "
                        "not by this watchdog."
                    ),
                },
            ),
        )
    )
    result["commands"].append(github.issue_edit(repo, issue_number, remove=[config.LEASE_LABEL]))
    result.update(
        {
            "ok": True,
            "status": "COMPLETED",
            "summary": f"tau self-fix tick completed for {repo}#{issue_number}",
        }
    )
    log_event(run_id, "handle_ticket_repair_finish", issue=issue_number, ok=True)
    return result
