"""Shadow-LEGO post-run pipeline for SPARTA stress test sessions.

NON-NEGOTIABLE pipeline that runs after every stress test batch to close
the learning loop: stratified sampling, Tier 2 LLM rating, shadow.jsonl
writing, and auto_improve() triggering.
"""

from __future__ import annotations

import json
import math
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from loguru import logger

from sparta_stress_test.evidence_grader import (
    EvidenceResult,
    evidence_grades_agree,
    grade_evidence,
)
from sparta_stress_test.models import (
    GRADE_ORDER,
    MIN_STRATIFIED_SAMPLE,
    PI_MONO_SKILLS,
    SHADOW_DELTA_PATH,
    SHADOW_JSONL_PATH,
    StressSession,
    grades_agree,
)
from sparta_stress_test.retrieval import _call_scillm


# --------------------------------------------------------------------------- #
# Stratified sampling
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

    Returns dict of stratum_key -> sampled sessions.
    """
    random.seed(seed)
    strata: Dict[str, List[StressSession]] = {}

    for s in sessions:
        if not s.grade:
            continue
        persona_key = s.persona.split()[0].lower()  # margaret / jennifer
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


# --------------------------------------------------------------------------- #
# LLM rating (external judge)
# --------------------------------------------------------------------------- #


def _llm_rate_session(session: StressSession) -> Dict[str, Any]:
    """Have Tier 2 LLM (scillm) rate a single session as external judge.

    This is NOT self-grading. The LLM sees the full conversation transcript
    and produces a structured evaluation independent of Brandon's self-grade.
    """
    transcript_lines = []
    for turn in session.turns:
        transcript_lines.append(f"[{turn.speaker}] {turn.content[:500]}")
    transcript_text = "\n".join(transcript_lines)

    seed = session.seed_question

    # Collect QRA source_keys from all turns for ground truth verification
    all_source_keys = []
    for turn in session.turns:
        turn_keys = turn.metadata.get("source_keys", [])
        all_source_keys.extend(turn_keys)

    # Fetch QRA ground truth for teacher to verify citations
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

    # Build teacher prompt using SHARED taxonomy from semantic_grader
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
        # Normalize grade
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


# --------------------------------------------------------------------------- #
# Evidence-based rating (deterministic, ~800ms, replaces LLM for local grade)
# --------------------------------------------------------------------------- #


def _evidence_rate_session(session: StressSession) -> EvidenceResult:
    """Rate a session using deterministic evidence signals.

    Replaces the subjective A/B/C/F LLM grading with a 4-state evidence
    assessment: Pass, Ambiguous, Fail, Absurd. ~800ms total (no LLM calls).
    """
    seed = session.seed_question
    question = seed.get("question", "")

    # Get the system's answer from the last SPARTA turn
    answer = ""
    for turn in reversed(session.turns):
        if turn.role != "persona":
            answer = turn.content
            break

    return grade_evidence(
        question=question,
        answer=answer,
        target_control=seed.get("target_control", ""),
        difficulty=seed.get("difficulty", "medium"),
    )


# --------------------------------------------------------------------------- #
# Shadow.jsonl writing
# --------------------------------------------------------------------------- #


def _write_shadow_entries(
    sessions: List[StressSession],
    ratings: Dict[str, Dict[str, Any]],
    evidence_results: Dict[str, EvidenceResult] | None = None,
) -> int:
    """Write rated session results to /assistant shadow.jsonl.

    Writes TWO shadow entries per session when evidence results are available:
    1. Legacy A/B/C/F entry (task=sparta_stress_grading) for backward compat
    2. Evidence 4-state entry (task=sparta_stress_evidence) for the new pipeline

    The evidence entry is what the Wilson gate should evaluate for promotion.
    """
    SHADOW_JSONL_PATH.parent.mkdir(parents=True, exist_ok=True)
    evidence_results = evidence_results or {}
    count = 0

    with open(SHADOW_JSONL_PATH, "a") as f:
        for s in sessions:
            rating = ratings.get(s.session_id)
            if not rating:
                continue

            input_data = {
                "question": s.seed_question.get("question", "")[:500],
                "persona": s.persona,
                "difficulty": s.seed_question.get("difficulty", "unknown"),
                "target_control": s.seed_question.get("target_control", ""),
                "answer_text": (
                    s.turns[-2].content[:500]
                    if len(s.turns) >= 2
                    else ""
                ),
            }

            # Legacy A/B/C/F entry (backward compat with existing auto_improve)
            legacy_entry = {
                "task": "sparta_stress_grading",
                "scope": "sparta",
                "timestamp": datetime.now().isoformat(),
                "input_data": input_data,
                "teacher_result": rating,
                "teacher_grade": rating.get("teacher_grade", "C"),
                "teacher_confidence": rating.get("teacher_confidence", 0.0),
                "local_grade": s.grade.grade if s.grade else "F",
                "local_confidence": s.grade.composite if s.grade else 0.0,
                "local_source": "semantic_grader",
                "local_tier": 2,
                "agreed": rating.get("agreed", grades_agree(
                    rating.get("teacher_grade", "C"),
                    s.grade.grade if s.grade else "F",
                )),
                "qra_citation_count": sum(
                    len(t.metadata.get("source_keys", []))
                    for t in s.turns
                ),
                "student_model": "Qwen/Qwen3-Coder-Next-TEE",
                "teacher_model": "deepseek-ai/DeepSeek-V3",
            }
            f.write(json.dumps(legacy_entry) + "\n")
            count += 1

            # Evidence-based 4-state entry (new pipeline)
            ev = evidence_results.get(s.session_id)
            if ev:
                evidence_entry = {
                    "task": "sparta_stress_evidence",
                    "scope": "sparta",
                    "grade_type": "evidence",
                    "timestamp": datetime.now().isoformat(),
                    "input_data": input_data,
                    # Both local and teacher use the SAME deterministic grader
                    # so agreement is always 100% — the point is to track the
                    # evidence grade distribution, not local-vs-teacher agreement
                    "local_grade": ev.grade,
                    "teacher_grade": ev.grade,
                    "local_source": "evidence_grader",
                    "local_tier": 0,  # Tier 0 = deterministic, no LLM
                    "agreed": True,
                    # Evidence signals for analysis
                    "evidence": ev.to_dict(),
                    "student_model": "deterministic",
                    "teacher_model": "deterministic",
                }
                f.write(json.dumps(evidence_entry) + "\n")
                count += 1

    logger.info(f"Wrote {count} shadow entries to {SHADOW_JSONL_PATH}")
    return count


# --------------------------------------------------------------------------- #
# Main pipeline
# --------------------------------------------------------------------------- #


def shadow_lego_post_run(sessions: List[StressSession]) -> Dict[str, Any]:
    """NON-NEGOTIABLE Shadow-LEGO post-run pipeline.

    This MUST run after every stress test batch to close the learning loop.
    Without this, conversation data feeds nothing and the system never improves.

    Pipeline:
        1. Stratified sample by persona x resolution x composite bucket
        2. Tier 2 LLM rates each sample (external judge, NOT self-grade)
        3. Write shadow.jsonl entries for /assistant
        4. Trigger auto_improve() to decide promote/retrain/redesign
        5. Log summary for human review

    Returns summary dict with sample_size, agreement_rate, recommendations.
    """
    logger.info("=" * 60)
    logger.info("SHADOW-LEGO POST-RUN PIPELINE (NON-NEGOTIABLE)")
    logger.info("=" * 60)

    if len(sessions) < 10:
        logger.warning(f"Only {len(sessions)} sessions — too few for stratified sampling")
        return {"error": "insufficient_sessions", "count": len(sessions)}

    # Step 1: Stratified sample
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

    # Step 2a: Evidence-based grading (deterministic, ~800ms per session)
    logger.info(f"Step 2a: Evidence grading {sample_size} sessions (deterministic)...")
    evidence_results: Dict[str, EvidenceResult] = {}
    evidence_dist: Dict[str, int] = {}

    for i, s in enumerate(sampled_sessions):
        try:
            ev = _evidence_rate_session(s)
            evidence_results[s.session_id] = ev
            evidence_dist[ev.grade] = evidence_dist.get(ev.grade, 0) + 1
        except Exception as e:
            logger.warning(f"  Evidence grading failed for {s.session_id}: {e}")

    logger.info(
        f"Step 2a complete: {len(evidence_results)}/{sample_size} graded, "
        f"distribution={evidence_dist}"
    )

    # Step 2b: LLM rates each sampled session (Tier 2 external judge)
    # Kept for legacy A/B/C/F shadow entries and teacher comparison
    logger.info(f"Step 2b: LLM rating {sample_size} sessions via scillm (Tier 2)...")
    ratings: Dict[str, Dict[str, Any]] = {}
    agreed_count = 0

    for i, s in enumerate(sampled_sessions):
        try:
            rating = _llm_rate_session(s)
            ratings[s.session_id] = rating
            teacher_g = rating.get("teacher_grade", "C")
            brandon_g = s.grade.grade if s.grade else "F"
            if grades_agree(teacher_g, brandon_g):
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
        f"Step 2b complete: {rated_count}/{sample_size} rated, "
        f"agreement={agreement_rate:.1%}"
    )

    # Step 3: Write to /assistant shadow.jsonl (both legacy + evidence entries)
    shadow_count = _write_shadow_entries(sampled_sessions, ratings, evidence_results)
    logger.info(f"Step 3: Wrote {shadow_count} shadow entries to {SHADOW_JSONL_PATH}")

    # Step 4: Trigger auto_improve
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

    # Step 5: Grade distribution summary
    teacher_grades: Dict[str, int] = {}
    for r in ratings.values():
        g = r.get("teacher_grade", "?")
        teacher_grades[g] = teacher_grades.get(g, 0) + 1

    local_grades: Dict[str, int] = {}
    for s in sampled_sessions:
        if s.grade:
            g = s.grade.grade
            local_grades[g] = local_grades.get(g, 0) + 1

    # Confidence interval (95% CI for agreement rate)
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
        "evidence_grade_distribution": evidence_dist,
        "evidence_graded_count": len(evidence_results),
        "shadow_entries_written": shadow_count,
        "auto_improve_result": auto_improve_result,
        "shadow_jsonl_path": str(SHADOW_JSONL_PATH),
    }

    # Decision based on /assistant-lab thresholds
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
    logger.info(f"  Teacher grades (legacy): {teacher_grades}")
    logger.info(f"  Local grades (legacy): {local_grades}")
    logger.info(f"  Evidence grades: {evidence_dist}")
    logger.info(f"  Recommendation: {summary['recommendation']}")
    logger.info(f"  Shadow entries: {shadow_count} -> {SHADOW_JSONL_PATH}")
    logger.info("=" * 60)

    # Save summary alongside sessions
    summary_path = SHADOW_DELTA_PATH.parent / "shadow_lego_summary.json"
    try:
        summary_path.write_text(json.dumps(summary, indent=2, default=str))
        logger.info(f"Summary saved to {summary_path}")
    except Exception as e:
        logger.warning(f"Failed to save summary: {e}")

    return summary
