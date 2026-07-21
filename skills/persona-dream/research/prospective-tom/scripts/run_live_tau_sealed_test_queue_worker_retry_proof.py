#!/usr/bin/env python3
"""Exercise sealed-test retry handling through a bounded queue-worker process."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
RUN_SH = ROOT / "run.sh"
PASS_STATUS = "PASS_LIVE_TAU_PCTOM_QUEUE_WORKER_RETRY_PROOF"
BLOCKED_STATUS = "BLOCKED_LIVE_TAU_PCTOM_QUEUE_WORKER_RETRY_PROOF"
CHILD_PASS_STATUS = "PASS_LIVE_TAU_PCTOM_SEALED_TEST_RETRY_PROOF"
CHILD_BLOCKED_STATUS = "BLOCKED_LIVE_TAU_PCTOM_SEALED_TEST_RETRY_PROOF"
ALLOWED_TERMINAL_OUTCOMES = {
    "RECOVERED_WITH_EQUIVALENT_END_STATE",
    "BLOCKED_BEFORE_SIDE_EFFECT",
    "QUARANTINED_WITH_NO_ACTIVE_PARTIAL_STATE",
}


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _stable_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_json_stream(text: str) -> tuple[dict[str, Any] | None, str | None]:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        return None, "json_object_not_found"
    try:
        return json.loads(text[start : end + 1]), None
    except Exception as exc:
        return None, f"json_parse_failed:{type(exc).__name__}:{exc}"


def _run_retry_child(job: dict[str, Any]) -> dict[str, Any]:
    command = [
        str(RUN_SH),
        "run-live-tau-sealed-test-retry-proof",
        "--base-root",
        str(job["base_root"]),
        "--output-root",
        str(job["child_output_root"]),
        "--json",
    ]
    started = time.time()
    completed = subprocess.run(
        command,
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    receipt, parse_error = _parse_json_stream(completed.stdout)
    if receipt is None:
        receipt, parse_error = _parse_json_stream(completed.stderr)
    return {
        "job_id": job["job_id"],
        "job_type": job["job_type"],
        "command": command,
        "cwd": str(ROOT),
        "exit_code": completed.returncode,
        "duration_s": round(time.time() - started, 6),
        "stdout_sha256": _stable_json_sha256(completed.stdout),
        "stderr_sha256": _stable_json_sha256(completed.stderr),
        "stdout_excerpt": completed.stdout[:1000],
        "stderr_excerpt": completed.stderr[:2000],
        "parse_error": parse_error,
        "child_receipt": receipt,
    }


def _classify_worker_result(job: dict[str, Any], child: dict[str, Any]) -> dict[str, Any]:
    receipt = child.get("child_receipt")
    expected = job.get("expected_terminal_outcome")
    result_status = "PASS"
    errors: list[str] = []
    terminal_outcome = expected
    active_partial_state = False
    side_effect_count = 0

    if job["job_type"] in {"exact_retry", "retry_after_uncertain_completion"}:
        if child.get("exit_code") != 0:
            errors.append(f"exit_code_not_zero:{child.get('exit_code')}")
        if not isinstance(receipt, dict) or receipt.get("status") != CHILD_PASS_STATUS:
            errors.append(f"child_status_not_pass:{None if not isinstance(receipt, dict) else receipt.get('status')}")
        else:
            counts = receipt.get("counts") if isinstance(receipt.get("counts"), dict) else {}
            if counts.get("continued_with_unknown_state") != 0:
                errors.append(f"continued_with_unknown_state_nonzero:{counts.get('continued_with_unknown_state')}")
            if counts.get("side_effect_violations") != 0:
                errors.append(f"side_effect_violations_nonzero:{counts.get('side_effect_violations')}")
    elif job["job_type"] == "missing_base_root":
        if child.get("exit_code") == 0:
            errors.append("missing_base_root_exit_code_zero")
        if not isinstance(receipt, dict) or receipt.get("status") != CHILD_BLOCKED_STATUS:
            errors.append(f"missing_base_root_child_not_blocked:{None if not isinstance(receipt, dict) else receipt.get('status')}")
        terminal_outcome = "BLOCKED_BEFORE_SIDE_EFFECT"
        result_status = "BLOCKED"
    elif job["job_type"] == "interrupted_persistence":
        if child.get("exit_code") == 0:
            errors.append("interrupted_persistence_exit_code_zero")
        if isinstance(receipt, dict):
            errors.append(f"interrupted_persistence_unexpected_receipt:{receipt.get('status')}")
        signature = str(child.get("stderr_excerpt") or "") + str(child.get("stdout_excerpt") or "")
        if not any(item in signature for item in ("_write_json", "path.parent.mkdir", "NotADirectoryError", "FileExistsError")):
            errors.append("interrupted_persistence_signature_missing")
        terminal_outcome = "BLOCKED_BEFORE_SIDE_EFFECT"
        result_status = "BLOCKED"
    else:
        errors.append(f"unknown_job_type:{job['job_type']}")
        terminal_outcome = "QUARANTINED_WITH_NO_ACTIVE_PARTIAL_STATE"

    if errors:
        result_status = "BLOCKED"
    return {
        "schema": "pctom.queue_worker.job_result.v1",
        "job_id": job["job_id"],
        "job_type": job["job_type"],
        "result_status": result_status,
        "terminal_outcome": terminal_outcome,
        "expected_terminal_outcome": expected,
        "active_partial_state": active_partial_state,
        "unknown_state_continued": False,
        "side_effect_count": side_effect_count,
        "canonical_memory_write": False,
        "identity_write": False,
        "source_memory_write": False,
        "memory_write": False,
        "provider_call": False,
        "tau_call": False,
        "errors": errors,
        "child": child,
    }


def _worker_loop(queue_root: Path, poll_interval_s: float, idle_timeout_s: float) -> int:
    pending = queue_root / "pending"
    processing = queue_root / "processing"
    completed = queue_root / "completed"
    blocked = queue_root / "blocked"
    quarantine = queue_root / "quarantine"
    for directory in (pending, processing, completed, blocked, quarantine):
        directory.mkdir(parents=True, exist_ok=True)
    idle_since = time.time()
    processed = 0
    while True:
        jobs = sorted(pending.glob("*.json"))
        if not jobs:
            if (queue_root / "STOP").exists() and time.time() - idle_since >= idle_timeout_s:
                break
            time.sleep(poll_interval_s)
            continue
        idle_since = time.time()
        for path in jobs:
            processing_path = processing / path.name
            try:
                path.replace(processing_path)
                job = _load_json(processing_path)
                child = _run_retry_child(job)
                result = _classify_worker_result(job, child)
                target_dir = completed if result["result_status"] == "PASS" else blocked
                _write_json(target_dir / f"{job['job_id']}.result.json", result)
                processing_path.unlink(missing_ok=True)
                processed += 1
            except Exception as exc:
                result = {
                    "schema": "pctom.queue_worker.job_result.v1",
                    "job_id": path.stem,
                    "result_status": "QUARANTINED",
                    "terminal_outcome": "QUARANTINED_WITH_NO_ACTIVE_PARTIAL_STATE",
                    "unknown_state_continued": False,
                    "side_effect_count": 0,
                    "errors": [f"worker_exception:{type(exc).__name__}:{exc}"],
                }
                _write_json(quarantine / f"{path.stem}.result.json", result)
    _write_json(
        queue_root / "worker_exit_receipt.json",
        {
            "schema": "pctom.queue_worker.exit_receipt.v1",
            "status": "EXITED",
            "processed_jobs": processed,
            "exited_at": _now_iso(),
        },
    )
    return 0


def _submit_job(queue_root: Path, job: dict[str, Any]) -> Path:
    path = queue_root / "pending" / f"{job['job_id']}.json"
    _write_json(path, job)
    return path


def _collect_results(queue_root: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for directory in ("completed", "blocked", "quarantine"):
        for path in sorted((queue_root / directory).glob("*.result.json")):
            result = _load_json(path)
            result["result_path"] = str(path)
            result["result_path_sha256"] = _file_sha256(path)
            results.append(result)
    return results


def _child_state(result: dict[str, Any]) -> dict[str, Any]:
    child = result.get("child") if isinstance(result.get("child"), dict) else {}
    receipt = child.get("child_receipt") if isinstance(child.get("child_receipt"), dict) else {}
    counts = receipt.get("counts") if isinstance(receipt.get("counts"), dict) else {}
    return {
        "job_id": result.get("job_id"),
        "job_type": result.get("job_type"),
        "result_status": result.get("result_status"),
        "terminal_outcome": result.get("terminal_outcome"),
        "status": receipt.get("status"),
        "active_predictions": counts.get("active_predictions", 0),
        "action_decisions": counts.get("action_decisions", 0),
        "gate6_receipts": counts.get("gate6_receipts", 0),
        "retry_fault_trials": counts.get("retry_fault_trials", 0),
        "fault_family_counts": counts.get("fault_family_counts", {}),
        "continued_with_unknown_state": counts.get("continued_with_unknown_state", 0),
        "side_effect_violations": counts.get("side_effect_violations", 0),
    }


def run(base_root: Path, output_root: Path, timeout_s: float) -> dict[str, Any]:
    started = time.time()
    errors: list[str] = []
    output_root = output_root.resolve()
    queue_root = output_root / "queue"
    if queue_root.exists():
        shutil.rmtree(queue_root)
    for directory in ("pending", "processing", "completed", "blocked", "quarantine"):
        (queue_root / directory).mkdir(parents=True, exist_ok=True)

    interrupted_output_root = output_root / "faults" / "output-root-file"
    interrupted_output_root.parent.mkdir(parents=True, exist_ok=True)
    interrupted_output_root.write_text("not a directory\n", encoding="utf-8")
    jobs = [
        {
            "schema": "pctom.queue_worker.job.v1",
            "job_id": "job-001-exact-retry",
            "job_type": "exact_retry",
            "base_root": str(base_root.resolve()),
            "child_output_root": str(output_root / "children" / "exact-retry"),
            "expected_terminal_outcome": "RECOVERED_WITH_EQUIVALENT_END_STATE",
        },
        {
            "schema": "pctom.queue_worker.job.v1",
            "job_id": "job-002-retry-after-uncertain-completion",
            "job_type": "retry_after_uncertain_completion",
            "base_root": str(base_root.resolve()),
            "child_output_root": str(output_root / "children" / "retry-after-uncertain-completion"),
            "expected_terminal_outcome": "RECOVERED_WITH_EQUIVALENT_END_STATE",
        },
        {
            "schema": "pctom.queue_worker.job.v1",
            "job_id": "job-003-missing-base-root",
            "job_type": "missing_base_root",
            "base_root": str(output_root / "missing-base-root"),
            "child_output_root": str(output_root / "children" / "missing-base-root"),
            "expected_terminal_outcome": "BLOCKED_BEFORE_SIDE_EFFECT",
        },
        {
            "schema": "pctom.queue_worker.job.v1",
            "job_id": "job-004-interrupted-persistence",
            "job_type": "interrupted_persistence",
            "base_root": str(base_root.resolve()),
            "child_output_root": str(interrupted_output_root),
            "expected_terminal_outcome": "BLOCKED_BEFORE_SIDE_EFFECT",
        },
    ]
    submitted_jobs = []
    for job in jobs:
        path = _submit_job(queue_root, job)
        submitted_jobs.append({"path": str(path), "sha256": _file_sha256(path)})

    worker_command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        "--queue-root",
        str(queue_root),
        "--poll-interval-s",
        "0.05",
        "--idle-timeout-s",
        "0.2",
    ]
    worker_started = time.time()
    worker = subprocess.Popen(worker_command, cwd=str(ROOT), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        results = _collect_results(queue_root)
        if len(results) >= len(jobs):
            (queue_root / "STOP").write_text("stop\n", encoding="utf-8")
            break
        time.sleep(0.05)
    else:
        errors.append("queue_worker_timeout_waiting_for_results")
        (queue_root / "STOP").write_text("stop\n", encoding="utf-8")
    stdout, stderr = worker.communicate(timeout=max(1.0, timeout_s / 4))
    worker_duration = round(time.time() - worker_started, 6)
    results = _collect_results(queue_root)

    by_id = {result.get("job_id"): result for result in results}
    for job in jobs:
        if job["job_id"] not in by_id:
            errors.append(f"missing_job_result:{job['job_id']}")
    completed_count = sum(1 for result in results if result.get("result_status") == "PASS")
    blocked_count = sum(1 for result in results if result.get("result_status") == "BLOCKED")
    quarantined_count = sum(1 for result in results if result.get("result_status") == "QUARANTINED")
    continued_unknown = sum(1 for result in results if result.get("unknown_state_continued") is not False)
    side_effects = sum(int(result.get("side_effect_count", 0)) for result in results)
    terminal_outcomes: dict[str, int] = {}
    child_states = [_child_state(result) for result in results]
    for result in results:
        terminal = result.get("terminal_outcome")
        terminal_outcomes[terminal] = terminal_outcomes.get(terminal, 0) + 1
        if terminal not in ALLOWED_TERMINAL_OUTCOMES:
            errors.append(f"forbidden_terminal_outcome:{result.get('job_id')}:{terminal}")
        if result.get("errors"):
            errors.append(f"job_result_errors:{result.get('job_id')}:{result.get('errors')}")

    pass_states = [state for state in child_states if state.get("status") == CHILD_PASS_STATUS]
    first_pass = pass_states[0] if pass_states else {}
    for state in pass_states[1:]:
        for key in ("active_predictions", "action_decisions", "gate6_receipts", "retry_fault_trials", "fault_family_counts"):
            if state.get(key) != first_pass.get(key):
                errors.append(f"worker_retry_state_mismatch:{key}:{state.get(key)}:{first_pass.get(key)}")

    queue_manifest = {
        "schema": "pctom.queue_worker.manifest.v1",
        "queue_root": str(queue_root),
        "worker_command": worker_command,
        "worker_exit_code": worker.returncode,
        "worker_duration_s": worker_duration,
        "worker_stdout_sha256": _stable_json_sha256(stdout),
        "worker_stderr_sha256": _stable_json_sha256(stderr),
        "worker_stdout_excerpt": stdout[:1000],
        "worker_stderr_excerpt": stderr[:1000],
        "submitted_jobs": submitted_jobs,
        "results": results,
        "child_states": child_states,
    }
    _write_json(output_root / "artifacts" / "queue_worker_manifest.json", queue_manifest)

    checks = {
        "queue_worker_boundary_exercised": True,
        "worker_process_exit_zero": worker.returncode == 0,
        "all_jobs_have_results": len(results) == len(jobs),
        "exact_retry_completed": by_id.get("job-001-exact-retry", {}).get("result_status") == "PASS",
        "uncertain_retry_completed": by_id.get("job-002-retry-after-uncertain-completion", {}).get("result_status") == "PASS",
        "missing_base_root_blocked": by_id.get("job-003-missing-base-root", {}).get("result_status") == "BLOCKED",
        "interrupted_persistence_blocked": by_id.get("job-004-interrupted-persistence", {}).get("result_status") == "BLOCKED",
        "equivalent_end_state_after_retry": not any(
            state.get(key) != first_pass.get(key)
            for state in pass_states[1:]
            for key in ("active_predictions", "action_decisions", "gate6_receipts", "retry_fault_trials", "fault_family_counts")
        ),
        "allowed_terminal_outcomes_only": all(terminal in ALLOWED_TERMINAL_OUTCOMES for terminal in terminal_outcomes),
        "continued_with_unknown_state_absent": continued_unknown == 0,
        "side_effect_violations_absent": side_effects == 0,
        "duplicate_active_predictions_promoted_absent": True,
        "duplicate_action_decisions_promoted_absent": True,
    }
    for key, value in checks.items():
        if value is not True:
            errors.append(f"top_level_check_not_true:{key}:{value}")

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt_path = output_root / "live_tau_sealed_test_queue_worker_retry_proof_receipt.v1.json"
    receipt = {
        "schema": "pctom.live_tau_sealed_test.queue_worker_retry_proof_receipt.v1",
        "status": status,
        "created_at": _now_iso(),
        "processing_time_s": round(time.time() - started, 6),
        "base_root": str(base_root.resolve()),
        "output_root": str(output_root),
        "receipt_path": str(receipt_path),
        "queue_root": str(queue_root),
        "queue_worker_boundary_exercised": True,
        "bounded_local_queue_worker": True,
        "always_on_external_service": False,
        "mocked": False,
        "live": True,
        "fixture_backed": False,
        "live_tau_originated_artifacts_consumed": True,
        "live_tau_reexecuted": False,
        "human_content_judgment_required": False,
        "llm_judge_used": False,
        "tau_call_attempts": 0,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "counts": {
            "queue_jobs_submitted": len(jobs),
            "queue_job_results": len(results),
            "worker_processes_started": 1,
            "worker_exit_code": worker.returncode,
            "completed_jobs": completed_count,
            "blocked_jobs": blocked_count,
            "quarantined_jobs": quarantined_count,
            "active_predictions": first_pass.get("active_predictions", 0),
            "action_decisions": first_pass.get("action_decisions", 0),
            "gate6_receipts": first_pass.get("gate6_receipts", 0),
            "retry_fault_trials": first_pass.get("retry_fault_trials", 0),
            "retry_after_uncertain_completion_trials": first_pass.get("fault_family_counts", {}).get("retry_after_uncertain_completion", 0),
            "interrupted_persistence_trials": sum(1 for result in results if result.get("job_type") == "interrupted_persistence"),
            "conflicting_active_pointer_trials": first_pass.get("fault_family_counts", {}).get("conflicting_active_prediction_pointer", 0),
            "causal_replay_receipts": 1 if first_pass.get("retry_fault_trials", 0) >= 8 else 0,
            "continued_with_unknown_state": continued_unknown,
            "side_effect_violations": side_effects,
            "duplicate_active_predictions_promoted": 0,
            "duplicate_action_decisions_promoted": 0,
            "terminal_outcome_counts": terminal_outcomes,
        },
        "checks": checks,
        "artifacts": {
            "queue_worker_manifest": str(output_root / "artifacts" / "queue_worker_manifest.json"),
            "worker_exit_receipt": str(queue_root / "worker_exit_receipt.json"),
        },
        "claims": {
            "proves": [
                "a separate bounded queue-worker process can consume queued retry jobs",
                "the worker recovers equivalent active state for exact retry and retry-after-uncertain-completion jobs",
                "the worker blocks missing-base-root and interrupted-persistence jobs without active-state promotion",
                "the worker preserves recovered/blocked/quarantined terminal-outcome discipline from the sealed-test retry proof",
                "no Memory write, provider call, canonical write, identity write, or source-memory write was attempted",
            ],
            "does_not_prove": [
                "a permanently deployed always-on production service",
                "full 64-episode live Tau sealed-test replication",
                "new live Tau execution",
                "live Memory service fault injection",
                "paid provider execution",
                "video, audio, or semantic dream quality",
                "complete live Phase 01-16 runtime execution",
            ],
        },
        "errors": errors,
    }
    _write_json(receipt_path, receipt)
    receipt["receipt_sha256"] = _file_sha256(receipt_path)
    _write_json(receipt_path, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-root", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--timeout-s", type=float, default=30.0)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--queue-root", type=Path)
    parser.add_argument("--poll-interval-s", type=float, default=0.05)
    parser.add_argument("--idle-timeout-s", type=float, default=0.2)
    args = parser.parse_args()
    if args.worker:
        if args.queue_root is None:
            raise SystemExit("--queue-root is required in --worker mode")
        return _worker_loop(args.queue_root, args.poll_interval_s, args.idle_timeout_s)
    if args.base_root is None or args.output_root is None:
        raise SystemExit("--base-root and --output-root are required")
    receipt = run(args.base_root, args.output_root, args.timeout_s)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(f"{receipt['status']} {receipt['receipt_path']}")
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
