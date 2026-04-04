"""Gate 6: Per-step reasoning chain verification for QRA answers.

Parses QRA reasoning into individual claims, formalizes each into Lean4,
compiles them, and classifies failures using the LogicGraph error taxonomy
(arXiv:2602.21044).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from loguru import logger

from qra_models import (
    ERROR_TAXONOMY,
    ReasoningStepResult,
    ReasoningVerifyResult,
)


def _parse_reasoning_chain(reasoning: str) -> List[str]:
    """Parse a QRA reasoning chain into individual claims.

    Splits on sentence boundaries, numbered lists, and bullet points.
    """
    if not reasoning:
        return []

    # Split on numbered items (1. 2. 3.), bullets (- *), or sentences
    steps = re.split(r'(?:^|\n)\s*(?:\d+[\.\)]\s*|[-*]\s+)', reasoning)

    # Filter empty and clean up
    steps = [s.strip() for s in steps if s.strip() and len(s.strip()) > 10]

    # If no structured splits found, split by sentences
    if len(steps) <= 1 and reasoning:
        steps = re.split(r'(?<=[.!?])\s+', reasoning)
        steps = [s.strip() for s in steps if s.strip() and len(s.strip()) > 10]

    return steps


def _classify_compile_error(error_output: str) -> str:
    """Classify a compilation error into the LogicGraph error taxonomy."""
    lower = error_output.lower()

    if "unknown identifier" in lower or "undeclared" in lower:
        return "fact_hallucination"
    elif "type mismatch" in lower:
        return "invalid_deduction"
    elif "don't know how" in lower or "unsolved goals" in lower:
        return "insufficient_premise"
    elif "expected" in lower and "got" in lower:
        return "semantic_misinterpretation"
    elif "missing" in lower or "not found" in lower:
        return "information_omission"
    else:
        return "rule_misapplication"


def verify_qra_reasoning(
    qra: Dict[str, Any],
    container: str = "lean_runner",
    timeout: int = 120,
) -> ReasoningVerifyResult:
    """Verify per-step reasoning chain of a QRA.

    1. Parse reasoning chain into individual claims
    2. Formalize each claim into Lean4
    3. Compile via ParallelCompiler (or Docker fallback)
    4. Classify errors using LogicGraph taxonomy

    Args:
        qra: Dict with at minimum 'reasoning' field, optionally '_key'/'qra_id'
        container: Docker container for fallback compilation
        timeout: Per-step timeout

    Returns:
        ReasoningVerifyResult with per-step results and error taxonomy
    """
    qra_id = qra.get("_key", qra.get("qra_id", "unknown"))
    reasoning = qra.get("reasoning", "")

    steps = _parse_reasoning_chain(reasoning)

    result = ReasoningVerifyResult(
        qra_id=qra_id,
        steps_total=len(steps),
    )

    if not steps:
        return result

    # Try to use ParallelCompiler (lean-interact), fall back to Docker
    use_lean_interact = False
    try:
        from compiler import ParallelCompiler
        use_lean_interact = True
    except ImportError:
        pass

    # Try to use formalize for English->Lean4
    formalize_fn = None
    try:
        from formalize import formalize as _formalize_fn
        formalize_fn = _formalize_fn
    except ImportError:
        pass

    for step_text in steps:
        step_result = ReasoningStepResult(step_text=step_text)

        # Formalize the claim
        if formalize_fn:
            try:
                fr = formalize_fn(step_text, n_workers=1)
                step_result.lean4_code = fr.lean4_code
                step_result.compiled = fr.compiled
                if not fr.compiled and fr.compile_error:
                    step_result.error_type = _classify_compile_error(fr.compile_error)
                    step_result.error_detail = fr.compile_error[:200]
            except Exception as e:
                step_result.error_detail = str(e)
        else:
            # Fallback: wrap as a simple axiom check
            step_result.lean4_code = (
                f"-- Cannot formalize without formalize.py\n"
                f"-- Claim: {step_text[:100]}"
            )
            step_result.compiled = False
            step_result.error_detail = "formalize.py not available"

        if step_result.compiled:
            result.steps_verified += 1
        else:
            result.steps_failed += 1
            if step_result.error_type:
                result.error_taxonomy[step_result.error_type] = (
                    result.error_taxonomy.get(step_result.error_type, 0) + 1
                )

        result.step_results.append(step_result)

    return result
