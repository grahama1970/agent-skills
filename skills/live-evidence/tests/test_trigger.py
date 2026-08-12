"""Tests for deterministic transcript triggering."""

from live_evidence.config import InterviewProfile
from live_evidence.models import Speaker, TranscriptEvent, TranscriptKind
from live_evidence.trigger import TriggerEngine, extract_thread, search_terms


PROFILE = InterviewProfile(
    name="test",
    watch_terms=["agent", "evaluation"],
    project_aliases={"tau": ["receipt-gated", "goal-locked"]},
)


def test_interviewer_question_triggers() -> None:
    engine = TriggerEngine(PROFILE, cooldown_s=0)
    event = TranscriptEvent(
        speaker=Speaker.INTERVIEWER,
        kind=TranscriptKind.FINAL,
        text="How do you prevent an agent from drifting during a long workflow?",
    )
    decision = engine.decide(event)
    assert decision is not None
    assert decision.reason in {"question", "watch-term:agent"}


def test_graham_turn_does_not_trigger() -> None:
    engine = TriggerEngine(PROFILE, cooldown_s=0)
    event = TranscriptEvent(
        speaker=Speaker.GRAHAM,
        kind=TranscriptKind.FINAL,
        text="I use receipt-gated handoffs and explicit validation.",
    )
    assert engine.decide(event) is None


def test_project_alias_becomes_thread() -> None:
    assert extract_thread("Tell me about receipt-gated execution in Tau", PROFILE) == "tau"


def test_search_terms_are_bounded_and_not_question_words() -> None:
    terms = search_terms("How do agents use receipts and knowledge graphs in production?", limit=4)
    assert "How" not in terms
    assert len(terms) <= 4
    assert "agents" in terms
