#!/usr/bin/env python3
"""Classifier-based validation for SPARTA QRAs.

Uses the trained DistilBERT space classifier to identify QRAs with
generic IT content that should be space-specific.

Integration with reality-check-sparta assessment pipeline.
"""

import json
import sys
from pathlib import Path
from typing import Any

# Add memory skill to path for classifier import
MEMORY_SKILL_PATH = Path(__file__).resolve().parent.parent / "memory"
sys.path.insert(0, str(MEMORY_SKILL_PATH))

try:
    from space_classifier import SpaceClassifier, classify_query
    CLASSIFIER_AVAILABLE = True
except ImportError:
    CLASSIFIER_AVAILABLE = False
    SpaceClassifier = None
    classify_query = None


def validate_qra_with_classifier(
    qra_answer: str,
    qra_question: str = "",
    threshold: float = 0.7,
) -> dict[str, Any]:
    """Validate a single QRA using the space classifier.

    NOTE: The classifier was trained on full Q+A pairs, so we must classify
    the combined text to match training format. Answer-only classification
    was causing false "generic_it" results because the space context comes
    from the question framing.

    Args:
        qra_answer: The answer text to validate
        qra_question: Question text (required for accurate classification)
        threshold: Confidence threshold for flagging generic content

    Returns:
        Validation result with classification and issues
    """
    if not CLASSIFIER_AVAILABLE:
        return {
            "status": "SKIP",
            "reason": "Classifier not available",
            "classification": None,
        }

    # PRIMARY: Classify question + answer together (matches training format)
    # The classifier was trained on "Question: ... Answer: ..." pairs
    combined = f"Question: {qra_question}\nAnswer: {qra_answer}"
    combined_result = classify_query(combined)

    # SECONDARY: Also classify answer alone for borderline detection
    answer_result = classify_query(qra_answer)

    issues = []

    # Flag if combined Q+A is classified as generic IT with high confidence
    if not combined_result["is_space"] and combined_result["confidence"] > threshold:
        issues.append(
            f"GENERIC_IT: QRA classified as generic_it "
            f"(confidence: {combined_result['confidence']:.2%})"
        )

    # Informational: if answer alone is generic but combined is space, that's expected
    # (the question provides space context) - not an issue, just a note
    if combined_result["is_space"] and not answer_result["is_space"]:
        # This is actually GOOD - question provides space context as intended
        pass

    return {
        "status": "FAIL" if issues else "PASS",
        "issues": issues,
        "answer_classification": answer_result,
        "combined_classification": combined_result,
    }


def check_qra_space_specificity(
    conn,
    sample_size: int = 50,
    threshold: float = 0.7,
) -> dict[str, Any]:
    """Check QRAs for space-specific content using classifier.

    Args:
        conn: DuckDB connection
        sample_size: Number of QRAs to sample
        threshold: Confidence threshold for flagging

    Returns:
        Assessment results with statistics and flagged QRAs
    """
    if not CLASSIFIER_AVAILABLE:
        return {
            "status": "SKIP",
            "reason": "Classifier not available - install transformers and torch",
            "checked": 0,
            "flagged": [],
        }

    # Sample QRAs with diverse grounding scores
    results = conn.execute(f"""
        SELECT qra_id, control_id, question, answer, grounding_score
        FROM qra
        WHERE answer IS NOT NULL AND LENGTH(answer) > 50
        ORDER BY RANDOM()
        LIMIT {sample_size}
    """).fetchall()

    flagged = []
    space_count = 0
    generic_count = 0

    for row in results:
        qra_id, control_id, question, answer, grounding = row

        validation = validate_qra_with_classifier(
            qra_answer=answer,
            qra_question=question,
            threshold=threshold,
        )

        if validation["status"] == "FAIL":
            flagged.append({
                "qra_id": qra_id,
                "control_id": control_id,
                "question_preview": question[:100] if question else "",
                "answer_preview": answer[:200] if answer else "",
                "grounding_score": grounding,
                "issues": validation["issues"],
                # Use combined classification (matches training format)
                "space_prob": validation["combined_classification"]["all_probs"].get("space_cybersecurity", 0),
                "generic_prob": validation["combined_classification"]["all_probs"].get("generic_it", 0),
            })
            generic_count += 1
        else:
            space_count += 1

    total = len(results)
    generic_pct = (generic_count / total * 100) if total > 0 else 0

    # Determine status based on Brandon Bailey's grading scale
    # A+ EXCELLENT: <20% generic
    # A GOOD: 20-30% generic
    # B ACCEPTABLE: 30-50% generic
    # C NEEDS WORK: 50-70% generic
    # F FAIL: >70% generic
    if generic_pct >= 70:
        status = "FAIL"
        grade = "F"
    elif generic_pct >= 50:
        status = "WARN"
        grade = "C"
    elif generic_pct >= 30:
        status = "WARN"
        grade = "B"
    elif generic_pct >= 20:
        status = "PASS"
        grade = "A"
    else:
        status = "PASS"
        grade = "A+"

    issues = []
    if generic_count > 0:
        issues.append(f"{generic_count} QRAs classified as generic IT ({generic_pct:.1f}%)")

    return {
        "status": status,
        "grade": grade,
        "checked": total,
        "space_specific": space_count,
        "generic_it": generic_count,
        "generic_pct": round(generic_pct, 1),
        "issues": issues,
        "flagged": flagged[:10],  # Top 10 worst offenders
        "threshold": threshold,
    }


def classifier_status() -> dict[str, Any]:
    """Get classifier availability status."""
    if not CLASSIFIER_AVAILABLE:
        return {
            "available": False,
            "reason": "Classifier module not found or dependencies missing",
        }

    try:
        classifier = SpaceClassifier()
        # Quick test
        test_result = classifier.classify("RF jamming attack on satellite")
        return {
            "available": True,
            "model_path": str(classifier.model_path),
            "test_classification": test_result["label"],
            "test_confidence": round(test_result["confidence"], 3),
        }
    except Exception as e:
        return {
            "available": False,
            "reason": str(e),
        }


if __name__ == "__main__":
    import duckdb

    print("Classifier Status:")
    status = classifier_status()
    print(json.dumps(status, indent=2))

    if status.get("available"):
        # Test with sample queries
        test_queries = [
            "How do I detect RF jamming attacks on satellite uplinks?",
            "How do I configure a firewall rule?",
            "What controls protect spacecraft telemetry from spoofing?",
            "How do I update Windows?",
        ]

        print("\nTest Classifications:")
        for query in test_queries:
            result = classify_query(query)
            label = "SPACE" if result["is_space"] else "GENERIC"
            print(f"  [{label}] {result['confidence']:.1%} - {query[:50]}...")
