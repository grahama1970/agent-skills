#!/usr/bin/env python3
"""Restart Memory, then prove delayed PCTOM-R recall still works."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from run_live_memory_revision_recall import _file_sha256, _load_json, _write_json


PASS_STATUS = "PASS_PCTOM_LIVE_MEMORY_RESTART_DELAYED_RECALL"
BLOCKED_STATUS = "BLOCKED_PCTOM_LIVE_MEMORY_RESTART_DELAYED_RECALL"


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _run_command(argv: list[str], *, timeout_s: float) -> dict[str, Any]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        return {
            "argv": argv,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
            "timeout": False,
            "duration_s": round(time.monotonic() - started, 6),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "argv": argv,
            "returncode": None,
            "stdout": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
            "timeout": True,
            "duration_s": round(time.monotonic() - started, 6),
        }


def _systemctl_show(service_name: str) -> dict[str, Any]:
    result = _run_command(
        [
            "systemctl",
            "--user",
            "show",
            service_name,
            "--property=LoadState,ActiveState,SubState,MainPID,ExecMainPID,FragmentPath",
            "--no-pager",
        ],
        timeout_s=10.0,
    )
    fields: dict[str, str] = {}
    for line in result.get("stdout", "").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            fields[key] = value
    result["fields"] = fields
    return result


def _memory_health(memory_base_url: str) -> dict[str, Any]:
    started = time.monotonic()
    try:
        with httpx.Client(base_url=memory_base_url.rstrip("/"), timeout=httpx.Timeout(5.0, connect=2.0)) as client:
            response = client.get("/health")
        data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        return {
            "http_status": response.status_code,
            "ok": bool(isinstance(data, dict) and data.get("ok") is True),
            "data": data,
            "error": None,
            "duration_s": round(time.monotonic() - started, 6),
        }
    except Exception as exc:  # noqa: BLE001 - receipt needs concrete failure text.
        return {
            "http_status": None,
            "ok": False,
            "data": None,
            "error": repr(exc),
            "duration_s": round(time.monotonic() - started, 6),
        }


def _wait_for_memory(memory_base_url: str, service_name: str, timeout_s: float, sleep_s: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    attempts: list[dict[str, Any]] = []
    while True:
        show = _systemctl_show(service_name)
        health = _memory_health(memory_base_url)
        attempt = {
            "at": _now_iso(),
            "systemctl": show,
            "health": health,
        }
        attempts.append(attempt)
        fields = show.get("fields") if isinstance(show.get("fields"), dict) else {}
        if fields.get("ActiveState") == "active" and fields.get("SubState") == "running" and health.get("ok") is True:
            return {
                "ready": True,
                "attempts": attempts,
                "final_systemctl": show,
                "final_health": health,
            }
        if time.monotonic() >= deadline:
            return {
                "ready": False,
                "attempts": attempts,
                "final_systemctl": show,
                "final_health": health,
            }
        time.sleep(sleep_s)


def run(
    *,
    source_root: Path,
    output_root: Path,
    receipt_out: Path,
    memory_base_url: str,
    service_name: str,
    wait_timeout_s: float,
    wait_sleep_s: float,
    recall_attempts: int,
    recall_sleep_s: float,
) -> dict[str, Any]:
    started = time.monotonic()
    errors: list[str] = []
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    source_root = source_root.resolve()
    delayed_output_root = output_root / "delayed_after_restart"
    delayed_receipt_path = delayed_output_root / "live_memory_revision_delayed_recall_receipt.v1.json"

    pre_systemctl = _systemctl_show(service_name)
    pre_health = _memory_health(memory_base_url)
    pre_fields = pre_systemctl.get("fields") if isinstance(pre_systemctl.get("fields"), dict) else {}
    pre_pid = str(pre_fields.get("MainPID") or "")
    if pre_fields.get("ActiveState") != "active":
        errors.append(f"pre_memory_service_not_active:{pre_fields.get('ActiveState')}")
    if pre_health.get("ok") is not True:
        errors.append(f"pre_memory_health_not_ok:{pre_health.get('http_status')}:{pre_health.get('error')}")

    restart_result = _run_command(["systemctl", "--user", "restart", service_name], timeout_s=30.0)
    if restart_result.get("returncode") != 0:
        errors.append(f"memory_service_restart_returncode:{restart_result.get('returncode')}")
    if restart_result.get("timeout") is True:
        errors.append("memory_service_restart_timeout")

    wait_result = _wait_for_memory(memory_base_url, service_name, wait_timeout_s, wait_sleep_s)
    post_systemctl = wait_result.get("final_systemctl") if isinstance(wait_result.get("final_systemctl"), dict) else {}
    post_fields = post_systemctl.get("fields") if isinstance(post_systemctl.get("fields"), dict) else {}
    post_pid = str(post_fields.get("MainPID") or "")
    pid_changed = bool(pre_pid and post_pid and pre_pid != post_pid and post_pid != "0")
    if wait_result.get("ready") is not True:
        errors.append("memory_service_not_ready_after_restart")
    if not pid_changed:
        errors.append(f"memory_service_pid_not_changed:{pre_pid}:{post_pid}")

    delayed_cmd = [
        sys.executable,
        str(Path(__file__).with_name("run_live_memory_revision_delayed_recall.py")),
        "--source-root",
        str(source_root),
        "--output-root",
        str(delayed_output_root),
        "--receipt-out",
        str(delayed_receipt_path),
        "--memory-base-url",
        memory_base_url,
        "--recall-attempts",
        str(recall_attempts),
        "--recall-sleep-s",
        str(recall_sleep_s),
        "--json",
    ]
    delayed_result = _run_command(delayed_cmd, timeout_s=max(60.0, wait_timeout_s + recall_attempts * max(1.0, recall_sleep_s) + 20.0))
    if delayed_result.get("returncode") != 0:
        errors.append(f"delayed_recall_after_restart_returncode:{delayed_result.get('returncode')}")
    delayed_receipt = _load_json(delayed_receipt_path, errors, "delayed_recall_after_restart_receipt")
    if not isinstance(delayed_receipt, dict):
        delayed_receipt = {}
    if delayed_receipt.get("status") != "PASS_PCTOM_LIVE_MEMORY_REVISION_DELAYED_RECALL":
        errors.append(f"delayed_recall_after_restart_status:{delayed_receipt.get('status')}")

    delayed_counts = delayed_receipt.get("counts") if isinstance(delayed_receipt.get("counts"), dict) else {}
    for key, minimum in (
        ("source_memory_documents", 16),
        ("source_semantic_documents", 16),
        ("delayed_exact_rereads", 16),
        ("delayed_semantic_exact_rereads", 16),
        ("delayed_recall_queries", 4),
        ("delayed_recall_hits", 4),
    ):
        if int(delayed_counts.get(key, 0) or 0) < minimum:
            errors.append(f"delayed_recall_after_restart_count_lt:{key}:{delayed_counts.get(key)}:{minimum}")
    for key in (
        "memory_write_attempts",
        "canonical_memory_write_attempts",
        "identity_write_attempts",
        "source_memory_write_attempts",
        "tau_call_attempts",
        "provider_call_attempts",
    ):
        if int(delayed_receipt.get(key, 0) or 0) != 0:
            errors.append(f"delayed_recall_after_restart_side_effect_counter_nonzero:{key}:{delayed_receipt.get(key)}")

    receipt = {
        "schema": "persona_dream.research.prospective_tom.live_memory_restart_delayed_recall_receipt.v1",
        "created_at": _now_iso(),
        "status": PASS_STATUS if not errors else BLOCKED_STATUS,
        "source_root": str(source_root),
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "memory_base_url": memory_base_url.rstrip("/"),
        "service_name": service_name,
        "pre_systemctl": pre_systemctl,
        "pre_health": pre_health,
        "restart_result": restart_result,
        "wait_result": wait_result,
        "post_systemctl": post_systemctl,
        "post_health": wait_result.get("final_health"),
        "pre_main_pid": pre_pid,
        "post_main_pid": post_pid,
        "pid_changed": pid_changed,
        "delayed_recall_command": delayed_cmd,
        "delayed_recall_result": delayed_result,
        "delayed_recall_receipt": str(delayed_receipt_path),
        "delayed_recall_receipt_sha256": _file_sha256(delayed_receipt_path) if delayed_receipt_path.exists() else None,
        "delayed_recall_status": delayed_receipt.get("status"),
        "delayed_recall_counts": delayed_counts,
        "delayed_recall_artifact_sha256": delayed_receipt.get("artifact_sha256"),
        "errors": errors,
        "mocked": False,
        "live": True,
        "fixture_backed": False,
        "memory_service_restart_attempts": 1,
        "memory_write_attempts": int(delayed_receipt.get("memory_write_attempts", 0) or 0),
        "canonical_memory_write_attempts": int(delayed_receipt.get("canonical_memory_write_attempts", 0) or 0),
        "identity_write_attempts": int(delayed_receipt.get("identity_write_attempts", 0) or 0),
        "source_memory_write_attempts": int(delayed_receipt.get("source_memory_write_attempts", 0) or 0),
        "tau_call_attempts": int(delayed_receipt.get("tau_call_attempts", 0) or 0),
        "provider_call_attempts": int(delayed_receipt.get("provider_call_attempts", 0) or 0),
        "human_content_judgment_required": False,
        "llm_judge_used": False,
        "processing_time_s": round(time.monotonic() - started, 6),
        "claims": {
            "proves": [
                f"the user service {service_name} restarted and changed MainPID before post-restart recall",
                "after Memory service restart, a fresh no-write delayed-recall process exact-reread persisted PCTOM-R revision records and semantic mirrors",
                "after Memory service restart, live Memory /recall returned condition-scoped PCTOM-R revision context for M/R/D/CD",
                "the post-restart delayed-recall proof used no Memory write, canonical write, identity write, source-memory write, Tau call, provider call, LLM judge, or human content judgment",
            ]
            if not errors
            else [
                "the Memory service restart delayed-recall checker failed closed before accepting restart-retention evidence",
            ],
            "does_not_prove": [
                "long-duration wall-clock retention beyond this restart interval",
                "new live Tau execution",
                "paid provider execution",
                "video, audio, or semantic dream quality",
                "complete live Phase 01-16 runtime execution",
                "non-Memory external service fault injection",
            ],
        },
    }
    _write_json(receipt_out, receipt)
    receipt["receipt_sha256"] = _file_sha256(receipt_out)
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, default=None)
    parser.add_argument("--memory-base-url", default="http://127.0.0.1:8601")
    parser.add_argument("--service-name", default="embry-memory")
    parser.add_argument("--wait-timeout-s", type=float, default=60.0)
    parser.add_argument("--wait-sleep-s", type=float, default=1.0)
    parser.add_argument("--recall-attempts", type=int, default=3)
    parser.add_argument("--recall-sleep-s", type=float, default=1.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt_out = args.receipt_out or (args.output_root / "live_memory_restart_delayed_recall_receipt.v1.json")
    receipt = run(
        source_root=args.source_root,
        output_root=args.output_root,
        receipt_out=receipt_out,
        memory_base_url=args.memory_base_url,
        service_name=args.service_name,
        wait_timeout_s=args.wait_timeout_s,
        wait_sleep_s=args.wait_sleep_s,
        recall_attempts=args.recall_attempts,
        recall_sleep_s=args.recall_sleep_s,
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
