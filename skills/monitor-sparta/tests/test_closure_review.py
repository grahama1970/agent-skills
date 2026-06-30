from __future__ import annotations

import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import closure_bundle_gate
import closure_review


def write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def closing_receipt(path: Path) -> Path:
    return write_json(
        path,
        {
            "schema": "ops_arango.issue_worker.receipt.v1",
            "terminal_status": "DONE",
            "tau_handoff": {
                "ok": True,
                "handoff_path": "/tmp/handoff.json",
                "validation_path": "/tmp/validation.json",
                "validation": {"ok": True, "errors": []},
            },
        },
    )


def nonclosing_receipt(path: Path) -> Path:
    return write_json(
        path,
        {
            "schema": "ops_arango.issue_worker.receipt.v1",
            "terminal_status": "OPERATOR_REQUIRED",
        },
    )


def test_verify_and_review_create_bundle_receipts(tmp_path: Path) -> None:
    closure_path = closing_receipt(tmp_path / "closure.json")
    verifier_path = tmp_path / "verifier.json"
    reviewer_path = tmp_path / "reviewer.json"

    verifier = closure_review.verifier_receipt(
        closure_path,
        artifact_dir=tmp_path,
        verifier_id="test-verifier",
    )
    write_json(verifier_path, verifier)
    reviewer = closure_review.reviewer_receipt(
        closure_path,
        verifier_path,
        reviewer_id="test-reviewer",
    )
    write_json(reviewer_path, reviewer)
    bundle = closure_bundle_gate.gate_bundle(
        closure_receipt_path=closure_path,
        verifier_receipt_path=verifier_path,
        reviewer_receipt_path=reviewer_path,
    )

    assert verifier["decision"] == "pass"
    assert reviewer["decision"] == "pass"
    assert bundle["ok"] is True


def test_verify_records_blocking_findings_for_nonclosing_receipt(tmp_path: Path) -> None:
    closure_path = nonclosing_receipt(tmp_path / "closure.json")

    verifier = closure_review.verifier_receipt(
        closure_path,
        artifact_dir=tmp_path,
        verifier_id="test-verifier",
    )

    assert verifier["decision"] == "fail"
    assert "receipt_gate:closure_required_but_not_claimed" in verifier["blocking_findings"]


def test_review_fails_when_verifier_failed(tmp_path: Path) -> None:
    closure_path = nonclosing_receipt(tmp_path / "closure.json")
    verifier = closure_review.verifier_receipt(
        closure_path,
        artifact_dir=tmp_path,
        verifier_id="test-verifier",
    )
    verifier_path = write_json(tmp_path / "verifier.json", verifier)

    reviewer = closure_review.reviewer_receipt(
        closure_path,
        verifier_path,
        reviewer_id="test-reviewer",
    )

    assert reviewer["decision"] == "fail"
    assert any(item.startswith("verifier:verifier_decision_not_pass") for item in reviewer["blocking_findings"])
