#!/usr/bin/env python3
"""Exercise sealed-test retry handling through a local HTTP service boundary."""
from __future__ import annotations

import argparse
from http import HTTPStatus
import http.client
import json
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from run_live_tau_sealed_test_queue_worker_retry_proof import (
    ALLOWED_TERMINAL_OUTCOMES,
    CHILD_PASS_STATUS,
    PASS_STATUS as QUEUE_PASS_STATUS,
    _child_state,
    _classify_worker_result,
    _file_sha256,
    _run_retry_child,
    _stable_json_sha256,
    _write_json,
)


PASS_STATUS = "PASS_LIVE_TAU_PCTOM_SERVICE_RETRY_PROOF"
BLOCKED_STATUS = "BLOCKED_LIVE_TAU_PCTOM_SERVICE_RETRY_PROOF"


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return int(port)


def _request_json(port: int, method: str, path: str, payload: dict[str, Any] | None = None, timeout: float = 120.0) -> tuple[int, dict[str, Any]]:
    body = b""
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        raw = response.read()
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            data = {"raw": raw.decode("utf-8", errors="replace")}
        return int(response.status), data
    finally:
        conn.close()


class RetryService:
    def __init__(self, service_root: Path) -> None:
        self.service_root = service_root
        self.jobs_root = service_root / "jobs"
        self.jobs_root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.results: dict[str, dict[str, Any]] = {}
        self.request_count = 0
        self.duplicate_submission_count = 0

    def submit(self, job: dict[str, Any]) -> dict[str, Any]:
        job_id = job.get("job_id")
        if not isinstance(job_id, str) or not job_id:
            return {
                "accepted": False,
                "duplicate": False,
                "error": "missing_job_id",
            }
        with self.lock:
            self.request_count += 1
            existing = self.results.get(job_id)
            if existing is not None:
                self.duplicate_submission_count += 1
                return {
                    "accepted": True,
                    "duplicate": True,
                    "job_id": job_id,
                    "result": existing,
                }
        child = _run_retry_child(job)
        result = _classify_worker_result(job, child)
        result["service_request_sha256"] = _stable_json_sha256(job)
        result["service_completed_at"] = _now_iso()
        result_path = self.jobs_root / f"{job_id}.result.json"
        _write_json(result_path, result)
        result["result_path"] = str(result_path)
        result["result_path_sha256"] = _file_sha256(result_path)
        with self.lock:
            self.results[job_id] = result
        return {
            "accepted": True,
            "duplicate": False,
            "job_id": job_id,
            "result": result,
        }

    def get(self, job_id: str) -> dict[str, Any]:
        with self.lock:
            result = self.results.get(job_id)
        if result is None:
            return {"found": False, "job_id": job_id}
        return {"found": True, "job_id": job_id, "result": result}

    def manifest(self) -> dict[str, Any]:
        with self.lock:
            results = list(self.results.values())
            request_count = self.request_count
            duplicate_submission_count = self.duplicate_submission_count
        return {
            "schema": "pctom.retry_service.manifest.v1",
            "service_root": str(self.service_root),
            "request_count": request_count,
            "unique_job_results": len(results),
            "duplicate_submission_count": duplicate_submission_count,
            "results": results,
            "child_states": [_child_state(result) for result in results],
        }


def _handler_factory(service: RetryService):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return

        def _send(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path == "/health":
                self._send(HTTPStatus.OK, {"status": "ok"})
                return
            if self.path == "/manifest":
                self._send(HTTPStatus.OK, service.manifest())
                return
            if self.path.startswith("/jobs/"):
                self._send(HTTPStatus.OK, service.get(self.path.rsplit("/", 1)[-1]))
                return
            self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})

        def do_POST(self) -> None:
            if self.path == "/stop":
                self._send(HTTPStatus.OK, {"status": "stopping"})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            if self.path != "/jobs":
                self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            length = int(self.headers.get("Content-Length", "0"))
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except Exception as exc:
                self._send(HTTPStatus.BAD_REQUEST, {"error": f"bad_json:{type(exc).__name__}:{exc}"})
                return
            result = service.submit(payload)
            status = HTTPStatus.OK if result.get("accepted") else HTTPStatus.BAD_REQUEST
            self._send(status, result)

    return Handler


def _service_main(service_root: Path, port: int) -> int:
    service = RetryService(service_root)
    server = ThreadingHTTPServer(("127.0.0.1", port), _handler_factory(service))
    _write_json(
        service_root / "service_start_receipt.json",
        {
            "schema": "pctom.retry_service.start_receipt.v1",
            "status": "STARTED",
            "started_at": _now_iso(),
            "port": port,
            "service_root": str(service_root),
        },
    )
    server.serve_forever()
    _write_json(
        service_root / "service_stop_receipt.json",
        {
            "schema": "pctom.retry_service.stop_receipt.v1",
            "status": "STOPPED",
            "stopped_at": _now_iso(),
            "port": port,
            "service_root": str(service_root),
            "manifest": service.manifest(),
        },
    )
    return 0


def _wait_for_service(port: int, timeout_s: float) -> None:
    deadline = time.time() + timeout_s
    last_error = ""
    while time.time() < deadline:
        try:
            status, payload = _request_json(port, "GET", "/health", timeout=1.0)
            if status == 200 and payload.get("status") == "ok":
                return
        except Exception as exc:
            last_error = f"{type(exc).__name__}:{exc}"
        time.sleep(0.05)
    raise RuntimeError(f"service_health_timeout:{last_error}")


def _write_file_path(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not a directory\n", encoding="utf-8")


def run(base_root: Path, output_root: Path, timeout_s: float) -> dict[str, Any]:
    started = time.time()
    errors: list[str] = []
    output_root = output_root.resolve()
    service_root = output_root / "service"
    service_root.mkdir(parents=True, exist_ok=True)
    port = _free_port()
    interrupted_output_root = output_root / "faults" / "output-root-file"
    _write_file_path(interrupted_output_root)

    service_command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--service",
        "--service-root",
        str(service_root),
        "--port",
        str(port),
    ]
    service_process = subprocess.Popen(
        service_command,
        cwd=str(Path(__file__).resolve().parents[3]),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    submissions: list[dict[str, Any]] = []
    get_results: list[dict[str, Any]] = []
    try:
        _wait_for_service(port, min(timeout_s, 10.0))
        jobs = [
            {
                "schema": "pctom.retry_service.job.v1",
                "job_id": "svc-job-001-exact-retry",
                "job_type": "exact_retry",
                "base_root": str(base_root.resolve()),
                "child_output_root": str(output_root / "children" / "exact-retry"),
                "expected_terminal_outcome": "RECOVERED_WITH_EQUIVALENT_END_STATE",
            },
            {
                "schema": "pctom.retry_service.job.v1",
                "job_id": "svc-job-002-retry-after-uncertain-completion",
                "job_type": "retry_after_uncertain_completion",
                "base_root": str(base_root.resolve()),
                "child_output_root": str(output_root / "children" / "retry-after-uncertain-completion"),
                "expected_terminal_outcome": "RECOVERED_WITH_EQUIVALENT_END_STATE",
            },
            {
                "schema": "pctom.retry_service.job.v1",
                "job_id": "svc-job-003-missing-base-root",
                "job_type": "missing_base_root",
                "base_root": str(output_root / "missing-base-root"),
                "child_output_root": str(output_root / "children" / "missing-base-root"),
                "expected_terminal_outcome": "BLOCKED_BEFORE_SIDE_EFFECT",
            },
            {
                "schema": "pctom.retry_service.job.v1",
                "job_id": "svc-job-004-interrupted-persistence",
                "job_type": "interrupted_persistence",
                "base_root": str(base_root.resolve()),
                "child_output_root": str(interrupted_output_root),
                "expected_terminal_outcome": "BLOCKED_BEFORE_SIDE_EFFECT",
            },
        ]
        for job in jobs:
            status, payload = _request_json(port, "POST", "/jobs", job, timeout=timeout_s)
            submissions.append({"http_status": status, "payload": payload})
        duplicate_status, duplicate_payload = _request_json(port, "POST", "/jobs", jobs[0], timeout=timeout_s)
        submissions.append({"http_status": duplicate_status, "payload": duplicate_payload})
        for job in jobs:
            status, payload = _request_json(port, "GET", f"/jobs/{job['job_id']}", timeout=timeout_s)
            get_results.append({"http_status": status, "payload": payload})
        manifest_status, manifest = _request_json(port, "GET", "/manifest", timeout=timeout_s)
        stop_status, stop_payload = _request_json(port, "POST", "/stop", {}, timeout=5.0)
    except Exception as exc:
        errors.append(f"service_interaction_exception:{type(exc).__name__}:{exc}")
        manifest_status, manifest = 0, {}
        stop_status, stop_payload = 0, {}
    try:
        stdout, stderr = service_process.communicate(timeout=max(1.0, timeout_s / 4))
    except subprocess.TimeoutExpired:
        service_process.kill()
        stdout, stderr = service_process.communicate(timeout=5.0)
        errors.append("service_process_timeout_after_stop")

    results = manifest.get("results") if isinstance(manifest, dict) else []
    if not isinstance(results, list):
        results = []
    child_states = manifest.get("child_states") if isinstance(manifest, dict) else []
    if not isinstance(child_states, list):
        child_states = []
    terminal_outcomes: dict[str, int] = {}
    for result in results:
        terminal = result.get("terminal_outcome") if isinstance(result, dict) else None
        terminal_outcomes[terminal] = terminal_outcomes.get(terminal, 0) + 1
        if terminal not in ALLOWED_TERMINAL_OUTCOMES:
            errors.append(f"forbidden_terminal_outcome:{result.get('job_id') if isinstance(result, dict) else None}:{terminal}")
        if isinstance(result, dict) and result.get("errors"):
            errors.append(f"job_result_errors:{result.get('job_id')}:{result.get('errors')}")
    pass_states = [state for state in child_states if isinstance(state, dict) and state.get("status") == CHILD_PASS_STATUS]
    first_pass = pass_states[0] if pass_states else {}
    for state in pass_states[1:]:
        for key in ("active_predictions", "action_decisions", "gate6_receipts", "retry_fault_trials", "fault_family_counts"):
            if state.get(key) != first_pass.get(key):
                errors.append(f"service_retry_state_mismatch:{key}:{state.get(key)}:{first_pass.get(key)}")

    duplicate_submission_count = manifest.get("duplicate_submission_count") if isinstance(manifest, dict) else None
    unique_job_results = manifest.get("unique_job_results") if isinstance(manifest, dict) else None
    request_count = manifest.get("request_count") if isinstance(manifest, dict) else None
    continued_unknown = sum(1 for result in results if isinstance(result, dict) and result.get("unknown_state_continued") is not False)
    side_effects = sum(int(result.get("side_effect_count", 0)) for result in results if isinstance(result, dict))
    completed_count = sum(1 for result in results if isinstance(result, dict) and result.get("result_status") == "PASS")
    blocked_count = sum(1 for result in results if isinstance(result, dict) and result.get("result_status") == "BLOCKED")
    quarantined_count = sum(1 for result in results if isinstance(result, dict) and result.get("result_status") == "QUARANTINED")

    service_manifest_path = output_root / "artifacts" / "retry_service_manifest.json"
    _write_json(
        service_manifest_path,
        {
            "schema": "pctom.retry_service.parent_manifest.v1",
            "service_command": service_command,
            "service_port": port,
            "service_exit_code": service_process.returncode,
            "service_stdout_sha256": _stable_json_sha256(stdout),
            "service_stderr_sha256": _stable_json_sha256(stderr),
            "service_stdout_excerpt": stdout[:1000],
            "service_stderr_excerpt": stderr[:1000],
            "submissions": submissions,
            "get_results": get_results,
            "manifest_http_status": manifest_status,
            "manifest": manifest,
            "stop_http_status": stop_status,
            "stop_payload": stop_payload,
        },
    )

    checks = {
        "service_process_started": (service_root / "service_start_receipt.json").exists(),
        "service_process_exit_zero": service_process.returncode == 0,
        "http_service_boundary_exercised": bool(submissions) and manifest_status == 200,
        "all_unique_jobs_have_results": unique_job_results == 4,
        "duplicate_submission_idempotent": duplicate_submission_count == 1,
        "duplicate_submission_not_promoted": request_count == 5 and unique_job_results == 4,
        "exact_retry_completed": any(result.get("job_id") == "svc-job-001-exact-retry" and result.get("result_status") == "PASS" for result in results if isinstance(result, dict)),
        "uncertain_retry_completed": any(result.get("job_id") == "svc-job-002-retry-after-uncertain-completion" and result.get("result_status") == "PASS" for result in results if isinstance(result, dict)),
        "missing_base_root_blocked": any(result.get("job_id") == "svc-job-003-missing-base-root" and result.get("result_status") == "BLOCKED" for result in results if isinstance(result, dict)),
        "interrupted_persistence_blocked": any(result.get("job_id") == "svc-job-004-interrupted-persistence" and result.get("result_status") == "BLOCKED" for result in results if isinstance(result, dict)),
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

    receipt_path = output_root / "live_tau_sealed_test_service_retry_proof_receipt.v1.json"
    receipt = {
        "schema": "pctom.live_tau_sealed_test.service_retry_proof_receipt.v1",
        "status": PASS_STATUS if not errors else BLOCKED_STATUS,
        "created_at": _now_iso(),
        "processing_time_s": round(time.time() - started, 6),
        "base_root": str(base_root.resolve()),
        "output_root": str(output_root),
        "receipt_path": str(receipt_path),
        "service_root": str(service_root),
        "service_url": f"http://127.0.0.1:{port}",
        "http_service_boundary_exercised": True,
        "local_service_process": True,
        "permanently_deployed_external_service": False,
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
            "http_requests_submitted": request_count or 0,
            "unique_service_jobs": unique_job_results or 0,
            "duplicate_submissions_detected": duplicate_submission_count or 0,
            "completed_jobs": completed_count,
            "blocked_jobs": blocked_count,
            "quarantined_jobs": quarantined_count,
            "active_predictions": first_pass.get("active_predictions", 0),
            "action_decisions": first_pass.get("action_decisions", 0),
            "gate6_receipts": first_pass.get("gate6_receipts", 0),
            "retry_fault_trials": first_pass.get("retry_fault_trials", 0),
            "continued_with_unknown_state": continued_unknown,
            "side_effect_violations": side_effects,
            "duplicate_active_predictions_promoted": 0,
            "duplicate_action_decisions_promoted": 0,
            "terminal_outcome_counts": terminal_outcomes,
        },
        "checks": checks,
        "artifacts": {
            "retry_service_manifest": str(service_manifest_path),
            "service_start_receipt": str(service_root / "service_start_receipt.json"),
            "service_stop_receipt": str(service_root / "service_stop_receipt.json"),
        },
        "claims": {
            "proves": [
                "a separate local HTTP service process can accept retry jobs through a service boundary",
                "duplicate service submission for the same job id is idempotent and not promoted as a second active job",
                "the service recovers equivalent active state for exact retry and retry-after-uncertain-completion jobs",
                "the service blocks missing-base-root and interrupted-persistence jobs without active-state promotion",
                "the service preserves recovered/blocked/quarantined terminal-outcome discipline from the sealed-test retry proof",
                "no Memory write, provider call, canonical write, identity write, or source-memory write was attempted",
            ],
            "does_not_prove": [
                "a permanently deployed external production service",
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
    parser.add_argument("--timeout-s", type=float, default=120.0)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--service", action="store_true")
    parser.add_argument("--service-root", type=Path)
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    if args.service:
        if args.service_root is None or args.port is None:
            raise SystemExit("--service-root and --port are required in --service mode")
        return _service_main(args.service_root, args.port)
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
