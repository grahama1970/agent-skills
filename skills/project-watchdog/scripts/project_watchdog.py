#!/usr/bin/env python3
"""Project Watchdog: cross-project GitHub issue cron runner."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any

import typer

SKILL_DIR = Path(__file__).resolve().parents[1]
REGISTRY_DIR = SKILL_DIR / "registry"
PROJECTS_PATH = REGISTRY_DIR / "projects.json"
STATE_PATH = REGISTRY_DIR / "state.json"
STATE_ROOT = Path.home() / ".local" / "state" / "project-watchdog"
LOG_DIR = STATE_ROOT / "logs"
RECEIPT_ROOT = STATE_ROOT / "receipts"
LOCK_DIR = STATE_ROOT / "lock"
CRON_MARKER = "# project-watchdog global issue cron"
TAU_REPAIR_MARKER = "project-watchdog-action:add-tau-coder-command-spec"
TAU_HANDOFF_DISPATCH_MARKER = "project-watchdog-action:tau-handoff-dispatch"
TAU_ROOT = Path("/home/graham/workspace/experiments/tau")
TAU_CODER_SPEC = (
    TAU_ROOT
    / "experiments/goal-locked-subagents/agent-command-specs/coder/tau-dispatch-command.json"
)
AGENTS_ROOT = Path("/home/graham/workspace/experiments/agent-skills/agents")
TAU_ACTIVE_GOAL_HASH = "sha256:1111111111111111111111111111111111111111111111111111111111111111"
UV_BIN = Path("/home/graham/.local/bin/uv")
app = typer.Typer(add_completion=False, help="Run one bounded project watchdog tick.")


@app.command("tick")
def tick_command(
    apply: bool = typer.Option(False, "--apply", help="Apply mutations instead of dry-run scan."),
    project: str = typer.Option("tau", "--project", help="Registered project id."),
    max_tickets: int = typer.Option(1, "--max-tickets", min=1, help="Maximum issues to handle."),
) -> None:
    """Scan and handle at most one bounded project ticket."""
    ensure_dirs()
    raise typer.Exit(tick(apply=apply, project_id=project, max_tickets=max_tickets))


@app.command("install-cron")
def install_cron_command(
    apply: bool = typer.Option(False, "--apply", help="Install the crontab entry."),
    minute: str = typer.Option("*", "--minute", help="Cron minute field."),
) -> None:
    """Install or dry-run the project-watchdog cron line."""
    ensure_dirs()
    raise typer.Exit(install_cron(apply=apply, minute=minute))


@app.command("set-state")
def set_state_command(
    scope: str = typer.Argument(..., help="global or project"),
    state: str = typer.Argument(..., help="active, paused, or stopped"),
    project: str = typer.Option("tau", "--project", help="Project id when scope=project."),
    reason: str = typer.Option("operator request", "--reason", help="State transition reason."),
) -> None:
    """Set global or per-project watchdog state."""
    if scope not in {"global", "project"}:
        typer.echo("scope must be global or project", err=True)
        raise typer.Exit(2)
    if state not in {"active", "paused", "stopped"}:
        typer.echo("state must be active, paused, or stopped", err=True)
        raise typer.Exit(2)
    ensure_dirs()
    raise typer.Exit(set_state(scope, state, project_id=project, reason=reason))


@app.command("status")
def status_command() -> None:
    """Print watchdog registry, state, log, and cron status."""
    ensure_dirs()
    print(json.dumps(status_payload(), indent=2, sort_keys=True))


def ensure_dirs() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    RECEIPT_ROOT.mkdir(parents=True, exist_ok=True)


def timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def log_event(run_id: str, message: str, **fields: Any) -> None:
    event = {
        "ts": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "run_id": run_id,
        "message": message,
        **fields,
    }
    with (LOG_DIR / "project-watchdog.log").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")


def run_cmd(
    command: list[str],
    *,
    cwd: Path | None = None,
    input_text: str | None = None,
    timeout_s: int = 120,
) -> dict[str, Any]:
    started = datetime.now(UTC)
    env = os.environ.copy()
    env["PATH"] = f"{UV_BIN.parent}:{env.get('PATH', '')}"
    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        env=env,
        input=input_text,
        text=True,
        capture_output=True,
        timeout=timeout_s,
        check=False,
    )
    return {
        "command": command,
        "cwd": str(cwd) if cwd else None,
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "duration_seconds": (datetime.now(UTC) - started).total_seconds(),
    }


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} root must be a JSON object")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def tick(*, apply: bool, project_id: str, max_tickets: int) -> int:
    run_id = f"project-watchdog-{timestamp()}"
    receipt_dir = RECEIPT_ROOT / run_id
    receipt_dir.mkdir(parents=True, exist_ok=True)
    log_event(run_id, "tick_start", apply=apply, project_id=project_id, max_tickets=max_tickets)

    if not acquire_lock(run_id):
        receipt = base_receipt(run_id, receipt_dir, apply)
        receipt.update({"ok": False, "status": "BLOCKED", "errors": ["lock already held"]})
        return finish(run_id, receipt_dir, receipt, 1)
    try:
        return tick_locked(run_id, receipt_dir, apply=apply, project_id=project_id, max_tickets=max_tickets)
    finally:
        release_lock()


def tick_locked(
    run_id: str,
    receipt_dir: Path,
    *,
    apply: bool,
    project_id: str,
    max_tickets: int,
) -> int:
    receipt = base_receipt(run_id, receipt_dir, apply)
    projects = load_json(PROJECTS_PATH)
    state = load_json(STATE_PATH)
    receipt["state_snapshot"] = state

    global_state = state.get("global", {}).get("state")
    if global_state != "active":
        receipt.update({"ok": True, "status": "SKIPPED", "stop_reason": f"global_state_{global_state}"})
        log_event(run_id, "tick_skipped", reason=receipt["stop_reason"])
        return finish(run_id, receipt_dir, receipt, 0)

    project = find_project(projects, project_id)
    project_state = state.get("projects", {}).get(project_id, {}).get("state")
    if project_state != "active":
        receipt.update({"ok": True, "status": "SKIPPED", "stop_reason": f"project_state_{project_state}"})
        log_event(run_id, "project_skipped", reason=receipt["stop_reason"])
        return finish(run_id, receipt_dir, receipt, 0)

    issues = list_routable_tau_issues(run_id, project)
    receipt["scanned_issues"] = issues
    if not issues:
        receipt.update({"ok": True, "status": "NOOP", "stop_reason": "no_routable_issues"})
        log_event(run_id, "no_routable_issues")
        return finish(run_id, receipt_dir, receipt, 0)

    handled = 0
    for issue in issues[:max_tickets]:
        handled += 1
        if issue.get("watchdog_action") == "tau_handoff_dispatch":
            result = handle_tau_handoff_dispatch_issue(run_id, receipt_dir, issue, apply=apply)
        else:
            result = handle_tau_coder_spec_issue(run_id, receipt_dir, issue, apply=apply)
        receipt.setdefault("handled_issues", []).append(result)
    receipt["handled_count"] = handled
    receipt["ok"] = all(item.get("ok") for item in receipt.get("handled_issues", []))
    receipt["status"] = "COMPLETED" if receipt["ok"] else "NEEDS_ATTENTION"
    return finish(run_id, receipt_dir, receipt, 0 if receipt["ok"] else 1)


def base_receipt(run_id: str, receipt_dir: Path, apply: bool) -> dict[str, Any]:
    return {
        "schema": "agent_skills.project_watchdog.tick_receipt.v1",
        "run_id": run_id,
        "mocked": False,
        "live": True,
        "apply": apply,
        "receipt_dir": str(receipt_dir),
        "log_file": str(LOG_DIR / "project-watchdog.log"),
        "cron_log_file": str(LOG_DIR / "cron.log"),
        "handled_issues": [],
        "errors": [],
    }


def finish(run_id: str, receipt_dir: Path, receipt: dict[str, Any], exit_code: int) -> int:
    receipt_path = receipt_dir / "receipt.json"
    receipt["receipt_path"] = str(receipt_path)
    write_json(receipt_path, receipt)
    log_event(
        run_id,
        "tick_finish",
        status=receipt.get("status"),
        ok=receipt.get("ok"),
        receipt_path=str(receipt_path),
        exit_code=exit_code,
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return exit_code


def acquire_lock(run_id: str) -> bool:
    try:
        LOCK_DIR.mkdir(parents=True)
    except FileExistsError:
        return False
    (LOCK_DIR / "owner.json").write_text(
        json.dumps({"run_id": run_id, "pid": os.getpid(), "ts": timestamp()}, indent=2) + "\n",
        encoding="utf-8",
    )
    return True


def release_lock() -> None:
    try:
        (LOCK_DIR / "owner.json").unlink(missing_ok=True)
        LOCK_DIR.rmdir()
    except FileNotFoundError:
        return
    except OSError:
        return


def find_project(projects: dict[str, Any], project_id: str) -> dict[str, Any]:
    for project in projects.get("projects", []):
        if project.get("project_id") == project_id:
            return project
    raise ValueError(f"unknown project_id: {project_id}")


def list_routable_tau_issues(run_id: str, project: dict[str, Any]) -> list[dict[str, Any]]:
    repo = str(project["repo"])
    command = [
        "gh",
        "issue",
        "list",
        "--repo",
        repo,
        "--state",
        "open",
        "--label",
        "agent-work",
        "--limit",
        "50",
        "--json",
        "number,title,body,labels,url",
    ]
    result = run_cmd(command, timeout_s=60)
    log_event(run_id, "github_issue_scan", repo=repo, exit_code=result["exit_code"])
    if result["exit_code"] != 0:
        raise RuntimeError(f"gh issue list failed: {result['stderr']}")
    issues = json.loads(result["stdout"] or "[]")
    routable: list[dict[str, Any]] = []
    for issue in issues:
        labels = {label.get("name") for label in issue.get("labels", [])}
        if "agent-active" in labels or "agent-blocked" in labels:
            continue
        body = issue.get("body") or ""
        if (
            "next:coder" in labels
            and "executor:local" in labels
            and TAU_REPAIR_MARKER in body
        ):
            issue["watchdog_action"] = "add_tau_coder_command_spec"
            routable.append(issue)
        elif (
            "executor:local" in labels
            and TAU_HANDOFF_DISPATCH_MARKER in body
        ):
            issue["watchdog_action"] = "tau_handoff_dispatch"
            routable.append(issue)
    return routable


def parse_issue_fields(body: str) -> dict[str, str]:
    """Extract shell-style key=value fields from a GitHub issue body."""
    fields: dict[str, str] = {}
    for token in shlex.split(body.replace("\r", " ")):
        key, sep, value = token.partition("=")
        if sep:
            fields[key.strip()] = value.strip()
    return fields


def repo_relative_existing_path(value: str) -> Path:
    """Return a safe repo-relative Tau path or raise ValueError."""
    posix_path = PurePosixPath(value)
    if posix_path.is_absolute() or ".." in posix_path.parts:
        raise ValueError(f"start path must be repo-relative without '..': {value}")
    path = TAU_ROOT / Path(value)
    if not path.is_file():
        raise ValueError(f"start handoff path does not exist: {value}")
    return path


def parse_positive_int(value: str, *, field: str) -> int:
    if not value.isdecimal() or int(value) < 1:
        raise ValueError(f"{field} must be a positive integer: {value}")
    return int(value)


def parse_bool(value: str, *, field: str) -> bool:
    normalized = value.lower()
    if normalized not in {"true", "false"}:
        raise ValueError(f"{field} must be true or false: {value}")
    return normalized == "true"


def handle_tau_handoff_dispatch_issue(
    run_id: str,
    receipt_dir: Path,
    issue: dict[str, Any],
    *,
    apply: bool,
) -> dict[str, Any]:
    issue_number = int(issue["number"])
    issue_url = str(issue["url"])
    log_event(run_id, "handle_handoff_dispatch_start", issue=issue_number, url=issue_url)
    result: dict[str, Any] = {
        "project_id": "tau",
        "issue_number": issue_number,
        "issue_url": issue_url,
        "selected_agent": None,
        "action": "tau_handoff_dispatch",
        "ok": False,
        "commands": [],
        "artifacts": [],
    }
    body = issue.get("body") or ""
    try:
        fields = parse_issue_fields(body)
        start_path = repo_relative_existing_path(fields["start"])
        max_steps = parse_positive_int(fields.get("max_steps", "1"), field="max_steps")
        active_goal_hash = fields.get("active_goal_hash", TAU_ACTIVE_GOAL_HASH)
        if not active_goal_hash.startswith("sha256:"):
            raise ValueError(f"active_goal_hash must start with sha256:: {active_goal_hash}")
        apply_transport = parse_bool(fields.get("apply_transport", "false"), field="apply_transport")
    except KeyError:
        result.update({"ok": False, "status": "BLOCKED", "summary": "missing required start field"})
        return result
    except ValueError as exc:
        result.update({"ok": False, "status": "BLOCKED", "summary": str(exc)})
        return result

    resolved = {
        "schema": "agent_skills.project_watchdog.tau_handoff_dispatch_inputs.v1",
        "issue": f"issue#{issue_number}",
        "issue_url": issue_url,
        "start": str(start_path.relative_to(TAU_ROOT)),
        "max_steps": max_steps,
        "active_goal_hash": active_goal_hash,
        "apply_transport": apply_transport,
    }
    resolved_path = receipt_dir / "tau-handoff-dispatch-inputs.json"
    write_json(resolved_path, resolved)
    result["artifacts"].append(str(resolved_path))

    if not apply:
        result.update({"ok": True, "status": "DRY_RUN", "summary": "would run Tau handoff dispatch"})
        return result

    lease_body = watchdog_comment(
        "Lease acquired",
        {
            "schema": "agent_skills.project_watchdog.lease.v1",
            "run_id": run_id,
            "issue": f"issue#{issue_number}",
            "selected_agent": "tau-handoff-dispatch",
            "action": "tau_handoff_dispatch",
            "inputs": resolved,
        },
    )
    result["commands"].append(gh_issue_comment(issue_number, lease_body))
    result["commands"].append(gh_issue_edit(issue_number, add=["agent-active"], remove=[]))

    loop_dir = receipt_dir / "tau-command-loop"
    loop_command = [
        str(UV_BIN),
        "run",
        "tau",
        "handoff-command-loop",
        "--start",
        str(start_path),
        "--receipt-dir",
        str(loop_dir),
        "--agents-root",
        str(AGENTS_ROOT),
        "--command-spec-root",
        str(TAU_ROOT / "experiments/goal-locked-subagents/agent-command-specs"),
        "--active-goal-hash",
        active_goal_hash,
        "--max-steps",
        str(max_steps),
    ]
    loop_result = run_cmd(loop_command, cwd=TAU_ROOT, timeout_s=120)
    result["commands"].append(loop_result)
    loop_receipt = loop_dir / "command-loop-receipt.json"
    result["artifacts"].append(str(loop_receipt))

    transport_path = receipt_dir / "tau-github-transport.json"
    transport_command = [
        str(UV_BIN),
        "run",
        "tau",
        "handoff-command-loop-github-transport",
        str(loop_receipt),
        "--receipt",
        str(transport_path),
    ]
    if apply_transport:
        transport_command.append("--apply")
    transport_result = run_cmd(transport_command, cwd=TAU_ROOT, timeout_s=120)
    result["commands"].append(transport_result)
    result["artifacts"].append(str(transport_path))

    if loop_result["exit_code"] != 0 or transport_result["exit_code"] != 0:
        result.update({"ok": False, "status": "NEEDS_ATTENTION", "summary": "Tau handoff dispatch failed"})
        result["commands"].append(gh_issue_edit(issue_number, add=["agent-blocked"], remove=["agent-active"]))
        return result

    evidence_body = watchdog_comment(
        "Tau handoff dispatch evidence",
        {
            "schema": "agent_skills.project_watchdog.tau_handoff_dispatch_receipt.v1",
            "run_id": run_id,
            "issue": f"issue#{issue_number}",
            "inputs": resolved,
            "loop_exit_code": loop_result["exit_code"],
            "transport_exit_code": transport_result["exit_code"],
            "command_loop_receipt": str(loop_receipt),
            "github_transport_receipt": str(transport_path),
            "mocked": False,
            "live": True,
            "scope": "Runs one bounded Tau handoff command-loop tick from a GitHub issue and renders or applies terminal GitHub transport.",
        },
    )
    result["commands"].append(gh_issue_comment(issue_number, evidence_body))
    result["commands"].append(
        gh_issue_edit(
            issue_number,
            add=["agent-done"],
            remove=["agent-active", "next:coder", "next:reviewer", "executor:local"],
        )
    )
    close = run_cmd(["gh", "issue", "close", str(issue_number), "--repo", "grahama1970/tau", "--reason", "completed"])
    result["commands"].append(close)
    result.update({"ok": close["exit_code"] == 0, "status": "COMPLETED", "summary": "Tau handoff dispatch executed"})
    log_event(run_id, "handle_handoff_dispatch_finish", issue=issue_number, ok=result["ok"])
    return result


def handle_tau_coder_spec_issue(
    run_id: str,
    receipt_dir: Path,
    issue: dict[str, Any],
    *,
    apply: bool,
) -> dict[str, Any]:
    issue_number = int(issue["number"])
    issue_url = str(issue["url"])
    log_event(run_id, "handle_issue_start", issue=issue_number, url=issue_url)
    result: dict[str, Any] = {
        "project_id": "tau",
        "issue_number": issue_number,
        "issue_url": issue_url,
        "selected_agent": "coder",
        "action": "add_tau_coder_command_spec",
        "ok": False,
        "commands": [],
        "artifacts": [],
    }
    if not apply:
        result.update({"ok": True, "status": "DRY_RUN", "summary": "would add coder command spec"})
        return result

    lease_body = watchdog_comment(
        "Lease acquired",
        {
            "schema": "agent_skills.project_watchdog.lease.v1",
            "run_id": run_id,
            "issue": f"issue#{issue_number}",
            "selected_agent": "coder",
            "action": "add_tau_coder_command_spec",
        },
    )
    result["commands"].append(gh_issue_comment(issue_number, lease_body))
    result["commands"].append(gh_issue_edit(issue_number, add=["agent-active"], remove=[]))

    write_tau_coder_command_spec()
    result["artifacts"].append(str(TAU_CODER_SPEC))

    start_handoff = make_tau_coder_start_handoff(issue_number, issue_url)
    start_path = receipt_dir / "tau-coder-start-handoff.json"
    write_json(start_path, start_handoff)
    result["artifacts"].append(str(start_path))

    loop_dir = receipt_dir / "tau-command-loop"
    command = [
        str(UV_BIN),
        "run",
        "tau",
        "handoff-command-loop",
        "--start",
        str(start_path),
        "--receipt-dir",
        str(loop_dir),
        "--agents-root",
        str(AGENTS_ROOT),
        "--command-spec-root",
        str(TAU_ROOT / "experiments/goal-locked-subagents/agent-command-specs"),
        "--active-goal-hash",
        TAU_ACTIVE_GOAL_HASH,
        "--max-steps",
        "2",
    ]
    loop_result = run_cmd(command, cwd=TAU_ROOT, timeout_s=120)
    result["commands"].append(loop_result)
    result["artifacts"].append(str(loop_dir / "command-loop-receipt.json"))

    targeted = run_cmd(
        [
            str(UV_BIN),
            "run",
            "--project",
            str(TAU_ROOT),
            "pytest",
            "-q",
            "tests/test_cli.py::test_cli_handoff_agent_adapter_emits_tau_handoff",
            "tests/test_subagent_receipt.py::test_headless_subagent_receipt_import_does_not_require_textual",
        ],
        cwd=TAU_ROOT,
        timeout_s=120,
    )
    result["commands"].append(targeted)

    git_status = run_cmd(["git", "status", "--short"], cwd=TAU_ROOT)
    result["commands"].append(git_status)
    if loop_result["exit_code"] != 0 or targeted["exit_code"] != 0:
        result.update({"ok": False, "status": "NEEDS_ATTENTION", "summary": "repair command failed"})
        result["commands"].append(gh_issue_edit(issue_number, add=["agent-blocked"], remove=["agent-active"]))
        return result

    run_cmd(["git", "add", str(TAU_CODER_SPEC.relative_to(TAU_ROOT))], cwd=TAU_ROOT)
    commit = run_cmd(["git", "commit", "-m", "Add Tau coder command spec overlay"], cwd=TAU_ROOT)
    result["commands"].append(commit)
    if commit["exit_code"] == 0:
        push = run_cmd(["git", "push", "grahama1970", "main"], cwd=TAU_ROOT, timeout_s=120)
        result["commands"].append(push)

    evidence_body = watchdog_comment(
        "Repair evidence",
        {
            "schema": "agent_skills.project_watchdog.repair_receipt.v1",
            "run_id": run_id,
            "issue": f"issue#{issue_number}",
            "selected_agent": "coder",
            "changed_file": str(TAU_CODER_SPEC.relative_to(TAU_ROOT)),
            "loop_exit_code": loop_result["exit_code"],
            "targeted_tests_exit_code": targeted["exit_code"],
            "command_loop_receipt": str(loop_dir / "command-loop-receipt.json"),
            "mocked": False,
            "live": True,
            "scope": "Adds the missing Tau coder command-spec overlay and verifies one command-loop route to coder.",
        },
    )
    result["commands"].append(gh_issue_comment(issue_number, evidence_body))
    result["commands"].append(
        gh_issue_edit(
            issue_number,
            add=["agent-done"],
            remove=["agent-active", "next:coder", "executor:local"],
        )
    )
    close = run_cmd(["gh", "issue", "close", str(issue_number), "--repo", "grahama1970/tau", "--reason", "completed"])
    result["commands"].append(close)
    result.update({"ok": close["exit_code"] == 0, "status": "COMPLETED", "summary": "coder command spec added"})
    log_event(run_id, "handle_issue_finish", issue=issue_number, ok=result["ok"])
    return result


def write_tau_coder_command_spec() -> None:
    payload = {
        "command": [
            str(UV_BIN),
            "run",
            "tau",
            "handoff-agent-adapter",
            "--result-status",
            "COMPLETED",
            "--result-summary",
            "Coder consumed the Tau handoff JSON contract through the Tau-owned command-spec overlay.",
            "--next-agent",
            "human",
            "--next-executor",
            "human",
            "--next-reason",
            "Human review is required after this bounded watchdog repair proof.",
            "--required-evidence",
            "Human reviews the watchdog receipt, Tau command-loop receipt, pushed commit, and issue comment.",
            "--stop-condition",
            "Human accepts, redirects, or requests another bounded subagent.",
        ],
        "cwd": ".",
        "timeout_s": 30,
    }
    write_json(TAU_CODER_SPEC, payload)


def make_tau_coder_start_handoff(issue_number: int, issue_url: str) -> dict[str, Any]:
    return {
        "schema": "tau.agent_handoff.v1",
        "github": {
            "repo": "grahama1970/tau",
            "target": f"issue#{issue_number}",
            "current_labels": ["agent-work", "next:coder", "executor:local"],
        },
        "goal": {
            "goal_id": "goal-project-watchdog-live-coder-spec",
            "goal_version": 1,
            "goal_hash": TAU_ACTIVE_GOAL_HASH,
        },
        "previous_subagent": "coder",
        "context": {
            "summary": "Project watchdog found Tau allows coder routes but lacks a coder command-spec overlay.",
            "artifacts": [issue_url, str(TAU_CODER_SPEC)],
        },
        "result": {
            "status": "NEEDS_AGENT",
            "summary": "Coder command-spec overlay is required for Tau cron to dispatch next:coder issues.",
            "evidence": [f"Missing before repair: {TAU_CODER_SPEC}"],
        },
        "rationale": "Tau's command-loop cannot run a selected coder subagent without a command-spec overlay.",
        "next_agent": {
            "name": "coder",
            "executor": "local",
            "reason": "Coder should consume the handoff and route to reviewer for independent validation.",
        },
        "required_evidence": [
            "Coder command-spec overlay exists.",
            "Tau command-loop selects coder and emits a schema-valid next handoff.",
        ],
        "stop_condition": "Coder routes to reviewer or Tau fails closed.",
    }


def watchdog_comment(title: str, payload: dict[str, Any]) -> str:
    return (
        f"## Project Watchdog: {title}\n\n"
        "<!-- project-watchdog:v1 -->\n"
        "```json\n"
        f"{json.dumps(payload, indent=2, sort_keys=True)}\n"
        "```\n"
    )


def gh_issue_comment(issue_number: int, body: str) -> dict[str, Any]:
    return run_cmd(
        ["gh", "issue", "comment", str(issue_number), "--repo", "grahama1970/tau", "--body", body],
        timeout_s=60,
    )


def gh_issue_edit(issue_number: int, *, add: list[str], remove: list[str]) -> dict[str, Any]:
    command = ["gh", "issue", "edit", str(issue_number), "--repo", "grahama1970/tau"]
    for label in add:
        command.extend(["--add-label", label])
    for label in remove:
        command.extend(["--remove-label", label])
    return run_cmd(command, timeout_s=60)


def install_cron(*, apply: bool, minute: str) -> int:
    run_id = f"project-watchdog-install-{timestamp()}"
    cron_log = LOG_DIR / "cron.log"
    command = (
        f"{minute} * * * * cd {shlex.quote(str(SKILL_DIR))} && "
        f"{shlex.quote(str(SKILL_DIR / 'run.sh'))} tick --apply --project tau --max-tickets 1 "
        f">> {shlex.quote(str(cron_log))} 2>&1 {CRON_MARKER}"
    )
    current = run_cmd(["crontab", "-l"])
    existing = current["stdout"] if current["exit_code"] == 0 else ""
    lines = [line for line in existing.splitlines() if CRON_MARKER not in line]
    lines.append(command)
    new_crontab = "\n".join(lines).rstrip() + "\n"
    receipt = {
        "schema": "agent_skills.project_watchdog.cron_install_receipt.v1",
        "run_id": run_id,
        "apply": apply,
        "cron_line": command,
        "cron_log": str(cron_log),
        "previous_had_entry": CRON_MARKER in existing,
        "mocked": False,
        "live": True,
    }
    if apply:
        install = run_cmd(["crontab", "-"], input_text=new_crontab)
        receipt["install_result"] = install
        receipt["ok"] = install["exit_code"] == 0
        receipt["status"] = "INSTALLED" if receipt["ok"] else "FAILED"
    else:
        receipt["ok"] = True
        receipt["status"] = "DRY_RUN"
    receipt_dir = RECEIPT_ROOT / run_id
    receipt_dir.mkdir(parents=True, exist_ok=True)
    return finish(run_id, receipt_dir, receipt, 0 if receipt["ok"] else 1)


def set_state(scope: str, state_value: str, *, project_id: str, reason: str) -> int:
    run_id = f"project-watchdog-state-{timestamp()}"
    state = load_json(STATE_PATH)
    if scope == "global":
        state.setdefault("global", {})["state"] = state_value
        state["global"]["reason"] = reason
    else:
        state.setdefault("projects", {}).setdefault(project_id, {})["state"] = state_value
        state["projects"][project_id]["reason"] = reason
    state["updated_at"] = datetime.now(UTC).date().isoformat()
    write_json(STATE_PATH, state)
    receipt = {
        "schema": "agent_skills.project_watchdog.state_change_receipt.v1",
        "run_id": run_id,
        "ok": True,
        "status": "UPDATED",
        "scope": scope,
        "project_id": project_id if scope == "project" else None,
        "state": state_value,
        "reason": reason,
        "mocked": False,
        "live": True,
    }
    receipt_dir = RECEIPT_ROOT / run_id
    receipt_dir.mkdir(parents=True, exist_ok=True)
    return finish(run_id, receipt_dir, receipt, 0)


def status_payload() -> dict[str, Any]:
    return {
        "schema": "agent_skills.project_watchdog.status.v1",
        "state": load_json(STATE_PATH),
        "project_count": len(load_json(PROJECTS_PATH).get("projects", [])),
        "log_file": str(LOG_DIR / "project-watchdog.log"),
        "cron_log_file": str(LOG_DIR / "cron.log"),
        "receipt_root": str(RECEIPT_ROOT),
        "cron_entries": run_cmd(["crontab", "-l"])["stdout"],
    }


if __name__ == "__main__":
    try:
        app()
    except Exception as exc:
        ensure_dirs()
        run_id = f"project-watchdog-error-{timestamp()}"
        log_event(run_id, "fatal_error", error=str(exc))
        print(f"project-watchdog error: {exc}", file=sys.stderr)
        raise
