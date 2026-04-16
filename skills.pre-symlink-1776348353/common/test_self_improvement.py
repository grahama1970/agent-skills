#!/usr/bin/env python3
"""Tests for common/self_improvement.py shared patterns."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from self_improvement import (
    Strategy,
    STRATEGIES,
    get_strategy,
    strategy_instruction,
    should_keep,
    ErrorSeverity,
    ERROR_TYPE_TO_SEVERITY,
    classify_error_severity,
    error_severity_from_text,
    RoundEntry,
    correction_message,
)


def test_strategy_escalation():
    """Test strategy selection based on round and error trajectory."""
    print("Testing strategy escalation...")

    # Round 1 always direct_fix
    assert get_strategy(1) == Strategy.direct_fix

    # Normal progression (round N → index N-1)
    assert get_strategy(2) == Strategy.structured_analysis  # round 2 → index 1
    assert get_strategy(3) == Strategy.different_approach   # round 3 → index 2
    assert get_strategy(4) == Strategy.simplify             # round 4 → index 3
    assert get_strategy(5) == Strategy.escalate             # round 5 → index 4

    # Same error repeating → escalate faster (skip ahead by 1)
    strat = get_strategy(2, prev_error_severity="import", curr_error_severity="import")
    assert strat == Strategy.different_approach, f"Expected different_approach (skip), got {strat}"

    strat = get_strategy(3, prev_error_severity="syntax", curr_error_severity="syntax")
    assert strat == Strategy.simplify, f"Expected simplify (skip), got {strat}"

    # Score improving → stay at current level (don't over-escalate)
    strat = get_strategy(3, score_improving=True)
    assert strat == Strategy.different_approach, f"Expected different_approach (stay at round-1), got {strat}"

    print("  PASS: Strategy escalation")


def test_strategy_instructions():
    """Test that all strategies have instructions."""
    print("Testing strategy instructions...")

    for strategy in STRATEGIES:
        instr = strategy_instruction(strategy)
        assert instr, f"No instruction for {strategy}"
        assert len(instr) > 20, f"Instruction too short for {strategy}"

    print("  PASS: Strategy instructions")


def test_should_keep():
    """Test keep/discard decision with epsilon."""
    print("Testing should_keep...")

    # Clear improvement → keep
    assert should_keep(0.5, 0.6) is True
    assert should_keep(0.5, 0.52) is True  # > 0.01 epsilon

    # No improvement → discard
    assert should_keep(0.5, 0.5) is False
    assert should_keep(0.5, 0.505) is False  # < 0.01 epsilon
    assert should_keep(0.5, 0.51) is False  # exactly 0.01, not > epsilon

    # Regression → discard
    assert should_keep(0.5, 0.4) is False

    # Custom epsilon
    assert should_keep(0.5, 0.501, epsilon=0.0001) is True
    assert should_keep(0.5, 0.501, epsilon=0.01) is False

    print("  PASS: should_keep")


def test_error_severity_classification():
    """Test error severity classification."""
    print("Testing error severity classification...")

    # Single error types
    assert classify_error_severity(["SyntaxError"]) == ErrorSeverity.syntax
    assert classify_error_severity(["ImportError"]) == ErrorSeverity.import_
    assert classify_error_severity(["TypeError"]) == ErrorSeverity.contract
    assert classify_error_severity(["AssertionError"]) == ErrorSeverity.logic
    assert classify_error_severity(["RuntimeError"]) == ErrorSeverity.runtime

    # Mixed → returns highest priority
    assert classify_error_severity(["TypeError", "SyntaxError"]) == ErrorSeverity.syntax
    assert classify_error_severity(["RuntimeError", "ImportError"]) == ErrorSeverity.import_

    # Unknown
    assert classify_error_severity([]) == ErrorSeverity.unknown
    assert classify_error_severity(["CustomError"]) == ErrorSeverity.unknown

    print("  PASS: Error severity classification")


def test_error_severity_from_text():
    """Test extracting error severity from raw text."""
    print("Testing error_severity_from_text...")

    text1 = "Traceback: SyntaxError: invalid syntax at line 5"
    assert error_severity_from_text(text1) == ErrorSeverity.syntax

    text2 = "ModuleNotFoundError: No module named 'foo'"
    assert error_severity_from_text(text2) == ErrorSeverity.import_

    text3 = "TypeError: expected str, got int\nKeyError: 'missing'"
    assert error_severity_from_text(text3) == ErrorSeverity.contract  # TypeError first in priority

    text4 = "All tests passed!"
    assert error_severity_from_text(text4) == ErrorSeverity.unknown

    print("  PASS: Error severity from text")


def test_round_entry():
    """Test RoundEntry dataclass serialization."""
    print("Testing RoundEntry...")

    entry = RoundEntry(
        round=2,
        task_id="test-task",
        score=0.75,
        prev_score=0.5,
        delta=0.25,
        status="keep",
        strategy=Strategy.structured_analysis,
        error_count=3,
        error_severity=ErrorSeverity.contract,
        errors_by_type={"TypeError": 2, "KeyError": 1},
        latency_ms=1234.5,
        metadata={"backend": "codex", "commit": "abc123"},
    )

    # to_dict
    d = entry.to_dict()
    assert d["round"] == 2
    assert d["strategy"] == "structured_analysis"
    assert d["error_severity"] == "contract"
    assert d["backend"] == "codex"  # metadata flattened

    # from_dict round-trip
    entry2 = RoundEntry.from_dict(d)
    assert entry2.round == entry.round
    assert entry2.strategy == entry.strategy
    assert entry2.error_severity == entry.error_severity
    assert entry2.metadata["backend"] == "codex"

    print("  PASS: RoundEntry")


def test_correction_message():
    """Test correction message generation."""
    print("Testing correction_message...")

    # Direct fix - simple
    msg = correction_message(
        "Invalid tags: foo, bar",
        valid_options=["alpha", "beta", "gamma"],
        strategy=Strategy.direct_fix,
    )
    assert "Invalid tags: foo, bar" in msg
    assert "alpha, beta, gamma" in msg
    assert "Please fix" in msg

    # Structured analysis - explains why
    msg = correction_message(
        "Wrong format",
        valid_options=["A", "B"],
        strategy=Strategy.structured_analysis,
    )
    assert "Let me explain why" in msg
    assert "exactly match" in msg

    # Different approach - with examples
    msg = correction_message(
        "Still wrong",
        examples=["example1", "example2"],
        strategy=Strategy.different_approach,
    )
    assert "different interpretation" in msg
    assert "example1" in msg

    # Simplify
    msg = correction_message(
        "Error",
        valid_options=["X", "Y", "Z"],
        strategy=Strategy.simplify,
    )
    assert "MOST LIKELY" in msg
    assert "simpler is better" in msg

    # Escalate - asks for reasoning
    msg = correction_message(
        "Final attempt",
        strategy=Strategy.escalate,
    )
    assert "understand your reasoning" in msg
    assert "What do you think" in msg

    print("  PASS: correction_message")


def main():
    """Run all tests."""
    print("=" * 60)
    print("common/self_improvement.py tests")
    print("=" * 60)

    try:
        test_strategy_escalation()
        test_strategy_instructions()
        test_should_keep()
        test_error_severity_classification()
        test_error_severity_from_text()
        test_round_entry()
        test_correction_message()

        print("=" * 60)
        print("ALL TESTS PASSED")
        print("=" * 60)
        return 0

    except AssertionError as e:
        print(f"\nFAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
