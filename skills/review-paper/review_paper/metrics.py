"""Deterministic diagnostics and humanization scoring for papers."""
from __future__ import annotations

import math
from collections import Counter

from .models import DiagnosticsSummary, HumanizationReport, PaperModel

TRANSITIONS = {
    "furthermore", "moreover", "in addition", "overall", "in conclusion",
    "therefore", "however", "interestingly", "notably", "thus",
}
HEDGES = {"may", "might", "could", "appears", "suggests", "likely", "possibly"}
CERTAINTY = {"clearly", "obviously", "definitely", "demonstrates", "proves", "certainly"}
PASSIVE_SIGNALS = (" was ", " were ", " is being ", " are being ", " been ")

BUZZWORDS = {
    "leverages", "paradigm", "unprecedented", "synergy", "holistic",
    "cutting-edge", "state-of-the-art", "groundbreaking", "transformative",
    "revolutionary", "novel", "robust", "scalable", "innovative",
}

SECTION_EXPECTATIONS = {
    "abstract": ["problem", "method", "result", "contribution"],
    "introduction": ["problem", "gap", "contribution"],
    "related work": ["prior", "compare", "position"],
    "methods": ["procedure", "setup", "parameters"],
    "results": ["metrics", "comparison", "interpretation"],
    "discussion": ["implication", "limitations", "interpretation"],
    "conclusion": ["summary", "limitations", "future"],
}

KEYWORD_MAP = {
    "problem": ["problem", "challenge", "difficulty", "limitation"],
    "method": ["method", "approach", "we propose", "we introduce"],
    "result": ["result", "improves", "outperforms", "findings"],
    "contribution": ["contribution", "we show", "we demonstrate"],
    "gap": ["gap", "however", "existing work", "prior work"],
    "prior": ["prior", "previous", "existing", "related"],
    "compare": ["compared", "comparison", "baseline", "relative to"],
    "position": ["differ", "unlike", "extends", "builds on"],
    "procedure": ["procedure", "pipeline", "steps", "algorithm"],
    "setup": ["setup", "environment", "dataset", "benchmark"],
    "parameters": ["parameter", "hyperparameter", "configuration"],
    "metrics": ["accuracy", "f1", "metric", "score"],
    "comparison": ["baseline", "compared", "relative to", "versus"],
    "interpretation": ["suggests", "indicates", "implies", "interpret"],
    "implication": ["implication", "meaning", "suggests", "broader"],
    "limitations": ["limitation", "constraint", "caution", "future work"],
    "summary": ["summary", "in this work", "we presented"],
    "future": ["future", "next", "further work"],
}


def _stats(values: list[int]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    return mean, math.sqrt(variance)


def _flatten_sentences(paper: PaperModel) -> list[str]:
    return [
        s.text
        for sec in paper.sections
        for para in sec.paragraphs
        for s in para.sentences
    ]


def _flatten_paragraphs(paper: PaperModel) -> list[str]:
    return [p.text for sec in paper.sections for p in sec.paragraphs]


def compute_diagnostics(paper: PaperModel) -> DiagnosticsSummary:
    sentence_lengths = [len(s.split()) for s in _flatten_sentences(paper)]
    paragraph_lengths = [len(p.split()) for p in _flatten_paragraphs(paper)]
    sentence_mean, sentence_stddev = _stats(sentence_lengths)
    paragraph_mean, paragraph_stddev = _stats(paragraph_lengths)

    tokens = [
        tok.strip(".,;:!?()[]{}\"'").lower() for tok in paper.raw_text.split()
    ]
    tokens = [t for t in tokens if t]
    lexical_diversity = (len(set(tokens)) / len(tokens)) if tokens else 0.0

    openings = Counter()
    transitions = Counter()
    hedge_hits = 0
    certainty_hits = 0
    passive_hits = 0

    for paragraph in _flatten_paragraphs(paper):
        words = [
            w.strip(".,;:!?()[]{}\"'").lower()
            for w in paragraph.split()
            if w.strip()
        ]
        if words:
            openings[" ".join(words[:3])] += 1
        lowered = paragraph.lower()
        for transition in TRANSITIONS:
            if transition in lowered:
                transitions[transition] += lowered.count(transition)
        hedge_hits += sum(1 for w in words if w in HEDGES)
        certainty_hits += sum(1 for w in words if w in CERTAINTY)
        passive_hits += sum(lowered.count(signal) for signal in PASSIVE_SIGNALS)

    section_coverage: dict[str, list[str]] = {}
    for section in paper.sections:
        title = section.title.lower()
        body = " ".join(p.text.lower() for p in section.paragraphs)
        missing: list[str] = []
        for section_name, expectations in SECTION_EXPECTATIONS.items():
            if section_name in title:
                for expectation in expectations:
                    if not any(k in body for k in KEYWORD_MAP[expectation]):
                        missing.append(expectation)
        if missing:
            section_coverage[section.title] = missing

    total_tokens = max(1, len(tokens))
    return DiagnosticsSummary(
        sentence_mean=sentence_mean,
        sentence_stddev=sentence_stddev,
        paragraph_mean=paragraph_mean,
        paragraph_stddev=paragraph_stddev,
        lexical_diversity=lexical_diversity,
        repeated_openings=[k for k, v in openings.items() if v >= 3],
        repeated_transitions=[k for k, v in transitions.items() if v >= 3],
        hedge_density=hedge_hits / total_tokens,
        certainty_density=certainty_hits / total_tokens,
        passive_voice_signals=passive_hits,
        section_coverage=section_coverage,
    )


def compute_humanization(paper: PaperModel, diag: DiagnosticsSummary) -> HumanizationReport:
    """Analyze AI-generation signals and produce a humanization score.

    Higher score = more human-sounding.  Lower score = more AI-tells detected.
    """
    ai_signals: list[str] = []
    human_signals: list[str] = []
    score = 1.0

    # Burstiness: humans vary sentence length; AI is uniform
    if diag.sentence_stddev < 4.0:
        ai_signals.append(
            f"low sentence burstiness (stddev={diag.sentence_stddev:.1f}, "
            f"human papers typically >6)",
        )
        score -= 0.15
    elif diag.sentence_stddev > 7.0:
        human_signals.append(
            f"good sentence variation (stddev={diag.sentence_stddev:.1f})",
        )

    if diag.paragraph_stddev < 20.0:
        ai_signals.append(
            f"uniform paragraph lengths (stddev={diag.paragraph_stddev:.1f})",
        )
        score -= 0.10

    # Lexical diversity: AI tends to reuse the same words
    if diag.lexical_diversity < 0.35:
        ai_signals.append(
            f"low lexical diversity ({diag.lexical_diversity:.3f}, "
            f"suggests repetitive vocabulary)",
        )
        score -= 0.15
    elif diag.lexical_diversity > 0.55:
        human_signals.append(
            f"rich vocabulary (diversity={diag.lexical_diversity:.3f})",
        )

    # Transition overuse: AI loves "furthermore", "moreover"
    if diag.repeated_transitions:
        ai_signals.append(
            f"overused transitions: {', '.join(diag.repeated_transitions[:5])}",
        )
        score -= 0.10 * min(len(diag.repeated_transitions), 3)

    # Repeated paragraph openings
    if diag.repeated_openings:
        ai_signals.append(
            f"repeated paragraph openings: {', '.join(diag.repeated_openings[:3])}",
        )
        score -= 0.10

    # Hedge/certainty balance
    if diag.hedge_density < 0.002 and diag.certainty_density < 0.002:
        ai_signals.append("flat epistemic stance (no hedging or certainty markers)")
        score -= 0.05
    elif 0.005 < diag.hedge_density < 0.04:
        human_signals.append("natural hedging level")

    if diag.certainty_density > 0.02:
        ai_signals.append(
            f"excessive certainty markers (density={diag.certainty_density:.3f})",
        )
        score -= 0.05

    # Passive voice: some is natural, none or excessive is a signal
    sentences = _flatten_sentences(paper)
    if sentences:
        passive_ratio = diag.passive_voice_signals / max(1, len(sentences))
        if passive_ratio > 0.3:
            ai_signals.append(
                f"heavy passive voice ({diag.passive_voice_signals} signals "
                f"in {len(sentences)} sentences)",
            )
            score -= 0.05

    # Buzzword detection
    lowered = paper.raw_text.lower()
    found_buzzwords = [b for b in BUZZWORDS if b in lowered]
    if len(found_buzzwords) >= 3:
        ai_signals.append(f"buzzword clustering: {', '.join(found_buzzwords[:5])}")
        score -= 0.05 * min(len(found_buzzwords), 3)

    # Section completeness (missing rhetorical components)
    if diag.section_coverage:
        missing_count = sum(len(v) for v in diag.section_coverage.values())
        if missing_count >= 3:
            ai_signals.append(
                f"{missing_count} missing section-purpose elements "
                f"across {len(diag.section_coverage)} sections",
            )
            score -= 0.05

    score = max(0.0, min(1.0, score))

    return HumanizationReport(
        ai_signals=ai_signals,
        human_signals=human_signals,
        humanization_score=round(score, 3),
    )
