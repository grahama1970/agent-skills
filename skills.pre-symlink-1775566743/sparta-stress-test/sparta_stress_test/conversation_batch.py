"""Batch runner, aggregation, and Shadow-LEGO post-run pipeline.

Contains run_batch_sessions(), aggregate_sessions(), the Shadow-LEGO
post-run pipeline (stratified sampling, LLM rating, shadow.jsonl),
and save/load utilities.
"""

from __future__ import annotations

import json
import math
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from sparta_stress_test.conversation_models import (
    MIN_STRATIFIED_SAMPLE,
    PI_MONO_SKILLS,
    SESSIONS_DIR,
    SHADOW_DELTA_PATH,
    SHADOW_JSONL_PATH,
    StressSession,
    _call_scillm,
)
from sparta_stress_test.conversation_runner import run_session
import sys


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
    """Run a batch of conversation sessions.

    Args:
        questions: List of mined question dicts.
        use_brandon_grading: Use Brandon /scillm tier-2 grading.
        archive: Submit each session to /episodic-archiver.
        verbose: Log every session result.

    Returns:
        List of completed StressSessions.
    """
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

    # Print per-session traceability summary
    for s in sessions:
        if not s.grade:
            continue
        trace_lines = []
        for t in s.turns:
            if t.speaker == "SPARTA" and t.traceability_report:
                meta = t.metadata or {}
                cards = meta.get("retrieval_cards", [])
                sg = meta.get("self_grade_final", {}) or {}
                verified = sg.get("qra_citations_verified", 0)
                total_cit = sg.get("qra_citations_total", 0)
                citation_dets = sg.get("citation_details", [])
                unverified = sum(1 for d in citation_dets if not d.get("verified", True))
                trace_lines.append(
                    f"  Turn {t.turn_number} (SPARTA): {len(cards)} QRAs retrieved, "
                    f"{verified}/{total_cit} citations verified, "
                    f"{unverified} unverified claims"
                )
        if trace_lines:
            logger.info(
                f"Session {s.session_id}: {s.persona}\n"
                + "\n".join(trace_lines)
                + f"\n  Grade: {s.grade.grade} ({s.grade.composite:.2f})"
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

    # Per-session traceability summaries
    traceability_summaries = []
    for s in sessions:
        if not s.grade:
            continue
        session_trace = {
            "session_id": s.session_id,
            "persona": s.persona,
            "grade": s.grade.grade,
            "composite": s.grade.composite,
            "turns": [],
        }
        for t in s.turns:
            if t.speaker == "SPARTA" and t.traceability_report:
                # Extract key metrics from turn metadata
                meta = t.metadata or {}
                cards = meta.get("retrieval_cards", [])
                sg = meta.get("self_grade_final", {}) or {}
                verified = sg.get("qra_citations_verified", 0)
                total_cit = sg.get("qra_citations_total", 0)
                # Count unverified from citation_details if available
                citation_dets = sg.get("citation_details", [])
                unverified = sum(1 for d in citation_dets if not d.get("verified", True))
                session_trace["turns"].append({
                    "turn_number": t.turn_number,
                    "qras_retrieved": len(cards),
                    "citations_verified": verified,
                    "citations_total": total_cit,
                    "unverified_claims": unverified,
                })
        if session_trace["turns"]:
            traceability_summaries.append(session_trace)

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
        "traceability_summaries": traceability_summaries,
    }


# --------------------------------------------------------------------------- #
# Shadow-LEGO Post-Run Pipeline (NON-NEGOTIABLE)
# --------------------------------------------------------------------------- #


def _categorize_composite(composite: float) -> str:
    """Bucket composite scores for stratification."""
    if composite >= 0.90:
        return "excellent"
    elif composite >= 0.75:
        return "good"
    elif composite >= 0.60:
        return "fair"
    elif composite >= 0.40:
        return "poor"
    return "failing"


def _stratified_sample_sessions(
    sessions: List[StressSession],
    samples_per_stratum: int = 5,
    seed: int = 42,
) -> Dict[str, List[StressSession]]:
    """Draw a statistically stratified sample from completed sessions.

    Stratifies by 3 dimensions simultaneously:
      - persona (Margaret Chen / Jennifer Cheung)
      - resolution (resolved / no_coverage / partial / ambiguous)
      - composite bucket (excellent / good / fair / poor / failing)
    """
    random.seed(seed)
    strata: Dict[str, List[StressSession]] = {}

    for s in sessions:
        if not s.grade:
            continue
        persona_key = s.persona.split()[0].lower()
        resolution_key = s.resolution or "unknown"
        composite_key = _categorize_composite(s.grade.composite)
        stratum = f"{persona_key}_{resolution_key}_{composite_key}"

        if stratum not in strata:
            strata[stratum] = []
        strata[stratum].append(s)

    sampled: Dict[str, List[StressSession]] = {}
    total_sampled = 0
    for key, group in strata.items():
        shuffled = group.copy()
        random.shuffle(shuffled)
        take = min(samples_per_stratum, len(shuffled))
        sampled[key] = shuffled[:take]
        total_sampled += take

    logger.info(
        f"Stratified sample: {total_sampled} sessions from "
        f"{len(strata)} strata (population={len(sessions)})"
    )
    return sampled


def _llm_rate_session(session: StressSession) -> Dict[str, Any]:
    """Have Tier 2 LLM (scillm) rate a single session as external judge."""
    transcript_lines = []
    for turn in session.turns:
        transcript_lines.append(f"[{turn.speaker}] {turn.content[:500]}")
    transcript_text = "\n".join(transcript_lines)

    seed = session.seed_question
    grade = session.grade

    all_source_keys = []
    for turn in session.turns:
        turn_keys = turn.metadata.get("source_keys", [])
        all_source_keys.extend(turn_keys)

    qra_ground_truth_text = ""
    if all_source_keys:
        try:
            from sparta_stress_test.semantic_grader import _build_qra_ground_truth
            qra_ground_truth_text = _build_qra_ground_truth(all_source_keys[:5])
        except Exception as e:
            logger.debug(f"QRA ground truth fetch failed: {e}")
            qra_ground_truth_text = "(unavailable)"
    else:
        qra_ground_truth_text = "(No QRA source keys recorded in session turns)"

    try:
        from sparta_stress_test.semantic_grader import (
            RESPONSE_TYPE_TAXONOMY as _RT_TAX,
            RESPONSE_TYPE_GRADING_RULES as _RT_RULES,
        )
    except ImportError:
        _RT_TAX = ""
        _RT_RULES = ""

    prompt = f"""You are an EXTERNAL quality auditor for the SPARTA space systems QRA pipeline.
You are NOT the system that produced these answers. You are an independent judge.
You have NOT seen any prior grades. Judge the answer quality from scratch.

CRITICAL RULE: QRA citation accuracy is the ONLY valid quality signal.
- "Good answer" = cites REAL controls from ground truth with CORRECT information
- "Bad answer" = cites fabricated frameworks or wrong information about real controls

{_RT_TAX}

TRANSCRIPT:
{transcript_text[:3000]}

METADATA:
- Persona: {session.persona}
- Difficulty: {seed.get('difficulty', 'unknown')}
- Target control: {seed.get('target_control', 'N/A')}

QRA GROUND TRUTH (retrieved during session — the ONLY source of valid facts):
{qra_ground_truth_text}

{_RT_RULES}

STEP 1: Classify the response type (CITED, NO-COVERAGE, or HALLUCINATED)
- If the answer says "I don't have coverage" / "I don't recognize" -> NO-COVERAGE
- If the answer cites specific controls -> CITED (verify each against ground truth)
- If the answer invents information not from the QRA ground truth -> HALLUCINATED

STEP 2: CITATION VERIFICATION (only if response type is CITED)
Go through the answer line by line. For each factual claim:
- Is the control/framework/protocol mentioned in the QRA GROUND TRUTH above?
- If YES: does the stated information MATCH what the ground truth says?
- If the answer mentions frameworks/controls NOT in the ground truth -> mark FABRICATED

STEP 3: Grade based on response type and verification rules above.

Return JSON:
{{
    "teacher_grade": "A+"|"A"|"B"|"C"|"F",
    "teacher_confidence": 0.0-1.0,
    "response_type": "CITED"|"NO-COVERAGE"|"HALLUCINATED",
    "citation_verification": ["SV-MA-3: VERIFIED", "Orion Protocol: FABRICATED"],
    "issues": ["specific issue 1", "issue 2"],
    "reasoning": "1-2 sentence rationale focusing on citation accuracy"
}}"""

    raw = _call_scillm(
        system="You are an independent quality auditor. Be critical and honest. Grade F ONLY for hallucinated/fabricated frameworks or wrong info on real controls. Grade B for honest 'I don't have coverage' answers — saying 'I don't know' when the database lacks data is CORRECT behavior, not failure.",
        user_prompt=prompt,
        max_tokens=768,
    )

    try:
        result = json.loads(raw)
        valid_grades = {"A+", "A", "B", "C", "F"}
        if result.get("teacher_grade") not in valid_grades:
            result["teacher_grade"] = "C"
        return result
    except (json.JSONDecodeError, TypeError):
        logger.warning(f"LLM rating parse failed: {raw[:200]}")
        return {
            "teacher_grade": "C",
            "teacher_confidence": 0.0,
            "agreed": False,
            "issues": ["parse_failure"],
            "reasoning": f"Failed to parse LLM response: {raw[:100]}",
        }


_GRADE_ORDER = {"A+": 0, "A": 1, "B": 2, "C": 3, "F": 4}


def _grades_agree(grade_a: str, grade_b: str) -> bool:
    """Fuzzy agreement: grades within 1 step count as AGREE."""
    idx_a = _GRADE_ORDER.get(grade_a, 4)
    idx_b = _GRADE_ORDER.get(grade_b, 4)
    return abs(idx_a - idx_b) <= 1


def _write_shadow_entries(
    sessions: List[StressSession],
    ratings: Dict[str, Dict[str, Any]],
) -> int:
    """Write rated session results to /assistant shadow.jsonl."""
    SHADOW_JSONL_PATH.parent.mkdir(parents=True, exist_ok=True)
    count = 0

    with open(SHADOW_JSONL_PATH, "a") as f:
        for s in sessions:
            rating = ratings.get(s.session_id)
            if not rating:
                continue

            entry = {
                "task": "sparta_stress_grading",
                "scope": "sparta",
                "timestamp": datetime.now().isoformat(),
                "input_data": {
                    "question": s.seed_question.get("question", "")[:500],
                    "persona": s.persona,
                    "difficulty": s.seed_question.get("difficulty", "unknown"),
                    "target_control": s.seed_question.get("target_control", ""),
                    "answer_text": (
                        s.turns[-2].content[:500]
                        if len(s.turns) >= 2
                        else ""
                    ),
                },
                "teacher_result": rating,
                "teacher_grade": rating.get("teacher_grade", "C"),
                "teacher_confidence": rating.get("teacher_confidence", 0.0),
                "local_grade": s.grade.grade if s.grade else "F",
                "local_confidence": s.grade.composite if s.grade else 0.0,
                "local_source": "semantic_grader",
                "local_tier": 2,
                "agreed": rating.get("agreed", _grades_agree(
                    rating.get("teacher_grade", "C"),
                    s.grade.grade if s.grade else "F",
                )),
                "qra_citation_count": sum(
                    len(t.metadata.get("source_keys", []))
                    for t in s.turns
                ),
                "qra_citations_verified": s.grade.qra_citations_verified if s.grade else 0,
                "qra_citations_total": s.grade.qra_citations_total if s.grade else 0,
                "qra_grounding_avg": (
                    s.grade.scores.get("qra_citation_accuracy", 0)
                    if s.grade and s.grade.scores else 0
                ),
                "student_model": "Qwen/Qwen3-Coder-Next-TEE",
                "teacher_model": "deepseek-ai/DeepSeek-V3",
            }

            f.write(json.dumps(entry) + "\n")
            count += 1

    logger.info(f"Wrote {count} shadow entries to {SHADOW_JSONL_PATH}")
    return count


def shadow_lego_post_run(sessions: List[StressSession]) -> Dict[str, Any]:
    """NON-NEGOTIABLE Shadow-LEGO post-run pipeline.

    This MUST run after every stress test batch to close the learning loop.

    Pipeline:
        1. Stratified sample by persona x resolution x composite bucket
        2. Tier 2 LLM rates each sample (external judge, NOT self-grade)
        3. Write shadow.jsonl entries for /assistant
        4. Trigger auto_improve() to decide promote/retrain/redesign
        5. Log summary for human review
    """
    logger.info("=" * 60)
    logger.info("SHADOW-LEGO POST-RUN PIPELINE (NON-NEGOTIABLE)")
    logger.info("=" * 60)

    if len(sessions) < 10:
        logger.warning(f"Only {len(sessions)} sessions — too few for stratified sampling")
        return {"error": "insufficient_sessions", "count": len(sessions)}

    samples_per = max(3, min(10, len(sessions) // 20))
    strata = _stratified_sample_sessions(sessions, samples_per_stratum=samples_per)

    sampled_sessions = []
    for group in strata.values():
        sampled_sessions.extend(group)

    sample_size = len(sampled_sessions)
    logger.info(
        f"Step 1: Stratified sample = {sample_size} sessions "
        f"from {len(strata)} strata"
    )

    if sample_size < MIN_STRATIFIED_SAMPLE and len(sessions) >= MIN_STRATIFIED_SAMPLE:
        random.seed(42)
        sampled_sessions = random.sample(sessions, min(MIN_STRATIFIED_SAMPLE, len(sessions)))
        sample_size = len(sampled_sessions)
        logger.info(f"Fallback: random sample of {sample_size} (strata too sparse)")

    logger.info(f"Step 2: LLM rating {sample_size} sessions via scillm (Tier 2)...")
    ratings: Dict[str, Dict[str, Any]] = {}
    agreed_count = 0

    for i, s in enumerate(sampled_sessions):
        try:
            rating = _llm_rate_session(s)
            ratings[s.session_id] = rating
            teacher_g = rating.get("teacher_grade", "C")
            brandon_g = s.grade.grade if s.grade else "F"
            if _grades_agree(teacher_g, brandon_g):
                agreed_count += 1
            if (i + 1) % 10 == 0:
                logger.info(
                    f"  Rated {i+1}/{sample_size} "
                    f"(agreement so far: {agreed_count}/{i+1})"
                )
        except Exception as e:
            logger.warning(f"  Rating failed for {s.session_id}: {e}")
            continue

    rated_count = len(ratings)
    agreement_rate = agreed_count / max(1, rated_count)
    logger.info(
        f"Step 2 complete: {rated_count}/{sample_size} rated, "
        f"agreement={agreement_rate:.1%}"
    )

    shadow_count = _write_shadow_entries(sampled_sessions, ratings)
    logger.info(f"Step 3: Wrote {shadow_count} shadow entries to {SHADOW_JSONL_PATH}")

    auto_improve_result = None
    try:
        model_factory_path = str(
            PI_MONO_SKILLS / "assistant" / "model_factory.py"
        )
        if Path(model_factory_path).exists():
            assistant_dir = str(PI_MONO_SKILLS / "assistant")
            if assistant_dir not in sys.path:
                sys.path.insert(0, assistant_dir)
            from model_factory import ModelFactory
            factory = ModelFactory()
            auto_improve_result = factory.auto_improve("sparta_stress_grading")
            logger.info(
                f"Step 4: auto_improve result: "
                f"{json.dumps(auto_improve_result, default=str)[:200]}"
            )
        else:
            logger.warning("Step 4: ModelFactory not found, skipping auto_improve")
    except Exception as e:
        logger.warning(f"Step 4: auto_improve failed: {e}")

    teacher_grades: Dict[str, int] = {}
    for r in ratings.values():
        g = r.get("teacher_grade", "?")
        teacher_grades[g] = teacher_grades.get(g, 0) + 1

    local_grades: Dict[str, int] = {}
    for s in sampled_sessions:
        if s.grade:
            g = s.grade.grade
            local_grades[g] = local_grades.get(g, 0) + 1

    if rated_count > 0:
        p = agreement_rate
        margin = 1.96 * math.sqrt(p * (1 - p) / rated_count)
        ci_str = f"{p:.1%} +/- {margin:.1%}"
    else:
        ci_str = "N/A"

    summary = {
        "pipeline": "shadow_lego_post_run",
        "timestamp": datetime.now().isoformat(),
        "population": len(sessions),
        "sample_size": sample_size,
        "rated_count": rated_count,
        "strata_count": len(strata),
        "agreement_rate": round(agreement_rate, 4),
        "agreement_ci_95": ci_str,
        "teacher_grade_distribution": teacher_grades,
        "local_grade_distribution": local_grades,
        "shadow_entries_written": shadow_count,
        "auto_improve_result": auto_improve_result,
        "shadow_jsonl_path": str(SHADOW_JSONL_PATH),
    }

    if rated_count >= 50:
        if agreement_rate >= 0.90:
            summary["recommendation"] = "PROMOTE — self-grading matches teacher"
        elif agreement_rate >= 0.80:
            summary["recommendation"] = "PLATEAU — consider /prompt-lab redesign"
        elif agreement_rate >= 0.70:
            summary["recommendation"] = "RETRAIN — need more teacher labels"
        else:
            summary["recommendation"] = "AGGRESSIVE_RETRAIN — architecture change needed"
    else:
        summary["recommendation"] = (
            f"WAIT — only {rated_count} samples, need >=50 for promotion decision"
        )

    logger.info("=" * 60)
    logger.info("SHADOW-LEGO POST-RUN SUMMARY")
    logger.info(f"  Population: {len(sessions)} sessions")
    logger.info(f"  Sample: {sample_size} (stratified)")
    logger.info(f"  Rated: {rated_count}")
    logger.info(f"  Agreement: {ci_str}")
    logger.info(f"  Teacher grades: {teacher_grades}")
    logger.info(f"  Local grades: {local_grades}")
    logger.info(f"  Recommendation: {summary['recommendation']}")
    logger.info(f"  Shadow entries: {shadow_count} -> {SHADOW_JSONL_PATH}")
    logger.info("=" * 60)

    summary_path = SHADOW_DELTA_PATH.parent / "shadow_lego_summary.json"
    try:
        summary_path.write_text(json.dumps(summary, indent=2, default=str))
        logger.info(f"Summary saved to {summary_path}")
    except Exception as e:
        logger.warning(f"Failed to save summary: {e}")

    return summary


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
