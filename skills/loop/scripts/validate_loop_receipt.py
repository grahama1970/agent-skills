#!/usr/bin/env python3
"""Validate a $loop skill receipt without third-party dependencies."""
from __future__ import annotations

import argparse
import fnmatch
import json
import sys
from pathlib import PurePosixPath
from typing import Any

VERDICTS = {"PASS", "NEEDS_CHANGES", "BLOCKED"}
STOP_REASONS = {
    "REVIEWER_PASS",
    "REVIEWER_BLOCKED",
    "MAX_ATTEMPTS",
    "SCOPE_BLOCKED",
    "HUMAN_DECISION",
    "SCHEDULE_REGISTERED",
}
REQUIRED_ROOT_KEYS = {
    "loop_id",
    "objective",
    "run_dir",
    "max_attempts",
    "attempts_used",
    "allowed_scope",
    "agents",
    "final_verdict",
    "stop_reason",
    "explorer_receipt",
    "attempts",
    "final_changed_files",
    "final_tests_run",
    "remaining_risks",
}


def is_safe_relative_path(path: str) -> bool:
    if not isinstance(path, str) or not path:
        return False
    p = PurePosixPath(path.replace("\\", "/"))
    return not p.is_absolute() and ".." not in p.parts


def matches_any(path: str, patterns: list[str]) -> bool:
    normalized = path.replace("\\", "/")
    return any(fnmatch.fnmatch(normalized, pat) for pat in patterns)


def changed_file_allowed(path: str, include: list[str], exclude: list[str]) -> bool:
    if not is_safe_relative_path(path):
        return False
    if exclude and matches_any(path, exclude):
        return False
    return matches_any(path, include)


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


def validate_artifact_path(errors: list[str], value: Any, ctx: str, run_dir: str | None) -> None:
    if not isinstance(value, str) or not value:
        errors.append(f"{ctx}: expected non-empty string path")
        return
    if not is_safe_relative_path(value):
        errors.append(f"{ctx}: path must be safe and relative")
        return
    if run_dir and not value.startswith(run_dir.rstrip("/") + "/"):
        errors.append(f"{ctx}: path must live under run_dir {run_dir!r}")


def validate_receipt(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    for key in sorted(REQUIRED_ROOT_KEYS):
        if key not in data:
            errors.append(f"receipt: missing required key {key!r}")

    loop_id = require_type(errors, data, "loop_id", str, "receipt")
    objective = require_type(errors, data, "objective", str, "receipt")
    run_dir = require_type(errors, data, "run_dir", str, "receipt")
    max_attempts = require_type(errors, data, "max_attempts", int, "receipt")
    attempts_used = require_type(errors, data, "attempts_used", int, "receipt")
    allowed_scope = require_type(errors, data, "allowed_scope", dict, "receipt")
    agents = require_type(errors, data, "agents", dict, "receipt")
    final_verdict = require_type(errors, data, "final_verdict", str, "receipt")
    stop_reason = require_type(errors, data, "stop_reason", str, "receipt")
    explorer = require_type(errors, data, "explorer_receipt", dict, "receipt")
    attempts = require_type(errors, data, "attempts", list, "receipt")
    final_changed_files = require_type(errors, data, "final_changed_files", list, "receipt")
    final_tests_run = require_type(errors, data, "final_tests_run", list, "receipt")
    remaining_risks = require_type(errors, data, "remaining_risks", list, "receipt")

    if loop_id == "":
        errors.append("receipt.loop_id: must not be empty")
    if objective == "":
        errors.append("receipt.objective: must not be empty")
    if isinstance(run_dir, str):
        if not run_dir.startswith(".loop/runs/") or not is_safe_relative_path(run_dir):
            errors.append("receipt.run_dir: must be a safe relative path under .loop/runs/")
    if isinstance(max_attempts, int) and not (1 <= max_attempts <= 10):
        errors.append("receipt.max_attempts: must be between 1 and 10")
    if isinstance(final_verdict, str) and final_verdict not in VERDICTS:
        errors.append(f"receipt.final_verdict: must be one of {sorted(VERDICTS)}")
    if isinstance(stop_reason, str) and stop_reason not in STOP_REASONS:
        errors.append(f"receipt.stop_reason: must be one of {sorted(STOP_REASONS)}")

    include: list[str] = []
    exclude: list[str] = []
    if isinstance(allowed_scope, dict):
        include = require_string_list(errors, allowed_scope, "include", "receipt.allowed_scope")
        exclude_val = allowed_scope.get("exclude", [])
        if not isinstance(exclude_val, list):
            errors.append("receipt.allowed_scope.exclude: expected list")
        else:
            exclude = [x for x in exclude_val if isinstance(x, str)]
            if len(exclude) != len(exclude_val):
                errors.append("receipt.allowed_scope.exclude: all entries must be strings")
        if not include:
            errors.append("receipt.allowed_scope.include: must contain at least one glob pattern")

    producer_agent = "coder"
    if isinstance(agents, dict):
        expected = {"explorer": "explorer", "code_reviewer": "code-reviewer"}
        for key, expected_name in expected.items():
            val = agents.get(key)
            if val != expected_name:
                errors.append(f"receipt.agents.{key}: expected {expected_name!r}, got {val!r}")
        if "producer" in agents:
            producer_agent = agents.get("producer")
            if producer_agent not in {"coder", "technical-writer"}:
                errors.append("receipt.agents.producer: expected 'coder' or 'technical-writer'")
        elif agents.get("coder") != "coder":
            errors.append(f"receipt.agents.coder: expected 'coder', got {agents.get('coder')!r}")

    if isinstance(explorer, dict):
        if explorer.get("agent") != "explorer":
            errors.append("receipt.explorer_receipt.agent: expected 'explorer'")
        if explorer.get("mode") != "read_only":
            errors.append("receipt.explorer_receipt.mode: expected 'read_only'")
        for key in ("target_files", "test_files", "risks", "recommended_plan"):
            require_string_list(errors, explorer, key, "receipt.explorer_receipt")
        require_type(errors, explorer, "objective", str, "receipt.explorer_receipt")

    if isinstance(attempts, list) and isinstance(attempts_used, int):
        if attempts_used != len(attempts):
            errors.append(f"receipt.attempts_used: {attempts_used} does not match attempts length {len(attempts)}")
        if isinstance(max_attempts, int) and len(attempts) > max_attempts:
            errors.append(f"receipt.attempts: length {len(attempts)} exceeds max_attempts {max_attempts}")
        if len(attempts) == 0 and final_verdict != "BLOCKED":
            errors.append("receipt.attempts: non-BLOCKED receipt must include at least one attempt")

    reviewer_verdicts: list[str] = []
    pass_seen_at: int | None = None

    if isinstance(attempts, list):
        for idx, attempt in enumerate(attempts, start=1):
            ctx = f"receipt.attempts[{idx - 1}]"
            if not isinstance(attempt, dict):
                errors.append(f"{ctx}: expected object")
                continue
            if attempt.get("attempt") != idx:
                errors.append(f"{ctx}.attempt: expected sequential attempt number {idx}")

            artifact_paths = require_type(errors, attempt, "artifact_paths", dict, ctx)
            coder = require_type(errors, attempt, "coder_receipt", dict, ctx)
            reviewer = require_type(errors, attempt, "code_reviewer_receipt", dict, ctx)

            if isinstance(artifact_paths, dict):
                for key in ("changed_files", "diff", "tests_log", "coder_receipt", "code_reviewer_receipt"):
                    validate_artifact_path(errors, artifact_paths.get(key), f"{ctx}.artifact_paths.{key}", run_dir if isinstance(run_dir, str) else None)

            if isinstance(coder, dict):
                if coder.get("agent") != producer_agent:
                    errors.append(f"{ctx}.coder_receipt.agent: expected {producer_agent!r}")
                if coder.get("attempt") != idx:
                    errors.append(f"{ctx}.coder_receipt.attempt: expected {idx}")
                cf = require_string_list(errors, coder, "changed_files", f"{ctx}.coder_receipt")
                require_string_list(errors, coder, "tests_run", f"{ctx}.coder_receipt")
                require_string_list(errors, coder, "assumptions", f"{ctx}.coder_receipt")
                require_type(errors, coder, "summary", str, f"{ctx}.coder_receipt")
                for f in cf:
                    if include and not changed_file_allowed(f, include, exclude):
                        errors.append(f"{ctx}.coder_receipt.changed_files: {f!r} is outside allowed_scope")

            if isinstance(reviewer, dict):
                if reviewer.get("agent") != "code-reviewer":
                    errors.append(f"{ctx}.code_reviewer_receipt.agent: expected 'code-reviewer'")
                if reviewer.get("attempt") != idx:
                    errors.append(f"{ctx}.code_reviewer_receipt.attempt: expected {idx}")
                if reviewer.get("mode") != "fresh_read_only":
                    errors.append(f"{ctx}.code_reviewer_receipt.mode: expected 'fresh_read_only'")
                verdict = require_type(errors, reviewer, "verdict", str, f"{ctx}.code_reviewer_receipt")
                require_string_list(errors, reviewer, "findings", f"{ctx}.code_reviewer_receipt")
                require_string_list(errors, reviewer, "required_fixes", f"{ctx}.code_reviewer_receipt")
                require_string_list(errors, reviewer, "tests_checked", f"{ctx}.code_reviewer_receipt")
                edited = require_type(errors, reviewer, "edited_files", list, f"{ctx}.code_reviewer_receipt")
                if isinstance(verdict, str):
                    if verdict not in VERDICTS:
                        errors.append(f"{ctx}.code_reviewer_receipt.verdict: must be one of {sorted(VERDICTS)}")
                    reviewer_verdicts.append(verdict)
                    if verdict == "PASS" and pass_seen_at is None:
                        pass_seen_at = idx
                if isinstance(edited, list) and edited:
                    errors.append(f"{ctx}.code_reviewer_receipt.edited_files: reviewer must be read-only; got {edited}")

    if pass_seen_at is not None and isinstance(attempts, list) and pass_seen_at != len(attempts):
        errors.append("receipt.attempts: loop continued after code-reviewer PASS")

    last_verdict = reviewer_verdicts[-1] if reviewer_verdicts else None
    if final_verdict == "PASS":
        if last_verdict != "PASS":
            errors.append("receipt.final_verdict: PASS requires final code_reviewer_receipt.verdict PASS")
        if stop_reason != "REVIEWER_PASS":
            errors.append("receipt.stop_reason: PASS requires REVIEWER_PASS")
        if isinstance(final_tests_run, list) and not final_tests_run and not data.get("no_test_explanation"):
            errors.append("receipt.final_tests_run: PASS requires tests/checks or no_test_explanation")

    if final_verdict == "BLOCKED" and stop_reason in {"REVIEWER_PASS", "MAX_ATTEMPTS"}:
        errors.append(f"receipt.stop_reason: BLOCKED cannot use {stop_reason}")
    if final_verdict != "PASS" and stop_reason == "REVIEWER_PASS":
        errors.append("receipt.stop_reason: REVIEWER_PASS requires final_verdict PASS")
    if final_verdict == "NEEDS_CHANGES" and stop_reason not in {"MAX_ATTEMPTS", "HUMAN_DECISION", "SCOPE_BLOCKED"}:
        errors.append("receipt.stop_reason: NEEDS_CHANGES normally requires MAX_ATTEMPTS, HUMAN_DECISION, or SCOPE_BLOCKED")

    if isinstance(final_changed_files, list):
        for f in final_changed_files:
            if not isinstance(f, str):
                errors.append("receipt.final_changed_files: all entries must be strings")
            elif include and not changed_file_allowed(f, include, exclude):
                errors.append(f"receipt.final_changed_files: {f!r} is outside allowed_scope")

    for key, value in (("final_tests_run", final_tests_run), ("remaining_risks", remaining_risks)):
        if isinstance(value, list):
            for item in value:
                if not isinstance(item, str):
                    errors.append(f"receipt.{key}: all entries must be strings")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a $loop receipt JSON file.")
    parser.add_argument("receipt", help="Path to loop receipt JSON")
    parser.add_argument("--print-summary", action="store_true", help="Print short PASS/FAIL summary")
    args = parser.parse_args()

    try:
        with open(args.receipt, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: could not read JSON: {exc}", file=sys.stderr)
        return 2

    if not isinstance(data, dict):
        print("ERROR: receipt root must be a JSON object", file=sys.stderr)
        return 2

    errors = validate_receipt(data)
    if errors:
        print("LOOP RECEIPT INVALID", file=sys.stderr)
        for err in errors:
            print(f"- {err}", file=sys.stderr)
        return 1

    if args.print_summary:
        print(f"LOOP RECEIPT VALID: {data.get('final_verdict')} after {data.get('attempts_used')} attempt(s)")
    else:
        print("LOOP RECEIPT VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
