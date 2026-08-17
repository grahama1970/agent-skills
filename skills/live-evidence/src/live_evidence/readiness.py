"""Decide when to consult the resolver, and hold Ask until a question is ready.

Two separate jobs, deliberately kept apart:

`ReadinessTrigger` is a deterministic floor. It answers only "has enough
changed to be worth a model call?" and never decides whether a question exists.
It is punctuation-independent on purpose: measured on live PipeWire capture,
speech-to-text emitted ~8 events/sec, exactly 1 `final` in 45 seconds, and
inconsistent punctuation (7 periods across 977 chars in one buffer, 17 across
1583 in another). Sentence-boundary detection also cannot help, because a
buffer can end at a grammatically complete sentence while the question itself
is still unfinished -- observed directly on a captured snapshot that ended with
a clean period mid-problem-statement.

`ReadinessVerdict` is the resolver's judgment. Question detection, completeness,
and clarifying questions are semantic work and belong to the model. The
heuristic trigger that preceded this produced 3 cards from a video's opening
narration and 0 from the real questions.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ClarifyingQuestion(BaseModel):
    """One clarification the resolver decided is worth asking."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1, max_length=80)
    question: str = Field(min_length=1, max_length=400)
    why_it_matters: str | None = Field(default=None, max_length=400)
    default_assumption: str | None = Field(default=None, max_length=400)
    blocking: bool = False


class ReadinessVerdict(BaseModel):
    """Structured resolver output governing whether Ask may run.

    `question_asked_yet` and `ready_to_answer` are deliberately distinct: a
    question routinely exists long before it is answerable, and conflating them
    is what let a truncated problem statement reach the solver.
    """

    model_config = ConfigDict(extra="ignore")

    question_asked_yet: bool = False
    question_complete: bool = False
    ready_to_answer: bool = False
    blocking_reason: Literal[
        "none",
        "truncated",
        "awaiting_more_speech",
        "needs_clarification",
        "not_a_question",
    ] = "not_a_question"
    question_type: Literal["research", "code", "leetcode", "client", "none"] = "none"
    actionable: bool = False
    canonical_question: str = ""
    clarifying_questions: list[ClarifyingQuestion] = Field(default_factory=list, max_length=6)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @property
    def may_invoke_ask(self) -> bool:
        """Ask runs only for a ready, actionable, typed question."""

        return (
            self.ready_to_answer
            and self.actionable
            and self.question_type != "none"
            and self.blocking_reason == "none"
        )


@dataclass
class TriggerOutcome:
    """Why the trigger did or did not fire, so decisions stay inspectable."""

    consult: bool
    reason: str
    new_chars: int
    gap_s: float


@dataclass
class ReadinessTrigger:
    """Cheap floor deciding when the resolver is worth calling.

    Fires on a speech pause or on accumulated new text, never on punctuation.
    A false positive costs one resolver call, which the resolver then rejects;
    a false negative silently drops a question. The thresholds are therefore
    tuned to fail toward calling.
    """

    min_new_chars: int = 120
    # Speech pauses are detected as text STABILITY, not as gaps between events.
    # Measured on live capture: events arrive at 8.4/sec on a decoder cadence
    # whether or not anyone is speaking, so an arrival-gap trigger never fires
    # (0 of 8 fires across three configurations). A buffer that stops changing
    # is the only pause signal this stream actually carries.
    stable_for_s: float = 1.5
    min_interval_s: float = 3.0

    _consulted_len: int = field(default=0, init=False)
    _last_consult_at: float | None = field(default=None, init=False)
    _last_event_at: float | None = field(default=None, init=False)
    _last_text: str = field(default="", init=False)
    _last_change_at: float | None = field(default=None, init=False)

    def observe(self, buffer_text: str, now: float) -> TriggerOutcome:
        """Record an event arrival and report whether to consult the resolver."""

        gap_s = 0.0 if self._last_event_at is None else max(0.0, now - self._last_event_at)
        self._last_event_at = now
        if buffer_text != self._last_text:
            self._last_text = buffer_text
            self._last_change_at = now
        stable_s = 0.0 if self._last_change_at is None else max(0.0, now - self._last_change_at)
        new_chars = max(0, len(buffer_text) - self._consulted_len)

        if new_chars <= 0:
            return TriggerOutcome(False, "no_new_text", new_chars, gap_s)
        if self._last_consult_at is not None and (now - self._last_consult_at) < self.min_interval_s:
            return TriggerOutcome(False, "rate_limited", new_chars, gap_s)
        if stable_s >= self.stable_for_s:
            return self._fire(buffer_text, now, "speech_settled", new_chars, gap_s)
        if new_chars >= self.min_new_chars:
            return self._fire(buffer_text, now, "char_delta", new_chars, gap_s)
        return TriggerOutcome(False, "accumulating", new_chars, gap_s)

    def _fire(self, buffer_text: str, now: float, reason: str, new_chars: int, gap_s: float) -> TriggerOutcome:
        self._consulted_len = len(buffer_text)
        self._last_consult_at = now
        return TriggerOutcome(True, reason, new_chars, gap_s)

    def reset(self) -> None:
        """Forget consultation history, e.g. when a session restarts."""

        self._consulted_len = 0
        self._last_consult_at = None
        self._last_event_at = None


_JSON_BLOCK = re.compile(r"\{.*\}", re.S)


def parse_verdict(raw: str) -> ReadinessVerdict | None:
    """Parse resolver output, failing closed rather than guessing.

    An unparseable verdict must never read as permission to answer, so this
    returns None and callers treat that as "not ready".
    """

    if not raw or not raw.strip():
        return None
    match = _JSON_BLOCK.search(raw)
    if match is None:
        return None
    try:
        payload: Any = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    verdicts = payload.get("verdicts")
    if isinstance(verdicts, list) and verdicts:
        payload = verdicts[-1] if isinstance(verdicts[-1], dict) else payload
    try:
        return ReadinessVerdict.model_validate(payload)
    except Exception:
        return None
