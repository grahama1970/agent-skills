"""Deterministic token-overlap routing for explain-project.

The router intentionally does not use an LLM or default to the first record.
Ties remain AMBIGUOUS and zero-overlap questions remain NO_MATCH.
"""

from __future__ import annotations

from .models import FeatureExplainer, RouteDecision


def _tokens(text: str) -> set[str]:
    normalized = "".join(
        char.lower() if char.isalnum() else " "
        for char in text
    )
    return {
        token
        for token in normalized.split()
        if len(token) > 3
    }


def score(row: FeatureExplainer, question: str) -> int:
    """Count distinct meaningful question tokens present in an explainer."""

    haystack = " ".join(
        [
            row.question,
            row.title,
            row.question_family,
            *row.teleprompter_points,
            *row.related_questions,
        ]
    )
    return len(_tokens(question) & _tokens(haystack))


def route(
    rows: list[FeatureExplainer],
    question: str,
) -> RouteDecision:
    """Route without guessing through ties or zero-overlap cases."""

    scores = {
        row.feature_id: score(row, question)
        for row in rows
    }
    best = max(scores.values(), default=0)

    if best == 0:
        return RouteDecision(
            status="NO_MATCH",
            question=question,
            scores=scores,
        )

    winners = sorted(
        feature_id
        for feature_id, value in scores.items()
        if value == best
    )

    if len(winners) > 1:
        return RouteDecision(
            status="AMBIGUOUS",
            question=question,
            scores=scores,
            candidates=winners,
        )

    return RouteDecision(
        status="MATCHED",
        question=question,
        scores=scores,
        matched_feature=winners[0],
        candidates=winners,
    )
