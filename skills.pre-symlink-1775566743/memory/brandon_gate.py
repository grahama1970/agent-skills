#!/usr/bin/env python3
"""Brandon Bailey Simulacrum - Grounding Gate.

Filters QRA responses based on grounding score threshold.
Brandon requires 0.7 minimum grounding to prevent hallucination in security-critical responses.

Usage:
    from brandon_gate import filter_by_grounding, format_uncertain_response

    accepted, rejected = filter_by_grounding(qras)
    if not accepted:
        response = format_uncertain_response(query, len(rejected))
"""

import re
from typing import Any

# Brandon's grounding threshold - higher than default 0.55 for security domain
BRANDON_GROUNDING_THRESHOLD = 0.70

# Hallucination/speculation markers — QRAs containing these are downgraded
# These indicate the LLM was speculating rather than grounding in source material
SPECULATION_MARKERS = re.compile(
    r'hypothesized|assumed without evidence|speculated|inferred without evidence|'
    r'it is assumed that|we can assume|this is speculative|unverified claim|'
    r'likely based on assumption|probably would|theoretically might|'
    r'one could imagine|it stands to reason',
    re.IGNORECASE,
)

# Penalty applied to grounding score when speculation markers found
SPECULATION_PENALTY = 0.15


def filter_by_grounding(
    qras: list[dict[str, Any]],
    threshold: float = BRANDON_GROUNDING_THRESHOLD,
) -> tuple[list[dict], list[dict]]:
    """Split QRAs into accepted and rejected based on grounding threshold.

    Args:
        qras: List of QRA dicts with 'grounding_score' field
        threshold: Minimum grounding score (default 0.70 for Brandon)

    Returns:
        Tuple of (accepted_qras, rejected_qras)
    """
    accepted = []
    rejected = []

    for qra in qras:
        score = qra.get("grounding_score", 0.0)
        answer_text = qra.get("answer", "")
        reasoning_text = qra.get("reasoning", "")

        # Check for speculation markers — penalize grounding score
        has_speculation = bool(
            SPECULATION_MARKERS.search(answer_text)
            or SPECULATION_MARKERS.search(reasoning_text)
        )
        if has_speculation:
            score = max(0.0, score - SPECULATION_PENALTY)

        if score >= threshold:
            if has_speculation:
                qra = {**qra, "_speculation_detected": True, "grounding_score": score}
            accepted.append(qra)
        else:
            reason = f"Below {threshold} threshold"
            if has_speculation:
                reason += " (speculation markers detected, penalty applied)"
            rejected.append({
                "qra_id": qra.get("qra_id", "unknown"),
                "grounding_score": score,
                "question": qra.get("question", "")[:100],
                "reason": reason,
            })

    return accepted, rejected


def format_uncertain_response(query: str, rejected_count: int) -> str:
    """Generate 'I'm uncertain' response when all QRAs below threshold.

    This is a key safety mechanism - Brandon admits uncertainty rather than
    providing potentially unreliable security guidance.

    Args:
        query: The user's original question
        rejected_count: Number of QRAs that failed the grounding check

    Returns:
        A response explaining the uncertainty
    """
    return f"""I found {rejected_count} potential answer(s) related to your question, but I'm not confident enough in the source alignment to give you a definitive answer.

This could mean:
- The question combines multiple SPARTA concepts that aren't directly linked
- The source material doesn't directly address this specific scenario
- More specific phrasing with SPARTA terminology might help

**Options:**
1. Rephrase with specific SPARTA control IDs or technique names
2. Ask about a narrower aspect of the question
3. I can show you what I found with appropriate caveats (say "show anyway")

For security-critical decisions, please consult The Aerospace Corporation directly."""


def compute_response_confidence(
    accepted_qras: list[dict],
    rejected_count: int,
) -> dict[str, Any]:
    """Compute overall response confidence metrics.

    Args:
        accepted_qras: QRAs that passed the grounding threshold
        rejected_count: Number of QRAs that failed

    Returns:
        Dict with confidence metrics for audit logging
    """
    if not accepted_qras:
        return {
            "confidence_level": "none",
            "avg_grounding": 0.0,
            "qras_used": 0,
            "qras_rejected": rejected_count,
            "recommendation": "Ask user to rephrase or escalate to human expert",
        }

    scores = [qra.get("grounding_score", 0.0) for qra in accepted_qras]
    avg_score = sum(scores) / len(scores)
    min_score = min(scores)

    if avg_score >= 0.9 and min_score >= 0.8:
        level = "high"
        rec = "Safe to answer with citations"
    elif avg_score >= 0.75:
        level = "medium"
        rec = "Answer with explicit caveats"
    else:
        level = "low"
        rec = "Consider asking for clarification"

    return {
        "confidence_level": level,
        "avg_grounding": round(avg_score, 3),
        "min_grounding": round(min_score, 3),
        "qras_used": len(accepted_qras),
        "qras_rejected": rejected_count,
        "recommendation": rec,
    }


def format_grounded_response(
    accepted_qras: list[dict],
    confidence: dict[str, Any],
) -> str:
    """Format a response using grounded QRAs.

    Args:
        accepted_qras: QRAs that passed the grounding threshold
        confidence: Confidence metrics from compute_response_confidence

    Returns:
        Formatted response with citations
    """
    if not accepted_qras:
        return ""

    # Sort by grounding score, highest first
    sorted_qras = sorted(
        accepted_qras,
        key=lambda q: q.get("grounding_score", 0),
        reverse=True,
    )

    parts = []

    # Add caveat if confidence is not high
    if confidence["confidence_level"] != "high":
        parts.append(
            f"*Note: Response confidence is {confidence['confidence_level']} "
            f"(avg grounding: {confidence['avg_grounding']:.0%})*\n"
        )

    # Use top QRA as primary answer
    top_qra = sorted_qras[0]
    parts.append(top_qra.get("answer", ""))

    # Add citations
    citations = top_qra.get("citations", [])
    if citations:
        parts.append("\n\n**Sources:**")
        for i, cit in enumerate(citations[:3], 1):
            if cit and len(cit) > 10:
                parts.append(f'\n{i}. "{cit[:150]}..."')

    # Reference control/technique if available
    control_id = top_qra.get("control_id")
    technique_id = top_qra.get("technique_id")
    if control_id or technique_id:
        refs = []
        if control_id:
            refs.append(f"Control: {control_id}")
        if technique_id:
            refs.append(f"Technique: {technique_id}")
        parts.append(f"\n\n*SPARTA Reference: {', '.join(refs)}*")

    return "".join(parts)


def verify_taxonomy_tags(qra: dict[str, Any]) -> list[str]:
    """Verify that taxonomy tags are coherent with answer content.

    Returns list of incoherent tags that should be removed.
    Tags must have evidence in the answer text to be considered valid.

    Args:
        qra: QRA dict with 'answer', 'conceptual_tags', 'tactical_tags'

    Returns:
        List of tag names that lack evidence in the answer
    """
    TAG_EVIDENCE = {
        "Resilience": ["recover", "redundan", "failover", "backup", "restor", "resilien", "fault.toleran"],
        "Stealth": ["covert", "stealth", "evad", "undetect", "hidden", "conceal", "obfuscat"],
        "Precision": ["precis", "accura", "calibrat", "exact", "fine.grain", "targeted"],
        "Fragility": ["fragil", "brittle", "vulnerab", "single.point", "weak"],
        "Corruption": ["corrupt", "tamper", "manipulat", "poison", "inject", "modif"],
        "Loyalty": ["trust", "authentic", "verif", "integrit", "loyal", "attest"],
    }

    answer = (qra.get("answer", "") + " " + qra.get("reasoning", "")).lower()
    incoherent = []

    for tag_list_name in ("conceptual_tags", "tactical_tags"):
        tags = qra.get(tag_list_name, [])
        for tag in tags:
            tag_upper = tag.strip()
            evidence_patterns = TAG_EVIDENCE.get(tag_upper)
            if evidence_patterns is None:
                continue  # Unknown tag — don't flag
            has_evidence = any(
                re.search(pattern, answer) for pattern in evidence_patterns
            )
            if not has_evidence:
                incoherent.append(tag_upper)

    return incoherent


if __name__ == "__main__":
    # Quick self-test
    test_qras = [
        {"qra_id": "1", "grounding_score": 0.85, "answer": "High grounding answer"},
        {"qra_id": "2", "grounding_score": 0.65, "answer": "Low grounding answer"},
        {"qra_id": "3", "grounding_score": 0.72, "answer": "Medium grounding answer"},
        {"qra_id": "4", "grounding_score": 0.91, "answer": "Very high grounding"},
    ]

    accepted, rejected = filter_by_grounding(test_qras)
    print(f"Accepted: {len(accepted)} (IDs: {[q['qra_id'] for q in accepted]})")
    print(f"Rejected: {len(rejected)} (IDs: {[q['qra_id'] for q in rejected]})")

    confidence = compute_response_confidence(accepted, len(rejected))
    print(f"Confidence: {confidence}")

    assert len(accepted) == 3, f"Expected 3 accepted, got {len(accepted)}"
    assert len(rejected) == 1, f"Expected 1 rejected, got {len(rejected)}"
    assert rejected[0]["qra_id"] == "2", "Wrong QRA rejected"

    print("\nAll tests passed!")
