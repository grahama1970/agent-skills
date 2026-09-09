from __future__ import annotations

import json
import hashlib
from pathlib import Path

from live_evidence.models import EvidenceCard
from live_evidence.reviewed_answer import binding_text, read_reviewed_answer


def bind_review(
    tmp_path: Path,
    card: EvidenceCard,
    answer: str | None = None,
    *,
    session_id: str | None = None,
    policy_digest: str | None = None,
) -> EvidenceCard:
    updates = {"answer": answer or card.answer or "Reviewed fixture answer."}
    if policy_digest is not None:
        updates["policy_digest"] = policy_digest
    approved = card.model_copy(update=updates)
    binding = review_binding(approved)
    if session_id is not None:
        binding["session_id"] = session_id
    run_dir = write_reviewed_run(tmp_path / "review-runs" / approved.card_id, binding, approved.answer or "")
    _, approval = read_reviewed_answer(run_dir, binding)
    return approved.model_copy(update={"review_verdict": "ok", "answer_review": approval})


def bind_review_to_state(tmp_path: Path, state, card: EvidenceCard, answer: str | None = None) -> EvidenceCard:
    return bind_review(
        tmp_path,
        card,
        answer,
        session_id=state.session_id(),
        policy_digest=state.session_policy_digest(),
    )


def review_binding(card: EvidenceCard) -> dict:
    return {
        "question_id": card.question_id,
        "question_revision": card.question_revision,
        "policy_digest": card.policy_digest,
        "query": card.query,
    }


def write_reviewed_run(run_dir: Path, binding: dict, answer: str) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    creator = run_dir / "node-artifacts" / "creator"
    reviewer = run_dir / "node-artifacts" / "reviewer"
    creator.mkdir(parents=True, exist_ok=True)
    reviewer.mkdir(parents=True, exist_ok=True)
    token = binding_text(binding)
    (run_dir / "dag.json").write_text(json.dumps({
        "context": {"dag_template": "creator-reviewer", "request": token},
        "entry_node": "creator",
        "edges": [{"from": "creator", "to": "reviewer"}],
    }))
    _write_node(creator, "creator", answer)
    reviewer_prompt = f"Review this exact answer.\n{token}\n{answer}"
    (reviewer / "prompt.md").write_text(reviewer_prompt)
    _write_node(reviewer, "reviewer", "VERDICT: PASS", verdict="PASS", prior_nodes=["creator"], prompt_path=reviewer / "prompt.md")
    return run_dir


def _write_node(
    node_dir: Path,
    node_id: str,
    response: str,
    *,
    verdict: str | None = None,
    prior_nodes: list[str] | None = None,
    prompt_path: Path | None = None,
) -> None:
    response_path = node_dir / "response.md"
    response_path.write_text(response)
    receipt = {
        "schema": "ask.tau_dag_handler_receipt.v1",
        "node_id": node_id,
        "ok": True,
        "status": "PASS",
        "live": True,
        "mocked": False,
        "response_path": str(response_path),
        "response_sha256": hashlib.sha256(response.encode()).hexdigest(),
    }
    if verdict is not None:
        receipt.update({
            "verdict": verdict,
            "requires_verdict": True,
            "prior_nodes": prior_nodes or [],
            "prompt_path": str(prompt_path),
        })
    (node_dir / "node-receipt.json").write_text(json.dumps(receipt))
