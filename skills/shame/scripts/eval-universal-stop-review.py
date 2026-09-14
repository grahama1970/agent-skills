#!/usr/bin/env python3
"""Universal stop-review gate regression.

This is intentionally small: the extension owns runtime stop interception, while
status-json-check owns the fail-closed receipt validation. The eval proves the
extension defaults terminal stops into the guarded path and the checker rejects
both missing status and unreviewed status on that path.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
INDEX = ROOT / "extensions/pi/lazy-report-shame-shame-shame/index.ts"
CHECKER = ROOT / "extensions/pi/lazy-report-shame-shame-shame/status-json-check.mjs"


def fenced(obj: dict) -> str:
    return "```json\n" + json.dumps(obj, indent=2) + "\n```\n"


def call_checker(text: str) -> dict:
    run = subprocess.run(
        ["node", str(CHECKER)],
        input=text,
        text=True,
        capture_output=True,
        timeout=20,
        env={**os.environ, "LRSSS_FORCE_STATUS": "1", "LRSSS_AUTHOR_PROVIDER": "openai"},
        check=False,
    )
    payload = json.loads(run.stdout)
    payload["exit_code"] = run.returncode
    return payload


def main() -> None:
    source = INDEX.read_text(encoding="utf-8")
    assert 'const UNIVERSAL_STOP_REVIEW = !flagDisabled(process.env.LAZY_REPORT_SHAME_UNIVERSAL_STOP_REVIEW ?? "1");' in source
    assert 'const forceStatus = UNIVERSAL_STOP_REVIEW || Boolean(budget.current)' in source
    assert 'bindings?.["pi-subagents.stop-review/1"]?.reviewer === true' in source
    assert 'auto-cross-provider-review.mjs' not in source

    missing = call_checker("Paris.\n")
    assert missing["decision"] == "reject", missing
    assert "missing_agent_status_json" in missing["reason_codes"], missing

    with tempfile.TemporaryDirectory(prefix="shame-universal-stop-") as raw:
        proof = Path(raw) / "proof.txt"
        proof.write_text("trivial answer proof ok\n", encoding="utf-8")
        status = {
            "schema": "pi.agent_status.v1",
            "goal": "answer a trivial question under universal stop review",
            "plain_answer": "Paris is the capital of France.",
            "state": "done",
            "changed": ["no change: trivial answer"],
            "verified": [{"command": f"read {proof}", "result": "trivial answer proof ok"}],
            "proof": [str(proof)],
        }
        unreviewed = call_checker("Paris.\n\n" + fenced(status))
        assert unreviewed["decision"] == "reject", unreviewed
        assert "cross_family_review_required" in unreviewed["reason_codes"], unreviewed
        review = unreviewed["features"].get("cross_family_review", {})
        assert review.get("owner") == "pi_harness", unreviewed

    print(json.dumps({
        "schema": "lazy_report_shame.universal_stop_review_eval.v1",
        "status": "PASS",
        "checked": [
            "extension defaults universal stop review on",
            "terminal stops are forced into the status contract",
            "unreviewed terminal status is rejected as pi_harness-owned cross-family review work",
            "the designated pi-subagents stop reviewer bypasses recursive Shame terminal rewriting",
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
