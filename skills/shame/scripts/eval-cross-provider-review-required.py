#!/usr/bin/env python3
"""Guarded Shame terminal reports require a cross-provider review proof."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CHECKER = ROOT / "extensions/pi/lazy-report-shame-shame-shame/status-json-check.mjs"


def fenced(obj: dict) -> str:
    return "```json\n" + json.dumps(obj) + "\n```\n"


def call(obj: dict, author: str = "openai") -> dict:
    run = subprocess.run(
        ["node", str(CHECKER)],
        input=fenced(obj),
        text=True,
        capture_output=True,
        timeout=20,
        env={**os.environ, "LRSSS_FORCE_STATUS": "1", "LRSSS_AUTHOR_PROVIDER": author},
        check=False,
    )
    out = json.loads(run.stdout)
    out["exit_code"] = run.returncode
    return out


def done_status(work: Path, proof: list[str] | None = None) -> dict:
    baseline = work / "baseline-proof.txt"
    baseline.write_text("baseline proof ok\n", encoding="utf-8")
    proofs = [str(baseline), *(proof or [])]
    verified = [{"command": f"read {baseline}", "result": "baseline proof ok"}]
    if proof:
        verified.append({"command": "cross-provider shame review", "result": "PASS"})
    return {
        "schema": "pi.agent_status.v1",
        "goal": "cross provider review regression",
        "answer": "Done only after external review.",
        "plain_answer": "This terminal report is accepted only when a different provider review proof is attached.",
        "state": "done",
        "changed": ["no change: fixture"],
        "verified": verified,
        "proof": proofs,
    }


def status_review_hash(status: dict) -> str:
    payload = {
        "goal": status.get("goal") or None,
        "answer": status.get("answer") or None,
        "plain_answer": status.get("plain_answer") or None,
        "state": status.get("state") or None,
        "changed": status.get("changed") if isinstance(status.get("changed"), list) else [],
    }
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


def write_review(work: Path, status: dict, *, author: str, reviewer: str, model: str = "zai/glm-5.3:high") -> Path:
    metadata = work / f"meta-{reviewer}.json"
    metadata.write_text(json.dumps({"model": model, "exitCode": 0}) + "\n", encoding="utf-8")
    payload = {
        "schema": "lazy_report_shame.cross_provider_review.v1",
        "verdict": "PASS",
        "author_provider": author,
        "reviewer_provider": reviewer,
        "reviewer_model": model,
        "review_metadata_path": str(metadata),
        "reviewed_candidate_hash": status_review_hash(status),
    }
    proof = work / f"review-{reviewer}.json"
    proof.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return proof


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="shame-cross-provider-") as raw:
        work = Path(raw)
        missing = call(done_status(work))
        assert missing["decision"] == "reject" and "cross_provider_review_required" in missing["reason_codes"], missing

        same_status = done_status(work)
        same = write_review(work, same_status, author="openai", reviewer="openai", model="openai-codex/gpt-5.5")
        same_bad = call(done_status(work, [str(same)]), author="openai")
        assert same_bad["decision"] == "reject" and (
            "cross_provider_review_required" in same_bad["reason_codes"]
            or "cross_provider_review_not_cross_provider" in same_bad["reason_codes"]
        ), same_bad

        reviewed_status = done_status(work)
        different = write_review(work, reviewed_status, author="openai", reviewer="zai", model="zai/glm-5.3:high")
        ok = call(done_status(work, [str(different)]), author="openai")
        assert ok["decision"] == "pass", ok
        assert str(different) in ok["features"]["status"]["proof"], ok

    print(json.dumps({
        "schema": "lazy_report_shame.cross_provider_review_required_eval.v1",
        "status": "PASS",
        "checked": [
            "terminal report without cross-provider review proof is rejected",
            "same-provider review proof is rejected",
            "different-provider review proof with subagent metadata is accepted",
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
