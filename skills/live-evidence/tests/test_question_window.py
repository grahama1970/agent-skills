"""Tests for split-question transcript windowing."""

from live_evidence.config import InterviewProfile
from live_evidence.models import Speaker, TranscriptEvent, TranscriptKind
from live_evidence.question_window import QuestionWindowBuilder


PROFILE = InterviewProfile(
    name="question-window-test",
    watch_terms=["invalid parentheses", "stack"],
    project_aliases={"youtube-eval": ["parenthesis interview"]},
)


def turn(
    sequence: int,
    text: str,
    *,
    speaker: Speaker = Speaker.INTERVIEWER,
    kind: TranscriptKind = TranscriptKind.FINAL,
    event_id: str | None = None,
) -> TranscriptEvent:
    return TranscriptEvent(
        event_id=event_id or f"event-{sequence:04d}",
        speaker=speaker,
        kind=kind,
        text=text,
        sequence=sequence,
    )


def test_split_interviewer_question_emits_one_candidate() -> None:
    builder = QuestionWindowBuilder(PROFILE, duplicate_ttl_s=60)

    first = builder.ingest(turn(1, "Given a string with parentheses, how would"))
    second = builder.ingest(turn(2, "you remove the minimum invalid parentheses?"))

    assert first.candidate is None
    assert second.candidate is not None
    assert second.duplicate is False
    assert second.candidate.normalized_question == (
        "Given a string with parentheses, how would "
        "you remove the minimum invalid parentheses?"
    )
    assert second.candidate.source_event_ids == ["event-0001", "event-0002"]
    assert second.candidate.start_sequence == 1
    assert second.candidate.end_sequence == 2


def test_candidate_turn_is_hard_boundary() -> None:
    builder = QuestionWindowBuilder(PROFILE, duplicate_ttl_s=60)

    assert builder.ingest(turn(1, "Given a string with parentheses, how would")).candidate is None
    assert (
        builder.ingest(
            turn(2, "I would use a stack.", speaker=Speaker.GRAHAM)
        ).candidate
        is None
    )
    assert (
        builder.ingest(turn(3, "you remove the minimum invalid parentheses?")).candidate
        is None
    )


def test_stabilized_and_final_duplicate_is_suppressed() -> None:
    builder = QuestionWindowBuilder(PROFILE, duplicate_ttl_s=60)

    stabilized = TranscriptEvent(
        event_id="event-stable",
        speaker=Speaker.INTERVIEWER,
        kind=TranscriptKind.STABILIZED,
        text="How would you remove the minimum invalid parentheses?",
        sequence=1,
    )
    final = TranscriptEvent(
        event_id="event-final",
        speaker=Speaker.INTERVIEWER,
        kind=TranscriptKind.FINAL,
        text="How would you remove the minimum invalid parentheses?",
        sequence=2,
    )

    first = builder.ingest(stabilized)
    second = builder.ingest(final)

    assert first.candidate is not None
    assert first.duplicate is False
    assert second.candidate is not None
    assert second.duplicate is True


def test_growing_stabilized_updates_replace_previous_event() -> None:
    builder = QuestionWindowBuilder(PROFILE, duplicate_ttl_s=60)
    texts = [
        "When I present the problem, pause the video.",
        "When I present the problem, pause the video and attempt a solution.",
        "When I present the problem, pause the video and attempt a solution, then come back.",
        "When I present the problem, pause the video and attempt a solution, then come back. How are you?",
    ]
    outcomes = []
    for index, text in enumerate(texts, start=1):
        outcomes.append(
            builder.ingest(
                TranscriptEvent(
                    event_id=f"event-stable-{index}",
                    speaker=Speaker.INTERVIEWER,
                    kind=TranscriptKind.STABILIZED,
                    text=text,
                    sequence=index * 2,
                )
            )
        )

    assert [outcome.candidate for outcome in outcomes[:-1]] == [None, None, None]
    assert outcomes[-1].candidate is None

    final = builder.ingest(
        TranscriptEvent(
            event_id="event-final-4",
            speaker=Speaker.INTERVIEWER,
            kind=TranscriptKind.FINAL,
            text=texts[-1],
            sequence=9,
        )
    )

    assert final.candidate is not None
    assert final.candidate.normalized_question == texts[-1]
    assert final.candidate.source_event_ids == ["event-final-4"]


def test_watch_term_stabilized_discussion_waits_for_final() -> None:
    builder = QuestionWindowBuilder(PROFILE, duplicate_ttl_s=60)

    stable = TranscriptEvent(
        event_id="event-stable",
        speaker=Speaker.INTERVIEWER,
        kind=TranscriptKind.STABILIZED,
        text=(
            "We need the last opening parentheses correspond like the next closing "
            "parentheses, so it's sort of like a stack type of structure."
        ),
        sequence=10,
    )
    final = stable.model_copy(
        update={
            "event_id": "event-final",
            "kind": TranscriptKind.FINAL,
            "sequence": 11,
        }
    )

    assert builder.ingest(stable).candidate is None
    outcome = builder.ingest(final)

    assert outcome.candidate is not None
    assert outcome.duplicate is False
    assert outcome.candidate.source_event_ids == ["event-final"]


def test_generic_stabilized_greeting_question_does_not_create_card() -> None:
    builder = QuestionWindowBuilder(PROFILE)

    outcome = builder.ingest(
        turn(
            20,
            "Hey Connor, how are you doing today? Good, good. Today we're going to go "
            "over a coding interview question, and I want to hear your thought process.",
            kind=TranscriptKind.STABILIZED,
        )
    )

    assert outcome.candidate is None
    assert outcome.reason == "not_question"


def test_long_live_pasted_problem_final_becomes_code_candidate() -> None:
    builder = QuestionWindowBuilder(PROFILE, duplicate_ttl_s=60)
    text = (
        "We'll be challenging, which is the whole point. When I present the problem, "
        "pause the video, attempt a solution, and then come back and see how the engineer "
        "tackles it. Hey Connor, how are you doing today? Good! How are you? Good, good. "
        "So today we're gonna go over a coding interview question. You're gonna have about "
        "20, 30 minutes. I'm gonna paste a problem for you to solve. The most important "
        "thing for me is I wanna really hear your thought process as you're going through "
        "the question. Whether you actually get the right answer or not, I'm more interested "
        "about your problem solving. So you ready to get started? Yeah, let's do it. "
        "All right, cool. Let me paste the question for you real quick. Given a string S "
        "of open parentheses, close parentheses, and lowercase English characters, your "
        "task is to remove the minimum number of parentheses in any position so that the "
        "resulting parentheses string is valid and return any valid string. Formally, a "
        "parentheses string is valid if and only if it's an empty string, contains only "
        "lowercase characters, or it can be written as A, B, A concatenate with B, where "
        "A and B are valid strings, or it can be written as parentheses A, close parentheses, "
        "where A is a valid string. So just to clarify, if we come below here, if we do "
        "like this, I would assume valid. This is not. So the idea is just same number of "
        "opening and closing, and then like something like this, that would be valid. "
        + "The interviewer keeps explaining the sample while the transcriber emits one "
        "growing cumulative final window. "
        * 8
    )

    outcome = builder.ingest(turn(50, text))

    assert len(text) > 1_800
    assert outcome.candidate is not None
    assert outcome.candidate.trigger_reason == "code-question"
    assert "remove the minimum number of parentheses" in outcome.candidate.normalized_question


def test_sequence_gap_prevents_unrelated_join() -> None:
    builder = QuestionWindowBuilder(PROFILE, max_sequence_gap=2)

    assert builder.ingest(turn(1, "Given a string with parentheses, how would")).candidate is None
    assert (
        builder.ingest(turn(10, "you remove the minimum invalid parentheses?")).candidate
        is None
    )


def test_short_fragment_does_not_trigger() -> None:
    builder = QuestionWindowBuilder(PROFILE)

    outcome = builder.ingest(turn(1, "What makes a"))

    assert outcome.candidate is None
    assert outcome.reason == "not_question"
