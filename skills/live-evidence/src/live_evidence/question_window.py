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
from .trigger import QUESTION_LEADS, extract_thread, is_code_question, tokenize


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
        duplicate_ttl_s: float = 15.0,
    ) -> None:
        self._profile = profile
        self._max_events = max_events
        self._max_chars = max_chars
        self._max_sequence_gap = max_sequence_gap
        self._duplicate_ttl_s = duplicate_ttl_s
        self._buffer: list[TranscriptEvent] = []
        self._recent: list[tuple[str, float]] = []
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
        if self._is_duplicate(fingerprint):
            self.reset()
            return WindowOutcome(candidate=candidate, duplicate=True, reason="duplicate")
        self._remember(fingerprint)
        self.reset()
        return WindowOutcome(candidate=candidate, duplicate=False, reason="accepted")

    def reset(self) -> None:
        """Clear the active rolling speech window."""

        self._buffer = []

    def _append_or_replace(self, event: TranscriptEvent) -> None:
        self._buffer = [item for item in self._buffer if item.event_id != event.event_id]
        if (
            event.kind is TranscriptKind.FINAL
            and self._buffer
            and self._buffer[-1].kind is TranscriptKind.STABILIZED
            and _token_overlap(event.text, self._buffer[-1].text) >= 0.88
        ):
            self._buffer[-1] = event
            return
        if (
            event.kind is TranscriptKind.STABILIZED
            and self._buffer
            and self._buffer[-1].kind is TranscriptKind.STABILIZED
            and _is_incremental_update(event.text, self._buffer[-1].text)
        ):
            self._buffer[-1] = event
            return
        self._buffer.append(event)
        self._buffer.sort(key=lambda item: item.sequence if item.sequence is not None else 0)

    def _enforce_bounds(self) -> None:
        while len(self._buffer) > self._max_events:
            self._buffer.pop(0)
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
        if (
            first == "when"
            and len(tokens) > 1
            and tokens[1].casefold() in {"i", "we"}
            and not text.rstrip().endswith("?")
        ):
            return None
        lower_text = text.casefold()
        matched_alias = next((alias for alias in self._aliases if alias in lower_text), None)
        matched_term = next((term for term in self._watch_terms if term in lower_text), None)
        is_question = text.rstrip().endswith("?") or first in QUESTION_LEADS
        code_question = (
            is_code_question(text)
            and self._buffer
            and self._buffer[-1].kind is TranscriptKind.FINAL
        )
        has_question_shape = is_question or matched_alias is not None
        if (
            is_question
            and matched_alias is None
            and matched_term is None
            and not code_question
            and self._buffer
            and self._buffer[-1].kind is not TranscriptKind.FINAL
        ):
            return None
        if (
            matched_term
            and not has_question_shape
            and not code_question
            and self._buffer
            and self._buffer[-1].kind is not TranscriptKind.FINAL
        ):
            return None
        if code_question:
            return "code-question"
        if matched_alias:
            return f"project:{self._aliases[matched_alias]}"
        if matched_term:
            return f"watch-term:{matched_term}"
        if is_question:
            return "question"
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

    def _is_duplicate(self, fingerprint: str) -> bool:
        now = monotonic()
        self._recent = [
            (key, seen_at)
            for key, seen_at in self._recent
            if now - seen_at <= self._duplicate_ttl_s
        ]
        return any(key == fingerprint for key, _ in self._recent)

    def _remember(self, fingerprint: str) -> None:
        self._recent.append((fingerprint, monotonic()))


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


def _is_incremental_update(left: str, right: str) -> bool:
    left_normalized = " ".join(token.casefold() for token in tokenize(left))
    right_normalized = " ".join(token.casefold() for token in tokenize(right))
    if not left_normalized or not right_normalized:
        return False
    if left_normalized.startswith(right_normalized) or right_normalized.startswith(left_normalized):
        return True
    return _token_overlap(left, right) >= 0.55
