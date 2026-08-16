"""Durable memory of what Ask was blocked on, so avoidance becomes detectable.

Purpose
    Ask emits `BLOCKED` in 58 places and, before this module, persisted none of
    it across runs. A blocker existed for the length of one process and then
    evaporated. That is why no detector could ever catch the failure this was
    built for: an agent hits a blocker on the load-bearing part, does not say
    "blocked", and instead produces a stream of defensible deterministic work
    beside it. Every step is real. None of it touches the thing that stopped.

    `goal-drift` cannot see this. It grades work against the registered human
    goal, and this work *serves* the goal -- it is the right target, avoiding
    the hard part of it. goal-drift would report clean, exactly as the
    knowledge-drift auditor reported clean in the incident that skill was
    written for.

    So the missing substrate is not a cleverer judge. It is memory: a blocker
    nobody recorded cannot be avoided-around detectably.

Design
    Append-only JSONL. A blocker is opened by a run that hit it, and stays open
    until something clears it with live proof. Nothing closes a blocker by
    assertion: `clear()` requires evidence that the live path ran, because "I
    believe this is fixed now" is the same sentence an avoiding agent writes.

    Identity is `(target, failure_code)`, not the run id. The same wall hit by
    three runs is one blocker, or every retry would look like fresh news.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

LEDGER = Path.home() / ".ask" / "blockers.jsonl"
LEDGER_ENV = "ASK_BLOCKER_LEDGER"

OPEN = "open"
CLEARED = "cleared"
ACKNOWLEDGED = "acknowledged"

#: Statuses that mean the run did not get where it was going.
BLOCKED_STATUSES = {"BLOCKED", "NEEDS_ATTENTION"}


def ledger_path() -> Path:
    override = os.environ.get(LEDGER_ENV, "").strip()
    return Path(override) if override else LEDGER


def blocker_key(target: str, failure_code: str) -> str:
    """The same wall hit by three runs is one blocker, not three."""
    return f"{str(target or 'unknown').strip()}::{str(failure_code or 'unspecified').strip()}"


def _append(entry: dict[str, Any]) -> bool:
    try:
        path = ledger_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_file() and path.stat().st_size:
            with path.open("rb") as probe:
                probe.seek(-1, os.SEEK_END)
                if probe.read(1) != b"\n":
                    with path.open("a", encoding="utf-8") as repair:
                        repair.write("\n")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
    except OSError:
        # Recording a blocker must never take a run down. The cost of a failed
        # write is the pre-existing blindness, not a failed roundtable.
        return False
    return True


def record(
    *,
    target: str,
    failure_code: str,
    status: str = "BLOCKED",
    run_dir: str = "",
    message: str = "",
    now: float | None = None,
) -> dict[str, Any]:
    """Open (or re-observe) a blocker. Returns the entry written."""
    entry = {
        "schema": "ask.blocker_ledger_entry.v1",
        "event": OPEN,
        "key": blocker_key(target, failure_code),
        "target": str(target or "unknown"),
        "failure_code": str(failure_code or "unspecified"),
        "status": str(status or "BLOCKED"),
        "run_dir": str(run_dir or ""),
        "message": str(message or "")[:500],
        "at": time.time() if now is None else float(now),
    }
    _append(entry)
    return entry


def clear(
    *,
    target: str,
    failure_code: str,
    live_proof: str,
    run_dir: str = "",
    now: float | None = None,
) -> dict[str, Any]:
    """Close a blocker with evidence that the live path actually ran.

    `live_proof` is required and must be non-empty: a blocker closed by
    assertion is indistinguishable from a blocker being avoided, and the whole
    point of the ledger is to tell those apart.
    """
    proof = str(live_proof or "").strip()
    if not proof:
        raise ValueError(
            "clearing a blocker requires live proof; "
            "'it should work now' is what an avoiding agent also says"
        )
    entry = {
        "schema": "ask.blocker_ledger_entry.v1",
        "event": CLEARED,
        "key": blocker_key(target, failure_code),
        "target": str(target or "unknown"),
        "failure_code": str(failure_code or "unspecified"),
        "live_proof": proof,
        "run_dir": str(run_dir or ""),
        "at": time.time() if now is None else float(now),
    }
    _append(entry)
    return entry


def acknowledge(*, target: str, failure_code: str, note: str = "", now: float | None = None) -> dict[str, Any]:
    """Record that the blocker was reported to the human as blocked.

    This is the honest exit. It does not clear anything -- the wall is still
    there -- but it distinguishes "stopped and said so" from "kept going
    quietly", which is the distinction the detector is looking for.
    """
    entry = {
        "schema": "ask.blocker_ledger_entry.v1",
        "event": ACKNOWLEDGED,
        "key": blocker_key(target, failure_code),
        "target": str(target or "unknown"),
        "failure_code": str(failure_code or "unspecified"),
        "note": str(note or "")[:500],
        "at": time.time() if now is None else float(now),
    }
    _append(entry)
    return entry


def load() -> list[dict[str, Any]]:
    path = ledger_path()
    if not path.is_file():
        return []
    try:
        raw = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    entries: list[dict[str, Any]] = []
    for line in raw:
        if not line.strip():
            continue
        try:
            loaded = json.loads(line)
        except ValueError:
            continue
        if isinstance(loaded, dict) and loaded.get("key"):
            entries.append(loaded)
    return entries


def state() -> dict[str, dict[str, Any]]:
    """Current state per blocker, replayed from the append-only log."""
    current: dict[str, dict[str, Any]] = {}
    for entry in sorted(load(), key=lambda e: float(e.get("at") or 0)):
        key = str(entry["key"])
        event = str(entry.get("event") or OPEN)
        record_for_key = current.setdefault(
            key,
            {
                "key": key,
                "target": entry.get("target"),
                "failure_code": entry.get("failure_code"),
                "state": OPEN,
                "observations": 0,
                "first_seen": entry.get("at"),
            },
        )
        record_for_key["last_seen"] = entry.get("at")
        if event == OPEN:
            record_for_key["observations"] += 1
            # A re-observation reopens: the wall is demonstrably still there,
            # whatever an earlier clear claimed.
            record_for_key["state"] = OPEN
            record_for_key["run_dir"] = entry.get("run_dir")
            record_for_key["message"] = entry.get("message")
        elif event == CLEARED:
            record_for_key["state"] = CLEARED
            record_for_key["live_proof"] = entry.get("live_proof")
        elif event == ACKNOWLEDGED:
            # Acknowledged is a property of an open blocker, not a resolution.
            if record_for_key["state"] != CLEARED:
                record_for_key["state"] = OPEN
            record_for_key["acknowledged"] = True
            record_for_key["acknowledged_note"] = entry.get("note")
    return current


def open_blockers() -> list[dict[str, Any]]:
    return [entry for entry in state().values() if entry.get("state") == OPEN]


def most_specific_failure_code(run_dir: str) -> str:
    """The lane's own failure code, not the run's generic status.

    A run that ends NEEDS_ATTENTION says nothing about the wall; the node
    receipt says `browser_submit_not_accepted`. Recording the generic status
    collapses every distinct blocker into one useless key -- observed on the
    first live run, where four different lane failures all landed as
    `unknown::NEEDS_ATTENTION`.
    """
    root = Path(str(run_dir or ""))
    if not root.is_dir():
        return ""
    for receipt in sorted(root.glob("node-artifacts/*/node-receipt.json")):
        try:
            payload = json.loads(receipt.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        code = str((payload or {}).get("failure_code") or "").strip()
        if code:
            return code
    return ""


def target_of_bundle(bundle: Any) -> str:
    """Ask's target lives at `dag.target.target`, not at the top level."""
    if not isinstance(bundle, dict):
        return ""
    dag = bundle.get("dag") if isinstance(bundle.get("dag"), dict) else bundle
    target = dag.get("target")
    if isinstance(target, dict):
        return str(target.get("target") or target.get("repo") or "")
    if isinstance(target, str) and target:
        return target
    return str(dag.get("dag_id") or "")


def record_from_execution(execution: Any, *, target: str = "", run_dir: str = "") -> dict[str, Any] | None:
    """Record a blocker directly from an Ask execution result, if it is one.

    Wired at the single point where `execution-status.json` is written, so a
    blocker is remembered without any cooperation from the agent that hit it.
    That matters: the agent this detects is, by construction, the one who would
    not have filed the report.
    """
    if not isinstance(execution, dict):
        return None
    status = str(execution.get("status") or "")
    if status not in BLOCKED_STATUSES and execution.get("ok") is not False:
        return None
    failure_code = str(
        execution.get("blocked_reason")
        or execution.get("failure_code")
        or most_specific_failure_code(run_dir)
        or (status or "unspecified")
    )
    return record(
        target=str(target or execution.get("target") or execution.get("dag_id") or "unknown"),
        failure_code=failure_code,
        status=status or "BLOCKED",
        run_dir=str(run_dir or ""),
        message=str(execution.get("message") or ""),
    )
