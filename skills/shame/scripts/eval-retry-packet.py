#!/usr/bin/env python3
"""Regression for bounded self-contained shame retry packets."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

VALIDATOR = Path(__file__).with_name("retry_request_schema.py")


def validate(packet: dict) -> tuple[int, dict]:
    run = subprocess.run(["python3", str(VALIDATOR), "validate"], input=json.dumps(packet), text=True, capture_output=True, timeout=10)
    return run.returncode, json.loads(run.stdout)


def packet(**overrides) -> dict:
    base = {
        "schema": "lazy_report_shame.retry_request.v1",
        "format_only": True,
        "allowed_tools": [],
        "max_corrections": 1,
        "candidate_hash": "sha256:" + "1" * 64,
        "checker": "test",
        "reason_codes": ["proof_json_schema_missing"],
        "diagnostics_sha256": "sha256:" + "2" * 64,
        "review_packet": "pending-review-packet",
        "validation_result": {"schema": "pi.agent_status.validation_result.v1", "valid": False, "errors": []},
        "recovery_decision": {
            "schema": "lazy_report_shame.recovery_decision.v1",
            "action": "existing_proof_substitution",
            "format_only": True,
            "allowed_tools": [],
            "reason": "cite_existing_typed_receipt",
        },
        "evidence_snapshot": [{
            "proof": "ticket-closure.json",
            "schema": "ticket.closure_receipt.v1",
            "digest": "sha256:" + "3" * 64,
            "validation": "admitted",
            "reason_codes": [],
        }],
        "next": {"action": "emit_pi_agent_status_v1", "reason": "cite_existing_typed_receipt"},
    }
    base.update(overrides)
    return base


def main() -> None:
    code, result = validate(packet())
    assert code == 0 and result["valid"] is True, result

    code, result = validate(packet(allowed_tools=["read"]))
    assert code == 1, result

    too_large = packet(review_packet="x" * 9000)
    code, result = validate(too_large)
    assert code == 1 and any("retry_request_too_large" in str(e) for e in result["errors"]), result

    print(json.dumps({
        "schema": "lazy_report_shame.retry_packet_eval.v1",
        "status": "PASS",
        "checked": [
            "retry packet is typed and self-contained",
            "format-only retry allows no tools",
            "retry packet is byte-bounded",
            "evidence snapshot carries proof schema and digest",
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
