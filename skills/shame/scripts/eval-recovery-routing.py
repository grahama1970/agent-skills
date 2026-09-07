#!/usr/bin/env python3
"""Regression for typed shame recovery routing."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROUTER = Path(__file__).with_name("recovery_decision_schema.py")


def decide(reason_codes: list[str], **extra) -> dict:
    payload = {"schema": "lazy_report_shame.recovery_input.v1", "reason_codes": reason_codes, **extra}
    run = subprocess.run(["python3", str(ROUTER), "decide"], input=json.dumps(payload), text=True, capture_output=True, timeout=10)
    assert run.returncode == 0, run.stderr + run.stdout
    return json.loads(run.stdout)


def expect(name: str, reason_codes: list[str], action: str, format_only: bool, **extra) -> None:
    result = decide(reason_codes, **extra)
    assert result["schema"] == "lazy_report_shame.recovery_decision.v1", (name, result)
    assert result["action"] == action, (name, result)
    assert result["format_only"] is format_only, (name, result)
    if format_only:
        assert result["allowed_tools"] == [], (name, result)


def main() -> None:
    expect("formatting", ["missing_agent_status_json"], "output_only_repair", True)
    expect("existing-proof", ["proof_json_schema_missing"], "existing_proof_substitution", True)
    expect("missing-evidence", ["proof_path_missing"], "continue_execution", False, next_command="materialize proof")
    expect("validator-failure", ["validator_crashed"], "validator_failure", False)
    expect("unresolved-work", ["task_acceptance_checks_incomplete"], "continue_execution", False, next_command="task_check")
    expect("accepted-task", ["task_already_accepted"], "output_only_repair", True, task_phase="accepted")
    expect("retried", ["missing_agent_status_json"], "stop_retry", True, retried=True)
    print(json.dumps({
        "schema": "lazy_report_shame.recovery_routing_eval.v1",
        "status": "PASS",
        "checked": [
            "formatting uses output-only repair",
            "existing proof substitution stays output-only",
            "missing evidence continues execution instead of format repair",
            "validator failure is explicit infrastructure recovery",
            "unresolved work continues execution",
            "accepted task does not reopen execution",
            "retry exhaustion stops retry",
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
