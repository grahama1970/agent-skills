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
import os
import shlex
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from loguru import logger

from . import config, github, registry, streaks
from .core import (
    acquire_execution_lock,
    acquire_lock,
    base_receipt,
    finish,
    load_json,
    lock_holder_alive,
    log_event,
    release_execution_lock,
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
from .ui_export import build_snapshot

#: Skip reasons a later tick can clear without anyone intervening. A lease ends
#: when its holder finishes, and an empty or fully-blocked queue refills as
#: tickets are filed and unblocked. Everything else -- a paused project, a
#: stopped one, a lease scan that will not run -- stays true until a human acts.
#:
#: Idle is normal. Idle for too long is the idle-streak escalation's job, not
#: this one's.
_SELF_CLEARING_SKIPS = frozenset(
    {"lane_busy", "no_routable_issues", "dependency_unblocked_this_tick"}
)


def _handled_result_allows_agent_followup(result: dict[str, Any]) -> bool:
    """Return true when a failed lane is still an agent-owned next step.

    ``NEEDS_ATTENTION`` used to mean "stop and ask the human" even for errors
    that named an obvious machine next step, such as a completion attestor that
    ran but emitted no parseable verdict. That trained supervising agents to
    bury the real next action in a final status report. A lane may now mark
    ``requires_human_input: false`` to say: do not claim success, but the next
    action is authorized for the agent and the tick should not fail as a human
    blocker.
    """
    return result.get("ok") is True or result.get("requires_human_input") is False


def _handled_tick_status(result: dict[str, Any], *, preview: bool) -> str:
    if preview:
        return "DRY_RUN"
    if result.get("ok") is True:
        return "COMPLETED"
    if result.get("requires_human_input") is False:
        return "COMPLETED"
    return "NEEDS_ATTENTION"


def _record_agent_authorization(receipt: dict[str, Any], result: dict[str, Any]) -> None:
    if result.get("ok") is True or result.get("requires_human_input") is not False:
        return
    receipt["requires_human_input"] = False
    receipt["authorized_agent_next_steps"] = result.get("authorized_agent_next_steps") or []
    receipt["agent_action_required"] = True


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


def tick(*, apply: bool, project_id: str, max_tickets: int, only_issue: int | None = None) -> int:
    """Run one bounded watchdog tick under the single-tick lock."""
    run_id = f"project-watchdog-{timestamp()}"
    receipt_dir = config.receipt_root() / run_id
    receipt_dir.mkdir(parents=True, exist_ok=True)
    log_event(run_id, "tick_start", apply=apply, project_id=project_id, max_tickets=max_tickets)

    # Overnight batch work owns the machine between the quiet hours; a repair
    # dispatch there competes with jobs that cannot be restarted cheaply. The
    # issues are still there afterwards.
    if apply and config.tick_would_enter_quiet_hours():
        receipt = base_receipt(run_id, receipt_dir, apply)
        window = config.quiet_window()
        receipt.update(
            {
                "ok": True,
                "status": "SKIPPED",
                "stop_reason": "quiet_hours",
                "summary": (
                    f"deferring to overnight batch work ({window[0]:02d}:00-{window[1]:02d}:00); "
                    "set PROJECT_WATCHDOG_QUIET_HOURS to change"
                ),
            }
        )
        log_event(run_id, "tick_skipped_quiet_hours", window=list(window))
        return finish(run_id, receipt_dir, receipt, 0, persist=False)

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
    scheduler_lock_held = True

    def release_scheduler_lock() -> None:
        nonlocal scheduler_lock_held
        if scheduler_lock_held:
            release_lock()
            scheduler_lock_held = False

    try:
        _test_hold_lock_if_requested(run_id)
        return _tick_locked(
            run_id, receipt_dir, apply=apply, project_id=project_id, max_tickets=max_tickets,
            only_issue=only_issue, release_scheduler_lock=release_scheduler_lock,
        )
    finally:
        release_scheduler_lock()


#: State keys a tick owns. Everything else in the document belongs to the
#: operator and must survive a tick that started before they changed it.
_TICK_OWNED_STATE_KEYS = ("last_served_project", "closure_audit_attempts",
                          "completion_attested_at")


def _test_hold_lock_if_requested(run_id: str) -> None:
    """Pause with the real singleton lock held for overlap regression evals."""
    raw = os.environ.get("PROJECT_WATCHDOG_TEST_HOLD_LOCK_SECONDS", "").strip()
    if not raw:
        return
    try:
        seconds = float(raw)
    except ValueError:
        seconds = 0.0
    if seconds <= 0:
        return
    log_event(run_id, "test_hold_lock_start", seconds=seconds)
    time.sleep(seconds)
    log_event(run_id, "test_hold_lock_finish", seconds=seconds)


def _persist_tick_state(state: dict[str, Any]) -> None:
    """Write back only the keys a tick owns, merged onto what is on disk now.

    A tick reads state at the start and used to write the whole document at the
    end, so any operator change landing in between was silently reverted:
    `set-state project active --project watchdog-probe` reported UPDATED and the
    project was simply absent afterwards, because a tick already in flight wrote
    its stale copy over it. The project then never dispatched.
    """
    current = load_json(config.state_path())
    for key in _TICK_OWNED_STATE_KEYS:
        if key in state:
            current[key] = state[key]
    write_json(config.state_path(), current)


def _project_runtime_state(project: dict[str, Any], state: dict[str, Any]) -> str | None:
    """Runtime state for a project, falling back to registry policy for new ids."""
    cid = str(project.get("project_id"))
    explicit = state.get("projects", {}).get(cid, {}).get("state")
    if explicit:
        return str(explicit)
    policy = project.get("state_policy") or {}
    default = policy.get("default_state")
    return str(default) if default else None


def _audit_one_closure(
    run_id: str,
    receipt_dir: Path,
    state: dict[str, Any],
    receipt: dict[str, Any],
    *,
    apply: bool,
    candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Review the oldest unchecked closure across active projects, if any.

    One per tick, and only when no project had repair work, so the audit lane
    can never starve the repair lane.
    """
    pending_by_project: list[dict[str, Any]] = []
    for candidate in candidates or registry.rotation_order(load_json(config.projects_path()), state):
        cid = str(candidate.get("project_id"))
        if _project_runtime_state(candidate, state) != "active":
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
        if audited.get("ok") is True and audited.get("verdict") in {"PASS", "FAIL"}:
            attempts.pop(key, None)  # durably answered: no reason to hold it back
        else:
            attempts[key] = now
        _persist_tick_state(state)
    return audited


def _attest_completion(
    run_id: str,
    receipt_dir: Path,
    state: dict[str, Any],
    receipt: dict[str, Any],
    *,
    apply: bool,
    candidates: list[dict[str, Any]] | None = None,
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
    for candidate in candidates or registry.rotation_order(load_json(config.projects_path()), state):
        cid = str(candidate.get("project_id"))
        if _project_runtime_state(candidate, state) != "active":
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
            _persist_tick_state(state)
        return result
    return None


def _tick_locked(
    run_id: str,
    receipt_dir: Path,
    *,
    apply: bool,
    project_id: str,
    max_tickets: int,
    only_issue: int | None = None,
    release_scheduler_lock: Callable[[], None] | None = None,
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

    projects_doc = load_json(config.projects_path())
    if project_id == "all":
        rotation_mode = "fleet"
        candidates = registry.rotation_order(projects_doc, state)
    else:
        try:
            requested_project = find_project(projects_doc, project_id)
        except ValueError as exc:
            receipt.update({"ok": False, "status": "BLOCKED", "errors": [str(exc)]})
            logger.error("{}", exc)
            return finish(run_id, receipt_dir, receipt, 2)
        rotation_mode = "strict"
        candidates = [requested_project]

    # Fleet mode tries every active project, best candidate first, until one has
    # work. Strict mode tries only the requested project; it must never dispatch
    # another repository while the receipt says a specific project was requested.
    skipped: list[dict[str, Any]] = []
    project = None
    issues: list[dict[str, Any]] = []
    issue_scans: list[dict[str, Any]] = []

    for candidate in candidates:
        cid = str(candidate.get("project_id"))
        cstate = _project_runtime_state(candidate, state)
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
                only_issue=only_issue,
                apply=apply,
            )
        except (RuntimeError, ValueError) as exc:
            skipped.append({"project_id": cid, "reason": f"issue_scan_failed: {exc}"})
            logger.error("issue scan failed for project {}: {}", cid, exc)
            continue
        scan = {
            "project_id": cid,
            "repo": registry.project_repo(candidate),
            "scanned": registry.LAST_SCAN.get("scanned", 0),
            "excluded": registry.LAST_SCAN.get("excluded", {}),
            "excluded_issues": registry.LAST_SCAN.get("excluded_issues", {}),
            "dependency_unblocks": registry.LAST_SCAN.get("dependency_unblocks", []),
        }
        issue_scans.append(scan)
        dependency_unblocks = list(scan["dependency_unblocks"])
        if only_issue is not None:
            # Targeted repair (agent-skills#1456): lease ONLY the named issue.
            # If it is not routable right now, refuse without leasing anything
            # else -- spending this tick on an unrelated ticket would let the
            # eval-loop believe its regression got repair capacity.
            found = [i for i in found if int(i["number"]) == int(only_issue)]
            if not found:
                skipped.append({
                    "project_id": cid,
                    "reason": "targeted_issue_not_routable",
                    "targeted_issue": int(only_issue),
                })
                continue
        if dependency_unblocks and apply:
            project, issues = candidate, []
            receipt["issue_scans"] = issue_scans
            receipt["excluded_counts"] = scan["excluded"]
            receipt["excluded_issues"] = scan["excluded_issues"]
            receipt["excluded_issue_refs"] = {
                reason: [f"{scan['repo']}#{number}" for number in numbers]
                for reason, numbers in scan["excluded_issues"].items()
            }
            receipt["dependency_unblocks"] = dependency_unblocks
            receipt["lease_staleness"] = candidate_staleness
            receipt["reclaimed_leases"] = reclaimed
            receipt["in_flight"] = {
                "issues": [int(i["number"]) for i in in_flight],
                "targets": sorted(busy),
                "leases": registry.LAST_LEASE_SCAN.get("active", []),
            }
            break
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
        receipt["issue_scans"] = issue_scans
        receipt["excluded_counts"] = scan["excluded"]
        receipt["excluded_issues"] = scan["excluded_issues"]
        receipt["excluded_issue_refs"] = {
            reason: [f"{scan['repo']}#{number}" for number in numbers]
            for reason, numbers in scan["excluded_issues"].items()
        }
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
        "mode": rotation_mode,
        "requested": project_id,
        "selected": None if project is None else str(project.get("project_id")),
        "skipped": skipped,
    }
    receipt.setdefault("issue_scans", issue_scans)

    # No repair work anywhere. Before calling the tick idle, check whether any
    # recent closure needs reviewing: closing a ticket is a claim that the work
    # is done, and until now nothing verified that claim. Repairs come first --
    # an audit must never delay a ticket that is actually waiting.
    if project is None and only_issue is not None:
        # Targeted mode: this tick exists for one named issue. When it is not
        # dispatchable, refuse -- do NOT spend the tick on closure audits or
        # attestation, which would let the caller believe its regression got
        # repair capacity (agent-skills#1456).
        receipt.update({"ok": True, "status": "SKIPPED",
                        "stop_reason": "targeted_issue_not_routable",
                        "targeted_issue": int(only_issue)})
        return finish(run_id, receipt_dir, receipt, 0)

    if project is None:
        audited = _audit_one_closure(
            run_id, receipt_dir, state, receipt, apply=apply, candidates=candidates
        )
        if audited is not None:
            receipt["handled_issues"].append(audited)
            receipt["handled_count"] = 1
            # A previewed audit is not an event. Persisting a receipt for one
            # would put a directory on disk every minute for work not done.
            preview = audited.get("status") == "DRY_RUN"
            receipt["ok"] = _handled_result_allows_agent_followup(audited)
            _record_agent_authorization(receipt, audited)
            receipt["status"] = _handled_tick_status(audited, preview=preview)
            streaks.clear_idle(str(audited.get("project_id") or project_id))
            return finish(
                run_id, receipt_dir, receipt, 0 if receipt["ok"] else 1, persist=not preview
            )

    # Nothing to repair and nothing to audit: the point where the system would
    # otherwise call itself done. Ask an independent seat whether it actually is.
    if project is None:
        attested = _attest_completion(
            run_id, receipt_dir, state, receipt, apply=apply, candidates=candidates
        )
        if attested is not None:
            receipt["handled_issues"].append(attested)
            receipt["handled_count"] = 1
            preview = attested.get("status") == "DRY_RUN"
            receipt["ok"] = _handled_result_allows_agent_followup(attested)
            _record_agent_authorization(receipt, attested)
            receipt["status"] = _handled_tick_status(attested, preview=preview)
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
    _persist_tick_state(state)
    streaks.clear_idle(project_id)

    receipt["scanned_issues"] = issues
    if not issues and receipt.get("dependency_unblocks"):
        receipt["handled_issues"].extend(
            {
                "action": "dependency_unblock",
                "issue_number": int(row["issue_number"]),
                "repo": row["repo"],
                "ok": True,
                "status": "COMPLETED",
                "removed_labels": row.get("removed_labels", []),
                "refs": row.get("refs", []),
            }
            for row in receipt["dependency_unblocks"]
        )
        receipt["handled_count"] = len(receipt["handled_issues"])
        receipt["ok"] = True
        receipt["status"] = "COMPLETED"
        receipt["stop_reason"] = "dependency_unblocked_this_tick"
        return finish(run_id, receipt_dir, receipt, 0, persist=True)
    # A period wider than the observed maximum tick makes overlap unlikely; a
    # deadline below the period makes it structural. Without one the lock is
    # the only thing standing between a slow tick and a queue of skipped ones,
    # and the 302.8s maximum is a measurement, not a bound.
    deadline = tick_deadline_seconds()
    started = time.monotonic()
    dispatch_plan: list[dict[str, Any]] = []
    for index, issue in enumerate(issues[:max_tickets]):
        if defer_for_deadline(index, time.monotonic() - started, deadline):
            receipt["deadline_deferred"] = [int(i["number"]) for i in issues[index:max_tickets]]
            receipt["stop_reason"] = "tick_deadline"
            log_event(
                run_id, "tick_deadline_reached",
                deadline_seconds=deadline, deferred=receipt["deadline_deferred"],
            )
            break
        targets = set(str(t) for t in issue.get("watchdog_targets") or registry.issue_targets(issue))
        execution_lock = acquire_execution_lock(run_id, targets) if apply else None
        if apply and execution_lock is None:
            receipt["handled_issues"].append(
                {
                    "action": "ticket_repair",
                    "issue_number": int(issue["number"]),
                    "repo": registry.project_repo(project),
                    "ok": True,
                    "status": "SKIPPED",
                    "stop_reason": "execution_lock_held",
                    "targets": sorted(targets),
                }
            )
            continue
        dispatch_plan.append({"issue": issue, "targets": sorted(targets), "lock": execution_lock})

    if dispatch_plan and release_scheduler_lock is not None:
        receipt["scheduler_lock_released_before_dispatch"] = True
        release_scheduler_lock()

    for entry in dispatch_plan:
        issue = entry["issue"]
        execution_lock = entry.get("lock")
        try:
            result = handle_issue(run_id, receipt_dir, project, issue, apply=apply)
            result.setdefault("execution_lock_targets", entry["targets"])
            if execution_lock is not None:
                result.setdefault("execution_lock", str(execution_lock))
            receipt["handled_issues"].append(result)
        finally:
            release_execution_lock(execution_lock)
    receipt["handled_count"] = len(receipt["handled_issues"])
    receipt["ok"] = all(item.get("ok") for item in receipt["handled_issues"])
    receipt["status"] = "COMPLETED" if receipt["ok"] else "NEEDS_ATTENTION"
    return finish(run_id, receipt_dir, receipt, 0 if receipt["ok"] else 1)


def activate(*, apply: bool, minute: str = "*/5") -> int:
    """Turn the watchdog on in one call: schedule plus state.

    A project agent should be able to switch automatic issue handling on
    without a human editing crontab. Activation is two facts that must agree --
    a schedule exists, and global state is active -- and having them in
    separate commands is how the cron sat installed while the state was paused,
    or the reverse.

    It is idempotent and reports what it changed, so calling it when already
    active is a no-op rather than a duplicate entry.
    """
    run_id = f"project-watchdog-activate-{timestamp()}"
    steps: list[dict[str, Any]] = []

    # install_cron writes its own receipt through the shared finish(). Two JSON
    # documents on one stream is unparseable by any machine caller -- which is
    # exactly what the eval caught -- so activate captures it and owns stdout.
    import contextlib
    import io

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        cron_rc = install_cron(apply=apply, minute=minute)
    try:
        steps_cron_receipt = json.loads(buffer.getvalue() or "{}")
    except ValueError:
        steps_cron_receipt = {"raw": buffer.getvalue()[:400]}
    steps.append({
        "step": "install_cron",
        "minute": minute,
        "exit_code": cron_rc,
        "cron_line": steps_cron_receipt.get("cron_line"),
    })

    state_rc = 0
    if cron_rc == 0:
        with contextlib.redirect_stdout(io.StringIO()):
            state_rc = set_state("global", "active", project_id="", reason="activated by agent")
        steps.append({"step": "set_state_global_active", "exit_code": state_rc})

    window = config.quiet_window()
    receipt = {
        "schema": "agent_skills.project_watchdog.activate_receipt.v1",
        "run_id": run_id,
        "apply": bool(apply),
        "ok": cron_rc == 0 and state_rc == 0,
        "steps": steps,
        "minute": minute,
        "quiet_hours": f"{window[0]:02d}:00-{window[1]:02d}:00" if window else None,
        "note": (
            "automatic issue handling is on; ticks defer during quiet hours and "
            "whenever another tick or lane is still working"
        ),
    }
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["ok"] else 1



#: A tick has been observed at 302.8s. A period at or under that guarantees the
#: next invocation lands on a still-running one, which is the stacking the
#: runaway was made of. 300s is deliberately NOT treated as safe: the review
#: pointed out that 300 < 302.8, so */5 bounds log growth and empty scans but
#: does not by itself guarantee non-overlap -- the real fix is a tick deadline
#: below the period, tracked separately.
OBSERVED_MAX_TICK_SECONDS = 302.8
MIN_SAFE_PERIOD_SECONDS = 120

#: Fraction of the installed period a tick may consume before it stops taking
#: new work. Leaves room for the current issue to finish and for the receipt to
#: be written before the next firing.
TICK_DEADLINE_FRACTION = 0.8
DEFAULT_TICK_DEADLINE_SECONDS = 240


def installed_cron_minute() -> str | None:
    """The minute field of the installed watchdog crontab line, if any."""
    result = run_cmd(["crontab", "-l"], timeout_s=30)
    if result.get("exit_code") != 0:
        return None
    lines = str(result.get("stdout") or "").splitlines()
    for index, line in enumerate(lines):
        # The marker sits on its own comment line above the schedule.
        if config.CRON_MARKER not in line:
            continue
        for following in lines[index:]:
            stripped = following.strip()
            if not stripped or stripped.startswith("#"):
                continue
            return stripped.split()[0]
    return None


def defer_for_deadline(index: int, elapsed: float, deadline: float) -> bool:
    """Whether the tick should stop taking new work.

    Two rules, both deliberate. The check happens BETWEEN issues, never inside
    one: a half-dispatched repair is worse than one deferred to the next tick,
    which is only a period away. And the first issue is always attempted, or a
    tick that is already late would defer forever and no issue would ever be
    served -- a deadline that starves the queue is not a safety property.
    """
    return index > 0 and elapsed >= deadline


def tick_deadline_seconds() -> int:
    """How long a tick may keep taking new work, from the installed schedule.

    Derived rather than configured so the two cannot drift apart: a deadline
    longer than the period is the overlap it exists to prevent. Falls back to a
    bound below the `*/5` default when the crontab cannot be read.
    """
    override = os.environ.get("PROJECT_WATCHDOG_TICK_DEADLINE_SECONDS")
    if override and override.isdigit() and int(override) > 0:
        return int(override)
    minute = installed_cron_minute()
    period = minute_field_period_seconds(minute) if minute else None
    if not period:
        return DEFAULT_TICK_DEADLINE_SECONDS
    return max(30, int(period * TICK_DEADLINE_FRACTION))


def minute_field_period_seconds(minute: str) -> int | None:
    """Shortest gap in seconds between firings of a cron minute field.

    Expands the field rather than matching its spelling, because `*`, `*/1`,
    `0-59` and an enumerated `0,1,...,59` are the same schedule written four
    ways. Returns None when the field cannot be parsed, so an unparseable value
    is never silently treated as safe.
    """
    text = (minute or "").strip()
    if not text:
        return None
    fired: set[int] = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            return None
        step = 1
        if "/" in part:
            part, _, raw_step = part.partition("/")
            if not raw_step.isdigit() or int(raw_step) < 1:
                return None
            step = int(raw_step)
            part = part or "*"
        if part == "*":
            start, end = 0, 59
        elif "-" in part:
            lo, _, hi = part.partition("-")
            if not (lo.isdigit() and hi.isdigit()):
                return None
            start, end = int(lo), int(hi)
        elif part.isdigit():
            start = end = int(part)
        else:
            return None
        if not (0 <= start <= 59 and 0 <= end <= 59 and start <= end):
            return None
        fired.update(range(start, end + 1, step))
    if not fired:
        return None
    if len(fired) == 1:
        return 3600
    ordered = sorted(fired)
    gaps = [(b - a) * 60 for a, b in zip(ordered, ordered[1:])]
    gaps.append((60 - ordered[-1] + ordered[0]) * 60)  # wrap to the next hour
    return min(gaps)


def install_cron(*, apply: bool, minute: str, allow_every_minute: bool = False) -> int:
    """Install or dry-run the crontab line that drives the watchdog.

    The minute field defaults to ``*/5``. GitHub issues want near-immediate
    pickup, so the interval is short; it is not shorter because ``*`` produced
    a measured runaway. A tick whose median is 1.2s has a p90 of 27.5s and a
    maximum of 302.8s, so a 60s period overlaps constantly while a 300s period
    overlaps rarely and the lock skips that case cleanly. The result was 1,381 ``tick_already_running`` collisions, 43,581
    ticks that found nothing, 538 that did work (~1%), and a 1.2 GB log --
    after which the entry was disabled by hand on 2026-08-14.

    ``*`` is still reachable, but only with an explicit flag, so choosing it is
    a decision somebody made rather than a default nobody noticed.
    """
    # Reject by EFFECTIVE FREQUENCY, not spelling. Matching only a bare "*"
    # was bypassable by */1, 0-59, or an enumerated 0,1,2,...,59 -- all of which
    # install the same once-a-minute job the runaway came from. Adversarial
    # review caught this; the check now expands the field and counts.
    period = minute_field_period_seconds(minute)
    if period is None:
        # Fail closed. An unparseable field installed verbatim is a schedule
        # nobody has reasoned about, and cron may interpret it differently than
        # we would guess.
        print(
            f"refusing an unparseable cron minute field {minute!r}; "
            "use a plain field such as '*/5'.",
            file=sys.stderr,
        )
        return 2
    if period < MIN_SAFE_PERIOD_SECONDS and not allow_every_minute:
        print(
            f"refusing a schedule that fires every {period}s: ticks have been observed "
            f"at 302.8s, so anything under {MIN_SAFE_PERIOD_SECONDS}s overlaps and stacks "
            f"(1,381 observed collisions). Use --minute '*/5', or pass "
            "--allow-every-minute to override.",
            file=sys.stderr,
        )
        return 2
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
        f"{shlex.quote(str(config.SKILL_DIR / 'run.sh'))} tick --apply --project all "
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
    # Re-read and merge for the same reason the tick does: a tick running
    # concurrently owns last_served_project and the audit/attestation cooldowns,
    # and writing the whole document back would revert them.
    current = load_json(config.state_path())
    for key in _TICK_OWNED_STATE_KEYS:
        if key in current:
            state[key] = current[key]
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


def ui_payload(*, receipt_limit: int = 100) -> dict[str, Any]:
    """Return the read-only React UI snapshot payload."""
    return build_snapshot(status_payload(), receipt_limit=receipt_limit)


def ui_json(*, receipt_limit: int = 100) -> str:
    return json.dumps(ui_payload(receipt_limit=receipt_limit), indent=2, sort_keys=True)
