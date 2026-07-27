"""Top-level watchdog commands: tick, cron install, state transitions, status.

Purpose
    Sequence the primitives into the four operations the CLI exposes. This is
    the only module that decides *when* the watchdog scans, dispatches, or
    refuses.

Inputs
    CLI arguments, ``registry/projects.json``, and ``registry/state.json``.

Outputs
    Receipts printed to stdout and, for eventful runs, persisted under
    ``config.receipt_root()/<run_id>/receipt.json``.

Failure modes
    - State is fail-closed: anything other than ``active`` at either the global
      or the project scope refuses to dispatch.
    - A scan that cannot reach GitHub raises, producing a ``BLOCKED`` receipt
      rather than an empty-queue ``NOOP``. Reporting a failed scan as "no work"
      is the single most dangerous bug this module can have.
    - The single-tick lock prevents overlapping cron runs; a stale lock is
      reclaimed after ``config.LOCK_STALE_SECONDS``.
"""

from __future__ import annotations

import json
import shlex
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loguru import logger

from . import config, streaks
from .core import (
    acquire_lock,
    base_receipt,
    finish,
    load_json,
    log_event,
    release_lock,
    run_cmd,
    timestamp,
    write_json,
)
from .handlers import handle_issue
from .registry import find_project, list_routable_issues


def tick(*, apply: bool, project_id: str, max_tickets: int) -> int:
    """Run one bounded watchdog tick under the single-tick lock."""
    run_id = f"project-watchdog-{timestamp()}"
    receipt_dir = config.receipt_root() / run_id
    receipt_dir.mkdir(parents=True, exist_ok=True)
    log_event(run_id, "tick_start", apply=apply, project_id=project_id, max_tickets=max_tickets)

    if not acquire_lock(run_id):
        receipt = base_receipt(run_id, receipt_dir, apply)
        receipt.update({"ok": False, "status": "BLOCKED", "errors": ["lock already held"]})
        return finish(run_id, receipt_dir, receipt, 1, persist=False)
    try:
        return _tick_locked(
            run_id, receipt_dir, apply=apply, project_id=project_id, max_tickets=max_tickets
        )
    finally:
        release_lock()


def _tick_locked(
    run_id: str,
    receipt_dir: Path,
    *,
    apply: bool,
    project_id: str,
    max_tickets: int,
) -> int:
    receipt = base_receipt(run_id, receipt_dir, apply)
    state = load_json(config.STATE_PATH)
    receipt["state_snapshot"] = state

    global_state = state.get("global", {}).get("state")
    if global_state != "active":
        receipt.update(
            {"ok": True, "status": "SKIPPED", "stop_reason": f"global_state_{global_state}"}
        )
        log_event(run_id, "tick_skipped", reason=receipt["stop_reason"])
        return finish(run_id, receipt_dir, receipt, 0)

    try:
        project = find_project(load_json(config.PROJECTS_PATH), project_id)
    except ValueError as exc:
        receipt.update({"ok": False, "status": "BLOCKED", "errors": [str(exc)]})
        logger.error("{}", exc)
        return finish(run_id, receipt_dir, receipt, 2)

    project_state = state.get("projects", {}).get(project_id, {}).get("state")
    if project_state != "active":
        receipt.update(
            {"ok": True, "status": "SKIPPED", "stop_reason": f"project_state_{project_state}"}
        )
        log_event(run_id, "project_skipped", reason=receipt["stop_reason"])
        return finish(run_id, receipt_dir, receipt, 0)

    try:
        issues = list_routable_issues(run_id, project)
    except (RuntimeError, ValueError) as exc:
        receipt.update({"ok": False, "status": "BLOCKED", "errors": [f"issue scan failed: {exc}"]})
        logger.error("issue scan failed for project {}: {}", project_id, exc)
        return finish(run_id, receipt_dir, receipt, 1)

    receipt["scanned_issues"] = issues
    if not issues:
        streak = streaks.record_idle(project_id)
        receipt["idle_streak"] = streak.as_receipt_block()
        if streak.escalated:
            receipt.update(
                {
                    "ok": True,
                    "status": "NEEDS_ATTENTION",
                    "stop_reason": "idle_streak_exceeded",
                    "summary": (
                        f"{project_id} has had no routable issue for "
                        f"{streak.idle_seconds / 3600:.1f}h across "
                        f"{streak.consecutive_ticks} ticks. A scan that never "
                        f"matches is a defect, not an idle queue."
                    ),
                }
            )
            log_event(
                run_id,
                "idle_streak_escalated",
                project_id=project_id,
                idle_seconds=streak.idle_seconds,
                consecutive_ticks=streak.consecutive_ticks,
            )
            return finish(run_id, receipt_dir, receipt, 0, persist=streak.should_persist_receipt)
        receipt.update({"ok": True, "status": "NOOP", "stop_reason": "no_routable_issues"})
        log_event(
            run_id,
            "no_routable_issues",
            project_id=project_id,
            consecutive_idle_ticks=streak.consecutive_ticks,
        )
        return finish(run_id, receipt_dir, receipt, 0)

    streaks.clear_idle(project_id)
    for issue in issues[:max_tickets]:
        receipt["handled_issues"].append(
            handle_issue(run_id, receipt_dir, project, issue, apply=apply)
        )
    receipt["handled_count"] = len(receipt["handled_issues"])
    receipt["ok"] = all(item.get("ok") for item in receipt["handled_issues"])
    receipt["status"] = "COMPLETED" if receipt["ok"] else "NEEDS_ATTENTION"
    return finish(run_id, receipt_dir, receipt, 0 if receipt["ok"] else 1)


def install_cron(*, apply: bool, minute: str) -> int:
    """Install or dry-run the crontab line that drives the watchdog."""
    run_id = f"project-watchdog-install-{timestamp()}"
    cron_log = config.cron_log_path()
    command = (
        f"{minute} * * * * cd {shlex.quote(str(config.SKILL_DIR))} && "
        f"{shlex.quote(str(config.SKILL_DIR / 'run.sh'))} tick --apply --project tau "
        f"--max-tickets 1 >> {shlex.quote(str(cron_log))} 2>&1 {config.CRON_MARKER}"
    )
    current = run_cmd(["crontab", "-l"])
    existing = current["stdout"] if current["exit_code"] == 0 else ""
    lines = [line for line in existing.splitlines() if config.CRON_MARKER not in line]
    lines.append(command)
    new_crontab = "\n".join(lines).rstrip() + "\n"
    receipt: dict[str, Any] = {
        "schema": "agent_skills.project_watchdog.cron_install_receipt.v1",
        "run_id": run_id,
        "apply": apply,
        "cron_line": command,
        "cron_log": str(cron_log),
        "previous_had_entry": config.CRON_MARKER in existing,
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
    receipt_dir = config.receipt_root() / run_id
    receipt_dir.mkdir(parents=True, exist_ok=True)
    return finish(run_id, receipt_dir, receipt, 0 if receipt["ok"] else 1, persist=True)


def set_state(scope: str, state_value: str, *, project_id: str, reason: str) -> int:
    """Record an operator state transition at global or project scope."""
    run_id = f"project-watchdog-state-{timestamp()}"
    state = load_json(config.STATE_PATH)
    if scope == "global":
        state.setdefault("global", {})["state"] = state_value
        state["global"]["reason"] = reason
    else:
        state.setdefault("projects", {}).setdefault(project_id, {})["state"] = state_value
        state["projects"][project_id]["reason"] = reason
    state["updated_at"] = datetime.now(UTC).date().isoformat()
    write_json(config.STATE_PATH, state)
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
    receipt_dir = config.receipt_root() / run_id
    receipt_dir.mkdir(parents=True, exist_ok=True)
    return finish(run_id, receipt_dir, receipt, 0, persist=True)


def status_payload() -> dict[str, Any]:
    """Return registry, state, cron, and receipt-store facts for operators."""
    projects = load_json(config.PROJECTS_PATH).get("projects", [])
    receipts = config.receipt_root()
    stored = sum(1 for _ in receipts.glob("project-watchdog-*")) if receipts.is_dir() else 0
    return {
        "schema": "agent_skills.project_watchdog.status.v1",
        "state": load_json(config.STATE_PATH),
        "project_count": len(projects),
        "project_ids": sorted(str(entry.get("project_id")) for entry in projects),
        "log_file": str(config.event_log_path()),
        "cron_log_file": str(config.cron_log_path()),
        "receipt_root": str(receipts),
        "stored_receipt_dirs": stored,
        "lock_held": config.lock_dir().is_dir(),
        "idle_streaks": streaks.all_streaks(),
        "idle_escalation_seconds": config.NOOP_ESCALATION_SECONDS,
        "uv_bin": config.resolve_uv_bin(),
        "cron_entries": run_cmd(["crontab", "-l"])["stdout"],
    }


def status_json() -> str:
    return json.dumps(status_payload(), indent=2, sort_keys=True)
