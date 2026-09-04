"""Deterministic scanner fallback for provider failures.

STT emits interleaved raw/punctuated restatements of one growing utterance
(debugger-proven 2026-09-01 at coordinator _fallback_scan). Keyed grouping
merges every restatement of one question regardless of adjacency, so a
provider outage cannot flood the card lane with phantom questions.

ponytail: keyword classifier; replace with a small local intent model if
provider outages make this too noisy.
"""

from __future__ import annotations

from .scanner import ScannedQuestion

_ASK_TERMS = (
    "?", "assume", "assumed", "defend", "design", "explain", "give me", "how ",
    "implement", "show", "tell me", "walk through", "what ", "which ", "why ",
)
_CODE_TERMS = ("algorithm", "complexity", "implement", "parentheses", "python", "coderpad", "sql", "string", "patch")
_SKIP_TERMS = ("thanks for joining", "end of the technical section", "remaining time")

# Public alias for cross-module use (coordinator_retrieve junk gate).
ASK_TERMS = _ASK_TERMS


def question_words(text: str) -> list[str]:
    return [
        word for word in "".join(
            char if char.isalnum() else " " for char in text.casefold()
        ).split()
        if len(word) > 2
    ]


def same_progressive_question(left: str, right: str) -> bool:
    left_words = question_words(left)
    right_words = question_words(right)
    if len(left_words) < 4 or len(right_words) < 4:
        return False
    short, long = (left_words, right_words) if len(left_words) <= len(right_words) else (right_words, left_words)
    if long[:len(short)] == short:
        return True
    matched = 0
    cursor = 0
    for word in short:
        while cursor < len(long) and long[cursor] != word:
            cursor += 1
        if cursor >= len(long):
            continue
        matched += 1
        cursor += 1
    return matched / len(short) >= 0.86


def scanner_skip_text(text: str) -> bool:
    lowered = text.casefold()
    return any(term in lowered for term in _SKIP_TERMS)


def matching_progressive_question_id(
    question_text: str, ledger: list[dict[str, object]]
) -> str | None:
    for item in ledger:
        known_text = str(item.get("text") or "")
        if same_progressive_question(known_text, question_text):
            return str(item.get("id") or "") or None
    return None


def ledger_text(question_id: str | None, ledger: list[dict[str, object]]) -> str:
    if not question_id:
        return ""
    for item in ledger:
        if str(item.get("id") or "") == question_id:
            return str(item.get("text") or "")
    return ""


def fallback_question_key(text: str) -> str:
    lowered = text.casefold()
    if "live coding" in lowered or "implement" in lowered:
        return "live-coding"
    if "assume" in lowered or "assumed" in lowered or "worker" in lowered or "eks" in lowered:
        return "runtime-failure"
    return " ".join(question_words(text)[:6])


def coherent_tail(events: list) -> list:
    """Drop interim events and collapse consecutive same-speaker restatements."""

    def norm(text: str) -> str:
        return "".join(ch for ch in (text or "").lower() if ch.isalnum() or ch == " ")

    collapsed: list = []
    for item in events:
        if getattr(item.kind, "value", item.kind) == "interim":
            continue
        if collapsed and collapsed[-1].speaker == item.speaker:
            prev, cur = norm(collapsed[-1].text), norm(item.text)
            if prev in cur or cur in prev or prev[:80] == cur[:80]:
                if len(cur) >= len(prev):
                    collapsed[-1] = item
                continue
        collapsed.append(item)
    return collapsed


def fallback_scan(
    turns: list[dict[str, object]], ledger: list[dict[str, object]]
) -> tuple[ScannedQuestion, ...]:
    """Classify interviewer asks without a provider; merge STT restatements."""

    known = {str(item.get("text") or "").strip().casefold() for item in ledger}
    questions: list[ScannedQuestion] = []
    question_keys: list[str] = []
    for turn in turns:
        text = str(turn.get("text") or "").strip()
        lowered = text.casefold()
        if str(turn.get("speaker") or "").casefold() != "interviewer":
            continue
        if len(text.split()) < 5 or lowered in known or scanner_skip_text(text):
            continue
        if not any(term in lowered for term in _ASK_TERMS):
            continue
        category = "code" if any(term in lowered for term in _CODE_TERMS) else "architecture"
        skills = ("memory", "code", "ripgrep", "ask") if category == "code" else ("memory", "code")
        question = ScannedQuestion(
            question_id=matching_progressive_question_id(text, ledger),
            text=text,
            status="complete",
            category=category,
            skills=skills,
            source_turn_ids=(str(turn.get("turn_id") or ""),),
        )
        key = fallback_question_key(text)
        match_index = question_keys.index(key) if key in question_keys else -1
        if match_index >= 0 or (questions and same_progressive_question(questions[-1].text, question.text)):
            index = match_index if match_index >= 0 else len(questions) - 1
            prior = questions[index]
            questions[index] = ScannedQuestion(
                question_id=prior.question_id or question.question_id,
                text=question.text if len(question_words(question.text)) >= len(question_words(prior.text)) else prior.text,
                status="complete",
                category=question.category,
                skills=question.skills,
                source_turn_ids=tuple(dict.fromkeys((*prior.source_turn_ids, *question.source_turn_ids))),
            )
            continue
        question_keys.append(key)
        questions.append(question)
    return tuple(questions)
