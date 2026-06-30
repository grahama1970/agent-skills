#!/usr/bin/env python3
"""Module support for the monitor-sparta skill."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping


CLOSING_WORKER_STATUSES = {"DONE"}
CLOSING_SUPERVISOR_STATUSES = {"WORKER_DONE"}
NON_CLOSING_STATUSES = {
    "NO_CLAIMABLE_ISSUE",
    "NO_READY_ISSUE",
    "OPERATOR_REQUIRED",
    "READY_RETRY",
    "REVIEW_REQUIRED",
    "DRY_RUN_READY",
    "DRY_RUN_DONE",
    "BLOCKED_WAITING_ON_PROMPT_HEALTH",
}


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def nested_mapping(payload: Mapping[str, Any], *keys: str) -> dict[str, Any]:
    current: Any = payload
    for key in keys:
        if not isinstance(current, Mapping):
            return {}
        current = current.get(key)
    return dict(current) if isinstance(current, Mapping) else {}


def validate_tau_handoff_summary(summary: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if not summary:
        return ["tau_handoff_missing"]
    if not bool(summary.get("ok")):
        errors.append("tau_handoff_not_ok")
    handoff_path = str(summary.get("handoff_path") or "")
    validation_path = str(summary.get("validation_path") or "")
    if not handoff_path:
        errors.append("tau_handoff_path_missing")
    if not validation_path:
        errors.append("tau_validation_path_missing")
    validation = summary.get("validation")
    if isinstance(validation, Mapping):
        if not bool(validation.get("ok")):
            errors.append("tau_validation_not_ok")
        validation_errors = validation.get("errors")
        if isinstance(validation_errors, list) and validation_errors:
            errors.append("tau_validation_errors_present")
    return errors


def worker_tau_summary(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return nested_mapping(receipt, "tau_handoff")


def supervisor_tau_summary(receipt: Mapping[str, Any]) -> dict[str, Any]:
    worker = nested_mapping(receipt, "dispatch", "worker_receipt")
    if not worker:
        return {}
    return {
        "ok": worker.get("tau_handoff_ok"),
        "handoff_path": worker.get("tau_handoff_path"),
        "validation_path": worker.get("tau_validation_path"),
        "validation": nested_mapping(worker, "tau_handoff", "validation"),
    }


def gate_worker_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    terminal_status = str(receipt.get("terminal_status") or "")
    closing = terminal_status in CLOSING_WORKER_STATUSES
    tau_errors = validate_tau_handoff_summary(worker_tau_summary(receipt)) if closing else []
    return {
        "receipt_kind": "worker",
        "terminal_status": terminal_status,
        "closing_claim": closing,
        "ok": not tau_errors,
        "errors": tau_errors,
    }


def gate_supervisor_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    terminal_status = str(receipt.get("terminal_status") or "")
    closing = terminal_status in CLOSING_SUPERVISOR_STATUSES
    errors: list[str] = []
    if closing:
        command_result = nested_mapping(receipt, "dispatch", "command_result")
        worker = nested_mapping(receipt, "dispatch", "worker_receipt")
        selected = nested_mapping(receipt, "selected_issue")
        if not bool(command_result.get("ok")):
            errors.append("worker_command_not_ok")
        if not bool(worker.get("worker_receipt_found")):
            errors.append("worker_receipt_missing")
        if str(worker.get("worker_terminal_status") or "") != "DONE":
            errors.append("worker_terminal_status_not_done")
        if not selected.get("issue_id"):
            errors.append("selected_issue_id_missing")
        errors.extend(validate_tau_handoff_summary(supervisor_tau_summary(receipt)))
    return {
        "receipt_kind": "supervisor_tick",
        "terminal_status": terminal_status,
        "closing_claim": closing,
        "ok": not errors,
        "errors": errors,
    }


def gate_receipt(receipt: Mapping[str, Any], *, require_closure: bool = False) -> dict[str, Any]:
    schema = str(receipt.get("schema") or "")
    if schema == "monitor_sparta.supervisor_tick.receipt.v1":
        result = gate_supervisor_receipt(receipt)
    elif schema.endswith(".issue_worker.receipt.v1"):
        result = gate_worker_receipt(receipt)
    else:
        result = {
            "receipt_kind": "unknown",
            "terminal_status": str(receipt.get("terminal_status") or ""),
            "closing_claim": False,
            "ok": False,
            "errors": [f"unsupported_schema:{schema or 'missing'}"],
        }
    if require_closure and not result["closing_claim"]:
        result = dict(result)
        result["ok"] = False
        result["errors"] = [*result["errors"], "closure_required_but_not_claimed"]
    return {
        "schema": "monitor_sparta.receipt_gate.v1",
        "input_schema": schema,
        "require_closure": require_closure,
        **result,
        "mocked": False,
        "live": False,
        "proves": [
            "receipt does not claim monitor-sparta closure without Tau handoff proof",
        ],
        "does_not_prove": [
            "semantic correctness of the underlying SPARTA repair",
            "freshness of external artifacts unless the caller separately checks paths and timestamps",
            "that all monitor-sparta issues are resolved",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate monitor-sparta receipt closure proof.")
    parser.add_argument("receipt", type=Path, help="Worker or supervisor receipt JSON")
    parser.add_argument("--require-closure", action="store_true", help="Fail unless the receipt makes a close/DONE claim")
    parser.add_argument("--json", action="store_true", help="Print JSON gate receipt")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        receipt = load_json(args.receipt)
        result = gate_receipt(receipt, require_closure=bool(args.require_closure))
    except Exception as exc:  # noqa: BLE001 - command-line validation should return a receipt
        result = {
            "schema": "monitor_sparta.receipt_gate.v1",
            "ok": False,
            "errors": [f"gate_error:{type(exc).__name__}:{exc}"],
            "mocked": False,
            "live": False,
        }
    if args.json or not result.get("ok"):
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"PASS: {args.receipt}")
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
