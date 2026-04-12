"""
Grounding quality checker for CWE QRAs.

Sits on top of qra_schema.py to do heuristic second-pass validation:
- sentence-level support checks for reasoning and answer
- pair usefulness / genericness checks
- pair-to-pair redundancy checks

This is heuristic grounding validation, not full semantic proof.
"""
from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field
from typing import Iterable

from qra_schema import EvidenceItem, QRAPair, QRAResult


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "because",
    "by",
    "can",
    "could",
    "do",
    "does",
    "for",
    "from",
    "has",
    "have",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "may",
    "might",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "them",
    "there",
    "these",
    "this",
    "those",
    "to",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "while",
    "who",
    "why",
    "will",
    "with",
    "within",
    "without",
}

GENERIC_SECURITY_TERMS = {
    "security",
    "risk",
    "weakness",
    "vulnerability",
    "issue",
    "problem",
    "threat",
    "impact",
    "mitigation",
    "attacker",
    "software",
    "system",
    "code",
    "protection",
}

PAIR_TYPE_EXPECTED_HINTS: dict[str, set[str]] = {
    "implementation_guidance": {
        "mitigate",
        "prevent",
        "reduce",
        "avoid",
        "library",
        "compiler",
        "boundary",
        "copy",
        "buffer",
        "language",
    },
    "assessment_criteria": {
        "look",
        "review",
        "assess",
        "audit",
        "verify",
        "check",
        "implementation",
        "boundary",
        "copy",
        "buffer",
    },
    "scope_clarification": {
        "cover",
        "covered",
        "covers",
        "scope",
        "include",
        "included",
        "boundary",
        "read",
        "write",
        "memory",
    },
    "risk_context": {
        "risk",
        "impact",
        "matter",
        "serious",
        "execution",
        "crash",
        "availability",
        "information",
        "exploit",
    },
}


@dataclass(slots=True)
class CheckerConfig:
    # Sentence support thresholds (tuned via test_grounding_checker.py)
    # Well-grounded sentences empirically show overlap 0.25-0.50, jaccard 0.17-0.33
    min_sentence_token_overlap: float = 0.25  # lowered from 0.45
    min_sentence_quote_jaccard: float = 0.15  # lowered from 0.20
    # Question/answer usefulness thresholds
    min_question_evidence_overlap: float = 0.10  # lowered from 0.18 - questions often use different words
    min_answer_evidence_overlap: float = 0.20  # lowered from 0.25
    # Redundancy detection
    redundancy_threshold: float = 0.72
    near_duplicate_question_threshold: float = 0.55  # lowered from 0.80 - no stemming, so "cover"/"covered" differ
    # Genericness detection
    min_distinctive_token_count: int = 2  # lowered from 3
    max_unknown_token_ratio_in_sentence: float = 0.65  # raised from 0.60


@dataclass(slots=True)
class SentenceCheck:
    text: str
    supported: bool
    best_quote: str | None
    token_overlap: float
    quote_jaccard: float
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PairCheck:
    pair_id: str
    passed: bool
    reasoning_checks: list[SentenceCheck]
    answer_checks: list[SentenceCheck]
    usefulness_warnings: list[str] = field(default_factory=list)
    redundancy_warnings: list[str] = field(default_factory=list)

    @property
    def all_warnings(self) -> list[str]:
        warnings: list[str] = []
        warnings.extend(self.usefulness_warnings)
        warnings.extend(self.redundancy_warnings)
        for item in self.reasoning_checks + self.answer_checks:
            warnings.extend(item.warnings)
        return warnings


@dataclass(slots=True)
class RedundancyCheck:
    pair_id_a: str
    pair_id_b: str
    similarity: float
    flagged: bool
    reason: str


@dataclass(slots=True)
class GroundingReport:
    passed: bool
    pair_checks: list[PairCheck]
    redundancy_checks: list[RedundancyCheck]

    @property
    def errors(self) -> list[str]:
        errors: list[str] = []
        for pair in self.pair_checks:
            for check in pair.reasoning_checks + pair.answer_checks:
                if not check.supported:
                    errors.append(
                        f"{pair.pair_id}: unsupported sentence: {check.text}"
                    )
        for item in self.redundancy_checks:
            if item.flagged:
                errors.append(
                    f"redundancy: {item.pair_id_a} vs {item.pair_id_b} ({item.reason})"
                )
        return errors


def normalize_text(text: str) -> str:
    text = text.lower().strip()
    text = text.replace("\u2019", "'")
    text = re.sub(r"\s+", " ", text)
    return text


def split_sentences(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [part.strip() for part in parts if part.strip()]


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_#\-]+", normalize_text(text))


def content_tokens(text: str) -> set[str]:
    tokens = tokenize(text)
    return {
        token
        for token in tokens
        if token not in STOPWORDS and len(token) > 1
    }


def jaccard_similarity(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def overlap_ratio(source: set[str], target: set[str]) -> float:
    """
    Fraction of source tokens covered by target tokens.
    """
    if not source:
        return 1.0
    return len(source & target) / len(source)


def build_evidence_token_set(evidence: Iterable[EvidenceItem]) -> set[str]:
    tokens: set[str] = set()
    for item in evidence:
        tokens |= content_tokens(item.quote)
    return tokens


def best_quote_match(
    sentence: str,
    evidence: list[EvidenceItem],
) -> tuple[str | None, float, float]:
    sentence_tokens = content_tokens(sentence)

    best_quote: str | None = None
    best_overlap = 0.0
    best_jaccard = 0.0

    for item in evidence:
        quote = item.quote
        quote_tokens = content_tokens(quote)

        if normalize_text(sentence) in normalize_text(quote):
            return quote, 1.0, 1.0

        token_overlap = overlap_ratio(sentence_tokens, quote_tokens)
        quote_jaccard = jaccard_similarity(sentence_tokens, quote_tokens)

        if (token_overlap, quote_jaccard) > (best_overlap, best_jaccard):
            best_quote = quote
            best_overlap = token_overlap
            best_jaccard = quote_jaccard

    return best_quote, best_overlap, best_jaccard


def sentence_has_too_many_unknown_tokens(
    sentence: str,
    evidence_tokens: set[str],
    config: CheckerConfig,
) -> bool:
    sent_tokens = content_tokens(sentence)
    if not sent_tokens:
        return False

    unknown = {
        tok for tok in sent_tokens
        if tok not in evidence_tokens and tok not in GENERIC_SECURITY_TERMS
    }
    unknown_ratio = len(unknown) / len(sent_tokens)
    return unknown_ratio > config.max_unknown_token_ratio_in_sentence


def check_sentence_support(
    sentence: str,
    evidence: list[EvidenceItem],
    config: CheckerConfig,
) -> SentenceCheck:
    evidence_tokens = build_evidence_token_set(evidence)
    best_quote, token_overlap, quote_jaccard = best_quote_match(sentence, evidence)

    supported = (
        token_overlap >= config.min_sentence_token_overlap
        or quote_jaccard >= config.min_sentence_quote_jaccard
    )

    warnings: list[str] = []

    if not supported:
        warnings.append("Sentence does not appear sufficiently grounded in the provided evidence.")

    if sentence_has_too_many_unknown_tokens(sentence, evidence_tokens, config):
        warnings.append("Sentence introduces several tokens not present in the evidence.")

    return SentenceCheck(
        text=sentence,
        supported=supported,
        best_quote=best_quote,
        token_overlap=token_overlap,
        quote_jaccard=quote_jaccard,
        warnings=warnings,
    )


def check_block_support(
    text: str,
    evidence: list[EvidenceItem],
    config: CheckerConfig,
) -> list[SentenceCheck]:
    return [
        check_sentence_support(sentence, evidence, config)
        for sentence in split_sentences(text)
    ]


def check_pair_usefulness(pair: QRAPair, config: CheckerConfig) -> list[str]:
    warnings: list[str] = []

    evidence_tokens = build_evidence_token_set(pair.evidence)
    question_tokens = content_tokens(pair.question)
    answer_tokens = content_tokens(pair.answer)

    q_overlap = overlap_ratio(question_tokens, evidence_tokens)
    a_overlap = overlap_ratio(answer_tokens, evidence_tokens)

    if q_overlap < config.min_question_evidence_overlap:
        warnings.append(
            f"Question has low overlap with evidence tokens ({q_overlap:.2f}); it may be generic."
        )

    if a_overlap < config.min_answer_evidence_overlap:
        warnings.append(
            f"Answer has low overlap with evidence tokens ({a_overlap:.2f}); it may be weakly grounded."
        )

    distinctive_q_tokens = {
        tok for tok in question_tokens
        if tok not in GENERIC_SECURITY_TERMS
    }
    if len(distinctive_q_tokens) < config.min_distinctive_token_count:
        warnings.append("Question may be too generic or underspecified.")

    pair_type_name = pair.pair_type.value
    expected_hints = PAIR_TYPE_EXPECTED_HINTS.get(pair_type_name, set())
    combined_tokens = content_tokens(pair.question) | content_tokens(pair.answer)

    if expected_hints and not (combined_tokens & expected_hints):
        warnings.append(
            f"Question/answer content does not strongly reflect expected {pair_type_name} cues."
        )

    if pair.question.strip().endswith("?") is False:
        warnings.append("Question does not end with a question mark.")

    return warnings


def pair_similarity(pair_a: QRAPair, pair_b: QRAPair) -> float:
    a_tokens = (
        content_tokens(pair_a.question)
        | content_tokens(pair_a.answer)
        | content_tokens(pair_a.reasoning)
    )
    b_tokens = (
        content_tokens(pair_b.question)
        | content_tokens(pair_b.answer)
        | content_tokens(pair_b.reasoning)
    )
    return jaccard_similarity(a_tokens, b_tokens)


def question_similarity(pair_a: QRAPair, pair_b: QRAPair) -> float:
    return jaccard_similarity(
        content_tokens(pair_a.question),
        content_tokens(pair_b.question),
    )


def check_redundancy(
    pairs: list[QRAPair],
    config: CheckerConfig,
) -> list[RedundancyCheck]:
    results: list[RedundancyCheck] = []

    for pair_a, pair_b in itertools.combinations(pairs, 2):
        sim = pair_similarity(pair_a, pair_b)
        q_sim = question_similarity(pair_a, pair_b)

        flagged = False
        reason = ""

        if q_sim >= config.near_duplicate_question_threshold:
            flagged = True
            reason = f"near-duplicate questions (question similarity={q_sim:.2f})"
        elif sim >= config.redundancy_threshold:
            flagged = True
            reason = f"high overall content overlap (similarity={sim:.2f})"

        results.append(
            RedundancyCheck(
                pair_id_a=pair_a.pair_id,
                pair_id_b=pair_b.pair_id,
                similarity=max(sim, q_sim),
                flagged=flagged,
                reason=reason or "not flagged",
            )
        )

    return results


def run_grounding_checks(
    result: QRAResult,
    config: CheckerConfig | None = None,
) -> GroundingReport:
    config = config or CheckerConfig()

    pair_checks: list[PairCheck] = []

    for pair in result.pairs:
        reasoning_checks = check_block_support(pair.reasoning, pair.evidence, config)
        answer_checks = check_block_support(pair.answer, pair.evidence, config)
        usefulness_warnings = check_pair_usefulness(pair, config)

        passed = all(item.supported for item in reasoning_checks + answer_checks)

        pair_checks.append(
            PairCheck(
                pair_id=pair.pair_id,
                passed=passed,
                reasoning_checks=reasoning_checks,
                answer_checks=answer_checks,
                usefulness_warnings=usefulness_warnings,
            )
        )

    redundancy_checks = check_redundancy(result.pairs, config)

    pair_map = {pair_check.pair_id: pair_check for pair_check in pair_checks}
    for redundancy in redundancy_checks:
        if redundancy.flagged:
            pair_map[redundancy.pair_id_a].redundancy_warnings.append(
                f"Potential redundancy with {redundancy.pair_id_b}: {redundancy.reason}"
            )
            pair_map[redundancy.pair_id_b].redundancy_warnings.append(
                f"Potential redundancy with {redundancy.pair_id_a}: {redundancy.reason}"
            )

    passed = all(check.passed for check in pair_checks) and not any(
        item.flagged for item in redundancy_checks
    )

    return GroundingReport(
        passed=passed,
        pair_checks=pair_checks,
        redundancy_checks=redundancy_checks,
    )


def assert_grounding_passes(
    result: QRAResult,
    config: CheckerConfig | None = None,
) -> GroundingReport:
    report = run_grounding_checks(result, config=config)
    if not report.passed:
        raise ValueError("Grounding quality checks failed: " + "; ".join(report.errors))
    return report


def format_grounding_report(report: GroundingReport) -> str:
    lines: list[str] = []
    lines.append(f"passed={report.passed}")

    for pair in report.pair_checks:
        lines.append(f"- {pair.pair_id}: passed={pair.passed}")
        for check in pair.reasoning_checks:
            lines.append(
                "  reasoning: "
                f"supported={check.supported} "
                f"overlap={check.token_overlap:.2f} "
                f"jaccard={check.quote_jaccard:.2f} "
                f"text={check.text!r}"
            )
        for check in pair.answer_checks:
            lines.append(
                "  answer: "
                f"supported={check.supported} "
                f"overlap={check.token_overlap:.2f} "
                f"jaccard={check.quote_jaccard:.2f} "
                f"text={check.text!r}"
            )
        for warning in pair.all_warnings:
            lines.append(f"  warning: {warning}")

    for item in report.redundancy_checks:
        lines.append(
            f"- redundancy {item.pair_id_a} vs {item.pair_id_b}: "
            f"flagged={item.flagged} reason={item.reason}"
        )

    return "\n".join(lines)
