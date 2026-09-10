#!/usr/bin/env python3
"""Vague status reports must be steered toward concrete operational anchors."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CHECKER = ROOT / "extensions/pi/lazy-report-shame-shame-shame/status-json-check.mjs"
INDEX = ROOT / "extensions/pi/lazy-report-shame-shame-shame/index.ts"


def fenced(obj: dict) -> str:
    return "```json\n" + json.dumps(obj) + "\n```\n"


def call(obj: dict) -> dict:
    run = subprocess.run(
        ["node", str(CHECKER)],
        input=fenced(obj),
        text=True,
        capture_output=True,
        timeout=20,
        env={**os.environ, "LRSSS_FORCE_STATUS": "1"},
    )
    out = json.loads(run.stdout)
    out["exit_code"] = run.returncode
    return out


def main() -> None:
    vague = {
        "schema": "pi.agent_status.v1",
        "goal": "vague status regression",
        "state": "needs_human",
        "changed": ["no change: reproduced vague status"],
        "needs_human": {"action": "inspect external dashboard", "reason": "dashboard access is manual"},
    }
    # Existing state-specific fields are operational anchors, so accepted data-first reports stay accepted.
    accepted = call(vague)
    assert accepted["decision"] == "pass", accepted

    no_anchor = {
        "schema": "pi.agent_status.v1",
        "goal": "vague status regression",
        "state": "continuing",
        "changed": ["no change: fixture"],
        "not_done": [{"item": "finish proof", "next_command": "skills/shame/run.sh preflight /tmp/candidate.md"}],
    }
    continuing = call(no_anchor)
    assert continuing["decision"] == "pass", continuing

    with tempfile.TemporaryDirectory(prefix="shame-vague-status-") as raw:
        work = Path(raw)
        proof = work / "proof.txt"
        proof.write_text("concrete proof anchor\n", encoding="utf-8")
        rich = {
            "schema": "pi.agent_status.v1",
            "goal": "vague status regression",
            "state": "done",
            "changed": ["extensions/pi/lazy-report-shame-shame-shame/index.ts"],
            "run_dir": str(work),
            "artifacts": [str(work / "artifact.json")],
            "receipts": [str(work / "receipt.json")],
            "nodes": [{"id": "status-check", "status": "PASS", "receipt": str(work / "receipt.json")}],
            "verified": [{"command": f"read {proof}", "result": "concrete proof anchor"}],
            "proof": [str(proof)],
        }
        rich_ok = call(rich)
        assert rich_ok["decision"] == "pass", rich_ok
        rendered = rich_ok["features"]["status"]
        assert rendered["run_dir"] == str(work)
        assert rendered["artifacts"] == [str(work / "artifact.json")]
        assert rendered["receipts"] == [str(work / "receipt.json")]
        assert rendered["nodes"][0]["status"] == "PASS"

    index_text = INDEX.read_text(encoding="utf-8")
    assert "schema: \"lazy_report_shame.retry_request.v1\"" in index_text
    assert "schema: \"lazy_report_shame.follow_up.v1\"" in index_text
    assert "suggested_status: suggestedRetryStatus(candidate, check)" in index_text
    assert "Copy packet.suggested_status" in index_text
    notice = index_text[index_text.index("function rejectionNotice"):index_text.index("function retryEvidenceSnapshot")]
    assert "diagnostics_sha256" in notice
    assert "validation_result" not in notice
    assert "Run dir:" in index_text and "Node:" in index_text and "Missing artifact:" in index_text

    print(json.dumps({
        "schema": "lazy_report_shame.vague_status_eval.v1",
        "status": "PASS",
        "checked": [
            "schema-passing needs_human and continuing reports remain data-first accepted",
            "done status carries run_dir, artifact, receipt, and node fields through the checker",
            "visible renderer knows run dir, receipts, artifacts, node status, blocked, and missing artifact lines",
            "visible rejection notice is compact and hashes raw diagnostics",
            "retry_request includes a copyable continuing suggested_status to avoid blind schema repair guesses",
            "retry_request and follow_up typed packet schemas remain present",
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
