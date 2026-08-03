#!/usr/bin/env python3
"""Bounded QRA final-assessment worker for monitor-sparta.

This worker is a thin subagent wrapper around:

    monitor_sparta.py qra-final-assessment

It owns retry discipline and receipts. It does not repair QRAs, upload to
Hugging Face, or decide global monitor-sparta completion.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Sequence


DEFAULT_MEMORY_ROOT = Path("/home/graham/workspace/experiments/memory")
DEFAULT_RUN_ROOT = Path("/mnt/storage12tb/skills/review-db/outputs/qra-auditor/final-assessment")
DEFAULT_MONITOR_OUTPUT = Path(
    "/mnt/storage12tb/skills/review-db/outputs/monitor-sparta-supervisor/final-qra-assessment"
)


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True, default=str) + "\n")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def classify_attempt(
    *,
    proc: subprocess.CompletedProcess[str],
    receipt_path: Path,
) -> tuple[str, dict[str, Any] | None, str | None]:
    """Classify one monitor-sparta command attempt."""
    if not proc.stdout.strip() and not receipt_path.exists():
        return "retryable_empty_response", None, "stdout_empty_and_receipt_missing"
    if not receipt_path.exists():
        return "retryable_missing_receipt", None, "receipt_missing"
    try:
        receipt = load_json(receipt_path)
    except Exception as exc:  # noqa: BLE001
        return "retryable_malformed_receipt", None, f"{type(exc).__name__}: {exc}"

    if receipt.get("profile") != "monitor_sparta_final_qra_quality_assessment":
        return "retryable_malformed_receipt", receipt, f"unexpected_profile:{receipt.get('profile')}"

    failed = int((receipt.get("overall") or {}).get("failed") or 0)
    ledger = receipt.get("ledger") if isinstance(receipt.get("ledger"), dict) else {}
    if proc.returncode == 0 and failed == 0:
        return "pass", receipt, None
    if failed > 0:
        return "assessment_failed", receipt, f"overall_failed:{failed}"
    if ledger.get("applied") is False and "apply_ledger" in " ".join(proc.args if isinstance(proc.args, list) else []):
        return "assessment_failed", receipt, "ledger_not_applied"
    return "retryable_command_failure", receipt, f"returncode:{proc.returncode}"


def run(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    run_id = args.run_id or f"qra-final-assessment-worker-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    run_dir = Path(args.run_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    request_path = run_dir / "request.json"
    events_path = run_dir / "events.jsonl"
    attempts_path = run_dir / "attempts.jsonl"
    receipt_path = run_dir / "receipt.json"
    monitor_output = Path(args.monitor_output)

    request = {
        "schema": "qra_auditor.final_assessment.request.v1",
        "run_id": run_id,
        "created_at": utc_now(),
        "memory_root": str(args.memory_root),
        "monitor_output": str(monitor_output),
        "samples_per_stratum": args.samples_per_stratum,
        "candidate_probe_limit": args.candidate_probe_limit,
        "max_total_samples": args.max_total_samples,
        "max_strata": args.max_strata,
        "apply_ledger": args.apply_ledger,
        "max_attempts": args.max_attempts,
        "timeout_seconds": args.timeout_seconds,
        "mocked": False,
        "live": True,
    }
    write_json(request_path, request)
    append_jsonl(
        events_path,
        {
            "run_id": run_id,
            "phase": "start",
            "current_artifact": str(request_path),
            "command_or_api": "qra_final_assessment_worker",
            "evidence": {"paths": [str(request_path)]},
            "bug_or_blocker": None,
            "next_step": "invoke monitor_sparta.py qra-final-assessment",
            "stop_condition": "pass_or_valid_failed_assessment_or_retry_budget_exhausted",
        },
    )

    attempts: list[dict[str, Any]] = []
    final_monitor_receipt: dict[str, Any] | None = None
    terminal_status = "BLOCKED_NO_ATTEMPT"
    terminal_reason: str | None = None
    monitor_receipt_path: Path | None = None

    for attempt_num in range(1, args.max_attempts + 1):
        attempt_run_id = run_id if attempt_num == 1 else f"{run_id}-retry-{attempt_num}"
        monitor_receipt_path = monitor_output / attempt_run_id / "final_receipt.json"
        cmd = [
            sys.executable,
            str(Path(args.memory_root) / "scripts" / "validation" / "monitor_sparta.py"),
            "qra-final-assessment",
            "--samples-per-stratum",
            str(args.samples_per_stratum),
            "--candidate-probe-limit",
            str(args.candidate_probe_limit),
            "--max-total-samples",
            str(args.max_total_samples),
            "--run-id",
            attempt_run_id,
            "--output-dir",
            str(monitor_output),
            "--json",
        ]
        if args.max_strata is not None:
            cmd.extend(["--max-strata", str(args.max_strata)])
        if args.apply_ledger:
            cmd.append("--apply-ledger")

        append_jsonl(
            events_path,
            {
                "run_id": run_id,
                "phase": "attempt_start",
                "attempt": attempt_num,
                "current_artifact": str(monitor_receipt_path),
                "command_or_api": " ".join(cmd),
                "evidence": {"paths": []},
                "bug_or_blocker": None,
                "next_step": "wait_for_monitor_receipt",
                "stop_condition": "receipt_classified",
            },
        )
        started = time.time()
        try:
            proc = subprocess.run(
                cmd,
                text=True,
                capture_output=True,
                timeout=args.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            attempt = {
                "attempt": attempt_num,
                "status": "retryable_timeout",
                "reason": f"timeout_seconds:{args.timeout_seconds}",
                "duration_seconds": round(time.time() - started, 3),
                "stdout_len": len(exc.stdout or ""),
                "stderr_len": len(exc.stderr or ""),
                "monitor_receipt_path": str(monitor_receipt_path),
            }
            attempts.append(attempt)
            append_jsonl(attempts_path, attempt)
            if attempt_num >= args.max_attempts:
                terminal_status = "BLOCKED_RETRY_BUDGET_EXHAUSTED"
                terminal_reason = attempt["reason"]
                break
            continue

        status, monitor_receipt, reason = classify_attempt(proc=proc, receipt_path=monitor_receipt_path)
        final_monitor_receipt = monitor_receipt
        attempt = {
            "attempt": attempt_num,
            "status": status,
            "reason": reason,
            "returncode": proc.returncode,
            "duration_seconds": round(time.time() - started, 3),
            "stdout_len": len(proc.stdout or ""),
            "stderr_len": len(proc.stderr or ""),
            "monitor_receipt_path": str(monitor_receipt_path),
            "overall": (monitor_receipt or {}).get("overall") if monitor_receipt else None,
        }
        attempts.append(attempt)
        append_jsonl(attempts_path, attempt)

        if status == "pass":
            terminal_status = "PASS"
            terminal_reason = None
            break
        if status == "assessment_failed":
            terminal_status = "ASSESSMENT_FAILED"
            terminal_reason = reason
            break
        if attempt_num >= args.max_attempts:
            terminal_status = "BLOCKED_RETRY_BUDGET_EXHAUSTED"
            terminal_reason = reason
            break

    receipt = {
        "schema": "qra_auditor.final_assessment_worker.receipt.v1",
        "run_id": run_id,
        "run_dir": str(run_dir),
        "terminal_status": terminal_status,
        "terminal_reason": terminal_reason,
        "attempts_used": len(attempts),
        "max_attempts": args.max_attempts,
        "retry_policy": {
            "retry_on": ["empty_response", "malformed_json", "missing_receipt", "timeout", "transient_command_failure"],
            "stop_on": ["pass", "valid_failed_assessment", "retry_budget_exhausted"],
        },
        "monitor_receipt_path": str(monitor_receipt_path) if monitor_receipt_path else None,
        "monitor_overall": (final_monitor_receipt or {}).get("overall") if final_monitor_receipt else None,
        "global_product_blockers": (final_monitor_receipt or {}).get("global_product_blockers") if final_monitor_receipt else None,
        "artifacts": {
            "request": str(request_path),
            "events": str(events_path),
            "attempts": str(attempts_path),
            "receipt": str(receipt_path),
        },
        "mocked": False,
        "live": True,
    }
    write_json(receipt_path, receipt)
    append_jsonl(
        events_path,
        {
            "run_id": run_id,
            "phase": "final",
            "current_artifact": str(receipt_path),
            "command_or_api": "qra_final_assessment_worker",
            "evidence": {"counts": {"attempts_used": len(attempts)}, "paths": [str(receipt_path)]},
            "bug_or_blocker": None if terminal_status == "PASS" else terminal_status,
            "next_step": "consume_receipt_or_repair_manifest",
            "stop_condition": terminal_status,
        },
    )
    if terminal_status == "PASS":
        return 0, receipt
    if terminal_status == "ASSESSMENT_FAILED":
        return 10, receipt
    return 20, receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id")
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--memory-root", type=Path, default=DEFAULT_MEMORY_ROOT)
    parser.add_argument("--monitor-output", type=Path, default=DEFAULT_MONITOR_OUTPUT)
    parser.add_argument("--samples-per-stratum", type=int, default=2)
    parser.add_argument("--candidate-probe-limit", type=int, default=5000)
    parser.add_argument("--max-total-samples", type=int, default=500)
    parser.add_argument("--max-strata", type=int)
    parser.add_argument("--apply-ledger", action="store_true")
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.max_attempts < 1:
        raise SystemExit("--max-attempts must be >= 1")
    rc, receipt = run(args)
    print(json.dumps(receipt, indent=2, sort_keys=True, default=str))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
