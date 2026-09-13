#!/usr/bin/env python3
"""Shame accepts only a candidate-bound pi-subagents stop-review receipt."""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from review_receipt_fixture import attach_review

ROOT = Path(__file__).resolve().parents[3]
CHECKER = ROOT / "extensions/pi/lazy-report-shame-shame-shame/status-json-check.mjs"


def fenced(obj: dict) -> str:
    return "```json\n" + json.dumps(obj, indent=2) + "\n```\n"


def check(text: str) -> dict:
    run = subprocess.run(
        ["node", str(CHECKER)], input=text, text=True, capture_output=True,
        env={"PATH": "/usr/bin:/bin", "LRSSS_FORCE_STATUS": "1", "LRSSS_AUTHOR_PROVIDER": "openai"},
        check=False, timeout=20,
    )
    return json.loads(run.stdout)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="shame-pi-subagents-review-") as raw:
        work = Path(raw)
        proof = work / "proof.txt"
        proof.write_text("baseline proof ok\n", encoding="utf-8")
        status = {
            "schema": "pi.agent_status.v1",
            "goal": "pi-subagents stop-review regression",
            "answer": "Accepted only after the reviewer child passes.",
            "plain_answer": "The Pi harness reviewer child must pass before stop.",
            "state": "done",
            "changed": ["no change: fixture"],
            "verified": [{"command": f"read {proof}", "result": "baseline proof ok"}],
            "proof": [str(proof)],
        }
        unreviewed = check(fenced(status))
        assert unreviewed["decision"] == "reject" and "cross_family_review_required" in unreviewed["reason_codes"], unreviewed

        attach_review(work, status)
        reviewed = check(fenced(status))
        assert reviewed["decision"] == "pass", reviewed
        assert reviewed["features"]["cross_family_review"] == {"status": "reviewed", "degraded": False}, reviewed

        receipt = json.loads(Path(status["proof"][-1]).read_text(encoding="utf-8"))
        receipt["generated_by"] = "lazy-report-shame-shame-shame"
        Path(status["proof"][-1]).write_text(json.dumps(receipt), encoding="utf-8")
        legacy = check(fenced(status))
        assert legacy["decision"] == "reject" and "cross_provider_review_not_hook_generated" in legacy["reason_codes"], legacy

    print(json.dumps({
        "schema": "lazy_report_shame.pi_subagents_stop_review_eval.v1",
        "status": "PASS",
        "checked": [
            "unreviewed terminal stop is rejected",
            "candidate-bound pi-subagents reviewer receipt is accepted",
            "legacy Shame-owned reviewer receipt is rejected",
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
