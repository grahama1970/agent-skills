#!/usr/bin/env python3
"""Cross-provider review is hook-owned, never an agent repair task."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CHECKER = ROOT / "extensions/pi/lazy-report-shame-shame-shame/status-json-check.mjs"
RUN = ROOT / "skills/shame/run.sh"
INDEX = ROOT / "extensions/pi/lazy-report-shame-shame-shame/index.ts"

FORBIDDEN = (
    "obtain_cross_family_review_then_resubmit",
    "attach_valid_cross_family_review_receipt",
)


def fenced(obj: dict) -> str:
    return "```json\n" + json.dumps(obj, indent=2) + "\n```\n"


def call_checker(text: str, *, preflight: bool = False) -> dict:
    cmd = [str(RUN), "preflight", "-"] if preflight else ["node", str(CHECKER)]
    run = subprocess.run(
        cmd,
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
    with tempfile.TemporaryDirectory(prefix="shame-harness-owned-review-") as raw:
        work = Path(raw)
        proof = work / "proof.txt"
        proof.write_text("base proof ok\n", encoding="utf-8")
        status = {
            "schema": "pi.agent_status.v1",
            "goal": "harness-owned cross-provider review regression",
            "answer": "Done only after hook review.",
            "plain_answer": "The final answer is ready for the hook-owned reviewer to check.",
            "state": "done",
            "changed": ["no change: fixture"],
            "verified": [{"command": f"read {proof}", "result": "base proof ok"}],
            "proof": [str(proof)],
        }
        text = fenced(status)
        missing = call_checker(text)
        assert missing["decision"] == "reject" and missing["reason_codes"] == ["cross_family_review_required"], missing
        steering = missing["features"]["validation_result"]["steering"][0]
        assert steering["action"] == "await_harness_cross_provider_review", steering
        assert steering["owner"] == "pi_harness" and steering["agent_actionable"] is False, steering
        assert all(token not in json.dumps(missing) for token in FORBIDDEN), missing

        preflight = call_checker(text, preflight=True)
        assert preflight["decision"] == "pass", preflight
        assert preflight["features"]["cross_family_review"] == {"status": "pending_harness_review", "degraded": False}, preflight

    index_text = INDEX.read_text(encoding="utf-8")
    assert all(token not in index_text for token in FORBIDDEN), "agent-visible impossible repair action survived in index.ts"
    assert "harnessReviewUnavailableNotice" in index_text, "hook review failure must stop at harness notice"

    print(json.dumps({
        "schema": "lazy_report_shame.cross_provider_review_harness_owned_eval.v1",
        "status": "PASS",
        "checked": [
            "missing cross-provider review routes to await_harness_cross_provider_review",
            "missing review is marked owner=pi_harness and agent_actionable=false",
            "forbidden agent repair actions are absent",
            "run.sh preflight passes valid status while marking review pending for the hook",
            "index.ts has a harness-owned unavailable-review stop path",
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
