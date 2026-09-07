#!/usr/bin/env python3
"""Regression for done proof binding: text snippets are not execution receipts."""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

VALIDATOR = Path(__file__).with_name("agent_status_schema.py")


def validate(payload: dict) -> dict:
    run = subprocess.run(
        ["python3", str(VALIDATOR), "validate", "-"],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
        timeout=15,
    )
    if not run.stdout.strip():
        raise AssertionError({"exit_code": run.returncode, "stderr": run.stderr})
    result = json.loads(run.stdout.strip().splitlines()[-1])
    result["exit_code"] = run.returncode
    return result


def status(proof: Path, command: str = "task_check unit", result: str = "PASS") -> dict:
    return {
        "schema": "pi.agent_status.v1",
        "goal": "bind done proof to an execution receipt",
        "state": "done",
        "changed": ["no code change: fixture status"],
        "verified": [{"command": command, "result": result}],
        "proof": [str(proof)],
    }


def error_types(result: dict) -> set[str]:
    return {error["type"] for error in result.get("errors", [])}


def assert_rejects(name: str, payload: dict, code: str) -> None:
    result = validate(payload)
    assert result["exit_code"] == 1, (name, result)
    assert code in error_types(result), (name, result)


def assert_accepts(name: str, payload: dict) -> None:
    result = validate(payload)
    assert result["exit_code"] == 0 and result["valid"] is True, (name, result)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="shame-done-receipt-") as raw:
        work = Path(raw)

        unrelated = work / "unrelated.txt"
        unrelated.write_text("task_check unit was NOT RUN; unrelated check: PASS\n")
        assert_rejects("unrelated_text", status(unrelated), "verified_not_backed_by_proof")

        malformed = work / "malformed.json"
        malformed.write_text('{"schema":"agentic_evals.report.v2",')
        assert_rejects("malformed_json", status(malformed), "proof_json_malformed")

        unknown = work / "unknown.json"
        unknown.write_text(json.dumps({"schema": "unknown.receipt.v1", "status": "PASS"}))
        assert_rejects("unknown_schema", status(unknown), "proof_schema_unsupported")

        failed = work / "failed-agentic-eval.json"
        failed.write_text(json.dumps({
            "schema": "agentic_evals.report.v2",
            "readiness": "NOT_READY",
            "outcome_counts": {"PASS": 0, "FAIL": 1, "BLOCKED": 0, "NOT_TESTED": 0},
            "cases": [{"argv": ["python3", "focused-check"], "outcome": "FAIL"}],
        }))
        assert_rejects("failed_receipt", status(failed, "python3 focused-check", "READY"), "agentic_eval_proof_not_ready")

        valid = work / "ready-agentic-eval.json"
        valid.write_text(json.dumps({
            "schema": "agentic_evals.report.v2",
            "readiness": "READY",
            "outcome_counts": {"PASS": 1, "FAIL": 0, "BLOCKED": 0, "NOT_TESTED": 0},
            "cases": [{"argv": ["python3", "focused-check"], "outcome": "PASS"}],
        }))
        assert_accepts("ready_receipt", status(valid, "python3 focused-check", "READY"))

        closure = work / "ticket-closure.json"
        closure.write_text(json.dumps({
            "schema": "ticket.closure_receipt.v1",
            "action": "close",
            "issue": "1614",
            "repo": "grahama1970/agent-skills",
            "reason": "completed",
            "state": "CLOSED",
            "proof_path": str(valid),
            "proof_sha256": "sha256:" + "0" * 64,
            "closed_at": "2026-09-07T00:00:00+00:00",
        }))
        assert_accepts("ticket_closure", status(closure, "close grahama1970/agent-skills#1614", "CLOSED"))

        bad_closure = work / "ticket-open.json"
        bad_closure.write_text(json.dumps({
            "schema": "ticket.closure_receipt.v1",
            "action": "close",
            "issue": "1614",
            "repo": "grahama1970/agent-skills",
            "reason": "completed",
            "state": "OPEN",
            "proof_path": str(valid),
            "proof_sha256": "sha256:" + "0" * 64,
            "closed_at": "2026-09-07T00:00:00+00:00",
        }))
        assert_rejects("ticket_not_closed", status(bad_closure, "close grahama1970/agent-skills#1614", "CLOSED"), "ticket_closure_receipt_not_closed")

        artifact = work / "sum.txt"
        artifact.write_text("sum=42\n")
        assert_accepts("read_artifact", status(artifact, "read sum artifact", "42"))

    print(json.dumps({
        "schema": "lazy_report_shame.done_receipt_binding_eval.v1",
        "status": "PASS",
        "checked": [
            "unrelated text cannot authorize done",
            "malformed JSON proof is rejected",
            "unknown JSON proof schema is rejected",
            "failed agentic eval receipt is rejected",
            "READY agentic eval receipt can authorize a matching verified item",
            "ticket closure receipt can authorize a close readback",
            "non-closed ticket receipt is rejected",
            "read-only artifact evidence remains allowed for artifact readbacks",
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
