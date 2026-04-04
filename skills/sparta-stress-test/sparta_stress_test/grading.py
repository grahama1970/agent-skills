"""Session grading, self-grading loop, and QRA promotion for SPARTA conversations.

Handles Brandon's grading pipeline: semantic LLM grading, self-grading
improvement loop, QRA promotion for satisfactory answers, and episodic recall.
"""

from __future__ import annotations

import hashlib
import json
import sys
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from sparta_stress_test.models import (
    PI_MONO_SKILLS,
    SELF_GRADE_MAX_ITERATIONS,
    SELF_GRADE_TARGET_COMPOSITE,
    SHADOW_JSONL_PATH,
    SessionGrade,
    StressSession,
)
from sparta_stress_test.prompts import BRANDON_SESSION_GRADE
from sparta_stress_test.retrieval import (
    _call_scillm,
    _extract_entity_ids,
    _get_db,
    _validate_entities_with_parents,
    _HAS_QUALITY_UTILS,
)

# Episodic recall for self-grading loop
try:
    from graph_memory.agent import recall as _episodic_recall
    _HAS_EPISODIC = True
except ImportError:
    _HAS_EPISODIC = False

# /assistant cascade (Tier 0 → 0.5 → 2 GPT rationale)
try:
    _assistant_path = str(PI_MONO_SKILLS / "assistant")
    if _assistant_path not in sys.path:
        sys.path.insert(0, _assistant_path)
    from assistant import classify as _assistant_classify
    _HAS_ASSISTANT = True
except ImportError:
    _HAS_ASSISTANT = False

# QRA bridge for promotion
try:
    from graph_memory.qra_bridge import QRABridge
    _HAS_QRA_BRIDGE = True
except ImportError:
    _HAS_QRA_BRIDGE = False

# Bridge extraction for QRA promotion
try:
    from graph_memory.lessons.store import extract_bridges_fast
    _HAS_BRIDGES = True
except ImportError:
    _HAS_BRIDGES = False


# --------------------------------------------------------------------------- #
# Shadow-LEGO entry logging
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
    """Log a Brandon decision to shadow.jsonl for /assistant classifier training.

    Every clarify vs answer decision gets recorded with taxonomy bridges.
    The /assistant cascade already reads shadow.jsonl — richer entries mean
    better Tier 0 classifiers.
    """
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


# --------------------------------------------------------------------------- #
# Persona follow-up evaluation (Turn 3)
# --------------------------------------------------------------------------- #


def _persona_evaluate(
    persona: str,
    original_question: str,
    sparta_answer: str,
    adversarial: bool = False,
) -> Dict:
    """Have the persona evaluate SPARTA's answer and generate follow-up.

    Returns dict with: evaluation, follow_up, reasoning
    """
    from sparta_stress_test.prompts import MARGARET_FOLLOWUP, JENNIFER_FOLLOWUP

    system = MARGARET_FOLLOWUP if "Margaret" in persona else JENNIFER_FOLLOWUP

    user_prompt = f"""YOUR ORIGINAL QUESTION:
{original_question}

SPARTA'S ANSWER:
{sparta_answer}

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
    This function only exists as a fallback when Brandon LLM grading fails,
    and returns an explicit 'ungraded' marker so results are not confused
    with real grades.
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


def _grade_session_brandon(session: StressSession) -> SessionGrade:
    """Tier 2 Brandon grading via /scillm for full session."""
    # Build readable transcript
    transcript_lines = []
    for turn in session.turns:
        speaker = turn.speaker
        transcript_lines.append(f"[Turn {turn.turn_number}] {speaker}: {turn.content}")
    transcript_text = "\n\n".join(transcript_lines)

    seed = session.seed_question

    # Collect QRA source_keys from all turns for ground truth verification
    all_source_keys = []
    for turn in session.turns:
        turn_keys = turn.metadata.get("source_keys", [])
        all_source_keys.extend(turn_keys)

    # Fetch QRA ground truth for Brandon to verify citations
    qra_ground_truth_text = ""
    if all_source_keys:
        try:
            from sparta_stress_test.semantic_grader import _build_qra_ground_truth
            qra_ground_truth_text = _build_qra_ground_truth(all_source_keys[:5])
        except Exception as e:
            logger.debug(f"QRA ground truth fetch failed for Brandon: {e}")
            qra_ground_truth_text = "(unavailable)"
    else:
        qra_ground_truth_text = "(No QRA source keys recorded in session turns)"

    prompt = BRANDON_SESSION_GRADE.format(
        persona=session.persona,
        transcript=transcript_text,
        difficulty=seed.get("difficulty", "medium"),
        expected_action=seed.get("expected_action", "QUERY"),
        target_control=seed.get("target_control", "N/A"),
        adversarial=session.adversarial,
        qra_ground_truth=qra_ground_truth_text,
    )

    raw = _call_scillm(
        system="You are Brandon Bailey, Principal Director of Cyber Assessments at The Aerospace Corporation.",
        user_prompt=prompt,
        max_tokens=1024,
    )

    try:
        result = json.loads(raw)
        return SessionGrade(
            composite=float(result.get("composite", 0.0)),
            grade=result.get("grade", "F"),
            scores=result.get("scores", {}),
            tier=2,
            source="brandon_scillm",
            rationale=result.get("rationale", ""),
            reasoning_sound=result.get("reasoning_sound"),
            taxonomy_correct=result.get("taxonomy_correct"),
        )
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.warning(f"Brandon grading parse failed: {e}")
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
) -> dict:
    """Self-grade using semantic LLM (Qwen3) + QRA citation verification.

    BANNED: No keyword scanning, no word overlap heuristics.
    Grade comes from cross-model LLM with full context + QRA ground truth.
    /assistant classify still called for shadow logging (classifier learns to approximate).
    """
    from sparta_stress_test.semantic_grader import grade_response_semantic, STUDENT_MODEL

    # --- Deterministic hallucination check (pre-LLM) ---
    # Extract entity IDs from the ANSWER and validate against knowledge graph.
    # If the answer cites controls that don't exist, it's hallucination — no LLM needed.
    # GUARD: Skip when SPARTA collections are empty (no data to validate against).
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
                pass  # DB unavailable — skip deterministic check

    result = grade_response_semantic(
        question=question,
        answer=answer,
        transcript=transcript,
        qra_source_keys=qra_source_keys or [],
        target_control=target_control or "",
        difficulty=difficulty,
        expected_action=expected_action,
        model=STUDENT_MODEL,
    )

    # Override LLM grade if deterministic check found hallucinated entities
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

    # Shadow log via /assistant cascade so classifiers learn to approximate
    if use_gpt_rationale and _HAS_ASSISTANT and result.get("grade") not in ("A+", "A"):
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


def _recall_episodic_context(question: str, scope: str = "sparta") -> str:
    """Query episodic memory for similar past questions/responses.

    Returns a context string with prior answers that can inform re-retrieval.
    Uses graph_memory.agent.recall() for BM25 + graph fusion search.
    """
    if not _HAS_EPISODIC:
        return ""

    try:
        result = _episodic_recall(q=question, scope=scope, k=3, depth=1)
        items = result.get("items", [])
        if not items:
            return ""

        context_parts = []
        for item in items[:3]:
            title = item.get("title", "")
            solution = item.get("solution", item.get("content", ""))
            if solution:
                context_parts.append(
                    f"[Prior: {title}] {solution[:300]}"
                )

        if context_parts:
            context = "\n".join(context_parts)
            logger.debug(
                f"Episodic context: {len(context_parts)} prior answers "
                f"({len(context)} chars)"
            )
            return context
    except Exception as e:
        logger.debug(f"Episodic recall failed: {e}")

    return ""


def _self_grading_loop(
    question_text: str,
    target_control: Optional[str],
    seed_question: dict,
    initial_result: dict,
) -> tuple[dict, list[dict]]:
    """Self-grading improvement loop — iterate until predicted A+ or max iterations.

    Personas self-grade their response like a thoughtful human reviewing
    their own answer. If the predicted grade is below A, the system:
    1. Recalls similar past sessions from episodic memory
    2. Re-retrieves with excluded keys + episodic context
    3. Re-grades the improved response
    4. Repeats until A+ or max iterations

    Returns:
        (best_result, iteration_log) — the best SPARTA result and a log of iterations
    """
    from sparta_stress_test.retrieval import _sparta_answer

    difficulty = seed_question.get("difficulty", "medium")
    expected_action = seed_question.get("expected_action", "QUERY")

    # Build cumulative transcript from all turns
    transcript = f"Turn 1:\nQ: {question_text}\nA: {initial_result['answer_text']}"

    # Initial self-grade — semantic LLM with full context + QRA citations
    self_grade = _self_grade_response(
        question=question_text,
        answer=initial_result["answer_text"],
        qra_source_keys=initial_result.get("source_keys", []),
        transcript=transcript,
        target_control=target_control,
        qra_count=initial_result.get("qra_count", 0),
        difficulty=difficulty,
        expected_action=expected_action,
    )

    iteration_log = [{
        "iteration": 0,
        "grade": self_grade["grade"],
        "composite": self_grade["composite"],
        "issues": self_grade["issues"],
        "rationale": self_grade.get("rationale", ""),
        "qra_count": initial_result.get("qra_count", 0),
        "qra_citations_verified": self_grade.get("qra_citations_verified", 0),
        "qra_citations_total": self_grade.get("qra_citations_total", 0),
    }]

    best_result = initial_result
    best_composite = self_grade["composite"]
    final_result = initial_result  # Track the FINAL result (not best)
    final_grade = self_grade
    first_composite = self_grade["composite"]  # For delta tracking

    # Already A+ — no improvement needed
    if self_grade["composite"] >= SELF_GRADE_TARGET_COMPOSITE:
        logger.debug(
            f"Self-grade: {self_grade['grade']} ({self_grade['composite']:.0%}) "
            f"— accepted on first pass"
        )
        return best_result, iteration_log

    # Improvement loop
    all_exclude_keys = list(initial_result.get("source_keys", []))
    prev_composite = self_grade["composite"]
    stall_count = 0
    has_invalid_entities = bool(initial_result.get("invalid_entities"))

    for iteration in range(1, SELF_GRADE_MAX_ITERATIONS + 1):
        # Skip futile iterations when issue is unknown entities (unfixable by re-retrieval)
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

        # Step 1: Recall episodic context for similar past questions
        episodic_context = _recall_episodic_context(question_text)

        # Step 2: Build enriched question with episodic context + GPT rationale
        enriched_question = question_text
        # Include GPT rationale as retrieval guidance (what to fix)
        rationale = self_grade.get("rationale", "")
        if rationale:
            enriched_question += f"\n\n[Improvement guidance: {rationale[:200]}]"
        if episodic_context:
            enriched_question += f"\n\n[Context from similar prior answers:]\n{episodic_context[:500]}"

        # Step 3: Re-retrieve with excluded keys to force new QRA lanes
        retry_result = _sparta_answer(
            enriched_question,
            target_control=target_control,
            exclude_keys=all_exclude_keys,
            difficulty=difficulty,
            expected_action=expected_action,
        )

        # Append new turn to transcript
        transcript += f"\n\nTurn {iteration + 1}:\nQ: {question_text}\nA: {retry_result['answer_text']}"

        # Step 4: Self-grade the new response — semantic LLM with full transcript
        new_grade = _self_grade_response(
            question=question_text,  # Grade against original question, not enriched
            answer=retry_result["answer_text"],
            qra_source_keys=retry_result.get("source_keys", []),
            transcript=transcript,
            target_control=target_control,
            qra_count=retry_result.get("qra_count", 0),
            difficulty=difficulty,
            expected_action=expected_action,
        )

        iteration_log.append({
            "iteration": iteration,
            "grade": new_grade["grade"],
            "composite": new_grade["composite"],
            "issues": new_grade["issues"],
            "rationale": new_grade.get("rationale", ""),
            "qra_count": retry_result.get("qra_count", 0),
            "qra_citations_verified": new_grade.get("qra_citations_verified", 0),
            "qra_citations_total": new_grade.get("qra_citations_total", 0),
            "had_episodic_context": bool(episodic_context),
            "had_gpt_rationale": bool(rationale),
        })

        # Track excluded keys across iterations
        all_exclude_keys.extend(retry_result.get("source_keys", []))

        # Track best result (for reference) and final result (for grading)
        final_result = retry_result
        final_grade = new_grade
        if new_grade["composite"] > best_composite:
            best_result = retry_result
            best_composite = new_grade["composite"]
            self_grade = new_grade
            stall_count = 0
        else:
            stall_count += 1

        # Check if we've reached the target
        if new_grade["composite"] >= SELF_GRADE_TARGET_COMPOSITE:
            logger.debug(
                f"Self-grade: {new_grade['grade']} ({new_grade['composite']:.0%}) "
                f"— accepted after {iteration} iteration(s)"
            )
            break

        # If a retry returned CLARIFY, keep best prior answer and stop
        if retry_result.get("action") == "CLARIFY":
            logger.debug(
                f"Self-grade: retry returned CLARIFY — keeping best prior answer "
                f"({best_composite:.0%})"
            )
            break

        # Early break if stalled (no improvement for 2 consecutive iterations)
        if stall_count >= 2:
            logger.debug(
                f"Self-grade: stalled at {self_grade['grade']} ({best_composite:.0%}) "
                f"after {iteration} iterations — no improvement, accepting best"
            )
            break

    # Attach delta and iteration metadata to the final log
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

    # Return FINAL result (not best) — regression must be visible
    return final_result, iteration_log


# --------------------------------------------------------------------------- #
# QRA Promotion (satisfactory answer → new sparta_qra)
# --------------------------------------------------------------------------- #


def _check_promotion_eligible(
    session: Any,
    sparta_result: Dict,
    evaluation: str,
    final_composite: float,
) -> bool:
    """Check if a synthesized answer should be promoted to a new sparta_qra."""
    # Must be satisfactory or flaw caught
    if evaluation not in ("satisfactory", "flaw_caught"):
        return False
    # Must meet quality threshold
    if final_composite < 0.85:
        return False
    # Must be a synthesis (steering or graph-inferred), not pre-existing QRA
    answer = sparta_result.get("answer_text", "")
    is_synthesis = (
        sparta_result.get("steering")
        or "[GRAPH-INFERRED]" in answer
        or sparta_result.get("_source") == "multi_turn_conversation"
    )
    if not is_synthesis:
        return False
    # Must not be a bare guess with zero grounding
    if "[NOT IN CORPUS]" in answer and sparta_result.get("qra_count", 0) == 0:
        return False
    return True


def _promote_to_qra(
    question: str,
    answer: str,
    entities: List[str],
    session_id: str,
    persona: str,
    composite: float,
    turn_num: int = 0,
) -> Optional[str]:
    """Promote a satisfactory synthesized answer to a new sparta_qra.

    Returns the QRA key if promoted, None if failed.
    """
    if not _HAS_QRA_BRIDGE:
        logger.debug("QRABridge not available — skipping promotion")
        return None

    try:
        db = _get_db()
        bridge = QRABridge(db)

        target_control = entities[0] if entities else ""
        query_hash = hashlib.md5(question.encode()).hexdigest()[:12]
        synth_hash = hashlib.md5(f"{question}{answer}".encode()).hexdigest()[:12]

        # Extract bridge tags if available
        bridge_tags = []
        conceptual_tags = []
        tactical_tags = []
        if _HAS_BRIDGES:
            try:
                bridges = extract_bridges_fast(f"{question} {answer}")
                bridge_tags = bridges if isinstance(bridges, list) else list(bridges.keys()) if isinstance(bridges, dict) else []
            except Exception:
                pass

        # Try /taxonomy extract via subprocess for full tags (non-blocking)
        try:
            tax_result = subprocess.run(
                [
                    sys.executable, "-m", "graph_memory.agent_cli",
                    "taxonomy-extract",
                    "--text", f"{question} {answer}"[:500],
                    "--vocabulary", "sparta",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if tax_result.returncode == 0:
                tax_data = json.loads(tax_result.stdout)
                conceptual_tags = tax_data.get("conceptual_tags", [])
                tactical_tags = tax_data.get("tactical_tags", [])
        except Exception:
            pass

        qra_doc = {
            "_key": f"qra__persona-conv__{synth_hash}",
            "qra_id": f"synth_persona_{query_hash}",
            "run_id": "persona-conversation",
            "control_id": target_control,
            "question": question,
            "answer": answer,
            "reasoning": (
                f"Promoted from conversation {session_id}, turn {turn_num}. "
                f"Persona '{persona}' evaluated 'satisfactory' (composite={composite:.2f})."
            ),
            "grounding_score": composite,
            "conceptual_tags": conceptual_tags,
            "tactical_tags": tactical_tags,
            "bridge_attributes": bridge_tags,
            "_source": "persona_conversation_promotion",
            "_scope": "sparta",
            "created_at": time.time(),
        }

        # Quality gate: assess_qra() routes PASS/WARN/FAIL
        try:
            from graph_memory.quality.assess import assess_qra
            assessment = assess_qra(qra_doc)
        except ImportError:
            assessment = {"grade": "PASS", "notes": ["assess_qra not available"]}

        if assessment["grade"] == "FAIL":
            try:
                from graph_memory.candidate_bridge import CandidateBridge
                CandidateBridge(db).log_rejected(qra_doc, assessment)
            except Exception:
                pass
            logger.info(
                f"Rejected QRA for {target_control} (grade=FAIL, "
                f"notes={assessment.get('notes', [])})"
            )
            return None
        elif assessment["grade"] == "WARN":
            try:
                from graph_memory.candidate_bridge import CandidateBridge
                CandidateBridge(db).stage(qra_doc, assessment)
            except Exception as stage_err:
                logger.debug(f"Failed to stage WARN candidate: {stage_err}")
            logger.info(
                f"Staged QRA {qra_doc['_key']} for review (grade=WARN, "
                f"notes={assessment.get('notes', [])})"
            )
            return f"staged:{qra_doc['_key']}"
        else:  # PASS
            bridge.upsert_qra(qra_doc)
            logger.info(
                f"Promoted QRA {qra_doc['_key']} for {target_control} "
                f"(composite={composite:.2f}, session={session_id})"
            )
            return qra_doc["_key"]

    except Exception as e:
        logger.warning(f"QRA promotion failed: {e}")
        return None
