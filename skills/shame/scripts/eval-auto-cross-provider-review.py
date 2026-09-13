#!/usr/bin/env python3
"""Stop-hook reviewer invocation writes a bound cross-provider receipt."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
AUTO = ROOT / "extensions/pi/lazy-report-shame-shame-shame/auto-cross-provider-review.mjs"
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
    with tempfile.TemporaryDirectory(prefix="shame-auto-review-") as raw:
        work = Path(raw)
        baseline = work / "baseline-proof.txt"
        baseline.write_text("baseline proof ok\n", encoding="utf-8")
        status = {
            "schema": "pi.agent_status.v1",
            "goal": "automatic cross-provider reviewer regression",
            "answer": "Done only after hook-owned review.",
            "plain_answer": "The hook must invoke the reviewer and attach its receipt before acceptance.",
            "state": "done",
            "changed": ["no change: fixture"],
            "verified": [{"command": f"read {baseline}", "result": "baseline proof ok"}],
            "proof": [str(baseline)],
        }
        before = call_checker(fenced(status))
        assert before["decision"] == "reject" and "cross_family_review_required" in before["reason_codes"], before

        candidate = "Fixture terminal answer.\n\n" + fenced(status)
        review = subprocess.run(
            ["node", str(AUTO)],
            input=json.dumps({"text": candidate, "status": status, "author_provider": "openai"}),
            text=True,
            capture_output=True,
            timeout=30,
            env={
                **os.environ,
                "LAZY_REPORT_SHAME_REVIEW_DIR": str(work / "reviews"),
                "LAZY_REPORT_SHAME_REVIEWER_MODEL": "zai/glm-5.3:high",
                "LAZY_REPORT_SHAME_REVIEWER_COMMAND": "printf 'VERDICT: PASS\\nCRITIQUE: fixture reviewer confirms proof boundary.\\n'",
            },
            check=False,
        )
        assert review.returncode == 0, review.stderr or review.stdout
        review_payload = json.loads(review.stdout)
        receipt = Path(review_payload["receipt_path"])
        metadata = Path(review_payload["metadata_path"])
        output = Path(review_payload["output_path"])
        assert receipt.is_file() and metadata.is_file() and output.is_file(), review_payload
        receipt_data = json.loads(receipt.read_text(encoding="utf-8"))
        metadata_data = json.loads(metadata.read_text(encoding="utf-8"))
        assert receipt_data["generated_by"] == "lazy-report-shame-shame-shame", receipt_data
        assert metadata_data["generated_by"] == "lazy-report-shame-shame-shame", metadata_data
        assert receipt_data["review_metadata_path"] == str(metadata), receipt_data
        assert receipt_data["review_output_path"] == str(output), receipt_data

        status["proof"].append(str(receipt))
        status["verified"].append({"command": "cross-provider shame review", "result": "PASS"})
        after = call_checker(fenced(status))
        assert after["decision"] == "pass", after
        assert after["features"]["cross_family_review"] == {"status": "reviewed", "degraded": False}, after

        zai_review = subprocess.run(
            ["node", str(AUTO)],
            input=json.dumps({"text": candidate, "status": status, "author_provider": "zai"}),
            text=True,
            capture_output=True,
            timeout=30,
            env={
                **os.environ,
                "LAZY_REPORT_SHAME_REVIEW_DIR": str(work / "zai-author-reviews"),
                "LAZY_REPORT_SHAME_REVIEWER_COMMAND": "printf 'VERDICT: PASS\\nCRITIQUE: fixture reviewer confirms proof boundary.\\n'",
            },
            check=False,
        )
        assert zai_review.returncode == 0, zai_review.stderr or zai_review.stdout
        zai_payload = json.loads(zai_review.stdout)
        zai_receipt = json.loads(Path(zai_payload["receipt_path"]).read_text(encoding="utf-8"))
        assert zai_receipt["author_provider"] == "zai" and zai_receipt["reviewer_provider"] == "openai", zai_receipt

    print(json.dumps({
        "schema": "lazy_report_shame.auto_cross_provider_review_eval.v1",
        "status": "PASS",
        "checked": [
            "unreviewed guarded stop is rejected",
            "auto-cross-provider-review invokes configured reviewer command",
            "hook-owned receipt, metadata, and reviewer output are written",
            "checker accepts the same stop after the generated receipt is attached",
            "zai authors are assigned an OpenAI-family reviewer by default",
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
