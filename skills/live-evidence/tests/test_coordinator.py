"""Tests for retrieval routing policy."""

from live_evidence.config import InterviewProfile
from live_evidence.coordinator import _card_sources_for_decision, _code_problem_key
from live_evidence.models import EvidenceSource, Freshness, RetrievalLane
from live_evidence.trigger import TriggerDecision


def test_code_problem_key_is_stable_for_growing_parentheses_prompt() -> None:
    first = (
        "Turn any valid string. Formally, a parenthesis string is valid. "
        "Does the order matter here? So to make it clear, paste in the sample "
        "in terms of looking for minimum number of parentheses."
    )
    grown = (
        "Turn any valid string. Formally, a parentheses string is valid. "
        "Does the order matter here? So to make it clear, paste in the sample "
        "in terms of looking for minimum number of parentheses to remove so the output is valid."
    )

    assert _code_problem_key(first) == _code_problem_key(grown)


def test_code_card_keeps_current_source_when_ask_degrades() -> None:
    profile = InterviewProfile(
        name="youtube",
        repo_priorities=["youtube-eval"],
    )
    decision = TriggerDecision(
        event_id="turn-1",
        query="Find the minimum number of parentheses to remove from the input.",
        thread="youtube-eval",
        reason="code-question",
        code_related=True,
    )
    current_source = EvidenceSource(
        lane=RetrievalLane.RIPGREP,
        label="youtube-eval/newly_written_solution.js",
        excerpt="function countMinimumInvalidParentheses(input) { return { left, right }; }",
        score=0.7,
        freshness=Freshness.CURRENT,
        repository="youtube-eval",
        path="/repo/newly_written_solution.js",
        line_start=33,
    )

    selected = _card_sources_for_decision(decision, [current_source], [], profile)

    assert selected == [current_source]
