"""Session runner, batch execution, archiver integration, and aggregation.

Contains the main run_session() and run_batch_sessions() entry points,
episodic archiver integration, blame analysis, and session aggregation.
"""

from __future__ import annotations
import os

import hashlib
import json
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from sparta_stress_test.models import (
    OUTER_LOOP_MAX_ROUNDS,
    OUTER_LOOP_STALL_TOLERANCE,
    OUTER_LOOP_TARGET,
    PI_MONO_SKILLS,
    SHADOW_DELTA_PATH,
    SESSIONS_DIR,
    StressSession,
)
from sparta_stress_test.retrieval import (
    _call_scillm,
    _extract_entity_ids,
    _get_db,
)
from sparta_stress_test.grading import (
    _check_promotion_eligible,
    _grade_session_brandon,
    _grade_session_heuristic,
    _log_shadow_entry,
    _persona_evaluate,
    _promote_to_qra,
    _self_grade_response,
    _self_grading_loop,
)
from sparta_stress_test.sparta_answer import _sparta_answer


# --------------------------------------------------------------------------- #
# Shadow-LEGO delta logging (training data for classifiers/GPTs/regressors)
# --------------------------------------------------------------------------- #


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
    """Log the improvement delta for Shadow-LEGO training.

    Each entry captures: how much did the self-grading loop improve the response?
    The delta (final - first) is the training signal for classifiers, GPTs, and
    regressors that learn which retrieval strategies produce the best improvement.
    """
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


# --------------------------------------------------------------------------- #
# Session runner (the main loop — like BattleOrchestrator.run_round)
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

    # --- Outer conversation loop: Brandon self-improves, persona gates ---
    target_control = seed_question.get("target_control")
    exclude_keys: list = []       # Accumulate used QRA keys across rounds
    all_self_grade_logs: list = []  # All inner-loop logs for shadow delta
    outer_round = 0
    evaluation = "incomplete"
    eval_result: Dict = {}
    first_composite: float = 0.0  # Shadow-LEGO: first self-grade composite
    final_composite: float = 0.0  # Shadow-LEGO: last self-grade composite
    prev_composite: float = -1.0  # Stall detection: previous round composite
    stall_count: int = 0          # Consecutive rounds with negligible delta
    persona_feedback_context = ""  # Accumulated persona feedback for re-retrieval

    for outer_round in range(1, OUTER_LOOP_MAX_ROUNDS + 1):
        # --- Brandon retrieves + inner self-grade loop ---
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

        # CLARIFY is a terminal response — grade directly, no iteration
        if sparta_result.get("action") in ("CLARIFY", "INTERVIEW"):
            expected_action = seed_question.get("expected_action", "QUERY")
            self_grade = _self_grade_response(
                question=query_text,
                answer=sparta_result["answer_text"],
                expected_action=expected_action,
                target_control=target_control,
                difficulty=seed_question.get("difficulty", "medium"),
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

        # Track shadow delta composites
        if self_grade_log:
            grade_entries = [e for e in self_grade_log if not e.get("_summary")]
            round_composite = grade_entries[-1].get("composite", 0.0) if grade_entries else 0.0
            if outer_round == 1:
                first_composite = grade_entries[0].get("composite", 0.0) if grade_entries else 0.0
            final_composite = round_composite

            # Stall detection
            if prev_composite >= 0 and abs(round_composite - prev_composite) < OUTER_LOOP_STALL_TOLERANCE:
                stall_count += 1
            else:
                stall_count = 0
            prev_composite = round_composite

        # --- Shadow-LEGO entry for this turn ---
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
            },
        )

        # Accumulate used keys so next round gets fresh QRAs
        exclude_keys.extend(sparta_result.get("source_keys", []))

        # --- Persona evaluates Brandon's answer ---
        eval_result = _persona_evaluate(
            persona=persona,
            original_question=question_text,
            sparta_answer=sparta_result["answer_text"],
            adversarial=adversarial,
        )

        evaluation = eval_result.get("evaluation", "incomplete")
        follow_up = eval_result.get("follow_up", "").strip()
        reasoning = eval_result.get("reasoning", "")

        logger.debug(
            f"Session {session_id} outer round {outer_round}: "
            f"persona says '{evaluation}' (composite={final_composite:.2f})"
        )

        # --- Persona satisfied or flaw caught -> conversation ends ---
        if evaluation in ("satisfactory", "flaw_caught"):
            # --- QRA Promotion ---
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

        # --- Persona not satisfied -> log feedback, cycle again ---
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

        # Accumulate persona feedback for next retrieval round
        persona_feedback_context = (
            f"{persona} ({evaluation}): {follow_up or reasoning}"
        )

        # Stall detection
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

    # Alias for downstream compatibility
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

    # --- Grade the session ---
    if use_brandon_grading:
        try:
            session.grade = _grade_session_brandon(session)
        except Exception as e:
            logger.warning(f"Brandon grading failed ({e}), falling back to heuristic")
            session.grade = _grade_session_heuristic(session)
    else:
        session.grade = _grade_session_heuristic(session)

    # Propagate citation metrics from self-grading into SessionGrade
    if all_self_grade_logs:
        final_sg = all_self_grade_logs[-1]
        session.grade.qra_citations_verified = final_sg.get("qra_citations_verified", 0)
        session.grade.qra_citations_total = final_sg.get("qra_citations_total", 0)

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
            db.collection("sparta_qra").insert(candidate, overwrite=True)
            logger.debug(f"Captured QRA {qra_id} (delta={candidate['delta']:.2f})")
        except Exception as e:
            logger.debug(f"QRA capture failed: {e}")

    # --- Archive to /episodic-archiver ---
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

        # Analyze failing sessions
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
                        f"{analysis.get('primary_blame', 'unknown')} -- "
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
{{{{
  "primary_blame": "component_name",
  "secondary_blame": ["other_component"],
  "summary": "What went wrong in 1-2 sentences",
  "fix_suggestions": ["Specific actionable fix"],
  "affected_controls": ["SV-XX-N if applicable"]
}}}}"""

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


# --------------------------------------------------------------------------- #
# Batch runner
# --------------------------------------------------------------------------- #


def run_batch_sessions(
    questions: List[Dict[str, Any]],
    *,
    use_brandon_grading: bool = True,
    archive: bool = True,
    verbose: bool = False,
) -> List[StressSession]:
    """Run a batch of conversation sessions."""
    sessions = []
    start = time.monotonic()

    for i, question in enumerate(questions):
        try:
            session = run_session(
                seed_question=question,
                use_brandon_grading=use_brandon_grading,
                archive=archive,
            )
            sessions.append(session)

            if verbose or (session.grade and session.grade.grade in ("C", "F")):
                g = session.grade
                logger.info(
                    f"[{i+1}/{len(questions)}] {g.grade} ({g.composite:.0%}) "
                    f"[{len(session.turns)}T] "
                    f"{session.persona[:8]} "
                    f"{question.get('question', '')[:50]}"
                )
            elif (i + 1) % 10 == 0:
                elapsed = time.monotonic() - start
                rate = (i + 1) / elapsed * 60
                logger.info(f"Progress: {i+1}/{len(questions)} ({rate:.0f} sessions/min)")

        except Exception as e:
            logger.error(f"Session {i+1} failed: {e}")
            continue

    elapsed = time.monotonic() - start
    logger.info(
        f"Batch complete: {len(sessions)}/{len(questions)} sessions "
        f"in {elapsed:.1f}s ({len(sessions)/elapsed*60:.0f}/min)"
    )

    return sessions


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #


def aggregate_sessions(sessions: List[StressSession]) -> Dict[str, Any]:
    """Aggregate session results into a summary report."""
    if not sessions:
        return {"total": 0}

    grades = {}
    by_persona = {}
    by_difficulty = {}
    by_evaluation = {}
    dimension_scores = {}
    archived_count = 0
    adversarial_count = 0
    turn_counts = []

    for s in sessions:
        if not s.grade:
            continue

        grade = s.grade.grade
        grades[grade] = grades.get(grade, 0) + 1
        turn_counts.append(len(s.turns))

        if s.archived:
            archived_count += 1
        if s.adversarial:
            adversarial_count += 1

        p = s.persona
        if p not in by_persona:
            by_persona[p] = {"total": 0, "composites": []}
        by_persona[p]["total"] += 1
        by_persona[p]["composites"].append(s.grade.composite)

        d = s.seed_question.get("difficulty", "unknown")
        if d not in by_difficulty:
            by_difficulty[d] = {"total": 0, "composites": []}
        by_difficulty[d]["total"] += 1
        by_difficulty[d]["composites"].append(s.grade.composite)

        for turn in s.turns:
            ev = turn.metadata.get("evaluation")
            if ev:
                by_evaluation[ev] = by_evaluation.get(ev, 0) + 1

        for dim, score in s.grade.scores.items():
            if dim not in dimension_scores:
                dimension_scores[dim] = []
            dimension_scores[dim].append(score)

    total = len(sessions)
    passing = sum(grades.get(g, 0) for g in ("A+", "A", "B"))

    for key in by_persona:
        cs = by_persona[key].pop("composites")
        by_persona[key]["avg_composite"] = round(sum(cs) / len(cs), 3) if cs else 0
    for key in by_difficulty:
        cs = by_difficulty[key].pop("composites")
        by_difficulty[key]["avg_composite"] = round(sum(cs) / len(cs), 3) if cs else 0

    dimension_avgs = {
        dim: round(sum(scores) / len(scores), 3)
        for dim, scores in dimension_scores.items()
    }

    return {
        "total": total,
        "overall_grades": grades,
        "pass_rate": round(passing / total, 3) if total > 0 else 0,
        "by_persona": by_persona,
        "by_difficulty": by_difficulty,
        "by_evaluation": by_evaluation,
        "dimension_averages": dimension_avgs,
        "avg_turns": round(sum(turn_counts) / len(turn_counts), 1),
        "archived_count": archived_count,
        "adversarial_count": adversarial_count,
    }


# --------------------------------------------------------------------------- #
# Save/Load
# --------------------------------------------------------------------------- #


def save_sessions(sessions: List[StressSession], output_path: Optional[Path] = None) -> Path:
    """Save sessions to JSONL."""
    if output_path is None:
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_path = SESSIONS_DIR / f"sessions_{timestamp}.jsonl"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for s in sessions:
            f.write(json.dumps(s.to_dict(), default=str) + "\n")

    logger.info(f"Saved {len(sessions)} sessions to {output_path}")
    return output_path
