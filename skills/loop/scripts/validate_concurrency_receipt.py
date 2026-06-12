#!/usr/bin/env python3
"""Validate a concurrency-proof receipt without third-party dependencies."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from typing import Any


RECEIPT_TYPE = "concurrency-proof.v1"
CLAIMS = {"HANDLE_CONCURRENCY_PROVEN", "OVERLAP_PROVEN", "BLOCKED"}
STOP_REASONS = {
    "HANDLES_CLOSED",
    "OVERLAP_CONFIRMED",
    "SOURCE_CHANGED",
    "HANDLE_FAILED",
    "VALIDATION_FAILED",
    "RUNTIME_ERROR",
}
REQUIRED_ROOT_KEYS = {
    "receipt_type",
    "proof_id",
    "objective",
    "claim",
    "stop_reason",
    "agents",
    "spawn_order",
    "wait_order",
    "close_order",
    "overlap",
    "checks_run",
    "source_files_changed_outside_loop",
    "runtime_stderr",
    "remaining_risks",
}


def parse_time(value: Any, ctx: str, errors: list[str]) -> datetime | None:
    if not isinstance(value, str) or not value:
        errors.append(f"{ctx}: expected non-empty ISO timestamp string")
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{ctx}: invalid ISO timestamp {value!r}")
        return None


def require_type(errors: list[str], obj: Any, key: str, expected: type, ctx: str) -> Any:
    if not isinstance(obj, dict) or key not in obj:
        errors.append(f"{ctx}: missing required key {key!r}")
        return None
    value = obj[key]
    if not isinstance(value, expected):
        errors.append(f"{ctx}.{key}: expected {expected.__name__}, got {type(value).__name__}")
        return None
    return value


def require_string_list(errors: list[str], obj: dict[str, Any], key: str, ctx: str) -> list[str]:
    value = require_type(errors, obj, key, list, ctx)
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for idx, item in enumerate(value):
        if not isinstance(item, str):
            errors.append(f"{ctx}.{key}[{idx}]: expected string, got {type(item).__name__}")
        else:
            out.append(item)
    return out


def intervals_overlap(agents: list[dict[str, Any]], errors: list[str]) -> bool:
    intervals: list[tuple[str, datetime, datetime]] = []
    for idx, agent in enumerate(agents):
        label = str(agent.get("label") or f"agent[{idx}]")
        start = parse_time(agent.get("started_at"), f"receipt.agents[{idx}].started_at", errors)
        stop = parse_time(agent.get("stopped_at"), f"receipt.agents[{idx}].stopped_at", errors)
        if start and stop:
            if stop < start:
                errors.append(f"receipt.agents[{idx}]: stopped_at precedes started_at")
            intervals.append((label, start, stop))
    for left_idx, (left_label, left_start, left_stop) in enumerate(intervals):
        for right_label, right_start, right_stop in intervals[left_idx + 1:]:
            if max(left_start, right_start) < min(left_stop, right_stop):
                return True
    return False


def stderr_has_panic(text: str) -> bool:
    lowered = text.lower()
    return "panicked at" in lowered or "failed printing to stdout: broken pipe" in lowered


def validate_receipt(data: dict[str, Any], stderr_text: str | None = None) -> list[str]:
    errors: list[str] = []

    for key in sorted(REQUIRED_ROOT_KEYS):
        if key not in data:
            errors.append(f"receipt: missing required key {key!r}")

    if "final_verdict" in data:
        errors.append("receipt.final_verdict: not allowed for concurrency-proof.v1; use claim")

    receipt_type = require_type(errors, data, "receipt_type", str, "receipt")
    proof_id = require_type(errors, data, "proof_id", str, "receipt")
    objective = require_type(errors, data, "objective", str, "receipt")
    claim = require_type(errors, data, "claim", str, "receipt")
    stop_reason = require_type(errors, data, "stop_reason", str, "receipt")
    agents = require_type(errors, data, "agents", list, "receipt")
    spawn_order = require_string_list(errors, data, "spawn_order", "receipt")
    wait_order = require_string_list(errors, data, "wait_order", "receipt")
    close_order = require_string_list(errors, data, "close_order", "receipt")
    overlap = require_type(errors, data, "overlap", dict, "receipt")
    require_type(errors, data, "checks_run", list, "receipt")
    changed = require_string_list(errors, data, "source_files_changed_outside_loop", "receipt")
    runtime_stderr = require_type(errors, data, "runtime_stderr", dict, "receipt")
    require_string_list(errors, data, "remaining_risks", "receipt")

    if receipt_type != RECEIPT_TYPE:
        errors.append(f"receipt.receipt_type: expected {RECEIPT_TYPE!r}")
    if proof_id == "":
        errors.append("receipt.proof_id: must not be empty")
    if objective == "":
        errors.append("receipt.objective: must not be empty")
    if isinstance(claim, str) and claim not in CLAIMS:
        errors.append(f"receipt.claim: must be one of {sorted(CLAIMS)}")
    if isinstance(stop_reason, str) and stop_reason not in STOP_REASONS:
        errors.append(f"receipt.stop_reason: must be one of {sorted(STOP_REASONS)}")

    labels: list[str] = []
    agent_dicts: list[dict[str, Any]] = []
    if isinstance(agents, list):
        for idx, agent in enumerate(agents):
            ctx = f"receipt.agents[{idx}]"
            if not isinstance(agent, dict):
                errors.append(f"{ctx}: expected object")
                continue
            agent_dicts.append(agent)
            label = require_type(errors, agent, "label", str, ctx)
            require_type(errors, agent, "agent_name", str, ctx)
            require_type(errors, agent, "agent_id", str, ctx)
            spawned = require_type(errors, agent, "spawned_before_first_wait", bool, ctx)
            waited = require_type(errors, agent, "wait_completed", bool, ctx)
            closed = require_type(errors, agent, "handle_closed", bool, ctx)
            edited = require_type(errors, agent, "edited_files", list, ctx)
            inspected = require_type(errors, agent, "inspected_files", list, ctx)
            nested = require_type(errors, agent, "nested_subagents_spawned", bool, ctx)
            parse_time(agent.get("started_at"), f"{ctx}.started_at", errors)
            parse_time(agent.get("stopped_at"), f"{ctx}.stopped_at", errors)
            if isinstance(label, str):
                labels.append(label)
            if spawned is not True and claim in {"HANDLE_CONCURRENCY_PROVEN", "OVERLAP_PROVEN"}:
                errors.append(f"{ctx}.spawned_before_first_wait: must be true for proven claims")
            if waited is not True and claim in {"HANDLE_CONCURRENCY_PROVEN", "OVERLAP_PROVEN"}:
                errors.append(f"{ctx}.wait_completed: must be true for proven claims")
            if closed is not True and claim in {"HANDLE_CONCURRENCY_PROVEN", "OVERLAP_PROVEN"}:
                errors.append(f"{ctx}.handle_closed: must be true for proven claims")
            if isinstance(edited, list) and edited:
                errors.append(f"{ctx}.edited_files: read-only agents must report []")
            if isinstance(inspected, list) and not all(isinstance(item, str) for item in inspected):
                errors.append(f"{ctx}.inspected_files: all entries must be strings")
            if nested is not False:
                errors.append(f"{ctx}.nested_subagents_spawned: must be false")

    if claim in {"HANDLE_CONCURRENCY_PROVEN", "OVERLAP_PROVEN"} and len(labels) < 2:
        errors.append("receipt.agents: proven concurrency claims require at least two agents")

    for key, order in (("spawn_order", spawn_order), ("wait_order", wait_order), ("close_order", close_order)):
        if labels and sorted(order) != sorted(labels):
            errors.append(f"receipt.{key}: must contain exactly the agent labels {labels!r}")

    actual_overlap = intervals_overlap(agent_dicts, errors)
    if isinstance(overlap, dict):
        claimed = require_type(errors, overlap, "claimed", bool, "receipt.overlap")
        proved = require_type(errors, overlap, "proved", bool, "receipt.overlap")
        require_type(errors, overlap, "reason", str, "receipt.overlap")
        if claim == "HANDLE_CONCURRENCY_PROVEN":
            if claimed:
                errors.append("receipt.overlap.claimed: must be false for HANDLE_CONCURRENCY_PROVEN")
            if proved:
                errors.append("receipt.overlap.proved: must be false for HANDLE_CONCURRENCY_PROVEN")
        if claim == "OVERLAP_PROVEN":
            if stop_reason != "OVERLAP_CONFIRMED":
                errors.append("receipt.stop_reason: OVERLAP_PROVEN requires OVERLAP_CONFIRMED")
            if claimed is not True or proved is not True:
                errors.append("receipt.overlap: OVERLAP_PROVEN requires claimed=true and proved=true")
            if not actual_overlap:
                errors.append("receipt.overlap: timestamps do not prove overlap")

    if claim == "HANDLE_CONCURRENCY_PROVEN" and stop_reason != "HANDLES_CLOSED":
        errors.append("receipt.stop_reason: HANDLE_CONCURRENCY_PROVEN requires HANDLES_CLOSED")
    if claim in {"HANDLE_CONCURRENCY_PROVEN", "OVERLAP_PROVEN"} and changed:
        errors.append("receipt.source_files_changed_outside_loop: proven claims require []")

    if isinstance(runtime_stderr, dict):
        panic = require_type(errors, runtime_stderr, "panic_detected", bool, "receipt.runtime_stderr")
        waived = require_type(errors, runtime_stderr, "waived", bool, "receipt.runtime_stderr")
        waiver_reason = require_type(errors, runtime_stderr, "waiver_reason", str, "receipt.runtime_stderr")
        if stderr_text is not None and stderr_has_panic(stderr_text) and panic is not True:
            errors.append("receipt.runtime_stderr.panic_detected: stderr log contains a panic but receipt says false")
        if panic and not waived:
            errors.append("receipt.runtime_stderr: panic_detected requires waived=true or non-accepted claim")
        if waived and not waiver_reason:
            errors.append("receipt.runtime_stderr.waiver_reason: required when waived=true")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a concurrency-proof receipt JSON file.")
    parser.add_argument("receipt", help="Path to concurrency-proof receipt JSON")
    parser.add_argument("--stderr-log", help="Optional monitor stderr log to cross-check runtime_stderr.panic_detected")
    parser.add_argument("--print-summary", action="store_true", help="Print short PASS/FAIL summary")
    args = parser.parse_args()

    try:
        data = json.loads(open(args.receipt, encoding="utf-8").read())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"CONCURRENCY RECEIPT INVALID: {exc}", file=sys.stderr)
        return 2
    if not isinstance(data, dict):
        print("CONCURRENCY RECEIPT INVALID: root must be a JSON object", file=sys.stderr)
        return 2

    stderr_text: str | None = None
    if args.stderr_log:
        try:
            stderr_text = open(args.stderr_log, encoding="utf-8", errors="replace").read()
        except OSError as exc:
            print(f"CONCURRENCY RECEIPT INVALID: could not read stderr log: {exc}", file=sys.stderr)
            return 2

    errors = validate_receipt(data, stderr_text=stderr_text)
    if errors:
        print("CONCURRENCY RECEIPT INVALID", file=sys.stderr)
        for err in errors:
            print(f"- {err}", file=sys.stderr)
        return 1

    if args.print_summary:
        print(
            "CONCURRENCY RECEIPT VALID "
            f"proof_id={data['proof_id']} claim={data['claim']} stop_reason={data['stop_reason']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
