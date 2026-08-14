"""Portable run inspection and control for Ask runs (#1402).

Purpose
    ``list``/``latest``/``show``/``watch``/``steer``/``cancel``/``resume`` over
    Tau identities, built on ``ask.run_projection.v1`` rather than a second
    state model.

    The design constraint that shapes everything here: **Ask does not own
    settlement, so it must not simulate control it does not have.** Tau exposes
    resume and repair; it exposes no steer or cancel seam. Rather than wrap
    process signals and call it control -- which the ticket names as
    non-closure -- unsupported operations report ``unsupported`` truthfully and
    mutate nothing.

    Two separations carry the honesty:

    - A cancellation *request* is not a cancellation. The request is recorded;
      the run only reads ``CANCELLED`` once an authoritative artifact says so.
      An unacknowledged signal that projected as ``CANCELLED`` would tell an
      operator work stopped when it may still be running.
    - Resume skips nodes whose evidence was already admitted. Re-running an
      accepted creator to reach a failed reviewer duplicates real, often paid,
      effects.

Inputs
    A run directory or run id under the Ask artifact root.

Outputs
    Control receipts (``ask.run_control.v1``) and projections.

Failure modes
    A missing run, an unsupported operation, or a stale attempt is reported
    with a reason code and no side effect. Nothing here raises to signal a
    control outcome.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Iterator

from .run_projection import project_run

CONTROL_SCHEMA = "ask.run_control.v1"

# Guidance may narrow but never widen. These are the dimensions a steer could
# be used to escalate, which is why they are rejected before delivery rather
# than validated by the receiving node.
WIDENING_MARKERS = (
    "ignore the goal",
    "ignore previous",
    "change the goal",
    "new goal",
    "disregard the immutable",
    "allow network",
    "allow write",
    "grant access",
    "escalate",
    "sudo",
    "--dangerously",
    "skip evidence",
    "skip proof",
    "no proof needed",
    "bypass",
)

TERMINAL_STAGES = {"SETTLED"}


def artifact_root() -> Path:
    configured = os.environ.get("ASK_RUN_OUTPUT_ROOT")
    if configured:
        return Path(configured)
    return Path("/mnt/storage12tb/skills/ask/outputs/.ask_artifacts/tau-dag-runs")


def _receipt(action: str, run_id: str, **fields: Any) -> dict[str, Any]:
    return {
        "schema": CONTROL_SCHEMA,
        "action": action,
        "run_id": run_id,
        "requested_at": time.time(),
        **fields,
    }


def list_runs(limit: int = 20, root: Path | None = None) -> list[dict[str, Any]]:
    """Recent runs, newest first, bounded.

    Sorted by directory mtime and truncated BEFORE projecting: the corpus is
    ~1700 runs and projecting all of them to show twenty would make ``list``
    cost grow without bound, which the ticket forbids.
    """
    base = root or artifact_root()
    if not base.is_dir():
        return []
    try:
        candidates = [d for d in base.iterdir() if d.is_dir()]
    except OSError:
        return []
    candidates.sort(key=lambda d: d.stat().st_mtime if d.exists() else 0, reverse=True)
    rows: list[dict[str, Any]] = []
    for directory in candidates[: max(1, limit)]:
        projection = project_run(directory)
        rows.append(
            {
                "run_id": projection["run_id"],
                "lifecycle": projection["lifecycle"],
                "mode": projection.get("mode"),
                "goal": (projection.get("immutable_goal") or "")[:60],
                "age_seconds": int(time.time() - directory.stat().st_mtime),
                "nodes": projection["node_count"],
                "unsettled": len(projection["unsettled_nodes"]),
                "next_action": projection["next_action"],
                "run_dir": projection["run_dir"],
            }
        )
    return rows


def resolve_run(run: str, root: Path | None = None) -> Path | None:
    """Accept a run id or a path; return the directory or None."""
    candidate = Path(run)
    if candidate.is_dir():
        return candidate
    base = root or artifact_root()
    direct = base / run
    return direct if direct.is_dir() else None


def watch_events(
    run_dir: Path,
    *,
    poll_seconds: float = 2.0,
    max_polls: int = 0,
) -> Iterator[dict[str, Any]]:
    """Yield semantic events by diffing successive projections.

    Events are derived from the projection rather than from a second event
    stream, so watch can never disagree with ``show`` about a node's state.
    Detaching is the caller's business: this generator has no side effects, so
    abandoning it cannot cancel anything.
    """
    previous: dict[str, str] = {}
    polls = 0
    while True:
        projection = project_run(run_dir)
        for node in projection["nodes"]:
            was = previous.get(node["node_id"])
            now = node["stage"]
            if was != now:
                yield {
                    "event": "node_stage_changed",
                    "run_id": projection["run_id"],
                    "node_id": node["node_id"],
                    "from": was,
                    "to": now,
                    "evidence_admitted": node["evidence_admitted"],
                    "cause": node.get("failure_code") or node.get("limitation"),
                    "at": time.time(),
                }
                previous[node["node_id"]] = now
        if projection["terminal"]:
            yield {
                "event": "run_settled",
                "run_id": projection["run_id"],
                "lifecycle": projection["lifecycle"],
                "at": time.time(),
            }
            return
        polls += 1
        if max_polls and polls >= max_polls:
            yield {
                "event": "watch_detached",
                "run_id": projection["run_id"],
                "reason": "max_polls_reached",
                "at": time.time(),
            }
            return
        time.sleep(poll_seconds)


def guidance_violations(message: str) -> list[str]:
    """Ways a steer would widen scope. Empty means it only narrows."""
    lowered = message.lower()
    return [marker for marker in WIDENING_MARKERS if marker in lowered]


def steer(run_dir: Path, node_id: str, message: str) -> dict[str, Any]:
    """Attempt bounded guidance to one node.

    Validation happens BEFORE any delivery attempt: guidance that would widen
    scope must never reach the node, because a node that receives it has
    already been influenced whether or not it complies.
    """
    projection = project_run(run_dir)
    receipt = _receipt("steer", projection["run_id"], node_id=node_id, delivered=False)

    violations = guidance_violations(message)
    if violations:
        receipt.update(
            outcome="rejected",
            reason_code="guidance_would_widen_scope",
            violations=violations,
            explanation="guidance may narrow a node's work, never widen paths, tools, effects, evidence or the goal",
        )
        return receipt

    node = next((n for n in projection["nodes"] if n["node_id"] == node_id), None)
    if node is None:
        receipt.update(
            outcome="rejected",
            reason_code="unknown_node",
            explanation=f"{node_id} is not in this run's frozen DAG",
        )
        return receipt

    if node["stage"] in TERMINAL_STAGES or projection["terminal"]:
        receipt.update(
            outcome="rejected",
            reason_code="node_already_terminal",
            explanation="a settled node cannot be steered; its evidence is already admitted",
        )
        return receipt

    # No Tau control seam exists for in-flight nodes. Saying so is the honest
    # answer; wrapping a process signal and calling it steering would be the
    # dishonest one the ticket rules out.
    receipt.update(
        outcome="unsupported",
        reason_code="no_tau_control_seam",
        explanation=(
            "Tau exposes resume and repair but no run/node steer seam; "
            "nothing was delivered and no prompt or session was mutated"
        ),
        target_kind=node["target_kind"],
        node_stage=node["stage"],
    )
    return receipt


def cancel(run_dir: Path, node_id: str = "") -> dict[str, Any]:
    """Record a cancellation request; never assert cancellation.

    Required proof 4: request and authoritative acknowledgement are separate.
    An unacknowledged signal that projected as CANCELLED would tell an operator
    the work stopped when it may still be running and still spending.
    """
    projection = project_run(run_dir)
    receipt = _receipt("cancel", projection["run_id"], node_id=node_id or None)

    if projection["terminal"]:
        receipt.update(
            outcome="noop",
            reason_code="already_terminal",
            acknowledged=True,
            lifecycle=projection["lifecycle"],
            explanation="run already settled; nothing to cancel",
        )
        return receipt

    receipt.update(
        outcome="requested",
        reason_code="no_tau_cancel_seam",
        acknowledged=False,
        lifecycle_at_request=projection["lifecycle"],
        explanation=(
            "cancellation requested and recorded; Tau exposes no cancel seam, so this is "
            "NOT an acknowledgement and the run must not be read as CANCELLED"
        ),
    )
    path = run_dir / "cancel-request.json"
    try:
        path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        receipt["receipt_path"] = str(path)
    except OSError as exc:
        receipt["receipt_write_error"] = str(exc)
    return receipt


def resume_plan(run_dir: Path) -> dict[str, Any]:
    """What a resume would rerun, and what it must not.

    Required proof 7: a node whose evidence was admitted is never rerun.
    Re-running an accepted creator to reach a failed reviewer duplicates real
    and often paid effects, which is the failure this plan exists to prevent.
    """
    projection = project_run(run_dir)
    accepted = [n["node_id"] for n in projection["nodes"] if n["evidence_admitted"]]
    rerun = [n["node_id"] for n in projection["nodes"] if not n["evidence_admitted"]]
    return {
        "schema": CONTROL_SCHEMA,
        "action": "resume_plan",
        "run_id": projection["run_id"],
        "already_accepted": accepted,
        "would_rerun": rerun,
        "duplicate_risk": [],
        "source": "node-receipt.json evidence admission, not terminal scrollback",
    }


def resume(run_dir: Path, execute: bool = False) -> dict[str, Any]:
    """Resume through Tau, skipping already-accepted work."""
    plan = resume_plan(run_dir)
    receipt = _receipt("resume", plan["run_id"], plan=plan, executed=False)

    if not plan["would_rerun"]:
        receipt.update(
            outcome="noop",
            reason_code="nothing_unsettled",
            explanation="every node already has admitted evidence",
        )
        return receipt

    tau_run = Path(__file__).resolve().parents[3] / "tau" / "run.sh"
    if not tau_run.is_file():
        receipt.update(
            outcome="unsupported",
            reason_code="tau_wrapper_absent",
            explanation="no Tau wrapper to resume through",
        )
        return receipt

    if not execute:
        receipt.update(
            outcome="planned",
            reason_code="dry_run",
            next_command=f"{tau_run} workflow-resume {run_dir}",
            explanation="resume plan computed; pass execute to run it",
        )
        return receipt

    try:
        completed = subprocess.run(
            [str(tau_run), "workflow-resume", str(run_dir)],
            capture_output=True, text=True, timeout=900, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        receipt.update(outcome="failed", reason_code="resume_invocation_failed", explanation=str(exc)[:200])
        return receipt

    receipt.update(
        executed=True,
        outcome="completed" if completed.returncode == 0 else "failed",
        reason_code="tau_workflow_resume",
        returncode=completed.returncode,
        stderr_excerpt=(completed.stderr or "")[-300:],
    )
    # Verify the promise: nothing already accepted may have been rerun.
    after = project_run(run_dir)
    still_accepted = {n["node_id"] for n in after["nodes"] if n["evidence_admitted"]}
    lost = [n for n in plan["already_accepted"] if n not in still_accepted]
    receipt["accepted_work_preserved"] = not lost
    receipt["lost_accepted_nodes"] = lost
    return receipt
