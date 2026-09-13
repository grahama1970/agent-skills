#!/usr/bin/env python3
"""Artifact requests must get artifact content, not proof/status/path only."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CHECKER = ROOT / "extensions/pi/lazy-report-shame-shame-shame/status-json-check.mjs"


def fenced(obj: dict) -> str:
    return "```json\n" + json.dumps(obj) + "\n```\n"


def call(body: str, user_text: str) -> dict:
    run = subprocess.run(
        ["node", str(CHECKER)],
        input=body,
        text=True,
        capture_output=True,
        timeout=20,
        env={**os.environ, "LRSSS_FORCE_STATUS": "1", "LRSSS_USER_TEXT": user_text},
    )
    out = json.loads(run.stdout)
    out["exit_code"] = run.returncode
    return out


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="shame-artifact-delivery-") as raw:
        work = Path(raw)
        proof = work / "proof.txt"
        proof.write_text("artifact delivery proof token\n", encoding="utf-8")
        status = {
            "schema": "pi.agent_status.v1",
            "goal": "artifact delivery regression",
            "answer": "Report is ready.",
            "plain_answer": "The report is ready at /tmp/report.md and the proof passed.",
            "state": "done",
            "changed": ["extensions/pi/lazy-report-shame-shame-shame/status-json-check.mjs"],
            "verified": [{"command": f"read {proof}", "result": "artifact delivery proof token"}],
            "proof": [str(proof)],
        }

        bad = call(fenced(status), "Show me the complete report.md.")
        assert bad["decision"] == "reject", bad
        assert "artifact_delivery_missing_content" in bad["reason_codes"], bad

        report = "\n".join([
            "# Battle Report",
            "",
            "## Summary",
            "The requested report content is pasted here before the status block.",
            "",
            "| Section | Finding |",
            "| --- | --- |",
            "| Acceptance contract floor | PASS |",
            "| Beyond-contract exploits | 0 survived |",
            "| Adaptive lineage | recorded |",
            "",
            "## Evidence",
            "This is material report text, not a pointer to a path or a proof summary.",
        ])
        good_status = dict(status)
        good_status["plain_answer"] = "The requested report is pasted above."
        good = call(report + "\n\n" + fenced(good_status), "Show me the complete report.md.")
        assert good["decision"] == "pass", good

        where_status = dict(status)
        where_status["answer"] = "Here is where the report is: /tmp/report.md."
        where_status["plain_answer"] = "Here is where the report is: /tmp/report.md."
        where = call(fenced(where_status), "Where is the report.md?")
        assert where["decision"] == "pass", where

        cannot = {
            "schema": "pi.agent_status.v1",
            "goal": "artifact delivery regression",
            "answer": "Cannot access the report.",
            "plain_answer": "I cannot access report.md from here; upload it or provide the path.",
            "state": "needs_human",
            "changed": ["no change: artifact path unavailable"],
            "needs_human": {"action": "provide the report path", "reason": "the requested artifact path is not available to this session"},
        }
        cannot_result = call(fenced(cannot), "Paste the report.md.")
        assert cannot_result["decision"] == "pass", cannot_result

    print(json.dumps({
        "schema": "lazy_report_shame.artifact_delivery_request_eval.v1",
        "status": "PASS",
        "checked": [
            "show/paste report requests reject proof-status-path-only answers",
            "material report content before the status JSON passes",
            "where-is path requests are not mistaken for paste/show requests",
            "explicit cannot-access answers remain allowed when the artifact is unavailable",
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
