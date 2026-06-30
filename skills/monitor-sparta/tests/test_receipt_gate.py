from __future__ import annotations

import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import receipt_gate


def valid_tau() -> dict:
    return {
        "ok": True,
        "handoff_path": "/tmp/handoff.json",
        "validation_path": "/tmp/validation.json",
        "validation": {"ok": True, "errors": []},
    }


def test_worker_done_requires_valid_tau_handoff() -> None:
    receipt = {
        "schema": "ops_arango.issue_worker.receipt.v1",
        "terminal_status": "DONE",
        "tau_handoff": valid_tau(),
    }

    result = receipt_gate.gate_receipt(receipt, require_closure=True)

    assert result["ok"] is True
    assert result["closing_claim"] is True
    assert result["receipt_kind"] == "worker"


def test_worker_done_rejects_missing_tau_handoff() -> None:
    receipt = {
        "schema": "ops_arango.issue_worker.receipt.v1",
        "terminal_status": "DONE",
    }

    result = receipt_gate.gate_receipt(receipt, require_closure=True)

    assert result["ok"] is False
    assert "tau_handoff_missing" in result["errors"]


def test_non_closing_worker_receipt_passes_unless_closure_required() -> None:
    receipt = {
        "schema": "ux_coverage_auditor.issue_worker.receipt.v1",
        "terminal_status": "REVIEW_REQUIRED",
    }

    result = receipt_gate.gate_receipt(receipt)
    required = receipt_gate.gate_receipt(receipt, require_closure=True)

    assert result["ok"] is True
    assert result["closing_claim"] is False
    assert required["ok"] is False
    assert "closure_required_but_not_claimed" in required["errors"]


def test_supervisor_worker_done_requires_worker_receipt_and_tau_handoff() -> None:
    receipt = {
        "schema": "monitor_sparta.supervisor_tick.receipt.v1",
        "terminal_status": "WORKER_DONE",
        "selected_issue": {"issue_id": "issue-1"},
        "dispatch": {
            "command_result": {"ok": True},
            "worker_receipt": {
                "worker_receipt_found": True,
                "worker_terminal_status": "DONE",
                "tau_handoff_ok": True,
                "tau_handoff_path": "/tmp/handoff.json",
                "tau_validation_path": "/tmp/validation.json",
                "tau_handoff": {"validation": {"ok": True, "errors": []}},
            },
        },
    }

    result = receipt_gate.gate_receipt(receipt, require_closure=True)

    assert result["ok"] is True
    assert result["receipt_kind"] == "supervisor_tick"


def test_supervisor_worker_done_rejects_missing_tau_handoff() -> None:
    receipt = {
        "schema": "monitor_sparta.supervisor_tick.receipt.v1",
        "terminal_status": "WORKER_DONE",
        "selected_issue": {"issue_id": "issue-1"},
        "dispatch": {
            "command_result": {"ok": True},
            "worker_receipt": {
                "worker_receipt_found": True,
                "worker_terminal_status": "DONE",
                "tau_handoff_ok": False,
            },
        },
    }

    result = receipt_gate.gate_receipt(receipt, require_closure=True)

    assert result["ok"] is False
    assert "tau_handoff_not_ok" in result["errors"]
    assert "tau_handoff_path_missing" in result["errors"]
