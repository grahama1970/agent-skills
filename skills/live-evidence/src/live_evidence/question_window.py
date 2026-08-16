"""Bounded interviewer question windowing.

RealtimeSTT may split one spoken question across multiple stabilized/final
events. This module assembles recent contiguous interviewer text into one
question candidate while treating candidate speech as a hard boundary.
"""

from __future__ import annotations

import hashlib
import re
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
from .trigger import CODE_PROMPT_TERMS, QUESTION_LEADS, extract_thread, is_code_prompt, is_code_question, tokenize


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
        code_topic_ttl_s: float = 90.0,
    ) -> None:
        self._profile = profile
        self._max_events = max_events
        self._max_chars = max_chars
        self._max_sequence_gap = max_sequence_gap
        self._duplicate_ttl_s = duplicate_ttl_s
        self._code_topic_ttl_s = code_topic_ttl_s
        self._buffer: list[TranscriptEvent] = []
        self._recent: list[tuple[str, str, float]] = []
        self._recent_code_topics: list[tuple[set[str], float]] = []
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
        window_text = _normalize_question(" ".join(item.text for item in self._buffer))
        question_text = self._best_retrieval_query(window_text)
        reason = self._trigger_reason(question_text)
        if reason is None:
            return WindowOutcome(reason="not_question")

        spans = self._spans(window_text)
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
        if self._is_duplicate(fingerprint, question_text) or self._is_duplicate_code_topic(question_text):
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
        if (
            len(self._buffer) == 1
            and text[:1].islower()
            and first not in QUESTION_LEADS
            and not is_code_prompt(text)
        ):
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
        is_question = "?" in text or first in QUESTION_LEADS
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

    def _is_duplicate(self, fingerprint: str, text: str) -> bool:
        now = monotonic()
        self._recent = [
            (key, recent_text, seen_at)
            for key, recent_text, seen_at in self._recent
            if now - seen_at <= self._duplicate_ttl_s
        ]
        return any(
            key == fingerprint
            or _token_overlap(text, recent_text) >= 0.58
            or _token_containment(text, recent_text) >= 0.72
            for key, recent_text, _ in self._recent
        )

    def _remember(self, fingerprint: str, text: str) -> None:
        self._recent.append((fingerprint, text, monotonic()))
        code_terms = _code_terms(text)
        if code_terms:
            self._recent_code_topics.append((code_terms, monotonic()))

    def _is_duplicate_code_topic(self, text: str) -> bool:
        if not is_code_prompt(text):
            return False
        terms = _code_terms(text)
        if len(terms) < 3:
            return False
        now = monotonic()
        self._recent_code_topics = [
            (recent_terms, seen_at)
            for recent_terms, seen_at in self._recent_code_topics
            if now - seen_at <= self._code_topic_ttl_s
        ]
        for recent_terms, _ in self._recent_code_topics:
            overlap = len(terms & recent_terms)
            if overlap / min(len(terms), len(recent_terms)) >= 0.6:
                return True
        return False

    def _best_retrieval_query(self, text: str) -> str:
        candidates = _query_candidates(text)
        if len(candidates) <= 1:
            return candidates[0] if candidates else text
        best = max(
            enumerate(candidates),
            key=lambda item: (
                self._query_score(item[1]),
                item[0],
            ),
        )[1]
        return _normalize_question(best)

    def _query_score(self, text: str) -> float:
        tokens = [token.casefold() for token in tokenize(text)]
        if len(tokens) < 4:
            return -100.0
        lower_text = text.casefold()
        score = 0.0
        if is_code_question(text):
            score += 110.0
        elif is_code_prompt(text):
            score += 85.0
        if "?" in text:
            score += 14.0
        if tokens[0] in QUESTION_LEADS:
            score += 10.0
        if "opening parentheses always" in lower_text or "opening parenthesis always" in lower_text:
            score += 45.0
        if "given a string" in lower_text:
            score += 35.0
        if "remove the minimum" in lower_text:
            score += 35.0
        score += 16.0 * sum(1 for alias in self._aliases if alias in lower_text)
        score += 18.0 * sum(1 for term in self._watch_terms if term in lower_text)
        score += min(len(set(tokens) & CODE_PROMPT_TERMS), 8) * 7.0
        score += min(
            len({token for token in tokens if token not in QUESTION_LEADS and len(token) >= 4}),
            12,
        )
        if _is_smalltalk(text):
            score -= 45.0
        if len(text) > 520:
            score -= min((len(text) - 520) / 40.0, 25.0)
        return score


def candidate_event_ids(spans: list[EventSpan]) -> list[str]:
    """Return event ids in the same order as the candidate spans."""

    return [span.event_id for span in spans]


def candidate_thread(candidate: QuestionCandidate, profile: InterviewProfile) -> str:
    """Create the current-thread label for one question candidate."""

    return extract_thread(candidate.normalized_question, profile)


def _normalize_question(text: str) -> str:
    return " ".join(text.split())[:1_200]


def _query_candidates(text: str) -> list[str]:
    clean = _normalize_question(text)
    if not clean:
        return []
    candidates: list[str] = []
    start = 0
    for match in re.finditer(r"[?.!]+", clean):
        end = match.end()
        fragment = clean[start:end].strip(" ,;:-")
        if fragment:
            candidates.append(fragment)
        start = end
    tail = clean[start:].strip(" ,;:-")
    if tail:
        candidates.append(tail)
    if not candidates:
        candidates.append(clean)
    merged: list[str] = []
    for candidate in candidates:
        tokens = tokenize(candidate)
        if len(tokens) >= 4:
            merged.append(candidate)
        elif merged:
            merged[-1] = f"{merged[-1]} {candidate}".strip()
        else:
            merged.append(candidate)
    selected: list[str] = []
    for candidate in merged:
        normalized = _normalize_question(candidate)
        if len(tokenize(normalized)) < 4:
            continue
        dense_windows = _dense_token_windows(normalized)
        if dense_windows:
            selected.extend(dense_windows)
        else:
            selected.append(normalized)
    return selected


def _dense_token_windows(text: str) -> list[str]:
    tokens = tokenize(text)
    if len(tokens) <= 32:
        return []
    windows: list[str] = []
    for size in (14, 20, 26):
        if len(tokens) <= size:
            continue
        for start in range(0, len(tokens) - size + 1, 4):
            window = tokens[start : start + size]
            normalized_window = {token.casefold() for token in window}
            if len(normalized_window & CODE_PROMPT_TERMS) < 3:
                continue
            candidate = _trim_dense_window(window)
            if len(tokenize(candidate)) < 8:
                continue
            if candidate not in windows:
                windows.append(candidate)
    return windows


def _trim_dense_window(tokens: list[str]) -> str:
    lowered = [token.casefold() for token in tokens]
    for pattern in (
        ("given", "a", "string"),
        ("opening", "parentheses", "always"),
        ("opening", "parenthesis", "always"),
        ("open", "parentheses"),
        ("remove", "the", "minimum"),
        ("minimum", "number", "of", "parentheses"),
    ):
        limit = len(lowered) - len(pattern) + 1
        for index in range(max(limit, 0)):
            if tuple(lowered[index : index + len(pattern)]) == pattern:
                return " ".join(tokens[index:])
    for index, token in enumerate(lowered):
        if token in CODE_PROMPT_TERMS:
            trimmed = tokens[index:]
            if len(trimmed) >= 8:
                return " ".join(trimmed)
    return " ".join(tokens)


def _is_smalltalk(text: str) -> bool:
    lower = text.casefold()
    smalltalk_phrases = {
        "how are you",
        "ready to get started",
        "are you ready",
        "doing today",
        "let's do it",
        "thought process",
        "pause the video",
    }
    return any(phrase in lower for phrase in smalltalk_phrases)


def _fingerprint(text: str) -> str:
    normalized = " ".join(token.casefold() for token in tokenize(text))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _token_overlap(left: str, right: str) -> float:
    left_tokens = {token.casefold() for token in tokenize(left)}
    right_tokens = {token.casefold() for token in tokenize(right)}
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(len(left_tokens), len(right_tokens))


def _token_containment(left: str, right: str) -> float:
    left_tokens = {token.casefold() for token in tokenize(left)}
    right_tokens = {token.casefold() for token in tokenize(right)}
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))


def _code_terms(text: str) -> set[str]:
    return {token.casefold() for token in tokenize(text)} & CODE_PROMPT_TERMS


def _is_incremental_update(left: str, right: str) -> bool:
    left_normalized = " ".join(token.casefold() for token in tokenize(left))
    right_normalized = " ".join(token.casefold() for token in tokenize(right))
    if not left_normalized or not right_normalized:
        return False
    if left_normalized.startswith(right_normalized) or right_normalized.startswith(left_normalized):
        return True
    return _token_overlap(left, right) >= 0.55
