"""Deterministic turn-trigger and topic extraction.

The trigger intentionally avoids an LLM in the listening loop. It operates on a
small documented grammar: final or stabilized interviewer turns, question words,
question punctuation, and profile watch terms. This keeps latency and false
activation behavior inspectable.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic

from .config import InterviewProfile
from .models import Speaker, TranscriptEvent, TranscriptKind


QUESTION_LEADS = {
    "how",
    "what",
    "why",
    "when",
    "where",
    "who",
    "which",
    "can",
    "could",
    "would",
    "will",
    "do",
    "does",
    "did",
    "have",
    "has",
    "tell",
    "describe",
    "explain",
    "walk",
}

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "i",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "our",
    "that",
    "the",
    "their",
    "this",
    "to",
    "we",
    "with",
    "you",
    "your",
    "about",
    "alright",
    "assume",
    "correct",
    "even",
    "just",
    "like",
    "right",
    "same",
    "something",
    "still",
    "though",
}

CODE_PROMPT_TERMS = {
    "algorithm",
    "array",
    "binary",
    "characters",
    "closing",
    "complexity",
    "function",
    "find",
    "implement",
    "input",
    "lowercase",
    "minimum",
    "opening",
    "output",
    "parentheses",
    "parenthesis",
    "removal",
    "remove",
    "return",
    "stack",
    "string",
    "strings",
    "valid",
}

CODE_PROMPT_PHRASES = {
    "coding language",
    "closing parenthesis",
    "closing parentheses",
    "function and",
    "opening parenthesis",
    "opening parentheses",
    "remove extra",
    "string input",
    "valid string",
    "parentheses string",
    "parenthesis string",
    "minimum number",
    "input string",
    "return the",
    "stack type",
}


@dataclass(frozen=True, slots=True)
class TriggerDecision:
    """Accepted evidence-retrieval trigger."""

    event_id: str
    query: str
    thread: str
    reason: str
    code_related: bool = False


class TriggerEngine:
    """Stateful deduplication and trigger classification."""

    def __init__(
        self,
        profile: InterviewProfile,
        cooldown_s: float = 4.0,
        code_cooldown_s: float = 90.0,
    ) -> None:
        self._profile = profile
        self._cooldown_s = cooldown_s
        self._code_cooldown_s = code_cooldown_s
        self._last_key = ""
        self._last_triggered_at = 0.0
        self._last_code_triggered_at = 0.0
        self._watch_terms = {
            term.casefold() for term in profile.watch_terms if term.strip()
        }
        self._aliases = {
            alias.casefold(): project
            for project, aliases in profile.project_aliases.items()
            for alias in [project, *aliases]
            if alias.strip()
        }

    def decide(self, event: TranscriptEvent) -> TriggerDecision | None:
        """Return a trigger only for substantive interviewer evidence moments."""

        if event.speaker is not Speaker.INTERVIEWER:
            return None
        if event.kind is not TranscriptKind.FINAL:
            return None

        tokens = tokenize(event.text)
        if len(tokens) < 4:
            return None

        normalized = " ".join(tokens)
        code_related = is_code_prompt(event.text)
        now = monotonic()
        code_trigger_ready = is_code_question(event.text)
        if code_related and not code_trigger_ready:
            return None
        key = _dedupe_key(tokens, code_related=code_trigger_ready)
        if key == self._last_key and now - self._last_triggered_at < self._cooldown_s:
            return None
        if code_trigger_ready and now - self._last_code_triggered_at < self._code_cooldown_s:
            return None

        first = tokens[0].casefold()
        lower_text = event.text.casefold()
        matched_term = next((term for term in self._watch_terms if term in lower_text), None)
        matched_alias = next((alias for alias in self._aliases if alias in lower_text), None)
        is_question = event.text.rstrip().endswith("?") or first in QUESTION_LEADS
        if not (is_question or matched_term or matched_alias or code_trigger_ready):
            return None

        reason = "question"
        if code_trigger_ready:
            reason = "code-question"
        elif matched_alias:
            reason = f"project:{self._aliases[matched_alias]}"
        elif matched_term:
            reason = f"watch-term:{matched_term}"

        self._last_key = key
        self._last_triggered_at = now
        if code_trigger_ready:
            self._last_code_triggered_at = now
        return TriggerDecision(
            event_id=event.event_id,
            query=event.text,
            thread=extract_thread(event.text, self._profile),
            reason=reason,
            code_related=code_trigger_ready,
        )


def tokenize(text: str) -> list[str]:
    """Tokenize human text using bounded alphanumeric punctuation rules."""

    tokens: list[str] = []
    current: list[str] = []
    for char in text:
        if char.isalnum() or char in {"-", "_", "/", "."}:
            current.append(char)
        elif current:
            tokens.append("".join(current).strip("._-/"))
            current = []
    if current:
        tokens.append("".join(current).strip("._-/"))
    return [token for token in tokens if token]


def extract_thread(text: str, profile: InterviewProfile) -> str:
    """Create a glanceable topic label from aliases and high-signal terms."""

    lower_text = text.casefold()
    projects = [
        project
        for project, aliases in profile.project_aliases.items()
        if any(alias.casefold() in lower_text for alias in [project, *aliases])
    ]
    if projects:
        return " · ".join(projects[:3])

    selected: list[str] = []
    for token in tokenize(text):
        normalized = token.casefold()
        if normalized in STOPWORDS or len(normalized) < 4:
            continue
        if normalized not in {item.casefold() for item in selected}:
            selected.append(token)
        if len(selected) == 5:
            break
    return " · ".join(selected) if selected else "Current discussion"


def search_terms(text: str, limit: int = 8) -> list[str]:
    """Return bounded fixed-string terms suitable for ripgrep."""

    terms: list[str] = []
    for token in tokenize(text):
        normalized = token.casefold()
        if normalized in QUESTION_LEADS or normalized in STOPWORDS or len(normalized) < 4:
            continue
        if normalized not in {term.casefold() for term in terms}:
            terms.append(token)
        if len(terms) >= limit:
            break
    return terms


def is_code_prompt(text: str) -> bool:
    """Detect interview-style coding prompts without invoking a model."""

    lower = text.casefold()
    phrase_hits = sum(1 for phrase in CODE_PROMPT_PHRASES if phrase in lower)
    term_hits = len({token.casefold() for token in tokenize(text)} & CODE_PROMPT_TERMS)
    return phrase_hits >= 1 and term_hits >= 3


def is_code_question(text: str) -> bool:
    """Detect code prompts ready for the Ask solution lane."""

    return is_code_prompt(text) and _has_code_action(text)


def _dedupe_key(tokens: list[str], *, code_related: bool) -> str:
    """Use stable high-signal keys so growing STT partials do not card-storm."""

    if code_related:
        high_signal: list[str] = []
        for token in tokens:
            normalized = token.casefold()
            if normalized not in CODE_PROMPT_TERMS or normalized in high_signal:
                continue
            high_signal.append(normalized)
            if len(high_signal) == 5:
                break
        return "code:" + " ".join(high_signal)
    high_signal = []
    for token in tokens:
        normalized = token.casefold()
        if normalized in QUESTION_LEADS or normalized in STOPWORDS or len(normalized) < 4:
            continue
        if normalized not in high_signal:
            high_signal.append(normalized)
        if len(high_signal) == 5:
            break
    return "question:" + " ".join(high_signal) if high_signal else " ".join(tokens[:8]).casefold()


def _has_code_action(text: str) -> bool:
    tokens = {token.casefold() for token in tokenize(text)}
    return bool(tokens & {"find", "makes", "minimum", "output", "return", "remove", "removal", "stack"})
