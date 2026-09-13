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
    output = work / f"output-{reviewer}.md"
    output.write_text("VERDICT: PASS\nCRITIQUE: fixture reviewer accepted the proof boundary.\n", encoding="utf-8")
    metadata = work / f"meta-{reviewer}.json"
    metadata.write_text(json.dumps({
        "schema": "lazy_report_shame.cross_provider_review_metadata.v1",
        "generated_by": "lazy-report-shame-shame-shame",
        "model": model,
        "exitCode": 0,
        "output_path": str(output),
    }) + "\n", encoding="utf-8")
    payload = {
        "schema": "lazy_report_shame.cross_provider_review.v1",
        "generated_by": "lazy-report-shame-shame-shame",
        "verdict": "PASS",
        "author_provider": author,
        "reviewer_provider": reviewer,
        "reviewer_model": model,
        "review_metadata_path": str(metadata),
        "review_output_path": str(output),
        "reviewed_candidate_hash": status_review_hash(status),
    }
    proof = work / f"review-{reviewer}.json"
    proof.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return proof


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="shame-cross-provider-") as raw:
        work = Path(raw)
        missing = call(done_status(work))
        assert missing["decision"] == "reject" and "cross_family_review_required" in missing["reason_codes"], missing
        assert missing["features"]["cross_family_review"]["status"] == "unreviewed", missing

        same_status = done_status(work)
        same = write_review(work, same_status, author="openai", reviewer="openai", model="openai-codex/gpt-5.5")
        same_bad = call(done_status(work, [str(same)]), author="openai")
        assert same_bad["decision"] == "reject" and (
            "cross_family_review_required" in same_bad["reason_codes"]
            or "cross_provider_review_not_cross_provider" in same_bad["reason_codes"]
        ), same_bad
        # The pydantic layer catches literal same-provider strings; the checker
        # family gate catches alias families (next case).

        # A receipt whose reviewer_model is a same-family alias is still self-review.
        alias_status = done_status(work)
        alias = write_review(work, alias_status, author="openai", reviewer="openai-codex", model="openai/gpt-5.6")
        alias_bad = call(done_status(work, [str(alias)]), author="openai")
        assert alias_bad["decision"] == "reject" and "same-family" in alias_bad["features"]["cross_family_review"]["reason"], alias_bad

        # Pi-subagents receipt metadata is mandatory: missing file / nonzero exit / model mismatch all fail.
        reviewed_status = done_status(work)
        different = write_review(work, reviewed_status, author="openai", reviewer="zai", model="zai/glm-5.3:high")
        ok = call(done_status(work, [str(different)]), author="openai")
        assert ok["decision"] == "pass", ok
        assert ok["features"]["cross_family_review"] == {"status": "reviewed", "degraded": False}, ok
        assert str(different) in ok["features"]["status"]["proof"], ok

        broken_meta = work / "review-zai.json"
        payload = json.loads(broken_meta.read_text(encoding="utf-8"))
        payload["review_metadata_path"] = str(work / "does-not-exist.json")
        broken_meta.write_text(json.dumps(payload), encoding="utf-8")
        no_meta = call(done_status(work, [str(broken_meta)]), author="openai")
        assert no_meta["decision"] == "reject" and "cross_provider_review_metadata_not_found" in no_meta["reason_codes"], no_meta

        nonzero = write_review(work, reviewed_status, author="openai", reviewer="zai")
        nz_payload = json.loads(nonzero.read_text(encoding="utf-8"))
        nz_meta = work / "meta-nonzero.json"
        nz_meta.write_text(json.dumps({
            "schema": "lazy_report_shame.cross_provider_review_metadata.v1",
            "generated_by": "lazy-report-shame-shame-shame",
            "model": nz_payload["reviewer_model"],
            "exitCode": 3,
            "output_path": nz_payload["review_output_path"],
        }), encoding="utf-8")
        nz_payload["review_metadata_path"] = str(nz_meta)
        nonzero.write_text(json.dumps(nz_payload), encoding="utf-8")
        nz_bad = call(done_status(work, [str(nonzero)]), author="openai")
        assert nz_bad["decision"] == "reject" and "cross_provider_review_failed_run" in nz_bad["reason_codes"], nz_bad

        # Reviewer rejection (verdict REJECT) restarts with the critique as steering.
        def rejected_status(work: Path, proof: list[str]) -> dict:
            status = done_status(work, proof)
            status["verified"][-1] = {"command": "cross-provider shame review", "result": "REJECT"}
            return status

        reject_status = rejected_status(work, [])
        fail_review = write_review(work, reject_status, author="openai", reviewer="zai", model="zai/glm-5.3:high")
        fail_payload = json.loads(fail_review.read_text(encoding="utf-8"))
        fail_payload["verdict"] = "REJECT"
        fail_payload["critique"] = "The claim of READY evals is unsupported; no receipts exist for the rerun."
        fail_review.write_text(json.dumps(fail_payload), encoding="utf-8")
        final_reject_status = rejected_status(work, [str(fail_review)])
        rejected = call(final_reject_status, author="openai")
        assert rejected["decision"] == "reject" and rejected["reason_codes"] == ["cross_family_review_rejected"], rejected
        steering = rejected["features"]["validation_result"]["steering"][0]
        assert steering["action"] == "restart_with_reviewer_critique" and steering["restart"] is True, steering
        assert "unsupported" in steering["reviewer_critique"], steering

        # Honest no-work needs_human stop passes degraded/unreviewed, with no
        # fabricated scratch-file changed[] filler.
        needs_human = {
            "schema": "pi.agent_status.v1",
            "goal": "cross provider review regression",
            "answer": "No work was possible; the cross-family reviewer is unavailable.",
            "plain_answer": "No work was possible this stop; the cross-family reviewer is unavailable.",
            "state": "needs_human",
            "changed": ["no change: cross-family reviewer unavailable"],
            "needs_human": {"action": "provide or enable a cross-family reviewer", "reason": "review unavailable"},
        }
        # NO EXCEPTIONS: even the honest needs_human stop is rejected as
        # unreviewed/degraded without a review receipt.
        degraded = call(needs_human)
        assert degraded["decision"] == "reject" and "cross_family_review_required" in degraded["reason_codes"], degraded
        assert degraded["features"]["cross_family_review"] == {
            "status": "unreviewed", "degraded": True,
            "reason": "missing lazy_report_shame.cross_provider_review.v1 proof",
        }, degraded
        assert degraded["features"]["validation_result"]["steering"][0]["unreviewed"] is True, degraded

        # With a valid cross-family receipt, the same honest no-work needs_human
        # passes cleanly, still without fabricated scratch-file changed[] filler.
        needs_human_status = {
            "schema": "pi.agent_status.v1",
            "goal": "cross provider review regression",
            "answer": "No work was possible; a human decision is required.",
            "plain_answer": "No work was possible this stop; a human decision is required.",
            "state": "needs_human",
            "changed": ["no change: no work performed"],
            "verified": [{"command": "cross-provider shame review", "result": "PASS"}],
            "proof": [],
            "needs_human": {"action": "decide whether to enable the missing integration", "reason": "blocker requires human choice"},
        }
        reviewed_human = write_review(work, needs_human_status, author="openai", reviewer="zai", model="zai/glm-5.3:high")
        needs_human_status["proof"] = [str(reviewed_human)]
        reviewed_human.write_text(json.dumps({
            **json.loads(reviewed_human.read_text(encoding="utf-8")),
            "reviewed_candidate_hash": status_review_hash(needs_human_status),
        }), encoding="utf-8")
        honest = call(needs_human_status)
        assert honest["decision"] == "pass", honest
        assert honest["features"]["cross_family_review"] == {"status": "reviewed", "degraded": False}, honest
        assert all(item.startswith("no change") for item in honest["features"]["status"]["changed"]), honest

        # A non-terminal stop (state=continuing) cannot dodge the review gate.
        continuing = {
            "schema": "pi.agent_status.v1",
            "goal": "cross provider review regression",
            "answer": "Work continues.",
            "plain_answer": "Work continues; one command remains before the stop can be reviewed.",
            "state": "continuing",
            "changed": ["no change: fixture"],
            "not_done": [{"item": "final eval", "next_command": "python3 skills/shame/sanity.sh"}],
        }
        cont = call(continuing)
        assert cont["decision"] == "reject" and "cross_family_review_required" in cont["reason_codes"], cont
        assert cont["features"]["cross_family_review"]["status"] == "unreviewed", cont

    print(json.dumps({
        "schema": "lazy_report_shame.cross_provider_review_required_eval.v1",
        "status": "PASS",
        "checked": [
            "guarded stop without cross-family review receipt is rejected (any state, not only done)",
            "same-provider review proof is rejected",
            "same-family alias reviewer (openai vs openai-codex/gpt-5.6) is rejected as self-review",
            "different-family review receipt with pi-subagents metadata is accepted",
            "missing/nonzero/mismatched pi-subagents metadata rejects the receipt",
            "reviewer REJECT verdict rejects with restart_with_reviewer_critique steering carrying the critique",
            "honest no-work needs_human WITHOUT review is rejected unreviewed/degraded (no exceptions)",
            "honest no-work needs_human WITH cross-family receipt passes cleanly, no fabricated changed[] filler",
            "state=continuing cannot dodge the review gate",
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
