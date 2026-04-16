"""Grading and self-improvement loop for SPARTA conversation simulation.

Handles persona evaluation, Brandon session grading, the self-grading
improvement loop, shadow-LEGO delta logging, and episodic recall for
the inner self-improvement cycle.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger

from sparta_stress_test.conversation_models import (
    SELF_GRADE_MAX_ITERATIONS,
    SELF_GRADE_TARGET_COMPOSITE,
    SHADOW_DELTA_PATH,
    SHADOW_JSONL_PATH,
    SessionGrade,
    StressSession,
    _HAS_ASSISTANT,
    _HAS_QUALITY_UTILS,
    _call_scillm,
    _get_db,
)
from sparta_stress_test.conversation_prompts import (
    BRANDON_SESSION_GRADE,
    MARGARET_FOLLOWUP,
    JENNIFER_FOLLOWUP,
)
from sparta_stress_test.conversation_retrieval import (
    _recall_episodic_context,
    _sparta_answer,
)
from sparta_stress_test.conversation_synthesis import (
    _extract_entity_ids,
    _validate_entities_with_parents,
)

# Conditional imports
try:
    from assistant import classify as _assistant_classify
except ImportError:
    _assistant_classify = None


def _try_lean4_verification(answer_text: str, qra_count: int) -> Optional[Dict]:
    """Attempt Lean4 reasoning verification via the lean4-prove service.

    Returns None if service unavailable or no QRAs cited.
    Non-fatal — grading continues without Lean4 if service is down.
    """
    if qra_count == 0:
        return None

    import os
    lean4_url = os.getenv("LEAN4_SERVICE_URL", "http://localhost:8604")

    try:
        import httpx
        # Check if service is available (fast health check)
        health = httpx.get(f"{lean4_url}/health", timeout=2.0)
        if health.status_code != 200:
            return None
    except Exception:
        logger.debug("Lean4 service not available — skipping reasoning verification")
        return None

    try:
        # Use qra_reasoning module if available
        import sys
        from pathlib import Path
        lean4_skill = Path(__file__).resolve().parents[2] / "lean4-prove"
        if str(lean4_skill) not in sys.path:
            sys.path.insert(0, str(lean4_skill))

        from qra_reasoning import verify_qra_reasoning

        result = verify_qra_reasoning(
            {"reasoning": answer_text, "qra_id": "conversation_grading"},
            timeout=30,
        )

        score = (
            result.steps_verified / max(result.steps_total, 1)
            if result.steps_total > 0
            else 0.5
        )

        return {
            "score": score,
            "steps_total": result.steps_total,
            "steps_verified": result.steps_verified,
            "steps_failed": result.steps_failed,
            "error_taxonomy": result.error_taxonomy,
        }
    except Exception as e:
        logger.debug(f"Lean4 verification failed: {e}")
        return None


# --------------------------------------------------------------------------- #
# Persona follow-up evaluation (Turn 3)
# --------------------------------------------------------------------------- #


def _persona_evaluate(
    persona: str,
    original_question: str,
    sparta_answer: str,
    adversarial: bool = False,
    process_evidence: dict = None,
) -> Dict:
    """Have the persona evaluate SPARTA's answer and generate follow-up.

    Returns dict with: evaluation, follow_up, reasoning.
    process_evidence provides deterministic signals (verified citations,
    bridge overlap, richness) so the persona can make informed decisions
    rather than relying solely on answer text quality.
    """
    system = MARGARET_FOLLOWUP if "Margaret" in persona else JENNIFER_FOLLOWUP

    # Fix 5: Always inject process evidence into persona prompt so persona
    # judges grounding quality, not just text quality.
    evidence_block = ""
    if process_evidence:
        verified = process_evidence.get("qra_citations_verified", 0)
        total = process_evidence.get("qra_citations_total", 0)
        bridge_count = process_evidence.get("bridge_overlap_count", 0)
        richness = process_evidence.get("richness_score", 0.0)
        self_grade = process_evidence.get("self_grade", "")
        self_composite = process_evidence.get("self_composite", 0.0)
        citation_pct = f"{verified}/{total} ({verified/max(total,1)*100:.0f}%)" if total > 0 else "0/0"
        evidence_block = f"""

DETERMINISTIC EVIDENCE (from ArangoDB — these are facts, not opinions):
- Citations verified: {citation_pct}
- Bridge overlap: {bridge_count} tags matched
- Richness score: {richness:.2f}
- Self-grade: {self_grade} ({self_composite:.0%})

IMPORTANT: Consider this evidence when evaluating. A well-grounded answer
with awkward phrasing is BETTER than a fluent answer with no citations.
If citations are verified and bridge overlap is high, the answer IS grounded
in the QRA corpus — do NOT mark it "wrong" for style issues alone."""

    user_prompt = f"""YOUR ORIGINAL QUESTION:
{original_question}

SPARTA'S ANSWER:
{sparta_answer}
{evidence_block}
{"NOTE: You intentionally injected a flaw in your question. Evaluate whether SPARTA caught it." if adversarial else ""}

Evaluate the answer and decide your follow-up action."""

    raw = _call_scillm(system, user_prompt, max_tokens=512)

    try:
        result = json.loads(raw)
        return {
            "evaluation": result.get("evaluation", "incomplete"),
            "follow_up": result.get("follow_up", ""),
            "reasoning": result.get("reasoning", ""),
        }
    except (json.JSONDecodeError, TypeError):
        logger.warning(f"Could not parse persona evaluation: {raw[:200]}")
        return {
            "evaluation": "incomplete",
            "follow_up": "Could you provide more specific details about the relevant SPARTA controls?",
            "reasoning": "Failed to parse LLM response",
        }


# --------------------------------------------------------------------------- #
# Brandon session grading (post-session)
# --------------------------------------------------------------------------- #


def _grade_session_heuristic(session: StressSession) -> SessionGrade:
    """DEPRECATED: Heuristic grading is BANNED. Returns ungraded placeholder.

    Keyword scanning for assessments is prohibited across Embry-OS.
    Use semantic_grader.grade_response_semantic() instead.
    """
    logger.warning("Heuristic grading invoked — returning UNGRADED placeholder")
    return SessionGrade(
        composite=0.0,
        grade="F",
        scores={},
        tier=0,
        source="ungraded_fallback",
        rationale="Brandon LLM grading failed; heuristic scanning is BANNED. This session is UNGRADED.",
    )


def _grade_session_brandon(
    session: StressSession,
    best_self_composite: float = 0.0,
    process_signals: dict = None,
) -> SessionGrade:
    """Tier 2 Brandon grading via /scillm for full session.

    Uses deterministic anchoring: 60% from computed signals (verified
    citations, bridge overlap, richness, self-grade composite), 40%
    from Brandon's LLM qualitative assessment. This prevents wild
    grade swings between calls.
    """
    seed = session.seed_question
    expected_action = seed.get("expected_action", "QUERY")
    target_control = seed.get("target_control", "")

    # --- Bug fix: Correct rejection grading ---
    # When persona says "flaw_caught" on an adversarial/flawed question,
    # SPARTA correctly identified the flaw. This is an A, not an F.
    # Without this, correct NO_MATCH responses get F because 0 citations.
    persona_evals = [
        t.metadata.get("evaluation", "")
        for t in session.turns
        if t.role == "persona" and t.metadata
    ]
    if "flaw_caught" in persona_evals:
        is_adversarial = (
            session.adversarial
            or expected_action in ("NO_MATCH", "OFF_TOPIC")
            or seed.get("difficulty") == "flawed"
        )
        if is_adversarial:
            logger.debug(
                "Correct rejection: flaw_caught on adversarial question → A(85%)"
            )
            return SessionGrade(
                composite=0.85,
                grade="A",
                scores={"error_detection": 1.0, "session_coherence": 0.85},
                tier=2,
                source="correct_rejection_deterministic",
                rationale=(
                    "SPARTA correctly identified a flaw in an adversarial question. "
                    "Persona confirmed with 'flaw_caught'. 0 citations is correct "
                    "because the question itself was invalid."
                ),
            )

    transcript_lines = []
    for turn in session.turns:
        speaker = turn.speaker
        transcript_lines.append(f"[Turn {turn.turn_number}] {speaker}: {turn.content}")
    transcript_text = "\n\n".join(transcript_lines)

    all_source_keys = []
    for turn in session.turns:
        turn_keys = turn.metadata.get("source_keys", [])
        all_source_keys.extend(turn_keys)

    qra_ground_truth_text = ""
    if all_source_keys:
        try:
            from sparta_stress_test.semantic_grader import _build_qra_ground_truth
            qra_ground_truth_text = _build_qra_ground_truth(all_source_keys[:10])
        except Exception as e:
            logger.debug(f"QRA ground truth fetch failed for Brandon: {e}")
            qra_ground_truth_text = "(unavailable)"
    else:
        qra_ground_truth_text = "(No QRA source keys recorded in session turns)"

    # Compute deterministic anchor from process signals
    psig = process_signals or {}
    verified = psig.get("qra_citations_verified", 0)
    total = psig.get("qra_citations_total", 0)
    citation_ratio = verified / max(total, 1) if total > 0 else 0.0
    bridge_overlap = min(psig.get("bridge_overlap_count", 0) / 5.0, 1.0)
    richness = psig.get("richness_score", 0.0) or 0.0

    # --- Bug fix: Wrong-control relevance check ---
    # If target_control is set (e.g. "SV-SP-7") but the answer cites QRAs
    # from a different control (e.g. "SV-SP-10" via episodic memory),
    # those citations are IRRELEVANT. Penalize the citation_ratio.
    # Fix 6: Only apply wrong-control penalty on the FIRST SPARTA answer (turn 2).
    # If the persona asked a follow-up about a different control, the answer
    # should cite that control, not the original target.
    relevance_penalty = ""
    if target_control and verified > 0:
        import re as _re
        # Find the FIRST SPARTA answer turn only (turn 2)
        answer_text = ""
        sparta_turn_count = 0
        for turn in session.turns:
            if turn.speaker == "SPARTA":
                sparta_turn_count += 1
                if sparta_turn_count == 1:
                    answer_text = turn.content
                    break
        # Only apply penalty on first answer, not follow-up responses
        if answer_text and sparta_turn_count == 1:
            # Extract all control IDs from the answer
            answer_control_ids = set(_re.findall(r'[A-Z]{1,4}-[A-Z]{1,4}-\d{1,5}', answer_text))
            # If the answer mentions controls but NOT the target, citations are wrong-control
            if answer_control_ids and target_control not in answer_control_ids:
                logger.warning(
                    f"Wrong-control citations: asked about {target_control} but "
                    f"answer cites {answer_control_ids}"
                )
                citation_ratio *= 0.1  # 90% penalty — citations exist but for wrong control
                relevance_penalty = (
                    f" [WRONG-CONTROL: asked {target_control}, "
                    f"cited {sorted(answer_control_ids)[:3]}]"
                )

    det_score = (
        citation_ratio * 0.30
        + bridge_overlap * 0.10
        + richness * 0.05
        + min(best_self_composite, 1.0) * 0.15
    )
    det_score = max(0.0, min(0.60, det_score))

    det_summary = (
        f"Citations: {verified}/{total} verified{relevance_penalty}. "
        f"Bridge overlap: {psig.get('bridge_overlap_count', 0)} tags. "
        f"Richness: {richness:.2f}. "
        f"Best self-grade composite: {best_self_composite:.0%}. "
        f"Deterministic anchor: {det_score:.2f}/0.60."
    )

    prompt = BRANDON_SESSION_GRADE.format(
        persona=session.persona,
        transcript=transcript_text,
        difficulty=seed.get("difficulty", "medium"),
        expected_action=seed.get("expected_action", "QUERY"),
        target_control=seed.get("target_control", "N/A"),
        adversarial=session.adversarial,
        qra_ground_truth=qra_ground_truth_text,
    )

    # Append deterministic evidence to prompt
    prompt += f"""

DETERMINISTIC EVIDENCE (computed from ArangoDB lookups — HARD FACTS):
{det_summary}

CRITICAL: Your qualitative assessment accounts for 40% of the final grade.
The deterministic anchor ({det_score:.2f}) is already computed from verified
citations and taxonomy overlap. Your scores should COMPLEMENT, not contradict,
these facts. If 10/10 citations are verified, qra_citation_accuracy MUST be >= 0.9."""

    raw = _call_scillm(
        system="You are Brandon Bailey, Principal Director of Cyber Assessments at The Aerospace Corporation.",
        user_prompt=prompt,
        max_tokens=1024,
    )

    try:
        result = json.loads(raw)

        # Bug 12 fix: Compute LLM qualitative from individual scores,
        # NOT the LLM's self-computed composite. The LLM may classify
        # as "HALLUCINATED" (composite=0.0) even when deterministic
        # signals confirm the answer is grounded.
        scores = result.get("scores", {})
        qual_keys = [
            "initial_response_quality", "disambiguation_handling",
            "follow_up_quality", "response_naturalness",
            "domain_accuracy", "session_coherence",
        ]
        # Normalize 0-3 coarse scale to 0-1 (matches Fix 4 prompt change)
        raw_values = [float(scores.get(k, 1.5)) for k in qual_keys if k in scores]
        qual_values = [v / 3.0 if v > 1.0 else v for v in raw_values]
        if qual_values:
            llm_composite = sum(qual_values) / len(qual_values)
        else:
            llm_composite = float(result.get("composite", 0.0))

        # Apply deterministic anchoring: 60% det + 40% LLM
        anchored_composite = det_score + llm_composite * 0.40
        anchored_composite = max(0.0, min(1.0, anchored_composite))

        # Determine grade from anchored composite
        if anchored_composite >= 0.90:
            grade = "A+"
        elif anchored_composite >= 0.80:
            grade = "A"
        elif anchored_composite >= 0.65:
            grade = "B"
        elif anchored_composite >= 0.50:
            grade = "C"
        else:
            grade = "F"

        logger.debug(
            f"Brandon session grade: det={det_score:.2f} + llm={llm_composite:.2f}*0.40 "
            f"= {anchored_composite:.2f} → {grade}"
        )

        return SessionGrade(
            composite=anchored_composite,
            grade=grade,
            scores=result.get("scores", {}),
            tier=2,
            source="brandon_scillm_anchored",
            rationale=result.get("rationale", ""),
            reasoning_sound=result.get("reasoning_sound"),
            taxonomy_correct=result.get("taxonomy_correct"),
        )
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.warning(f"Brandon grading parse failed: {e}")
        # Fall back to deterministic-only grade
        if det_score >= 0.40:
            grade = "B" if det_score >= 0.45 else "C"
            return SessionGrade(
                composite=det_score,
                grade=grade,
                scores={},
                tier=1,
                source="deterministic_fallback",
                rationale=f"Brandon LLM failed ({e}), using deterministic anchor: {det_summary}",
            )
        return _grade_session_heuristic(session)


# --------------------------------------------------------------------------- #
# Self-grading improvement loop
# --------------------------------------------------------------------------- #


def _self_grade_response(
    question: str,
    answer: str,
    qra_source_keys: list = None,
    transcript: str = "",
    target_control: str = None,
    qra_count: int = 0,
    difficulty: str = "medium",
    expected_action: str = "QUERY",
    use_gpt_rationale: bool = True,
    process_signals: dict = None,
) -> dict:
    """Self-grade using deterministic anchoring + LLM qualitative assessment.

    Process signals (from retrieval pipeline) anchor 60% of the grade:
    - citation_ratio from ArangoDB lookup
    - lean4_score from formal verification
    - bridge_overlap from taxonomy intersection
    - richness_score from disambiguation evidence
    - delta_improvement from self-correction tracking
    """
    from sparta_stress_test.semantic_grader import grade_response_semantic, STUDENT_MODEL

    process_signals = process_signals or {}

    answer_hallucinated_entities = []
    if _HAS_QUALITY_UTILS:
        answer_entities = _extract_entity_ids(answer)
        if answer_entities:
            try:
                from graph_memory.arango_client import get_db
                db = get_db()
                _has_data = db.collection("sparta_qra").count() > 0
                if _has_data:
                    validity = _validate_entities_with_parents(answer_entities, db)
                    answer_hallucinated_entities = [
                        e for e in answer_entities if not validity.get(e, True)
                    ]
                    if answer_hallucinated_entities:
                        logger.warning(
                            f"Answer cites non-existent entities: {answer_hallucinated_entities}"
                        )
            except Exception:
                pass

    result = grade_response_semantic(
        question=question,
        answer=answer,
        transcript=transcript,
        qra_source_keys=qra_source_keys or [],
        target_control=target_control or "",
        difficulty=difficulty,
        expected_action=expected_action,
        model=STUDENT_MODEL,
        process_signals=process_signals,
    )

    if answer_hallucinated_entities:
        result["grade"] = "F"
        result["composite"] = min(result["composite"], 0.30)
        result["issues"] = result.get("issues", []) + [
            f"hallucinated_entity:{e}" for e in answer_hallucinated_entities
        ]
        result["rationale"] = (
            f"DETERMINISTIC OVERRIDE: Answer cites non-existent entities "
            f"{answer_hallucinated_entities}. {result.get('rationale', '')}"
        )

    if use_gpt_rationale and _HAS_ASSISTANT and _assistant_classify and result.get("grade") not in ("A+", "A"):
        try:
            grading_text = (
                f"Q: {question[:300]}\n"
                f"A: {answer[:500]}\n"
                f"QRA citations: {result.get('qra_citations_verified', 0)}/{result.get('qra_citations_total', 0)}\n"
                f"Semantic grade: {result.get('grade')} ({result.get('composite', 0):.0%})"
            )
            _assistant_classify(
                text=grading_text,
                task="response_quality",
                scope="sparta",
                confidence_threshold=0.75,
            )
        except Exception as e:
            logger.debug(f"/assistant shadow log failed: {e}")

    return result


def _self_grading_loop(
    question_text: str,
    target_control: Optional[str],
    seed_question: dict,
    initial_result: dict,
) -> tuple[dict, list[dict]]:
    """Self-grading improvement loop -- iterate until predicted A+ or max iterations.

    Returns:
        (best_result, iteration_log)
    """
    difficulty = seed_question.get("difficulty", "medium")
    expected_action = seed_question.get("expected_action", "QUERY")

    transcript = f"Turn 1:\nQ: {question_text}\nA: {initial_result['answer_text']}"

    # Two-stage evidence collection: gather ALL deterministic evidence FIRST
    # (citations, /lean4-prove, /assistant, /memory trace, bridge overlap)
    # then pass to the LLM grader as read-only context.
    retrieval_evidence = initial_result.get("evidence", {})
    initial_process_signals = {
        "bridge_overlap_count": initial_result.get("bridge_overlap_count", 0),
        "bridge_tags_matched": initial_result.get("bridge_tags_matched", []),
        "richness_score": retrieval_evidence.get("richness_score", 0.0),
        "framework_coverage": retrieval_evidence.get("framework_coverage", {}),
        "delta_improvement": 0.0,  # No delta on first pass
    }

    # Fix 2: Cache initial retrieval results (source_keys, QRA docs) so
    # self-grade iterations 1+ don't re-retrieve and lose citations.
    _cached_source_keys = list(initial_result.get("source_keys", []))
    _cached_qra_count = initial_result.get("qra_count", 0)

    self_grade = _self_grade_response(
        question=question_text,
        answer=initial_result["answer_text"],
        qra_source_keys=_cached_source_keys,
        transcript=transcript,
        target_control=target_control,
        qra_count=_cached_qra_count,
        difficulty=difficulty,
        expected_action=expected_action,
        process_signals=initial_process_signals,
    )

    # Extract lean4 results from the evidence collected inside grade_response_semantic
    lean4_score = self_grade.get("scores", {}).get("reasoning_chain_soundness", 0.0)
    lean4_error_taxonomy = self_grade.get("lean4_error_taxonomy", {})

    iteration_log = [{
        "iteration": 0,
        "grade": self_grade["grade"],
        "composite": self_grade["composite"],
        "issues": self_grade["issues"],
        "rationale": self_grade.get("rationale", ""),
        "qra_count": initial_result.get("qra_count", 0),
        "qra_citations_verified": self_grade.get("qra_citations_verified", 0),
        "qra_citations_total": self_grade.get("qra_citations_total", 0),
        "citation_details": self_grade.get("citation_details", []),
        "lean4_score": lean4_score if lean4_score > 0 else None,
        "lean4_errors": lean4_error_taxonomy,
        "evidence_sources": self_grade.get("evidence_sources", []),
    }]

    best_result = initial_result
    best_composite = self_grade["composite"]
    final_result = initial_result
    final_grade = self_grade
    first_composite = self_grade["composite"]

    if self_grade["composite"] >= SELF_GRADE_TARGET_COMPOSITE:
        logger.debug(
            f"Self-grade: {self_grade['grade']} ({self_grade['composite']:.0%}) "
            f"— accepted on first pass"
        )
        return best_result, iteration_log

    all_exclude_keys = list(initial_result.get("source_keys", []))
    prev_composite = self_grade["composite"]
    stall_count = 0
    has_invalid_entities = bool(initial_result.get("invalid_entities"))

    for iteration in range(1, SELF_GRADE_MAX_ITERATIONS + 1):
        if has_invalid_entities and self_grade.get("qra_citations_total", 0) == 0:
            logger.debug(
                f"Self-grade: skipping further iterations — no QRA citations possible "
                f"with unknown entities {initial_result.get('invalid_entities', [])}"
            )
            break
        logger.debug(
            f"Self-grade iteration {iteration}/{SELF_GRADE_MAX_ITERATIONS}: "
            f"current={self_grade['grade']} ({self_grade['composite']:.0%}), "
            f"issues={self_grade['issues']}"
        )

        episodic_context = _recall_episodic_context(question_text)

        enriched_question = question_text
        rationale = self_grade.get("rationale", "")
        if rationale:
            enriched_question += f"\n\n[Improvement guidance: {rationale[:200]}]"
        if episodic_context:
            enriched_question += f"\n\n[Context from similar prior answers:]\n{episodic_context[:500]}"

        retry_result = _sparta_answer(
            enriched_question,
            target_control=target_control,
            exclude_keys=all_exclude_keys,
            difficulty=difficulty,
            expected_action=expected_action,
        )

        transcript += f"\n\nTurn {iteration + 1}:\nQ: {question_text}\nA: {retry_result['answer_text']}"

        # Fix 2: Merge cached source keys from iteration 0 with any new keys
        # from re-retrieval, so citation verification always includes the
        # original sources that were used in the initial answer.
        retry_source_keys = list(retry_result.get("source_keys", []))
        merged_source_keys = list(dict.fromkeys(_cached_source_keys + retry_source_keys))

        # Process signals with delta improvement from previous iteration
        retry_evidence = retry_result.get("evidence", {})
        retry_process_signals = {
            "lean4_score": 0.0,  # Updated after lean4 verification below
            "bridge_overlap_count": retry_result.get("bridge_overlap_count", 0),
            "bridge_tags_matched": retry_result.get("bridge_tags_matched", []),
            "richness_score": retry_evidence.get("richness_score", 0.0),
            "framework_coverage": retry_evidence.get("framework_coverage", {}),
            "delta_improvement": (prev_composite - first_composite) if iteration > 0 else 0.0,
        }

        # Two-stage grading: collect_evidence runs inside grade_response_semantic
        # (lean4, assistant, memory trace all called automatically)
        # Use merged source keys so citations from iteration 0 are preserved
        new_grade = _self_grade_response(
            question=question_text,
            answer=retry_result["answer_text"],
            qra_source_keys=merged_source_keys,
            transcript=transcript,
            target_control=target_control,
            qra_count=max(_cached_qra_count, retry_result.get("qra_count", 0)),
            difficulty=difficulty,
            expected_action=expected_action,
            process_signals=retry_process_signals,
        )

        retry_lean4_score = new_grade.get("scores", {}).get("reasoning_chain_soundness", 0.0)

        iteration_log.append({
            "iteration": iteration,
            "grade": new_grade["grade"],
            "composite": new_grade["composite"],
            "issues": new_grade["issues"],
            "rationale": new_grade.get("rationale", ""),
            "qra_count": retry_result.get("qra_count", 0),
            "qra_citations_verified": new_grade.get("qra_citations_verified", 0),
            "qra_citations_total": new_grade.get("qra_citations_total", 0),
            "citation_details": new_grade.get("citation_details", []),
            "had_episodic_context": bool(episodic_context),
            "had_gpt_rationale": bool(rationale),
            "lean4_score": retry_lean4_score if retry_lean4_score > 0 else None,
            "lean4_errors": new_grade.get("lean4_error_taxonomy", {}),
            "evidence_sources": new_grade.get("evidence_sources", []),
        })

        all_exclude_keys.extend(retry_result.get("source_keys", []))

        final_result = retry_result
        final_grade = new_grade
        if new_grade["composite"] > best_composite:
            best_result = retry_result
            best_composite = new_grade["composite"]
            self_grade = new_grade
            stall_count = 0
        else:
            stall_count += 1

        if new_grade["composite"] >= SELF_GRADE_TARGET_COMPOSITE:
            logger.debug(
                f"Self-grade: {new_grade['grade']} ({new_grade['composite']:.0%}) "
                f"— accepted after {iteration} iteration(s)"
            )
            break

        if retry_result.get("action") == "CLARIFY":
            logger.debug(
                f"Self-grade: retry returned CLARIFY — keeping best prior answer "
                f"({best_composite:.0%})"
            )
            break

        if stall_count >= 2:
            logger.debug(
                f"Self-grade: stalled at {self_grade['grade']} ({best_composite:.0%}) "
                f"after {iteration} iterations — no improvement, accepting best"
            )
            break

    final_composite = final_grade["composite"]
    iteration_log.append({
        "_summary": True,
        "first_composite": first_composite,
        "final_composite": final_composite,
        "best_composite": best_composite,
        "delta": final_composite - first_composite,
        "iterations": len(iteration_log),
        "regressed": final_composite < first_composite,
        "final_grade": final_grade["grade"],
    })

    # Return the BEST result, not the last one — prevents regressions
    # from overwriting improvements
    return best_result, iteration_log


# --------------------------------------------------------------------------- #
# Shadow-LEGO delta logging (training data for classifiers/GPTs/regressors)
# --------------------------------------------------------------------------- #


def _log_shadow_entry(
    *,
    question: str,
    decision: str,
    clarify_trigger: Optional[str] = None,
    entities: Optional[List[str]] = None,
    lanes_used: Optional[List[str]] = None,
    qra_count: int = 0,
    labels_used: Optional[List[str]] = None,
    bridges: Optional[List[str]] = None,
    student_grade: str = "",
    teacher_grade: str = "",
) -> None:
    """Log a Brandon decision to shadow.jsonl for /assistant classifier training."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "input": question[:500],
        "decision": decision,
        "clarify_trigger": clarify_trigger,
        "entities_extracted": entities or [],
        "aql_lanes_used": lanes_used or [],
        "qra_count": qra_count,
        "labels_used": labels_used or [],
        "bridges": bridges or [],
        "student_grade": student_grade,
        "teacher_grade": teacher_grade,
        "agreed": student_grade == teacher_grade if (student_grade and teacher_grade) else None,
    }
    try:
        SHADOW_JSONL_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(SHADOW_JSONL_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.debug(f"Shadow entry log failed: {e}")


def _log_shadow_delta(
    *,
    session_id: str,
    question: str,
    persona: str,
    first_composite: float,
    final_composite: float,
    outer_rounds: int,
    inner_iterations: int,
    evaluation: str,
) -> None:
    """Log the improvement delta for Shadow-LEGO training."""
    from sparta_stress_test.conversation_models import OUTER_LOOP_TARGET

    entry = {
        "session_id": session_id,
        "timestamp": datetime.now().isoformat(),
        "question": question[:500],
        "persona": persona,
        "first_composite": round(first_composite, 4),
        "final_composite": round(final_composite, 4),
        "delta": round(final_composite - first_composite, 4),
        "outer_rounds": outer_rounds,
        "inner_iterations": inner_iterations,
        "persona_evaluation": evaluation,
        "target_met": final_composite >= OUTER_LOOP_TARGET,
    }
    try:
        SHADOW_DELTA_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(SHADOW_DELTA_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")
        logger.debug(
            f"Shadow delta: {first_composite:.2f}->{final_composite:.2f} "
            f"(delta={entry['delta']:+.2f}, {outer_rounds} outer, {inner_iterations} inner)"
        )
    except Exception as e:
        logger.warning(f"Shadow delta log failed: {e}")
