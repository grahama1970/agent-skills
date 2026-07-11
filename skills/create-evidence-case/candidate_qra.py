"""QRA quarantine pipeline and evidence case persistence.

Handles:
- EvidenceCaseStore2: persist complete evidence cases to /memory
- Candidate QRA quarantine: stage SATISFIED cases for human review
- Promote/reject candidates via /interview integration
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from loguru import logger

from collect import (
    SKILLS_DIR,
    _grade_item_confidence,
    _memory_learn_direct,
)
from models import (
    ClaimNode,
    DecompositionNode,
    EvidenceNode,
    StrategyNode,
    VerdictNode,
)
from scoring import (
    gates_to_grade,
    gates_to_score,
    gates_to_verdict,
    win_credit,
)
from storage import EvidenceCaseStore
from strategies import COMPOSED_SKILLS


INTERVIEW_SKILL = SKILLS_DIR / "interview" / "run.sh"

CANDIDATE_STORAGE = Path("/mnt/storage12tb/skills/create-evidence-case/candidates")
if not CANDIDATE_STORAGE.exists():
    CANDIDATE_STORAGE = Path(__file__).parent / "state" / "candidates"
CANDIDATE_STORAGE.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Persistence — store evidence cases in /memory
# ---------------------------------------------------------------------------

class EvidenceCaseStore2:
    """Thin wrapper around EvidenceCaseStore for v4 persistence."""

    def __init__(self):
        self.store = EvidenceCaseStore()

    def persist_case(
        self,
        question: str,
        category: str,
        verdict_state: str,
        gates: list[dict],
        evidence_items: list[dict],
        answer: str,
        technique_groups: dict[str, int] | None = None,
        sub_claims: list[str] | None = None,
        control_ids: list[str] | None = None,
        decomposition: dict | None = None,
        grade: str | None = None,
        score: float | None = None,
        # v4.3 schema fields — self-contained QRA metadata
        source_framework: str | None = None,
        source_control_id: str | None = None,
        relationship_id: str | None = None,
        expertise: str | None = None,
        difficulty: str | None = None,
        mind: list[str] | None = None,
        evidence_case: dict | None = None,
        formal_proof: dict | None = None,
        sacm_ref: dict | None = None,
    ) -> dict:
        """Persist a complete evidence case. Called by the agent after reasoning.

        v4.3 adds self-contained QRA metadata:
        - source_framework: SPARTA, NIST-800-53, CWE, CAPEC
        - source_control_id: SA-1, IA-5, CWE-287
        - evidence_case: crosswalk chains (null if no edges = valid)
        - formal_proof: Lean4 proof refs (null if not verified)
        - sacm_ref: SACM context/claim node refs
        """
        claim = ClaimNode(
            text=question,
            category=category,
            control_ids=control_ids or [],
            gate_results=gates,
            sub_claims=sub_claims or [],
        )
        claim.verdict = verdict_state.upper()

        evidence = []
        for item in evidence_items[:10]:
            sol = item.get("solution", item.get("text", item.get("answer", "")))
            cid = item.get("control_id", "")
            tactical = item.get("tactical_tags", [])
            conf = _grade_item_confidence(item)
            evidence.append(EvidenceNode(
                method="EXAMINE",
                layer="sparta_qra",
                collector="agent_decision",
                result={
                    "source": "sparta_qra",
                    "qra_text": sol[:300] if isinstance(sol, str) else "",
                    "control_id": cid,
                    "technique": tactical[0] if tactical else cid,
                    "question": (item.get("question", "") or "")[:100],
                },
                confidence=conf,
                artifact_ref="sparta_qra",
                control_ids=[cid] if cid else [],
            ))

        gates_passed = sum(1 for g in gates if g.get("passed"))
        strategy = StrategyNode(
            name="agent_driven",
            skills=COMPOSED_SKILLS,
            turns=len(gates),
            score=score,
            selected=True,
        )

        verdict = VerdictNode(
            state=verdict_state,
            grade=grade,
            score=score,
            strategy_id=strategy.id,
            evidence_ids=[e.id for e in evidence],
            reasoning=answer,
            grader={"type": "agent_driven", "model_id": "", "modified_in_session": False},
        )

        # Persist to /memory before returning so a successful CLI result has a
        # durable evidence-case artifact rather than an unfinished daemon thread.
        from storage import _upsert_evidence_case

        # Build consolidated case document for single upsert
        case_doc = {
            "question": question[:500],
            "category": category,
            "verdict": verdict.state,
            "grade": verdict.grade,
            "score": verdict.score,
            "gates_passed": gates_passed,
            "gates_total": len(gates),
            "gate_results": gates,
            "control_ids": control_ids[:10] if control_ids else [],
            "answer_preview": answer[:300],
            "claim": claim.to_dict(),
            "strategy": strategy.to_dict(),
            "evidence_nodes": [e.to_dict() for e in evidence],
            "verdict_node": verdict.to_dict(),
            # v4.3 self-contained QRA metadata
            "source_framework": source_framework,
            "source_control_id": source_control_id,
            "relationship_id": relationship_id,
            "expertise": expertise or "expert",
            "difficulty": difficulty or "single_hop",
            "mind": mind or [],
            "evidence_case": evidence_case,  # null = no crosswalk edges (valid)
            "formal_proof": formal_proof,    # null = not verified (valid)
            "sacm_ref": sacm_ref,            # null = not exported (valid)
        }

        persistence_ok = _upsert_evidence_case(case_doc)

        return {
            "claim": claim.to_dict(),
            "strategies": [strategy.to_dict()],
            "evidence": [e.to_dict() for e in evidence],
            "verdict": verdict.to_dict(),
            "answer": answer,
            "gate_trace": gates,
            "gates_passed": gates_passed,
            "gates_total": len(gates),
            "control_ids": control_ids[:20] if control_ids else [],
            "recall_count": len(evidence_items),
            "technique_groups": technique_groups or {},
            "sub_claims": sub_claims or [],
            "decomposition": decomposition,
            # v4.3 self-contained QRA metadata
            "source_framework": source_framework,
            "source_control_id": source_control_id,
            "relationship_id": relationship_id,
            "expertise": expertise or "expert",
            "difficulty": difficulty or "single_hop",
            "mind": mind or [],
            "evidence_case": evidence_case,
            "formal_proof": formal_proof,
            "sacm_ref": sacm_ref,
            "persistence": {
                "ok": persistence_ok,
                "collection": "evidence_cases",
            },
        }


# ---------------------------------------------------------------------------
# QRA Quarantine — SATISFIED cases become candidate QRAs for human review
# ---------------------------------------------------------------------------

def quarantine_as_candidate_qra(
    question: str,
    answer: str,
    case_result: dict,
    evidence_items: list[dict],
) -> dict:
    """Stage a SATISFIED evidence case as a candidate QRA for human review."""
    technique_groups = case_result.get("technique_groups", {})
    control_ids = sorted({
        item.get("control_id", "")
        for item in evidence_items if item.get("control_id")
    })
    tactical_tags = sorted(technique_groups.keys()) if technique_groups else ["Harden"]
    tactical_tags = [t for t in tactical_tags if t and t != "UNTAGGED"]

    qhash = hashlib.sha256(question.encode()).hexdigest()[:12]
    candidate_id = f"EC-{qhash}"

    source_qra_keys = [
        item.get("_key", item.get("id", ""))
        for item in evidence_items[:10]
        if item.get("_key") or item.get("id")
    ]

    candidate = {
        "candidate_id": candidate_id,
        "question": question,
        "answer": answer,
        "control_ids": control_ids,
        "tactical_tags": tactical_tags,
        "source": "evidence_case",
        "source_qra_keys": source_qra_keys,
        "technique_bridge": case_result.get("gate_trace", [{}])[-1].get("detail", ""),
        "verdict": case_result.get("verdict", {}).get("state", "satisfied"),
        "grade": case_result.get("verdict", {}).get("grade", ""),
        "status": "pending_review",
        "created_at": time.time(),
        "reviewed_at": None,
        "reviewer_decision": None,
        # v4.3 self-contained QRA metadata (passed through from persist_case)
        "source_framework": case_result.get("source_framework"),
        "source_control_id": case_result.get("source_control_id"),
        "relationship_id": case_result.get("relationship_id"),
        "expertise": case_result.get("expertise", "expert"),
        "difficulty": case_result.get("difficulty", "single_hop"),
        "mind": case_result.get("mind", []),
        "evidence_case": case_result.get("evidence_case"),
        "formal_proof": case_result.get("formal_proof"),
        "sacm_ref": case_result.get("sacm_ref"),
    }

    tags = ["qra_candidate", "pending_review"] + control_ids[:5]
    if not _memory_learn_direct(
        problem=question[:500],
        solution=json.dumps(candidate, default=str),
        scope="sparta_qra_candidates",
        tags=tags,
    ):
        logger.warning("candidate persist failed for {}", candidate_id)

    candidate_file = CANDIDATE_STORAGE / f"{candidate_id}.json"
    candidate_file.write_text(json.dumps(candidate, indent=2, default=str))

    interview_file = generate_review_questions(candidate, evidence_items)

    logger.info("Quarantined candidate QRA {} — review via: {}", candidate_id, interview_file)
    return {
        "candidate_id": candidate_id,
        "candidate_file": str(candidate_file),
        "interview_file": str(interview_file),
        "status": "pending_review",
    }


def generate_review_questions(candidate: dict, evidence_items: list[dict]) -> Path:
    """Generate /interview questions.json for human QRA review."""
    cid = candidate["candidate_id"]

    source_summary = []
    for i, item in enumerate(evidence_items[:5], 1):
        ctrl = item.get("control_id", "?")
        tags = ", ".join(item.get("tactical_tags", [])[:3])
        q_text = (item.get("question", "") or "")[:80]
        source_summary.append(f"{i}. [{ctrl}] ({tags}) {q_text}")
    sources_text = "\n".join(source_summary)

    questions = {
        "title": f"QRA Review: {cid}",
        "context": (
            f"Evidence case produced a SATISFIED verdict. "
            f"Review this candidate QRA for promotion to the production corpus.\n\n"
            f"**Question:** {candidate['question']}\n\n"
            f"**Synthesized Answer:** {candidate['answer'][:500]}\n\n"
            f"**Control IDs:** {', '.join(candidate['control_ids'][:10])}\n\n"
            f"**Tactical Tags:** {', '.join(candidate['tactical_tags'])}\n\n"
            f"**Technique Bridge:** {candidate.get('technique_bridge', 'N/A')}\n\n"
            f"**Source QRAs:**\n{sources_text}"
        ),
        "questions": [
            {
                "id": "approve_answer",
                "text": "Is the synthesized answer accurate and well-grounded?",
                "type": "yes_no_refine",
                "recommendation": "yes",
                "reason": f"Grade {candidate.get('grade', '?')} with {len(candidate['control_ids'])} controls and coherent technique bridge.",
            },
            {
                "id": "edit_answer",
                "text": "Edit the answer if needed (leave empty to keep as-is):",
                "type": "text",
                "required": False,
                "recommendation": "",
                "reason": "Only edit if factual errors or missing context.",
            },
            {
                "id": "confirm_controls",
                "text": f"Are these control IDs correct? {', '.join(candidate['control_ids'][:8])}",
                "type": "yes_no_refine",
                "recommendation": "yes",
                "reason": "Controls extracted from QRA recall data.",
            },
            {
                "id": "confirm_tags",
                "text": f"Are these tactical tags appropriate? {', '.join(candidate['tactical_tags'])}",
                "type": "yes_no_refine",
                "recommendation": "yes",
                "reason": "Tags derived from dominant technique bridge.",
            },
            {
                "id": "final_decision",
                "text": "Final decision: Promote this QRA to production?",
                "type": "select",
                "options": ["approve", "approve_with_edits", "reject", "defer"],
                "recommendation": "approve",
                "reason": "SATISFIED evidence case with sufficient grounding.",
            },
            {
                "id": "rejection_reason",
                "text": "If rejecting, why? (for GRPO training data)",
                "type": "text",
                "required": False,
                "recommendation": "",
                "reason": "Rejection reasons help improve future QRA generation.",
            },
        ],
    }

    interview_file = CANDIDATE_STORAGE / f"{cid}_review.json"
    interview_file.write_text(json.dumps(questions, indent=2))
    return interview_file


def generate_gap_review_questions(
    question: str,
    case_result: dict,
    clarify_result: dict | None,
) -> Path:
    """Generate /interview questions.json for INCONCLUSIVE gap review."""
    qhash = hashlib.sha256(question.encode()).hexdigest()[:8]

    technique_detail = ""
    for step in case_result.get("gate_trace", []):
        if "technique" in step.get("gate", ""):
            technique_detail = step.get("detail", "")

    clarify_text = ""
    if clarify_result and isinstance(clarify_result, dict):
        clarify_text = json.dumps(clarify_result, indent=2, default=str)[:1000]

    questions = {
        "title": f"Gap Review: {qhash}",
        "context": (
            f"Evidence case returned INCONCLUSIVE. Review whether this is a real corpus gap.\n\n"
            f"**Question:** {question}\n\n"
            f"**Technique Analysis:** {technique_detail}\n\n"
            f"**Clarify Output:** {clarify_text}"
        ),
        "questions": [
            {
                "id": "gap_type",
                "text": "Is this a real corpus gap or a false gap?",
                "type": "select",
                "options": ["real_gap", "false_gap", "partial_coverage", "out_of_scope"],
                "recommendation": "real_gap",
                "reason": "Technique bridge failed — entities don't share a technique.",
            },
            {
                "id": "research_action",
                "text": "What action should be taken?",
                "type": "select",
                "options": ["dogpile_research", "adjust_thresholds", "manual_qra", "ignore"],
                "recommendation": "dogpile_research",
                "reason": "Use /dogpile Tier 3 research to find external evidence.",
            },
            {
                "id": "notes",
                "text": "Additional context or notes:",
                "type": "text",
                "required": False,
            },
        ],
    }

    interview_file = CANDIDATE_STORAGE / f"gap_{qhash}_review.json"
    interview_file.write_text(json.dumps(questions, indent=2))
    return interview_file


def build_gap_review_candidate(
    *,
    question: str,
    case_result: dict,
    clarify_result: dict | None = None,
) -> dict[str, Any]:
    """Build an advisory CAE gap-review request without mutating a QRA.

    This is the handoff shape for /ask cae-gap-review, /monitor-sparta, and
    Sparta Chat. It intentionally does not repair, approve, or persist a QRA.
    Proposed QRA corrections remain recommendations until a fresh
    /create-evidence-case run grounds them.
    """
    gate_trace = list(case_result.get("gate_trace") or [])
    verdict = case_result.get("verdict") if isinstance(case_result.get("verdict"), dict) else {}
    evidence_case = case_result.get("evidence_case") if isinstance(case_result.get("evidence_case"), dict) else {}
    missing_spans: list[Any] = []
    for step in gate_trace:
        if not isinstance(step, dict):
            continue
        if step.get("passed") is False:
            missing_spans.append({
                "gate": step.get("gate", ""),
                "detail": step.get("detail", ""),
                "blocking_entities": step.get("blocking_entities", []),
            })
    if clarify_result:
        missing_spans.append({
            "gate": "clarify",
            "detail": "Clarification output was produced for the failed evidence case.",
            "clarify_result": clarify_result,
        })
    return {
        "kind": "cae_gap_review_candidate",
        "advisory_only": True,
        "question": question,
        "evidence_case_id": (
            evidence_case.get("case_id")
            or evidence_case.get("id")
            or case_result.get("case_id")
            or case_result.get("id")
        ),
        "evidence_case_version": (
            evidence_case.get("version")
            or case_result.get("evidence_case_version")
            or case_result.get("version")
        ),
        "source_evidence_case_hash": (
            evidence_case.get("hash")
            or case_result.get("evidence_case_hash")
            or case_result.get("case_hash")
        ),
        "verdict_state": verdict.get("state") or case_result.get("verdict_state") or case_result.get("verdict"),
        "final_status": "NEEDS_VERIFICATION",
        "gate_trace": gate_trace,
        "entities": case_result.get("entities") or case_result.get("control_ids") or [],
        "missing_spans": missing_spans,
        "source_artifacts": case_result.get("source_artifacts") or case_result.get("evidence") or [],
        "qra_correction_recommendation": {
            "status": "not_proposed",
            "requires_new_evidence_case": True,
        },
        "mutation_policy": "no_qra_mutation",
    }


def promote_candidate_qra(candidate_id: str, edited_answer: str | None = None) -> dict:
    """Promote an approved candidate QRA to sparta_qra collection."""
    candidate_file = CANDIDATE_STORAGE / f"{candidate_id}.json"
    if not candidate_file.exists():
        return {"ok": False, "error": f"Candidate {candidate_id} not found"}

    candidate = json.loads(candidate_file.read_text())

    answer = edited_answer if edited_answer else candidate["answer"]

    qra_data = {
        "question": candidate["question"],
        "answer": answer,
        "control_id": candidate["control_ids"][0] if candidate["control_ids"] else "",
        "tactical_tags": candidate["tactical_tags"],
        "source": "evidence_case_promoted",
        "source_candidate_id": candidate_id,
        "source_qra_keys": candidate.get("source_qra_keys", []),
        "promoted_at": time.time(),
        # v4.3 self-contained QRA metadata
        "source_framework": candidate.get("source_framework"),
        "source_control_id": candidate.get("source_control_id"),
        "relationship_id": candidate.get("relationship_id"),
        "expertise": candidate.get("expertise", "expert"),
        "difficulty": candidate.get("difficulty", "single_hop"),
        "mind": candidate.get("mind", []),
        "evidence_case": candidate.get("evidence_case"),
        "formal_proof": candidate.get("formal_proof"),
        "sacm_ref": candidate.get("sacm_ref"),
    }

    tags = ["promoted_qra", "evidence_case"] + candidate["tactical_tags"][:5]
    ok = _memory_learn_direct(
        problem=candidate["question"][:500],
        solution=json.dumps(qra_data, default=str),
        scope="sparta_qra",
        tags=tags,
    )

    candidate["status"] = "promoted" if ok else "promotion_failed"
    candidate["reviewed_at"] = time.time()
    candidate["reviewer_decision"] = "approve"
    candidate_file.write_text(json.dumps(candidate, indent=2, default=str))

    return {"ok": ok, "candidate_id": candidate_id, "status": candidate["status"]}


def reject_candidate_qra(candidate_id: str, reason: str = "") -> dict:
    """Reject a candidate QRA and move to rejected_qras for GRPO training."""
    candidate_file = CANDIDATE_STORAGE / f"{candidate_id}.json"
    if not candidate_file.exists():
        return {"ok": False, "error": f"Candidate {candidate_id} not found"}

    candidate = json.loads(candidate_file.read_text())

    rejection = {
        **candidate,
        "status": "rejected",
        "rejection_reason": reason,
        "reviewed_at": time.time(),
        "reviewer_decision": "reject",
    }

    _memory_learn_direct(
        problem=candidate["question"][:500],
        solution=json.dumps(rejection, default=str),
        scope="rejected_qras",
        tags=["rejected_qra", "grpo_training"],
    )

    candidate["status"] = "rejected"
    candidate["reviewed_at"] = time.time()
    candidate["reviewer_decision"] = "reject"
    candidate["rejection_reason"] = reason
    candidate_file.write_text(json.dumps(candidate, indent=2, default=str))

    return {"ok": True, "candidate_id": candidate_id, "status": "rejected"}


def process_interview_result(candidate_id: str, interview_result: dict) -> dict:
    """Process /interview responses and promote or reject the candidate."""
    responses = interview_result.get("responses", {})

    final = responses.get("final_decision", {})
    decision = final.get("value", "defer") if isinstance(final, dict) else str(final)

    if decision in ("approve", "approve_with_edits"):
        edit_resp = responses.get("edit_answer", {})
        edited = edit_resp.get("value", "") if isinstance(edit_resp, dict) else ""
        edited = edited.strip() if edited else None
        return promote_candidate_qra(candidate_id, edited_answer=edited)

    elif decision == "reject":
        reason_resp = responses.get("rejection_reason", {})
        reason = reason_resp.get("value", "") if isinstance(reason_resp, dict) else ""
        return reject_candidate_qra(candidate_id, reason=str(reason))

    else:
        return {"ok": True, "candidate_id": candidate_id, "status": "deferred"}
