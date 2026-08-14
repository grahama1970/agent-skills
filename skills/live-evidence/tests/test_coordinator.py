"""Tests for retrieval routing policy."""

from live_evidence.coordinator import _code_problem_key


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
