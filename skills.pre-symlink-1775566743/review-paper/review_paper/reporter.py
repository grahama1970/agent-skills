"""Report generation: revision plans, markdown reports, and output writers."""
from __future__ import annotations

import json
from pathlib import Path

from .models import AnalysisResult, RevisionItem


def build_revision_plan(result: AnalysisResult) -> list[RevisionItem]:
    items: list[RevisionItem] = []
    diagnostics = result.diagnostics

    if diagnostics.sentence_stddev < 6:
        items.append(RevisionItem(
            priority=1, target="global", category="style",
            issue="low sentence burstiness",
            action="vary sentence length in flagged sections",
        ))
    if diagnostics.paragraph_stddev < 35:
        items.append(RevisionItem(
            priority=1, target="global", category="structure",
            issue="uniform paragraph lengths",
            action="split dense paragraphs and merge thin fragments where needed",
        ))
    if diagnostics.lexical_diversity < 0.35:
        items.append(RevisionItem(
            priority=1, target="global", category="style",
            issue="low lexical diversity",
            action="replace repeated generic phrases with section-specific language",
        ))
    if diagnostics.repeated_openings:
        items.append(RevisionItem(
            priority=1, target="global", category="repetition",
            issue=(
                f"repeated paragraph openings: "
                f"{', '.join(diagnostics.repeated_openings[:5])}"
            ),
            action="rewrite paragraph openings to vary rhetorical entry points",
        ))
    if diagnostics.repeated_transitions:
        items.append(RevisionItem(
            priority=2, target="global", category="repetition",
            issue=(
                f"overused transitions: "
                f"{', '.join(diagnostics.repeated_transitions[:5])}"
            ),
            action=(
                "remove formulaic transitions and use more direct discourse links"
            ),
        ))
    if diagnostics.section_coverage:
        for section, missing in diagnostics.section_coverage.items():
            items.append(RevisionItem(
                priority=1, target=section, category="section-purpose",
                issue=f"missing expected section elements: {', '.join(missing)}",
                action="add the missing rhetorical components for this section",
            ))

    # Humanization items
    humanization = result.humanization
    if humanization.humanization_score < 0.6:
        items.append(RevisionItem(
            priority=1, target="global", category="humanization",
            issue=(
                f"humanization score {humanization.humanization_score:.2f} — "
                f"paper reads as AI-generated"
            ),
            action="address AI signals: " + "; ".join(humanization.ai_signals[:3]),
        ))

    for alignment in result.persona_alignment:
        if alignment.alignment_score < 0.55:
            items.append(RevisionItem(
                priority=1, target=alignment.section_title, category="persona",
                issue="persona/section mismatch",
                action=alignment.recommendation,
            ))
        elif alignment.issues:
            items.append(RevisionItem(
                priority=2, target=alignment.section_title, category="persona",
                issue="; ".join(alignment.issues[:2]),
                action=alignment.recommendation,
            ))

    if result.cross_persona_issues:
        items.append(RevisionItem(
            priority=1, target="paper", category="consistency",
            issue="cross-persona inconsistency detected",
            action=(
                "normalize terminology, certainty level, and contribution "
                "framing across sections"
            ),
        ))

    return sorted(items, key=lambda x: (x.priority, x.category, x.target))


def render_markdown_report(result: AnalysisResult) -> str:
    d = result.diagnostics
    h = result.humanization
    lines = [
        f"# Paper Review: {result.paper.title}",
        "",
        "## Humanization Score",
        f"**{h.humanization_score:.2f}** / 1.00",
        "",
    ]

    if h.ai_signals:
        lines.append("### AI Signals Detected")
        for signal in h.ai_signals:
            lines.append(f"- {signal}")
        lines.append("")

    if h.human_signals:
        lines.append("### Human Signals")
        for signal in h.human_signals:
            lines.append(f"- {signal}")
        lines.append("")

    lines.extend([
        "## Diagnostics Summary",
        f"- Sentence mean/stddev: {d.sentence_mean:.2f} / {d.sentence_stddev:.2f}",
        f"- Paragraph mean/stddev: {d.paragraph_mean:.2f} / {d.paragraph_stddev:.2f}",
        f"- Lexical diversity: {d.lexical_diversity:.3f}",
        f"- Hedge density: {d.hedge_density:.3f}",
        f"- Certainty density: {d.certainty_density:.3f}",
        f"- Passive voice signals: {d.passive_voice_signals}",
        "",
        "## Persona Alignment",
    ])
    for alignment in result.persona_alignment:
        lines.extend([
            f"### {alignment.section_title}",
            f"- Intended persona: {alignment.intended_persona or 'unassigned'}",
            f"- Alignment score: {alignment.alignment_score:.3f}",
            (
                f"- Style / rhetorical / epistemic / section-fit: "
                f"{alignment.style_alignment:.3f} / "
                f"{alignment.rhetorical_alignment:.3f} / "
                f"{alignment.epistemic_alignment:.3f} / "
                f"{alignment.section_fitness:.3f}"
            ),
        ])
        if alignment.issues:
            lines.append(f"- Issues: {'; '.join(alignment.issues)}")
        lines.append(f"- Recommendation: {alignment.recommendation}")
        lines.append("")

    if result.section_reviews:
        lines.extend(["## LLM Section Reviews", ""])
        lines.append("| Section | Score | Accuracy | Voice | Completeness | Clarity | Humanness | Issues |")
        lines.append("|---------|-------|----------|-------|--------------|---------|-----------|--------|")
        for sr in result.section_reviews:
            dim_scores = {d.name: d.score for d in sr.dimensions}
            lines.append(
                f"| {sr.section_title} | {sr.weighted_score:.1f} "
                f"| {dim_scores.get('accuracy', '-')} "
                f"| {dim_scores.get('voice', '-')} "
                f"| {dim_scores.get('completeness', '-')} "
                f"| {dim_scores.get('clarity', '-')} "
                f"| {dim_scores.get('humanness', '-')} "
                f"| {len(sr.issues)} |"
            )
        lines.append("")
        if result.overall_score > 0:
            lines.append(f"**Overall LLM Score: {result.overall_score:.1f} / 10**")
            lines.append("")

    lines.extend([
        "## Cross-Persona Consistency",
        f"- Score: {result.cross_persona_consistency:.3f}",
    ])
    if result.cross_persona_issues:
        for issue in result.cross_persona_issues:
            lines.append(f"- {issue}")
    lines.append("")

    lines.append("## Revision Plan")
    for item in result.revision_plan:
        lines.append(
            f"- P{item.priority} [{item.category}] {item.target}: "
            f"{item.issue} -> {item.action}",
        )

    return "\n".join(lines) + "\n"


def write_outputs(
    result: AnalysisResult,
    json_out: Path | None,
    report_out: Path | None,
    rewrite_out: Path | None,
) -> None:
    if json_out:
        json_out.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    if report_out:
        report_out.write_text(render_markdown_report(result), encoding="utf-8")
    if rewrite_out:
        rewrite_out.write_text(result.paper.raw_text, encoding="utf-8")


def emit_json_line(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False))
