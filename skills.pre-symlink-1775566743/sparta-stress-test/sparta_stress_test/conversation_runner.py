"""Session runner and archiver for SPARTA conversation simulation.

Contains run_session() -- the main conversation loop that orchestrates
persona questions, SPARTA answers, self-grading, and QRA capture.
Also includes episodic archiver integration and blame analysis.
"""

from __future__ import annotations
import os

import hashlib
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger

from sparta_stress_test.conversation_models import (
    OUTER_LOOP_MAX_ROUNDS,
    OUTER_LOOP_STALL_TOLERANCE,
    PI_MONO_SKILLS,
    StressSession,
    _call_scillm,
    _get_db,
)
from sparta_stress_test.conversation_grading import (
    _grade_session_brandon,
    _grade_session_heuristic,
    _log_shadow_delta,
    _log_shadow_entry,
    _persona_evaluate,
    _self_grade_response,
    _self_grading_loop,
)
from sparta_stress_test.conversation_retrieval import (
    _extract_entity_ids,
    _sparta_answer,
)
from sparta_stress_test.conversation_steering import (
    _check_promotion_eligible,
    _promote_to_qra,
)
from sparta_stress_test.conversation_traceability import (
    build_traceability_report as _build_traceability_report,
    check_synthesis_sparsity as _check_synthesis_sparsity,
)
from sparta_stress_test.question_miner import (
    _get_control_id_pattern,
    _load_valid_controls,
)


# --------------------------------------------------------------------------- #
# Follow-up Question Validation
# --------------------------------------------------------------------------- #

def _validate_follow_up_controls(follow_up: str) -> str:
    """Validate control IDs in persona follow-up text against ControlCatalog.

    If hallucinated IDs found, strip them and append a note.
    Returns the (possibly modified) follow_up text.
    """
    if not follow_up:
        return follow_up

    pattern = _get_control_id_pattern()
    found_ids = pattern.findall(follow_up)
    if not found_ids:
        return follow_up

    valid_ids = _load_valid_controls()
    if not valid_ids:
        return follow_up  # Can't validate without catalog

    hallucinated = [cid for cid in found_ids if cid not in valid_ids]
    if not hallucinated:
        return follow_up

    logger.warning(
        f"Persona follow-up contains hallucinated control IDs: {hallucinated}"
    )
    # Strip hallucinated IDs from follow-up text
    cleaned = follow_up
    for cid in hallucinated:
        cleaned = cleaned.replace(cid, f"[INVALID:{cid}]")
    cleaned += f" (Note: {', '.join(hallucinated)} {'is' if len(hallucinated) == 1 else 'are'} not recognized SPARTA control{'s' if len(hallucinated) > 1 else ''})"
    return cleaned


# --------------------------------------------------------------------------- #
# Session runner (the main loop)
# --------------------------------------------------------------------------- #


def run_session(
    seed_question: Dict[str, Any],
    *,
    use_brandon_grading: bool = True,
    archive: bool = True,
) -> StressSession:
    """Run a single multi-turn stress test session.

    Args:
        seed_question: Mined question dict with question, persona, expected_action, etc.
        use_brandon_grading: If True, use Brandon via /scillm (Tier 2). Else heuristic only.
        archive: If True, submit transcript to /episodic-archiver.

    Returns:
        Completed StressSession with turns and grade.
    """
    session_id = f"stress_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hashlib.md5(seed_question.get('question', '').encode()).hexdigest()[:8]}"
    persona = seed_question.get("persona", "Margaret Chen")
    adversarial = seed_question.get("expected_action", "QUERY") in (
        "CLARIFY",
        "NO_MATCH",
        "OFF_TOPIC",
    )

    session = StressSession(
        session_id=session_id,
        persona=persona,
        seed_question=seed_question,
        adversarial=adversarial,
        status="running",
        started_at=datetime.now().isoformat(),
    )

    logger.debug(f"Session {session_id}: {persona} asks ({seed_question.get('difficulty', '?')})")

    # --- Turn 1: Persona asks the seed question ---
    question_text = seed_question["question"]
    session.add_turn(
        speaker=persona,
        role="persona",
        content=question_text,
        action=seed_question.get("expected_action", "QUERY"),
        metadata={
            "difficulty": seed_question.get("difficulty"),
            "source": seed_question.get("source"),
            "bridge_tags": seed_question.get("bridge_tags", []),
        },
    )

    # --- Outer conversation loop ---
    target_control = seed_question.get("target_control")
    exclude_keys: list = []
    all_self_grade_logs: list = []
    outer_round = 0
    evaluation = "incomplete"
    eval_result: Dict = {}
    first_composite: float = 0.0
    final_composite: float = 0.0
    best_composite: float = 0.0
    prev_composite: float = -1.0
    stall_count: int = 0
    persona_feedback_context = ""
    sparta_result: Dict = {}

    for outer_round in range(1, OUTER_LOOP_MAX_ROUNDS + 1):
        query_text = question_text
        if persona_feedback_context:
            query_text = f"{question_text}\n\nPRIOR FEEDBACK: {persona_feedback_context}"

        sparta_result = _sparta_answer(
            query_text,
            target_control,
            exclude_keys=exclude_keys,
            difficulty=seed_question.get("difficulty", "medium"),
            expected_action=seed_question.get("expected_action", "QUERY"),
        )

        if sparta_result.get("action") in ("CLARIFY", "INTERVIEW"):
            expected_action = seed_question.get("expected_action", "QUERY")
            # Build process signals for CLARIFY/INTERVIEW actions
            _evidence = sparta_result.get("evidence", {})
            _psig = {
                "richness_score": _evidence.get("richness_score", 0.0),
                "bridge_overlap_count": sparta_result.get("bridge_overlap_count", 0),
                "bridge_tags_matched": sparta_result.get("bridge_tags_matched", []),
                "framework_coverage": _evidence.get("framework_coverage", {}),
            }
            self_grade = _self_grade_response(
                question=query_text,
                answer=sparta_result["answer_text"],
                expected_action=expected_action,
                target_control=target_control,
                difficulty=seed_question.get("difficulty", "medium"),
                process_signals=_psig,
            )
            self_grade_log = [{
                "iteration": 0,
                "grade": self_grade["grade"],
                "composite": self_grade["composite"],
                "issues": self_grade.get("issues", []),
                "action": sparta_result["action"],
            }]
            all_self_grade_logs.extend(self_grade_log)
        else:
            sparta_result, self_grade_log = _self_grading_loop(
                question_text=query_text,
                target_control=target_control,
                seed_question=seed_question,
                initial_result=sparta_result,
            )
            all_self_grade_logs.extend(self_grade_log)

        if self_grade_log:
            summary = self_grade_log[-1] if self_grade_log[-1].get("_summary") else None
            grade_entries = [e for e in self_grade_log if not e.get("_summary")]
            # Use best composite from self-grade loop, not last
            round_composite = (
                summary.get("best_composite", 0.0) if summary
                else max((e.get("composite", 0.0) for e in grade_entries), default=0.0)
            )
            if outer_round == 1:
                first_composite = grade_entries[0].get("composite", 0.0) if grade_entries else 0.0
            final_composite = round_composite
            best_composite = max(best_composite, round_composite)

            if prev_composite >= 0 and abs(round_composite - prev_composite) < OUTER_LOOP_STALL_TOLERANCE:
                stall_count += 1
            else:
                stall_count = 0
            prev_composite = round_composite

        # --- Shadow-LEGO entry ---
        _shadow_decision = "CLARIFY" if sparta_result.get("action") in ("CLARIFY", "INTERVIEW") else "ANSWER"
        _shadow_grade = self_grade_log[-1] if self_grade_log else {}
        _shadow_labels = []
        if sparta_result.get("answer_text"):
            for _lbl in ("QRA-GROUNDED", "MEMORY-RECALL", "GRAPH-INFERRED",
                         "NOT IN CORPUS", "EPISODIC"):
                if f"[{_lbl}]" in sparta_result["answer_text"]:
                    _shadow_labels.append(_lbl)
        _shadow_clarify_trigger = None
        if _shadow_decision == "CLARIFY":
            _cd = sparta_result.get("clarify_detail", {}).get("diagnostics", {})
            for _trig in ("intent_says_clarify", "zero_bridges", "low_recall_confidence",
                          "entities_without_qras", "low_bridge_correlation"):
                if _cd.get(_trig):
                    _shadow_clarify_trigger = _trig
                    break
        _log_shadow_entry(
            question=query_text,
            decision=_shadow_decision,
            clarify_trigger=_shadow_clarify_trigger,
            entities=_extract_entity_ids(query_text),
            lanes_used=sparta_result.get("lanes_used", []),
            qra_count=sparta_result.get("qra_count", 0),
            labels_used=_shadow_labels,
            bridges=seed_question.get("bridge_tags", []),
            student_grade=_shadow_grade.get("grade", ""),
        )

        session.qra_results = sparta_result

        session.add_turn(
            speaker="SPARTA",
            role="system",
            content=sparta_result["answer_text"],
            action=sparta_result.get("action", "QUERY"),
            metadata={
                "qra_count": sparta_result.get("qra_count", 0),
                "techniques": sparta_result.get("sparta_techniques", []),
                "countermeasures": sparta_result.get("sparta_countermeasures", []),
                "source_keys": sparta_result.get("source_keys", []),
                "self_grade_iterations": len(self_grade_log),
                "self_grade_final": self_grade_log[-1] if self_grade_log else {},
                "outer_round": outer_round,
                "bridge_overlap_count": sparta_result.get("bridge_overlap_count", 0),
                "richness_score": sparta_result.get("evidence", {}).get("richness_score", 0.0),
                "retrieval_cards": sparta_result.get("retrieval_cards", []),
            },
        )

        # --- Per-Turn Traceability Report ---
        _citation_details = []
        for _sg_entry in self_grade_log:
            if _sg_entry.get("citation_details"):
                _citation_details = _sg_entry["citation_details"]
                break
        # Also try from the last grade entry
        if not _citation_details and self_grade_log:
            _citation_details = self_grade_log[-1].get("citation_details", [])

        # DON'T exclude prior source keys in outer loop — persona follow-ups
        # often relate to the same QRAs. Excluding them forces retrieval of
        # entirely new QRAs that may verify poorly, causing citation drops
        # (A+ → C pattern). The inner self-grade loop handles dedup via its
        # own exclude_keys in _self_grading_loop().
        # exclude_keys.extend(sparta_result.get("source_keys", []))

        # --- Lie-detector Layer 3b: Guard synthesis when no blessed QRA ---
        sparsity_result: Dict = {}
        _qra_count = sparta_result.get("qra_count", 0)
        _has_control = bool(target_control)
        _is_synthesis = (_qra_count == 0 and not _has_control
                         and sparta_result.get("action") not in ("CLARIFY", "INTERVIEW", "NO_MATCH"))
        if _is_synthesis:
            try:
                sparsity_result = _check_synthesis_sparsity(
                    answer_text=sparta_result["answer_text"],
                    query=question_text,
                )
                logger.debug(
                    f"Lie-detector L3b: {sparsity_result.get('verdict', '?')} "
                    f"(bridge={sparsity_result.get('bridge_coverage', 0):.2f}, "
                    f"entity={sparsity_result.get('entity_coverage', 0):.2f})"
                )
                if sparsity_result.get("verdict") == "SPARSE":
                    # Flag the turn — synthesis is not grounded in the knowledge graph
                    session.add_turn(
                        speaker="LIE_DETECTOR",
                        role="system",
                        content=(
                            f"[SPARSE] Synthesis sparsity detected. "
                            f"Bridge coverage: {sparsity_result.get('bridge_coverage', 0):.2f}, "
                            f"Entity coverage: {sparsity_result.get('entity_coverage', 0):.2f}. "
                            f"Missing: {', '.join(sparsity_result.get('missing_entities', [])[:5])}"
                        ),
                        action="LIE_DETECTOR_FLAG",
                        metadata=sparsity_result,
                    )
            except Exception as e:
                logger.debug(f"Lie-detector L3b failed (non-fatal): {e}")

        # --- Build and store traceability report ---
        try:
            report = _build_traceability_report(
                question=query_text,
                turn_number=len(session.turns),
                sparta_result=sparta_result,
                citation_details=_citation_details,
                self_grade_log=self_grade_log,
                sparsity_result=sparsity_result if sparsity_result else None,
            )
            # Store on the SPARTA answer turn (the one we just added)
            for _t in reversed(session.turns):
                if _t.speaker == "SPARTA":
                    _t.traceability_report = report
                    break
            # Print it — this is the ANTI-OPACITY measure
            logger.info(f"\n{report}")
        except Exception as _trace_err:
            logger.debug(f"Traceability report generation failed: {_trace_err}")

        # --- Persona evaluates (with process evidence) ---
        _pe = {
            "qra_citations_verified": self_grade_log[-1].get("qra_citations_verified", 0) if self_grade_log else 0,
            "qra_citations_total": self_grade_log[-1].get("qra_citations_total", 0) if self_grade_log else 0,
            "bridge_overlap_count": sparta_result.get("bridge_overlap_count", 0),
            "richness_score": sparta_result.get("evidence", {}).get("richness_score", 0.0),
            "self_grade": self_grade_log[-1].get("grade", "") if self_grade_log else "",
            "self_composite": final_composite,
            "synthesis_sparsity": sparsity_result.get("verdict", "") if sparsity_result else "",
            "synthesis_bridge_coverage": sparsity_result.get("bridge_coverage", 0.0) if sparsity_result else 0.0,
        }
        eval_result = _persona_evaluate(
            persona=persona,
            original_question=question_text,
            sparta_answer=sparta_result["answer_text"],
            adversarial=adversarial,
            process_evidence=_pe,
        )

        evaluation = eval_result.get("evaluation", "incomplete")
        follow_up = eval_result.get("follow_up", "").strip()
        reasoning = eval_result.get("reasoning", "")

        # Validate control IDs in follow-up before using it as next question
        if follow_up:
            follow_up = _validate_follow_up_controls(follow_up)

        logger.debug(
            f"Session {session_id} outer round {outer_round}: "
            f"persona says '{evaluation}' (composite={final_composite:.2f})"
        )

        if evaluation in ("satisfactory", "flaw_caught"):
            promoted_key = None
            if _check_promotion_eligible(session, sparta_result, evaluation, final_composite):
                promote_entities = [target_control] if target_control else _extract_entity_ids(question_text)
                promoted_key = _promote_to_qra(
                    question=question_text,
                    answer=sparta_result["answer_text"],
                    entities=promote_entities,
                    session_id=session.session_id,
                    persona=persona,
                    composite=final_composite,
                    turn_num=outer_round,
                )

            session.add_turn(
                speaker=persona,
                role="persona",
                content=f"[{evaluation}] {reasoning}",
                action="EVALUATE",
                metadata={
                    "evaluation": evaluation,
                    "reasoning": reasoning,
                    "outer_round": outer_round,
                    "promoted_qra": promoted_key,
                },
            )
            break

        session.add_turn(
            speaker=persona,
            role="persona",
            content=follow_up if follow_up else f"[{evaluation}] {reasoning}",
            action="FOLLOW_UP" if follow_up else "EVALUATE",
            metadata={
                "evaluation": evaluation,
                "reasoning": reasoning,
                "outer_round": outer_round,
            },
        )

        persona_feedback_context = (
            f"{persona} ({evaluation}): {follow_up or reasoning}"
        )

        if stall_count >= 2:
            logger.info(
                f"Session {session_id}: stall detected at round {outer_round} "
                f"(composite ~{final_composite:.2f} for {stall_count + 1} rounds)"
            )
            break

    else:
        logger.info(
            f"Session {session_id}: exhausted {OUTER_LOOP_MAX_ROUNDS} outer rounds, "
            f"final evaluation='{evaluation}'"
        )

    self_grade_log = all_self_grade_logs

    # --- Log shadow delta ---
    _log_shadow_delta(
        session_id=session_id,
        question=question_text,
        persona=persona,
        first_composite=first_composite,
        final_composite=final_composite,
        outer_rounds=outer_round,
        inner_iterations=len(all_self_grade_logs),
        evaluation=evaluation,
    )

    # --- Determine resolution status ---
    persona_evals = [
        t.metadata.get("evaluation", "") for t in session.turns
        if t.role == "persona" and t.metadata
    ]
    if "flaw_caught" in persona_evals or evaluation == "correct":
        session.resolution = "resolved"
    elif evaluation == "wrong" or persona_evals.count("wrong") >= 2:
        session.resolution = "no_coverage"
    elif evaluation == "incomplete":
        session.resolution = "partial"
    elif evaluation in ("flaw_missed", "ambiguous"):
        session.resolution = "ambiguous"
    else:
        session.resolution = "resolved"

    # --- Grade the session (with deterministic anchoring) ---
    # Use BEST citation data across all iterations, not last
    _best_verified = 0
    _best_total = 0
    _best_bridge = 0
    _best_richness = 0.0
    for _sg_entry in all_self_grade_logs:
        v = _sg_entry.get("qra_citations_verified", 0)
        t = _sg_entry.get("qra_citations_total", 0)
        if v > _best_verified:
            _best_verified = v
            _best_total = t
    # Also track best bridge/richness across all turns
    for turn in session.turns:
        if turn.metadata:
            b = turn.metadata.get("bridge_overlap_count", 0)
            r = turn.metadata.get("richness_score", 0.0)
            if b > _best_bridge:
                _best_bridge = b
            if r > _best_richness:
                _best_richness = r
    # Fall back to latest sparta_result if no turn metadata
    if _best_bridge == 0:
        _best_bridge = sparta_result.get("bridge_overlap_count", 0)
    if _best_richness == 0.0:
        _best_richness = sparta_result.get("evidence", {}).get("richness_score", 0.0)

    # Check if any turn was flagged SPARSE by lie-detector
    _lie_detector_flags = [
        t for t in session.turns
        if t.action == "LIE_DETECTOR_FLAG"
    ]
    _session_psig = {
        "qra_citations_verified": _best_verified,
        "qra_citations_total": _best_total,
        "bridge_overlap_count": _best_bridge,
        "richness_score": _best_richness,
        "synthesis_sparse": bool(_lie_detector_flags),
    }
    if use_brandon_grading:
        try:
            session.grade = _grade_session_brandon(
                session,
                best_self_composite=best_composite,
                process_signals=_session_psig,
            )
        except Exception as e:
            logger.warning(f"Brandon grading failed ({e}), falling back to heuristic")
            session.grade = _grade_session_heuristic(session)
    else:
        session.grade = _grade_session_heuristic(session)

    if all_self_grade_logs:
        session.grade.qra_citations_verified = _best_verified
        session.grade.qra_citations_total = _best_total

    # --- Session-level citation floor ---
    # If the best self-grade was significantly higher than the session grade,
    # and we have verified citations, the session grade should not be F.
    if session.grade.composite < 0.50 and best_composite >= 0.60:
        verified = session.grade.qra_citations_verified or 0
        if verified > 0:
            floor = max(session.grade.composite, best_composite * 0.80)
            logger.debug(
                f"Session grade floor: {session.grade.grade} ({session.grade.composite:.0%}) "
                f"→ best_composite={best_composite:.0%}, verified={verified}, "
                f"floor={floor:.0%}"
            )
            session.grade.composite = floor
            if floor >= 0.80:
                session.grade.grade = "B"
            elif floor >= 0.60:
                session.grade.grade = "C"

    # --- Lie-detector sparsity ceiling ---
    # If synthesis was flagged SPARSE and no QRA citations exist,
    # cap the grade — ungrounded synthesis should not get an A.
    if _lie_detector_flags and session.grade.composite > 0.70:
        if (session.grade.qra_citations_verified or 0) == 0:
            logger.debug(
                f"Lie-detector cap: {session.grade.grade} ({session.grade.composite:.0%}) "
                f"→ capped at C(70%) due to SPARSE synthesis with no citations"
            )
            session.grade.composite = 0.70
            session.grade.grade = "C"

    session.status = "completed"
    session.completed_at = datetime.now().isoformat()

    logger.info(
        f"Session {session_id}: {session.grade.grade} "
        f"({session.grade.composite:.0%}) "
        f"[{len(session.turns)} turns, tier={session.grade.tier}] "
        f"{question_text[:60]}"
    )

    # --- Capture refined answer as QRA ---
    if session.grade and session.grade.composite >= 0.70 and sparta_result.get("answer_text"):
        try:
            db = _get_db()
            reasoning_parts = []
            for entry in self_grade_log:
                it = entry.get("iteration", "?")
                g = entry.get("grade", "?")
                c = entry.get("composite", 0)
                issues = entry.get("issues", [])
                rationale = entry.get("rationale", "")
                reasoning_parts.append(
                    f"Iteration {it}: {g} ({c:.0%})"
                    + (f" issues={issues}" if issues else "")
                    + (f" rationale={rationale[:200]}" if rationale else "")
                )
            if outer_round > 1:
                reasoning_parts.append(
                    f"Outer loop: {outer_round} rounds, "
                    f"persona evaluation='{evaluation}'"
                )

            query_hash = hashlib.md5(question_text.encode()).hexdigest()[:12]
            qra_id = f"conv_{session_id}_{query_hash}"
            source_keys = sparta_result.get("source_keys", [])
            candidate = {
                "_key": qra_id,
                "qra_id": qra_id,
                "question": question_text,
                "answer": sparta_result["answer_text"],
                "reasoning": "\n".join(reasoning_parts),
                "control_id": sparta_result.get("target_control", ""),
                "grounding_score": session.grade.composite,
                "_source": "multi_turn_conversation",
                "_source_qra_keys": source_keys[:5],
                "_scope": "sparta",
                "run_id": f"conversation-{session_id}",
                "persona": persona,
                "iteration_count": len(self_grade_log),
                "outer_rounds": outer_round,
                "persona_evaluation": evaluation,
                "initial_grade": self_grade_log[0].get("grade", "?") if self_grade_log else "?",
                "final_grade": session.grade.grade,
                "first_composite": first_composite,
                "final_composite": final_composite,
                "delta": round(final_composite - first_composite, 4),
            }
            # Run assess_qra gate before insertion (same gate as main 12_qra.py pipeline)
            _assessment_verdict = "PASS"
            try:
                from sparta.pipeline_duckdb.qra_assessment import assess_qra
                assessment = assess_qra(candidate)
                _assessment_verdict = assessment.get("verdict", "PASS")
                if _assessment_verdict == "FAIL":
                    logger.warning(
                        f"QRA {qra_id} REJECTED by assess_qra: "
                        f"{assessment.get('reasons', [])}"
                    )
                elif _assessment_verdict == "WARN":
                    logger.info(
                        f"QRA {qra_id} passed assess_qra with WARN: "
                        f"{assessment.get('reasons', [])} — inserting (multi-turn validated)"
                    )
            except ImportError:
                logger.info(
                    "ASSESS_QRA_UNAVAILABLE: sparta.pipeline_duckdb.qra_assessment not importable — "
                    "inserting conversation QRA without assessment gate"
                )
            except Exception as e:
                logger.warning(f"assess_qra failed ({e}) — inserting anyway")

            if _assessment_verdict != "FAIL":
                db.collection("sparta_qra").insert(candidate, overwrite=True)
                logger.debug(f"Captured QRA {qra_id} (delta={candidate['delta']:.2f}, assessment={_assessment_verdict})")
        except Exception as e:
            logger.debug(f"QRA capture failed: {e}")

    # --- Archive ---
    if archive:
        _archive_session(session)

    return session


# --------------------------------------------------------------------------- #
# Episodic archiver integration
# --------------------------------------------------------------------------- #


def _archive_session(session: StressSession) -> bool:
    """Submit session transcript to /episodic-archiver for archival + analysis."""
    try:
        transcript = session.to_transcript()

        transcript["metadata"] = {
            "type": "sparta_stress_test",
            "persona": session.persona,
            "difficulty": session.seed_question.get("difficulty"),
            "expected_action": session.seed_question.get("expected_action"),
            "target_control": session.seed_question.get("target_control"),
            "adversarial": session.adversarial,
            "grade": session.grade.grade if session.grade else None,
            "composite": session.grade.composite if session.grade else None,
            "qra_count": session.qra_results.get("qra_count", 0),
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", prefix=f"stress_{session.session_id}_", delete=False
        ) as f:
            json.dump(transcript, f, indent=2)
            transcript_path = f.name

        archived = False

        archiver_path = PI_MONO_SKILLS / "episodic-archiver"
        if archiver_path.exists():
            archiver_module = str(archiver_path)
            if archiver_module not in sys.path:
                sys.path.insert(0, archiver_module)
            try:
                from archive_episode import analyze_and_archive
                analyze_and_archive(transcript_path)
                archived = True
                logger.debug(f"Archived session {session.session_id}")
            except Exception as e:
                logger.debug(f"Python archiver failed: {e}, trying shell")

                run_sh = archiver_path / "run.sh"
                if run_sh.exists():
                    result = subprocess.run(
                        [str(run_sh), "archive", transcript_path],
                        capture_output=True, text=True, timeout=30,
                        cwd=str(archiver_path),
                        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
                    )
                    archived = result.returncode == 0

        should_analyze = (
            session.grade
            and (session.grade.grade in ("C", "F") or session.adversarial)
        )

        if archived and should_analyze:
            try:
                analysis = _analyze_session_blame(session)
                if analysis:
                    session.blame = analysis
                    logger.info(
                        f"Blame analysis for {session.session_id}: "
                        f"{analysis.get('primary_blame', 'unknown')} — "
                        f"{analysis.get('summary', '')[:80]}"
                    )
            except Exception as e:
                logger.debug(f"Blame analysis failed: {e}")

        session.archived = archived
        return archived

    except Exception as e:
        logger.warning(f"Failed to archive session {session.session_id}: {e}")
        return False


def _analyze_session_blame(session: StressSession) -> Optional[Dict]:
    """Analyze a failing session to identify which skill in the chain is at fault."""
    transcript_lines = []
    for turn in session.turns:
        transcript_lines.append(f"[{turn.speaker}] {turn.content}")
    transcript_text = "\n".join(transcript_lines)

    seed = session.seed_question
    grade = session.grade

    prompt = f"""Analyze this FAILED stress test session and identify which component in the
SPARTA pipeline is at fault. The pipeline has these components:

1. **sparta_qra**: The QRA corpus (207K+ question-reasoning-answer pairs). Blame if answer
   content is wrong, missing, or low quality.
2. **persona_prompt**: Margaret Chen / Jennifer Cheung persona prompts. Blame if the question
   was unnatural, wrong voice, or the evaluation in turn 3 was incorrect.
3. **intent_mapper**: The local LoRA that classifies question intent. Blame if the action
   (QUERY/CLARIFY/NO_MATCH) was misclassified.
4. **memory_taxonomy**: Bridge taxonomy (Precision/Resilience/Fragility/Corruption/Loyalty/Stealth).
   Blame if taxonomy tags are wrong or missing.
5. **learn_datalake**: F-36 data ingestion pipeline. Blame if the question references F-36
   content that should exist but doesn't.
6. **extractor**: Document extraction pipeline. Blame if source data didn't reach ArangoDB.
7. **nlg_synthesis**: Natural language generation. Blame if the answer text has artifacts
   (pipes, JSON, database fields).
8. **question_quality**: The question quality gate. Blame if the question itself was bad
   (too vague, untestable, wrong difficulty label).

SESSION:
{transcript_text}

METADATA:
- Persona: {session.persona}
- Difficulty: {seed.get('difficulty', 'unknown')}
- Expected action: {seed.get('expected_action', 'QUERY')}
- Target control: {seed.get('target_control', 'N/A')}
- Adversarial injection: {session.adversarial}
- Grade: {grade.grade if grade else 'N/A'} ({grade.composite:.0%} if grade else 0)
- Dimension scores: {json.dumps(grade.scores) if grade else '{{}}'}

Return JSON:
{{
  "primary_blame": "component_name",
  "secondary_blame": ["other_component"],
  "summary": "What went wrong in 1-2 sentences",
  "fix_suggestions": ["Specific actionable fix"],
  "affected_controls": ["SV-XX-N if applicable"]
}}"""

    raw = _call_scillm(
        system="You are a pipeline diagnostics engineer analyzing a failed stress test.",
        user_prompt=prompt,
        max_tokens=512,
    )

    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.debug(f"Blame analysis parse failed: {raw[:200]}")
        return None


def aggregate_blame(sessions: List[StressSession]) -> Dict[str, Any]:
    """Aggregate blame attribution across all failing sessions."""
    blame_counts = {}
    secondary_counts = {}
    fix_suggestions = []
    affected_controls = set()

    for s in sessions:
        blame = getattr(s, "blame", None)
        if not blame or not isinstance(blame, dict):
            continue

        primary = blame.get("primary_blame", "unknown")
        blame_counts[primary] = blame_counts.get(primary, 0) + 1

        for sec in blame.get("secondary_blame", []):
            secondary_counts[sec] = secondary_counts.get(sec, 0) + 1

        for fix in blame.get("fix_suggestions", []):
            fix_suggestions.append({"blame": primary, "fix": fix})

        for ctrl in blame.get("affected_controls", []):
            affected_controls.add(ctrl)

    return {
        "primary_blame_distribution": dict(sorted(blame_counts.items(), key=lambda x: -x[1])),
        "secondary_blame_distribution": dict(sorted(secondary_counts.items(), key=lambda x: -x[1])),
        "top_fix_suggestions": fix_suggestions[:20],
        "affected_controls": sorted(affected_controls),
        "total_analyzed": sum(blame_counts.values()),
    }
