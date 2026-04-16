"""Response quality utilities for SPARTA persona conversations.

IMPORTANT: Keyword scanning for assessments is BANNED across all Embry-OS.
Use semantic_grader.grade_response_semantic() for all quality assessment.

This module retains ONLY:
- extract_entities() — regex entity ID extraction (utility, not assessment)
- validate_entities() — ArangoDB entity existence check (utility, not assessment)
- _ENTITY_RE — regex pattern for entity extraction

Everything else has been deprecated in favor of semantic LLM grading.
"""
from __future__ import annotations

import re
from typing import Any

from loguru import logger


# Entity ID patterns (KEPT — utility for entity extraction, not keyword scanning)
_ENTITY_RE = re.compile(
    r'(SV-[A-Z]{2,4}-\d+|[A-Z]{2,4}-\d{1,4}(?:\.\d+)?|CWE-\d+|T\d{4}(?:\.\d{3})?|'
    r'CM\d{4}|D3-[A-Z]+|AU-\d+(?:\(\d+\))?|SI-\d+(?:\(\d+\))?|AC-\d+(?:\(\d+\))?|'
    r'IA-\d+(?:\(\d+\))?|SC-\d+(?:\(\d+\))?|SR-\d+(?:\(\d+\))?|PE-\d+|IR-\d+|'
    r'MA-\d+|RA-\d+|CA-\d+|PL-\d+|SA-\d+|PM-\d+|MP-\d+|CP-\d+|AT-\d+)',
    re.IGNORECASE
)


def extract_entities(text: str) -> list[str]:
    """Extract SPARTA/NIST/CWE/ATT&CK entity IDs from text."""
    return [m.upper() for m in _ENTITY_RE.findall(text)]


def validate_entities(entities: list[str], db: Any) -> dict[str, bool]:
    """Check which entities actually exist in ArangoDB.

    Returns dict mapping entity_id → exists (bool).
    """
    if not entities or not db:
        return {}

    results = {}
    for eid in entities:
        try:
            # Check sparta_qra collection
            cursor = db.aql.execute(
                "FOR q IN sparta_qra FILTER q.control_id == @cid LIMIT 1 RETURN 1",
                bind_vars={"cid": eid},
            )
            if list(cursor):
                results[eid] = True
                continue

            # Check controls collection
            cursor = db.aql.execute(
                "FOR c IN controls FILTER c.control_id == @cid LIMIT 1 RETURN 1",
                bind_vars={"cid": eid},
            )
            results[eid] = bool(list(cursor))
        except Exception:
            results[eid] = True  # Assume valid on error (don't block)

    return results


def assess_response_quality(**kwargs) -> dict[str, Any]:
    """BANNED: Keyword scanning for assessments is prohibited.

    Use semantic_grader.grade_response_semantic() instead.
    This function existed as a Tier 0/0.5 heuristic+classifier quality gate.
    It has been replaced by full-transcript semantic LLM grading with QRA
    citation verification — the ONLY valid quality signal in Embry-OS.
    """
    raise DeprecationError(
        "BANNED: Keyword scanning for assessments is prohibited across all Embry-OS. "
        "Use semantic_grader.grade_response_semantic() instead. "
        "QRA citation is the ONLY valid quality signal."
    )


def improve_response(**kwargs) -> str:
    """BANNED: Keyword-based response improvement is prohibited.

    The self-grading loop now uses semantic LLM grading with full transcript
    context and QRA ground truth. Re-retrieval is guided by LLM rationale,
    not heuristic issue detection.
    """
    raise DeprecationError(
        "BANNED: Keyword-based response improvement is prohibited. "
        "Use the semantic self-grading loop in conversation_sim._self_grading_loop() instead."
    )


class DeprecationError(Exception):
    """Raised when banned keyword scanning functions are called."""
    pass
