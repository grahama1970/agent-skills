"""7-dimension grading for SPARTA stress test results.

Architecture follows the /assistant cascade pattern:
  Tier 0:   Heuristic (this module's deterministic scoring)      free, microseconds
  Tier 0.5: Classifier (trained via /create-classifier)          free, ~10ms
  Tier 1.5: GPT (trained via /create-gpt from Brandon's labels)  free, ~200ms
  Tier 2:   scillm Brandon (persona teacher, authoritative)       paid, 2-5s

The cascade flow:
  1. grade_response() runs tier-0 heuristic scoring (deterministic, always runs)
  2. grade_via_cascade() routes through /assistant for persona-validated grading
  3. Brandon's tier-2 labels are harvested nightly to train tier 0.5/1.5 models
  4. /classifier-lab and /gpt-lab benchmark the student models against Brandon

Grades each response across:
1. action_correctness — Did intent mapper choose the right action?
2. name_match — Does response reference correct control?
3. technique_coverage — Fraction of expected techniques found
4. cm_coverage — Fraction of expected CMs found
5. disambiguation_quality — Does clarification suggest the right controls?
6. error_detection — Caught the bad ID? Suggested closest match?
7. response_naturalness — No pipe separators, no raw JSON, reads as conversation
"""

import json
import re
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

# Known pipe-separator patterns from raw QRA concatenation
_PIPE_PATTERN = re.compile(r'\s*\|\s*')
_JSON_PATTERN = re.compile(r'[{}\[\]"]:')
_RAW_KEY_PATTERN = re.compile(r'\b(control_id|grounding_score|_key|sparta_techniques)\b')

# Task name for /assistant registry
GRADER_TASK = "cascade-grader"
GRADER_SCOPE = "brandon_bailey"

# pi-mono skills path for /assistant import
PI_MONO_SKILLS = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Tier 0: Heuristic grading (deterministic, always runs)
# ---------------------------------------------------------------------------

def grade_response(
    question: dict,
    intent_result: dict,
    answer: Optional[dict],
    nlg_response: Optional[str],
) -> dict:
    """Grade a single stress test response across 7 dimensions (Tier 0 heuristic).

    This is the deterministic baseline. For persona-validated grading,
    use grade_via_cascade() which routes through the /assistant 4-tier cascade.

    Args:
        question: Question bank entry with expected_action, target_control, etc.
        intent_result: Output from /sparta-intent (action, entities, etc.)
        answer: QRA lookup result (if action was QUERY).
        nlg_response: Brandon's natural language response (if NLG was applied).

    Returns:
        Dict with per-dimension scores (0.0-1.0), composite score, and letter grade.
    """
    expected_action = question.get("expected_action", "QUERY")
    difficulty = question.get("difficulty", "simple")
    actual_action = intent_result.get("action", "")

    scores = {}

    is_code = question.get("category", "") in ("code", "pipeline")

    # 1. action_correctness
    # CLARIFY is valid behavior for ambiguous difficulty questions even if
    # expected_action was technically QUERY.  It means the pipeline correctly
    # detected ambiguity and asked for clarification instead of guessing.
    if actual_action == expected_action:
        scores["action_correctness"] = 1.0
    elif actual_action == "CLARIFY" and difficulty == "ambiguous":
        # Correct disambiguation — CLARIFY is the right call for ambiguous queries
        scores["action_correctness"] = 1.0
    elif actual_action == "CLARIFY" and expected_action == "QUERY":
        # Unnecessary clarification on a non-ambiguous question — cautious but not wrong
        scores["action_correctness"] = 0.5
    else:
        scores["action_correctness"] = 0.0

    # 2-4: content grading differs between SPARTA and code questions
    if expected_action == "QUERY" and actual_action == "QUERY":
        if is_code:
            # Code questions: check target_file mention instead of control ID
            scores["name_match"] = _grade_code_name_match(question, answer)
            # No techniques/CMs for code — auto-pass
            scores["technique_coverage"] = 1.0
            scores["cm_coverage"] = 1.0
            # Code-specific: did the answer cite actual skills/files?
            scores["evidence_quality"] = _grade_evidence_quality(question, answer)
        else:
            scores["name_match"] = _grade_name_match(question, answer)
            scores["technique_coverage"] = _grade_technique_coverage(question, answer)
            scores["cm_coverage"] = _grade_cm_coverage(question, answer)
    elif expected_action == "QUERY" and actual_action == "CLARIFY":
        if difficulty == "ambiguous":
            pass  # Content grades N/A — disambiguation_quality replaces them
        else:
            pass  # Unnecessary clarification — mild penalty via action_correctness
    elif expected_action == "QUERY":
        # Wrong action for a QUERY question — zero for content grades
        scores["name_match"] = 0.0
        if is_code:
            scores["technique_coverage"] = 1.0
            scores["cm_coverage"] = 1.0
        else:
            scores["technique_coverage"] = 0.0
            scores["cm_coverage"] = 0.0

    # 5. disambiguation_quality — scored when CLARIFY is expected OR actual
    if expected_action == "CLARIFY" or actual_action == "CLARIFY":
        scores["disambiguation_quality"] = _grade_disambiguation(question, intent_result)

    # 6. error_detection (only for NO_MATCH/flawed)
    if expected_action == "NO_MATCH" or difficulty == "flawed":
        scores["error_detection"] = _grade_error_detection(question, intent_result, answer)

    # 7. response_naturalness (applies to all responses with text)
    response_text = nlg_response or ""
    if not response_text and answer:
        response_text = answer.get("answer_text", "")
    if not response_text:
        response_text = intent_result.get("persona_guidance", "")
    scores["response_naturalness"] = _grade_naturalness(response_text)

    # Composite: weighted average of applicable dimensions
    applicable = {k: v for k, v in scores.items()}
    if not applicable:
        composite = 0.0
    else:
        # action_correctness gets 2x weight — it's the gatekeeper
        weighted_sum = 0.0
        weight_total = 0.0
        for dim, score in applicable.items():
            w = 2.0 if dim == "action_correctness" else 1.0
            weighted_sum += score * w
            weight_total += w
        composite = weighted_sum / weight_total if weight_total > 0 else 0.0

    grade = _composite_to_grade(composite)

    return {
        "scores": scores,
        "composite": round(composite, 3),
        "grade": grade,
        "difficulty": difficulty,
        "expected_action": expected_action,
        "actual_action": actual_action,
        "tier": 0,
        "source": "heuristic",
    }


# ---------------------------------------------------------------------------
# Cascade grading via /assistant (Tier 0 → 0.5 → 1.5 → 2)
# ---------------------------------------------------------------------------

def grade_via_cascade(
    question: dict,
    intent_result: dict,
    answer: Optional[dict],
    nlg_response: Optional[str],
    *,
    confidence_threshold: float = 0.85,
) -> dict:
    """Grade through /assistant 4-tier cascade with Brandon as Tier 2 teacher.

    Flow:
      Tier 0:   Heuristic (grade_response above)
      Tier 0.5: Classifier (if trained via /create-classifier + /classifier-lab)
      Tier 1.5: GPT (if trained via /create-gpt + /gpt-lab)
      Tier 2:   Brandon via /scillm (authoritative teacher labels)

    If /assistant is unavailable, falls back to Tier 0 heuristic only.
    """
    # Always compute tier-0 heuristic as baseline
    heuristic_result = grade_response(question, intent_result, answer, nlg_response)

    # Try cascade via /assistant
    try:
        assistant_validate = _get_assistant_validate()
        if assistant_validate is None:
            return heuristic_result

        # Build input payload for /assistant
        input_data = _build_cascade_input(question, intent_result, answer, nlg_response)

        # Heuristic fn wraps our tier-0 into /assistant format.
        # Returns None for complex/uncertain questions to force escalation.
        def heuristic_fn(inp: dict) -> Optional[dict]:
            difficulty = heuristic_result.get("difficulty", "")
            composite = heuristic_result.get("composite", 0)
            # Escalate complex/ambiguous questions or low-confidence grades
            if difficulty in ("complex", "ambiguous") or composite < 0.7:
                return None  # cascade skips tier 0, tries 0.5+
            return {
                "grade": heuristic_result["grade"],
                "composite": heuristic_result["composite"],
                "scores": heuristic_result["scores"],
                "difficulty": heuristic_result["difficulty"],
                "expected_action": heuristic_result["expected_action"],
                "actual_action": heuristic_result["actual_action"],
            }

        # Run cascade — /assistant handles tier escalation
        tier_result = assistant_validate(
            input_data=input_data,
            task=GRADER_TASK,
            scope=GRADER_SCOPE,
            confidence_threshold=confidence_threshold,
            heuristic_fn=heuristic_fn,
        )

        # Merge cascade result with heuristic baseline
        cascade_grade = tier_result.result if tier_result.result else {}
        return {
            "scores": cascade_grade.get("scores", heuristic_result["scores"]),
            "composite": cascade_grade.get("composite", heuristic_result["composite"]),
            "grade": cascade_grade.get("grade", heuristic_result["grade"]),
            "difficulty": heuristic_result["difficulty"],
            "expected_action": heuristic_result["expected_action"],
            "actual_action": heuristic_result["actual_action"],
            "tier": tier_result.tier,
            "source": tier_result.source,
            "confidence": tier_result.confidence,
            "latency_ms": tier_result.latency_ms,
            # Brandon-specific fields (only from tier 2)
            "reasoning_sound": cascade_grade.get("reasoning_sound"),
            "taxonomy_correct": cascade_grade.get("taxonomy_correct"),
            "rationale": cascade_grade.get("rationale"),
        }

    except Exception as e:
        logger.warning(f"Cascade grading failed, falling back to heuristic: {type(e).__name__}: {e}")
        # Add cascade_failed metadata so we know this was attempted
        heuristic_result["cascade_failed"] = str(e)
        return heuristic_result


def _build_cascade_input(
    question: dict,
    intent_result: dict,
    answer: Optional[dict],
    nlg_response: Optional[str],
) -> dict:
    """Build input payload for /assistant cascade.

    This is the schema that Brandon (tier 2) and trained GPTs (tier 1.5)
    will receive for grading.
    """
    return {
        "question": question.get("question", ""),
        "difficulty": question.get("difficulty", ""),
        "persona": question.get("persona", ""),
        "expected_action": question.get("expected_action", ""),
        "target_control": question.get("target_control"),
        "expected_techniques": question.get("expected_techniques", []),
        "expected_countermeasures": question.get("expected_countermeasures", []),
        "bridge_tags": question.get("bridge_tags", []),
        "actual_action": intent_result.get("action", ""),
        "intent_entities": intent_result.get("entities", {}),
        "answer_text": (answer.get("answer_text", "") if answer else ""),
        "answer_control_id": (answer.get("control_id", "") if answer else ""),
        "answer_techniques": (answer.get("sparta_techniques", []) if answer else []),
        "answer_countermeasures": (answer.get("sparta_countermeasures", []) if answer else []),
        "nlg_response": nlg_response or "",
    }


def _get_assistant_validate() -> Optional[Callable]:
    """Lazy import of /assistant validate function."""
    try:
        if str(PI_MONO_SKILLS) not in sys.path:
            sys.path.insert(0, str(PI_MONO_SKILLS))
        from assistant.assistant import validate
        return validate
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Training label export (for /create-classifier and /create-gpt)
# ---------------------------------------------------------------------------

def export_training_labels(
    results: List[dict],
    output_path: Path,
    *,
    tier_filter: Optional[int] = 2,
) -> int:
    """Export grading results as training labels for /create-gpt and /create-classifier.

    Filters to tier-2 (Brandon teacher) results by default, since those are
    the authoritative labels that student models should learn from.

    Output format: JSONL compatible with /create-gpt task spec and /create-classifier.

    Args:
        results: List of grade results from grade_via_cascade().
        output_path: Where to write the JSONL training data.
        tier_filter: Only export results from this tier (None = all tiers).

    Returns:
        Number of labels exported.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0

    with open(output_path, "w") as f:
        for r in results:
            # Filter by tier if specified
            if tier_filter is not None and r.get("tier") != tier_filter:
                continue

            label = {
                # Input features (what the student model sees)
                "input": {
                    "question": r.get("question_text", ""),
                    "difficulty": r.get("difficulty", ""),
                    "expected_action": r.get("expected_action", ""),
                    "actual_action": r.get("actual_action", ""),
                    "answer_text": r.get("answer_text", ""),
                    "nlg_response": r.get("nlg_response", ""),
                },
                # Output labels (what the student model should predict)
                "output": {
                    "grade": r.get("grade", ""),
                    "composite": r.get("composite", 0.0),
                    "scores": r.get("scores", {}),
                    "reasoning_sound": r.get("reasoning_sound"),
                    "taxonomy_correct": r.get("taxonomy_correct"),
                },
                # Metadata
                "source": r.get("source", ""),
                "tier": r.get("tier", -1),
                "confidence": r.get("confidence", 0.0),
            }
            f.write(json.dumps(label) + "\n")
            count += 1

    logger.info(f"Exported {count} training labels to {output_path}")
    return count


# ---------------------------------------------------------------------------
# Brandon's scillm grading prompt (Tier 2 teacher)
# ---------------------------------------------------------------------------

BRANDON_GRADING_PROMPT = """You are Brandon Bailey, Principal Director of Cyber Assessments at The Aerospace Corporation.

You are grading a SPARTA stress test response. Evaluate across these 7 dimensions (each 0.0-1.0):

1. action_correctness: Did the intent mapper choose the right action? Expected: {expected_action}, Got: {actual_action}
2. name_match: Does the response reference the correct control ({target_control})?
3. technique_coverage: What fraction of expected techniques were found?
4. cm_coverage: What fraction of expected countermeasures were found?
5. disambiguation_quality: (CLARIFY only) Did it suggest relevant follow-up questions?
6. error_detection: (NO_MATCH only) Did it catch the bad control ID?
7. response_naturalness: Is the response conversational? No raw JSON, no pipe separators?

QUESTION (difficulty={difficulty}, persona={persona}):
{question}

EXPECTED TECHNIQUES: {expected_techniques}
EXPECTED COUNTERMEASURES: {expected_countermeasures}

ACTUAL RESPONSE:
{nlg_response}

Return JSON only:
{{"grade": "A+|A|B|C|F", "composite": 0.85, "scores": {{"action_correctness": 1.0, ...}}, "reasoning_sound": true, "taxonomy_correct": true, "rationale": "brief explanation"}}"""


def format_brandon_prompt(
    question: dict,
    intent_result: dict,
    answer: Optional[dict],
    nlg_response: Optional[str],
) -> str:
    """Format the Brandon grading prompt for /scillm tier-2 calls.

    This prompt is what Brandon sees when /assistant escalates to tier 2.
    The result becomes the authoritative label for training student models.
    """
    return BRANDON_GRADING_PROMPT.format(
        expected_action=question.get("expected_action", "QUERY"),
        actual_action=intent_result.get("action", ""),
        target_control=question.get("target_control", "N/A"),
        difficulty=question.get("difficulty", ""),
        persona=question.get("persona", ""),
        question=question.get("question", ""),
        expected_techniques=question.get("expected_techniques", []),
        expected_countermeasures=question.get("expected_countermeasures", []),
        nlg_response=nlg_response or (answer.get("answer_text", "") if answer else ""),
    )


# ---------------------------------------------------------------------------
# Tier 0 dimension scorers (unchanged deterministic logic)
# ---------------------------------------------------------------------------

def _grade_name_match(question: dict, answer: Optional[dict]) -> float:
    """Score 1.0/0.7/0.0 for control name/ID matching."""
    if not answer or not answer.get("answered"):
        return 0.0

    target = question.get("target_control") or ""
    answer_text = (answer.get("answer_text", "") or "").lower()

    # Exact control ID match
    if target and target.lower() in answer_text:
        return 1.0

    # Check ground truth name
    gt_name = question.get("ground_truth_name", "")
    if gt_name and gt_name.lower() in answer_text:
        return 1.0

    # Partial: any significant word from control name
    if gt_name:
        words = [w for w in gt_name.lower().split() if len(w) > 3]
        if words and any(w in answer_text for w in words):
            return 0.7

    return 0.0


def _grade_technique_coverage(question: dict, answer: Optional[dict]) -> float:
    """Fraction of expected techniques found in answer."""
    expected = question.get("expected_techniques", [])
    if not expected:
        return 1.0  # No techniques expected = pass by default

    if not answer or not answer.get("answered"):
        return 0.0

    answer_text = (answer.get("answer_text", "") or "").lower()
    answer_techniques = set(answer.get("sparta_techniques", []))

    found = 0
    for t in expected:
        t_lower = t.lower()
        if t in answer_techniques:
            found += 1
        elif t_lower in answer_text:
            found += 1
        elif any(at.lower().startswith(t_lower.split(".")[0]) for at in answer_techniques):
            found += 0.5

    return min(1.0, found / len(expected))


def _grade_cm_coverage(question: dict, answer: Optional[dict]) -> float:
    """Fraction of expected countermeasures found in answer."""
    expected = question.get("expected_countermeasures", [])
    if not expected:
        return 1.0

    if not answer or not answer.get("answered"):
        return 0.0

    answer_text = (answer.get("answer_text", "") or "").lower()
    answer_cms = set(answer.get("sparta_countermeasures", []))

    found = 0
    for cm in expected:
        cm_lower = cm.lower()
        if cm in answer_cms:
            found += 1
        elif cm_lower in answer_text:
            found += 1
        elif any(acm.lower().startswith(cm_lower[:4]) for acm in answer_cms):
            found += 0.5

    return min(1.0, found / len(expected))


def _grade_disambiguation(question: dict, intent_result: dict) -> float:
    """Grade disambiguation quality for CLARIFY responses."""
    suggestions = intent_result.get("suggested_questions", [])
    guidance = intent_result.get("persona_guidance", "")

    if not suggestions and not guidance:
        return 0.0

    score = 0.0

    # Has suggestions?
    if suggestions:
        score += 0.4

    # Has persona-voiced guidance text?
    if guidance and len(guidance) > 20:
        score += 0.3

    # Suggestions are relevant (mention SPARTA domain terms)?
    sparta_terms = {"satellite", "spacecraft", "ground station", "uplink", "control",
                    "threat", "attack", "security", "telemetry", "firmware", "cyber",
                    "jamming", "spoofing", "command", "rf", "gps"}
    if suggestions:
        relevant = sum(
            1 for s in suggestions
            if any(term in s.lower() for term in sparta_terms)
        )
        if relevant == len(suggestions):
            score += 0.3
        elif relevant > 0:
            score += 0.15

    return min(1.0, score)


def _grade_error_detection(
    question: dict,
    intent_result: dict,
    answer: Optional[dict],
) -> float:
    """Grade error detection for flawed questions."""
    actual_action = intent_result.get("action", "")

    # Best: correctly identified as NO_MATCH
    if actual_action == "NO_MATCH":
        score = 0.7

        # Bonus: suggested closest valid control
        guidance = intent_result.get("persona_guidance", "")
        if guidance and re.search(r'SV-[A-Z]{2}-\d+', guidance):
            score += 0.3
        return min(1.0, score)

    # Acceptable: returned CLARIFY (recognized something was wrong)
    if actual_action == "CLARIFY":
        return 0.5

    # Bad: returned QUERY with no results
    if answer and not answer.get("answered"):
        return 0.4

    # Worst: returned QUERY with results for a fake control
    return 0.0


def _grade_code_name_match(question: dict, answer: Optional[dict]) -> float:
    """Score 1.0/0.7/0.0 for target file/module matching in code answers."""
    if not answer or not answer.get("answered"):
        return 0.0

    target_file = question.get("target_file", "")
    target_module = question.get("target_module", "")
    answer_text = (answer.get("answer_text", "") or "").lower()

    # Pipeline/analytics questions without a target file — score on content quality
    # These are valid questions about convergence, verdicts, trends, etc.
    if not target_file and not target_module:
        category = question.get("category", "")
        if category == "pipeline":
            # Score based on whether the answer contains relevant pipeline terms
            pipeline_terms = [
                "convergence", "score", "dimension", "pass", "fail",
                "verdict", "trend", "table_fidelity", "content_coverage",
                "section_alignment", "remediation", "pipeline",
            ]
            matches = sum(1 for t in pipeline_terms if t in answer_text)
            if matches >= 3:
                return 1.0
            if matches >= 1:
                return 0.8
            if len(answer_text) > 50:
                return 0.6
            return 0.3
        # Generic no-target question: give partial credit for substance
        if answer_text and len(answer_text) > 50:
            return 0.5
        return 0.3

    # Exact file name match
    if target_file and target_file.lower() in answer_text:
        return 1.0

    # Module name match
    if target_module and target_module.lower() in answer_text:
        return 0.9

    # Partial: step name (e.g. "s05c" from "s05c_table_merger.py")
    if target_file:
        stem = target_file.replace(".py", "").lower()
        # Check step prefix (s00, s05c, etc.)
        parts = stem.split("_")
        if parts and parts[0] in answer_text:
            return 0.7
        # Check descriptive name (table_merger, profile_detector)
        desc = "_".join(parts[1:]) if len(parts) > 1 else ""
        if desc and desc in answer_text:
            return 0.7

    # Has any substance at all?
    if answer_text and len(answer_text) > 50:
        return 0.3

    return 0.0


def _grade_evidence_quality(question: dict, answer: Optional[dict]) -> float:
    """Score code answers on evidence quality: did skills provide real data?"""
    if not answer or not answer.get("answered"):
        return 0.0

    score = 0.0
    source_skills = answer.get("source_skills", [])
    answer_text = answer.get("answer_text", "")

    # Credit for each skill that contributed evidence
    if source_skills:
        score += min(0.5, 0.15 * len(source_skills))

    # Credit for specific code artifacts in the answer
    code_indicators = ["def ", "class ", "import ", "function", "method", "return"]
    pipeline_indicators = [
        "convergence", "score", "dimension", "pass", "fail",
        "verdict", "trend", "trajectory", "remediation",
    ]
    text_lower = answer_text.lower()
    if any(ind in text_lower for ind in code_indicators):
        score += 0.2
    elif any(ind in text_lower for ind in pipeline_indicators):
        score += 0.2  # Pipeline analytics evidence is equally valid

    # Credit for file paths or module references
    if ".py" in answer_text or "pipeline" in text_lower:
        score += 0.15

    # Credit for substantive length (not a stub answer)
    word_count = len(answer_text.split())
    if word_count >= 30:
        score += 0.15
    elif word_count >= 15:
        score += 0.1

    return min(1.0, score)


def _grade_naturalness(text: str) -> float:
    """Grade response naturalness — no pipe separators, no raw JSON."""
    if not text:
        return 0.0

    score = 1.0

    # Penalize pipe-separated content (raw QRA concatenation)
    pipe_count = len(_PIPE_PATTERN.findall(text))
    if pipe_count > 2:
        score -= 0.4
    elif pipe_count > 0:
        score -= 0.2

    # Penalize raw JSON artifacts
    if _JSON_PATTERN.search(text):
        score -= 0.3

    # Penalize raw database field names
    if _RAW_KEY_PATTERN.search(text):
        score -= 0.3

    # Reward conversational length (not too short, not too long)
    word_count = len(text.split())
    if word_count < 10:
        score -= 0.2
    elif word_count > 500:
        score -= 0.1

    return max(0.0, score)


def _composite_to_grade(composite: float) -> str:
    """Convert composite score to letter grade."""
    if composite >= 0.90:
        return "A+"
    elif composite >= 0.80:
        return "A"
    elif composite >= 0.65:
        return "B"
    elif composite >= 0.50:
        return "C"
    else:
        return "F"


# ---------------------------------------------------------------------------
# Aggregation (unchanged)
# ---------------------------------------------------------------------------

def aggregate_grades(results: list[dict]) -> dict:
    """Aggregate grading results into a summary report.

    Returns per-difficulty and overall statistics.
    """
    by_difficulty = {}
    overall_grades = {}
    dimension_scores = {}
    tier_distribution = {}

    for r in results:
        diff = r.get("difficulty", "unknown")
        grade = r.get("grade", "F")

        # Per-difficulty
        if diff not in by_difficulty:
            by_difficulty[diff] = {"total": 0, "grades": {}, "avg_composite": 0.0, "composites": []}
        by_difficulty[diff]["total"] += 1
        by_difficulty[diff]["grades"][grade] = by_difficulty[diff]["grades"].get(grade, 0) + 1
        by_difficulty[diff]["composites"].append(r.get("composite", 0))

        # Overall grades
        overall_grades[grade] = overall_grades.get(grade, 0) + 1

        # Per-dimension averages
        for dim, score in r.get("scores", {}).items():
            if dim not in dimension_scores:
                dimension_scores[dim] = []
            dimension_scores[dim].append(score)

        # Tier distribution (track cascade usage)
        tier = r.get("tier", 0)
        source = r.get("source", "heuristic")
        key = f"tier_{tier}_{source}"
        tier_distribution[key] = tier_distribution.get(key, 0) + 1

    # Compute averages
    for diff, data in by_difficulty.items():
        composites = data.pop("composites")
        data["avg_composite"] = round(sum(composites) / len(composites), 3) if composites else 0

    dimension_avgs = {
        dim: round(sum(scores) / len(scores), 3)
        for dim, scores in dimension_scores.items()
    }

    total = len(results)
    passing = sum(overall_grades.get(g, 0) for g in ("A+", "A", "B"))

    return {
        "total": total,
        "overall_grades": overall_grades,
        "pass_rate": round(passing / total, 3) if total > 0 else 0,
        "a_plus_rate": round(overall_grades.get("A+", 0) / total, 3) if total > 0 else 0,
        "by_difficulty": by_difficulty,
        "dimension_averages": dimension_avgs,
        "tier_distribution": tier_distribution,
    }
