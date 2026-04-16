"""Prompt constants and taxonomy definitions for semantic grading.

Contains the shared response type taxonomy, grading rules, dimensions,
and the main grading prompt template used by semantic_grader.py.
"""

# --------------------------------------------------------------------------- #
# GLOBAL SHARED RESPONSE TYPE TAXONOMY
# Used by student, teacher, and Brandon self-grade prompts.
# NO other taxonomy is permitted for grading responses.
# --------------------------------------------------------------------------- #
RESPONSE_TYPES = ("CITED", "NO-COVERAGE", "CLARIFY-REQUEST", "MISREAD", "HALLUCINATED")

RESPONSE_TYPE_TAXONOMY = """RESPONSE TYPE CLASSIFICATION (shared taxonomy -- student and teacher use the SAME types):
1. CITED: The answer provides substantive information citing specific controls/QRAs -> verify each citation against the QRA ground truth below
2. NO-COVERAGE: The answer honestly says "I don't have coverage", "I don't recognize that control", or asks to verify an entity -> this is CORRECT behavior when the database lacks matching QRAs. Also applies when the system correctly rejects a fake/adversarial control. "I don't know" + a follow-up question is the IDEAL NO-COVERAGE pattern.
3. CLARIFY-REQUEST: The system asks for clarification BEFORE attempting an answer. Shows the system knows its limits and collaborates rather than guessing. Examples: "Could you specify which control?", "Did you mean SV-SP-8 or SV-SP-9?", "What aspect of space systems security are you interested in?" This is CORRECT behavior for ambiguous or vague queries.
4. MISREAD: The answer says "I don't have coverage" BUT about a DIFFERENT topic than what the user asked. Example: user asks about "F-36-SRS-*" requirements, system says "I don't have coverage for SP-1." The system misread or hallucinated the question topic. This is a comprehension failure, NOT honest no-coverage.
5. HALLUCINATED: The answer invents frameworks, protocols, or control details NOT found in the QRA ground truth -> grade F"""

RESPONSE_TYPE_GRADING_RULES = """GRADING RULES BY RESPONSE TYPE:

**For NO-COVERAGE responses** (system honestly says it doesn't know or correctly rejects fabricated queries):
- If the system correctly rejects a fabricated control/framework -> grade A (caught the trap)
- If the system says "I don't have coverage" for a legitimate gap AND asks a follow-up question -> grade B (honest answer + good practice)
- If the system says "I don't have coverage" for a legitimate gap without follow-up -> grade B (still honest)
- qra_citation_accuracy = 1.0 (no citations needed -- honesty IS the correct response)
- The PRIMARY signals are error_detection and disambiguation_handling
- Grade F ONLY if the system fabricated information DESPITE claiming no coverage

**For CLARIFY-REQUEST responses** (system asks for clarification before answering):
- If expected_action was CLARIFY and the system asked for clarification -> grade A (detected ambiguity correctly)
- If expected_action was QUERY but the system asked for clarification -> grade B max (too cautious, but honest > hallucinated)
- If expected_action was QUERY on a clearly answerable question and the system clarified -> grade C (over-clarifying)
- qra_citation_accuracy = 1.0 (no citations needed -- clarifying IS the correct response for ambiguous queries)
- The PRIMARY signals are disambiguation_handling and initial_response_quality
- Grade F ONLY if the system fabricated information within the clarify request itself

**For MISREAD responses** (system says "I don't know" about the WRONG topic):
- The system misread or hallucinated the question topic -- it's answering a question nobody asked
- Example: user asks about "F-36-SRS-*" requirements, system asks about "SP-1" instead
- qra_citation_accuracy = 0.3 (comprehension failure, not honest no-coverage)
- Grade C if the system eventually corrected itself, F if it persisted in the misread
- This is NOT the same as honest NO-COVERAGE -- the system failed to understand the question

**For CITED responses** (system provides substantive answers with QRA citations):
- QRA citation accuracy is the PRIMARY grading signal
- For each claim in the answer: is it in the QRA GROUND TRUTH? If YES -> VERIFIED. If NO -> FABRICATED.
- If the answer cites NO real controls from QRA ground truth -> grade F
- If the answer invents frameworks not in ground truth -> grade F (reclassify as HALLUCINATED)
- ONLY grade B or above if the answer cites REAL controls with CORRECT information

**For HALLUCINATED responses** (system invents controls/frameworks):
- Always grade F -- fabricating information is never acceptable"""

# 8-dimension rubric (7 original + qra_citation_accuracy)
GRADING_DIMENSIONS = [
    "initial_response_quality",
    "disambiguation_handling",
    "error_detection",
    "follow_up_quality",
    "response_naturalness",
    "domain_accuracy",
    "session_coherence",
    "qra_citation_accuracy",
    "reasoning_chain_soundness",
]

def deterministic_only_grade(anchor: dict, citation_result: dict, model: str) -> dict:
    """Fallback grade using only deterministic signals when LLM is unavailable.

    Still benefits from /lean4-prove, /assistant, /memory trace evidence
    that was collected in Stage 1 -- just no LLM qualitative adjustment.
    """
    # Scale deterministic score to full range (it's 60% max)
    composite = anchor["deterministic_score"] / 0.60  # Scale to 0-1
    composite = min(composite, 1.0) * 0.85  # Cap at B+ without LLM qualitative

    if composite >= 0.80:
        grade = "A"
    elif composite >= 0.65:
        grade = "B"
    elif composite >= 0.50:
        grade = "C"
    else:
        grade = "F"

    scores = {d: 0.5 for d in GRADING_DIMENSIONS}
    # Override deterministic dimensions with actual evidence
    scores["qra_citation_accuracy"] = anchor["citation_ratio"]
    scores["reasoning_chain_soundness"] = anchor["lean4_score"]
    scores["assistant_confidence"] = anchor.get("assistant_confidence", 0.0)

    return {
        "grade": grade,
        "composite": composite,
        "scores": scores,
        "qra_citations_verified": citation_result.get("verified", 0),
        "qra_citations_total": citation_result.get("total", 0),
        "citation_details": citation_result.get("details", []),
        "rationale": (
            f"Deterministic-only grade (LLM unavailable). "
            f"Sources: {', '.join(anchor.get('sources_available', ['citation_verification']))}"
        ),
        "model_used": model,
        "reasoning_sound": None,
        "taxonomy_correct": None,
        "issues": ["llm_unavailable"],
        "tier": 1,
        "deterministic_anchor": anchor,
        "evidence_sources": anchor.get("sources_available", []),
    }


def fallback_grade(
    citation_result: dict,
    model: str,
    expected_action: str = "QUERY",
    difficulty: str = "medium",
) -> dict:
    """Fallback when LLM grading is unavailable."""
    verified = citation_result.get("verified", 0)
    total = citation_result.get("total", 0)
    citation_ratio = verified / max(total, 1)

    # CLARIFY-aware fallback: if no citations because the response was a
    # clarification request, grade based on whether CLARIFY was appropriate.
    if total == 0 and (expected_action == "CLARIFY" or difficulty == "ambiguous"):
        grade, composite = "A", 0.82
        rationale = (
            f"Fallback: LLM unavailable. CLARIFY response with no citations "
            f"is correct for {difficulty} difficulty (expected_action={expected_action})"
        )
        scores = {dim: 0.82 for dim in GRADING_DIMENSIONS}
        scores["disambiguation_handling"] = 0.95
        scores["qra_citation_accuracy"] = 1.0  # No citations needed
    elif total == 0 and expected_action == "QUERY":
        grade, composite = "C", 0.55
        rationale = (
            f"Fallback: LLM unavailable. No citations on expected QUERY. "
            f"May be unnecessary clarification."
        )
        scores = {dim: 0.55 for dim in GRADING_DIMENSIONS}
    else:
        # Conservative grading from citation ratio alone
        if citation_ratio >= 0.8:
            grade, composite = "B", 0.75
        elif citation_ratio >= 0.5:
            grade, composite = "C", 0.60
        else:
            grade, composite = "F", 0.40
        rationale = f"Fallback: LLM unavailable, graded on citation ratio ({verified}/{total})"
        scores = {dim: composite for dim in GRADING_DIMENSIONS}

    return {
        "grade": grade,
        "composite": composite,
        "scores": scores,
        "qra_citations_verified": verified,
        "qra_citations_total": total,
        "rationale": rationale,
        "model_used": model,
        "reasoning_sound": None,
        "taxonomy_correct": None,
        "issues": ["llm_unavailable"],
        "tier": 0,
    }


def format_process_evidence(anchor: dict, evidence: dict) -> str:
    """Format evidence_packet as read-only context for the LLM grading prompt.

    The LLM sees ALL deterministic evidence but CANNOT override it.
    This is the bridge between Stage 1 (evidence collection) and Stage 2 (LLM).
    """
    lines = [
        "DETERMINISTIC EVIDENCE (already computed -- do NOT override these scores):",
        f"- Citation verification: {anchor['citation_ratio']:.0%} "
        f"({evidence.get('citation', {}).get('verified', 0)}/{evidence.get('citation', {}).get('total', 0)} "
        f"claims verified via ArangoDB lookup)",
    ]

    if anchor["lean4_score"] > 0:
        lean4 = evidence.get("lean4", {})
        lines.append(
            f"- Lean4 formal proof: {anchor['lean4_score']:.0%} of reasoning steps verified "
            f"({lean4.get('steps_verified', 0)}/{lean4.get('steps_total', 0)} steps)"
        )

    assistant = evidence.get("assistant", {})
    if assistant:
        tier_label = {0: "heuristic", 0.5: "classifier", 1.5: "local GPT", 2: "scillm teacher"}
        tier = assistant.get("tier", 2)
        lines.append(
            f"- Trained classifier: confidence={assistant.get('confidence', 0):.0%} "
            f"(tier {tier} -- {tier_label.get(tier, 'unknown')}, source={assistant.get('source', 'N/A')})"
        )

    bridge_tags = evidence.get("bridge_tags_matched", [])
    if bridge_tags:
        lines.append(
            f"- Taxonomy bridge overlap: {len(bridge_tags)} tags matched "
            f"({', '.join(bridge_tags[:5])})"
        )

    graph_connected = evidence.get("graph_connected_count", 0)
    if graph_connected > 0:
        lines.append(
            f"- Graph connectivity: {graph_connected} results connected via graph traversal"
        )

    trace_verified = evidence.get("trace_claims_verified", 0)
    trace_total = evidence.get("trace_claims_total", 0)
    if trace_total > 0:
        lines.append(
            f"- Trace claim verification: {trace_verified}/{trace_total} claims "
            f"verified via /memory trace"
        )

    if anchor["richness_score"] > 0:
        lines.append(f"- Coverage richness: {anchor['richness_score']:.0%} (framework depth score)")

    if anchor["delta_bonus"] != 0:
        direction = "improved" if anchor["delta_bonus"] > 0 else "regressed"
        lines.append(f"- Self-correction: system {direction} across rounds")

    fw = evidence.get("framework_coverage", {})
    if fw:
        lines.append(f"- Framework coverage: {', '.join(f'{k}={v}' for k, v in fw.items())}")

    sources = evidence.get("sources_called", [])
    lines.append(f"\nEvidence sources used: {', '.join(sources) if sources else 'citation_verification only'}")
    lines.append(f"Deterministic anchor: {anchor['deterministic_score']:.2f}/0.60 (your qualitative scores control the remaining 0.40)")

    return "\n".join(lines)


SEMANTIC_GRADE_PROMPT = """You are a quality auditor for SPARTA space systems conversations.

IMPORTANT: Citation accuracy, Lean4 proofs, and taxonomy overlap are ALREADY COMPUTED
from deterministic sources (ArangoDB lookups, formal verification, taxonomy intersection).
You score ONLY the qualitative dimensions that require human-like judgment.

""" + RESPONSE_TYPE_TAXONOMY + """

FULL CONVERSATION TRANSCRIPT:
{transcript}

CURRENT TURN BEING GRADED:
Question: {question}
Answer: {answer}

SEED QUESTION METADATA:
- Difficulty: {difficulty}
- Expected action: {expected_action}
- Target control: {target_control}

QRA GROUND TRUTH (from ArangoDB -- verified source material):
{qra_ground_truth}

{process_evidence}

YOUR TASK: Score ONLY these 4 qualitative dimensions using a COARSE 4-POINT SCALE:

For each dimension, assign ONE of these integer scores:
  0 = absent/wrong -- dimension is completely missing or incorrect
  1 = weak/partial -- some attempt but major gaps or errors
  2 = adequate/correct -- meets expectations, addresses the question properly
  3 = strong/exemplary -- expert-level quality, reads like a domain specialist

Dimensions to score:
1. **response_naturalness**: Is the answer natural language? No raw JSON, pipe separators,
   database artifacts, or robotic formatting? A good answer reads like an expert explaining.
2. **domain_accuracy**: Are SPARTA terms, control IDs, techniques, and countermeasures
   used correctly? Does the answer demonstrate domain expertise (not just parroting)?
3. **session_coherence**: Does the conversation flow logically? Does each response build
   on previous context? Are follow-ups relevant to the original question?
4. **disambiguation_handling**: For ambiguous questions, did the system clarify appropriately?
   For clear questions, did it answer directly without unnecessary clarification?

Also classify the response type and provide brief rationale.

STEP 1: CLASSIFY RESPONSE TYPE
- CITED: Cites specific controls/QRAs with substantive information
- NO-COVERAGE: Honestly says "I don't have coverage" (correct behavior for gaps)
- CLARIFY-REQUEST: Asks for clarification before answering
- MISREAD: Says "I don't know" about wrong topic (comprehension failure)
- HALLUCINATED: Invents information not in QRA ground truth

STEP 2: Score the 4 qualitative dimensions above using ONLY integers 0, 1, 2, or 3.

SCORING CALIBRATION:
- 3 = Expert-level, reads like a SPARTA domain specialist wrote it
- 2 = Good, clearly uses correct terminology and addresses the question
- 1 = Poor, mostly off-topic, generic, or shows misunderstanding
- 0 = Terrible, wrong domain, hallucinated, or incoherent

If the answer substantively addresses the question with correct SPARTA concepts, score 2+.
If the answer uses QRA ground truth content accurately, score domain_accuracy 3.

Also score these additional dimensions (same 0-3 scale):
- **initial_response_quality**: Was first response appropriate for question type?
- **error_detection**: Caught fake/adversarial control references?
- **follow_up_quality**: Handled persona pushback well?

DO NOT score qra_citation_accuracy or reasoning_chain_soundness -- these are deterministic.

Return JSON only:
{{
  "response_type": "CITED|NO-COVERAGE|CLARIFY-REQUEST|MISREAD|HALLUCINATED",
  "scores": {{
    "response_naturalness": 2,
    "domain_accuracy": 2,
    "session_coherence": 2,
    "disambiguation_handling": 2,
    "initial_response_quality": 2,
    "error_detection": 2,
    "follow_up_quality": 2
  }},
  "reasoning_sound": true,
  "taxonomy_correct": true,
  "rationale": "Brief explanation of qualitative assessment"
}}"""
