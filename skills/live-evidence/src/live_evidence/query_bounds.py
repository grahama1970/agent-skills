"""Bound transcript windows into retrieval-sized questions."""

from __future__ import annotations

import re

from .readiness import ReadinessVerdict
from .retrieval.external import derive_manual_search_query


_QUESTION_SENTENCE_RE = re.compile(
    r"([^.?!]{8,}(?:\?|,\s*(?:right|correct|okay|yes)\b[.?!]?))", re.IGNORECASE
)


def bounded_query(raw: str, verdict: ReadinessVerdict | None) -> str:
    """Return one bounded question for retrieval and solver context."""

    problem_query = _code_problem_context_query(raw, verdict)
    if problem_query:
        return problem_query[:220]
    if verdict is not None:
        canonical = verdict.canonical_question.strip()
        if canonical:
            return canonical[:220]
    sentences = _QUESTION_SENTENCE_RE.findall(" ".join(raw.split()))
    picked: list[str] = []
    total = 0
    for sentence in reversed(sentences):
        sentence = sentence.strip()
        if total + len(sentence) + 1 > 220:
            break
        picked.insert(0, sentence)
        total += len(sentence) + 1
    if picked:
        return " ".join(picked)
    derived = derive_manual_search_query(raw, max_chars=220)
    return derived or raw


def _code_problem_context_query(raw: str, verdict: ReadinessVerdict | None = None) -> str:
    """Keep coding problem context when the canonical form is only a tail."""

    lower = " ".join(raw.casefold().split())
    strong_parentheses_context = (
        "parenthes" in lower
        and "minimum" in lower
        and any(
            term in lower
            for term in ("remove", "valid", "dangling", "corresponding opening")
        )
    )
    if not strong_parentheses_context:
        return ""
    if verdict is not None and verdict.question_type not in {"code", "leetcode", "none"}:
        return ""
    return (
        "Given a string with opening and closing parentheses, remove the "
        "minimum number of parentheses so the result is valid; preserve "
        "non-parenthesis characters."
    )
