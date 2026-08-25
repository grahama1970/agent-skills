"""Bounded interviewer question windowing.

RealtimeSTT may split one spoken question across multiple stabilized/final
events. This module assembles recent contiguous interviewer text into one
question candidate while treating candidate speech as a hard boundary.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from time import monotonic

from .config import InterviewProfile
from .models import (
    EventSpan,
    QuestionCandidate,
    Speaker,
    TranscriptEvent,
    TranscriptKind,
)
from .transcript_dedupe import is_progressive_restatement, richer_transcript_event
from .trigger import QUESTION_LEADS, extract_thread, tokenize

# Marker phrases that, in combination (>=2), identify a spoken problem
# statement that carries its question declaratively.
PROBLEM_STATEMENT_MARKERS = (
    "we're given",
    "we are given",
    "you're given",
    "you are given",
    "given an ",
    "given a ",
    "we want to",
    "we need to",
    "your task",
    "the task is",
    "find the",
    "return the",
    "implement a",
    "write a function",
)

# Single-turn coding prompts often arrive as imperatives rather than questions:
# "Write a function ...", "Implement binary search ...". Requiring two markers
# made the next unrelated interviewer turn join the same candidate.
IMPERATIVE_PROBLEM_PREFIXES = (
    "write a function",
    "implement ",
)


@dataclass(frozen=True, slots=True)
class WindowOutcome:
    """Result from adding one transcript event to the rolling window."""

    candidate: QuestionCandidate | None = None
    duplicate: bool = False
    reason: str = "no_candidate"


class QuestionWindowBuilder:
    """Assemble split interviewer chunks into deduplicated question candidates."""

    def __init__(
        self,
        profile: InterviewProfile,
        *,
        max_events: int = 4,
        max_chars: int = 1_800,
        max_sequence_gap: int = 2,
        duplicate_ttl_s: float = 45.0,
    ) -> None:
        self._profile = profile
        self._max_events = max_events
        self._max_chars = max_chars
        self._max_sequence_gap = max_sequence_gap
        self._duplicate_ttl_s = duplicate_ttl_s
        self._buffer: list[TranscriptEvent] = []
        self._recent: list[tuple[str, str, float]] = []
        self._watch_terms = {
            term.casefold() for term in profile.watch_terms if term.strip()
        }
        self._aliases = {
            alias.casefold(): project
            for project, aliases in profile.project_aliases.items()
            for alias in [project, *aliases]
            if alias.strip()
        }

    def ingest(self, event: TranscriptEvent) -> WindowOutcome:
        """Add one event and return an accepted or duplicate question candidate."""

        if event.kind not in {TranscriptKind.STABILIZED, TranscriptKind.FINAL}:
            return WindowOutcome(reason="not_stable")
        if event.speaker is not Speaker.INTERVIEWER:
            self.reset()
            return WindowOutcome(reason="speaker_boundary")
        if self._should_reset_for_sequence(event):
            self.reset()

        self._append_or_replace(event)
        self._enforce_bounds()
        question_text = _normalize_question(" ".join(item.text for item in self._buffer))
        reason = self._trigger_reason(question_text)
        if reason is None:
            return WindowOutcome(reason="not_question")

        spans = self._spans(question_text)
        fingerprint = _fingerprint(question_text)
        candidate = QuestionCandidate(
            question_id=f"q_{_fingerprint('|'.join([*candidate_event_ids(spans), question_text]))[:32]}",
            normalized_question=question_text,
            speaker=Speaker.INTERVIEWER,
            source_event_ids=candidate_event_ids(spans),
            source_spans=spans,
            start_sequence=spans[0].sequence,
            end_sequence=spans[-1].sequence,
            trigger_reason=reason,
            fingerprint=fingerprint,
        )
        if self._is_duplicate(fingerprint, question_text):
            self.reset()
            return WindowOutcome(candidate=candidate, duplicate=True, reason="duplicate")
        self._remember(fingerprint, question_text)
        self.reset()
        return WindowOutcome(candidate=candidate, duplicate=False, reason="accepted")

    def reset(self) -> None:
        """Clear the active rolling speech window."""

        self._buffer = []

    def _append_or_replace(self, event: TranscriptEvent) -> None:
        self._buffer = [item for item in self._buffer if item.event_id != event.event_id]
        if self._buffer and is_progressive_restatement(self._buffer[-1], event):
            self._buffer[-1] = richer_transcript_event(self._buffer[-1], event)
            return
        if (
            event.kind is TranscriptKind.FINAL
            and self._buffer
            and self._buffer[-1].kind is TranscriptKind.STABILIZED
            and _token_overlap(event.text, self._buffer[-1].text) >= 0.88
        ):
            self._buffer[-1] = event
            return
        self._buffer.append(event)
        self._buffer.sort(key=lambda item: item.sequence if item.sequence is not None else 0)

    def _enforce_bounds(self) -> None:
        while len(self._buffer) > self._max_events:
            self._buffer.pop(0)
        # Keep at least one event: real STT events routinely exceed max_chars on
        # their own (measured mean 640 chars on live PipeWire capture), and an
        # unguarded loop drains the buffer to empty, so the turn is silently
        # dropped as not_question instead of being considered.
        while len(self._buffer) > 1 and len(" ".join(item.text for item in self._buffer)) > self._max_chars:
            self._buffer.pop(0)

    def _should_reset_for_sequence(self, event: TranscriptEvent) -> bool:
        if not self._buffer:
            return False
        last_sequence = self._buffer[-1].sequence
        current_sequence = event.sequence
        if last_sequence is None or current_sequence is None:
            return False
        if current_sequence <= last_sequence:
            return True
        return current_sequence - last_sequence > self._max_sequence_gap

    def _trigger_reason(self, text: str) -> str | None:
        tokens = tokenize(text)
        if len(tokens) < 4:
            return None
        first = tokens[0].casefold()
        if len(self._buffer) == 1 and text[:1].islower() and first not in QUESTION_LEADS:
            return None
        lower_text = text.casefold()
        matched_alias = next((alias for alias in self._aliases if alias in lower_text), None)
        matched_term = next((term for term in self._watch_terms if term in lower_text), None)
        is_question = "?" in text or first in QUESTION_LEADS
        if matched_alias:
            return f"project:{self._aliases[matched_alias]}"
        if matched_term:
            return f"watch-term:{matched_term}"
        if is_question:
            return "question"
        if any(lower_text.startswith(prefix) for prefix in IMPERATIVE_PROBLEM_PREFIXES):
            return "problem_statement"
        # Declarative problem statements: a code walkthrough or task briefing
        # states its question without interrogative form ("we're given an
        # input array ... we want to find the two values ... return the
        # indices"). Two or more marker phrases open the gate; the stage-1
        # resolver stays the authority on whether anything is answerable, so
        # this only widens what it gets to judge.
        markers = sum(1 for marker in PROBLEM_STATEMENT_MARKERS if marker in lower_text)
        if markers >= 2:
            return "problem_statement"
        return None

    def _spans(self, joined_text: str) -> list[EventSpan]:
        spans: list[EventSpan] = []
        cursor = 0
        for index, event in enumerate(self._buffer):
            text = event.text
            start = cursor
            end = start + len(text)
            spans.append(
                EventSpan(
                    event_id=event.event_id,
                    sequence=event.sequence if event.sequence is not None else index,
                    start_offset=start,
                    end_offset=end,
                )
            )
            cursor = end + 1
        if spans and spans[-1].end_offset > len(joined_text):
            last = spans[-1]
            spans[-1] = last.model_copy(update={"end_offset": len(joined_text)})
        return spans

    def _is_duplicate(self, fingerprint: str, text: str) -> bool:
        now = monotonic()
        self._recent = [
            (key, recent_text, seen_at)
            for key, recent_text, seen_at in self._recent
            if now - seen_at <= self._duplicate_ttl_s
        ]
        # Two similarity clauses, both DIRECTIONAL on purpose:
        # - overlap (intersection / MAX >= 0.58) collapses near-identical
        #   restatements;
        # - candidate containment (intersection / len(candidate) >= 0.9)
        #   collapses short fragments whose tokens are already inside recent
        #   text (tag-question restatements like "...has to come before
        #   closing, right?").
        # The former symmetric MIN-containment clause is deliberately gone:
        # live STT events are cumulative rolling buffers, so "intro plus a
        # genuinely new question" was suppressed as a duplicate of the intro
        # for the whole TTL (observed live: three cards from the intro, none
        # from the actual problem statement). Candidate-directional
        # containment cannot do that -- a window with substantial NEW tokens
        # keeps its containment low and correctly proceeds.
        return any(
            key == fingerprint
            or _token_overlap(text, recent_text) >= 0.58
            or _candidate_containment(text, recent_text) >= 0.9
            for key, recent_text, _ in self._recent
        )

    def _remember(self, fingerprint: str, text: str) -> None:
        self._recent.append((fingerprint, text, monotonic()))


def candidate_event_ids(spans: list[EventSpan]) -> list[str]:
    """Return event ids in the same order as the candidate spans."""

    return [span.event_id for span in spans]


def candidate_thread(candidate: QuestionCandidate, profile: InterviewProfile) -> str:
    """Create the current-thread label for one question candidate."""

    return extract_thread(candidate.normalized_question, profile)


def _normalize_question(text: str) -> str:
    return " ".join(text.split())[:1_200]


def _fingerprint(text: str) -> str:
    normalized = " ".join(token.casefold() for token in tokenize(text))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _token_overlap(left: str, right: str) -> float:
    left_tokens = {token.casefold() for token in tokenize(left)}
    right_tokens = {token.casefold() for token in tokenize(right)}
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(len(left_tokens), len(right_tokens))


def _candidate_containment(candidate: str, recent: str) -> float:
    """Fraction of the candidate's own tokens already present in recent text."""
    candidate_tokens = {token.casefold() for token in tokenize(candidate)}
    recent_tokens = {token.casefold() for token in tokenize(recent)}
    if not candidate_tokens or not recent_tokens:
        return 0.0
    return len(candidate_tokens & recent_tokens) / len(candidate_tokens)


def _token_containment(left: str, right: str) -> float:
    left_tokens = {token.casefold() for token in tokenize(left)}
    right_tokens = {token.casefold() for token in tokenize(right)}
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))
