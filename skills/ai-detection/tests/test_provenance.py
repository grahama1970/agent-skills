"""Metadata-only GitHub provenance classification into three distinct label tiers."""
from ai_detection.provenance import (
    EFFICACY_ELIGIBLE,
    CommitSignal,
    Provenance,
    classify,
    detector_label,
    survey,
)


def test_bot_author_is_agent_authored():
    assert classify(CommitSignal("claude[bot]", "fix parser")) == Provenance.AGENT_AUTHORED
    assert classify(CommitSignal("cursor[bot]", "refactor")) == Provenance.AGENT_AUTHORED


def test_coauthor_trailer_is_ai_assisted_not_agent():
    sig = CommitSignal("alice", "add feature\n\nCo-authored-by: Claude <noreply@anthropic.com>")
    assert classify(sig) == Provenance.AI_ASSISTED  # human author + edit => weak label


def test_plain_human_commit_is_human_proxy():
    assert classify(CommitSignal("bob", "tidy up")) == Provenance.HUMAN_PROXY


def test_github_actions_is_not_an_agent():
    # Generic CI automation must not be counted as authored AI code.
    assert classify(CommitSignal("github-actions[bot]", "bump version")) == Provenance.HUMAN_PROXY


def test_label_mapping_and_efficacy_gate():
    assert detector_label(Provenance.HUMAN_PROXY) == "human"
    assert detector_label(Provenance.AGENT_AUTHORED) == "machine"
    assert detector_label(Provenance.AI_ASSISTED) == "machine"
    # Integrity rule: no gh-mined class may feed the efficacy tier.
    assert EFFICACY_ELIGIBLE == frozenset()


def test_survey_counts_all_three_classes():
    signals = [
        CommitSignal("claude[bot]", "x"),
        CommitSignal("alice", "y\nCo-authored-by: Cursor"),
        CommitSignal("bob", "z"),
        CommitSignal("carol", "w"),
    ]
    assert survey(signals) == {"agent_authored": 1, "ai_assisted": 1, "human_proxy": 2}
