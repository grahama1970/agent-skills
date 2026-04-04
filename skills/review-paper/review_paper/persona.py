"""Persona profile loading and 4-dimensional section alignment scoring."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from .models import PaperModel, PersonaAlignmentResult, PersonaProfile


def load_personas(path: Path | None) -> dict[str, PersonaProfile]:
    if path is None:
        return {}
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(raw)
    else:
        data = yaml.safe_load(raw)
    profiles: dict[str, PersonaProfile] = {}
    for key, value in (data or {}).items():
        if isinstance(value, dict):
            payload = {"name": value.get("name", key), **value}
            profiles[key.lower()] = PersonaProfile.model_validate(payload)
    return profiles


def _ratio(hits: int, total: int) -> float:
    return min(1.0, hits / total) if total > 0 else 0.0


def _hedging_target_score(target: str, density: float) -> float:
    ranges = {
        "low": (0.0, 0.01),
        "medium": (0.005, 0.03),
        "high": (0.02, 0.08),
    }
    lo, hi = ranges.get(target, ranges["medium"])
    if lo <= density <= hi:
        return 1.0
    distance = min(abs(density - lo), abs(density - hi))
    return max(0.0, 1.0 - distance * 25)


def evaluate_persona_alignment(
    paper: PaperModel,
    personas: dict[str, PersonaProfile],
) -> tuple[list[PersonaAlignmentResult], float, list[str]]:
    results: list[PersonaAlignmentResult] = []
    dominant_markers: dict[str, str] = {}

    for section in paper.sections:
        title_key = section.title.lower()
        persona = personas.get(title_key) or personas.get(section.id.lower())
        body = " ".join(p.text for p in section.paragraphs)
        lowered = body.lower()
        tokens = [
            w.strip(".,;:!?()[]{}\"'").lower()
            for w in body.split()
            if w.strip()
        ]
        total = max(1, len(tokens))

        if persona is None:
            results.append(
                PersonaAlignmentResult(
                    section_id=section.id,
                    section_title=section.title,
                    intended_persona=None,
                    alignment_score=0.5,
                    style_alignment=0.5,
                    rhetorical_alignment=0.5,
                    epistemic_alignment=0.5,
                    section_fitness=0.5,
                    issues=["no persona profile supplied for this section"],
                    recommendation=(
                        "add a persona profile or mark this section as "
                        "intentionally unassigned"
                    ),
                ),
            )
            continue

        preferred_hits = sum(
            lowered.count(marker.lower()) for marker in persona.preferred_markers
        )
        discouraged_hits = sum(
            lowered.count(marker.lower()) for marker in persona.discouraged_markers
        )
        rhetorical_hits = sum(
            lowered.count(pref.lower()) for pref in persona.rhetorical_preferences
        )
        hedge_set = {"may", "might", "could", "suggests", "appears", "likely"}
        hedge_density = sum(1 for t in tokens if t in hedge_set) / total

        style_alignment = max(
            0.0,
            min(
                1.0,
                _ratio(preferred_hits, max(1, len(persona.preferred_markers)))
                - _ratio(
                    discouraged_hits,
                    max(1, len(persona.discouraged_markers) or 1),
                )
                * 0.5,
            ),
        )
        rhetorical_alignment = _ratio(
            rhetorical_hits, max(1, len(persona.rhetorical_preferences)),
        )
        epistemic_alignment = _hedging_target_score(
            persona.hedging_target, hedge_density,
        )
        section_fitness = persona.section_affinity.get(title_key, 0.6)
        alignment_score = round(
            (style_alignment + rhetorical_alignment + epistemic_alignment + section_fitness) / 4,
            3,
        )

        issues: list[str] = []
        if preferred_hits == 0 and persona.preferred_markers:
            issues.append("expected persona markers are largely absent")
        if discouraged_hits > 0:
            issues.append("discouraged persona markers appear in the section")
        if rhetorical_alignment < 0.34:
            issues.append(
                "rhetorical behavior does not strongly reflect the persona brief",
            )
        if section_fitness < 0.5:
            issues.append("persona profile has weak affinity for this section type")

        recommendation = "retain persona and revise flagged paragraphs"
        if section_fitness < 0.5:
            recommendation = (
                "consider reassigning this section to a better-fit persona"
            )
        elif alignment_score < 0.55:
            recommendation = (
                "keep the section purpose but rewrite for persona consistency"
            )

        marker_name = (
            persona.preferred_markers[0] if persona.preferred_markers else persona.name
        )
        dominant_markers[section.title] = marker_name
        results.append(
            PersonaAlignmentResult(
                section_id=section.id,
                section_title=section.title,
                intended_persona=persona.name,
                alignment_score=alignment_score,
                style_alignment=round(style_alignment, 3),
                rhetorical_alignment=round(rhetorical_alignment, 3),
                epistemic_alignment=round(epistemic_alignment, 3),
                section_fitness=round(section_fitness, 3),
                issues=issues,
                recommendation=recommendation,
            ),
        )

    cross_issues: list[str] = []
    if results:
        scores = [r.alignment_score for r in results]
        consistency = sum(scores) / len(scores)
    else:
        consistency = 1.0

    low_sections = [r.section_title for r in results if r.alignment_score < 0.5]
    if len(low_sections) >= 2:
        cross_issues.append(
            f"multiple sections show persona drift: {', '.join(low_sections)}",
        )

    if (
        len(set(dominant_markers.values())) == len(dominant_markers)
        and len(dominant_markers) > 3
    ):
        cross_issues.append(
            "personas may be too stylistically fragmented across adjacent sections",
        )
        consistency = min(consistency, 0.72)

    return results, round(consistency, 3), cross_issues
