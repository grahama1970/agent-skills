#!/usr/bin/env python3
"""Regression: ticket closure receipt can authorize final shame done without retry."""
from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "run.sh"


def run_preflight(markdown: Path) -> tuple[int, dict]:
    run = subprocess.run([str(RUN), "preflight", str(markdown)], text=True, capture_output=True, timeout=20)
    return run.returncode, json.loads(run.stdout)


def write_status(path: Path, proof: Path, command: str, result: str) -> None:
    path.write_text(
        "Done.\n```json\n"
        + json.dumps({
            "schema": "pi.agent_status.v1",
            "state": "done",
            "goal": "close ticket with typed receipt",
            "changed": ["closed ticket with typed closure receipt"],
            "verified": [{"command": command, "result": result}],
            "proof": [str(proof)],
        })
        + "\n```\n"
    )


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp_s:
        tmp = Path(tmp_s)
        proof_file = tmp / "proof.md"
        proof_file.write_text("deterministic proof body")
        closure = tmp / "closure.json"
        closure.write_text(json.dumps({
            "schema": "ticket.closure_receipt.v1",
            "action": "close",
            "issue": "1625",
            "repo": "grahama1970/agent-skills",
            "state": "CLOSED",
            "proof_path": str(proof_file),
            "proof_sha256": hashlib.sha256(proof_file.read_bytes()).hexdigest(),
        }))
        status = tmp / "status.md"
        write_status(status, closure, "close grahama1970/agent-skills#1625", "CLOSED")
        code, result = run_preflight(status)
        assert code == 0 and result["decision"] == "pass", result

        raw_issue = tmp / "raw-issue.json"
        raw_issue.write_text(json.dumps({"url": "https://github.com/grahama1970/agent-skills/issues/1625", "state": "closed"}))
        raw_status = tmp / "raw-status.md"
        write_status(raw_status, raw_issue, "close grahama1970/agent-skills#1625", "CLOSED")
        code, result = run_preflight(raw_status)
        assert code == 1 and "proof_json_schema_missing" in result["reason_codes"], result

    print(json.dumps({
        "schema": "lazy_report_shame.ticket_close_final_eval.v1",
        "status": "PASS",
        "checked": [
            "typed ticket closure receipt authorizes final done status",
            "raw issue JSON does not authorize done status",
            "preflight pass means no shame retry is queued before final answer",
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
