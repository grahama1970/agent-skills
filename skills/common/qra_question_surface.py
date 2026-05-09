"""Deterministic guards for malformed QRA question surfaces.

These checks reject records where the `question` field is only a heading,
control ID, opaque key, or short label fragment instead of a standalone
question or review task.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


FAIL_VERDICT = "FAIL_NON_QUESTION_SURFACE"
PASS_VERDICT = "PASS"
ADVERSARIAL_CLASSIFICATION = "adversarial"
MALFORMED_CLASSIFICATION = "malformed"

_ACCEPTED_STEMS = {
    "what",
    "why",
    "how",
    "when",
    "where",
    "which",
    "who",
    "given",
    "explain",
    "compare",
    "assess",
    "identify",
    "describe",
}
_TASK_VERBS = {
    "describe",
    "explain",
    "compare",
    "assess",
    "identify",
    "prioritize",
    "mitigate",
    "detect",
    "relate",
    "support",
    "affect",
    "address",
    "cover",
    "reduce",
    "prevent",
    "verify",
    "validate",
    "apply",
    "analyze",
    "evaluate",
    "recommend",
    "summarize",
}
_KNOWN_HEADINGS = {
    "decision surface",
    "related controls",
    "control relationship",
    "attack pattern",
    "evidence",
    "trace",
}

_ADVERSARIAL_MARKER_RE = re.compile(
    r"\b(?:"
    r"adversarial(?:\s+training)?|"
    r"retained\s+for\s+adversarial\s+training|"
    r"ambiguous\s+referent|"
    r"plan\s+repair|"
    r"negative\s+example|"
    r"guardrail\s+fixture"
    r")\b",
    re.IGNORECASE,
)

_CONTROL_ID_RE = re.compile(
    r"\b(?:"
    r"CAPEC-\d+|CWE-\d+|CVE-\d{4}-\d+|T\d{4}(?:\.\d{3})?|"
    r"IA-\d{4}(?:\.\d+)?|EXF-\d{4}(?:\.\d+)?|DE-\d{4}(?:\.\d+)?|"
    r"SV-[A-Z]{2}-\d+(?:\.\d+)?|CM\d{4}|ST\d{4}|D3-[A-Z0-9-]+|"
    r"AC-\d+(?:\(\d+\))?|SI-\d+(?:\(\d+\))?|SA-\d+(?:\(\d+\))?|"
    r"SC-\d+(?:\(\d+\))?|IA-\d+(?:\(\d+\))?"
    r")\b",
    re.IGNORECASE,
)
_HEX_TOKEN_RE = re.compile(r"\b[0-9a-f]{12,}\b", re.IGNORECASE)
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")


@dataclass(frozen=True)
class QuestionSurfaceFinding:
    verdict: str
    rule_ids: list[str] = field(default_factory=list)
    blocking_entities: list[str] = field(default_factory=list)
    reason: str = ""
    classification: str = ""
    adversarial: bool = False
    adversarial_type: str = ""

    @property
    def ok(self) -> bool:
        return self.verdict == PASS_VERDICT

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "ok": self.ok,
            "rule_ids": self.rule_ids,
            "blocking_entities": self.blocking_entities,
            "reason": self.reason,
            "classification": self.classification,
            "adversarial": self.adversarial,
            "adversarial_type": self.adversarial_type,
        }


def normalize_question_surface(question: str | None) -> str:
    return re.sub(r"\s+", " ", (question or "").strip())


def extract_control_ids(text: str) -> list[str]:
    return sorted({match.group(0) for match in _CONTROL_ID_RE.finditer(text)})


def extract_hex_tokens(text: str) -> list[str]:
    return sorted({match.group(0) for match in _HEX_TOKEN_RE.finditer(text)})


def detect_adversarial_markers(text: str | None) -> list[str]:
    surface = normalize_question_surface(text)
    return sorted({match.group(0) for match in _ADVERSARIAL_MARKER_RE.finditer(surface)})


def detect_non_question_surface(question: str | None) -> QuestionSurfaceFinding:
    text = normalize_question_surface(question)
    if not text:
        return QuestionSurfaceFinding(
            verdict=FAIL_VERDICT,
            rule_ids=["QS01"],
            reason="question is blank",
        )

    lower = text.lower()
    words = _WORD_RE.findall(text)
    first_word = words[0].lower() if words else ""
    ids = extract_control_ids(text)
    hex_tokens = extract_hex_tokens(text)
    adversarial_markers = detect_adversarial_markers(text)
    rule_ids: list[str] = []
    verb_tokens = {word.lower() for word in words}
    has_predicate = bool(verb_tokens & _TASK_VERBS)

    stripped = _CONTROL_ID_RE.sub(" ", text)
    stripped = _HEX_TOKEN_RE.sub(" ", stripped)
    stripped = re.sub(r"[^A-Za-z ]+", " ", stripped)
    stripped_words = _WORD_RE.findall(stripped)
    stripped_lower = " ".join(stripped_words).lower()
    is_short_heading = 0 < len(stripped_words) <= 4
    matched_heading = next((heading for heading in _KNOWN_HEADINGS if heading in stripped_lower), "")
    is_known_heading = bool(matched_heading)
    is_title_like = bool(stripped_words) and all(word[:1].isupper() for word in stripped_words)

    is_question_or_task = "?" in text or first_word in _ACCEPTED_STEMS or has_predicate
    looks_like_fragment = bool(ids or hex_tokens or is_known_heading or (is_short_heading and is_title_like))
    if not is_question_or_task and looks_like_fragment:
        rule_ids.append("QS01")
    if (ids or hex_tokens) and (not stripped_words or ((is_short_heading or is_known_heading) and not is_question_or_task)):
        rule_ids.append("QS02")

    # A hash/key used in a terse surface is almost always metadata rendered as a question.
    if hex_tokens and (len(words) <= 8 or not is_question_or_task):
        rule_ids.append("QS03")

    if not has_predicate and not is_question_or_task and looks_like_fragment:
        rule_ids.append("QS04")

    # ID-only strings are invalid even if they slip past heading stripping.
    if ids and not stripped_words:
        rule_ids.append("QS02")

    if rule_ids:
        blocking = ids + hex_tokens
        if matched_heading:
            blocking.insert(0, matched_heading.title())
        return QuestionSurfaceFinding(
            verdict=FAIL_VERDICT,
            rule_ids=sorted(set(rule_ids)),
            blocking_entities=blocking,
            reason="question surface is a heading, ID, opaque key, or fragment rather than a standalone question",
            classification=ADVERSARIAL_CLASSIFICATION if adversarial_markers else MALFORMED_CLASSIFICATION,
            adversarial=bool(adversarial_markers),
            adversarial_type="non_question_surface_ambiguous_referent" if adversarial_markers else "",
        )

    return QuestionSurfaceFinding(verdict=PASS_VERDICT, classification="valid")
