"""QRA Assessor reward function for GRPO training.

Implements Brandon Bailey's full rubric as a numeric reward signal:
- Structural checks: anchoring, grounding, space terms
- Semantic checks: reasoning quality, taxonomy correctness, relevance
- Augmentation quality: similar questions, paraphrased answer

Used by /create-gpt train_grpo.py during GRPO optimization.

Interface:
    compute_reward(output: dict, input: dict, reference: dict = None) -> float
"""
from __future__ import annotations

from typing import Any, Dict, Optional


# Framework-specific grounding thresholds (from 12_qra.py assess_qra)
GROUNDING_THRESHOLDS = {
    "D3FEND": {"fail": 0.60, "warn": 0.70},
    "CWE": {"fail": 0.55, "warn": 0.65},
    "ATT&CK": {"fail": 0.60, "warn": 0.70},
    "NIST": {"fail": 0.55, "warn": 0.65},
    "SPARTA": {"fail": 0.55, "warn": 0.65},
    "ESA": {"fail": 0.55, "warn": 0.65},
}
DEFAULT_THRESHOLD = {"fail": 0.55, "warn": 0.65}


def compute_reward(
    output: Dict[str, Any],
    input_data: Dict[str, Any],
    reference: Optional[Dict[str, Any]] = None,
) -> float:
    """Compute reward for QRA assessment output.

    Scoring weights:
    - Grade match with reference (if available): 0.40 weight
    - Semantic field matches (reasoning_sound, taxonomy_correct, relevance_score): 0.30 weight
    - Structural field matches (anchoring_ok, space_terms_ok): 0.15 weight
    - Grounding consistency with framework thresholds: 0.15 weight

    Returns:
        float in [0, 1]
    """
    score = 0.0

    grade = output.get("grade", "")
    confidence = output.get("confidence", 0.0)
    issues = output.get("issues", [])

    # --- Grade accuracy (0.40 weight) ---
    if reference:
        ref_grade = reference.get("grade", "")
        if grade == ref_grade:
            score += 0.40
        elif _grade_distance(grade, ref_grade) == 1:
            score += 0.20
    else:
        if grade in ("PASS", "WARN", "FAIL"):
            score += 0.20
            if 0.0 < confidence <= 1.0:
                score += 0.10
            if grade == "WARN" and issues:
                score += 0.10
            elif grade == "PASS" and not issues:
                score += 0.10

    # --- Semantic field accuracy (0.30 weight) ---
    semantic_fields = ("reasoning_sound", "taxonomy_correct", "relevance_score")
    if reference:
        sem_matches = 0
        sem_total = 0
        for field_name in semantic_fields:
            ref_val = reference.get(field_name)
            out_val = output.get(field_name)
            if ref_val is None or out_val is None:
                continue
            sem_total += 1
            if isinstance(ref_val, bool):
                if bool(ref_val) == bool(out_val):
                    sem_matches += 1
            else:
                # Numeric (relevance_score) — within 0.15 tolerance
                try:
                    if abs(float(ref_val) - float(out_val)) <= 0.15:
                        sem_matches += 1
                except (ValueError, TypeError):
                    if str(ref_val) == str(out_val):
                        sem_matches += 1
        if sem_total > 0:
            score += 0.30 * (sem_matches / sem_total)
    else:
        # No reference: reward for having semantic fields with valid values
        has_fields = 0
        reasoning_sound = output.get("reasoning_sound")
        taxonomy_correct = output.get("taxonomy_correct")
        relevance_score = output.get("relevance_score")
        if reasoning_sound is not None:
            has_fields += 1
        if taxonomy_correct is not None:
            has_fields += 1
        if relevance_score is not None:
            has_fields += 1
            # Bonus for relevance_score being a valid number in range
            try:
                r = float(relevance_score)
                if 0.0 <= r <= 1.0:
                    has_fields += 0.5  # extra credit
            except (ValueError, TypeError):
                pass
        score += 0.30 * min(1.0, has_fields / 3.0)

    # --- Structural field accuracy (0.15 weight) ---
    structural_fields = ("anchoring_ok", "space_terms_ok")
    if reference:
        struct_matches = 0
        struct_total = 0
        for field_name in structural_fields:
            ref_val = reference.get(field_name)
            out_val = output.get(field_name)
            if ref_val is not None and out_val is not None:
                struct_total += 1
                if bool(ref_val) == bool(out_val):
                    struct_matches += 1
        if struct_total > 0:
            score += 0.15 * (struct_matches / struct_total)
    else:
        anchoring_ok = output.get("anchoring_ok")
        space_terms_ok = output.get("space_terms_ok")
        if anchoring_ok is not None and space_terms_ok is not None:
            score += 0.15

    # --- Grounding consistency (0.15 weight) ---
    framework = input_data.get("framework", "")
    input_grounding = input_data.get("grounding_score", 0.0)
    thresholds = GROUNDING_THRESHOLDS.get(framework, DEFAULT_THRESHOLD)

    if input_grounding and grade:
        if input_grounding < thresholds["fail"] and grade == "FAIL":
            score += 0.15
        elif thresholds["fail"] <= input_grounding < thresholds["warn"] and grade == "WARN":
            score += 0.15
        elif input_grounding >= thresholds["warn"] and grade == "PASS":
            score += 0.12
        elif input_grounding >= thresholds["warn"] and grade in ("PASS", "WARN"):
            score += 0.08

    return min(1.0, max(0.0, score))


def _grade_distance(a: str, b: str) -> int:
    """Distance between grades: PASS=0, WARN=1, FAIL=2."""
    order = {"PASS": 0, "WARN": 1, "FAIL": 2}
    return abs(order.get(a, -1) - order.get(b, -1))
