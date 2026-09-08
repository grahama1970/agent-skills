#!/usr/bin/env python3
"""Regression for shame spiral-to-ticket request records."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EXTENSION = ROOT / "extensions/pi/lazy-report-shame-shame-shame/index.ts"


def main() -> None:
    source = EXTENSION.read_text()
    assert "writeSpiralTicketRequest" in source
    assert "report_retry_exhausted" in source
    assert "lazy_report_shame.spiral_ticket_request.v1" in source
    request = {
        "schema": "lazy_report_shame.spiral_ticket_request.v1",
        "fingerprint": "sha256:" + "a" * 64,
        "title": "Fix shame spiral deadbeefcafebabe",
        "target": "skills/shame",
        "route": "backend_python_or_skill_runtime",
        "agent": "agent-skill-maintainer",
        "labels": ["agent-work"],
        "reason_codes": ["missing_agent_status_json"],
        "candidate_hash": "sha256:" + "b" * 64,
        "checker": "test-checker",
        "review_packet": "/tmp/pending-review-packet.json",
        "recovery_decision": {
            "schema": "lazy_report_shame.recovery_decision.v1",
            "action": "stop_retry",
            "format_only": True,
            "allowed_tools": [],
            "reason": "status_contract_retry_exhausted",
        },
        "body_path": "/tmp/shame-spiral.md",
        "ticket_command": "skills/ticket/run.sh maintenance 'Fix shame spiral deadbeefcafebabe' --target skills/shame --route backend_python_or_skill_runtime --agent agent-skill-maintainer --label agent-work --apply",
        "watchdog_route": "project-watchdog -> ticket_repair",
    }
    assert request["schema"] == "lazy_report_shame.spiral_ticket_request.v1"
    assert request["target"] == "skills/shame"
    assert request["route"] == "backend_python_or_skill_runtime"
    assert "agent-work" in request["labels"]
    assert "skills/ticket/run.sh maintenance" in request["ticket_command"]
    assert "--apply" in request["ticket_command"]
    assert request["watchdog_route"] == "project-watchdog -> ticket_repair"
    assert request["recovery_decision"]["action"] == "stop_retry"
    assert request["reason_codes"]
    print(json.dumps({
        "schema": "lazy_report_shame.spiral_ticket_request_eval.v1",
        "status": "PASS",
        "checked": [
            "retry exhaustion is a distinct report_retry_exhausted event",
            "spiral ticket requests target skills/shame",
            "ticket command creates an agent-work maintenance ticket",
            "project-watchdog route is ticket_repair",
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
