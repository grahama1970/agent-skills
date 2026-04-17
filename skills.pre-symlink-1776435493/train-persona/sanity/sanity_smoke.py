#!/usr/bin/env python3
"""Sanity tests for train-persona skill."""

import json
import sys
import tempfile
from pathlib import Path

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from upgrade_traces import compute_complexity, route_trace, CorrectionEpisode, UpgradedTrace
from train_persona import (
    load_persona_config,
    persona_consistency_reward,
    reasoning_coherence_reward,
)


def test_complexity_scoring():
    """Test complexity scoring for routing."""
    print("Testing complexity scoring...")

    # Easy query
    score, bucket = compute_complexity(
        "What is SPARTA?",
        "SPARTA is a framework for space cybersecurity."
    )
    assert bucket in ["easy", "medium"], f"Expected easy/medium, got {bucket}"

    # Hard query with technical terms
    score, bucket = compute_complexity(
        "Compare CWE-787 and CWE-125 in the context of ATT&CK technique T1071 and how SPARTA REC-0012 mitigates them",
        "This requires analyzing multiple frameworks..." * 20
    )
    assert bucket in ["hard", "ambiguous"], f"Expected hard/ambiguous, got {bucket}"

    print("  ✓ Complexity scoring works")


def test_route_selection():
    """Test route selection based on complexity."""
    print("Testing route selection...")

    route = route_trace("What is SPARTA?", "Simple answer")
    assert route == "one_shot", f"Expected one_shot, got {route}"

    print("  ✓ Route selection works")


def test_persona_config():
    """Test persona config loading."""
    print("Testing persona config loading...")

    embry = load_persona_config("Embry")
    assert embry.name == "Embry"
    assert embry.template == "intern"
    assert len(embry.humility_patterns) > 0

    horus = load_persona_config("Horus")
    assert horus.name == "Horus"
    assert horus.template == "expert"

    print("  ✓ Persona config loading works")


def test_persona_consistency_reward():
    """Test persona consistency reward function."""
    print("Testing persona consistency reward...")

    embry = load_persona_config("Embry")

    # Good response with humility
    good_response = "I'm still learning about this topic. Based on my training with Brandon, RF jamming..."
    scores = persona_consistency_reward([good_response], embry)
    assert len(scores) == 1
    assert scores[0] > 0.3, f"Expected score > 0.3, got {scores[0]}"

    # Bad response (overconfident)
    bad_response = "I know everything about this. I'm an expert in all domains."
    scores = persona_consistency_reward([bad_response], embry)
    assert scores[0] < 0.5, f"Expected score < 0.5 for overconfident response, got {scores[0]}"

    print("  ✓ Persona consistency reward works")


def test_reasoning_coherence_reward():
    """Test reasoning coherence reward function."""
    print("Testing reasoning coherence reward...")

    # Good structured response
    good_response = """
    First, let me analyze the query.
    Step 1: Identify the relevant SPARTA technique.
    Step 2: Look up the countermeasures.
    Therefore, the answer is CM-0045.
    In conclusion, spectrum monitoring is the key defense.
    """
    scores = reasoning_coherence_reward([good_response])
    assert scores[0] > 0.5, f"Expected score > 0.5 for structured response, got {scores[0]}"

    # Poor unstructured response
    bad_response = "Just do the thing. It works. Trust me."
    scores = reasoning_coherence_reward([bad_response])
    assert scores[0] < 0.5, f"Expected score < 0.5 for unstructured response, got {scores[0]}"

    print("  ✓ Reasoning coherence reward works")


def test_correction_episode_structure():
    """Test correction episode data structure."""
    print("Testing correction episode structure...")

    ep = CorrectionEpisode(
        episode_id="ep_001",
        state_before="Step 1: The ID is REC-012...",
        bad_step="REC-012",
        critique="SPARTA IDs use 4 digits",
        fixed_step="REC-0012",
        verification="Confirmed against source",
    )

    assert ep.episode_id == "ep_001"
    assert "REC-012" in ep.bad_step
    assert "REC-0012" in ep.fixed_step

    print("  ✓ Correction episode structure works")


def test_upgraded_trace_structure():
    """Test upgraded trace data structure."""
    print("Testing upgraded trace structure...")

    trace = UpgradedTrace(
        original_query="How do I detect RF jamming?",
        original_response="Use spectrum monitoring.",
        improved_trace=[
            {"step": 1, "thought": "RF jamming is REC-0012"},
            {"step": 2, "thought": "Countermeasure is CM-0045"},
        ],
        final_response="To detect RF jamming (REC-0012), implement CM-0045 Spectrum Monitoring.",
        episodes=[],
        confidence=0.85,
        route="one_shot",
    )

    assert trace.confidence == 0.85
    assert len(trace.improved_trace) == 2
    assert trace.route == "one_shot"

    print("  ✓ Upgraded trace structure works")


def main():
    """Run all sanity tests."""
    print("\n=== train-persona Sanity Tests ===\n")

    try:
        test_complexity_scoring()
        test_route_selection()
        test_persona_config()
        test_persona_consistency_reward()
        test_reasoning_coherence_reward()
        test_correction_episode_structure()
        test_upgraded_trace_structure()

        print("\n✅ All sanity tests passed!\n")
        return 0

    except AssertionError as e:
        print(f"\n❌ Test failed: {e}\n")
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}\n")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
