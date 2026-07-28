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
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loguru import logger

from . import config, github, registry, streaks
from .core import (
    acquire_lock,
    base_receipt,
    finish,
    load_json,
    lock_holder_alive,
    log_event,
    release_lock,
    run_cmd,
    timestamp,
    write_json,
)
from .handlers import (
    handle_closure_audit,
    handle_completion_attestation,
    handle_issue,
)
from .registry import find_project, list_routable_issues

#: Skip reasons a later tick can clear without anyone intervening. A lease ends
#: when its holder finishes, and an empty or fully-blocked queue refills as
#: tickets are filed and unblocked. Everything else -- a paused project, a
#: stopped one, a lease scan that will not run -- stays true until a human acts.
#:
#: Idle is normal. Idle for too long is the idle-streak escalation's job, not
#: this one's.
_SELF_CLEARING_SKIPS = frozenset({"lane_busy", "no_routable_issues"})


def _record_fleet_stall(receipt: dict[str, Any], skipped: list[dict[str, Any]]) -> None:
    """Mark a tick that serviced no project, and say whether it can recover.

    Both no-project-serviceable paths used to report ``ok: True`` and exit 0, so
    a fleet where every project is paused looked exactly like a quiet minute.
    Cron saw success indefinitely while nothing was dispatched -- the failure
    this watchdog exists to prevent, in the watchdog itself.

    A stall held open only by leases is transient and stays ``ok``. A stall with
    any other cause cannot clear on its own, so it reports NEEDS_ATTENTION and a
    nonzero exit.
    """
    reasons = [str(entry.get("reason", "")) for entry in skipped]
    blocking = sorted({r for r in reasons if r.split(":")[0] not in _SELF_CLEARING_SKIPS})
    receipt["fleet_stall"] = {
        "serviced_projects": 0,
        "candidates": len(skipped),
        "by_reason": {r: reasons.count(r) for r in sorted(set(reasons))},
        "self_clearing": not blocking,
        "needs_human": blocking,
    }
    if blocking:
        receipt["ok"] = False
        receipt["status"] = "NEEDS_ATTENTION"
        detail = "; ".join(
            f"{entry.get('project_id')}: {entry.get('reason')}" for entry in skipped
        )
        receipt["summary"] = (
            f"no registered project was serviceable and the reasons do not clear on their own "
            f"({detail}). The watchdog will dispatch nothing until this is resolved."
        )
    else:
        receipt["ok"] = True


def _reclaim_stale_leases(
    repo: str,
    stale: list[dict[str, Any]],
    *,
    apply: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Clear only expired lease labels and return reclaimed rows plus failures."""
    reclaimed: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    if not apply:
        return reclaimed, failures
    for entry in stale:
        command = github.issue_edit(
            repo,
            int(entry["issue_number"]),
            remove=list(entry.get("labels", [])),
        )
        row = {**entry, "command": command}
        if command.get("exit_code") == 0:
            row["status"] = "reclaimed"
            reclaimed.append(row)
        else:
            row["status"] = "reclaim_failed"
            failures.append(row)
    return reclaimed, failures


def tick(*, apply: bool, project_id: str, max_tickets: int) -> int:
    """Run one bounded watchdog tick under the single-tick lock."""
    run_id = f"project-watchdog-{timestamp()}"
    receipt_dir = config.receipt_root() / run_id
    receipt_dir.mkdir(parents=True, exist_ok=True)
    log_event(run_id, "tick_start", apply=apply, project_id=project_id, max_tickets=max_tickets)

    if not acquire_lock(run_id):
        receipt = base_receipt(run_id, receipt_dir, apply)
        # Stepping aside for a tick that is genuinely working is not an error.
        # An audit takes minutes, so treating contention as failure logged
        # BLOCKED and exited 1 every minute for the whole run -- a healthy
        # long-running lane reading as a broken one. A lock held by nothing is
        # still a fault.
        if lock_holder_alive():
            receipt.update(
                {
                    "ok": True,
                    "status": "SKIPPED",
                    "stop_reason": "tick_already_running",
                    "summary": "another tick holds the lock and is still working",
                }
            )
            log_event(run_id, "tick_skipped_lock_held")
            return finish(run_id, receipt_dir, receipt, 0, persist=False)
        receipt.update({"ok": False, "status": "BLOCKED", "errors": ["lock already held"]})
        return finish(run_id, receipt_dir, receipt, 1, persist=False)
    try:
        return _tick_locked(
            run_id, receipt_dir, apply=apply, project_id=project_id, max_tickets=max_tickets
        )
    finally:
        release_lock()


def _audit_one_closure(
    run_id: str,
    receipt_dir: Path,
    state: dict[str, Any],
    receipt: dict[str, Any],
    *,
    apply: bool,
) -> dict[str, Any] | None:
    """Review the oldest unchecked closure across active projects, if any.

    One per tick, and only when no project had repair work, so the audit lane
    can never starve the repair lane.
    """
    pending_by_project: list[dict[str, Any]] = []
    for candidate in registry.rotation_order(load_json(config.projects_path()), state):
        cid = str(candidate.get("project_id"))
        if state.get("projects", {}).get(cid, {}).get("state") != "active":
            continue
        try:
            pending = registry.list_closed_for_audit(run_id, candidate)
        except RuntimeError as exc:
            logger.error("closure audit scan failed for {}: {}", cid, exc)
            continue
        if pending:
            pending_by_project.append({"project": candidate, "pending": pending})

    receipt["closure_audit"] = {
        "pending_counts": {
            str(e["project"].get("project_id")): len(e["pending"]) for e in pending_by_project
        }
    }
    if not pending_by_project:
        return None

    # An audit that produced no verdict must not be retried on the next tick.
    # A provider outage otherwise pins the lane to one closure forever while the
    # rest of the backlog waits.
    now = time.time()
    attempts = state.setdefault("closure_audit_attempts", {})
    cooling: list[str] = []
    for entry in pending_by_project:
        repo = str(entry["project"].get("repo"))
        fresh = []
        for issue in entry["pending"]:
            key = f"{repo}#{issue['number']}"
            last = float(attempts.get(key) or 0)
            if now - last < config.CLOSURE_AUDIT_RETRY_COOLDOWN_SECONDS:
                cooling.append(key)
                continue
            fresh.append(issue)
        entry["pending"] = fresh
    receipt["closure_audit"]["cooling_down"] = len(cooling)

    ready = [e for e in pending_by_project if e["pending"]]
    if not ready:
        return None

    chosen = ready[0]
    # Oldest closure first: the longest-unverified claim is the one most worth
    # checking, and it makes progress through a backlog deterministic.
    issue = sorted(chosen["pending"], key=lambda i: str(i.get("closedAt") or ""))[0]
    receipt["closure_audit"]["selected"] = int(issue["number"])

    key = f"{chosen['project'].get('repo')}#{issue['number']}"
    audited = handle_closure_audit(run_id, receipt_dir, chosen["project"], issue, apply=apply)
    if apply:
        if audited.get("verdict"):
            attempts.pop(key, None)  # answered: no reason to hold it back
        else:
            attempts[key] = now
        write_json(config.state_path(), state)
    return audited


def _attest_completion(
    run_id: str,
    receipt_dir: Path,
    state: dict[str, Any],
    receipt: dict[str, Any],
    *,
    apply: bool,
) -> dict[str, Any] | None:
    """Ask an independent seat whether a finished-looking project is finished.

    Fires only when a project has no open routable ticket AND no closure left to
    audit -- the point where the system would otherwise declare itself done. An
    empty queue is equally consistent with nobody filing the remaining work, and
    every judgement up to here came from the models that did and reviewed it.

    Rate-limited per project: every ticket being closed is a durable state, so
    without that the cron would re-ask the same question every minute.
    """
    now = time.time()
    attested = state.setdefault("completion_attested_at", {})
    for candidate in registry.rotation_order(load_json(config.projects_path()), state):
        cid = str(candidate.get("project_id"))
        if state.get("projects", {}).get(cid, {}).get("state") != "active":
            continue
        record = attested.get(cid)
        if isinstance(record, dict):
            last, answered = float(record.get("at") or 0), bool(record.get("answered"))
        else:  # pre-existing state wrote a bare timestamp
            last, answered = float(record or 0), True
        window = (
            config.COMPLETION_ATTEST_INTERVAL_SECONDS
            if answered
            else config.COMPLETION_ATTEST_RETRY_SECONDS
        )
        if now - last < window:
            continue
        try:
            recent = registry.list_recently_closed(run_id, candidate)
        except RuntimeError as exc:
            logger.error("completion scan failed for {}: {}", cid, exc)
            continue
        if not recent:
            continue
        receipt["completion_attestation"] = {"project_id": cid, "closed_seen": len(recent)}
        result = handle_completion_attestation(
            run_id, receipt_dir, candidate, recent, apply=apply
        )
        # Stamp AFTER the run, recording whether it actually answered. Stamping
        # first meant a run that died mid-flight lost its verdict AND blocked
        # the retry for a full day: observed when a webgpt attestation reached
        # PASS on its handler node, and the wrapper was killed before it could
        # reopen the seven tickets it had named.
        if apply:
            attested[cid] = {"at": now, "answered": bool(result.get("verdict"))}
            write_json(config.state_path(), state)
        return result
    return None


def _tick_locked(
    run_id: str,
    receipt_dir: Path,
    *,
    apply: bool,
    project_id: str,
    max_tickets: int,
) -> int:
    receipt = base_receipt(run_id, receipt_dir, apply)
    state = load_json(config.state_path())
    receipt["state_snapshot"] = state

    global_state = state.get("global", {}).get("state")
    if global_state != "active":
        receipt.update(
            {"ok": True, "status": "SKIPPED", "stop_reason": f"global_state_{global_state}"}
        )
        log_event(run_id, "tick_skipped", reason=receipt["stop_reason"])
        return finish(run_id, receipt_dir, receipt, 0)

    try:
        project = find_project(load_json(config.projects_path()), project_id)
    except ValueError as exc:
        receipt.update({"ok": False, "status": "BLOCKED", "errors": [str(exc)]})
        logger.error("{}", exc)
        return finish(run_id, receipt_dir, receipt, 2)

    # Try every active project, best candidate first, until one has work. The
    # crontab pins a single project and the tick used to stop there: if that one
    # was paused, or active with nothing dispatchable, the whole fleet idled
    # while another project had a ready ticket (#1084).
    projects_doc = load_json(config.projects_path())
    skipped: list[dict[str, Any]] = []
    project = None
    issues: list[dict[str, Any]] = []

    for candidate in registry.rotation_order(projects_doc, state, requested=project_id):
        cid = str(candidate.get("project_id"))
        cstate = state.get("projects", {}).get(cid, {}).get("state")
        if cstate != "active":
            skipped.append({"project_id": cid, "reason": f"project_state_{cstate}"})
            continue
        try:
            in_flight = registry.lane_busy_issues(run_id, candidate)
        except RuntimeError as exc:
            # A failed lease scan must never read as "nothing in flight".
            skipped.append({"project_id": cid, "reason": f"lease_scan_failed: {exc}"})
            continue

        # Reclaim leases whose holder is gone before deciding this project has
        # nothing to do -- a stale lease is not work in flight (#1090).
        stale = list(registry.LAST_LEASE_SCAN.get("stale", []))
        candidate_staleness = {
            "stale_after_seconds": registry.LAST_LEASE_SCAN.get(
                "stale_after_seconds", config.LEASE_STALE_SECONDS
            ),
            "stale": stale,
            "unknown_acquisition_time": registry.LAST_LEASE_SCAN.get(
                "unknown_acquisition_time", []
            ),
        }
        reclaimed, reclaim_failures = _reclaim_stale_leases(
            registry.project_repo(candidate), stale, apply=apply
        )
        if reclaim_failures:
            skipped.append(
                {
                    "project_id": cid,
                    "reason": "stale_lease_reclaim_failed",
                    "reclaim_failures": reclaim_failures,
                }
            )
            continue

        busy = registry.busy_targets(in_flight)
        try:
            found = list_routable_issues(
                run_id,
                candidate,
                busy,
                skip_issue_numbers={int(e["issue_number"]) for e in reclaimed},
            )
        except (RuntimeError, ValueError) as exc:
            skipped.append({"project_id": cid, "reason": f"issue_scan_failed: {exc}"})
            logger.error("issue scan failed for project {}: {}", cid, exc)
            continue
        if not found:
            skipped.append(
                {
                    "project_id": cid,
                    "reason": "no_routable_issues",
                    "scanned": registry.LAST_SCAN.get("scanned", 0),
                    "excluded": registry.LAST_SCAN.get("excluded", {}),
                }
            )
            continue
        if not found and reclaimed:
            skipped.append(
                {
                    "project_id": cid,
                    "reason": "stale_leases_reclaimed",
                    "reclaimed": reclaimed,
                }
            )
            continue
        project, issues = candidate, found
        receipt["lease_staleness"] = candidate_staleness
        receipt["reclaimed_leases"] = reclaimed
        if not apply and stale:
            receipt["would_reclaim_leases"] = stale
        receipt["in_flight"] = {
            "issues": [int(i["number"]) for i in in_flight],
            "targets": sorted(busy),
            "leases": registry.LAST_LEASE_SCAN.get("active", []),
        }
        break

    receipt["rotation"] = {
        "requested": project_id,
        "selected": None if project is None else str(project.get("project_id")),
        "skipped": skipped,
    }

    # No repair work anywhere. Before calling the tick idle, check whether any
    # recent closure needs reviewing: closing a ticket is a claim that the work
    # is done, and until now nothing verified that claim. Repairs come first --
    # an audit must never delay a ticket that is actually waiting.
    if project is None:
        audited = _audit_one_closure(run_id, receipt_dir, state, receipt, apply=apply)
        if audited is not None:
            receipt["handled_issues"].append(audited)
            receipt["handled_count"] = 1
            receipt["ok"] = bool(audited.get("ok"))
            # A previewed audit is not an event. Persisting a receipt for one
            # would put a directory on disk every minute for work not done.
            preview = audited.get("status") == "DRY_RUN"
            receipt["status"] = (
                "DRY_RUN" if preview else ("COMPLETED" if receipt["ok"] else "NEEDS_ATTENTION")
            )
            streaks.clear_idle(str(audited.get("project_id") or project_id))
            return finish(
                run_id, receipt_dir, receipt, 0 if receipt["ok"] else 1, persist=not preview
            )

    # Nothing to repair and nothing to audit: the point where the system would
    # otherwise call itself done. Ask an independent seat whether it actually is.
    if project is None:
        attested = _attest_completion(run_id, receipt_dir, state, receipt, apply=apply)
        if attested is not None:
            receipt["handled_issues"].append(attested)
            receipt["handled_count"] = 1
            receipt["ok"] = bool(attested.get("ok"))
            preview = attested.get("status") == "DRY_RUN"
            receipt["status"] = (
                "DRY_RUN" if preview else ("COMPLETED" if receipt["ok"] else "NEEDS_ATTENTION")
            )
            return finish(
                run_id, receipt_dir, receipt, 0 if receipt["ok"] else 1, persist=not preview
            )

    if project is None:
        streak = streaks.record_idle(project_id)
        receipt["idle_streak"] = streak.as_receipt_block()
        receipt.update({"status": "NOOP", "stop_reason": "no_routable_issues"})
        _record_fleet_stall(receipt, skipped)
        if streak.escalated and receipt["ok"]:
            receipt.update(
                {
                    "status": "NEEDS_ATTENTION",
                    "stop_reason": "idle_streak_exceeded",
                    "summary": (
                        f"no project has had a routable issue for "
                        f"{streak.idle_seconds / 3600:.1f}h across "
                        f"{streak.consecutive_ticks} ticks. A scan that never "
                        f"matches is a defect, not an idle queue."
                    ),
                }
            )
            log_event(run_id, "idle_streak_escalated", project_id=project_id,
                      idle_seconds=streak.idle_seconds,
                      consecutive_ticks=streak.consecutive_ticks)
        log_event(run_id, "no_routable_issues", skipped=skipped,
                  fleet_stall=receipt["fleet_stall"])
        return finish(run_id, receipt_dir, receipt, 0 if receipt["ok"] else 1,
                      persist=streak.should_persist_receipt or not receipt["ok"])

    project_id = str(project.get("project_id"))
    receipt["project_id"] = project_id
    log_event(run_id, "project_selected", selected=project_id,
              requested=receipt["rotation"]["requested"], skipped=len(skipped))

    # Record who was served so the next tick starts after them, not at the head.
    state.setdefault("last_served_project", None)
    state["last_served_project"] = project_id
    write_json(config.state_path(), state)
    streaks.clear_idle(project_id)

    receipt["scanned_issues"] = issues
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
    # Run through a LOGIN shell. cron starts with a nearly empty environment and
    # does not read the user's profile, so provider credentials exported there
    # are absent: every audit seat under cron failed with
    # `scillm_auth_invalid_api_key` while the same handler answered fine from an
    # interactive shell. A login shell inherits them without copying a secret
    # into the crontab or into a file in the repo.
    inner = (
        f"cd {shlex.quote(str(config.SKILL_DIR))} && "
        f"{shlex.quote(str(config.SKILL_DIR / 'run.sh'))} tick --apply --project tau "
        f"--max-tickets 1"
    )
    init_file = config.shell_init_file()
    if init_file is not None:
        inner = f"source {shlex.quote(str(init_file))} >/dev/null 2>&1; {inner}"
    command = (
        f"{minute} * * * * {shlex.quote(config.login_shell())} -c {shlex.quote(inner)} "
        f">> {shlex.quote(str(cron_log))} 2>&1 {config.CRON_MARKER}"
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
    state = load_json(config.state_path())
    if scope == "global":
        state.setdefault("global", {})["state"] = state_value
        state["global"]["reason"] = reason
    else:
        state.setdefault("projects", {}).setdefault(project_id, {})["state"] = state_value
        state["projects"][project_id]["reason"] = reason
    state["updated_at"] = datetime.now(UTC).date().isoformat()
    write_json(config.state_path(), state)
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
    projects = load_json(config.projects_path()).get("projects", [])
    receipts = config.receipt_root()
    stored = sum(1 for _ in receipts.glob("project-watchdog-*")) if receipts.is_dir() else 0
    return {
        "schema": "agent_skills.project_watchdog.status.v1",
        "state": load_json(config.state_path()),
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
