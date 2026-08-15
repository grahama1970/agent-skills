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


def test_growing_non_code_question_triggers_once() -> None:
    engine = TriggerEngine(PROFILE, cooldown_s=30)
    first = TranscriptEvent(
        speaker=Speaker.INTERVIEWER,
        kind=TranscriptKind.STABILIZED,
        text="What is under specified security clarify response?",
    )
    grown = TranscriptEvent(
        speaker=Speaker.INTERVIEWER,
        kind=TranscriptKind.STABILIZED,
        text=(
            "What is under specified security clarify response? "
            "What is under specified security clarify response in clarify helpers?"
        ),
    )

    assert engine.decide(first) is not None
    assert engine.decide(grown) is None


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


def test_stabilized_filler_does_not_trigger() -> None:
    engine = TriggerEngine(PROFILE, cooldown_s=0)
    event = TranscriptEvent(
        speaker=Speaker.INTERVIEWER,
        kind=TranscriptKind.STABILIZED,
        text="That is alright, something like this is still not valid even though it has the same opening and closing.",
    )

    assert engine.decide(event) is None


def test_coding_problem_stabilized_turn_triggers_once_during_growth() -> None:
    engine = TriggerEngine(PROFILE, cooldown_s=30)
    setup = TranscriptEvent(
        speaker=Speaker.INTERVIEWER,
        kind=TranscriptKind.STABILIZED,
        text=(
            "Turn any valid string. Formally a parentheses string is valid if it contains "
            "only lowercase characters or can be written as AB where A and B are valid strings."
        ),
    )
    second = TranscriptEvent(
        speaker=Speaker.INTERVIEWER,
        kind=TranscriptKind.STABILIZED,
        text=(
            "Turn any valid string. Formally a parentheses string is valid if it contains "
            "only lowercase characters or can be written as AB where A and B are valid strings. "
            "Find the minimum number of parentheses to remove."
        ),
    )
    third = TranscriptEvent(
        speaker=Speaker.INTERVIEWER,
        kind=TranscriptKind.STABILIZED,
        text=(
            "Turn any valid string. Formally a parentheses string is valid if it contains "
            "only lowercase characters or can be written as AB where A and B are valid strings. "
            "Find the minimum number of parentheses to remove so the output is valid."
        ),
    )

    assert engine.decide(setup) is None
    decision = engine.decide(second)

    assert decision is not None
    assert decision.reason == "code-question"
    assert decision.code_related is True
    assert engine.decide(third) is None


def test_coding_problem_setup_question_waits_for_actionable_prompt() -> None:
    engine = TriggerEngine(PROFILE, cooldown_s=0)
    event = TranscriptEvent(
        speaker=Speaker.INTERVIEWER,
        kind=TranscriptKind.FINAL,
        text=(
            "Turn any valid string. Formally, a parenthesis string is valid if it contains "
            "only lowercase characters or can be written as AB where A and B are valid strings. "
            "Does the order matter here?"
        ),
    )

    assert engine.decide(event) is None


def test_real_stt_valid_parentheses_question_is_actionable() -> None:
    engine = TriggerEngine(PROFILE, cooldown_s=0)
    event = TranscriptEvent(
        speaker=Speaker.INTERVIEWER,
        kind=TranscriptKind.FINAL,
        text=(
            "What makes a parentheses string valid? A opening parentheses always has to come "
            "before closing, right? So if we sort of iterate to our string, each closing "
            "parenthesis needs a previous opening parenthesis."
        ),
    )

    decision = engine.decide(event)

    assert decision is not None
    assert decision.reason == "code-question"
    assert decision.code_related is True


def test_search_terms_are_bounded_and_not_question_words() -> None:
    terms = search_terms("How do agents use receipts and knowledge graphs in production?", limit=4)
    assert "How" not in terms
    assert len(terms) <= 4
    assert "agents" in terms
