"""Progressive transcript replacement helpers.

Realtime STT callbacks often restate the same utterance as it stabilizes:
``A opening`` -> ``A opening parenthesis`` -> full final text. Those updates may
arrive with different event ids, so event-id replacement alone is insufficient.
"""

from __future__ import annotations

from .models import TranscriptEvent, TranscriptKind
from .trigger import tokenize


STABLE_KINDS = {TranscriptKind.STABILIZED, TranscriptKind.FINAL}


def is_progressive_restatement(previous: TranscriptEvent, current: TranscriptEvent) -> bool:
    """Return true when current is another projection of the same utterance."""

    if previous.speaker is not current.speaker or previous.source is not current.source:
        return False
    if previous.kind not in STABLE_KINDS or current.kind not in STABLE_KINDS:
        return False
    if previous.sequence is not None and current.sequence is not None:
        gap = abs(current.sequence - previous.sequence)
        if gap > 6:
            return False
    return _text_is_restatement(previous.text, current.text)


def richer_transcript_event(previous: TranscriptEvent, current: TranscriptEvent) -> TranscriptEvent:
    """Choose the transcript projection that carries the most useful text."""

    previous_tokens = tokenize(previous.text)
    current_tokens = tokenize(current.text)
    if len(current_tokens) > len(previous_tokens):
        return current
    if len(current_tokens) == len(previous_tokens) and current.kind is TranscriptKind.FINAL:
        return current
    return previous


def _text_is_restatement(left: str, right: str) -> bool:
    left_tokens = [token.casefold() for token in tokenize(left)]
    right_tokens = [token.casefold() for token in tokenize(right)]
    if not left_tokens or not right_tokens:
        return False
    if left_tokens == right_tokens:
        return True
    short, long = (left_tokens, right_tokens) if len(left_tokens) <= len(right_tokens) else (right_tokens, left_tokens)
    if len(short) < 3:
        return False
    if long[: len(short)] == short:
        return True
    return _ordered_containment(short, long) >= 0.86


def _ordered_containment(short: list[str], long: list[str]) -> float:
    index = 0
    matched = 0
    for token in short:
        while index < len(long) and long[index] != token:
            index += 1
        if index >= len(long):
            continue
        matched += 1
        index += 1
    return matched / len(short)
