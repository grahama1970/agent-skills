"""Shared fixture helper: mint a valid cross-family pi-subagent review receipt.

Every guarded harness stop requires a lazy_report_shame.cross_provider_review.v1
receipt from a different model family, backed by reviewer subagent metadata.
Eval fixtures that expect acceptance attach one via attach_review().
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

DEFAULT_REVIEWER = "zai"
DEFAULT_MODEL = "zai/glm-5.3-flash"


GENERATOR = "pi-subagents"


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


def write_review(work: Path, status: dict, *, author: str = "openai",
                 reviewer: str = DEFAULT_REVIEWER, model: str = DEFAULT_MODEL,
                 verdict: str = "PASS", critique: str | None = None) -> Path:
    # Same shape the pi-subagents stop-review bridge emits; the checker rejects
    # receipts without this harness-owned provenance.
    output = work / f"output-{reviewer}.md"
    output.write_text(f"VERDICT: {verdict}\nCRITIQUE: {critique or 'fixture reviewer'}\n", encoding="utf-8")
    metadata = work / f"meta-{reviewer}.json"
    metadata.write_text(json.dumps({
        "schema": "lazy_report_shame.cross_provider_review_metadata.v1",
        "generated_by": GENERATOR,
        "model": model,
        "exitCode": 0,
        "output_path": str(output),
    }) + "\n", encoding="utf-8")
    payload = {
        "schema": "lazy_report_shame.cross_provider_review.v1",
        "generated_by": GENERATOR,
        "verdict": verdict,
        "author_provider": author,
        "reviewer_provider": reviewer,
        "reviewer_model": model,
        "review_metadata_path": str(metadata),
        "review_output_path": str(output),
        "reviewed_candidate_hash": status_review_hash(status),
    }
    if critique:
        payload["critique"] = critique
    proof = work / f"review-{reviewer}.json"
    proof.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return proof


def attach_review(work: Path, status: dict, *, author: str = "openai",
                  reviewer: str = DEFAULT_REVIEWER, model: str = DEFAULT_MODEL) -> dict:
    """Attach a PASS cross-family review receipt to a status fixture in place.

    Idempotent: strips any previously attached review proof/verified entries
    first, so a mutated variant can re-mint a receipt (the candidate hash binds
    plain_answer/answer, so mutating those invalidates the old receipt).
    """
    work.mkdir(parents=True, exist_ok=True)
    review_cmds = {"cross-provider shame review", "lazy_report_shame.cross_provider_review.v1"}
    status["proof"] = [p for p in status.get("proof", []) if "review-" not in Path(str(p)).name]
    status["verified"] = [v for v in status.get("verified", []) if v.get("command") not in review_cmds]
    proof = write_review(work, status, author=author, reviewer=reviewer, model=model)
    status.setdefault("proof", []).append(str(proof))
    status.setdefault("verified", []).append({"command": "cross-provider shame review", "result": "PASS"})
    # Recompute: hash covers goal/answer/plain_answer/state/changed only, so
    # appending proof/verified does not change it, but rewrite for safety.
    payload = json.loads(proof.read_text(encoding="utf-8"))
    payload["reviewed_candidate_hash"] = status_review_hash(status)
    proof.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return status


def env_with(author: str = "openai") -> dict:
    return {**os.environ, "LRSSS_AUTHOR_PROVIDER": author}
